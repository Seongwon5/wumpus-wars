"""추론하는 예시 봇.

쓰는 기법
- 명제논리: "바람 없는 칸의 상하좌우는 안전하다", "바람 칸의 미지 이웃이 하나뿐이면 그 칸이 구덩이다".
- 1차 술어 논리: "모든 칸 c 에 대해 Trap(c) <-> Trap(mirror(c))" 를 구체적인 칸에 적용 (전칭 예화).
- 대칭 추론: 관측과 모순되는 대칭 후보를 지워 적 야영지 위치를 찾는다.
- A*: 안전한 칸은 비용 1, 모르는 칸은 비싸게, 의심 칸은 더 비싸게. 휴리스틱은 맨해튼 거리 (허용 가능).

유닛마다 이 파일이 따로 실행되므로 전역 변수 K 는 그 유닛만의 지식 베이스다.
팀 공유 memory 칸 쓰임: [0] 지운 대칭 비트, [1],[2] 적 야영지 x+1, y+1, [3] 만든 궁수 수.
"""
import heapq

from wumpus.api import (MAX_ROUNDS, Move, Mine, Attack, Spawn, debug, DIRS, mirror, cheb, direction_to,
                        EXPLORER, ARCHER, CAMP, WALL, GOLD, PIT, CAMP_TILE,
                        CARRY_MAX, SAFE_RADIUS, COST)

SYMS = ('H', 'V', 'R')
BIT = {'H': 1, 'V': 2, 'R': 4}
SYM_KO = {'H': '좌우', 'V': '상하', 'R': '회전'}
RALLY = 3            # 궁수가 이만큼 모이면 출발

K = None             # 이 유닛의 지식 베이스
plan_i = 0           # 야영지의 생산 순서 위치


class Knowledge:
    def __init__(self, w, h, base):
        self.w, self.h, self.base = w, h, base
        self.tile = {}          # 본 칸 -> 글자
        self.walls = set()
        self.vib = {}           # 내가 서 본 칸 -> 바람 여부
        self.safe = set()
        self.trap = set()
        self.ruled_out = 0
        self.enemy_base = None
        self._add_safe_zone(base)

    # --- 기본 ---
    def inb(self, c):
        return 0 <= c[0] < self.w and 0 <= c[1] < self.h

    def nb4(self, c):
        for dx, dy in DIRS.values():
            n = (c[0] + dx, c[1] + dy)
            if self.inb(n):
                yield n

    def _add_safe_zone(self, b):
        r = SAFE_RADIUS
        for x in range(b[0] - r, b[0] + r + 1):
            for y in range(b[1] - r, b[1] + r + 1):
                if self.inb((x, y)):
                    self.safe.add((x, y))

    def alive_syms(self):
        return [s for s in SYMS if not self.ruled_out & BIT[s]]

    # --- 관측 ---
    def observe(self, me, view, memory):
        for c in view.visible_cells():
            t = view.tile(*c)
            self.tile[c] = t
            if t == WALL:
                self.walls.add(c)
            elif t == PIT:
                self.trap.add(c)
                self.safe.discard(c)
            elif t == GOLD:
                self.safe.add(c)                    # 규칙: 금 칸에는 구덩이가 없다
            elif t == CAMP_TILE and c != self.base and self.enemy_base is None:
                self._found_enemy(c)
        if me.kind != CAMP:
            self.vib[(me.x, me.y)] = view.breeze
            self.safe.add((me.x, me.y))
        # 팀 공유 정보 읽기
        self.ruled_out |= memory[0] & 7
        if self.enemy_base is None and memory[1]:
            self._found_enemy((memory[1] - 1, memory[2] - 1))
        self.check_symmetry()
        self.infer()
        # 팀 공유 정보 쓰기
        memory[0] |= self.ruled_out
        if self.enemy_base is not None:
            memory[1], memory[2] = self.enemy_base[0] + 1, self.enemy_base[1] + 1

    def _found_enemy(self, c):
        self.enemy_base = c
        self._add_safe_zone(c)
        for s in SYMS:
            if mirror(s, *self.base, self.w, self.h) != c:
                self.ruled_out |= BIT[s]

    # --- 대칭 추론: 모순되는 후보를 지운다 ---
    def check_symmetry(self):
        for s in self.alive_syms():
            m = mirror(s, *self.base, self.w, self.h)
            t = self.tile.get(m)
            if t is not None and t != CAMP_TILE:
                self.ruled_out |= BIT[s]
                continue
            for c in self.walls:
                tm = self.tile.get(mirror(s, *c, self.w, self.h))
                if tm is not None and tm != WALL:
                    self.ruled_out |= BIT[s]
                    break
        alive = self.alive_syms()
        if len(alive) == 1 and self.enemy_base is None:
            self._found_enemy(mirror(alive[0], *self.base, self.w, self.h))

    # --- 명제논리 추론 (고정점까지 반복) ---
    def infer(self):
        changed = True
        while changed:
            changed = False
            for c, v in self.vib.items():
                ns = [n for n in self.nb4(c) if n not in self.walls]
                if not v:
                    for n in ns:
                        if n not in self.safe:
                            self.safe.add(n)
                            changed = True
                else:
                    unknown = [n for n in ns if n not in self.safe]
                    if len(unknown) == 1 and unknown[0] not in self.trap:
                        self.trap.add(unknown[0])
                        changed = True
            # 대칭이 하나로 정해지면 안전 · 구덩이 사실을 거울 칸에도 적용한다
            alive = self.alive_syms()
            if len(alive) == 1:
                s = alive[0]
                for c in list(self.safe):
                    m = mirror(s, *c, self.w, self.h)
                    if m not in self.safe and m not in self.trap:
                        self.safe.add(m)
                        changed = True
                for c in list(self.trap):
                    m = mirror(s, *c, self.w, self.h)
                    if m not in self.trap:
                        self.trap.add(m)
                        changed = True

    def suspect(self, c):
        """바람한 칸에 붙어 있고 안전이 증명되지 않은 칸."""
        return c not in self.safe and any(self.vib.get(n) for n in self.nb4(c))

    # --- A* ---
    def cost(self, c):
        if c in self.walls or c in self.trap or c == self.base or c == self.enemy_base:
            return None
        if c in self.safe:
            return 1
        return 40 if self.suspect(c) else 8

    def find_path(self, start, goals, occupied=()):
        goals = set(goals)
        if not goals:
            return None
        few = len(goals) <= 8

        def h(c):
            if not few:
                return 0                            # 목표가 많으면 다익스트라
            return min(abs(c[0] - g[0]) + abs(c[1] - g[1]) for g in goals)

        g = {start: 0}
        came = {start: None}
        pq = [(h(start), 0, start)]
        while pq:
            f, gc, c = heapq.heappop(pq)
            if gc > g[c]:
                continue
            if c in goals:
                path = []
                while c is not None:
                    path.append(c)
                    c = came[c]
                return path[::-1]
            for n in self.nb4(c):
                step = self.cost(n)
                if step is None:
                    continue
                if n in occupied:
                    continue                        # 다른 유닛이 선 칸은 지나지 않는다
                ng = gc + step
                if ng < g.get(n, 1 << 30):
                    g[n] = ng
                    came[n] = c
                    heapq.heappush(pq, (ng + h(n), ng, n))
        return None


# ---------------- 머릿속 그리기 ----------------
def show_mind(path, label):
    alive = K.alive_syms()
    debug.say('대칭 후보: ' + (', '.join(SYM_KO[s] for s in alive) or '없음'))
    debug.say('목표: ' + label)
    for c in K.trap:
        debug.mark(*c, 'red')
    shown = 0
    for c in K.safe:
        if c not in K.vib and K.tile.get(c) != WALL and shown < 150:
            debug.mark(*c, 'green')
            shown += 1
    for c in K.vib:
        if K.vib[c]:
            for n in K.nb4(c):
                if K.suspect(n) and n not in K.trap:
                    debug.mark(*n, 'yellow')
    if K.enemy_base is None:
        for s in alive:
            debug.mark(*mirror(s, *K.base, K.w, K.h), 'purple')
    if path:
        debug.path(path, 'white')


def step_along(me, path, occupied):
    if not path or len(path) < 2:
        return None
    nxt = path[1]
    if nxt in occupied:
        return None
    return Move(direction_to(me.x, me.y, *nxt))


# ---------------- 역할 ----------------
def turn(me, view, memory):
    global K
    if K is None:
        K = Knowledge(view.width, view.height, view.my_camp)
    K.observe(me, view, memory)
    if me.kind == CAMP:
        return base_turn(me, view, memory)
    if me.kind == EXPLORER:
        return explorer_turn(me, view)
    return guardian_turn(me, view, memory)


PLAN = [EXPLORER, ARCHER, EXPLORER, ARCHER, ARCHER, EXPLORER, ARCHER, ARCHER]


def base_turn(me, view, memory):
    global plan_i
    kind = PLAN[plan_i % len(PLAN)]
    debug.say(f'다음 생산: {"탐험가" if kind == EXPLORER else "궁수"} (금고 {me.bank}/{COST[kind]})')
    if view.unit_count >= 10 or me.bank < COST[kind]:
        return None
    for d in 'NESW':
        dx, dy = DIRS[d]
        c = (me.x + dx, me.y + dy)
        if view.tile(*c) not in (None, WALL) and not any(u.x == c[0] and u.y == c[1] for u in view.units()):
            plan_i += 1
            if kind == ARCHER:
                memory[3] += 1
            return Spawn(kind, d)
    return None


def explorer_turn(me, view):
    pos = (me.x, me.y)
    occupied = {(u.x, u.y) for u in view.units() if u.id != me.id}
    home = {n for n in K.nb4(K.base) if n not in K.walls and n not in occupied}

    if me.carry >= CARRY_MAX or (me.carry > 0 and me.round > MAX_ROUNDS - 30):
        goals, label = home, '귀환 (짐 %d)' % me.carry
    elif K.tile.get(pos) == GOLD and me.carry < CARRY_MAX:
        show_mind(None, '채굴')
        return Mine()
    else:
        ores = {c for c, t in K.tile.items() if t == GOLD} - occupied
        if ores:
            goals, label = ores, '금'
        else:
            frontier = {c for c in K.safe if c not in K.vib and c not in K.walls
                        and c != K.base and c != K.enemy_base and c not in occupied}
            if frontier:
                goals, label = frontier, '탐사 (안전 증명된 칸)'
            else:
                goals = {n for c in K.vib for n in K.nb4(c)
                         if n not in K.safe and n not in K.trap and n not in K.walls and n not in occupied}
                label = '탐사 (위험 감수)'
    path = K.find_path(pos, goals, occupied)
    if path is None and me.carry > 0:
        path, label = K.find_path(pos, home, occupied), '귀환'
    show_mind(path, label + (' → (%d,%d)' % path[-1] if path else ' (길 없음)'))
    return step_along(me, path, occupied)


def guardian_turn(me, view, memory):
    pos = (me.x, me.y)
    units = view.units()
    occupied = {(u.x, u.y) for u in units if u.id != me.id}
    enemies = [u for u in units if u.team != me.team]

    near = [u for u in enemies if cheb(me.x, me.y, u.x, u.y) <= 1]
    if near:
        t = min(near, key=lambda u: (u.kind == CAMP, u.kind != ARCHER, u.hp, u.id))
        show_mind(None, '공격 #%d' % t.id)
        return Attack(t.x, t.y)

    if memory[3] < RALLY and me.round < 150:
        # 집결: 야영지 근처에서 기다린다
        show_mind(None, '집결 대기 (%d/%d)' % (memory[3], RALLY))
        # 야영지 바로 옆이면 생산 자리를 비켜 준다
        bx, by = K.base
        if abs(me.x - bx) + abs(me.y - by) <= 2:
            for n in sorted(K.nb4(pos)):
                far = abs(n[0] - bx) + abs(n[1] - by) > abs(me.x - bx) + abs(me.y - by)
                if far and n in K.safe and n not in occupied and K.cost(n) is not None:
                    return Move(direction_to(me.x, me.y, *n))
        return None

    if K.enemy_base is not None:
        eb = K.enemy_base
        goals = {(eb[0] + dx, eb[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - {eb}
        label = '적 야영지 (%d,%d)' % eb
    elif enemies:
        e = min(enemies, key=lambda u: (abs(u.x - me.x) + abs(u.y - me.y), u.id))
        goals, label = set(K.nb4((e.x, e.y))), '추격 #%d' % e.id
    else:
        cands = [mirror(s, *K.base, K.w, K.h) for s in K.alive_syms()]
        cand = min(cands, key=lambda c: (abs(c[0] - me.x) + abs(c[1] - me.y), c))
        goals = {(x, y) for x in range(K.w) for y in range(K.h)
                 if (x - cand[0]) ** 2 + (y - cand[1]) ** 2 <= 8 and (x, y) != cand}
        label = '정찰: 후보 (%d,%d)' % cand
    goals = {c for c in goals if K.inb(c) and K.cost(c) is not None}
    path = K.find_path(pos, goals, occupied)
    show_mind(path, label)
    return step_along(me, path, occupied)
