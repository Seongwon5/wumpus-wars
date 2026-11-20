"""무작위 봇: 추론 없이 아무 데나 걷는다. 구덩이를 자주 밟는다."""
import random

from wumpus.api import (Move, Mine, Attack, Spawn, DIRS, EXPLORER, ARCHER, CAMP,
                        WALL, GOLD, PIT, CARRY_MAX, cheb)


def turn(me, view, memory):
    if me.kind == CAMP:
        return Spawn(random.choice([EXPLORER, EXPLORER, ARCHER]), random.choice('NESW'))

    if me.kind == ARCHER:
        for u in view.units():
            if u.team != me.team and cheb(me.x, me.y, u.x, u.y) <= 1:
                return Attack(u.x, u.y)

    if me.kind == EXPLORER and view.tile(me.x, me.y) == GOLD and me.carry < CARRY_MAX:
        return Mine()

    moves = []
    for d, (dx, dy) in DIRS.items():
        t = view.tile(me.x + dx, me.y + dy)
        if t is not None and t not in (WALL, PIT):
            moves.append(d)
    if not moves:
        return None
    # 짐이 가득하면 야영지 쪽으로 조금 더 자주 간다
    if me.kind == EXPLORER and me.carry >= CARRY_MAX and random.random() < 0.7:
        bx, by = view.my_camp
        moves.sort(key=lambda d: abs(me.x + DIRS[d][0] - bx) + abs(me.y + DIRS[d][1] - by))
        return Move(moves[0])
    return Move(random.choice(moves))
