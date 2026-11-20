"""게임 엔진. 같은 봇 · 같은 맵 · 같은 시드면 같은 결과가 나온다."""
import os
import random
import time

from . import api
from .api import (DIRS, EXPLORER, ARCHER, CAMP, EMPTY, WALL, GOLD, PIT, CAMP_TILE,
                  MAX_ROUNDS, MEMORY_SIZE, MAX_UNITS, START_BANK, INCOME_EVERY, COST, HP,
                  VISION_R2, ATTACK_DAMAGE, CAMP_ATTACK, CARRY_MAX, REGROW_EVERY, cheb, Move, Mine, Attack, Spawn)

TEAM_NAMES = ('붉은 원정대', '푸른 원정대')
KIND_CODE = {EXPLORER: 'E', ARCHER: 'G', CAMP: 'B'}


def _offsets(r2):
    r = int(r2 ** 0.5) + 1
    return [(dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1) if dx * dx + dy * dy <= r2]


OFFSETS = {k: _offsets(v) for k, v in VISION_R2.items()}


class Unit:
    def __init__(self, uid, team, kind, x, y):
        self.id, self.team, self.kind = uid, team, kind
        self.x, self.y = x, y
        self.hp = HP[kind]
        self.carry = 0
        self.alive = True
        self.ns = None          # 이 유닛 전용 봇 이름공간


class Me:
    """봇에게 주는 자기 정보 (복사본)."""

    def __init__(self, u, g):
        self.id, self.team, self.kind = u.id, u.team, u.kind
        self.x, self.y, self.hp, self.carry = u.x, u.y, u.hp, u.carry
        self.round = g.round
        self.bank = g.bank[u.team]


class UnitInfo:
    __slots__ = ('id', 'team', 'kind', 'x', 'y', 'hp', 'carry')

    def __init__(self, u):
        self.id, self.team, self.kind = u.id, u.team, u.kind
        self.x, self.y, self.hp, self.carry = u.x, u.y, u.hp, u.carry

    def __repr__(self):
        return f'UnitInfo(#{self.id} {self.kind} team={self.team} ({self.x},{self.y}) hp={self.hp})'


class View:
    """유닛이 지금 보고 느끼는 것."""

    def __init__(self, g, u):
        self._g = g
        self._vis = g.vision(u)
        self.width, self.height = g.w, g.h
        self.round = g.round
        self.team = u.team
        self.my_camp = g.bases[u.team].x, g.bases[u.team].y
        self.bank = g.bank[u.team]
        self.score = g.score[u.team]
        self.unit_count = sum(1 for v in g.units if v.alive and v.team == u.team)
        # 바람: 지금 선 칸의 상하좌우 이웃 중에 구덩이가 있으면 True
        self.breeze = u.kind != CAMP and g.breeze_at(u.x, u.y)

    def visible(self, x, y):
        return (x, y) in self._vis

    def visible_cells(self):
        return sorted(self._vis)

    def tile(self, x, y):
        """보이는 칸이면 '.', '#', 'G', 'P', 'C' 중 하나. 안 보이면 None. 숨은 구덩이는 '.' 로 보인다."""
        if (x, y) not in self._vis:
            return None
        return self._g.public_tile(x, y)

    def gold(self, x, y):
        if (x, y) not in self._vis:
            return None
        return self._g.ore.get((x, y), 0)

    def units(self):
        """보이는 유닛 목록 (야영지 포함, 자기 자신 포함)."""
        g = self._g
        out = []
        for c in self._vis:
            v = g.at.get(c)
            if v is not None and v.alive:
                out.append(UnitInfo(v))
        out.sort(key=lambda v: v.id)
        return out


class Game:
    def __init__(self, gmap, bot_sources, bot_names, seed=0, time_limit_ms=None):
        self.map = gmap
        self.w, self.h = gmap.w, gmap.h
        self.walls = set(gmap.walls)
        self.ore = dict(gmap.ore)
        self.ore_max = dict(gmap.ore)   # 금맥마다 처음 양 (다시 자랄 때 한도)
        self.traps = set(gmap.traps)
        self.revealed = set()
        self.seed = seed
        self.time_limit_ms = time_limit_ms
        self.tstat = [[0.0, 0.0, 0, 0], [0.0, 0.0, 0, 0]]   # 팀마다 [합 ms, 최대 ms, 차례 수, 시간 초과 수]
        self.sources = bot_sources
        self.names = bot_names
        self.codes = [compile(src, f'<bot {i}: {bot_names[i]}>', 'exec') for i, src in enumerate(bot_sources)]
        self.bank = [START_BANK, START_BANK]
        self.score = [0, 0]
        self.memory = [[0] * MEMORY_SIZE, [0] * MEMORY_SIZE]
        self.round = 0
        self.next_id = 1
        self.at = {}
        self.units = []
        self.bases = []
        self.over = False
        self.winner = -1
        self.reason = ''
        self.events = []
        self.debug = {}
        self.ore_changed = set()
        for t, (x, y) in enumerate(gmap.bases):
            b = self._new_unit(t, CAMP, x, y)
            self.bases.append(b)
        # 처음 유닛: 팀마다 탐험가 둘 (번갈아 번호를 매긴다)
        for _ in range(2):
            for t in (0, 1):
                c = self._free_adjacent(self.bases[t])
                if c:
                    self.units.append(self._new_unit(t, EXPLORER, *c))
        self.frames = [self._frame()]

    # ---------- 칸 ----------
    def inb(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def public_tile(self, x, y):
        c = (x, y)
        if c in self.walls:
            return WALL
        v = self.at.get(c)
        if v is not None and v.kind == CAMP:
            return CAMP_TILE
        if c in self.revealed:
            return PIT
        if self.ore.get(c, 0) > 0:
            return GOLD
        return EMPTY

    def breeze_at(self, x, y):
        return any((x + dx, y + dy) in self.traps for dx, dy in DIRS.values())

    def vision(self, u):
        return {(u.x + dx, u.y + dy) for dx, dy in OFFSETS[u.kind] if self.inb(u.x + dx, u.y + dy)}

    def _free_adjacent(self, b):
        for dx, dy in DIRS.values():
            c = (b.x + dx, b.y + dy)
            if self.inb(*c) and c not in self.walls and c not in self.at and c not in self.traps:
                return c
        return None

    # ---------- 유닛 ----------
    def _new_unit(self, team, kind, x, y):
        u = Unit(self.next_id, team, kind, x, y)
        self.next_id += 1
        self.at[(x, y)] = u
        ns = {'__name__': f'bot_{team}_{u.id}'}
        try:
            exec(self.codes[team], ns)
            if not callable(ns.get('turn')):
                raise AttributeError('turn 함수가 없다')
            u.ns = ns
        except Exception as e:  # 봇 파일 자체가 깨졌으면 그 유닛은 아무것도 안 한다
            self.events.append(['err', u.id, f'불러오기 실패: {type(e).__name__}: {e}'[:160]])
        return u

    def _kill(self, u, cause):
        u.alive = False
        u.hp = 0
        self.at.pop((u.x, u.y), None)
        self.events.append(['die', u.id, u.x, u.y, cause])
        if u.kind == CAMP:
            self.over = True
            self.winner = 1 - u.team
            self.reason = '야영지 파괴'

    # ---------- 차례 ----------
    def _take_turn(self, u):
        act = None
        api.debug.reset()
        if u.ns is not None:
            me = Me(u, self)
            view = View(self, u)
            random.seed(self.seed * 1000003 + self.round * 1009 + u.id)
            t0 = time.perf_counter()
            try:
                act = u.ns['turn'](me, view, self.memory[u.team])
            except Exception as e:
                act = None
                self.events.append(['err', u.id, f'{type(e).__name__}: {e}'[:160]])
            ms = (time.perf_counter() - t0) * 1000
            ts = self.tstat[u.team]
            ts[0] += ms; ts[1] = max(ts[1], ms); ts[2] += 1
            if self.time_limit_ms and ms > self.time_limit_ms:      # 시간을 넘긴 차례는 행동을 버린다
                act = None; ts[3] += 1
                self.events.append(['err', u.id, f'시간 초과: {ms:.1f} ms > {self.time_limit_ms} ms'])
            self._fix_memory(u.team)
        d = api.debug.dump()
        if d:
            self.debug[u.id] = d
        if act is not None:
            self._apply(u, act)
        if u.alive and u.kind == EXPLORER and u.carry > 0:
            b = self.bases[u.team]
            if abs(u.x - b.x) + abs(u.y - b.y) == 1:
                self.score[u.team] += u.carry
                self.bank[u.team] += u.carry
                self.events.append(['dlv', u.id, u.carry, u.x, u.y, u.team])
                u.carry = 0
        if u.alive and u.kind == CAMP and CAMP_ATTACK > 0 and not self.over:
            near = [v for v in self.units if v.alive and v.team != u.team and cheb(u.x, u.y, v.x, v.y) <= 1]
            if near:
                t = min(near, key=lambda v: (v.hp, v.id))
                t.hp -= CAMP_ATTACK
                self.events.append(['atk', u.id, u.x, u.y, t.x, t.y, t.id])
                if t.hp <= 0:
                    self._kill(t, 'atk')

    def _fix_memory(self, team):
        mem = self.memory[team]
        fixed = []
        for v in list(mem[:MEMORY_SIZE]):
            try:
                v = int(v)
            except Exception:
                v = 0
            v &= 0xFFFFFFFF                       # 32비트 부호 있는 정수로 자른다
            fixed.append(v - (1 << 32) if v >= (1 << 31) else v)
        fixed += [0] * (MEMORY_SIZE - len(fixed))
        mem[:] = fixed

    def _apply(self, u, act):
        if isinstance(act, Move) and u.kind != CAMP:
            if act.d not in DIRS:
                return
            dx, dy = DIRS[act.d]
            n = (u.x + dx, u.y + dy)
            if not self.inb(*n) or n in self.walls or n in self.at:
                return
            del self.at[(u.x, u.y)]
            u.x, u.y = n
            self.at[n] = u
            if n in self.traps:
                self.revealed.add(n)
                self.events.append(['trap', u.id, n[0], n[1]])
                self._kill(u, 'trap')
        elif isinstance(act, Mine) and u.kind == EXPLORER:
            c = (u.x, u.y)
            if self.ore.get(c, 0) > 0 and u.carry < CARRY_MAX:
                self.ore[c] -= 1
                u.carry += 1
                self.ore_changed.add(c)
                self.events.append(['mine', u.id, u.x, u.y])
                if self.ore[c] == 0:
                    del self.ore[c]
        elif isinstance(act, Attack) and u.kind == ARCHER:
            try:
                tx, ty = int(act.x), int(act.y)
            except Exception:
                return
            if (tx, ty) == (u.x, u.y) or cheb(u.x, u.y, tx, ty) > 1:
                return
            t = self.at.get((tx, ty))
            if t is None or t.team == u.team:
                return
            t.hp -= ATTACK_DAMAGE
            self.events.append(['atk', u.id, u.x, u.y, tx, ty, t.id])
            if t.hp <= 0:
                self._kill(t, 'atk')
        elif isinstance(act, Spawn) and u.kind == CAMP:
            if act.kind not in COST or act.d not in DIRS:
                return
            if self.bank[u.team] < COST[act.kind]:
                return
            if sum(1 for v in self.units if v.alive and v.team == u.team) >= MAX_UNITS:
                return
            dx, dy = DIRS[act.d]
            n = (u.x + dx, u.y + dy)
            if not self.inb(*n) or n in self.walls or n in self.at or n in self.traps:
                return
            self.bank[u.team] -= COST[act.kind]
            v = self._new_unit(u.team, act.kind, *n)
            self.units.append(v)
            self.events.append(['spawn', v.id, v.team, KIND_CODE[v.kind], v.x, v.y])

    # ---------- 기록 ----------
    def _vis_hex(self, team):
        bits = [0] * (self.w * self.h)
        for u in [self.bases[team]] + self.units:
            if u.alive and u.team == team:
                for (x, y) in self.vision(u):
                    bits[y * self.w + x] = 1
        bits += [0] * (-len(bits) % 4)
        return ''.join('%x' % (bits[i] | bits[i + 1] << 1 | bits[i + 2] << 2 | bits[i + 3] << 3)
                       for i in range(0, len(bits), 4))

    def _frame(self):
        units = []
        for u in self.units:
            if u.alive:
                units.append([u.id, u.team, KIND_CODE[u.kind], u.x, u.y, u.hp, u.carry,
                              1 if self.breeze_at(u.x, u.y) else 0])
        fr = {
            'u': units,
            'o': [[x, y, self.ore.get((x, y), 0)] for (x, y) in sorted(self.ore_changed)],
            'bh': [max(0, b.hp) for b in self.bases],
            'bk': list(self.bank),
            'sc': list(self.score),
            'e': self.events,
            'v': [self._vis_hex(0), self._vis_hex(1)],
        }
        if self.debug:
            fr['d'] = {str(k): v for k, v in self.debug.items()}
        self.events, self.debug, self.ore_changed = [], {}, set()
        return fr

    # ---------- 경기 ----------
    def play(self):
        for r in range(1, MAX_ROUNDS + 1):
            self.round = r
            if r % INCOME_EVERY == 0:
                self.bank[0] += 1
                self.bank[1] += 1
            if REGROW_EVERY and r % REGROW_EVERY == 0:
                for c, mx in self.ore_max.items():
                    if self.ore.get(c, 0) < mx:
                        self.ore[c] = self.ore.get(c, 0) + 1
                        self.ore_changed.add(c)
            order = self.bases if r % 2 == 1 else self.bases[::-1]
            for u in list(order) + sorted(self.units, key=lambda v: v.id):
                if u.alive and not self.over:
                    self._take_turn(u)
            self.units = [u for u in self.units if u.alive]
            self.frames.append(self._frame())
            if self.over:
                break
        if not self.over:
            self._judge()
        return self.replay()

    def _judge(self):
        keys = [(self.score[t], self.bases[t].hp, sum(1 for u in self.units if u.team == t)) for t in (0, 1)]
        names = ('바친 금', '야영지 체력', '유닛 수')
        for i in range(3):
            if keys[0][i] != keys[1][i]:
                self.winner = 0 if keys[0][i] > keys[1][i] else 1
                self.reason = f'{MAX_ROUNDS}라운드 끝, {names[i]}'
                return
        self.winner = -1
        self.reason = '무승부'

    def replay(self):
        m = self.map
        rows = [''.join('#' if (x, y) in m.walls else '.' for x in range(m.w)) for y in range(m.h)]
        return {
            'format': 'wumpus-replay-1',
            'meta': {
                'w': m.w, 'h': m.h, 'sym': m.sym, 'map_seed': m.seed, 'seed': self.seed,
                'names': list(self.names), 'teams': list(TEAM_NAMES),
                'winner': self.winner, 'reason': self.reason, 'rounds': len(self.frames) - 1,
                'score': list(self.score), 'map': getattr(m, 'name', ''),
                'time_ms': [{'avg': round(t[0] / max(1, t[2]), 3), 'max': round(t[1], 3), 'turns': t[2], 'over': t[3]} for t in self.tstat],
                'time_limit_ms': self.time_limit_ms,
            },
            'const': {
                'hp': {'E': HP[EXPLORER], 'G': HP[ARCHER], 'B': HP[CAMP]},
                'carry': CARRY_MAX, 'max_rounds': MAX_ROUNDS,
                'cost': {'E': COST[EXPLORER], 'G': COST[ARCHER]},
                'vision': {'E': VISION_R2[EXPLORER], 'G': VISION_R2[ARCHER], 'B': VISION_R2[CAMP]},
            },
            'map': {
                'rows': rows,
                'ore': [[x, y, a] for (x, y), a in sorted(m.ore.items())],
                'traps': sorted([x, y] for x, y in m.traps),
                'bases': [[x, y] for x, y in m.bases],
                'base_ids': [b.id for b in self.bases],
            },
            'frames': self.frames,
        }


def resolve_bot(spec, bots_dir='bots'):
    """봇 지정: .py 파일, main.py 가 든 폴더, 또는 bots/ 안의 이름. (경로, 이름) 을 돌려준다."""
    repo_bots = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bots')
    cands = [spec, os.path.join(spec, 'main.py')]
    for d in (bots_dir, repo_bots):            # 지금 폴더의 bots/ 를 먼저, 없으면 저장소의 bots/
        cands += [os.path.join(d, spec, 'main.py'), os.path.join(d, spec + '.py')]
    for c in cands:
        if os.path.isfile(c):
            path = os.path.abspath(c)
            base = os.path.basename(path)
            name = os.path.basename(os.path.dirname(path)) if base == 'main.py' else os.path.splitext(base)[0]
            return path, name
    raise FileNotFoundError(f'봇을 찾을 수 없다: {spec} (bots/<이름>/main.py 또는 .py 파일 경로)')


def run_match(gmap, bot_paths, seed=0, names=None, time_limit_ms=None):
    sources, auto = [], []
    for p in bot_paths:
        path, name = resolve_bot(p)
        with open(path, encoding='utf-8') as f:
            sources.append(f.read())
        auto.append(name)
    return Game(gmap, sources, names or auto, seed, time_limit_ms).play()
