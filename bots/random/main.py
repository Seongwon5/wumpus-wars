"""무작위 봇: 추론 없이 아무 데나 걷는다. 구덩이에 자주 빠진다 (비교용)."""
import random

from wumpus.api import Move, Mine, Attack, Spawn, DIRS, EXPLORER, CAMP, CARRY_MAX


def turn(me, view, memory):
    if me.kind == CAMP:
        return Spawn(EXPLORER, random.choice('NESW'))
    if view.glitter and (view.gold(me.x, me.y) or 0) > 0 and me.carry < CARRY_MAX:
        return Mine()
    if view.hurt:                                   # 아프면 아무 옆 칸이나 친다
        dx, dy = random.choice(list(DIRS.values()))
        return Attack(me.x + dx, me.y + dy)
    if me.carry >= CARRY_MAX and random.random() < 0.7:   # 짐이 가득하면 야영지 쪽으로 조금 더 자주
        bx, by = view.my_camp
        d = min('NESW', key=lambda d: abs(me.x + DIRS[d][0] - bx) + abs(me.y + DIRS[d][1] - by))
        return Move(d)
    return Move(random.choice('NESW'))
