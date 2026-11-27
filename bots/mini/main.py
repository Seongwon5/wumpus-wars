import random
from wumpus.api import Move, Mine, Spawn, EXPLORER, CAMP, WALL, DIRS, direction_to

path = []          # 야영지 옆에서 지금 칸까지 걸어온 길 (돌아갈 때 쓴다)
seen = set()       # 서 봤거나 막혔던 칸
calm = set()       # 바람도 악취도 없던 칸 (이 칸의 상하좌우는 안전!)
target = None      # 지난 차례에 들어가려던 칸


def turn(me, view, memory):
    global target
    if me.kind == CAMP:                                    # 야영지: 빈 옆 칸에 모험가를 뽑는다
        for d, (dx, dy) in DIRS.items():
            if view.tile(me.x + dx, me.y + dy) not in (None, WALL):
                return Spawn(EXPLORER, d)
        return None

    here = (me.x, me.y)
    if view.bump and target:                               # 막혔다 → 그 칸은 못 가는 칸
        seen.add(target)
    if here in path:
        del path[path.index(here) + 1:]                    # 맴돈 고리는 잘라 낸다
    else:
        path.append(here)
    seen.add(here)
    if not (view.breeze or view.stench):
        calm.add(here)

    if view.glitter and me.carry < 10:                     # 반짝이면 캔다
        return Mine()

    near = [(here[0] + dx, here[1] + dy) for dx, dy in DIRS.values()]
    near = [c for c in near if 0 <= c[0] < view.width and 0 <= c[1] < view.height]
    new = [c for c in near if c not in seen]
    if me.carry >= 10 or here not in calm or not new:      # 짐이 찼거나, 위험하거나, 막다른 곳
        if me.carry < 10 and here in calm:
            new = [c for c in near if c in calm]           # 아는 안전한 칸으로 돌아다닌다
        elif len(path) >= 2:
            new = [path[-2]]                               # 왔던 길로 한 칸 되돌아간다
    if not new:
        return None                                        # 야영지 옆: 금은 저절로 바쳐진다
    target = random.choice(new)
    return Move(direction_to(*here, *target))
