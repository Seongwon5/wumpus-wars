"""재미 지표: 옛 규칙과 새 규칙 (fun-rules) 의 경기 모습을 숫자로 비교한다.

python -X utf8 tools/funstats.py --old OLD_BOT.py --new logic --maps 40

지표 (판마다 재고 평균):
- 끝난 이유, 길이
- 마주침 생존율: 탐험가가 적 궁수와 체비셰프 2 안에 처음 들어온 뒤 10라운드 안에 쓰러지지 않은 비율
- 화살로 쓰러진 탐험가 수
- 앞선 팀이 바뀐 횟수 (바친 금 차의 부호가 바뀐 횟수)
- 탐험가 없는 라운드: 50라운드 뒤, 한 팀이라도 탐험가가 0인 라운드 비율 (한 종류만 남은 지루한 시간)
- 새 사건 수: 밀치기, 밀어서 떨어뜨림, 웜퍼스 처치, 잡아먹힘, 떨어진 금 줍기
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OFF = {'line_shot': False, 'arrows': False, 'push': False, 'loot': False, 'wumpus': False}


def maps_list(n):
    from wumpus.maps import list_maps
    return [('file', m) for m in list_maps()] + [('gen', i) for i in range(1, max(0, n - len(list_maps())) + 1)]


def one(args):
    bots, rules, kind, m, seat = args
    os.chdir(ROOT)
    from wumpus.maps import load_map, generate
    from wumpus.engine import run_match
    g = load_map(m) if kind == 'file' else generate(m)
    b = bots if seat == 0 else bots[::-1]
    r = run_match(g, b, seed=1, rules=rules)
    return measure(r)


def measure(r):
    frames = r['frames']
    first = {}          # 탐험가 id -> 처음 마주친 라운드
    died = {}           # id -> (라운드, 원인)
    shot_exp = 0
    lead, changes = 0, 0
    no_exp = 0
    ev = {'push': 0, 'pushkill': 0, 'scream': 0, 'eaten': 0, 'pick': 0, 'atk': 0, 'refill': 0}
    pushed = {}
    for i, fr in enumerate(frames):
        us = fr['u']
        arch = [(u[1], u[3], u[4]) for u in us if u[2] == 'G']
        for u in us:
            if u[2] == 'E' and u[0] not in first:
                if any(t != u[1] and max(abs(x - u[3]), abs(y - u[4])) <= 2 for t, x, y in arch):
                    first[u[0]] = i
        kinds = {u[0]: u[2] for u in frames[i - 1]['u']} if i else {}
        for e in fr['e']:
            k = e[0]
            if k in ev:
                ev[k] += 1
            if k == 'push' and (e[5], e[6]) != (e[7], e[8]):
                pushed[e[4]] = i
            if k == 'die':
                died[e[1]] = (i, e[4])
                if e[4] == 'atk' and kinds.get(e[1]) == 'E':
                    shot_exp += 1
                if e[4] in ('trap', 'wumpus') and pushed.get(e[1]) == i:
                    ev['pushkill'] += 1
        d = fr['sc'][0] - fr['sc'][1]
        s = (d > 0) - (d < 0)
        if s and lead and s != lead:
            changes += 1
        if s:
            lead = s
        if i > 50:
            ne = [sum(1 for u in us if u[1] == t and u[2] == 'E') for t in (0, 1)]
            if min(ne) == 0:
                no_exp += 1
    enc = len(first)
    surv = sum(1 for uid, r0 in first.items() if not (uid in died and died[uid][0] - r0 <= 10))
    m = r['meta']
    return {'reason': m['reason'].split(',')[0].split(' ')[0] if '야영지' in m['reason'] else '시간 끝', 'rounds': m['rounds'],
            'enc': enc, 'surv': surv, 'shot_exp': shot_exp, 'changes': changes,
            'no_exp': no_exp / max(1, len(frames) - 51), **ev}


def summarize(name, rows):
    n = len(rows)
    agg = lambda k: sum(r[k] for r in rows) / n
    enc = sum(r['enc'] for r in rows)
    surv = sum(r['surv'] for r in rows)
    camp = sum(1 for r in rows if r['reason'] != '시간 끝')
    print(f'[{name}] {n}판')
    print(f'  야영지 파괴로 끝 {camp / n:.0%} · 평균 길이 {agg("rounds"):.0f}라운드')
    print(f'  마주침 생존율 {surv / max(1, enc):.0%} ({surv}/{enc}) · 화살에 쓰러진 탐험가 {agg("shot_exp"):.1f}/판')
    print(f'  앞선 팀 바뀜 {agg("changes"):.2f}/판 · 탐험가 없는 시간 {agg("no_exp"):.0%}')
    print(f'  밀치기 {agg("push"):.1f} (떨어뜨림 {agg("pushkill"):.2f}) · 웜퍼스 처치 {agg("scream"):.2f} · 잡아먹힘 {agg("eaten"):.2f}'
          f' · 줍기 {agg("pick"):.1f} · 화살 {agg("atk"):.1f} · 채우기 {agg("refill"):.1f} /판')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--old', required=True, help='옛 규칙에서 쓸 봇')
    ap.add_argument('--new', default='logic', help='새 규칙에서 쓸 봇')
    ap.add_argument('--maps', type=int, default=40)
    ap.add_argument('--new-only', action='store_true')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()
    ms = maps_list(a.maps)
    with ProcessPoolExecutor(a.jobs) as ex:
        sets = (('옛 규칙', a.old, OFF), ('새 규칙', a.new, None))
        for name, bot, rules in (sets[1:] if a.new_only else sets):
            jobs = [([bot, bot], rules, k, m, s) for k, m in ms for s in (0, 1)]
            summarize(name, list(ex.map(one, jobs)))


if __name__ == '__main__':
    main()
