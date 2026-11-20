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


# ---- 행동 ----
class Move:
    """한 칸 이동. d 는 'N','E','S','W'."""
    __slots__ = ('d',)

    def __init__(self, d):
        self.d = d

    def __repr__(self):
        return f'Move({self.d!r})'


class Mine:
    """서 있는 금 칸에서 금 1을 캔다 (탐험가만)."""
    __slots__ = ()

    def __repr__(self):
        return 'Mine()'


class Attack:
    """주변 8칸 (체비셰프 1) 의 적 유닛이나 적 야영지를 친다 (궁수만)."""
    __slots__ = ('x', 'y')

    def __init__(self, x, y):
        self.x, self.y = x, y

    def __repr__(self):
        return f'Attack({self.x}, {self.y})'


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
