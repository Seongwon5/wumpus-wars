"""웜퍼스 워즈 명령줄 도구.

  python -m wumpus run    봇A 봇B  [--map 맵] [--seed N] [--open]     경기 하나 + 리플레이
  python -m wumpus scrim  봇A 봇B  [--maps all] [--seeds 1,2] [--jobs 4]  여러 맵 묶음 대전 (오프라인 스크림)
  python -m wumpus view   리플레이.json                              리플레이를 뷰어로 열기
  python -m wumpus viewer [--out viewer.html]                         빈 뷰어 (json 을 끌어다 놓아 연다)
  python -m wumpus maps   [list | show 맵 | gen --seed N --name 이름]    맵 목록 · 그림 · 만들기
  python -m wumpus new    새봇이름 [--from starter]                    봇 폴더 만들기
  python -m wumpus check  봇                                         봇 점검 (오류 · 시간)

pip install -e . 로 설치하면 'python -m wumpus' 대신 'wumpus' 만 써도 된다.
"""
import argparse
import concurrent.futures as cf
import csv
import os
import shutil
import sys
import time
import unicodedata

from . import __version__
from .engine import run_match, resolve_bot
from .maps import load_map, list_maps, generate, save_map, MAP_DIR
from .replay import save_json, load_json, write_html, open_in_browser

DEFAULT_MAP = 'temple_gate'


def _say(*a):
    print(*a, flush=True)


def _w(s):
    """글자 폭 (한글은 2칸)."""
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in str(s))


def _pad(s, n, right=False):
    s = str(s)
    sp = ' ' * max(0, n - _w(s))
    return sp + s if right else s + sp


def _team_errors(rep):
    """팀마다 오류 (예외 · 시간 초과) 사건 수와 첫 메시지 몇 개."""
    owner = {bid: t for t, bid in enumerate(rep['map']['base_ids'])}
    errs = [[0, []], [0, []]]
    for i, fr in enumerate(rep['frames']):
        for u in fr['u']:
            owner[u[0]] = u[1]
        for e in fr['e']:
            if e[0] == 'err':
                t = owner.get(e[1], -1)
                if t >= 0:
                    errs[t][0] += 1
                    if len(errs[t][1]) < 3:
                        errs[t][1].append(f'라운드 {i} 유닛 #{e[1]}: {e[2]}')
    return errs


def _winner_text(rep):
    m = rep['meta']
    if m['winner'] < 0:
        return '무승부'
    return f"{m['teams'][m['winner']]} ({m['names'][m['winner']]}) 승리"


def _ops_txt(m, t):
    o = (m.get('ops') or [None, None])[t]
    if not o:
        return ''
    return f" | 연산 (차례당) 평균 {o['avg']:,}, 최대 {o['max']:,}" + (f", 한도 초과 {o['over']}번" if o['over'] else '')


# ---------------- run ----------------
def cmd_run(a):
    gmap = load_map(a.map)
    t0 = time.time()
    rep = run_match(gmap, [a.red, a.blue], seed=a.seed, time_limit_ms=a.time_limit, ops_limit=not a.no_ops_limit)
    dt = time.time() - t0
    m = rep['meta']
    os.makedirs(a.out, exist_ok=True)
    base = os.path.join(a.out, a.name or f"{m['names'][0]}-vs-{m['names'][1]}-{gmap.name}-s{a.seed}")
    save_json(rep, base + '.json')
    _say(f"맵 {gmap.name} ({m['w']}x{m['h']}, 대칭 {m['sym']}) | {_winner_text(rep)} - {m['reason']}")
    _say(f"라운드 {m['rounds']} | 바친 금 {m['score'][0]} : {m['score'][1]} | {dt:.1f}초")
    for t in (0, 1):
        tm = m['time_ms'][t]
        _say(f"  {m['teams'][t]} {m['names'][t]}: 차례당 평균 {tm['avg']:.2f} ms, 최대 {tm['max']:.1f} ms" +
             (f", 시간 초과 {tm['over']}번" if tm['over'] else '') + _ops_txt(m, t))
    for t, (n, msgs) in enumerate(_team_errors(rep)):
        if n:
            _say(f"  {m['teams'][t]} 오류 {n}번. 예: {msgs[0]}")
    _say('리플레이:', base + '.json')
    if not a.no_html:
        write_html(rep, base + '.html')
        _say('뷰어    :', base + '.html')
        if a.open:
            open_in_browser(base + '.html')


# ---------------- scrim ----------------
def _play(task):
    """프로세스 하나에서 경기 하나. 결과 요약 (와 리플레이 저장) 을 돌려준다."""
    bots, map_name, seed, seat, limit, save_dir, ops = task
    gmap = load_map(map_name)
    t0 = time.time()
    rep = run_match(gmap, bots, seed=seed, time_limit_ms=limit, ops_limit=ops)
    m = rep['meta']
    errs = _team_errors(rep)
    out = {'map': gmap.name, 'seed': seed, 'seat': seat, 'winner': m['winner'], 'reason': m['reason'],
           'rounds': m['rounds'], 'score': m['score'], 'camp_hp': m.get('camp_hp'), 'time': m['time_ms'],
           'ops': m.get('ops'), 'errors': [e[0] for e in errs], 'err_msg': [e[1][:1] for e in errs], 'sec': time.time() - t0}
    if save_dir:
        base = os.path.join(save_dir, f'{gmap.name}-s{seed}-{"AB"[seat]}')
        save_json(rep, base + '.json')
        write_html(rep, base + '.html')
    return out


def _map_list(spec):
    if spec == 'all':
        names = list_maps()
        if not names:
            raise SystemExit('maps/ 폴더에 맵이 없다.')
        return names
    return [s.strip() for s in spec.split(',') if s.strip()]


def _seeds(spec):
    out = []
    for part in spec.split(','):
        if '-' in part:
            lo, hi = part.split('-')
            out += list(range(int(lo), int(hi) + 1))
        elif part.strip():
            out.append(int(part))
    return out


def cmd_scrim(a):
    pa, na = resolve_bot(a.bot_a)
    pb, nb = resolve_bot(a.bot_b)
    if na == nb:
        na, nb = na + '(A)', nb + '(B)'
    maps, seeds = _map_list(a.maps), _seeds(a.seeds)
    seats = (0,) if a.one_side else (0, 1)
    save_dir = None
    if a.save:
        save_dir = os.path.join(a.out, time.strftime('scrim-%Y%m%d-%H%M%S'))
        os.makedirs(save_dir, exist_ok=True)
    tasks = []
    for mp in maps:
        for sd in seeds:
            for seat in seats:     # seat 0: A 가 붉은 원정대, seat 1: 진영을 바꿔 A 가 푸른 원정대
                tasks.append(([pa, pb] if seat == 0 else [pb, pa], mp, sd, seat, a.time_limit, save_dir, not a.no_ops_limit))
    _say(f'스크림: {na} vs {nb} | 맵 {len(maps)}개 x 시드 {len(seeds)}개 x 진영 {len(seats)} = {len(tasks)}판 | 동시에 {a.jobs}판')
    t0 = time.time()
    results = []
    if a.jobs > 1:
        with cf.ProcessPoolExecutor(max_workers=a.jobs) as ex:
            futs = [ex.submit(_play, t) for t in tasks]
            for i, f in enumerate(cf.as_completed(futs), 1):
                results.append(f.result())
                print(f'\r  진행 {i}/{len(tasks)}', end='', flush=True)
        print()
    else:
        for t in tasks:
            results.append(_play(t))
    results.sort(key=lambda r: (maps.index(r['map']) if r['map'] in maps else 0, r['seed'], r['seat']))

    # A 쪽에서 본 결과로 바꾸기
    wins = [0, 0]; draws = 0; rows = []
    gold = [0, 0]; rounds = 0; kills = 0; err = [0, 0]; tmax = [0.0, 0.0]; tavg = [0.0, 0.0]; omax = [0, 0]; oover = [0, 0]
    for r in results:
        ia, ib = (0, 1) if r['seat'] == 0 else (1, 0)        # A 와 B 의 팀 번호
        if r['winner'] < 0:
            draws += 1; res = '무승부'
        elif r['winner'] == ia:
            wins[0] += 1; res = f'{na} 승'
        else:
            wins[1] += 1; res = f'{nb} 승'
        gold[0] += r['score'][ia]; gold[1] += r['score'][ib]; rounds += r['rounds']
        kills += '파괴' in r['reason']
        err[0] += r['errors'][ia]; err[1] += r['errors'][ib]
        tmax[0] = max(tmax[0], r['time'][ia]['max']); tmax[1] = max(tmax[1], r['time'][ib]['max'])
        tavg[0] += r['time'][ia]['avg']; tavg[1] += r['time'][ib]['avg']
        if r.get('ops'):
            omax[0] = max(omax[0], r['ops'][ia]['max']); omax[1] = max(omax[1], r['ops'][ib]['max'])
            oover[0] += r['ops'][ia]['over']; oover[1] += r['ops'][ib]['over']
        rows.append([r['map'], r['seed'], f"{na} {'붉은' if ia == 0 else '푸른'}", res, r['reason'], r['rounds'],
                     r['score'][ia], r['score'][ib]])
    if not a.quiet:
        w = max(_w(x[0]) for x in rows) + 2
        ws = max(_w(x[2]) for x in rows) + 2
        wr = max(_w(x[3]) for x in rows) + 2
        _say('\n' + _pad('맵', w) + _pad('시드', 5, True) + '  ' + _pad('A 진영', ws) + _pad('결과', wr)
             + _pad('라운드', 7, True) + _pad('금 A:B', 11, True) + '  끝난 이유')
        for mp, sd, side, res, why, rd, ga, gb in rows:
            _say(_pad(mp, w) + _pad(sd, 5, True) + '  ' + _pad(side, ws) + _pad(res, wr)
                 + _pad(rd, 7, True) + _pad(f'{ga}:{gb}', 11, True) + '  ' + why)
    n = len(results)
    _say(f'\n== 요약 ({n}판, {time.time() - t0:.0f}초) ==')
    _say(f'{na}: {wins[0]}승  {nb}: {wins[1]}승  무승부: {draws}   ->  {na} 승률 {100 * (wins[0] + 0.5 * draws) / n:.1f}%')
    _say(f'평균 바친 금  {na} {gold[0] / n:.1f}  :  {nb} {gold[1] / n:.1f}')
    _say(f'평균 라운드 {rounds / n:.0f} | 야영지 파괴로 끝난 판 {kills}/{n}')
    _say(f'차례 시간 (ms) 평균/최대  {na} {tavg[0] / n:.2f}/{tmax[0]:.1f}  {nb} {tavg[1] / n:.2f}/{tmax[1]:.1f}')
    if omax[0] or omax[1]:
        _say(f'연산 (차례당) 최대  {na} {omax[0]:,}  {nb} {omax[1]:,} | 한도 초과 차례  {na} {oover[0]}번  {nb} {oover[1]}번')
    if err[0] or err[1]:
        _say(f'오류 사건  {na} {err[0]}번  {nb} {err[1]}번  (wumpus check 로 원인을 본다)')
    if save_dir:
        _say('리플레이 폴더:', save_dir)
    if a.csv:
        with open(a.csv, 'w', newline='', encoding='utf-8-sig') as f:
            wr = csv.writer(f)
            wr.writerow(['map', 'seed', 'A_side', 'result', 'reason', 'rounds', 'gold_A', 'gold_B'])
            wr.writerows(rows)
        _say('CSV:', a.csv)


# ---------------- view / viewer ----------------
def cmd_view(a):
    rep = load_json(a.replay)
    out = a.out or os.path.splitext(a.replay)[0] + '.html'
    write_html(rep, out)
    _say('뷰어:', out)
    if not a.no_open:
        open_in_browser(out)


def cmd_viewer(a):
    write_html(None, a.out)
    _say('빈 뷰어:', a.out, '(리플레이 .json 파일을 이 창에 끌어다 놓으면 열린다)')
    if not a.no_open:
        open_in_browser(a.out)


# ---------------- maps ----------------
def cmd_maps(a):
    if a.action == 'list':
        names = list_maps()
        _say(f'maps/ 의 맵 {len(names)}개')
        for n in names:
            g = load_map(n)
            _say(f'  {n:<16} {g.w}x{g.h}  대칭 {g.sym}  금맥 {len(g.ore)}칸 (금 {sum(g.ore.values())})  구덩이 {len(g.traps)}개')
    elif a.action == 'show':
        g = load_map(a.target)
        _say(f'{g.name}: {g.w}x{g.h}, 대칭 {g.sym}   # 벽  G 금  P 구덩이  A 붉은 야영지  B 푸른 야영지')
        _say(g.ascii())
    elif a.action == 'gen':
        g = generate(a.seed, a.size or None, a.size or None, a.sym, a.target or f'gen{a.seed}')
        os.makedirs(a.dir, exist_ok=True)
        path = os.path.join(a.dir, g.name + '.json')
        save_map(g, path)
        _say(f'저장: {path} ({g.w}x{g.h}, 대칭 {g.sym})')


# ---------------- new / check ----------------
def cmd_new(a):
    src, _ = resolve_bot(a.src)
    dst_dir = os.path.join(a.dir, a.name)
    if os.path.exists(dst_dir):
        raise SystemExit(f'이미 있다: {dst_dir}')
    os.makedirs(dst_dir)
    shutil.copy(src, os.path.join(dst_dir, 'main.py'))
    _say(f'만들었다: {dst_dir}/main.py ({a.src} 를 복사)')
    _say(f'시험:  python -m wumpus run {a.name} random --open')


def cmd_check(a):
    path, name = resolve_bot(a.bot)
    _say(f'봇 점검: {name} ({path})')
    src = open(path, encoding='utf-8').read()
    try:
        compile(src, path, 'exec')
    except SyntaxError as e:
        raise SystemExit(f'  문법 오류: {e}')
    ns = {'__name__': 'check'}
    exec(compile(src, path, 'exec'), ns)
    if not callable(ns.get('turn')):
        raise SystemExit('  turn(me, view, memory) 함수가 없다.')
    _say('  불러오기 OK, turn 함수 있음')
    for seat in (0, 1):
        bots = [a.bot, a.opponent] if seat == 0 else [a.opponent, a.bot]
        rep = run_match(load_map(a.map), bots, seed=1, time_limit_ms=a.time_limit, ops_limit=not a.no_ops_limit)
        m = rep['meta']; me = seat
        n, msgs = _team_errors(rep)[me]
        tm = m['time_ms'][me]
        res = '무승부' if m['winner'] < 0 else ('승' if m['winner'] == me else '패')
        _say(f"  {m['teams'][me]} 진영 vs {a.opponent}: {res} ({m['reason']}, {m['rounds']}라운드, 금 {m['score'][me]}:{m['score'][1 - me]})")
        _say(f"    차례 시간 평균 {tm['avg']:.2f} ms, 최대 {tm['max']:.1f} ms" + _ops_txt(m, me) + f" | 오류 {n}번")
        for s in msgs:
            _say('     -', s)


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog='wumpus', description=f'웜퍼스 워즈 {__version__} 도구')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('run', help='경기 하나를 돌리고 리플레이를 만든다')
    p.add_argument('red', help='붉은 원정대 봇 (bots/ 안의 이름 또는 파일 경로)')
    p.add_argument('blue', help='푸른 원정대 봇')
    p.add_argument('--map', default=DEFAULT_MAP, help=f'맵 이름 (maps/), .json 경로, 또는 gen:시드 (기본 {DEFAULT_MAP})')
    p.add_argument('--seed', type=int, default=1, help='경기 시드: 봇의 random 이 이 값으로 정해진다 (기본 1)')
    p.add_argument('--out', default='replays', help='리플레이 폴더 (기본 replays)')
    p.add_argument('--name', help='리플레이 파일 이름 (확장자 빼고)')
    p.add_argument('--open', action='store_true', help='끝나면 뷰어를 브라우저로 연다')
    p.add_argument('--no-html', action='store_true', help='.json 만 쓰고 .html 은 안 쓴다')
    p.add_argument('--time-limit', type=float, default=None, help='차례당 시간 한도 ms (넘기면 그 차례 행동을 버린다). 기본 1000 (시간 안전망), 0 이면 끔')
    p.add_argument('--no-ops-limit', action='store_true', help='연산 한도를 끈다 (빠르지만 공식 규칙이 아니다)')
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser('scrim', help='여러 맵에서 두 봇을 겨루고 승패를 센다')
    p.add_argument('bot_a'); p.add_argument('bot_b')
    p.add_argument('--maps', default='all', help='all 또는 맵1,맵2,... (gen:시드 도 된다)')
    p.add_argument('--seeds', default='1', help='경기 시드 목록: 1,2,3 또는 1-5 (기본 1)')
    p.add_argument('--one-side', action='store_true', help='진영을 바꿔 한 번 더 하지 않는다 (기본은 양쪽 진영 모두)')
    p.add_argument('--jobs', type=int, default=max(1, min(4, (os.cpu_count() or 2) - 1)), help='동시에 돌릴 경기 수')
    p.add_argument('--save', action='store_true', help='모든 판의 리플레이를 저장한다')
    p.add_argument('--out', default='replays', help='--save 때 리플레이 폴더')
    p.add_argument('--csv', help='판마다 결과를 CSV 로 저장')
    p.add_argument('--time-limit', type=float, default=None)
    p.add_argument('--no-ops-limit', action='store_true', help='연산 한도를 끈다 (빠르지만 공식 규칙이 아니다)')
    p.add_argument('--quiet', action='store_true', help='판마다 줄을 찍지 않고 요약만')
    p.set_defaults(fn=cmd_scrim)

    p = sub.add_parser('view', help='리플레이 .json 을 뷰어로 연다')
    p.add_argument('replay'); p.add_argument('--out'); p.add_argument('--no-open', action='store_true')
    p.set_defaults(fn=cmd_view)

    p = sub.add_parser('viewer', help='빈 뷰어 html 을 만든다 (json 을 끌어다 놓아 연다)')
    p.add_argument('--out', default='viewer.html'); p.add_argument('--no-open', action='store_true')
    p.set_defaults(fn=cmd_viewer)

    p = sub.add_parser('maps', help='맵 목록 · 그림 · 만들기')
    p.add_argument('action', nargs='?', default='list', choices=['list', 'show', 'gen'])
    p.add_argument('target', nargs='?', help='show: 맵 이름 / gen: 새 맵 이름')
    p.add_argument('--seed', type=int, default=1); p.add_argument('--size', type=int, default=0)
    p.add_argument('--sym', choices=['H', 'V', 'R']); p.add_argument('--dir', default=MAP_DIR)
    p.set_defaults(fn=cmd_maps)

    p = sub.add_parser('new', help='새 봇 폴더를 만든다')
    p.add_argument('name'); p.add_argument('--from', dest='src', default='starter')
    p.add_argument('--dir', default='bots', help='봇을 만들 폴더 (기본 bots)')
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser('check', help='봇을 점검한다 (불러오기 · 오류 · 차례 시간)')
    p.add_argument('bot'); p.add_argument('--opponent', default='random'); p.add_argument('--map', default=DEFAULT_MAP)
    p.add_argument('--time-limit', type=float, default=None)
    p.add_argument('--no-ops-limit', action='store_true', help='연산 한도를 끈다 (빠르지만 공식 규칙이 아니다)')
    p.set_defaults(fn=cmd_check)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except FileNotFoundError as e:
        raise SystemExit(str(e))


if __name__ == '__main__':
    main()
