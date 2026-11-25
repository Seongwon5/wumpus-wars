"""시작용 봇 (starter) — 웜퍼스 월드의 모험가.

이 파일을 복사해 자기 봇을 만든다:   python -m wumpus new 내봇이름

규칙 요약 (자세히는 docs/RULES.md · docs/API.md)
- 이 파일에는 turn(me, view, memory) 함수가 꼭 있어야 한다.
- 모험가 · 야영지마다 이 파일이 따로 실행된다. 아래 전역 변수는 그 모험가 혼자만의 기억이다.
- 모험가는 **자기 칸만** 느낀다. 옆 칸의 벽 · 구덩이 · 금 · 웜퍼스 · 다른 모험가는 보이지 않는다.
  지각: view.breeze 바람 · view.stench 악취 · view.glitter 반짝임 · view.bump 부딪힘
        view.footsteps 발소리 · view.hurt 아픔 · view.screams 비명 · view.warmth 열기 · view.cries 외침
- 우리 야영지 위치 (view.my_camp) 만 안다. 적 야영지는 맵 대칭 (좌우 H · 상하 V · 180도 R 중 하나) 으로 본 우리 야영지의 거울 칸이다.
- 한 턴에 행동 하나: Move(d) · Mine() · Attack(x, y) (상하좌우 옆 칸) · None (쉬기). 야영지는 Spawn(EXPLORER, d).
- 연산 한도: 유닛마다 한 차례에 10,000 (첫 차례만 200,000). 넘은 차례는 행동이 버려진다. 그래서 길 찾기에 상한 (SEARCH_CAP) 을 둔다.
- 불러올 수 있는 모듈: math · heapq · collections · itertools · functools · random · bisect · operator · copy · wumpus.api
- 팀끼리 나눌 정보는 memory (32비트 정수 16칸, 맵 전체는 못 담는다) 에 적는다.
- 코드 검사: `x.__class__` 같은 밑줄 두 개 속성, getattr · type · exec · open, 문자열 .format 은 쓸 수 없다 (걸리면 실격).

이 봇이 하는 일 (아홉 지각 가운데 외침만 TODO, 네 행동 · memory 를 고루 쓴다)
0. 열기 · 벽: 적 야영지 후보 (대칭 셋의 거울 칸) 를 지운다. 열기가 없으면 옆 칸은 야영지가 아니고,
   벽의 거울 칸에 서 본 적이 있으면 그 대칭은 아니다 (대칭이면 거울 칸도 벽이어야 한다).
1. 바람 · 악취: "둘 다 없는 칸의 상하좌우는 안전하다" 로 안전한 칸을 넓히며 탐험한다.
2. 반짝임: 캔다. 가득 차면 아는 길로 야영지에 돌아가 바친다.
3. 부딪힘 · 발소리: 부딪혔는데 발소리가 없으면 그 칸을 벽으로 기억한다.
4. 아픔: 옆 칸을 차례로 쳐서 반격한다. 적 야영지 옆에 서면 체력이 넉넉할 때 야영지를 친다.
5. 비명: 웜퍼스가 쓰러졌다는 뜻이다. 악취를 느꼈던 칸에 다시 가서 사라졌는지 확인한다.
6. memory: 찾은 금맥의 위치를 적어 팀과 나눈다. 바친 뒤에는 아는 금맥으로 돌아가고, 팀원이 찾은 금맥 쪽으로 탐험한다.

TODO 표시가 있는 곳부터 고쳐 보자.
"""
from collections import deque

from wumpus.api import (Move, Mine, Attack, Spawn, debug, DIRS, mirror,
                        EXPLORER, CAMP, WALL, CARRY_MAX, COST, MAX_ROUNDS, MAX_UNITS)

# ---------------- 이 모험가의 기억 (지식 베이스) ----------------
visited = set()      # 서 본 칸 (살아서 서 봤으니 안전하다)
safe = set()         # 안전하다고 추론한 칸 (구덩이도 웜퍼스도 없다)
walls = set()        # 부딪혀서 알아낸 벽
sure_walls = set()   # 그 가운데 발소리 없이 막힌 칸 (확실한 벽, 대칭 추론에 쓴다)
danger = set()       # 바람 · 악취를 느낀 칸 (그 옆 어딘가가 위험하다)
stench = set()       # 그 가운데 악취를 느낀 칸
recheck = set()      # 비명을 들은 뒤 다시 가 볼 악취 칸
heard = 0            # 지금까지 들은 비명 수
here = None          # 지금 선 칸
came_from = None     # 바로 전에 서 있던 칸
last_target = None   # 지난 차례에 들어가려던 칸
bumps = {}           # 칸 -> 연달아 부딪힌 횟수
move_fs = 0          # 지난 차례 (움직인 차례) 의 발소리
busy = {}            # 서 본 칸 -> 다른 모험가에게 막힌 라운드
swing = 0            # 반격할 때 다음에 칠 방향 번호
SEARCH_CAP = 220     # 한 차례의 길 찾기에서 펼칠 칸 수 상한 (연산 한도 안에 들도록 일의 양을 직접 센다)
work_left = 0        # 이번 차례에 더 펼칠 수 있는 칸 수
FIGHT_HP = 5         # 체력이 이보다 많을 때만 적 야영지를 친다
BUSY_ROUNDS = 8      # 다른 모험가에게 막힌 칸은 이 라운드 동안 돌아간다
D4 = tuple(DIRS.values())
syms = {'H', 'V', 'R'}  # 아직 지우지 못한 맵 대칭 (적 야영지 = 우리 야영지의 거울 칸)


def camp_candidates(view):
    """적 야영지 후보 칸들 (남은 대칭마다 우리 야영지의 거울 칸)."""
    return {mirror(sy, *view.my_camp, view.width, view.height) for sy in syms} - {view.my_camp}


def rule_out(test):
    """test(대칭) 가 참인 대칭을 지운다. 다 지워지면 (관측이 틀렸으면) 지우지 않는다."""
    left = {sy for sy in syms if not test(sy)}
    if left:
        syms.intersection_update(left)


def turn(me, view, memory):
    if me.kind == CAMP:
        return camp_turn(me, view, memory)
    return adventurer_turn(me, view, memory)


# ---------------- 야영지 ----------------
def camp_turn(me, view, memory):
    # TODO: 언제, 몇 명을 만들지 정해 보자 (금고를 아껴 둘 수도 있다)
    if me.bank < COST[EXPLORER] or view.unit_count >= MAX_UNITS:
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
    global last_target, swing, heard, here, came_from, work_left, move_fs
    work_left = SEARCH_CAP
    pos = (me.x, me.y)
    w, h = view.width, view.height
    if pos != here:
        came_from, here = here, pos

    # 1. 지각을 지식 베이스에 더한다
    if view.bump and last_target is not None:
        bumps[last_target] = bumps.get(last_target, 0) + 1
        if last_target in visited:                  # 서 본 칸이 막혔다 → 벽이 아니라 다른 모험가다. 잠시 그 칸을 돌아간다
            busy[last_target] = me.round
        elif move_fs == 0 or bumps[last_target] >= 3:
            # 움직일 때 발소리가 없었는데 막혔다 → 벽 (내 차례 안에서는 아무도 움직이지 않으므로 모험가일 수 없다).
            # 발소리가 있었으면 모험가일 수도 있지만, 세 번 연달아 막히면 벽이다 (모험가는 비켜 간다)
            walls.add(last_target)
            if move_fs == 0:                        # 확실한 벽만 대칭 추론에 쓴다
                sure_walls.add(last_target)
                wc = last_target                    # 1차 논리: 대칭이면 벽의 거울 칸도 벽이다 → 거울 칸에 서 본 적이 있으면 그 대칭은 아니다
                rule_out(lambda sy: mirror(sy, wc[0], wc[1], w, h) in visited)
    elif last_target is not None:
        bumps.pop(last_target, None)
    last_target = None
    move_fs = view.footsteps                        # 이번 차례에 움직이면, 그때의 발소리 (다음 차례에 부딪힘을 풀 때 쓴다)
    if view.screams > heard:                        # 비명: 웜퍼스가 쓰러졌다 → 악취 칸에 다시 가 본다
        heard = view.screams
        recheck.update(stench)
    recheck.discard(pos)
    visited.add(pos)
    rule_out(lambda sy: mirror(sy, pos[0], pos[1], w, h) in sure_walls)  # 내 칸의 거울 칸이 확실한 벽이면 그 대칭은 아니다
    nb = set(neighbors(pos, w, h))
    if view.my_camp not in nb:                      # 열기: 상하좌우에 야영지. 우리 야영지 옆이 아니면 적 야영지 단서다
        if view.warmth:
            rule_out(lambda sy: mirror(sy, *view.my_camp, w, h) not in nb)
        else:
            rule_out(lambda sy: mirror(sy, *view.my_camp, w, h) in nb)
    camps = camp_candidates(view)
    # TODO: 지운 대칭을 memory 로 팀원과 나눠 보자. 외침 (view.cries) 과 팀원 수로 적이 몇 명 쓰러졌는지도 셀 수 있다
    safe.add(pos)
    if not view.stench:
        stench.discard(pos)
    if view.breeze or view.stench:
        danger.add(pos)
        debug.mark(*pos, 'yellow')
        if view.stench:
            stench.add(pos)
            if heard:                               # 쓰러진 웜퍼스는 되살아난다 → 온 길만 빼고 옆 칸을 다시 의심한다
                safe.difference_update([n for n in neighbors(pos, w, h) if n != came_from])
    else:
        danger.discard(pos)
        for n in neighbors(pos, w, h):              # 명제 논리: ¬바람 ∧ ¬악취 → 상하좌우는 안전
            safe.add(n)
    # TODO: 바람 칸 둘레에서 "후보가 하나뿐이면 그 칸이 구덩이" 같은 추론을 더해 보자

    # 2. 적 야영지 옆 (대각선 포함) 에서는 야영지가 저절로 친다. 열기가 나고 맞닿은 후보가 있으면 체력이 넉넉할 때 친다
    near = [c for c in camps if max(abs(pos[0] - c[0]), abs(pos[1] - c[1])) <= 1]
    if near:
        touch = [c for c in near if abs(pos[0] - c[0]) + abs(pos[1] - c[1]) == 1]
        if touch and view.warmth and me.hp > FIGHT_HP:
            debug.say('적 야영지 공격 (%d,%d)' % touch[0])
            return Attack(*touch[0])
        # TODO: 적 야영지를 여럿이 함께 치러 가는 때를 정해 보자
    elif view.hurt:
        # 3. 아프면 반격한다 (누가 어디서 쳤는지는 모른다 → 옆 칸을 차례로 쳐 본다)
        # TODO: 발소리 · 팀원 위치로 적이 있는 칸을 추론해 보자
        cand = [n for n in neighbors(pos, w, h) if n not in walls and n != view.my_camp]
        if cand:
            t = cand[swing % len(cand)]
            swing += 1
            debug.say('아프다 → (%d,%d) 반격' % t)
            return Attack(*t)

    # 4. 반짝이면 캔다 (떨어진 금은 들어서면 저절로 줍는다). 금맥 위치는 memory 에 적어 팀과 나눈다
    code = 1 + pos[0] + pos[1] * w                  # 칸 하나를 정수 하나로 (0 은 빈 칸)
    gold = view.gold(*pos) or 0
    if gold > 0 and code not in memory and 0 in memory:
        memory[memory.index(0)] = code
    elif gold == 0 and code in memory:              # 다 캔 금맥은 지운다
        memory[memory.index(code)] = 0
    if view.glitter and gold > 0 and me.carry < CARRY_MAX:
        debug.say('반짝임 → 채굴')
        return Mine()

    # 5. 가득 차면 (또는 경기 끝이 가까우면) 야영지 옆 칸으로 돌아간다
    home = set(neighbors(view.my_camp, w, h)) - walls
    if me.carry >= CARRY_MAX or (me.carry > 0 and me.round > MAX_ROUNDS - 60):
        return go(me, pos, home, w, h, '귀환')

    # 6. 비명을 들었으면 악취 칸을 다시 확인하러 간다 (악취가 사라졌으면 그 둘레가 안전해진다)
    if recheck:
        act = go(me, pos, recheck & safe, w, h, '악취 확인')
        if act is not None:
            return act

    # 7. 아는 금맥으로 돌아가 캔다 (내가 서 본 금맥 가운데 가장 가까운 곳. 팀원이 다 캤다고 지운 곳은 빠진다)
    veins = [((v - 1) % w, (v - 1) // w) for v in memory if v]
    known = {v for v in veins if v in visited and v != pos}
    if known:
        act = go(me, pos, known, w, h, '금맥으로')
        if act is not None:
            return act

    # 8. 탐험: 안전하다고 추론했지만 아직 안 가 본 칸 → 없으면 위험을 감수한다
    frontier = safe - visited - walls - camps - {view.my_camp}
    if frontier:
        far = [v for v in veins if v not in visited]
        if far:                                     # 팀원이 찾은 금맥 쪽의 안 가 본 칸부터 (길이 멀면 가까운 칸부터)
            tx, ty = min(far, key=lambda v: (abs(v[0] - pos[0]) + abs(v[1] - pos[1]), v))
            near = min(frontier, key=lambda c: (abs(c[0] - tx) + abs(c[1] - ty), c))
            act = go(me, pos, {near}, w, h, '탐험 (금맥 쪽)')
            if act is not None:
                return act
        return go(me, pos, frontier, w, h, '탐험 (안전)')
    unknown = {n for c in danger for n in neighbors(c, w, h)} - visited - walls - camps - {view.my_camp}
    return go(me, pos, unknown, w, h, '탐험 (위험 감수)')


def go(me, pos, goals, w, h, label):
    """아는 안전한 칸으로만 걸어 goals 중 가장 가까운 칸으로 한 걸음 (너비 우선 탐색)."""
    global last_target, work_left
    if not goals:
        return None
    blocked = {c for c, r in busy.items() if me.round - r <= BUSY_ROUNDS}   # 방금 다른 모험가에게 막힌 칸은 돌아간다
    prev = {pos: None}
    q = deque([pos])
    while q:
        c = q.popleft()
        work_left -= 1
        if work_left < 0:                           # 상한: 여기까지 본 칸 가운데 목표에 가장 가까운 칸으로 간다 (빈 답을 내지 않는다)
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
            if n not in prev and n not in walls and n not in blocked and (n in safe or n in goals):
                prev[n] = c
                q.append(n)
    return None
