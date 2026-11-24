"""게임 엔진. 같은 봇 · 같은 맵 · 같은 시드면 같은 결과가 나온다."""
import os
import random
import time
import types

from . import api, guard
from .ops import meter, OpsExceeded
from .api import (DIRS, EXPLORER, ARCHER, CAMP, EMPTY, WALL, GOLD, PIT, CAMP_TILE,
                  MAX_ROUNDS, MEMORY_SIZE, MAX_UNITS, START_BANK, INCOME_EVERY, COST, HP,
                  VISION_R2, ATTACK_DAMAGE, CAMP_ATTACK, CARRY_MAX, REGROW_EVERY, cheb, Move, Mine, Attack, Spawn,
                  OPS_TURN, OPS_FIRST, TIME_SAFETY_MS, ALLOWED_IMPORTS, BLOCKED_BUILTINS,
                  Shoot, Push, _Frozen, AGENT_HP, AGENT_CARRY, WUMPUS_HP_A, WUMPUS_STRIKE_A, WUMPUS_WAKE_A, WUMPUS_HOARD_A, WUMPUS_HP_U, WUMPUS_ROAR, WUMPUS_ROAR_DMG, WUMPUS_REGEN, WUMPUS_HOARD_U, WUMPUS_RESPAWN, HP_UNIFIED, CARRY, MELEE_RANGE, BOW_RANGE, sight_cells, ARROW_RANGE, ARROWS_MAX, ARCHER_CARRY, DAGGER_DAMAGE, WUMPUS_HP, WUMPUS_HOARD, WUMPUS_CLEAR, RULES, mirror)

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


# ---------- 봇에게 주는 것: 내장 함수 · 모듈은 유닛마다 따로 만든 복사본이다 ----------
# (같이 쓰면 한 봇이 고친 것이 상대 봇 · 엔진 · 다음 판에 남는다)
_SAFE_BUILTINS = (
    'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray', 'bytes', 'callable', 'chr', 'classmethod', 'complex',
    'dict', 'divmod', 'enumerate', 'filter', 'float', 'format', 'frozenset', 'hasattr', 'hash', 'hex', 'id', 'int',
    'isinstance', 'issubclass', 'iter', 'len', 'list', 'map', 'max', 'min', 'next', 'object', 'oct', 'ord', 'pow',
    'print', 'property', 'range', 'repr', 'reversed', 'round', 'set', 'slice', 'sorted', 'staticmethod', 'str',
    'sum', 'super', 'tuple', 'zip', 'NotImplemented', 'Ellipsis', '__build_class__')
_NO_EXC = ('SystemExit', 'KeyboardInterrupt', 'GeneratorExit')


def _make_builtins():
    import builtins
    b = {k: getattr(builtins, k) for k in _SAFE_BUILTINS}
    for k, v in vars(builtins).items():             # 예외 클래스
        if isinstance(v, type) and issubclass(v, BaseException) and k not in _NO_EXC:
            b[k] = v
    return b


_BOT_BUILTINS = _make_builtins()
_BUILTIN_EXC = frozenset(v for v in _BOT_BUILTINS.values() if isinstance(v, type) and issubclass(v, BaseException))

_PICK = {       # 파이썬으로 짠 모듈은 줄 이름을 고른다 (속성 이름을 글로 받아 꺼내는 도구를 빼려고)
    'functools': ('reduce', 'partial', 'lru_cache', 'cache', 'cmp_to_key', 'total_ordering'),
    'collections': ('deque', 'defaultdict', 'OrderedDict', 'Counter', 'namedtuple', 'ChainMap'),
    'copy': ('copy', 'deepcopy'),
}
_DROP = {'operator': ('attrgetter', 'methodcaller'), 'random': ('SystemRandom',)}
_PLAIN = (int, float, str, bool, bytes, type(None))
_NO = object()


def _wrap(f):
    return lambda *a, **k: f(*a, **k)


def _share(v, modname):
    """모듈 속 값 하나를 봇에게 줄 모양으로 바꾼다. 줄 수 없으면 _NO."""
    if isinstance(v, types.FunctionType):           # 파이썬 함수: 유닛마다 새 껍데기 (함수에 속성을 달아 같이 쓰지 못하게)
        return _wrap(v)
    if isinstance(v, type):
        if isinstance(v, _Frozen) or v.__flags__ & (1 << 8):    # 고칠 수 없는 클래스는 그대로
            return v
        try:
            return type(v)(v.__name__, (v,), {'__module__': modname})   # 고칠 수 있는 클래스: 유닛마다 새 자식 클래스
        except TypeError:
            pass
        try:
            setattr(v, '_ww_probe', 1)
        except TypeError:
            return v
        delattr(v, '_ww_probe')
        return _NO
    if isinstance(v, (types.BuiltinFunctionType, types.MethodType)) or isinstance(v, _PLAIN):
        return v
    if isinstance(v, tuple) and all(isinstance(x, _PLAIN) for x in v):
        return v
    return _NO


def _make_importer():
    """유닛 하나가 쓸 import. 허용 모듈 (api.ALLOWED_IMPORTS) 의 복사본만 준다."""
    cache = {}

    def proxy(name):
        m = cache.get(name)
        if m is not None:
            return m
        m = cache[name] = types.ModuleType(name)
        if name == 'wumpus':
            m.api = proxy('wumpus.api')
            return m
        own = name == 'wumpus.api'
        real = api if own else __import__(name)
        keep, drop = _PICK.get(name), _DROP.get(name, ())
        for k, v in list(vars(real).items()):
            if k.startswith('_') or k in drop or (keep is not None and k not in keep):
                continue
            if own and isinstance(v, dict):         # DIRS · COST · HP ... 는 엔진도 쓰는 표다. 복사본을 준다
                v = dict(v)
            elif not (own and v is api.debug):
                v = _share(v, name)
            if v is not _NO:
                setattr(m, k, v)
        return m

    def bot_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level or name not in ALLOWED_IMPORTS:
            raise ImportError(f"봇에서는 '{name}' 모듈을 쓸 수 없다 (쓸 수 있는 것: {', '.join(ALLOWED_IMPORTS[1:])})")
        return proxy(name) if fromlist else proxy(name.split('.')[0])

    return bot_import


def _plain_repr(o, depth=0):
    """기본 값만 글로 바꾼다 (봇이 만든 객체의 __repr__ · __str__ 은 부르지 않는다)."""
    t = type(o)
    if t in (int, float, bool, type(None)):
        return repr(o)
    if t is str:
        return repr(o[:80])
    if t in (tuple, list) and depth < 2 and len(o) <= 8:
        inner = ', '.join(_plain_repr(x, depth + 1) for x in o)
        return f'({inner})' if t is tuple else f'[{inner}]'
    return '<...>'


def _err_text(e):
    """봇이 낸 예외를 기록용 글로. 봇 코드를 부르지 않는다."""
    t = type(e)
    name = type.__dict__['__name__'].__get__(t)
    if t not in _BUILTIN_EXC:
        return name
    args = BaseException.__dict__['args'].__get__(e)
    if type(args) is not tuple or not args:
        return name
    if len(args) == 1 and type(args[0]) is str:
        return f'{name}: {args[0]}'[:160]
    return f"{name}: {', '.join(_plain_repr(a) for a in args[:4])}"[:160]


def _clean_act(a):
    """봇이 돌려준 행동 하나를 엔진의 새 행동으로 옮긴다. 종류 · 값이 정확히 맞지 않으면 None."""
    t = type(a)
    try:
        if t is Move or t is Shoot or t is Push:
            d = a.d
            return t(d) if type(d) is str and d in DIRS else None
        if t is Mine:
            return Mine()
        if t is Attack:
            x, y = a.x, a.y
            return Attack(x, y) if type(x) is int and type(y) is int and abs(x) < 10000 and abs(y) < 10000 else None
        if t is Spawn:
            k, d = a.kind, a.d
            return Spawn(k, d) if type(k) is str and type(d) is str and k in COST and d in DIRS else None
    except AttributeError:                          # 값이 비어 있는 행동
        return None
    return None


def _debug_dump():
    """디버그 표시를 리플레이에 넣을 모양으로. 봇이 넣은 값은 종류를 확인하고 옮긴다."""
    d = api.debug
    out = {}
    try:
        def cell(c):
            return type(c) is list and len(c) == 2 and type(c[0]) is int and type(c[1]) is int and abs(c[0]) < 10000 and abs(c[1]) < 10000

        def text(v, n):
            return type(v) is str and len(v) <= n
        m, ln, tx = d.marks, d.lines, d.texts
        if type(m) is list:
            m = [[c[0], c[1], c[2]] for c in m[:api.Debug.MAX_MARKS] if type(c) is list and len(c) == 3 and cell(c[:2]) and text(c[2], 32)]
            if m:
                out['m'] = m
        if type(ln) is list:
            ln = [[q[0], [[c[0], c[1]] for c in q[1][:200] if cell(c)]] for q in ln[:8]
                  if type(q) is list and len(q) == 2 and text(q[0], 32) and type(q[1]) is list]
            if ln:
                out['l'] = ln
        if type(tx) is list:
            tx = [v for v in tx[:8] if text(v, 200)]
            if tx:
                out['t'] = tx
    except Exception:
        return {}
    return out


class Me(metaclass=_Frozen):
    """봇에게 주는 자기 정보 (복사본)."""

    def __init__(self, u, g):
        self.id, self.team, self.kind = u.id, u.team, u.kind
        self.x, self.y, self.hp, self.carry = u.x, u.y, u.hp, u.carry
        self.arrows = u.arrows
        self.round = g.round
        self.bank = g.bank[u.team]
        self.ops_limit = u.ops_first if u.ops_first else OPS_TURN   # 이 차례에 쓸 수 있는 연산


class UnitInfo(metaclass=_Frozen):
    __slots__ = ('id', 'team', 'kind', 'x', 'y', 'hp', 'carry', 'arrows')
    alive = True

    def __init__(self, u):
        self.id, self.team, self.kind = u.id, u.team, u.kind
        self.x, self.y, self.hp, self.carry = u.x, u.y, u.hp, u.carry
        self.arrows = u.arrows

    def __repr__(self):
        return f'UnitInfo(#{self.id} {self.kind} team={self.team} ({self.x},{self.y}) hp={self.hp})'


class View(metaclass=_Frozen):
    """유닛이 지금 보고 느끼는 것. 만들 때 보이는 칸의 값만 복사해 둔다 (게임 전체는 들고 있지 않다)."""

    def __init__(self, g, u):
        vis = g.vision(u)
        self._vis = vis
        self._tile = {c: g.public_tile(c[0], c[1]) for c in vis}
        self._gold = {c: g.ore.get(c, 0) for c in vis}
        self._arrows = {c: g.ground_arrows.get(c, 0) for c in vis}
        self._loot = {c: g.loot.get(c, 0) for c in vis}
        self._at = {c: UnitInfo(v) for c in vis for v in (g.at.get(c),) if v is not None and v.alive}
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
        return self._tile.get((x, y))

    def gold(self, x, y):
        if (x, y) not in self._vis:
            return None
        return self._gold.get((x, y), 0)

    def arrows_at(self, x, y):
        """보이는 칸에 떨어진 화살 수. 안 보이면 None."""
        if (x, y) not in self._vis:
            return None
        return self._arrows.get((x, y), 0)

    def loot(self, x, y):
        """보이는 칸에 떨어진 금 (쓰러진 유닛의 짐 · 웜퍼스 보물). 안 보이면 None."""
        if (x, y) not in self._vis:
            return None
        return self._loot.get((x, y), 0)

    def units(self):
        """보이는 유닛 목록 (야영지 포함, 자기 자신 포함)."""
        at = self._at
        out = []
        for c in self._vis:
            v = at.get(c)
            if v is not None and v.alive:
                out.append(UnitInfo(v))
        out.sort(key=lambda v: v.id)
        return out


class Game:
    def __init__(self, gmap, bot_sources, bot_names, seed=0, time_limit_ms=None, rules=None, ops_limit=True, turn_cb=None):
        self.turn_cb = turn_cb          # 봇 코드를 부르기 직전에 팀 번호를 알린다 (경기가 멈췄을 때 누구 차례였는지 알려고)
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
        self.time_limit_ms = TIME_SAFETY_MS if time_limit_ms is None else time_limit_ms   # 시간 안전망 (0 이면 끔)
        self.tstat = [[0.0, 0.0, 0, 0], [0.0, 0.0, 0, 0]]   # 팀마다 [합 ms, 최대 ms, 차례 수, 시간 초과 수]
        self.sources = bot_sources
        self.names = bot_names
        # 제출 코드 검사: 모든 봇이 거친다. 걸린 봇은 실격 (코드를 실행하지 않는다)
        self.rejected = [guard.check(src) for src in bot_sources]
        self.codes = [None if self.rejected[i] else compile(src, f'<bot {i}: {bot_names[i]}>', 'exec') for i, src in enumerate(bot_sources)]
        # 연산 한도: 유닛마다 차례당 OPS_TURN (첫 차례는 불러오기와 합쳐 OPS_FIRST). 남겨도 쌓이지 않는다
        self.ops_on = bool(ops_limit)
        self.ostat = [[0, 0, 0, 0], [0, 0, 0, 0]]   # 팀마다 [합, 최대 (첫 차례 빼고), 차례 수, 한도 초과 수]
        self.meter = meter()
        if self.ops_on:
            for c in self.codes:
                if c is not None:
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
        if self.codes[team] is None:               # 실격한 봇: 실행하지 않는다
            u.ops_first = 0
            return u
        b = dict(_BOT_BUILTINS)
        b['__import__'] = _make_importer()
        ns = {'__name__': f'bot_{team}_{u.id}', '__builtins__': b}
        if self.turn_cb:
            self.turn_cb(team)
        u.ops_first = OPS_FIRST                    # 첫 차례 몫: 불러오기에 쓰고 남은 만큼을 첫 turn 호출에 쓴다
        try:
            try:
                self._ops_run(team, lambda: exec(self.codes[team], ns), OPS_FIRST, first=True)
            finally:
                u.ops_first = max(OPS_TURN, OPS_FIRST - self.meter.count) if self.ops_on else OPS_FIRST
            if not callable(ns.get('turn')):
                raise AttributeError('turn 함수가 없다')
            u.ns = ns
        except KeyboardInterrupt:
            raise
        except BaseException as e:             # 봇 파일 자체가 깨졌으면 그 유닛은 아무것도 안 한다
            msg = '연산 한도 초과 (봇 파일 첫 실행)' if isinstance(e, OpsExceeded) else _err_text(e)
            self.events.append(['err', u.id, f'불러오기 실패: {msg}'[:160]])
        return u

    # ---------- 연산 한도 ----------
    def _ops_run(self, team, fn, limit=OPS_TURN, first=False):
        """봇 코드를 연산 한도 안에서 실행한다. 한도를 넘으면 OpsExceeded 를 던진다."""
        if not self.ops_on:
            return fn()
        self.meter.start(limit)
        try:
            r = fn()
        finally:
            n = self.meter.stop()
            st = self.ostat[team]
            st[0] += n; st[2] += 1
            if not first:
                st[1] = max(st[1], n)
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
            if self.turn_cb:
                self.turn_cb(u.team)
            t0 = time.perf_counter()
            try:
                first, u.ops_first = u.ops_first, 0
                act = self._ops_run(u.team, lambda: u.ns['turn'](me, view, self.memory[u.team]), first or OPS_TURN, first=bool(first))
            except OpsExceeded:
                act = None
                self.ostat[u.team][3] += 1
                self.events.append(['err', u.id, f'연산 한도 초과: 이번 차례 한도 {self.meter.limit}'])
            except KeyboardInterrupt:
                raise
            except BaseException as e:
                act = None
                self.events.append(['err', u.id, _err_text(e)])
            ms = (time.perf_counter() - t0) * 1000
            ts = self.tstat[u.team]
            ts[0] += ms; ts[1] = max(ts[1], ms); ts[2] += 1
            if self.time_limit_ms and ms > self.time_limit_ms:      # 시간을 넘긴 차례는 행동을 버린다
                act = None; ts[3] += 1
                self.events.append(['err', u.id, f'시간 초과: {ms:.1f} ms > {self.time_limit_ms} ms'])
            self._fix_memory(u.team)
        d = _debug_dump()
        if d:
            self.debug[u.id] = d
        # 봇이 돌려준 값은 종류가 정확히 맞을 때만 받는다 (봇이 만든 객체의 코드를 엔진이 부르지 않는다)
        if type(act) in (list, tuple):                  # (이동, 행동): 광부만 둘 다, 나머지는 첫 행동만
            acts = [a for a in act[:8] if a is not None]
            if self.rules['unified'] and u.kind == EXPLORER and not self.rules['agent']:
                mv = next((a for a in acts if type(a) is Move), None)
                ot = next((a for a in acts if type(a) is not Move), None)
                todo = [mv, ot]
            else:
                todo = acts[:1]
        else:
            todo = [act]
        for a in todo:
            a = _clean_act(a) if a is not None else None
            if a is not None and u.alive:
                self._apply(u, a)
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
            if type(v) is not int:                # 정수만 받는다 (다른 것은 0)
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
        if any(self.rejected):                          # 코드 검사에 걸린 봇은 경기 없이 진다
            bad = [t for t in (0, 1) if self.rejected[t]]
            self.over = True
            self.winner = -1 if len(bad) == 2 else 1 - bad[0]
            self.reason = '실격: 코드 검사 불합격 (' + ', '.join(str(self.names[t]) for t in bad) + ')'
            return self.replay()
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
                'rejected': [list(v) for v in self.rejected],
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


def run_match(gmap, bot_paths, seed=0, names=None, time_limit_ms=None, rules=None, ops_limit=True, turn_cb=None):
    sources, auto = [], []
    for p in bot_paths:
        path, name = resolve_bot(p)
        with open(path, encoding='utf-8') as f:
            sources.append(f.read())
        auto.append(name)
    return Game(gmap, sources, names or auto, seed, time_limit_ms, rules, ops_limit, turn_cb).play()
