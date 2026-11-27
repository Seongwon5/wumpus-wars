"""쉬운 규칙 설명서 (docs/EASY.md) 의 2D 설명 GIF 네 개를 만든다.

    python tools/easy_gifs.py        → docs/images/easy/*.gif

게임 엔진과 상관없이, 규칙을 보여 주려고 손으로 짠 장면이다.
"""
import copy
import math
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), '..', 'docs', 'images', 'easy')
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
FONT_B = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
KR = 1  # ttc 안의 한국어 글꼴 번호


def font(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, size, index=KR)


W = 680                 # 그림 너비
HUD_H, CAP_H = 44, 78   # 위 · 아래 띠 높이
PAPER = (246, 241, 232)
FLOOR = (232, 220, 196)
FLOOR_LINE = (210, 196, 170)
FOG = (52, 54, 70)
FOG_LINE = (64, 66, 84)
WALL = (110, 100, 92)
INK = (40, 36, 34)
TEAM = [(214, 72, 66), (54, 118, 214)]
TEAM_LIGHT = [(246, 205, 200), (200, 220, 248)]
GOLD = (242, 190, 40)
GREEN = (70, 160, 80)
ORANGE = (236, 140, 30)
RED = (210, 50, 50)
BUBBLE = {'바람': (120, 190, 240), '악취': (120, 190, 90), '반짝임': (250, 210, 70),
          '열기': (250, 150, 80), '부딪힘': (190, 190, 190), '비명!': (240, 110, 110),
          '아픔': (240, 110, 110), '열기 없음': (215, 215, 215), '아무 느낌 없음': (225, 225, 225)}


class Scene:
    """한 장면의 상태. snap() 할 때마다 그림 한 장을 찍는다."""

    def __init__(self, gw, gh, cell, title):
        self.gw, self.gh, self.c, self.title = gw, gh, cell, title
        self.ox = (W - gw * cell) // 2
        self.oy = HUD_H + 10
        self.H = self.oy + gh * cell + 10 + CAP_H
        self.tiles = {}        # (x, y) -> 'wall' 'pit' 'wumpus' 'deadw' 'gold' 'camp0' 'camp1'
        self.gold_n = {}
        self.fog = False       # True 면 known 밖은 어둠
        self.known = set()
        self.marks = {}        # (x, y) -> 'safe' 'q' 'pit' 'wump' 'hot'
        self.ghosts = {}       # (x, y) -> (글, 지워졌나)
        self.units = []        # dict(team, x, y, carry, hp, arrow, show_hp, alive)
        self.bubbles = []      # (unit 번호, 글)
        self.hud = []          # [(글, 색)]
        self.caption = ''
        self.lines = []        # 화살 · 대칭선 등: ('arrow', (x0,y0), (x1,y1)) ('mirror_v', x) ('link', a, b)
        self.frames, self.durs = [], []
        self.print_at = None   # 인쇄용 PNG 로 남길 장 번호 (없으면 마지막 장)

    # ---------- 그리기 ----------
    def px(self, x, y):
        return self.ox + x * self.c, self.oy + y * self.c

    def center(self, x, y):
        a, b = self.px(x, y)
        return a + self.c / 2, b + self.c / 2

    def draw(self):
        im = Image.new('RGB', (W, self.H), PAPER)
        d = ImageDraw.Draw(im, 'RGBA')
        c = self.c
        # 위 띠
        d.rectangle([0, 0, W, HUD_H], fill=(58, 50, 44))
        d.text((16, HUD_H / 2), self.title, font=font(19, True), fill=(250, 236, 200), anchor='lm')
        x = W - 14
        for text, col in reversed(self.hud):
            wdt = d.textlength(text, font=font(16, True))
            d.rounded_rectangle([x - wdt - 16, 9, x, HUD_H - 9], 8, fill=col)
            d.text((x - wdt / 2 - 8, HUD_H / 2), text, font=font(16, True), fill=INK, anchor='mm')
            x -= wdt + 24
        # 칸
        for gy in range(self.gh):
            for gx in range(self.gw):
                a, b = self.px(gx, gy)
                r = [a, b, a + c, b + c]
                t = self.tiles.get((gx, gy))
                hidden = self.fog and (gx, gy) not in self.known
                if hidden:
                    d.rectangle(r, fill=FOG, outline=FOG_LINE)
                    continue
                if t == 'wall':
                    d.rectangle(r, fill=WALL, outline=(90, 82, 76))
                    for k in range(1, 3):
                        yy = b + k * c / 3
                        d.line([a, yy, a + c, yy], fill=(92, 84, 78), width=2)
                    d.line([a + c / 2, b, a + c / 2, b + c / 3], fill=(92, 84, 78), width=2)
                    d.line([a + c / 4, b + c / 3, a + c / 4, b + 2 * c / 3], fill=(92, 84, 78), width=2)
                    d.line([a + 3 * c / 4, b + 2 * c / 3, a + 3 * c / 4, b + c], fill=(92, 84, 78), width=2)
                    continue
                fl = FLOOR
                if t in ('camp0', 'camp1'):
                    fl = TEAM_LIGHT[int(t[-1])]
                d.rectangle(r, fill=fl, outline=FLOOR_LINE)
                if t == 'pit':
                    d.ellipse([a + c * .14, b + c * .22, a + c * .86, b + c * .82], fill=(20, 18, 18), outline=(80, 70, 60), width=3)
                elif t == 'wumpus':
                    self._wumpus(d, a, b)
                elif t == 'deadw':
                    self._wumpus(d, a, b, dead=True)
                elif t == 'gold':
                    self._gold(d, a, b)
                elif t in ('camp0', 'camp1'):
                    self._camp(d, a, b, TEAM[int(t[-1])])
        # 표시
        for (gx, gy), m in self.marks.items():
            a, b = self.px(gx, gy)
            if m == 'safe':
                d.rectangle([a + 2, b + 2, a + c - 2, b + c - 2], fill=(90, 190, 100, 90), outline=GREEN, width=3)
                d.line([a + c * .3, b + c * .52, a + c * .45, b + c * .68, a + c * .72, b + c * .36], fill=GREEN, width=5)
            elif m == 'q':
                d.rectangle([a + 2, b + 2, a + c - 2, b + c - 2], fill=(250, 170, 60, 110), outline=ORANGE, width=3)
                d.text((a + c / 2, b + c / 2), '?', font=font(int(c * .5), True), fill=(150, 70, 0), anchor='mm')
            elif m in ('pit', 'wump'):
                d.rectangle([a + 2, b + 2, a + c - 2, b + c - 2], fill=(230, 60, 60, 120), outline=RED, width=4)
                d.text((a + c / 2, b + c / 2), '구덩이' if m == 'pit' else '굴', font=font(int(c * .24), True), fill=(255, 255, 255), anchor='mm',
                       stroke_width=2, stroke_fill=(150, 20, 20))
            elif m == 'hot':
                d.rectangle([a + 3, b + 3, a + c - 3, b + c - 3], outline=ORANGE, width=4)
        # 적 야영지 후보 (유령)
        for (gx, gy), (label, out) in self.ghosts.items():
            a, b = self.px(gx, gy)
            col = (150, 150, 150) if out else TEAM[1]
            self._dashed_tent(d, a, b, col)
            d.text((a + c / 2, b + c + 2), label, font=font(14, True), fill=(250, 250, 250) if self.fog else INK, anchor='mt',
                   stroke_width=3, stroke_fill=FOG if self.fog else PAPER)
            if out:
                d.line([a + 6, b + 6, a + c - 6, b + c - 6], fill=RED, width=5)
                d.line([a + c - 6, b + 6, a + 6, b + c - 6], fill=RED, width=5)
        # 선
        for ln in self.lines:
            if ln[0] == 'mirror_v':
                xx = self.ox + ln[1] * c
                for yy in range(self.oy, self.oy + self.gh * c, 14):
                    d.line([xx, yy, xx, yy + 7], fill=(255, 220, 120), width=3)
            elif ln[0] == 'mirror_h':
                yy = self.oy + ln[1] * c
                for xx in range(self.ox, self.ox + self.gw * c, 14):
                    d.line([xx, yy, xx + 7, yy], fill=(255, 220, 120), width=3)
            elif ln[0] == 'link':
                p, q = self.center(*ln[1]), self.center(*ln[2])
                d.line([p, q], fill=(255, 220, 120), width=4)
                for pt in (p, q):
                    d.ellipse([pt[0] - 6, pt[1] - 6, pt[0] + 6, pt[1] + 6], fill=(255, 220, 120))
            elif ln[0] == 'arrow':
                p = self.center(*ln[1])
                q = self.center(*ln[2])
                d.line([p, q], fill=(90, 60, 30), width=4)
                ang = math.atan2(q[1] - p[1], q[0] - p[0])
                for s in (2.6, -2.6):
                    d.line([q, (q[0] + 14 * math.cos(ang + s), q[1] + 14 * math.sin(ang + s))], fill=(90, 60, 30), width=4)
        # 모험가
        for u in self.units:
            if u.get('alive', True):
                self._unit(d, u)
        for ui, text in self.bubbles:
            self._bubble(d, self.units[ui], text)
        # 아래 띠 (설명)
        top = self.H - CAP_H
        d.rectangle([0, top, W, self.H], fill=(255, 252, 245))
        d.line([0, top, W, top], fill=(220, 208, 186), width=2)
        rows = self.caption.split('\n')
        f = font(19, True)
        f2 = font(17)
        yy = top + CAP_H / 2 - (len(rows) - 1) * 13
        for i, row in enumerate(rows):
            d.text((W / 2, yy + i * 26), row, font=f if i == 0 else f2, fill=INK if i == 0 else (90, 80, 70), anchor='mm')
        return im

    def _camp(self, d, a, b, col):
        c = self.c
        d.polygon([(a + c * .5, b + c * .14), (a + c * .88, b + c * .84), (a + c * .12, b + c * .84)], fill=col, outline=INK)
        d.polygon([(a + c * .5, b + c * .42), (a + c * .64, b + c * .84), (a + c * .36, b + c * .84)], fill=(60, 40, 30))
        d.line([a + c * .5, b + c * .14, a + c * .5, b + c * .02], fill=INK, width=2)
        d.polygon([(a + c * .5, b + c * .02), (a + c * .7, b + c * .07), (a + c * .5, b + c * .12)], fill=col)

    def _dashed_tent(self, d, a, b, col):
        c = self.c
        pts = [(a + c * .5, b + c * .14), (a + c * .88, b + c * .84), (a + c * .12, b + c * .84), (a + c * .5, b + c * .14)]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = 6
            for k in range(n):
                if k % 2 == 0:
                    d.line([x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n,
                            x0 + (x1 - x0) * (k + 1) / n, y0 + (y1 - y0) * (k + 1) / n], fill=col, width=4)

    def _gold(self, d, a, b):
        c = self.c
        for (cx, cy, s) in ((.38, .58, .2), (.62, .62, .17), (.5, .4, .16)):
            x, y, r = a + c * cx, b + c * cy, c * s
            d.polygon([(x - r, y), (x - r * .4, y - r * .8), (x + r * .6, y - r * .7), (x + r, y + r * .1),
                       (x + r * .3, y + r * .8), (x - r * .6, y + r * .6)], fill=GOLD, outline=(170, 120, 10))
        d.line([a + c * .45, b + c * .3, a + c * .5, b + c * .36], fill=(255, 255, 220), width=2)

    def _wumpus(self, d, a, b, dead=False):
        c = self.c
        body = (150, 150, 150) if dead else (86, 150, 70)
        d.rounded_rectangle([a + c * .16, b + c * .2, a + c * .84, b + c * .88], int(c * .25), fill=body, outline=INK, width=2)
        if dead:
            for ex in (.36, .64):
                x, y = a + c * ex, b + c * .45
                d.line([x - 6, y - 6, x + 6, y + 6], fill=INK, width=3)
                d.line([x + 6, y - 6, x - 6, y + 6], fill=INK, width=3)
        else:
            for ex in (.36, .64):
                x, y = a + c * ex, b + c * .45
                d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(255, 255, 255))
                d.ellipse([x - 3, y - 2, x + 3, y + 4], fill=INK)
            d.rectangle([a + c * .34, b + c * .66, a + c * .66, b + c * .74], fill=(40, 60, 30))

    def _unit(self, d, u):
        c = self.c
        cx, cy = self.center(u['x'], u['y'])
        r = c * .3
        col = TEAM[u['team']]
        if u.get('arrow'):
            d.line([cx + r * .2, cy - r * 1.25, cx + r * 1.1, cy + r * .2], fill=(120, 80, 40), width=4)
            d.polygon([(cx + r * .2, cy - r * 1.25), (cx + r * .55, cy - r * 1.05), (cx + r * .3, cy - r * .85)], fill=(80, 80, 80))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=INK, width=3)
        d.ellipse([cx - r * .38 - 3, cy - r * .2 - 3, cx - r * .38 + 3, cy - r * .2 + 3], fill=(255, 255, 255))
        d.ellipse([cx + r * .38 - 3, cy - r * .2 - 3, cx + r * .38 + 3, cy - r * .2 + 3], fill=(255, 255, 255))
        if u.get('carry'):
            t = str(u['carry'])
            bx, by = cx + r * .9, cy + r * .7
            w2 = max(11, d.textlength(t, font=font(14, True)) / 2 + 6)
            d.rounded_rectangle([bx - w2, by - 11, bx + w2, by + 11], 10, fill=GOLD, outline=(150, 100, 0), width=2)
            d.text((bx, by), t, font=font(14, True), fill=INK, anchor='mm')
        if u.get('show_hp'):
            hw = c * .8
            x0, y0 = cx - hw / 2, cy + r + 6
            d.rectangle([x0, y0, x0 + hw, y0 + 7], fill=(60, 50, 50))
            d.rectangle([x0, y0, x0 + hw * max(0, u['hp']) / 10, y0 + 7], fill=(90, 200, 90))

    def _bubble(self, d, u, text):
        c = self.c
        cx, cy = self.center(u['x'], u['y'])
        f = font(15, True)
        wdt = d.textlength(text, font=f) + 16
        top = cy - c * .3 - 40
        x0 = min(max(cx - wdt / 2, 4), W - wdt - 4)
        col = BUBBLE.get(text, (240, 240, 240))
        d.polygon([(cx - 6, top + 26), (cx + 6, top + 26), (cx, top + 34)], fill=col)
        d.rounded_rectangle([x0, top, x0 + wdt, top + 27], 9, fill=col, outline=INK, width=2)
        d.text((x0 + wdt / 2, top + 13), text, font=f, fill=INK, anchor='mm')

    # ---------- 찍기 ----------
    def mark_print(self):
        self.print_at = len(self.frames)

    def snap(self, ms=900):
        self.frames.append(self.draw())
        self.durs.append(ms)

    def walk(self, ui, steps, ms=110, sub=3, reveal=True):
        """모험가 ui 를 방향 글자 열 steps 대로 한 칸씩 걷게 한다 (칸 사이를 sub 장으로 잇는다)."""
        D = {'N': (0, -1), 'E': (1, 0), 'S': (0, 1), 'W': (-1, 0)}
        u = self.units[ui]
        for s in steps:
            dx, dy = D[s]
            x0, y0 = u['x'], u['y']
            for k in range(1, sub + 1):
                u['x'], u['y'] = x0 + dx * k / sub, y0 + dy * k / sub
                self.snap(ms)
            u['x'], u['y'] = x0 + dx, y0 + dy
            if reveal:
                self.known.add((u['x'], u['y']))

    def save(self, name):
        os.makedirs(OUT, exist_ok=True)
        # 모든 장면에서 고루 뽑아 한 팔레트를 만든다 (금 · 어둠 색이 빠지지 않게)
        pick = self.frames[::max(1, len(self.frames) // 8)]
        w0, h0 = self.frames[0].size
        mont = Image.new('RGB', (w0, h0 * len(pick) + 40))
        for i, f in enumerate(pick):
            mont.paste(f, (0, h0 * i))
        md = ImageDraw.Draw(mont)
        for i, col in enumerate([GOLD, (170, 120, 10), ORANGE, GREEN, RED, FOG, FOG_LINE, *TEAM, *TEAM_LIGHT, *BUBBLE.values()]):
            md.rectangle([i * 24, h0 * len(pick), i * 24 + 24, h0 * len(pick) + 40], fill=col)   # 꼭 지킬 색은 팔레트에 크게 넣는다
        pal = mont.quantize(colors=220, method=Image.Quantize.MEDIANCUT)
        fr = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in self.frames]
        self.durs[-1] = max(self.durs[-1], 2600)
        p = os.path.join(OUT, name)
        fr[0].save(p, save_all=True, append_images=fr[1:], duration=self.durs, loop=0, optimize=True)
        # 인쇄용 대표 그림 (마지막 장)
        self.frames[-1 if self.print_at is None else self.print_at].save(p.replace('.gif', '.png'))
        print(p, len(fr), 'frames', os.path.getsize(p) // 1024, 'KB')


def H(*kv):
    return list(kv)


# ===================== 1. 한 판의 흐름 =====================
def gif_loop():
    s = Scene(12, 7, 50, '① 한 판의 흐름: 뽑고 → 캐고 → 바친다')
    walls = [(5, 3), (6, 3), (3, 0), (8, 0), (0, 6), (11, 6)]
    pits = [(2, 5), (9, 5), (5, 6), (6, 6)]
    for c in walls:
        s.tiles[c] = 'wall'
    for c in pits:
        s.tiles[c] = 'pit'
    for c in [(4, 1), (7, 1)]:
        s.tiles[c] = 'gold'
    s.tiles[(1, 3)] = 'camp0'
    s.tiles[(10, 3)] = 'camp1'
    st = {'bank': [20, 20], 'score': [0, 0]}

    def hud():
        s.hud = [(f"붉은 금고 {st['bank'][0]} · 점수 {st['score'][0]}", TEAM_LIGHT[0]),
                 (f"푸른 금고 {st['bank'][1]} · 점수 {st['score'][1]}", TEAM_LIGHT[1])]
    hud()
    s.caption = '두 원정대가 금을 캐서 자기 야영지에 바치는 게임\n처음엔 모험가 0명, 금고 20 으로 시작한다'
    s.snap(2600)
    s.units = [dict(team=0, x=2, y=3, carry=0, arrow=True), dict(team=1, x=9, y=3, carry=0, arrow=True)]
    st['bank'] = [0, 0]
    hud()
    s.caption = '야영지가 금고 20 을 써서 옆 칸에 모험가를 뽑는다\n행동: Spawn(EXPLORER, 방향)'
    s.snap(2400)
    s.caption = '모험가는 한 차례에 행동 하나: 한 칸 이동, 캐기, 검, 화살 중 하나\n이동: Move(\'N\' / \'E\' / \'S\' / \'W\')'
    path_r, path_b = 'NNEE', 'NNWW'
    for a, b in zip(path_r, path_b):
        D = {'N': (0, -1), 'E': (1, 0), 'S': (0, 1), 'W': (-1, 0)}
        for k in range(1, 4):
            for u, ch in ((s.units[0], a), (s.units[1], b)):
                u['x'] += D[ch][0] / 3
                u['y'] += D[ch][1] / 3
            s.snap(120)
        for u in s.units:
            u['x'], u['y'] = round(u['x']), round(u['y'])
    s.bubbles = [(0, '반짝임'), (1, '반짝임')]
    s.caption = '반짝임 = 내가 선 칸에 금맥이 있다\n캐기: Mine() 한 번에 금 1개'
    s.snap(2200)
    for n in range(1, 6):
        for u in s.units:
            u['carry'] = n
        s.snap(450)
    s.bubbles = []
    s.caption = '든 금은 바쳐야 점수가 된다. 왔던 길로 야영지 옆까지 돌아간다\n(가다가 쓰러지면 든 금을 잃는다)'
    for a, b in zip('WWSS', 'EESS'):
        D = {'N': (0, -1), 'E': (1, 0), 'S': (0, 1), 'W': (-1, 0)}
        for k in range(1, 4):
            for u, ch in ((s.units[0], a), (s.units[1], b)):
                u['x'] += D[ch][0] / 3
                u['y'] += D[ch][1] / 3
            s.snap(120)
        for u in s.units:
            u['x'], u['y'] = round(u['x']), round(u['y'])
    for u in s.units:
        u['carry'] = 0
    st['score'] = [5, 5]
    st['bank'] = [5, 5]
    hud()
    s.marks = {(2, 3): 'hot', (9, 3): 'hot'}
    s.mark_print()
    s.caption = '야영지와 맞닿은 칸에서 차례를 마치면 저절로 바친다 → 점수 +5\n바친 금은 금고에도 들어가서 모험가를 더 뽑을 수 있다'
    s.snap(3000)
    s.marks = {}
    s.caption = '1000 라운드가 끝나면 바친 금이 많은 팀이 이긴다\n적 야영지(체력 150)를 부수면 그 자리에서 바로 이긴다'
    s.snap(3200)
    s.save('1_loop.gif')


# ===================== 2. 지각과 추론 =====================
def gif_infer():
    s = Scene(5, 5, 76, '② 자기 칸만 느낀다 → 기억하고 추론한다')
    s.tiles[(2, 4)] = 'pit'
    s.tiles[(3, 1)] = 'pit'
    s.tiles[(1, 1)] = 'wumpus'
    s.tiles[(4, 0)] = 'gold'
    s.fog = True
    s.units = [dict(team=0, x=0, y=4)]
    s.known = {(0, 4)}
    s.hud = [('봇이 아는 세상', (230, 230, 230))]
    s.caption = '모험가는 자기가 선 칸만 느낀다. 나머지는 모두 어둠\n구덩이 · 웜퍼스 · 금 · 적은 눈에 보이지 않는다'
    s.snap(2800)
    s.bubbles = [(0, '아무 느낌 없음')]
    s.caption = '바람이 없다 → 상하좌우에 구덩이가 없다'
    s.snap(1800)
    s.marks = {(1, 4): 'safe', (0, 3): 'safe'}
    s.caption = '바람이 없다 → 상하좌우에 구덩이가 없다\n→ 옆 두 칸은 안전 (초록)'
    s.snap(2400)
    s.bubbles = []
    s.walk(0, 'E')
    s.marks.pop((1, 4))
    s.bubbles = [(0, '바람')]
    s.caption = '바람! 상하좌우 어딘가에 구덩이가 있다\n어느 쪽인지는 알려 주지 않는다'
    s.snap(2200)
    s.marks.update({(2, 4): 'q', (1, 3): 'q'})
    s.caption = '후보는 오른쪽 칸과 위 칸 (?) 두 곳\n모르는 칸에 들어가는 건 도박이다. 안전한 칸으로 돌아간다'
    s.snap(2600)
    s.bubbles = []
    s.walk(0, 'W')
    s.walk(0, 'N')
    s.marks.pop((0, 3))
    s.bubbles = [(0, '아무 느낌 없음')]
    s.caption = '여기도 바람 없음 → 위 칸과 오른쪽 칸은 안전'
    s.snap(1800)
    s.marks.update({(1, 3): 'safe', (0, 2): 'safe'})
    s.snap(1800)
    s.marks[(2, 4)] = 'pit'
    s.mark_print()
    s.caption = '? 두 칸 중 하나가 안전으로 밝혀졌다 → 구덩이는 남은 하나!\n수업의 명제논리 추론 그대로다'
    s.snap(3000)
    s.bubbles = []
    s.fog = False
    s.marks = {(2, 4): 'pit'}
    s.hud = [('실제 맵 (봇에게는 안 보임)', (250, 225, 150))]
    s.caption = '정답 확인: 실제로 그 칸에 구덩이\n악취 → 웜퍼스 굴도 똑같이 추론한다 (굴에 들어가면 잡아먹힌다)'
    s.snap(3600)
    s.save('2_infer.gif')


# ===================== 3. 적 야영지 찾기 =====================
def gif_symmetry():
    s = Scene(12, 8, 48, '③ 적 야영지는 숨어 있다: 대칭으로 찾는다')
    gw, gh = 12, 8
    # 실제 맵은 180° 회전 (R) 대칭
    base_walls = [(5, 2), (9, 3), (0, 4)]
    base_pits = [(1, 6), (4, 4)]
    for x, y in base_walls:
        s.tiles[(x, y)] = 'wall'
        s.tiles[(gw - 1 - x, gh - 1 - y)] = 'wall'
    for x, y in base_pits:
        s.tiles[(x, y)] = 'pit'
        s.tiles[(gw - 1 - x, gh - 1 - y)] = 'pit'
    s.tiles[(2, 1)] = 'camp0'
    s.tiles[(9, 6)] = 'camp1'
    s.fog = True
    s.known = {(2, 1), (3, 1)}
    s.units = [dict(team=0, x=3, y=1)]
    s.hud = [('봇이 아는 세상', (230, 230, 230))]
    s.caption = '우리 야영지 위치만 안다. 맵은 좌우 · 상하 · 180° 회전 중 하나로 대칭\n→ 적 야영지는 우리 야영지의 거울 칸 세 곳 중 하나'
    s.snap(3000)
    s.ghosts = {(9, 1): ('좌우?', False), (2, 6): ('상하?', False), (9, 6): ('회전?', False)}
    s.snap(2600)
    s.caption = '후보를 하나씩 지워 보자'
    s.walk(0, 'EEES')
    s.walk(0, 'NW')
    s.bubbles = [(0, '부딪힘')]
    s.lines = [('arrow', (5, 1), (5, 2))]
    s.caption = '아래로 가려다 막혔다 (발소리도 없음) → 그 칸은 벽'
    s.snap(1400)
    s.known.add((5, 2))
    s.snap(1600)
    s.lines = [('mirror_v', 6), ('link', (5, 2), (6, 2))]
    s.marks = {(6, 2): 'hot'}
    s.caption = '좌우 대칭이라면 벽의 거울 칸 (노란 선 건너편) 도 벽이어야 한다\n그런데 그 칸에는 아까 서 봤다 → 좌우 대칭이 아니다!'
    s.snap(3400)
    s.ghosts[(9, 1)] = ('좌우?', True)
    s.lines, s.marks, s.bubbles = [], {}, []
    s.snap(1400)
    s.caption = '이번엔 상하 후보 쪽으로 가 본다'
    s.walk(0, 'WWSSSSS', ms=90)
    s.bubbles = [(0, '열기 없음')]
    s.marks = {(2, 6): 'hot'}
    s.caption = '열기 = 상하좌우에 야영지가 있다. 바로 옆이 후보인데 열기가 없다\n→ 상하 대칭도 아니다!'
    s.snap(3400)
    s.ghosts[(2, 6)] = ('상하?', True)
    s.marks, s.bubbles = {}, []
    s.ghosts[(9, 6)] = ('적 야영지!', False)
    s.mark_print()
    s.caption = '남은 후보는 180° 회전 하나 → 적 야영지는 여기\n(1차 논리 · 가설 지우기)'
    s.snap(3000)
    s.fog = False
    s.ghosts = {}
    s.hud = [('실제 맵 (180° 회전 대칭)', (250, 225, 150))]
    s.caption = '정답 확인. 벽 · 구덩이 · 금 · 야영지가 모두 같은 대칭을 따른다\n대칭을 알면 아직 안 가 본 쪽 지도도 거울로 알 수 있다'
    s.snap(3600)
    s.save('3_symmetry.gif')


# ===================== 4. 화살 · 웜퍼스 · 싸움 =====================
def gif_fight():
    s = Scene(8, 5, 66, '④ 화살과 웜퍼스, 그리고 금 빼앗기')
    s.tiles[(3, 2)] = 'wumpus'
    s.tiles[(6, 0)] = 'wall'
    s.tiles[(0, 4)] = 'wall'
    s.fog = True
    s.known = {(1, 1)}
    s.units = [dict(team=0, x=1, y=1, carry=0, arrow=True, hp=10)]
    s.hud = [('붉은 모험가: 화살 1발', TEAM_LIGHT[0])]
    s.caption = '웜퍼스는 굴에서 움직이지 않는다. 굴에 들어가면 잡아먹힌다\n쓰러뜨리는 방법은 화살뿐 (검은 안 통한다)'
    s.snap(2600)
    s.walk(0, 'EE')
    s.bubbles = [(0, '악취')]
    s.marks = {(4, 1): 'q', (3, 0): 'q', (3, 2): 'q'}
    s.caption = '악취 = 상하좌우에 웜퍼스 굴이 있다\n지나온 왼쪽 칸은 빼면 후보는 셋'
    s.snap(2600)
    s.bubbles = []
    s.walk(0, 'W')
    s.walk(0, 'S')
    s.bubbles = [(0, '악취')]
    s.marks.update({(2, 3): 'q', (1, 2): 'q'})
    s.caption = '여기도 악취. 두 곳 모두의 이웃인 칸만 남긴다\n→ 겹치는 칸은 하나뿐!'
    s.snap(2400)
    s.marks = {(3, 2): 'wump'}
    s.mark_print()
    s.snap(1800)
    s.bubbles = []
    s.caption = '같은 줄에 있으니 쏜다: Shoot(\'E\')\n화살은 벽 · 맵 끝까지 일직선으로 날아가 처음 만난 것에 맞는다'
    s.units[0]['arrow'] = False
    s.lines = [('arrow', (2, 2), (2.9, 2))]
    s.hud = [('붉은 모험가: 화살 0발', TEAM_LIGHT[0])]
    s.snap(1400)
    s.lines = []
    s.known.add((3, 2))
    s.tiles[(3, 2)] = 'deadw'
    s.marks = {}
    s.units[0]['carry'] = 30
    s.bubbles = [(0, '비명!')]
    s.caption = '명중! 웜퍼스가 쓰러지고 쏜 모험가가 보물 30 을 든다\n맵 전체가 비명을 듣는다. 화살은 야영지 옆에서 다시 채운다'
    s.snap(3200)
    # 2막: 싸움
    s.fog = False
    s.bubbles = []
    s.tiles[(3, 2)] = 'deadw'
    s.units[0]['show_hp'] = True
    s.units.append(dict(team=1, x=6, y=2, carry=4, arrow=True, hp=10, show_hp=True))
    s.hud = [('관전자 화면', (250, 225, 150))]
    s.caption = '그런데 금을 든 모험가는 표적이 된다 (체력 10)\n푸른 모험가가 같은 줄에서 화살을 쏜다 (피해 6)'
    s.snap(2400)
    s.units[1]['arrow'] = False
    s.lines = [('arrow', (5.6, 2), (2.4, 2))]
    s.snap(800)
    s.lines = []
    s.units[0]['hp'] = 4
    s.bubbles = [(0, '아픔')]
    s.snap(1600)
    s.bubbles = []
    s.caption = '다가와서 검으로 친다: Attack(x, y) (상하좌우 바로 옆 칸, 피해 3)'
    s.walk(1, 'SWWWW', ms=90, reveal=False)
    s.lines = [('arrow', (2, 2.9), (2, 2.35))]
    s.units[0]['hp'] = 1
    s.bubbles = [(0, '아픔')]
    s.snap(1300)
    s.lines, s.bubbles = [], []
    s.snap(400)
    s.lines = [('arrow', (2, 2.9), (2, 2.35))]
    s.snap(500)
    s.lines = []
    s.units[0]['hp'] = 0
    s.units[0]['alive'] = False
    s.units[1]['carry'] = 4 + 30 + 3
    s.caption = '쓰러뜨린 쪽이 상대가 든 금 + 3 을 바로 빼앗는다 (4 + 30 + 3 = 37)\n많이 들수록 위험하다. 언제 돌아가 바칠지가 전략이다'
    s.snap(3600)
    s.save('4_fight.gif')


if __name__ == '__main__':
    gif_loop()
    gif_infer()
    gif_symmetry()
    gif_fight()
