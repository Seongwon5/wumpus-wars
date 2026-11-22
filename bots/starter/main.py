"""시작용 봇 (starter).

이 파일을 복사해 자기 봇을 만든다:   python -m wumpus new 내봇이름

규칙
- 이 파일에는 turn(me, view, memory) 함수가 꼭 있어야 한다.
- 유닛 (야영지 · 탐험가 · 궁수) 마다 이 파일이 따로 실행된다.
  그래서 아래 전역 변수 (visited 등) 는 그 유닛 혼자만의 기억이다.
- 팀끼리 나눌 정보는 memory (정수 64칸) 에 적는다.
- turn 은 행동 하나 (Move · Mine · Shoot · Push · Spawn) 나 None (쉬기) 를 돌려준다.

지금은 아주 단순하게 움직인다. TODO 표시가 있는 곳부터 고쳐 보자.
"""
import random

from wumpus.api import (Move, Mine, Shoot, Push, Spawn, debug, DIRS, cheb,
                        EXPLORER, ARCHER, CAMP, WALL, GOLD, PIT, CARRY_MAX, COST, ARROW_RANGE)

visited = set()          # 이 유닛이 서 본 칸
breezy = set()           # 이 유닛이 바람을 느낀 칸


def turn(me, view, memory):
    if me.kind == CAMP:
        return camp_turn(me, view, memory)
    if me.kind == EXPLORER:
        return explorer_turn(me, view, memory)
    return archer_turn(me, view, memory)


# ---------------- 야영지 ----------------
def camp_turn(me, view, memory):
    # TODO: 탐험가와 궁수를 몇 기씩, 언제 만들지 정해 보자.
    kind = EXPLORER if view.unit_count < 6 else ARCHER
    if me.bank < COST[kind] or view.unit_count >= 10:
        return None
    for d, (dx, dy) in DIRS.items():
        x, y = me.x + dx, me.y + dy
        if view.tile(x, y) not in (None, WALL) and not occupied(view, x, y):
            return Spawn(kind, d)
    return None


# ---------------- 탐험가 ----------------
def explorer_turn(me, view, memory):
    visited.add((me.x, me.y))
    if view.breeze:
        breezy.add((me.x, me.y))
        debug.mark(me.x, me.y, 'yellow')          # 뷰어의 "머릿속" 에 보인다

    # 금을 다 채웠으면 야영지로 돌아간다 (야영지 옆에 서면 저절로 바쳐진다)
    if me.carry >= CARRY_MAX:
        return step_toward(me, view, *view.my_camp)

    # 바로 옆 적 뒤가 드러난 구덩이면 밀어 떨어뜨린다
    for u in view.units():
        if u.team != me.team and u.kind != CAMP and abs(u.x - me.x) + abs(u.y - me.y) == 1:
            if view.tile(2 * u.x - me.x, 2 * u.y - me.y) == PIT:
                return Push(next(d for d, (dx, dy) in DIRS.items() if (me.x + dx, me.y + dy) == (u.x, u.y)))

    # 금 칸 위에 서 있거나 떨어진 금이 있으면 캔다 (줍는다)
    if view.tile(me.x, me.y) == GOLD or view.loot(me.x, me.y):
        return Mine()
    # TODO: 악취 (view.stench) 가 나면 근처에 웜퍼스 굴이 있다. 굴로 들어가면 잡아먹힌다.

    # 보이는 금 중 가장 가까운 곳으로 간다
    golds = [(x, y) for (x, y) in view.visible_cells() if view.tile(x, y) == GOLD and not occupied(view, x, y)]
    if golds:
        gx, gy = min(golds, key=lambda c: abs(c[0] - me.x) + abs(c[1] - me.y))
        debug.path([(me.x, me.y), (gx, gy)], 'white')
        return step_toward(me, view, gx, gy)

    # TODO: 바람으로 구덩이를 추론해 안전한 칸만 골라 탐사하자 (지금은 무작위).
    return wander(me, view)


# ---------------- 궁수 ----------------
def archer_turn(me, view, memory):
    # 같은 줄 · 같은 열의 적이 사거리 안에 있으면 그쪽으로 쏜다 (화살이 있을 때)
    # TODO: 사이에 벽이나 우리 편이 있으면 화살이 막힌다. 화살이 떨어지면 야영지 옆에서 채우자 (me.arrows).
    for u in view.units():
        if u.team != me.team and me.arrows > 0 and (u.x == me.x or u.y == me.y) and 0 < abs(u.x - me.x) + abs(u.y - me.y) <= ARROW_RANGE:
            d = ('E' if u.x > me.x else 'W') if u.y == me.y else ('S' if u.y > me.y else 'N')
            return Shoot(d)
    # TODO: 적 야영지가 어디인지 대칭으로 추론해 그쪽으로 가자.
    return wander(me, view)


# ---------------- 도우미 ----------------
def occupied(view, x, y):
    return any(u.x == x and u.y == y for u in view.units())


def safe_moves(me, view):
    """벽 · 드러난 구덩이 · 다른 유닛이 없는 방향들."""
    out = []
    for d, (dx, dy) in DIRS.items():
        x, y = me.x + dx, me.y + dy
        t = view.tile(x, y)
        if t is not None and t not in (WALL, PIT) and not occupied(view, x, y):
            out.append(d)
    return out


def step_toward(me, view, tx, ty):
    moves = safe_moves(me, view)
    if not moves:
        return None
    best = min(moves, key=lambda d: abs(me.x + DIRS[d][0] - tx) + abs(me.y + DIRS[d][1] - ty))
    return Move(best)


def wander(me, view):
    moves = safe_moves(me, view)
    fresh = [d for d in moves if (me.x + DIRS[d][0], me.y + DIRS[d][1]) not in visited]
    pick = fresh or moves
    return Move(random.choice(pick)) if pick else None
