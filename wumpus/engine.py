"""게임 엔진. 같은 봇 · 같은 맵 · 같은 시드면 같은 결과가 나온다."""
import os
import random
import time

from . import api
from .ops import meter, OpsExceeded
from .api import (DIRS, EXPLORER, ARCHER, CAMP, EMPTY, WALL, GOLD, PIT, CAMP_TILE,
                  MAX_ROUNDS, MEMORY_SIZE, MAX_UNITS, START_BANK, INCOME_EVERY, COST, HP,
                  VISION_R2, ATTACK_DAMAGE, CAMP_ATTACK, CARRY_MAX, REGROW_EVERY, cheb, Move, Mine, Attack, Spawn,
                  OPS_PER_ROUND, OPS_BANK_MAX, OPS_TURN_MAX, OPS_TURN_MIN,
                  Shoot, Push, AGENT_HP, AGENT_CARRY, WUMPUS_HP_A, WUMPUS_STRIKE_A, WUMPUS_WAKE_A, WUMPUS_HOARD_A, WUMPUS_HP_U, WUMPUS_ROAR, WUMPUS_ROAR_DMG, WUMPUS_REGEN, WUMPUS_HOARD_U, WUMPUS_RESPAWN, HP_UNIFIED, CARRY, MELEE_RANGE, BOW_RANGE, sight_cells, ARROW_RANGE, ARROWS_MAX, ARCHER_CARRY, DAGGER_DAMAGE, WUMPUS_HP, WUMPUS_HOARD, WUMPUS_CLEAR, RULES, mirror)

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
        self.arrows = ARROWS_MAX if kind == ARCHER else 0
        self.alive = True
        self.ns = None          # 이 유닛 전용 봇 이름공간
        self.bump = False       # 시안 3: 지난 이동이 막혔나
        self.bumped = False     # 이번 라운드에 막혔나 (기록용)
        self.prev_hp = None     # 지난 차례 끝 체력 (아픔 지각)


class Me:
    """봇에게 주는 자기 정보 (복사본)."""

    def __init__(self, u, g):
        self.id, self.team, self.kind = u.id, u.team, u.kind
        self.x, self.y, self.hp, self.carry = u.x, u.y, u.hp, u.carry
        self.arrows = u.arrows
        self.round = g.round
        self.bank = g.bank[u.team]
        self.ops_bank = g.ops_bank[u.team]          # 팀 연산 예산 (이 차례를 시작할 때)


class UnitInfo:
    __slots__ = ('id', 'team', 'kind', 'x', 'y', 'hp', 'carry', 'arrows')

    def __init__(self, u):
        self.id, self.team, self.kind = u.id, u.team, u.kind
        self.x, self.y, self.hp, self.carry = u.x, u.y, u.hp, u.carry
        self.arrows = u.arrows

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
        # 악취: 지금 선 칸의 상하좌우 이웃에 살아 있는 웜퍼스가 있으면 True (웜퍼스 자체는 보이지 않는다)
        self.stench = u.kind != CAMP and g.stench_at(u.x, u.y)
        # 비명: 지금까지 쓰러진 웜퍼스 수 (맵 어디서든 모두에게 들린다)
        self.screams = g.screams
        self.rules = dict(g.rules)      # 켜진 규칙 (봇이 규칙에 맞게 움직이도록)
        # 시안 3 지각: 반짝임 · 부딪힘 · 발소리 · 아픔. 두 야영지 위치는 모두가 안다
        self.glitter = u.kind != CAMP and (g.ore.get((u.x, u.y), 0) > 0 or g.loot.get((u.x, u.y), 0) > 0)
        self.bump = u.bump
        self.footsteps = g.footsteps_at(u) if u.kind != CAMP else 0
        self.hurt = max(0, (u.prev_hp if u.prev_hp is not None else u.hp) - u.hp)
        self.enemy_camp = g.bases[1 - u.team].x, g.bases[1 - u.team].y

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

    def arrows_at(self, x, y):
        """보이는 칸에 떨어진 화살 수. 안 보이면 None."""
        if (x, y) not in self._vis:
            return None
        return self._g.ground_arrows.get((x, y), 0)

    def loot(self, x, y):
        """보이는 칸에 떨어진 금 (쓰러진 유닛의 짐 · 웜퍼스 보물). 안 보이면 None."""
        if (x, y) not in self._vis:
            return None
        return self._g.loot.get((x, y), 0)

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
    def __init__(self, gmap, bot_sources, bot_names, seed=0, time_limit_ms=None, rules=None, ops_limit=True):
        self.rules = dict(RULES)
        if rules:
            self.rules.update(rules)
        self.rules.setdefault('agent', False)
        if self.rules['agent']:
            self.rules['unified'] = True
            self.rules['push'] = False
        self.rules.setdefault('unified', False)
        self.rules.setdefault('hidden_pits', False)
        if self.rules['unified']:
            self.rules['line_shot'] = self.rules['arrows'] = False
        self.HPT = dict(HP_UNIFIED, **{EXPLORER: AGENT_HP}) if self.rules['agent'] else HP_UNIFIED if self.rules['unified'] else HP
        self.WHP = WUMPUS_HP_A if self.rules['agent'] else WUMPUS_HP_U
        self.map = gmap
        self.w, self.h = gmap.w, gmap.h
        self.walls = set(gmap.walls)
        self.ore = dict(gmap.ore)
        self.ore_max = dict(gmap.ore)   # 금맥마다 처음 양 (다시 자랄 때 한도)
        self.traps = set(gmap.traps)
        self.revealed = set()
        self.loot = {}                  # 칸 -> 떨어진 금
        self.loot_changed = False
        self.ground_arrows = {}         # 칸 -> 떨어진 화살 수
        self.arrows_changed = False
        self.frames_started = False
        self.wumpus = {}                # 굴 칸 -> 남은 체력 (0 이면 쓰러짐)
        self.screams = 0
        if self.rules['wumpus']:
            for c in wumpus_cells(gmap):
                self.wumpus[c] = (WUMPUS_HP_A if self.rules['agent'] else WUMPUS_HP_U) if self.rules['unified'] else WUMPUS_HP
        self.whit = set()               # 이번 라운드에 맞은 굴
        self.wfoe = {}                  # 굴 -> 이번 라운드에 친 유닛 id (시안 3: 깨어나서 먼저 노림)
        self.wawake = {}                # 굴 -> 깨어 있는 마지막 라운드
        self.wdead = {}                 # 굴 -> 쓰러진 라운드
        self.seed = seed
        self.time_limit_ms = time_limit_ms
        self.tstat = [[0.0, 0.0, 0, 0], [0.0, 0.0, 0, 0]]   # 팀마다 [합 ms, 최대 ms, 차례 수, 시간 초과 수]
        self.sources = bot_sources
        self.names = bot_names
        self.codes = [compile(src, f'<bot {i}: {bot_names[i]}>', 'exec') for i, src in enumerate(bot_sources)]
        # 연산 한도: 팀마다 예산 (줄 수). 차례마다 min(OPS_TURN_MAX, 예산) 까지 (늘 OPS_TURN_MIN 은 허락), 쓴 만큼 뺀다
        self.ops_on = bool(ops_limit)
        self.ops_bank = [OPS_BANK_MAX, OPS_BANK_MAX]
        self.ostat = [[0, 0, 0, 0], [0, 0, 0, 0]]   # 팀마다 [합 줄, 최대 줄, 차례 수, 한도 초과 수]
        self.meter = meter()
        if self.ops_on:
            for c in self.codes:
                self.meter.watch(c)
            self.meter.watch_host(Me, View, UnitInfo, *[v for k, v in vars(api).items()
                                                        if not k.startswith('_') and (isinstance(v, type) or callable(v)) and getattr(v, '__module__', '') == api.__name__])
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
        if c in self.revealed and not self.rules['hidden_pits']:
            return PIT
        if self.ore.get(c, 0) > 0:
            return GOLD
        return EMPTY

    def footsteps_at(self, u):
        """상하좌우의 다른 모험가 수 (팀 구분 없음, 야영지 빼고)."""
        n = 0
        for dx, dy in DIRS.values():
            v = self.at.get((u.x + dx, u.y + dy))
            if v is not None and v.alive and v.kind != CAMP:
                n += 1
        return n

    def breeze_at(self, x, y):
        return any((x + dx, y + dy) in self.traps for dx, dy in DIRS.values())

    def stench_at(self, x, y):
        return any(self.wumpus.get((x + dx, y + dy), 0) > 0 for dx, dy in DIRS.values())

    def _drop(self, c, amt):
        if amt > 0 and self.rules['loot']:
            self.loot[c] = self.loot.get(c, 0) + amt
            self.loot_changed = True
            self.events.append(['drop', c[0], c[1], amt])

    def vision(self, u):
        if self.rules.get('agent'):
            if u.kind == CAMP:                  # 야영지는 상하좌우 옆 칸까지 본다 (생산할 자리)
                return {(u.x + dx, u.y + dy) for dx, dy in [(0, 0)] + list(DIRS.values()) if self.inb(u.x + dx, u.y + dy)}
            return {(u.x, u.y)}                 # 시안 3: 모험가는 자기 칸만
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
        u.hp = self.HPT[kind]
        self.next_id += 1
        self.at[(x, y)] = u
        ns = {'__name__': f'bot_{team}_{u.id}'}
        try:
            self._ops_run(team, lambda: exec(self.codes[team], ns))
            if not callable(ns.get('turn')):
                raise AttributeError('turn 함수가 없다')
            u.ns = ns
        except (Exception, OpsExceeded) as e:  # 봇 파일 자체가 깨졌으면 그 유닛은 아무것도 안 한다
            msg = f'연산 한도 초과 (봇 파일 첫 실행)' if isinstance(e, OpsExceeded) else f'{type(e).__name__}: {e}'
            self.events.append(['err', u.id, f'불러오기 실패: {msg}'[:160]])
        return u

    # ---------- 연산 한도 ----------
    def _ops_run(self, team, fn):
        """봇 코드를 연산 한도 안에서 실행한다. 한도를 넘으면 OpsExceeded 를 던진다 (쓴 줄은 예산에서 뺀다)."""
        if not self.ops_on:
            return fn()
        limit = max(OPS_TURN_MIN, min(OPS_TURN_MAX, self.ops_bank[team]))
        self.meter.start(limit)
        try:
            r = fn()
        finally:
            n = self.meter.stop()
            self.ops_bank[team] -= min(n, limit)
            st = self.ostat[team]
            st[0] += n; st[1] = max(st[1], n); st[2] += 1
        if n > limit:                       # 봇이 OpsExceeded 를 잡아 삼켰어도 넘긴 차례는 넘긴 것
            raise OpsExceeded()
        return r

    def _kill(self, u, cause):
        u.alive = False
        u.hp = 0
        if cause != 'trap':             # 구덩이에 떨어지면 짐도 함께 사라진다
            self._drop((u.x, u.y), u.carry)
            if u.kind == ARCHER and u.arrows > 0 and self.rules['arrows']:
                self._land((u.x, u.y), u.arrows)
        u.arrows = 0
        u.carry = 0
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
            u.bump = False                          # 지각은 한 번만 (다음 차례엔 새로)
            u.prev_hp = u.hp
            random.seed(self.seed * 1000003 + self.round * 1009 + u.id)
            t0 = time.perf_counter()
            try:
                act = self._ops_run(u.team, lambda: u.ns['turn'](me, view, self.memory[u.team]))
            except OpsExceeded:
                act = None
                self.ostat[u.team][3] += 1
                self.events.append(['err', u.id, f'연산 한도 초과: 이번 차례 {self.meter.limit} 줄 (팀 예산 {max(0, self.ops_bank[u.team])})'])
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
        if isinstance(act, (list, tuple)):              # (이동, 행동): 광부만 둘 다, 나머지는 첫 행동만
            acts = [a for a in act if a is not None]
            if self.rules['unified'] and u.kind == EXPLORER and not self.rules['agent']:
                mv = next((a for a in acts if isinstance(a, Move)), None)
                ot = next((a for a in acts if not isinstance(a, Move)), None)
                if mv is not None:
                    self._apply(u, mv)
                if ot is not None and u.alive:
                    self._apply(u, ot)
            elif acts:
                self._apply(u, acts[0])
        elif act is not None:
            self._apply(u, act)
        if u.alive and u.kind == ARCHER and self.rules['arrows'] and u.arrows < ARROWS_MAX:
            b = self.bases[u.team]
            if cheb(u.x, u.y, b.x, b.y) <= 1:
                u.arrows = ARROWS_MAX
                self.events.append(['refill', u.id, u.x, u.y])
        if u.alive and u.kind in (EXPLORER, ARCHER) and u.carry > 0:
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

    def _landed(self, u):
        """유닛이 새 칸에 들어섰다 (걸어서 또는 밀려서). 구덩이면 떨어지고, 웜퍼스 굴이면 잡아먹힌다."""
        n = (u.x, u.y)
        if n in self.traps:
            self.revealed.add(n)
            self.events.append(['trap', u.id, n[0], n[1]])
            self._kill(u, 'trap')
        elif self.wumpus.get(n, 0) > 0:
            self.events.append(['eaten', u.id, n[0], n[1]])
            self._kill(u, 'wumpus')
        elif self.rules['unified'] and u.kind in CARRY and self.loot.get(n, 0) > 0 and u.carry < CARRY[u.kind]:
            take = min(self.loot[n], CARRY[u.kind] - u.carry)     # 시안 2: 떨어진 금은 들어서는 순간 줍는다
            self.loot[n] -= take
            u.carry += take
            if self.loot[n] == 0:
                del self.loot[n]
            self.loot_changed = True
            self.events.append(['pick', u.id, n[0], n[1], take])

    def _land(self, c, n=1):
        self.ground_arrows[c] = self.ground_arrows.get(c, 0) + n
        self.arrows_changed = True

    def _shoot(self, u, d):
        if d not in DIRS:
            return
        dx, dy = DIRS[d]
        adj = self.at.get((u.x + dx, u.y + dy))
        torch = adj is not None and adj.kind == CAMP and adj.team != u.team   # 바로 옆 적 야영지: 화살 없이 횃불로 태운다
        if self.rules['arrows'] and not torch:
            if u.arrows <= 0:
                if adj is not None and adj.team != u.team:              # 화살이 없으면 바로 옆 적을 단검으로
                    adj.hp -= DAGGER_DAMAGE
                    self.events.append(['stab', u.id, u.x, u.y, adj.x, adj.y, adj.id])
                    if adj.hp <= 0:
                        self._kill(adj, 'atk')
                return
            u.arrows -= 1
        x, y = u.x, u.y
        hit = None
        for _ in range(ARROW_RANGE):
            n = (x + dx, y + dy)
            if not self.inb(*n) or n in self.walls:
                break
            x, y = n
            if self.wumpus.get(n, 0) > 0:
                hit = 'w'
                break
            if n in self.at:
                hit = 'u'
                break
        if self.rules['arrows'] and not torch and (hit is None or (hit == 'u' and self.at[(x, y)].team == u.team)):
            self._land((x, y))                  # 빗나간 화살만 멈춘 칸에 떨어진다 (맞힌 화살은 부러진다)
        if hit == 'w':
            c = (x, y)
            self.wumpus[c] = max(0, self.wumpus[c] - ATTACK_DAMAGE)
            self.events.append(['atk', u.id, u.x, u.y, x, y, -1])     # -1 = 웜퍼스
            if self.wumpus[c] == 0:
                self.screams += 1
                self.events.append(['scream', u.id, x, y, u.team])
                self._drop(c, WUMPUS_HOARD)
            return
        if hit == 'u':
            t = self.at[(x, y)]
            if t.team != u.team:
                t.hp -= ATTACK_DAMAGE
                self.events.append(['atk', u.id, u.x, u.y, x, y, t.id])
                if t.hp <= 0:
                    self._kill(t, 'atk')
                return
        self.events.append(['atk', u.id, u.x, u.y, x, y, 0 if hit is None else -2])   # 0 빗나감, -2 우리 편에 막힘

    def _wumpus_phase(self, r):
        """라운드 끝: 살아 있는 웜퍼스는 둘레에 포효 (피해), 안 맞았으면 회복. 쓰러진 웜퍼스는 때가 되면 다시 나타난다."""
        for c in sorted(self.wumpus):
            hp = self.wumpus[c]
            agent = self.rules['agent']
            if hp > 0:
                awake = not agent or self.wawake.get(c, -1) >= r     # 시안 3: 공격받아 깨어 있을 때만 친다
                near = [v for v in self.units if v.alive and v.kind != CAMP and awake and abs(v.x - c[0]) + abs(v.y - c[1]) <= (1 if agent else WUMPUS_ROAR)]
                foes = self.wfoe.get(c, set())
                if agent:
                    near.sort(key=lambda v: (v.id not in foes, v.hp, v.id))   # 이번 라운드에 친 유닛을 먼저
                hits = near[:1] if agent else sorted(near, key=lambda v: (abs(v.x - c[0]) + abs(v.y - c[1]), v.hp, v.id))[:1]   # 한 명에게만
                if hits:
                    self.events.append(['roar', c[0], c[1], [v.id for v in hits]])
                for v in hits:
                    v.hp -= WUMPUS_STRIKE_A if agent else WUMPUS_ROAR_DMG
                    if v.hp <= 0:
                        self._kill(v, 'roar')
                if c not in self.whit and hp < self.WHP:
                    self.wumpus[c] = min(self.WHP, hp + WUMPUS_REGEN)
            else:
                d0 = self.wdead.setdefault(c, r)
                if r - d0 >= WUMPUS_RESPAWN and c not in self.at:
                    self.wumpus[c] = self.WHP
                    self.wdead.pop(c, None)
                    self.events.append(['wrespawn', c[0], c[1]])
        self.whit = set()
        self.wfoe = {}

    def _hit(self, u, tx, ty):
        """시안 2 공격: 광부는 바로 옆, 궁수는 맨해튼 3 안 (벽이 가리면 안 됨). 야영지는 바로 옆에서만."""
        d = abs(tx - u.x) + abs(ty - u.y)
        if d > (BOW_RANGE if u.kind == ARCHER else MELEE_RANGE):
            return
        if any(c in self.walls for c in sight_cells(u.x, u.y, tx, ty)):
            return
        c = (tx, ty)
        t = self.at.get(c) if d else None
        if d and t is not None and t.team != u.team and not (t.kind == CAMP and d > 1):
            t.hp -= ATTACK_DAMAGE
            self.events.append(['atk', u.id, u.x, u.y, tx, ty, t.id])
            if t.hp <= 0:
                self._kill(t, 'atk')
            return
        if self.ore.get(c, 0) > 0 and (d == 0 or not self.rules['agent']):   # 금맥 공격 = 캐기 (시안 3: 서 있는 칸만)
            if u.carry < CARRY[u.kind]:
                self.ore[c] -= 1
                u.carry += 1
                self.ore_changed.add(c)
                self.events.append(['mine', u.id, u.x, u.y, tx, ty])
                if self.ore[c] == 0:
                    del self.ore[c]
            return
        if d and self.wumpus.get(c, 0) > 0:
            self.whit.add(c)
            self.wfoe.setdefault(c, set()).add(u.id)
            self.wawake[c] = self.round + WUMPUS_WAKE_A          # 깨어난다
            self.wumpus[c] = max(0, self.wumpus[c] - ATTACK_DAMAGE)
            self.events.append(['atk', u.id, u.x, u.y, tx, ty, -1])
            if self.wumpus[c] == 0:
                self.screams += 1
                self.events.append(['scream', u.id, tx, ty, u.team])
                self._drop(c, WUMPUS_HOARD_A if self.rules['agent'] else WUMPUS_HOARD_U)
            return
        t = self.at.get(c)
        if t is None or t.team == u.team or (t.kind == CAMP and d > 1):
            return
        t.hp -= ATTACK_DAMAGE
        self.events.append(['atk', u.id, u.x, u.y, tx, ty, t.id])
        if t.hp <= 0:
            self._kill(t, 'atk')

    def _push(self, u, d):
        if d not in DIRS:
            return
        dx, dy = DIRS[d]
        c = (u.x + dx, u.y + dy)
        t = self.at.get(c)
        if t is None or t.team == u.team or t.kind == CAMP:
            return
        n = (c[0] + dx, c[1] + dy)
        if not self.inb(*n) or n in self.walls or n in self.at:
            self.events.append(['push', u.id, u.x, u.y, t.id, c[0], c[1], c[0], c[1]])   # 막혀서 그대로
            return
        del self.at[c]
        t.x, t.y = n
        self.at[n] = t
        self.events.append(['push', u.id, u.x, u.y, t.id, c[0], c[1], n[0], n[1]])
        self._landed(t)

    def _apply(self, u, act):
        if isinstance(act, Move) and u.kind != CAMP:
            if act.d not in DIRS:
                return
            dx, dy = DIRS[act.d]
            n = (u.x + dx, u.y + dy)
            if not self.inb(*n) or n in self.walls or n in self.at:
                u.bump = u.bumped = True                # 부딪힘 (벽 · 맵 끝 · 다른 모험가 · 야영지)
                self.events.append(['bump', u.id, u.x, u.y, n[0], n[1]])
                return
            del self.at[(u.x, u.y)]
            u.x, u.y = n
            self.at[n] = u
            self._landed(u)
        elif isinstance(act, Mine) and u.kind in (EXPLORER, ARCHER) and self.rules['unified']:
            self._hit(u, u.x, u.y)              # 시안 2: Mine() = 서 있는 칸의 금맥 공격
        elif isinstance(act, Mine) and u.kind in (EXPLORER, ARCHER):
            c = (u.x, u.y)
            cap = CARRY[u.kind] if self.rules['unified'] else CARRY_MAX if u.kind == EXPLORER else (ARCHER_CARRY if self.rules['loot'] else 0)
            if u.kind == ARCHER and self.ground_arrows.get(c, 0) > 0 and u.arrows < ARROWS_MAX:
                take = min(self.ground_arrows[c], ARROWS_MAX - u.arrows)
                self.ground_arrows[c] -= take
                u.arrows += take
                if self.ground_arrows[c] == 0:
                    del self.ground_arrows[c]
                self.arrows_changed = True
                self.events.append(['parrow', u.id, u.x, u.y, take])
            elif self.loot.get(c, 0) > 0 and u.carry < cap:
                take = min(self.loot[c], cap - u.carry)
                self.loot[c] -= take
                u.carry += take
                if self.loot[c] == 0:
                    del self.loot[c]
                self.loot_changed = True
                self.events.append(['pick', u.id, u.x, u.y, take])
            elif (u.kind == EXPLORER or self.rules['unified']) and self.ore.get(c, 0) > 0 and u.carry < cap:
                self.ore[c] -= 1
                u.carry += 1
                self.ore_changed.add(c)
                self.events.append(['mine', u.id, u.x, u.y])
                if self.ore[c] == 0:
                    del self.ore[c]
        elif isinstance(act, Shoot) and u.kind == ARCHER and self.rules['line_shot']:
            self._shoot(u, act.d)
        elif isinstance(act, Push) and u.kind == EXPLORER and self.rules['push']:
            self._push(u, act.d)
        elif isinstance(act, Attack) and u.kind in (EXPLORER, ARCHER) and self.rules['unified']:
            try:
                tx, ty = int(act.x), int(act.y)
            except Exception:
                return
            self._hit(u, tx, ty)
        elif isinstance(act, Attack) and u.kind == ARCHER:
            try:
                tx, ty = int(act.x), int(act.y)
            except Exception:
                return
            if self.rules['line_shot']:         # 같은 줄 · 같은 열이면 그쪽으로 쏜 것과 같다
                if (tx, ty) == (u.x, u.y) or (tx != u.x and ty != u.y):
                    return
                d = ('E' if tx > u.x else 'W') if ty == u.y else ('S' if ty > u.y else 'N')
                self._shoot(u, d)
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
            if act.kind not in COST or act.d not in DIRS or (self.rules['agent'] and act.kind != EXPLORER):
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
                              1 if self.breeze_at(u.x, u.y) else 0,
                              u.arrows if self.rules['arrows'] and u.kind == ARCHER else -1,
                              1 if u.kind != CAMP and self.stench_at(u.x, u.y) else 0,
                              1 if u.kind != CAMP and (self.ore.get((u.x, u.y), 0) > 0 or self.loot.get((u.x, u.y), 0) > 0) else 0,
                              1 if u.bumped else 0,
                              self.footsteps_at(u) if u.kind != CAMP else 0])
                u.bumped = False
        fr = {
            'u': units,
            'o': [[x, y, self.ore.get((x, y), 0)] for (x, y) in sorted(self.ore_changed)],
            'bh': [max(0, b.hp) for b in self.bases],
            'bk': list(self.bank),
            'sc': list(self.score),
            'e': self.events,
            'v': [self._vis_hex(0), self._vis_hex(1)],
        }
        if self.loot_changed or not self.frames_started:
            fr['l'] = [[x, y, a] for (x, y), a in sorted(self.loot.items())]
        if self.arrows_changed or not self.frames_started:
            fr['ar'] = [[x, y, a] for (x, y), a in sorted(self.ground_arrows.items())]
        if self.wumpus:
            fr['w'] = [self.wumpus[c] for c in sorted(self.wumpus)]
        if self.debug:
            fr['d'] = {str(k): v for k, v in self.debug.items()}
        self.events, self.debug, self.ore_changed, self.loot_changed, self.arrows_changed = [], {}, set(), False, False
        self.frames_started = True
        return fr

    # ---------- 경기 ----------
    def play(self):
        for r in range(1, MAX_ROUNDS + 1):
            self.round = r
            if self.ops_on:
                for t in (0, 1):
                    self.ops_bank[t] = min(OPS_BANK_MAX, max(0, self.ops_bank[t]) + OPS_PER_ROUND)
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
            if self.rules['unified'] and self.wumpus and not self.over:
                self._wumpus_phase(r)
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
                'ops': [{'avg': round(o[0] / max(1, o[2])), 'max': o[1], 'turns': o[2], 'over': o[3]} for o in self.ostat] if self.ops_on else None,
            },
            'const': {
                'hp': {'E': self.HPT[EXPLORER], 'G': self.HPT[ARCHER], 'B': self.HPT[CAMP]},
                'bow_range': BOW_RANGE, 'regrow': REGROW_EVERY, 'carry': {'E': CARRY[EXPLORER], 'G': CARRY[ARCHER]},
                'carry': CARRY_MAX, 'max_rounds': MAX_ROUNDS,
                'cost': {'E': COST[EXPLORER], 'G': COST[ARCHER]},
                'vision': {'E': VISION_R2[EXPLORER], 'G': VISION_R2[ARCHER], 'B': VISION_R2[CAMP]},
                'arrows': ARROWS_MAX if self.rules['arrows'] else 0, 'arrow_range': ARROW_RANGE,
                'wumpus_hp': self.WHP if self.rules['unified'] else WUMPUS_HP, 'agent_hp': AGENT_HP, 'wumpus_respawn': WUMPUS_RESPAWN, 'wumpus_roar': WUMPUS_ROAR, 'wumpus_roar_dmg': WUMPUS_ROAR_DMG, 'archer_carry': ARCHER_CARRY, 'dagger': DAGGER_DAMAGE,
                'rules': dict(self.rules),
            },
            'map': {
                'rows': rows,
                'ore': [[x, y, a] for (x, y), a in sorted(m.ore.items())],
                'traps': sorted([x, y] for x, y in m.traps),
                'bases': [[x, y] for x, y in m.bases],
                'base_ids': [b.id for b in self.bases],
                'wumpus': [list(c) for c in sorted(self.wumpus)],
            },
            'frames': self.frames,
        }


def wumpus_cells(gmap):
    """웜퍼스 굴: 벽 · 구덩이 · 금맥이 아니고 두 야영지에서 체비셰프 WUMPUS_CLEAR 밖인 칸 가운데
    맵 가운데에 가장 가까운 칸과 그 대칭 짝 (가운데 칸이 자기 짝이면 하나). 맵 파일에 'wumpus' 가 있으면 그것을 쓴다."""
    if getattr(gmap, 'wumpus', None):
        return [tuple(c) for c in gmap.wumpus]
    W, H = gmap.w, gmap.h
    mx, my = (W - 1) / 2, (H - 1) / 2

    def ok(c):
        return (c not in gmap.walls and c not in gmap.traps and c not in gmap.ore
                and all(cheb(c[0], c[1], bx, by) > WUMPUS_CLEAR for bx, by in gmap.bases)
                and not any((c[0] + dx, c[1] + dy) in gmap.traps for dx, dy in DIRS.values()))

    best = None
    for y in range(H):
        for x in range(W):
            c = (x, y)
            m = mirror(gmap.sym, x, y, W, H)
            if not ok(c) or not ok(m) or (c != m and cheb(c[0], c[1], m[0], m[1]) < 4):
                continue                        # 짝 굴은 서로 4칸 이상 떨어진다 (악취가 섞이지 않게)
            k = ((x - mx) ** 2 + (y - my) ** 2, y, x)
            if best is None or k < best[0]:
                best = (k, c)
    if best is None:
        return []
    c = best[1]
    return sorted({c, mirror(gmap.sym, c[0], c[1], W, H)})


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


def run_match(gmap, bot_paths, seed=0, names=None, time_limit_ms=None, rules=None, ops_limit=True):
    sources, auto = [], []
    for p in bot_paths:
        path, name = resolve_bot(p)
        with open(path, encoding='utf-8') as f:
            sources.append(f.read())
        auto.append(name)
    return Game(gmap, sources, names or auto, seed, time_limit_ms, rules, ops_limit).play()
