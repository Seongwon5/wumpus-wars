"""웜퍼스 워즈 토너먼트: 스위스 예선 → 더블 일리미네이션 본선.

  python -m wumpus tournament                      화면 (GUI) 을 연다: 봇 폴더 고르기 · 시작 · 진행 · 공개 범위 · zip 내보내기
  python -m wumpus tournament run  <폴더> --bots <학생 봇 폴더>    화면 없이 만들고 끝까지 돌린다 (멈췄다 다시 돌리면 이어서)
  python -m wumpus tournament pack <폴더> [--hide 8]            다른 컴퓨터에서 열 zip 하나로 묶는다

토너먼트 폴더:
  config.json   팀 · 설정 · 맵 목록        maps/   토너먼트를 만들 때 새로 생성한 맵 (기본 21개)
  bots/         봇 코드 사본 (만든 때 그대로)  state.json  예선 · 대진표 · 모든 판의 결과
  replays/<판>.js  리플레이 (gzip + base64, 브라우저가 file:// 에서도 읽는다)
  data.js       화면이 읽는 요약 (state 와 같은 내용)
"""
import base64
import datetime
import gzip
import json
import math
import multiprocessing as mp
import multiprocessing.connection as mpc
import os
import random
import shutil
import threading
import time
import zipfile

from . import guard
from .engine import run_match
from .maps import generate, load_map, save_map

VIEWER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viewer')
GAME_TIMEOUT = 600                      # 한 판의 시간 한도 (초). 넘기면 그때 코드가 돌던 팀의 실격


# ---------------------------------------------------------------- 저장 · 불러오기
def _jload(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _jsave(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


def find_bots(bots_dir):
    """학생 봇 폴더: <bots_dir>/<이름>/main.py 또는 <bots_dir>/<이름>.py. [(이름, 경로)]"""
    out = []
    for e in sorted(os.listdir(bots_dir)):
        p = os.path.join(bots_dir, e)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, 'main.py')):
            out.append((e, os.path.join(p, 'main.py')))
        elif e.endswith('.py') and os.path.isfile(p):
            out.append((e[:-3], p))
    return out


def scan_bots(bots_dir):
    """봇마다 코드 검사 결과. [{name, path, ok, problems}]"""
    res = []
    for name, path in find_bots(bots_dir):
        try:
            src = open(path, encoding='utf-8').read()
            bad = list(guard.check(src))
            if not guard.has_turn(src):
                bad.append('turn(me, view, memory) 함수가 없다')
        except Exception as e:                      # 읽을 수 없는 파일 (인코딩 등)
            bad = ['파일을 읽을 수 없다: %s' % e]
        res.append({'name': name, 'path': path, 'ok': not bad, 'problems': bad[:5]})
    return res


# ---------------------------------------------------------------- 만들기
def create(tdir, bots_dir, name=None, n_maps=21, swiss_rounds=7, seed=None, jobs=None):
    """토너먼트 폴더를 만든다: 봇 사본, 새 맵 n_maps 개, 설정."""
    if os.path.exists(os.path.join(tdir, 'config.json')):
        raise FileExistsError('이미 토너먼트가 있는 폴더다: ' + tdir)
    bots = find_bots(bots_dir)
    if len(bots) < 2:
        raise ValueError('봇이 둘 이상 있어야 한다 (%s 에서 %d개 찾음)' % (bots_dir, len(bots)))
    seed = int(seed if seed is not None else random.SystemRandom().randrange(1, 10 ** 6))
    os.makedirs(os.path.join(tdir, 'bots'), exist_ok=True)
    os.makedirs(os.path.join(tdir, 'maps'), exist_ok=True)
    os.makedirs(os.path.join(tdir, 'replays'), exist_ok=True)
    teams = []
    for i, (nm, path) in enumerate(bots):
        d = os.path.join(tdir, 'bots', '%03d' % i)
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(path, os.path.join(d, 'main.py'))
        teams.append({'id': i, 'name': nm})
    rng = random.Random(seed)
    maps = []
    for k in range(n_maps):                          # 토너먼트마다 새 맵 (맵 시드는 토너먼트 시드에서)
        ms = rng.randrange(10 ** 5, 10 ** 6)
        g = generate(ms, name='T%02d_%d' % (k + 1, ms))
        save_map(g, os.path.join(tdir, 'maps', '%02d.json' % (k + 1)))
        maps.append({'file': '%02d.json' % (k + 1), 'name': g.name, 'w': g.w, 'h': g.h, 'sym': g.sym, 'seed': ms})
    cfg = {'format': 'wumpus-tournament-1', 'name': name or os.path.basename(os.path.abspath(tdir)), 'seed': seed,
           'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'teams': teams, 'maps': maps,
           'swiss_rounds': int(swiss_rounds), 'jobs': jobs, 'id': '%s-%d' % (datetime.datetime.now().strftime('%Y%m%d%H%M%S'), seed)}
    _jsave(os.path.join(tdir, 'config.json'), cfg)
    st = {'phase': 'swiss', 'games': {}, 'swiss': [], 'standings': [], 'bracket': None, 'log': []}
    _jsave(os.path.join(tdir, 'state.json'), st)
    write_data(tdir)
    return cfg


# ---------------------------------------------------------------- 한 판 (따로 된 프로세스)
def _game(task):
    gid, red_path, blue_path, names, map_path, seed, out_js = task
    rep = run_match(load_map(map_path), [red_path, blue_path], seed=seed, names=names)
    rep['frames'] = [{k: v for k, v in fr.items() if k != 'd'} for fr in rep['frames']]   # 봇 머릿속 기록은 뺀다 (뷰어가 쓰지 않음)
    raw = json.dumps(rep, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    b64 = base64.b64encode(gzip.compress(raw, 6)).decode('ascii')
    with open(out_js + '.tmp', 'w', encoding='ascii') as f:
        f.write('__wwReplay(%s,"%s");\n' % (json.dumps(gid), b64))
    os.replace(out_js + '.tmp', out_js)
    m = rep['meta']
    return {'winner': m['winner'], 'reason': m['reason'], 'rounds': m['rounds'], 'score': m['score']}


def _child(task, conn, turn):
    try:
        conn.send(('ok', _game(task)))
    except BaseException as e:
        conn.send(('err', ('%s: %s' % (type(e).__name__, e))[:200]))


def _run_tasks(tasks, jobs, on_done, stop):
    """판마다 새 프로세스 (동시에 jobs 판). on_done(task, 결과) 를 끝난 차례대로 부른다."""
    ctx = mp.get_context('spawn')
    todo = list(tasks)
    running = {}
    while (todo or running) and not stop.is_set():
        while todo and len(running) < max(1, jobs):
            t = todo.pop(0)
            rx, tx = ctx.Pipe(False)
            turn = ctx.RawValue('i', -1)
            p = ctx.Process(target=_child, args=(t, tx, turn), daemon=True)
            p.start()
            tx.close()
            running[t[0]] = (p, rx, turn, time.time(), t)
        ready = mpc.wait([v[1] for v in running.values()], timeout=0.3)
        for gid, (p, rx, turn, t0, t) in list(running.items()):
            res = None
            if rx in ready:
                try:
                    kind, val = rx.recv()
                except (EOFError, OSError):
                    kind, val = 'err', '경기 프로세스가 죽었다'
                res = val if kind == 'ok' else {'winner': -1, 'reason': '무효: 엔진 오류 (%s)' % val, 'rounds': 0, 'score': [0, 0]}
            elif time.time() - t0 > GAME_TIMEOUT:
                p.kill()
                tm = turn.value
                res = {'winner': 1 - tm if tm in (0, 1) else -1, 'reason': '실격: 판 시간 한도 초과', 'rounds': 0, 'score': [0, 0]}
            if res is not None:
                p.join(10)
                rx.close()
                del running[gid]
                on_done(t, res)
    for p, rx, *_ in running.values():
        p.kill()


# ---------------------------------------------------------------- 스위스 예선
def _swiss_table(cfg, st):
    """팀마다 점수 (판 승 1, 무 0.5, 부전승 1), 상대 점수 합 (뷰홀츠), 바친 금 합."""
    n = len(cfg['teams'])
    pts, gold, opp = [0.0] * n, [0] * n, [[] for _ in range(n)]
    wdl = [[0, 0, 0] for _ in range(n)]
    byes = [0] * n
    for rnd in st['swiss']:
        for p in rnd:
            a, b = p['a'], p['b']
            if b is None:
                pts[a] += 1.0
                byes[a] += 1
                continue
            opp[a].append(b)
            opp[b].append(a)
            for gid in p['games']:
                g = st['games'].get(gid)
                if not g or 'res' not in g:
                    continue
                w = g['res']['winner']
                ta, tb = (a, b) if g['red'] == a else (b, a)
                sc = g['res']['score']
                gold[ta] += sc[0]
                gold[tb] += sc[1]
                if w == 0:
                    pts[ta] += 1; wdl[ta][0] += 1; wdl[tb][2] += 1
                elif w == 1:
                    pts[tb] += 1; wdl[tb][0] += 1; wdl[ta][2] += 1
                else:
                    pts[ta] += .5; pts[tb] += .5; wdl[ta][1] += 1; wdl[tb][1] += 1
    buch = [sum(pts[o] for o in opp[i]) for i in range(n)]
    rng = random.Random(cfg['seed'])
    tie = [rng.random() for _ in range(n)]
    order = sorted(range(n), key=lambda i: (-pts[i], -buch[i], -gold[i], tie[i]))
    return [{'team': i, 'rank': r + 1, 'pts': pts[i], 'buch': buch[i], 'gold': gold[i], 'wdl': wdl[i], 'byes': byes[i]}
            for r, i in enumerate(order)], opp, byes


def _swiss_pair(cfg, st, rnd):
    """점수가 비슷한 팀끼리, 이미 만난 상대는 피해서 짝짓는다. 홀수면 맨 아래 (부전승을 아직 안 받은) 팀이 부전승."""
    table, opp, byes = _swiss_table(cfg, st)
    order = [r['team'] for r in table]
    bye = None
    if len(order) % 2:
        for t in reversed(order):
            if byes[t] == 0:
                bye = t
                break
        bye = order[-1] if bye is None else bye
        order.remove(bye)
    pairs, left = [], list(order)
    while left:
        a = left.pop(0)
        k = next((i for i, b in enumerate(left) if b not in opp[a]), 0)
        pairs.append((a, left.pop(k)))
    n_maps = len(cfg['maps'])
    out = []
    for k, (a, b) in enumerate(pairs):
        mi = (rnd * 5 + k) % n_maps                   # 짝마다 다른 맵, 양쪽 진영으로 두 판
        gids = []
        for s in (0, 1):
            gid = 's%d-%02d-%d' % (rnd + 1, k + 1, s)
            red, blue = (a, b) if s == 0 else (b, a)
            st['games'][gid] = {'id': gid, 'red': red, 'blue': blue, 'map': mi, 'seed': cfg['seed'] % 1000 + rnd}
            gids.append(gid)
        out.append({'a': a, 'b': b, 'games': gids})
    if bye is not None:
        out.append({'a': bye, 'b': None, 'games': []})
    return out


# ---------------------------------------------------------------- 더블 일리미네이션
def _seed_positions(size):
    pos = [1, 2]
    while len(pos) < size:
        n = len(pos) * 2
        pos = [x for s in pos for x in (s, n + 1 - s)]
    return pos


def build_bracket(n):
    """n 팀의 더블 일리미네이션 (크기는 2 의 거듭제곱, 빈 자리는 부전승). 경기 사전과 순서를 돌려준다.
    자리 (slot) 는 {'seed': k} · {'win': 경기} · {'lose': 경기}."""
    k = max(1, math.ceil(math.log2(max(2, n))))
    size = 2 ** k
    M = {}

    def add(mid, br, rnd, idx, a, b):
        M[mid] = {'id': mid, 'br': br, 'rnd': rnd, 'idx': idx, 'src': [a, b]}
        return mid
    pos = _seed_positions(size)
    wb = []
    for r in range(1, k + 1):
        cur = []
        for i in range(size >> r):
            if r == 1:
                a, b = {'seed': pos[2 * i]}, {'seed': pos[2 * i + 1]}
            else:
                a, b = {'win': wb[-1][2 * i]}, {'win': wb[-1][2 * i + 1]}
            cur.append(add('W%d-%d' % (r, i + 1), 'W', r, i, a, b))
        wb.append(cur)
    lb = []
    if k >= 2:
        cur = []
        for i in range(size >> 2):                        # 패자조 1 라운드: 승자조 1 라운드 패자끼리
            cur.append(add('L1-%d' % (i + 1), 'L', 1, i, {'lose': wb[0][2 * i]}, {'lose': wb[0][2 * i + 1]}))
        lb.append(cur)
        for j in range(1, k):                             # 패자조 짝수 라운드: 승자조 j+1 라운드 패자가 내려온다
            losers = list(wb[j])
            if j % 2 == 1:
                losers.reverse()                          # 같은 상대를 바로 다시 만나지 않게 뒤집는다
            cur = []
            for i, mid in enumerate(lb[-1]):
                cur.append(add('L%d-%d' % (2 * j, i + 1), 'L', 2 * j, i, {'win': mid}, {'lose': losers[i]}))
            lb.append(cur)
            if j < k - 1:                                 # 패자조 홀수 라운드: 패자조끼리
                cur = []
                for i in range(len(lb[-1]) // 2):
                    cur.append(add('L%d-%d' % (2 * j + 1, i + 1), 'L', 2 * j + 1, i, {'win': lb[-1][2 * i]}, {'win': lb[-1][2 * i + 1]}))
                lb.append(cur)
    lb_final = lb[-1][0] if lb else None
    add('GF', 'GF', 1, 0, {'win': wb[-1][0]}, {'win': lb_final} if lb_final else {'lose': wb[-1][0]})
    add('GF2', 'GF2', 1, 0, {'win': 'GF'}, {'lose': 'GF'})
    return {'size': size, 'k': k, 'n': n, 'matches': M, 'wb': wb, 'lb': lb}


def _slot_team(B, slot, seeds):
    """자리에 들어갈 팀 (정해지지 않았으면 None, 빈 자리 (부전승) 면 -1)."""
    if 'seed' in slot:
        s = slot['seed']
        return seeds[s - 1] if s <= len(seeds) else -1
    m = B['matches'][slot.get('win') or slot.get('lose')]
    if 'win' in slot:
        return m.get('winner')
    return m.get('loser')


def _resolve(B, seeds):
    """정해진 자리 채우기 · 부전승 처리. 새로 붙을 수 있게 된 경기 목록 (두 팀이 다 있고 아직 안 치른) 을 돌려준다."""
    M = B['matches']
    order = list(M)                                       # 만든 순서 = 앞 경기가 먼저
    changed = True
    while changed:
        changed = False
        for mid in order:
            m = M[mid]
            if 'winner' in m:
                continue
            if mid == 'GF2':
                gf = M['GF']
                if 'winner' not in gf:
                    continue
                if gf['winner'] == gf['teams'][0]:         # 승자조 쪽이 이기면 리셋 없이 끝
                    m.update(teams=[gf['winner'], -1], winner=gf['winner'], loser=-1, bye=True, skip=True)
                    changed = True
                    continue
            ts = [_slot_team(B, s, seeds) for s in m['src']]
            m['teams'] = ts
            if None in ts:
                continue
            if ts[0] == -1 or ts[1] == -1:                  # 부전승 (둘 다 빈 자리면 빈 자리가 올라간다)
                w = ts[1] if ts[0] == -1 else ts[0]
                m.update(winner=w, loser=-1, bye=True)
                changed = True
    return [mid for mid in order if 'winner' not in M[mid] and None not in M[mid].get('teams', [None]) and -1 not in M[mid]['teams']]


def _layout(B):
    """화면 배치: 열 (시간 순서) 과 세로 자리. 부전승 경기는 그리지 않는다 (구조로 미리 정해진다)."""
    M = B['matches']
    col = {}

    def c(mid):
        if mid in col:
            return col[mid]
        m = M[mid]
        prev = [c(s.get('win') or s.get('lose')) for s in m['src'] if 'seed' not in s]
        base = max(prev) if prev else 0
        col[mid] = base + (1 if m.get('shown', True) else 0)
        return col[mid]
    for mid in M:
        c(mid)
    for mid in M:
        M[mid]['col'] = col[mid]
    slot = [0.0]

    def lay(mid, br):
        m = M[mid]
        ys = []
        for s in m['src']:
            src = s.get('win') or s.get('lose')
            if src and ('win' in s) and M[src]['br'] in br:
                y = lay(src, br)
                if y is not None:
                    ys.append(y)
        if m.get('shown', True):
            y = sum(ys) / len(ys) if ys else slot[0]
            if not ys:
                slot[0] += 1
            m['y'] = y
            return y
        return sum(ys) / len(ys) if ys else None
    lay(B['wb'][-1][0], ('W',))
    top = slot[0]
    slot[0] = top + 0.8                                    # 패자조는 승자조 아래
    if B['lb']:
        lay(B['lb'][-1][0], ('L',))
    B['wb_rows'] = top
    B['rows'] = slot[0]
    gy = M[B['wb'][-1][0]].get('y', 0)
    M['GF']['y'] = gy
    M['GF2']['y'] = gy


def _mark_structural_byes(B, n):
    """시드 배치만으로 정해지는 부전승 (빈 자리가 낀 경기) 을 표시한다: 화면에 그리지 않는다."""
    M = B['matches']
    empty = {}

    def e(slot):                                          # 이 자리가 결과와 상관없이 비어 있나
        if 'seed' in slot:
            return slot['seed'] > n
        src = slot.get('win') or slot.get('lose')
        m = M[src]
        ea, eb = e(m['src'][0]), e(m['src'][1])
        if 'win' in slot:
            return ea and eb
        return ea or eb                                   # 부전승 경기에는 패자가 없다
    for mid, m in M.items():
        if mid in ('GF', 'GF2'):
            m['shown'] = True
            continue
        m['shown'] = not (e(m['src'][0]) or e(m['src'][1]))


# ---------------------------------------------------------------- 진행
class Runner:
    """토너먼트 하나를 끝까지 돌린다 (멈췄다 다시 부르면 이어서). 진행은 status 로 본다."""

    def __init__(self, tdir, jobs=None, log=print):
        self.tdir = tdir
        self.cfg = _jload(os.path.join(tdir, 'config.json'))
        self.st = _jload(os.path.join(tdir, 'state.json'))
        self.jobs = jobs or self.cfg.get('jobs') or max(1, (os.cpu_count() or 2) - 2)
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.log_fn = log
        self.done = 0
        self.total = 0
        self.t0 = time.time()
        self.last_save = 0

    def log(self, s):
        line = time.strftime('%H:%M:%S ') + s
        self.st['log'] = (self.st.get('log') or [])[-200:] + [line]
        if self.log_fn:
            self.log_fn(line)

    def save(self, force=True):
        if not force and time.time() - self.last_save < 3:
            return
        self.last_save = time.time()
        _jsave(os.path.join(self.tdir, 'state.json'), self.st)
        write_data(self.tdir, self.cfg, self.st)

    def _task(self, gid):
        g = self.st['games'][gid]
        names = [self.cfg['teams'][g['red']]['name'], self.cfg['teams'][g['blue']]['name']]
        bp = lambda t: os.path.join(self.tdir, 'bots', '%03d' % t, 'main.py')
        return (gid, bp(g['red']), bp(g['blue']), names, os.path.join(self.tdir, 'maps', self.cfg['maps'][g['map']]['file']),
                g['seed'], os.path.join(self.tdir, 'replays', gid + '.js'))

    def _play(self, gids):
        todo = [g for g in gids if 'res' not in self.st['games'][g]]
        if not todo:
            return

        def done(task, res):
            with self.lock:
                self.st['games'][task[0]]['res'] = res
                self.done += 1
                self.save(force=False)
        _run_tasks([self._task(g) for g in todo], self.jobs, done, self.stop)
        self.save()

    def status(self):
        st = self.st
        el = time.time() - self.t0
        rate = self.done / el if el > 1 and self.done else 0
        left = max(0, self.total - self.games_done())
        return {'phase': st['phase'], 'done': self.games_done(), 'total': self.total, 'eta': (left / rate) if rate else None,
                'log': (st.get('log') or [])[-12:], 'running': not self.stop.is_set()}

    def games_done(self):
        return sum(1 for g in self.st['games'].values() if 'res' in g)

    def estimate_total(self):
        n = len(self.cfg['teams'])
        sw = self.cfg['swiss_rounds'] * (n // 2) * 2
        bm = sum(1 for m in (self.st['bracket'] or {}).get('matches', {}).values() if m.get('shown') and m['id'] != 'GF2') if self.st['bracket'] else max(1, 2 * n - 2)
        return sw + bm * len(self.cfg['maps'])

    def run(self):
        cfg, st = self.cfg, self.st
        self.total = self.estimate_total()
        # 1) 스위스 예선
        while st['phase'] == 'swiss' and not self.stop.is_set():
            r = len(st['swiss'])
            if r and any('res' not in st['games'][g] for p in st['swiss'][-1] for g in p['games']):
                self._play([g for p in st['swiss'][-1] for g in p['games']])
                continue
            if r >= cfg['swiss_rounds']:
                table, _, _ = _swiss_table(cfg, st)
                st['standings'] = table
                st['seeds'] = [row['team'] for row in table]
                B = build_bracket(len(cfg['teams']))
                _mark_structural_byes(B, len(cfg['teams']))
                _layout(B)
                st['bracket'] = {'size': B['size'], 'k': B['k'], 'n': B['n'], 'matches': B['matches'],
                                 'wb': B['wb'], 'lb': B['lb'], 'rows': B['rows'], 'wb_rows': B['wb_rows']}
                st['phase'] = 'bracket'
                self.total = self.estimate_total()
                self.log('예선 끝. 본선 대진표: %d팀 (크기 %d)' % (B['n'], B['size']))
                self.save()
                break
            st['swiss'].append(_swiss_pair(cfg, st, r))
            st['standings'] = _swiss_table(cfg, st)[0]
            self.log('예선 %d 라운드 시작 (%d쌍)' % (r + 1, len(st['swiss'][-1])))
            self.save()
            self._play([g for p in st['swiss'][-1] for g in p['games']])
            st['standings'] = _swiss_table(cfg, st)[0]
            self.save()
        # 2) 본선
        while st['phase'] == 'bracket' and not self.stop.is_set():
            B = st['bracket']
            ready = _resolve(B, st['seeds'])
            for mid in ready:
                m = B['matches'][mid]
                if 'games' not in m:
                    a, b = m['teams']
                    gids = []
                    for i in range(len(cfg['maps'])):     # 맵마다 한 판, 진영은 번갈아
                        gid = '%s-%02d' % (mid, i + 1)
                        red, blue = (a, b) if i % 2 == 0 else (b, a)
                        st['games'][gid] = {'id': gid, 'red': red, 'blue': blue, 'map': i, 'seed': cfg['seed'] % 1000 + 100}
                        gids.append(gid)
                    m['games'] = gids
            if not ready:
                if 'winner' in B['matches']['GF2']:
                    st['phase'] = 'done'
                    st['champion'] = B['matches']['GF2']['winner']
                    self.log('끝. 우승: %s' % cfg['teams'][st['champion']]['name'])
                    self.save()
                break
            self.log('본선: %s' % ', '.join(ready[:6]) + (' 외 %d' % (len(ready) - 6) if len(ready) > 6 else ''))
            self.save()
            self._play([g for mid in ready for g in B['matches'][mid]['games']])
            if self.stop.is_set():
                break
            for mid in ready:
                self._decide(B['matches'][mid])
            self.save()

    def _decide(self, m):
        """맵 21판의 결과로 승자를 정한다: 이긴 판 수 → 바친 금 합 → 높은 시드."""
        a, b = m['teams']
        wins, gold = {a: 0, b: 0}, {a: 0, b: 0}
        for gid in m['games']:
            g = self.st['games'][gid]
            res = g['res']
            sc = res['score']
            gold[g['red']] += sc[0]
            gold[g['blue']] += sc[1]
            if res['winner'] == 0:
                wins[g['red']] += 1
            elif res['winner'] == 1:
                wins[g['blue']] += 1
        seeds = self.st['seeds']
        key = lambda t: (wins[t], gold[t], -seeds.index(t))
        w = max((a, b), key=key)
        m.update(winner=w, loser=b if w == a else a, score=[wins[a], wins[b]], gold=[gold[a], gold[b]])


# ---------------------------------------------------------------- 화면용 요약 · 묶기
def write_data(tdir, cfg=None, st=None):
    cfg = cfg or _jload(os.path.join(tdir, 'config.json'))
    st = st or _jload(os.path.join(tdir, 'state.json'))
    games = {gid: {'r': g['red'], 'b': g['blue'], 'm': g['map'], **({'w': g['res']['winner'], 's': g['res']['score'], 'n': g['res']['rounds'],
                                                                    'why': g['res']['reason']} if 'res' in g else {})}
             for gid, g in st['games'].items()}
    data = {'config': {k: cfg[k] for k in ('name', 'created', 'seed', 'teams', 'maps', 'swiss_rounds', 'id')},
            'phase': st['phase'], 'swiss': st['swiss'], 'standings': st['standings'], 'seeds': st.get('seeds'),
            'bracket': st['bracket'], 'games': games, 'champion': st.get('champion'), 'hide': st.get('hide')}
    txt = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(tdir, 'data.js.tmp'), 'w', encoding='utf-8') as f:
        f.write('window.TOURNAMENT=' + txt + ';\n')
    os.replace(os.path.join(tdir, 'data.js.tmp'), os.path.join(tdir, 'data.js'))
    return data


def write_viewer(tdir):
    """리플레이 뷰어 (빈 뷰어, 화면이 리플레이를 보내 준다) 와 대진표 화면을 폴더에 쓴다."""
    from .replay import write_html
    write_html(None, os.path.join(tdir, 'viewer.html'))
    shutil.copyfile(os.path.join(VIEWER_DIR, 'tournament.html'), os.path.join(tdir, 'index.html'))


def pack(tdir, out=None, hide=None):
    """다른 컴퓨터에서 열 zip 하나: index.html (대진표) · viewer.html · data.js · replays/ · maps/. 봇 코드는 넣지 않는다."""
    cfg = _jload(os.path.join(tdir, 'config.json'))
    st = _jload(os.path.join(tdir, 'state.json'))
    st['hide'] = hide
    write_data(tdir, cfg, st)
    write_viewer(tdir)
    out = out or os.path.join(os.path.dirname(os.path.abspath(tdir)), cfg['name'] + '.zip')
    root = cfg['name']
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in ('index.html', 'viewer.html', 'data.js'):
            z.write(os.path.join(tdir, f), root + '/' + f)
        for sub in ('replays', 'maps'):
            d = os.path.join(tdir, sub)
            for f in sorted(os.listdir(d)):
                if not f.endswith('.tmp'):
                    z.write(os.path.join(d, f), root + '/' + sub + '/' + f, compress_type=zipfile.ZIP_STORED if sub == 'replays' else zipfile.ZIP_DEFLATED)
        z.writestr(root + '/열어 보기.txt', '압축을 풀고 index.html 을 브라우저 (크롬 · 엣지) 로 여세요. 인터넷 없이 열립니다.\n')
    return out


# ---------------------------------------------------------------- 프로그램 (브라우저 화면 + 작은 서버)
RECENT = os.path.join(os.path.expanduser('~'), '.wumpus_tournaments.json')


def _remember(tdir):
    items = [p for p in (_jload(RECENT, []) or []) if os.path.abspath(p) != os.path.abspath(tdir)]
    _jsave(RECENT, [os.path.abspath(tdir)] + items[:19])


def _read_data(tdir):
    """data.js (화면용 요약) 를 읽는다. zip 으로 받은 토너먼트에는 config · state 가 없고 이것만 있다."""
    p = os.path.join(tdir, 'data.js')
    if not os.path.isfile(p):
        return None
    txt = open(p, encoding='utf-8').read().strip()
    return json.loads(txt[len('window.TOURNAMENT='):].rstrip(';'))


def _pick(kind):
    """폴더 · zip 고르기 창 (tkinter). 따로 된 프로세스로 띄운다 (서버 스레드에서 창을 열 수 없으므로)."""
    import subprocess
    import sys
    code = ('import tkinter as tk\nfrom tkinter import filedialog\nr=tk.Tk();r.withdraw();r.attributes("-topmost",True)\n'
            + ('p=filedialog.askopenfilename(title="토너먼트 zip",filetypes=[("zip","*.zip")])\n' if kind == 'zip'
               else 'p=filedialog.askdirectory(title="폴더 고르기")\n') + 'print(p or "")')
    out = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], capture_output=True, text=True, encoding='utf-8', timeout=600)
    return out.stdout.strip()


def _estimate(n, maps, rounds, jobs, sec=6.0):
    games = rounds * (n // 2) * 2 + max(1, 2 * n - 2) * maps
    return games, games * sec / max(1, jobs)


class App:
    def __init__(self):
        self.tdir = None
        self.runner = None
        self.thread = None

    def open(self, path):
        path = os.path.abspath(path.strip().strip('"'))
        if path.lower().endswith('.zip'):
            dest = os.path.splitext(path)[0]
            if not os.path.isdir(dest):
                with zipfile.ZipFile(path) as z:
                    top = {n.split('/')[0] for n in z.namelist()}
                    if len(top) == 1:                     # zip 안에 폴더 하나: 그 폴더째 푼다
                        z.extractall(os.path.dirname(dest))
                        dest = os.path.join(os.path.dirname(dest), top.pop())
                    else:
                        z.extractall(dest)
            path = dest
        if not os.path.isfile(os.path.join(path, 'data.js')):
            subs = [os.path.join(path, d) for d in os.listdir(path) if os.path.isfile(os.path.join(path, d, 'data.js'))] if os.path.isdir(path) else []
            if len(subs) == 1:
                path = subs[0]
            else:
                raise ValueError('토너먼트 폴더가 아니다 (data.js 가 없다): ' + path)
        self.close()
        self.tdir = path
        if not os.path.isfile(os.path.join(path, 'viewer.html')):
            write_viewer(path)
        _remember(path)
        if os.path.isfile(os.path.join(path, 'config.json')):
            self.runner = Runner(path, log=None)
            self.runner.total = self.runner.estimate_total()
            self.runner.stop.set()                         # 멈춘 토너먼트는 '이어서 돌리기' 로 다시 시작

    def start(self):
        if not self.runner or (self.thread and self.thread.is_alive()):
            return
        self.runner.stop.clear()
        self.runner.t0 = time.time()
        self.runner.done = 0

        def go():
            try:
                self.runner.run()
            except Exception as e:                        # 화면에 보이게 기록
                self.runner.log('오류로 멈췄다: %s' % e)
                self.runner.save()
            finally:
                self.runner.stop.set()
        self.thread = threading.Thread(target=go, daemon=True)
        self.thread.start()

    def stop(self):
        if self.runner:
            self.runner.stop.set()

    def close(self):
        self.stop()
        if self.thread:
            self.thread.join(15)
        self.tdir, self.runner, self.thread = None, None, None

    def status(self):
        if not self.tdir:
            return {'loaded': False}
        p = os.path.join(self.tdir, 'data.js')
        s = {'loaded': True, 'path': self.tdir, 'version': os.path.getmtime(p) if os.path.isfile(p) else 0, 'can_run': False}
        if self.runner:
            s.update(self.runner.status())
            s['running'] = bool(self.thread and self.thread.is_alive() and not self.runner.stop.is_set())
            s['can_run'] = self.runner.st['phase'] != 'done'
        else:
            s.update(phase='done', running=False, total=0, done=0)
        return s

    def handle(self, path, body):
        if path == 'status':
            return self.status()
        if path == 'data':
            return _read_data(self.tdir) if self.tdir else {}
        if path == 'recent':
            items = []
            for p in _jload(RECENT, []) or []:
                d = _read_data(p) if os.path.isdir(p) else None
                if d:
                    items.append({'path': p, 'name': d['config']['name'], 'teams': len(d['config']['teams']),
                                  'phase': {'swiss': '예선 중', 'bracket': '본선 중', 'done': '끝남'}.get(d['phase'], d['phase'])})
            return {'items': items}
        if path == 'pick':
            return {'path': _pick(body.get('kind'))}
        if path == 'scan':
            d = (body.get('bots') or '').strip().strip('"')
            if not os.path.isdir(d):
                raise ValueError('봇 폴더가 없다: ' + d)
            bots = scan_bots(d)
            jobs = max(1, (os.cpu_count() or 2) - 2)
            games, sec = _estimate(len(bots), 21, 7, jobs)
            return {'bots': bots, 'jobs': jobs,
                    'estimate': '예상: 약 %d판, 약 %d~%d분 (동시 %d판, 맵 21개 · 예선 7라운드 기준)' % (games, sec / 60, sec * 2 / 60, jobs),
                    'default_out': os.path.dirname(os.path.abspath(d))}
        if path == 'create':
            bots = (body.get('bots') or '').strip().strip('"')
            name = (body.get('name') or '').strip() or 'tournament_' + time.strftime('%Y%m%d_%H%M')
            safe = ''.join(c if c.isalnum() or c in '-_ ' else '_' for c in name).strip() or 'tournament'
            out = (body.get('out') or '').strip().strip('"') or os.path.dirname(os.path.abspath(bots))
            tdir = os.path.join(out, safe)
            create(tdir, bots, name=name, n_maps=int(body.get('maps') or 21), swiss_rounds=int(body.get('rounds') or 7), jobs=body.get('jobs'))
            write_viewer(tdir)
            self.open(tdir)
            self.start()
            return {'ok': True, 'path': tdir}
        if path == 'open':
            self.open(body.get('path') or '')
            return {'ok': True}
        if path == 'close':
            self.close()
            return {'ok': True}
        if path == 'stop':
            self.stop()
            return {'ok': True}
        if path == 'resume':
            self.start()
            return {'ok': True}
        if path == 'pack':
            if not self.tdir or not os.path.isfile(os.path.join(self.tdir, 'config.json')):
                raise ValueError('만든 토너먼트 폴더에서만 묶을 수 있다')
            return {'path': pack(self.tdir, hide=body.get('hide'))}
        raise ValueError('모르는 요청: ' + path)


def serve(port=8770, open_browser=True):
    """프로그램 화면을 띄운다: http://127.0.0.1:port"""
    import http.server
    import mimetypes
    import urllib.parse
    import webbrowser
    app = App()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, data, ctype):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _api(self, name, body):
            try:
                res = app.handle(name, body)
                self._send(200, json.dumps(res, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')
            except Exception as e:
                self._send(200, json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            p = urllib.parse.unquote(u.path)
            if p.startswith('/api/'):
                return self._api(p[5:], {})
            if p in ('/', '/index.html'):
                f = os.path.join(VIEWER_DIR, 'tournament.html')
            elif p.startswith('/t/') and app.tdir:
                f = os.path.normpath(os.path.join(app.tdir, p[3:]))
                if not f.startswith(os.path.normpath(app.tdir)):
                    return self._send(403, b'', 'text/plain')
            else:
                return self._send(404, b'', 'text/plain')
            if not os.path.isfile(f):
                return self._send(404, b'', 'text/plain')
            ct = mimetypes.guess_type(f)[0] or 'application/octet-stream'
            if ct.startswith('text/') or ct.endswith('javascript'):
                ct += '; charset=utf-8'
            with open(f, 'rb') as fh:
                self._send(200, fh.read(), ct)

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}') if n else {}
            if u.path.startswith('/api/'):
                return self._api(u.path[5:], body)
            self._send(404, b'', 'text/plain')

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), H)
    url = 'http://127.0.0.1:%d/' % port
    print('웜퍼스 워즈 토너먼트 프로그램:', url)
    print('이 창을 닫으면 프로그램이 끝난다 (돌던 토너먼트는 다음에 "불러오기" 로 이어서 돌릴 수 있다).')
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
