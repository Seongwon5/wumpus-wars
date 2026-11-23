"""시작용 봇 (starter) — 웜퍼스 월드의 모험가.

이 파일을 복사해 자기 봇을 만든다:   python -m wumpus new 내봇이름

규칙 요약 (자세히는 docs/RULES.md · docs/API.md)
- 이 파일에는 turn(me, view, memory) 함수가 꼭 있어야 한다.
- 모험가 · 야영지마다 이 파일이 따로 실행된다. 아래 전역 변수는 그 모험가 혼자만의 기억이다.
- 모험가는 **자기 칸만** 느낀다. 옆 칸의 벽 · 구덩이 · 금 · 웜퍼스 · 다른 모험가는 보이지 않는다.
  지각: view.breeze 바람 · view.stench 악취 · view.glitter 반짝임 · view.bump 부딪힘
        view.footsteps 발소리 · view.hurt 아픔 · view.screams 비명
- 한 턴에 행동 하나: Move(d) · Mine() · Attack(x, y) (상하좌우 옆 칸) · None (쉬기)
- 연산 한도: 유닛마다 한 차례에 10,000 (첫 차례만 200,000). 넘은 차례는 행동이 버려진다. 그래서 길 찾기에 상한 (SEARCH_CAP) 을 둔다.
- 불러올 수 있는 모듈: math · heapq · collections · itertools · functools · random · bisect · operator · copy · wumpus.api
- 팀끼리 나눌 정보는 memory (32비트 정수 16칸, 맵 전체는 못 담는다) 에 적는다.

이 봇이 하는 일 (기본 동작은 다 한다)
1. "바람도 악취도 없는 칸의 상하좌우는 안전하다" 로 안전한 칸을 넓히며 탐험한다.
2. 반짝이면 캔다. 가득 차면 아는 길로 야영지에 돌아가 바친다.
3. 부딪혔는데 발소리가 없으면 그 칸을 벽으로 기억한다.
4. 아프면 옆 칸을 차례로 쳐서 반격한다.

TODO 표시가 있는 곳부터 고쳐 보자.
"""
from collections import deque

from wumpus.api import (Move, Mine, Attack, Spawn, debug, DIRS,
                        EXPLORER, CAMP, WALL, CARRY_MAX, COST, MAX_ROUNDS)

# ---------------- 이 모험가의 기억 (지식 베이스) ----------------
visited = set()      # 서 본 칸 (살아서 서 봤으니 안전하다)
safe = set()         # 안전하다고 추론한 칸 (구덩이도 웜퍼스도 없다)
walls = set()        # 부딪혀서 알아낸 벽
danger = set()       # 바람 · 악취를 느낀 칸 (그 옆 어딘가가 위험하다)
last_target = None   # 지난 차례에 들어가려던 칸
bumps = {}           # 칸 -> 연달아 부딪힌 횟수
swing = 0            # 반격할 때 다음에 칠 방향 번호
SEARCH_CAP = 220     # 길 찾기 한 번에 펼칠 칸 수 상한 (연산 한도 안에 들도록 일의 양을 직접 센다)
D4 = tuple(DIRS.values())


def turn(me, view, memory):
    if me.kind == CAMP:
        return camp_turn(me, view, memory)
    return adventurer_turn(me, view, memory)


# ---------------- 야영지 ----------------
def camp_turn(me, view, memory):
    # TODO: 언제, 몇 명을 만들지 정해 보자 (금고를 아껴 둘 수도 있다)
    if me.bank < COST[EXPLORER] or view.unit_count >= 10:
        return None
    taken = {(u.x, u.y) for u in view.units()}
    for d, (dx, dy) in DIRS.items():
        c = (me.x + dx, me.y + dy)
        if view.tile(*c) not in (None, WALL) and c not in taken:   # 야영지는 옆 칸까지 본다
            return Spawn(EXPLORER, d)
    return None


# ---------------- 모험가 ----------------
def neighbors(c, w, h):
    x, y = c
    return [(x + dx, y + dy) for dx, dy in D4 if 0 <= x + dx < w and 0 <= y + dy < h]


def adventurer_turn(me, view, memory):
    global last_target, swing
    pos = (me.x, me.y)
    w, h = view.width, view.height

    # 1. 지각을 지식 베이스에 더한다
    if view.bump and last_target is not None:
        bumps[last_target] = bumps.get(last_target, 0) + 1
        # 발소리 없이 막혔다 → 벽. 발소리가 있으면 모험가일 수도 있지만, 세 번 연달아 막히면 벽이다 (모험가는 비켜 간다)
        if view.footsteps == 0 or bumps[last_target] >= 3:
            walls.add(last_target)
    elif last_target is not None:
        bumps.pop(last_target, None)
    last_target = None
    visited.add(pos)
    safe.add(pos)
    if view.breeze or view.stench:
        danger.add(pos)
        debug.mark(*pos, 'yellow')
    else:
        for n in neighbors(pos, w, h):              # 명제 논리: ¬바람 ∧ ¬악취 → 상하좌우는 안전
            safe.add(n)
    # TODO: 바람 칸 둘레에서 "후보가 하나뿐이면 그 칸이 구덩이" 같은 추론을 더해 보자
    # TODO: memory 로 팀원과 벽 · 안전한 칸 지도를 나눠 보자

    # 2. 아프면 반격한다 (누가 어디서 쳤는지는 모른다 → 옆 칸을 차례로 쳐 본다)
    # TODO: 발소리 · 팀원 위치로 적이 있는 칸을 추론해 보자
    if view.hurt:
        cand = [n for n in neighbors(pos, w, h) if n not in walls and n != view.my_camp]
        if cand:
            t = cand[swing % len(cand)]
            swing += 1
            debug.say('아프다 → (%d,%d) 반격' % t)
            return Attack(*t)

    # 3. 반짝이면 캔다 (떨어진 금은 들어서면 저절로 줍는다)
    if view.glitter and (view.gold(*pos) or 0) > 0 and me.carry < CARRY_MAX:
        debug.say('반짝임 → 채굴')
        return Mine()

    # 4. 가득 차면 (또는 경기 끝이 가까우면) 야영지 옆 칸으로 돌아간다
    home = set(neighbors(view.my_camp, w, h)) - walls
    if me.carry >= CARRY_MAX or (me.carry > 0 and me.round > MAX_ROUNDS - 60):
        return go(me, pos, home, w, h, '귀환')

    # 5. 탐험: 안전하다고 추론했지만 아직 안 가 본 칸 → 없으면 위험을 감수한다
    # TODO: 적 야영지 (view.enemy_camp) 를 치러 가는 때를 정해 보자
    frontier = safe - visited - walls - {view.my_camp, view.enemy_camp}
    if frontier:
        return go(me, pos, frontier, w, h, '탐험 (안전)')
    unknown = {n for c in danger for n in neighbors(c, w, h)} - visited - walls - {view.my_camp, view.enemy_camp}
    return go(me, pos, unknown, w, h, '탐험 (위험 감수)')


def go(me, pos, goals, w, h, label):
    """아는 안전한 칸으로만 걸어 goals 중 가장 가까운 칸으로 한 걸음 (너비 우선 탐색)."""
    global last_target
    if not goals:
        return None
    prev = {pos: None}
    q = deque([pos])
    work = 0
    while q:
        c = q.popleft()
        work += 1
        if work > SEARCH_CAP:                       # 상한: 여기까지 본 칸 가운데 목표에 가장 가까운 칸으로 간다 (빈 답을 내지 않는다)
            gx, gy = min(goals)
            c = min(prev, key=lambda p: abs(p[0] - gx) + abs(p[1] - gy))
            goals = {c}
            if c == pos:
                return None
        if c in goals:
            while prev[c] != pos and prev[c] is not None:
                c = prev[c]
            last_target = c
            debug.say('%s → (%d,%d)' % (label, c[0], c[1]))
            return Move(next(d for d, (dx, dy) in DIRS.items() if (pos[0] + dx, pos[1] + dy) == c))
        for n in neighbors(c, w, h):
            if n not in prev and n not in walls and (n in safe or n in goals):
                prev[n] = c
                q.append(n)
    return None
