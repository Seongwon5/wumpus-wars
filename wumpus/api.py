"""봇이 쓰는 API: 행동, 상수, 디버그 표시.

봇 파일은 `turn(me, view, memory)` 함수 하나를 가진다.
유닛 하나마다 봇 파일이 따로 실행되므로, 모듈 전역 변수는 그 유닛만의 기억이다.
팀이 함께 쓰는 정보는 `memory` (정수 64칸) 로만 나눈다.
"""

# ---- 방향 (상하좌우 4방향) ----
DIRS = {'N': (0, -1), 'E': (1, 0), 'S': (0, 1), 'W': (-1, 0)}

# ---- 유닛 종류 ----
EXPLORER, ARCHER, CAMP = 'explorer', 'archer', 'camp'

# ---- 칸 종류 (view.tile 의 반환값) ----
EMPTY, WALL, GOLD, PIT, CAMP_TILE = '.', '#', 'G', 'P', 'C'
# None 은 "지금 안 보이는 칸" 이다. 숨은 구덩이는 EMPTY 로 보인다.

# ---- 규칙 상수 ----
MAX_ROUNDS = 500
MEMORY_SIZE = 64
MAX_UNITS = 10          # 팀당 살아 있는 유닛 수 한도 (야영지 제외)
START_BANK = 20
INCOME_EVERY = 3        # 3라운드마다 금고 +1
COST = {EXPLORER: 10, ARCHER: 15}
HP = {EXPLORER: 6, ARCHER: 15, CAMP: 150}
VISION_R2 = {EXPLORER: 10, ARCHER: 8, CAMP: 10}   # 시야: 거리 제곱 한도
ATTACK_DAMAGE = 3
CAMP_ATTACK = 1         # 야영지가 자기 차례 끝에 옆 8칸의 적 하나를 저절로 치는 피해 (0 이면 없음)
CARRY_MAX = 5
REGROW_EVERY = 12        # 금맥 칸마다 이 라운드마다 금 1개가 다시 자란다 (처음 양까지, 다 캔 칸도)
SAFE_RADIUS = 2         # 두 야영지에서 체비셰프 거리 2 안에는 구덩이가 없다
# 구덩이는 벽 · 금 칸에도 없다. 구덩이 배치도 맵 대칭을 따른다.

# ---- 새 규칙 (시안, fun-rules) ----
ARROW_RANGE = 5         # 화살은 상하좌우 한 방향으로 이 칸 수까지 날아간다 (벽 · 유닛 · 웜퍼스에서 멈춘다)
ARROWS_MAX = 3          # 궁수가 들 수 있는 화살 수. 차례 끝에 야영지 옆 8칸에 있으면 다시 가득 찬다
                        # 바로 옆 (상하좌우) 의 적 야영지를 칠 때는 화살을 쓰지 않는다 (횃불)
ARCHER_CARRY = 2        # 궁수는 캐지 못하지만, 떨어진 금을 이만큼 주워 나를 수 있다
DAGGER_DAMAGE = 1       # 화살이 없는 궁수가 바로 옆 (상하좌우) 적을 단검으로 찌르는 피해
# 빗나간 화살은 멈춘 칸에 떨어진다 (맞힌 화살은 부러진다). 궁수가 그 칸에서 Mine() 하면 화살통 한도까지 줍는다.
# 궁수가 쓰러지면 남은 화살도 그 칸에 떨어진다 (구덩이에 떨어지면 함께 사라짐).
WUMPUS_HP = 9           # 웜퍼스 체력 (화살 3발)
WUMPUS_HOARD = 20       # 웜퍼스가 쓰러지면 그 칸에 떨어지는 보물 금
WUMPUS_CLEAR = 5        # 웜퍼스 굴은 두 야영지에서 체비셰프 거리 5 밖, 맵 가운데에 가장 가까운 칸 (대칭 짝)
RULES = {               # 규칙 스위치 (모두 켜면 시안 규칙, 모두 끄면 옛 규칙)
    'line_shot': True,  # 궁수 공격 = 직선 화살 (끄면 옆 8칸 공격)
    'arrows': True,     # 화살 수 제한과 야영지에서 채우기
    'push': True,       # 탐험가 밀치기
    'loot': True,       # 쓰러지면 짐을 떨어뜨리고, 누구나 주움 (구덩이에 떨어지면 금도 사라짐)
    'wumpus': True,     # 중립 몬스터 웜퍼스와 악취
}


# ---- 행동 ----
class Move:
    """한 칸 이동. d 는 'N','E','S','W'."""
    __slots__ = ('d',)

    def __init__(self, d):
        self.d = d

    def __repr__(self):
        return f'Move({self.d!r})'


class Mine:
    """서 있는 칸에 떨어진 것을 줍는다. 없으면 금맥에서 금 1을 캔다 (탐험가만).
    궁수는 떨어진 화살을 먼저 (화살통 한도까지), 그다음 떨어진 금을 ARCHER_CARRY 까지 줍는다."""
    __slots__ = ()

    def __repr__(self):
        return 'Mine()'


class Attack:
    """(x, y) 를 친다 (궁수만). 직선 화살 규칙에서는 (x, y) 가 같은 줄 · 같은 열에 있으면 그쪽으로 Shoot 한 것과 같다.
    옛 규칙에서는 주변 8칸 (체비셰프 1) 의 적 유닛이나 적 야영지를 친다."""
    __slots__ = ('x', 'y')

    def __init__(self, x, y):
        self.x, self.y = x, y

    def __repr__(self):
        return f'Attack({self.x}, {self.y})'


class Shoot:
    """d 방향 ('N','E','S','W') 으로 화살을 쏜다 (궁수만, 화살이 있어야 함).
    화살은 ARROW_RANGE 칸까지 날아가 처음 만난 유닛 · 야영지 · 웜퍼스에 맞는다. 우리 편이면 막혀서 피해가 없다. 벽에서 멈춘다.
    화살이 없으면: 바로 옆 적 유닛은 단검으로 찌르고 (DAGGER_DAMAGE), 바로 옆 적 야영지는 횃불로 태운다."""
    __slots__ = ('d',)

    def __init__(self, d):
        self.d = d

    def __repr__(self):
        return f'Shoot({self.d!r})'


class Push:
    """d 방향 옆 칸의 적 유닛을 한 칸 더 민다 (탐험가만). 피해는 없지만, 밀린 칸이 구덩이나 웜퍼스 굴이면 떨어져 죽는다.
    밀릴 칸이 벽 · 유닛 · 맵 밖이면 아무 일도 없다."""
    __slots__ = ('d',)

    def __init__(self, d):
        self.d = d

    def __repr__(self):
        return f'Push({self.d!r})'


class Spawn:
    """야영지가 옆 칸 (d 방향) 에 유닛을 만든다 (야영지만)."""
    __slots__ = ('kind', 'd')

    def __init__(self, kind, d):
        self.kind, self.d = kind, d

    def __repr__(self):
        return f'Spawn({self.kind!r}, {self.d!r})'


# ---- 디버그 표시 ("봇의 머릿속 보기") ----
class Debug:
    """리플레이 뷰어에 겹쳐 그릴 표시. 경기 결과에는 영향이 없다."""
    MAX_MARKS = 400

    def __init__(self):
        self.reset()

    def reset(self):
        self.marks = []
        self.lines = []
        self.texts = []

    def mark(self, x, y, color='green'):
        """칸 하나에 색을 칠한다. color: green red yellow blue purple white 또는 '#rrggbb'."""
        if len(self.marks) < self.MAX_MARKS:
            self.marks.append([int(x), int(y), str(color)])

    def path(self, cells, color='white'):
        """칸 목록을 선으로 잇는다 (예: A* 경로)."""
        if len(self.lines) < 8:
            self.lines.append([str(color), [[int(x), int(y)] for x, y in list(cells)[:200]]])

    def say(self, text):
        """한 줄 글을 남긴다."""
        if len(self.texts) < 8:
            self.texts.append(str(text)[:200])

    def dump(self):
        out = {}
        if self.marks:
            out['m'] = self.marks
        if self.lines:
            out['l'] = self.lines
        if self.texts:
            out['t'] = self.texts
        return out


debug = Debug()


# ---- 도우미 ----
def mirror(sym, x, y, w, h):
    """대칭 sym ('H' 좌우, 'V' 상하, 'R' 180도 회전) 으로 옮긴 칸."""
    if sym == 'H':
        return (w - 1 - x, y)
    if sym == 'V':
        return (x, h - 1 - y)
    return (w - 1 - x, h - 1 - y)


def cheb(ax, ay, bx, by):
    """체비셰프 거리 (8방향 칸 거리)."""
    return max(abs(ax - bx), abs(ay - by))


def direction_to(ax, ay, bx, by):
    """이웃한 두 칸 사이의 방향 글자."""
    for d, (dx, dy) in DIRS.items():
        if ax + dx == bx and ay + dy == by:
            return d
    return None
