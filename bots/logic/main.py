"""추론하는 예시 봇.

쓰는 기법
- 명제논리: "바람 없는 칸의 상하좌우는 안전하다", "바람 칸의 미지 이웃이 하나뿐이면 그 칸이 구덩이다".
  웜퍼스도 같다: "악취 없는 칸의 상하좌우에는 웜퍼스가 없다", "악취 칸의 미지 이웃이 하나뿐이면 그 칸이 웜퍼스 굴이다".
- 1차 술어 논리: "모든 칸 c 에 대해 Trap(c) <-> Trap(mirror(c))" 를 구체적인 칸에 적용 (전칭 예화).
- 대칭 추론: 관측과 모순되는 대칭 후보를 지워 적 야영지 위치를 찾는다.
- A*: 안전한 칸은 비용 1, 모르는 칸은 비싸게, 의심 칸은 더 비싸게. 휴리스틱은 맨해튼 거리 (허용 가능).

유닛마다 이 파일이 따로 실행되므로 전역 변수 K 는 그 유닛만의 지식 베이스다.
팀 공유 memory 칸 쓰임: [0] 지운 대칭 비트, [1],[2] 적 야영지 x+1, y+1, [3] 만든 궁수 수.
"""
import heapq

from wumpus.api import (MAX_ROUNDS, Move, Mine, Shoot, Push, Spawn, Attack, sight_cells, BOW_RANGE, MELEE_RANGE, CARRY, debug, DIRS, mirror, cheb, direction_to,
                        EXPLORER, ARCHER, CAMP, WALL, GOLD, PIT, CAMP_TILE,
                        CARRY_MAX, SAFE_RADIUS, COST, ARROW_RANGE, ARCHER_CARRY, WUMPUS_CLEAR, ARROWS_MAX)

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
        self.smell = {}         # 내가 서 본 칸 -> 악취 여부
        self.safe = set()       # 구덩이가 아님이 증명된 칸
        self.trap = set()
        self.nw = set()         # 웜퍼스 굴이 아님이 증명된 칸
        self.wump = set()       # 웜퍼스 굴로 증명된 칸
        self.screams = 0
        self.loot = {}          # 본 떨어진 금
        self.garrows = {}       # 본 떨어진 화살
        self.ruled_out = 0
        self.enemy_base = None
        self._add_safe_zone(base)
        # 규칙: 웜퍼스 굴은 야영지에서 체비셰프 WUMPUS_CLEAR 밖에 있다
        for x in range(base[0] - WUMPUS_CLEAR, base[0] + WUMPUS_CLEAR + 1):
            for y in range(base[1] - WUMPUS_CLEAR, base[1] + WUMPUS_CLEAR + 1):
                self.nw.add((x, y))

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
        if view.screams > self.screams:          # 비명: 웜퍼스가 쓰러졌다. 오래된 악취 기억은 버린다
            self.screams = view.screams
            self.smell = {c: v for c, v in self.smell.items() if not v}
            self.wump.clear()
        for c in view.visible_cells():
            t = view.tile(*c)
            self.tile[c] = t
            ga = view.arrows_at(*c)
            if ga:
                self.garrows[c] = ga
            else:
                self.garrows.pop(c, None)
            lt = view.loot(*c)
            if lt:
                self.loot[c] = lt
            else:
                self.loot.pop(c, None)
            if t == WALL:
                self.walls.add(c)
            elif t == PIT:
                self.trap.add(c)
                self.safe.discard(c)
            elif t == GOLD:
                self.safe.add(c)                    # 규칙: 금 칸에는 구덩이도 웜퍼스도 없다
                self.nw.add(c)
            elif t == CAMP_TILE and c != self.base and self.enemy_base is None:
                self._found_enemy(c)
        for u in view.units():
            self.nw.add((u.x, u.y))                 # 유닛이 서 있는 칸은 굴이 아니다
        if me.kind != CAMP:
            self.vib[(me.x, me.y)] = view.breeze
            self.smell[(me.x, me.y)] = view.stench
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
            for c, v in self.smell.items():         # 웜퍼스: 바람과 같은 규칙
                ns = [n for n in self.nb4(c) if n not in self.walls]
                if not v:
                    for n in ns:
                        if n not in self.nw:
                            self.nw.add(n)
                            changed = True
                else:
                    unknown = [n for n in ns if n not in self.nw and n not in self.trap]
                    if len(unknown) == 1 and unknown[0] not in self.wump:
                        self.wump.add(unknown[0])
                        changed = True
            # 대칭이 하나로 정해지면 안전 · 구덩이 · 굴 사실을 거울 칸에도 적용한다
            alive = self.alive_syms()
            if len(alive) == 1:
                s = alive[0]
                for src, dst, bad in ((self.safe, self.safe, self.trap), (self.trap, self.trap, None),
                                      (self.nw, self.nw, self.wump), (self.wump, self.wump, None)):
                    for c in list(src):
                        m = mirror(s, *c, self.w, self.h)
                        if m not in dst and (bad is None or m not in bad):
                            dst.add(m)
                            changed = True

    def suspect(self, c):
        """바람한 칸에 붙어 있고 안전이 증명되지 않은 칸."""
        return c not in self.safe and any(self.vib.get(n) for n in self.nb4(c))

    def wsuspect(self, c):
        """악취 칸에 붙어 있고 굴이 아님이 증명되지 않은 칸."""
        return c in self.wump or (c not in self.nw and any(self.smell.get(n) for n in self.nb4(c)))

    # --- A* ---
    def cost(self, c):
        if c in self.walls or c in self.trap or c == self.base or c == self.enemy_base or self.wsuspect(c):
            return None
        near_w = any(abs(c[0] - w[0]) + abs(c[1] - w[1]) <= 3 for w in self.wump)   # 웜퍼스 공격 거리 (맨해튼 3): 되도록 피한다
        if c in self.safe:
            return 12 if near_w else 1
        return 40 if self.suspect(c) else (20 if near_w else 8)

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

    # --- 화살 줄 ---
    def line(self, a, b, occupied=()):
        """a 에서 b 로 화살이 닿는가: 같은 줄 · 같은 열, ARROW_RANGE 안, 사이에 벽 · 유닛 · 굴이 없다. 닿으면 방향을 돌려준다."""
        if a == b or (a[0] != b[0] and a[1] != b[1]):
            return None
        dist = abs(a[0] - b[0]) + abs(a[1] - b[1])
        if dist > ARROW_RANGE:
            return None
        d = ('E' if b[0] > a[0] else 'W') if a[1] == b[1] else ('S' if b[1] > a[1] else 'N')
        dx, dy = DIRS[d]
        c = a
        for _ in range(dist - 1):
            c = (c[0] + dx, c[1] + dy)
            if c in self.walls or c in occupied or c in self.wump:
                return None
        return d


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
    for c in K.smell:
        if K.smell[c]:
            for n in K.nb4(c):
                if K.wsuspect(n):
                    debug.mark(*n, 'blue')
    for c in K.wump:
        debug.mark(*c, 'purple')
    if K.enemy_base is None:
        for s in alive:
            debug.mark(*mirror(s, *K.base, K.w, K.h), 'white')
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
    if getattr(view, 'rules', {}).get('agent'):            # 시안 3: 자기 칸만 느끼는 모험가
        return agent_turn(me, view, memory)
    if getattr(view, 'rules', {}).get('unified'):          # 시안 2: 누구나 캐고 싸운다
        return miner_turn(me, view, memory) if me.kind == EXPLORER else archer_turn(me, view, memory)
    if me.kind == EXPLORER:
        return explorer_turn(me, view)
    return guardian_turn(me, view, memory)


PLAN = [EXPLORER, ARCHER, EXPLORER, ARCHER, ARCHER, EXPLORER, ARCHER, ARCHER]


def base_turn(me, view, memory):
    global plan_i
    kind = EXPLORER if getattr(view, 'rules', {}).get('agent') else PLAN[plan_i % len(PLAN)]
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


def threatened(c, archers, occupied):
    """칸 c 가 화살이 있는 적 궁수의 사격 줄 위인가."""
    return any(u.arrows != 0 and K.line((u.x, u.y), c, occupied - {(u.x, u.y), c}) for u in archers)


def explorer_turn(me, view):
    pos = (me.x, me.y)
    units = view.units()
    occupied = {(u.x, u.y) for u in units if u.id != me.id}
    home = {n for n in K.nb4(K.base) if n not in K.walls and n not in occupied}
    foes = [u for u in units if u.team != me.team and u.kind != CAMP]
    archers = [u for u in foes if u.kind == ARCHER]

    # 1. 밀치기: 옆의 적 뒤가 구덩이 · 웜퍼스 굴이면 밀어 떨어뜨린다
    for u in foes:
        d = direction_to(me.x, me.y, u.x, u.y)
        if d:
            dx, dy = DIRS[d]
            behind = (u.x + dx, u.y + dy)
            if behind in K.trap or behind in K.wump:
                show_mind(None, '밀치기 #%d → 구덩이' % u.id if behind in K.trap else '밀치기 #%d → 웜퍼스 굴' % u.id)
                return Push(d)

    # 2. 피하기: 적 궁수의 사격 줄 위면 줄 밖으로 비켜선다
    if threatened(pos, archers, occupied):
        best = None
        for n in sorted(K.nb4(pos)):
            if n in occupied or K.cost(n) is None or K.cost(n) > 8:
                continue
            k = (threatened(n, archers, occupied), K.cost(n), abs(n[0] - K.base[0]) + abs(n[1] - K.base[1]) if me.carry else 0)
            if best is None or k < best[0]:
                best = (k, n)
        if best is not None and not best[0][0]:
            show_mind(None, '사격 줄 피하기')
            return Move(direction_to(me.x, me.y, *best[1]))
        # 비킬 곳이 없으면 옆의 궁수를 밀어 낸다
        for u in archers:
            d = direction_to(me.x, me.y, u.x, u.y)
            if d:
                show_mind(None, '밀치기 #%d' % u.id)
                return Push(d)

    if me.carry >= CARRY_MAX or (me.carry > 0 and me.round > MAX_ROUNDS - 30):
        goals, label = home, '귀환 (짐 %d)' % me.carry
    elif (K.loot.get(pos) or K.tile.get(pos) == GOLD) and me.carry < CARRY_MAX:
        show_mind(None, '줍기' if K.loot.get(pos) else '채굴')
        return Mine()
    else:
        loot = {c for c in K.loot if K.cost(c) is not None} - occupied
        ores = {c for c, t in K.tile.items() if t == GOLD} - occupied
        if loot:
            goals, label = loot, '떨어진 금'
        elif ores:
            goals, label = ores, '금'
        else:
            frontier = {c for c in K.safe if c not in K.vib and c not in K.walls and not K.wsuspect(c)
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


def aligned_goals(target, occupied, lo=1):
    """target 을 쏠 수 있는 칸들 (같은 줄 · 같은 열, 거리 lo..ARROW_RANGE, 사이가 트임)."""
    out = set()
    for d, (dx, dy) in DIRS.items():
        for k in range(1, ARROW_RANGE + 1):
            c = (target[0] + dx * k, target[1] + dy * k)
            if not K.inb(c) or c in K.walls:
                break
            if k >= lo and K.cost(c) is not None and c not in occupied and K.line(c, target, occupied):
                out.add(c)
    return out


def guardian_turn(me, view, memory):
    pos = (me.x, me.y)
    units = view.units()
    occupied = {(u.x, u.y) for u in units if u.id != me.id}
    enemies = [u for u in units if u.team != me.team]
    bx, by = K.base

    # 0. 적 야영지 바로 옆이면 횃불로 태운다 (화살을 쓰지 않는다). 단 쏠 수 있는 적 궁수가 있으면 그쪽이 먼저
    camp_d = None
    for u in enemies:
        if u.kind == CAMP:
            camp_d = direction_to(me.x, me.y, u.x, u.y)
    armed_foe = me.arrows > 0 and any(u.kind == ARCHER and K.line(pos, (u.x, u.y), occupied - {(u.x, u.y)}) for u in enemies)
    if camp_d and not armed_foe:
        show_mind(None, '횃불로 적 야영지 태우기')
        return Shoot(camp_d)

    # 1. 쏠 수 있는 적이 줄 위에 있으면 쏜다 (궁수 > 탐험가 > 야영지)
    if me.arrows > 0:
        shots = []
        for u in enemies:
            d = K.line(pos, (u.x, u.y), occupied - {(u.x, u.y)})
            if d:
                shots.append(((u.kind == CAMP, u.kind != ARCHER, u.hp, u.id), d, u))
        if shots:
            _, d, t = min(shots)
            show_mind(None, '화살 → #%d (남은 화살 %d)' % (t.id, me.arrows - 1))
            return Shoot(d)
        # 웜퍼스 굴을 알고 줄 위에 있으면 쏜다
        for c in sorted(K.wump):
            d = K.line(pos, c, occupied)
            if d and not enemies:
                show_mind(None, '웜퍼스 사냥 (%d,%d)' % c)
                return Shoot(d)

    # 1b. 화살이 없으면 바로 옆 적을 단검으로 찌른다
    if me.arrows == 0:
        stab = [u for u in enemies if u.kind != CAMP and direction_to(me.x, me.y, u.x, u.y)]
        if stab:
            t = min(stab, key=lambda u: (u.hp, u.id))
            show_mind(None, '단검 → #%d' % t.id)
            return Shoot(direction_to(me.x, me.y, t.x, t.y))
    # 1c. 떨어진 화살: 서 있으면 줍고, 화살통이 비었거나 가까이 있으면 주우러 간다 (집보다 가까울 때)
    if K.garrows.get(pos) and me.arrows < ARROWS_MAX:
        show_mind(None, '화살 줍기 (%d개)' % K.garrows[pos])
        return Mine()
    if me.arrows < ARROWS_MAX and K.garrows:
        cand = {c for c in K.garrows if K.cost(c) is not None} - occupied
        reach = 99 if me.arrows == 0 else 4
        if cand:
            path = K.find_path(pos, cand, occupied)
            home_d = max(abs(me.x - bx), abs(me.y - by)) - 1
            if path and len(path) - 1 <= reach and (me.arrows > 0 or len(path) - 1 < home_d):
                show_mind(path, '떨어진 화살 주우러 → (%d,%d)' % path[-1])
                return step_along(me, path, occupied)

    # 2. 화살이 없으면 야영지로 채우러 간다 (적 야영지가 더 가까우면 그 옆으로 가서 태운다)
    eb = K.enemy_base
    if me.arrows == 0 and eb and (memory[3] >= RALLY or me.round >= 150) and             abs(eb[0] - me.x) + abs(eb[1] - me.y) < abs(bx - me.x) + abs(by - me.y):
        path = K.find_path(pos, {c for c in K.nb4(eb) if K.cost(c) is not None} - occupied, occupied)
        if path:
            show_mind(path, '화살 없음 → 적 야영지 옆으로 (횃불)')
            return step_along(me, path, occupied)
    if me.arrows == 0:
        goals = {(bx + dx, by + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - {K.base}
        path = K.find_path(pos, {c for c in goals if K.cost(c) is not None}, occupied)
        show_mind(path, '화살 채우러 귀환')
        return step_along(me, path, occupied)

    # 3. 떨어진 금: 서 있으면 줍고, 다 차면 바치러 간다
    if K.loot.get(pos) and me.carry < ARCHER_CARRY and not enemies:
        show_mind(None, '떨어진 금 줍기')
        return Mine()
    if me.carry >= ARCHER_CARRY or (me.carry > 0 and not enemies):
        home = {n for n in K.nb4(K.base) if n not in K.walls and n not in occupied}
        path = K.find_path(pos, home, occupied)
        if path:
            show_mind(path, '금 바치러 (짐 %d)' % me.carry)
            return step_along(me, path, occupied)
    near_loot = {c for c in K.loot if abs(c[0] - me.x) + abs(c[1] - me.y) <= 4 and K.cost(c) is not None} - occupied
    if near_loot and not enemies:
        path = K.find_path(pos, near_loot, occupied)
        if path:
            show_mind(path, '떨어진 금으로')
            return step_along(me, path, occupied)

    # 4. 보이는 적: 쏠 수 있는 자리로
    foes = [u for u in enemies if u.kind != CAMP]
    if foes:
        e = min(foes, key=lambda u: (abs(u.x - me.x) + abs(u.y - me.y), u.id))
        goals = aligned_goals((e.x, e.y), occupied, lo=2)
        path = K.find_path(pos, goals, occupied)
        if path:
            show_mind(path, '조준 자리로 (적 #%d)' % e.id)
            return step_along(me, path, occupied)

    if memory[3] < RALLY and me.round < 150:
        # 집결: 야영지 근처에서 기다린다. 아는 웜퍼스가 가까우면 사냥한다
        if K.wump:
            goals = set()
            for c in K.wump:
                goals |= aligned_goals(c, occupied, lo=2)
            path = K.find_path(pos, goals, occupied)
            if path and len(path) <= 12:
                show_mind(path, '웜퍼스 사냥 자리로')
                return step_along(me, path, occupied)
        show_mind(None, '집결 대기 (%d/%d)' % (memory[3], RALLY))
        if abs(me.x - bx) + abs(me.y - by) <= 2:
            for n in sorted(K.nb4(pos)):
                far = abs(n[0] - bx) + abs(n[1] - by) > abs(me.x - bx) + abs(me.y - by)
                if far and n in K.safe and n not in occupied and K.cost(n) is not None:
                    return Move(direction_to(me.x, me.y, *n))
        return None

    if K.enemy_base is not None:
        eb = K.enemy_base
        goals = {c for c in K.nb4(eb) if K.cost(c) is not None} - occupied   # 상하좌우 옆: 횃불로 태울 자리
        if not goals or not K.find_path(pos, goals, occupied):
            goals = aligned_goals(eb, occupied)
        label = '적 야영지 (%d,%d)' % eb
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


# ---------------- 시안 2 (unified): 누구나 캐고 싸운다 ----------------
def los(a, b):
    """두 칸 사이 시선이 벽에 막히지 않았나 (엔진과 같은 계산)."""
    return not any(c in K.walls for c in sight_cells(a[0], a[1], b[0], b[1]))


def pick_target(pos, enemies, r):
    """사거리 r (맨해튼) 안에서 칠 대상. 궁수 > 광부 > 야영지 (야영지는 바로 옆만), 체력 낮은 쪽."""
    cand = []
    for u in enemies:
        d = abs(u.x - pos[0]) + abs(u.y - pos[1])
        if d < 1 or d > r or (u.kind == CAMP and d != 1) or not los(pos, (u.x, u.y)):
            continue
        cand.append(((u.kind == CAMP, u.kind != ARCHER, u.hp, u.id), u))
    return min(cand, key=lambda t: t[0])[1] if cand else None


def range_goals(target, occupied, r=BOW_RANGE, lo=2):
    """target 을 칠 수 있는 칸들 (맨해튼 lo..r, 시선이 트임)."""
    out = set()
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            d = abs(dx) + abs(dy)
            c = (target[0] + dx, target[1] + dy)
            if lo <= d <= r and K.inb(c) and c not in occupied and K.cost(c) is not None and los(c, target):
                out.add(c)
    return out


def ore_in_range(p, r):
    """p 에서 칠 수 있는 (맨해튼 r 안, 시선 트임, 서 있는 칸 포함) 가장 가까운 금맥."""
    cs = [c for c, t in K.tile.items() if t == GOLD and abs(c[0] - p[0]) + abs(c[1] - p[1]) <= r and los(p, c)]
    return min(cs, key=lambda c: (abs(c[0] - p[0]) + abs(c[1] - p[1]), c)) if cs else None


def free_step(n, occupied):
    return n not in occupied and K.cost(n) is not None and K.cost(n) <= 8


def miner_turn(me, view, memory):
    """광부: 이동 1번 + 행동 1번. 싸움은 붙은 적만, 나머지는 캐서 나른다."""
    pos = (me.x, me.y)
    units = view.units()
    occupied = {(u.x, u.y) for u in units if u.id != me.id}
    enemies = [u for u in units if u.team != me.team]
    foes = [u for u in enemies if u.kind != CAMP]
    cap = CARRY[EXPLORER]
    home = {n for n in K.nb4(K.base) if n not in K.walls and n not in occupied}

    # 1. 밀치기: 옆의 적 뒤가 구덩이 · 웜퍼스 굴이면 밀어 떨어뜨린다
    for u in foes:
        d = direction_to(me.x, me.y, u.x, u.y)
        if d:
            dx, dy = DIRS[d]
            behind = (u.x + dx, u.y + dy)
            if behind in K.trap or behind in K.wump:
                show_mind(None, '밀치기 #%d → %s' % (u.id, '구덩이' if behind in K.trap else '웜퍼스 굴'))
                return Push(d)
    # 2. 바로 옆 적을 친다
    t = pick_target(pos, foes, MELEE_RANGE)
    if t:
        show_mind(None, '근접 공격 → #%d' % t.id)
        return Attack(t.x, t.y)
    # 3. 한 걸음 붙어서 친다 (이동 + 공격)
    best = None
    for n in sorted(K.nb4(pos)):
        if not free_step(n, occupied):
            continue
        t = pick_target(n, foes, MELEE_RANGE)
        if t and (best is None or (t.kind != ARCHER, t.hp) < best[0]):
            best = ((t.kind != ARCHER, t.hp), n, t)
    if best:
        _, n, t = best
        show_mind([pos, n], '붙어서 공격 → #%d' % t.id)
        return Move(direction_to(me.x, me.y, *n)), Attack(t.x, t.y)
    # 4. 옆에 아는 웜퍼스 굴이 있고 적이 없으면 굴을 친다
    if not foes:
        for c in sorted(K.wump):
            if abs(c[0] - me.x) + abs(c[1] - me.y) == 1:
                if me.hp <= 6:
                    break
                show_mind(None, '웜퍼스 치기 (%d,%d)' % c)
                return Attack(*c)
    # 5. 캐고 나르기 (이동한 칸이 금이면 같은 턴에 캔다)
    if me.carry >= cap or (me.carry > 0 and me.round > MAX_ROUNDS - 30):
        goals, label = home, '귀환 (짐 %d)' % me.carry
    elif ore_in_range(pos, MELEE_RANGE) and me.carry < cap:
        c = ore_in_range(pos, MELEE_RANGE)
        show_mind(None, '금맥 공격 (%d,%d)' % c)
        return Attack(*c)
    else:
        loot = {c for c in K.loot if K.cost(c) is not None} - occupied
        ores = set()
        for c, t in K.tile.items():
            if t == GOLD:
                ores |= {n for n in list(K.nb4(c)) + [c] if K.cost(n) is not None} - occupied
        if loot:
            goals, label = loot, '떨어진 금'
        elif ores:
            goals, label = ores, '금'
        else:
            frontier = {c for c in K.safe if c not in K.vib and c not in K.walls and not K.wsuspect(c)
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
    mv = step_along(me, path, occupied)
    if mv and len(path) >= 2:
        nxt = path[1]
        c = ore_in_range(nxt, MELEE_RANGE)
        if me.carry + (K.loot.get(nxt) or 0) < cap and c:
            return mv, Attack(*c)
        t = pick_target(nxt, enemies, MELEE_RANGE)
        if t and (t.kind != CAMP or me.carry == 0):
            return mv, Attack(t.x, t.y)
    return mv


def archer_turn(me, view, memory):
    """궁수: 이동 또는 행동 1번. 사거리 3 안의 적을 쏘고, 한가하면 가까운 금을 캔다."""
    pos = (me.x, me.y)
    units = view.units()
    occupied = {(u.x, u.y) for u in units if u.id != me.id}
    enemies = [u for u in units if u.team != me.team]
    foes = [u for u in enemies if u.kind != CAMP]
    bx, by = K.base
    cap = CARRY[ARCHER]
    home = {n for n in K.nb4(K.base) if n not in K.walls and n not in occupied}

    # 1. 사거리 안의 적
    t = pick_target(pos, enemies, BOW_RANGE)
    if t:
        show_mind(None, '활 → #%d' % t.id)
        return Attack(t.x, t.y)
    # 2. 웜퍼스 굴: 포효가 닿지 않는 거리 3 에서만 쏜다 (적이 안 보일 때)
    if not foes:
        for c in sorted(K.wump):
            if abs(c[0] - me.x) + abs(c[1] - me.y) == BOW_RANGE and los(pos, c) and me.hp > 6:   # 웜퍼스 한 방 (6) 을 버틸 체력일 때만
                show_mind(None, '웜퍼스 사냥 (%d,%d)' % c)
                return Attack(*c)
    # 3. 짐이 차면 바치러
    if me.carry >= cap or (me.carry > 0 and me.round > MAX_ROUNDS - 30):
        path = K.find_path(pos, home, occupied)
        if path:
            show_mind(path, '금 바치러 (짐 %d)' % me.carry)
            return step_along(me, path, occupied)
    # 4. 보이는 적: 쏠 수 있는 자리로
    if foes:
        e = min(foes, key=lambda u: (abs(u.x - me.x) + abs(u.y - me.y), u.id))
        path = K.find_path(pos, range_goals((e.x, e.y), occupied), occupied)
        if path:
            show_mind(path, '사격 자리로 (적 #%d)' % e.id)
            return step_along(me, path, occupied)
    # 5. 사거리 안의 금맥을 쏘아 캔다
    c = ore_in_range(pos, BOW_RANGE)
    if c and me.carry < cap:
        show_mind(None, '금맥 사격 (%d,%d)' % c)
        return Attack(*c)
    rally = memory[3] < RALLY and me.round < 150
    # 웜퍼스 사냥: 아는 굴이 가까우면 거리 3 자리로 (집결 뒤에도)
    if K.wump and not foes and me.carry < cap and me.hp > 6:
        goals = set()
        for c in K.wump:
            goals |= range_goals(c, occupied, lo=BOW_RANGE)
        path = K.find_path(pos, goals, occupied)
        if path and len(path) <= (12 if rally else 9):
            show_mind(path, '웜퍼스 사냥 자리로 (거리 3)')
            return step_along(me, path, occupied)
    # 6. 집결하는 동안: 가까운 웜퍼스 사냥, 아니면 가까운 금을 캔다
    if rally:
        if K.wump:
            goals = set()
            for c in K.wump:
                goals |= range_goals(c, occupied)
            path = K.find_path(pos, goals, occupied)
            if path and len(path) <= 12:
                show_mind(path, '웜퍼스 사냥 자리로')
                return step_along(me, path, occupied)
        gold = {c for c in K.loot if K.cost(c) is not None}
        for c, t in K.tile.items():
            if t == GOLD:
                gold |= range_goals(c, occupied, lo=0)
        path = K.find_path(pos, gold - occupied, occupied)
        if path and len(path) <= 10:
            show_mind(path, '집결 중 채굴 → (%d,%d)' % path[-1])
            return step_along(me, path, occupied)
        show_mind(None, '집결 대기 (%d/%d)' % (memory[3], RALLY))
        return None
    # 7. 출정: 적 야영지 바로 옆으로 (야영지는 옆에서만 칠 수 있다)
    if K.enemy_base is not None:
        eb = K.enemy_base
        goals = {c for c in K.nb4(eb) if K.cost(c) is not None} - occupied
        label = '적 야영지 (%d,%d)' % eb
        if not goals:
            goals = range_goals(eb, occupied, lo=2)
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


# ---------------- 시안 3 (agent): 자기 칸만 느끼는 모험가 ----------------
last_target = None      # 지난 차례에 들어가려던 칸 (부딪힘이면 벽인지 판단)
bumps = {}              # 칸 -> 연달아 부딪힌 횟수
atk_i = 0               # 발소리만 날 때 옆 칸을 차례로 쳐 본다


def mates_from(memory, me):
    """팀 공유 메모리 [8..55]: 모험가마다 (x+1)+64*(y+1) 와 그 라운드. 지난 라운드까지 적힌 팀원 위치."""
    k = me.id % 24
    memory[8 + 2 * k] = (me.x + 1) + 64 * (me.y + 1)
    memory[9 + 2 * k] = me.round
    out = set()
    for j in range(24):
        v, r = memory[8 + 2 * j], memory[9 + 2 * j]
        if j != k and v and me.round - r <= 1:
            out.add((v % 64 - 1, v // 64 - 1))
    return out


def agent_turn(me, view, memory):
    global last_target, atk_i
    pos = (me.x, me.y)
    eb = view.enemy_camp
    if K.enemy_base is None:
        K._found_enemy(eb)
    # 1. 부딪힘: 발소리가 없는데 막혔으면 그 칸은 벽이다 (발소리가 있으면 모험가일 수도 있다)
    if view.bump and last_target is not None and last_target not in (K.base, eb):
        bumps[last_target] = bumps.get(last_target, 0) + 1
        if view.footsteps == 0 or bumps[last_target] >= 3:    # 세 번 연달아 막히면 모험가가 아니라 벽이다
            K.walls.add(last_target)
            K.safe.discard(last_target)
    elif last_target is not None:
        bumps.pop(last_target, None)
    last_target = None
    mates = mates_from(memory, me)
    adj = [n for n in K.nb4(pos) if n not in K.walls and n not in mates and n != K.base and n not in K.trap and n not in K.wump]

    def go(goals, label):
        global last_target
        path = K.find_path(pos, goals, mates)
        show_mind(path, label + (' → (%d,%d)' % path[-1] if path else ' (길 없음)'))
        mv = step_along(me, path, mates)
        if mv:
            last_target = path[1]
            k = me.id % 24                       # 움직인 뒤 자리를 미리 적어 둔다 (팀원이 헷갈리지 않게)
            memory[8 + 2 * k] = (path[1][0] + 1) + 64 * (path[1][1] + 1)
        return mv

    # 2. 적 야영지가 바로 옆이면 친다
    if abs(eb[0] - me.x) + abs(eb[1] - me.y) == 1 and me.carry == 0:
        show_mind(None, '적 야영지 공격')
        return Attack(*eb)
    # 3. 싸움: 아프면 반드시, 발소리만 나면 짐이 없을 때 팀원이 아닌 옆 칸을 친다 (적이 어디인지 추론)
    enemy_near = view.footsteps > sum(1 for n in K.nb4(pos) if n in mates)   # 발소리가 옆 팀원 수보다 많으면 적이 있다
    if (view.hurt or enemy_near) and adj and (view.hurt or me.carry == 0):
        cand = [n for n in adj if n != eb]
        if cand:
            t = cand[atk_i % len(cand)]
            if not view.hurt:
                atk_i += 1
            show_mind(None, '검 → (%d,%d) (%s)' % (t[0], t[1], '아픔' if view.hurt else '발소리'))
            return Attack(*t)
    # 4. 반짝임: 이 칸의 금맥을 캔다 (떨어진 금은 들어서면 저절로 줍는다)
    if view.glitter and (view.gold(me.x, me.y) or 0) > 0 and me.carry < CARRY_MAX:
        show_mind(None, '반짝임 → 채굴')
        return Mine()
    home = {n for n in K.nb4(K.base) if n not in K.walls}
    if me.carry >= CARRY_MAX or (me.carry > 0 and me.round > MAX_ROUNDS - 40):
        return go(home - mates, '귀환 (짐 %d)' % me.carry)
    # 5. 아는 금맥으로
    ores = {c for c, t in K.tile.items() if t == GOLD} - {pos}
    if ores:
        return go(ores - mates, '아는 금맥')
    # 6. 늦게는 적 야영지를 치러 간다
    if me.round > MAX_ROUNDS * 0.6:
        return go({n for n in K.nb4(eb) if n not in K.walls} - mates, '적 야영지로')
    # 7. 탐험: 안전이 증명된, 아직 서 보지 않은 칸 → 없으면 바람 옆의 모르는 칸 (위험 감수)
    frontier = {c for c in K.safe if c not in K.vib and c not in K.walls and not K.wsuspect(c) and c not in (K.base, eb)} - mates
    if frontier:
        return go(frontier, '탐사 (안전 증명된 칸)')
    risky = {n for c in K.vib for n in K.nb4(c) if n not in K.safe and n not in K.trap and n not in K.walls} - mates
    return go(risky, '탐사 (위험 감수)')
