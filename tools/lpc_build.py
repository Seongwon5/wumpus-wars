"""LPC (Liberated Pixel Cup) 레이어를 합성해 뷰어용 캐릭터 시트를 만든다.

python -X utf8 tools/lpc_build.py <LPC 저장소> <decoration_medieval> <LPC_cavern_ruins> <oga_monsters> <oga_containers> <oga_warrior> <portraits-64px>

야영지 (천막 · 모닥불 · 팀 깃발) 는 bluecarrot16 의 "[LPC] Medieval Village Decorations" (CC-BY-SA 3.0+) 에서 가져온다:
https://opengameart.org/content/lpc-medieval-village-decorations

LPC 저장소: https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator
(spritesheets/, sheet_definitions/ 만 있으면 된다). 그림 라이선스는 레이어마다 다르며 (CC-BY-SA 3.0, GPL 3.0, OGA-BY 3.0, CC0 등),
모두 상업적 이용이 되고 만든 사람 표기가 필요하다. 쓴 레이어의 표기는 wumpus/viewer/sprites/CREDITS.md 에 자동으로 적는다.

결과 (wumpus/viewer/sprites/):
- explorer_0.png, explorer_1.png, archer_0.png, archer_1.png, wumpus.png : 128×128 칸 시트
- sprites.json : 동작별 줄 · 칸 수
줄 순서: 동작마다 방향 4줄 (위, 왼쪽, 아래, 오른쪽). 쓰러짐 (hurt) 은 1줄.
"""
import glob
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'wumpus', 'viewer', 'sprites')
CELL = 128          # 칸 크기 (곡괭이 휘두르기가 64 칸 밖으로 나간다)
OFF = 32            # 64 칸 그림을 128 칸 가운데에 놓는 자리

RAMPS = {
    'team0': ['#3a0e0e', '#7a1c18', '#b8322a', '#e8584a', '#ffa08a'],
    'team1': ['#0e1c3a', '#1a3f7a', '#2a6cc0', '#4aa0f0', '#a8dcff'],
    'brown_hair': ['#22120a', '#3e2412', '#5e3a1e', '#7e5230'],
    'blonde': ['#6a4818', '#a87228', '#e0b050', '#f4d07a', '#fff0c0'],
    'cream': ['#5a4c36', '#9a8a6c', '#cfc2a4', '#ece2cc'],
    'pants': ['#1a1410', '#2e241a', '#463626', '#5e4a34'],
    'leather': ['#1a0e06', '#2e1c10', '#4a3020', '#6a4830'],
    'green': ['#10200a', '#264216', '#3e6a22', '#5e8e30', '#94c454'],
    'moss': ['#0c160e', '#1e3222', '#34503a', '#4e7048', '#76965c', '#a8c47c', '#d4e8a0'],
    'gold': ['#3a2000', '#6a4004', '#a86c10', '#d89a20', '#f0c040', '#ffe080'],
}


def hexrgb(h):
    n = int(h[1:], 16)
    return (n >> 16 & 255, n >> 8 & 255, n & 255)


def recolor(img, ramp):
    """불투명 색을 밝기 순위대로 ramp 에 옮긴다 (가장 어두운 테두리는 가장 어두운 색으로)."""
    img = img.convert('RGBA')
    px = img.load()
    cols = {px[x, y][:3] for x in range(img.width) for y in range(img.height) if px[x, y][3] > 0}
    lum = sorted(cols, key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    rr = [hexrgb(h) for h in RAMPS[ramp]]
    m = {c: rr[min(len(rr) - 1, i * len(rr) // max(1, len(lum)))] for i, c in enumerate(lum)}
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a:
                px[x, y] = m[(r, g, b)] + (a,)
    return img


class Layer:
    def __init__(self, src, path, z, variant=None, ramp=None, credit=None):
        self.src, self.path, self.z, self.variant, self.ramp, self.credit = src, path, z, variant, ramp, credit
        self._cache = {}

    def sheet(self, anim):
        if anim in self._cache:
            return self._cache[anim]
        base = os.path.join(self.src, 'spritesheets', self.path)
        cands = [os.path.join(base, anim + '.png')]
        if self.variant:
            cands.insert(0, os.path.join(base, anim, self.variant + '.png'))
        im = None
        for c in cands:
            if os.path.isfile(c):
                im = Image.open(c).convert('RGBA')
                break
        if im is not None and self.ramp:
            im = recolor(im, self.ramp)
        self._cache[anim] = im
        return im


def frame(sheet, col, row, size=64):
    return sheet.crop((col * size, row * size, col * size + size, row * size + size))


def compose(layers, anim, col, row):
    """64 칸 동작의 한 칸을 128 칸 가운데에 합성."""
    out = Image.new('RGBA', (CELL, CELL))
    for L in sorted(layers, key=lambda l: l.z):
        sh = L.sheet(anim)
        if sh is None:
            continue
        r = row if sh.height > 64 else 0
        if (col + 1) * 64 > sh.width or (r + 1) * 64 > sh.height:
            continue
        out.alpha_composite(frame(sh, col, r), (OFF, OFF))
    return out


def tool_swing(layers, tool_bg, tool_fg, col, row):
    """곡괭이 휘두르기: 몸은 slash (64 칸), 곡괭이는 128 칸 앞 · 뒤 그림."""
    out = Image.new('RGBA', (CELL, CELL))
    out.alpha_composite(frame(tool_bg, col, row, 128))
    out.alpha_composite(compose(layers, 'slash', col, row))
    out.alpha_composite(frame(tool_fg, col, row, 128))
    return out


def build(name, layers, attack, extra=None):
    """시트 하나: idle (걷기 첫 칸), walk 8, attack n, hurt 6 (1줄)."""
    rows, meta = [], {}
    def add(key, frames_by_dir):
        meta[key] = {'row': len(rows), 'n': len(frames_by_dir[0]), 'dirs': len(frames_by_dir)}
        rows.extend(frames_by_dir)
    add('idle', [[compose(layers, 'walk', 0, d)] for d in range(4)])
    add('walk', [[compose(layers, 'walk', c, d) for c in range(1, 9)] for d in range(4)])
    if attack == 'tool':
        add('attack', [[tool_swing(layers, extra[0], extra[1], c, d) for c in range(6)] for d in range(4)])
    else:
        n = {'shoot': 13, 'slash': 6, 'thrust': 8}[attack]
        add('attack', [[compose(layers, attack, c, d) for c in range(n)] for d in range(4)])
    add('hurt', [[compose(layers, 'hurt', c, 0) for c in range(6)]])
    cols = max(len(r) for r in rows)
    sheet = Image.new('RGBA', (cols * CELL, len(rows) * CELL))
    for y, r in enumerate(rows):
        for x, im in enumerate(r):
            sheet.alpha_composite(im, (x * CELL, y * CELL))
    sheet.save(os.path.join(OUT, name + '.png'), optimize=True)
    return {'cols': cols, 'rows': len(rows), **meta}


def build_camp(deco, t):
    """야영지 시트: 살아 있는 5칸 (모닥불이 타오름) + 무너진 5칸 (검게 탄 천막이 불탐). 칸 160×160."""
    im = Image.open(os.path.join(deco, 'decorations-medieval.png')).convert('RGBA')
    tent = im.crop((384, 1728, 512, 1888))
    banner = im.crop((96, 1216, 128, 1312) if t == 0 else (32, 1216, 64, 1312))
    fires = [im.crop((256 + 32 * k, 1504, 288 + 32 * k, 1568)) for k in range(5)]
    burnt = tent.copy()
    px = burnt.load()
    for y in range(burnt.height):
        for x in range(burnt.width):
            r, g, b, a = px[x, y]
            if a:
                v = int((r + g + b) / 3 * 0.32)
                px[x, y] = (v + 10, v + 4, v, a)
    C = 160
    sheet = Image.new('RGBA', (C * 10, C))
    for k in range(5):
        f = Image.new('RGBA', (C, C))
        f.alpha_composite(banner, (2, 44))
        f.alpha_composite(tent, (24, 0))
        f.alpha_composite(fires[k], (122, 94))
        sheet.alpha_composite(f, (k * C, 0))
        d = Image.new('RGBA', (C, C))
        d.alpha_composite(burnt.resize((128, 120), Image.NEAREST), (24, 40))
        d.alpha_composite(fires[k], (44, 92))
        d.alpha_composite(fires[(k + 2) % 5], (86, 84))
        d.alpha_composite(fires[(k + 4) % 5], (64, 70))
        sheet.alpha_composite(d, ((5 + k) * C, 0))
    sheet.save(os.path.join(OUT, 'camp_%d.png' % t), optimize=True)
    return {'cols': 10, 'rows': 1, 'cell': C, 'foot': 152, 'alive': [0, 5], 'dead': [5, 5]}


def build_golem(mon):
    """웜퍼스: LPC 골렘 (Redshrike · William.Thompsonj, CC-BY 3.0 등) 을 이끼 낀 초록 돌로. 64 칸 그림을 128 칸 가운데에."""
    walk = recolor(Image.open(os.path.join(mon, 'golem-walk.png')), 'moss')
    atk = recolor(Image.open(os.path.join(mon, 'golem-atk.png')), 'moss')
    die = recolor(Image.open(os.path.join(mon, 'golem-die.png')), 'moss')
    def cell(sh, c, r):
        f = Image.new('RGBA', (CELL, CELL))
        f.alpha_composite(frame(sh, c, r), (OFF, OFF))
        return f
    rows, meta = [], {}
    def add(key, fr):
        meta[key] = {'row': len(rows), 'n': len(fr[0]), 'dirs': len(fr)}
        rows.extend(fr)
    add('idle', [[cell(walk, 0, d)] for d in range(4)])
    add('walk', [[cell(walk, c, d) for c in range(7)] for d in range(4)])
    add('attack', [[cell(atk, c, d) for c in range(7)] for d in range(4)])
    add('hurt', [[cell(die, c, 0) for c in range(7)]])
    cols = max(len(r) for r in rows)
    sheet = Image.new('RGBA', (cols * CELL, len(rows) * CELL))
    for y, r in enumerate(rows):
        for x, im in enumerate(r):
            sheet.alpha_composite(im, (x * CELL, y * CELL))
    sheet.save(os.path.join(OUT, 'wumpus.png'), optimize=True)
    return {'cols': cols, 'rows': len(rows), **meta}


def build_props(con, deco):
    """떨어진 금 (LPC Containers, CC-BY-SA 4.0): 주머니 · 주머니 더미 · 금 상자. 모서리 횃불 기둥 (Medieval Decorations): 불꽃 3장."""
    out = {}
    im = Image.open(os.path.join(con, 'container-contents-demo_0.png')).convert('RGBA')
    T = 32
    loot = Image.new('RGBA', (T * 3, T))
    for k, (c, r) in enumerate([(11, 26), (13, 27), (14, 10)]):
        loot.alpha_composite(im.crop((c * T, r * T, c * T + T, r * T + T)), (k * T, 0))
    loot.save(os.path.join(OUT, 'loot.png'))
    out['loot'] = {'cols': 3, 'rows': 1, 'cell': T, 'foot': 30}
    dm = Image.open(os.path.join(deco, 'decorations-medieval.png')).convert('RGBA')
    post = dm.crop((11 * T, 6 * T, 12 * T, 9 * T))
    br = Image.new('RGBA', (T * 3, 120))
    for k in range(3):
        f = Image.new('RGBA', (T, 120))
        f.alpha_composite(post, (0, 24))
        f.alpha_composite(dm.crop(((13 + k) * T, 5 * T, (14 + k) * T, 6 * T)), (0, 4))
        br.alpha_composite(f, (k * T, 0))
    br.save(os.path.join(OUT, 'brazier.png'))
    out['brazier'] = {'cols': 3, 'rows': 1, 'cell': T, 'foot': 118}
    return out


def build_cave(cav):
    """동굴 타일 (LPC Cavern and Ruin Tiles, CC-BY-SA 3.0 / GPL): 바닥 · 벽 옆면 · 벽 윗면 · 금맥 (파란 수정을 금색으로)."""
    im = Image.open(os.path.join(cav, 'cavern_ruins.png')).convert('RGBA')
    T = 32
    tile = lambda c, r, w=1, h=1: im.crop((c * T, r * T, (c + w) * T, (r + h) * T))
    out = {}
    floor = tile(0, 0)                                   # 어두운 동굴 바닥: 밝혀서 잘 보이게
    floor = Image.eval(floor.convert('RGB'), lambda v: min(255, int(v * 2.5 + 8))).convert('RGBA')
    fp = floor.load()                                   # 칸 경계: 아래 · 오른쪽은 어두운 줄, 위 · 왼쪽은 밝은 줄
    for i in range(T):
        for (x, y), k in (((i, T - 1), 0.55), ((T - 1, i), 0.55), ((i, 0), 1.25), ((0, i), 1.25)):
            r, g, b_, a_ = fp[x, y]
            fp[x, y] = (min(255, int(r * k)), min(255, int(g * k)), min(255, int(b_ * k)), a_)
    floor.save(os.path.join(OUT, 'floor.png'))
    out['floor'] = {'cols': 1, 'rows': 1, 'cell': T, 'tile': True}
    def stone(p, sat, bright, tint=(1.0, 1.0, 1.0)):     # 바위 질감: 채도를 빼고 밝기를 맞춘다 (판석 칸 · 줄눈 없음)
        p = p.convert('RGBA'); px = p.load()
        for y in range(p.height):
            for x in range(p.width):
                r, g, b, a = px[x, y]
                l = 0.3 * r + 0.59 * g + 0.11 * b
                c = [min(255, int((l + (v - l) * sat) * bright * t)) for v, t in zip((r, g, b), tint)]
                px[x, y] = (c[0], c[1], c[2], a)
        return p
    side = stone(tile(13, 1), 0.35, 0.95, (1.0, 0.97, 0.92))       # 옆면: 결이 세로로 난 회갈색 바위
    side.save(os.path.join(OUT, 'wall_side.png'))
    out['wall_side'] = {'cols': 1, 'rows': 1, 'cell': 32, 'tile': True}
    top = stone(tile(19, 1), 0.15, 1.05, (1.0, 0.98, 0.95))        # 윗면: 울퉁불퉁한 밝은 회색 바위
    top.save(os.path.join(OUT, 'wall_top.png'))
    out['wall_top'] = {'cols': 1, 'rows': 1, 'cell': 32, 'tile': True}
    tile(13, 3).save(os.path.join(OUT, 'pit.png'))      # 칸 하나짜리 낭떠러지 (금빛 테두리 · 갈색 절벽 · 검은 구멍)
    out['pit'] = {'cols': 1, 'rows': 1, 'cell': T, 'tile': True}
    tile(23, 2).save(os.path.join(OUT, 'bones.png'))    # 해골과 뼈 (쓰러진 웜퍼스 굴)
    out['bones'] = {'cols': 1, 'rows': 1, 'cell': T, 'foot': 30}
    rock = tile(12, 9)
    small, cluster, tall = tile(9, 10), tile(9, 11), tile(10, 10, 1, 2)
    gold = lambda p: recolor(p, 'gold')
    small, cluster, tall = gold(small), gold(cluster), gold(tall)
    C = 64
    sheet = Image.new('RGBA', (C * 8, C))
    plan = [[], [(small, 16, 32)], [(cluster, 16, 32)], [(cluster, 6, 32), (small, 28, 34)], [(tall, 16, 0)],
            [(tall, 10, 0), (small, 30, 34)], [(tall, 8, 0), (cluster, 26, 32)], [(cluster, 0, 30), (tall, 16, 0), (small, 34, 34)]]
    for k, parts in enumerate(plan):
        f = Image.new('RGBA', (C, C))
        f.alpha_composite(rock.resize((40, 40), Image.NEAREST), (12, 26))
        for p, x, y in parts:
            f.alpha_composite(p, (x, y))
        sheet.alpha_composite(f, (k * C, 0))
    sheet.save(os.path.join(OUT, 'ore.png'), optimize=True)
    out['ore'] = {'cols': 8, 'rows': 1, 'cell': C, 'foot': 62}
    return out


_HX = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
W_DARK = {_HX('#3e3542'): 0, _HX('#50404a'): 1, _HX('#735c6a'): 2}       # 머리카락 · 바지 · 테두리가 같이 쓰는 어두운 색
W_SKIN = {_HX('#ffe7d4'), _HX('#e6c6ae')}
W_HAIR = ['#8a5a1e', '#dcae48', '#f8e08c']                                # 금발 (어두운 동굴에서도 머리가 보이게)
W_TEAM = [  # 목도리 어두운 · 밝은, 겉옷 어두운 · 밝은
    {'#873455': '#c22a20', '#b34564': '#ff5a44', '#99766a': '#7c2620', '#c19f91': '#a83a30'},
    {'#873455': '#1f6fd0', '#b34564': '#48b0ff', '#99766a': '#1f3f7c', '#c19f91': '#2f5fae'},
]


def warrior_frame(fr, t):
    """검사 한 칸을 팀 색으로: 목도리 · 겉옷은 팀 색, 얼굴에 닿은 어두운 덩어리 (머리카락) 는 금발."""
    fr = fr.copy(); px = fr.load(); w, h = fr.size
    tm = {_HX(k): _HX(v) for k, v in W_TEAM[t].items()}
    seen = set()
    for y0 in range(h):
        for x0 in range(w):
            if (x0, y0) in seen or px[x0, y0][3] == 0 or px[x0, y0][:3] not in W_DARK:
                continue
            comp, st, touch = [], [(x0, y0)], False
            seen.add((x0, y0))
            while st:
                x, y = st.pop(); comp.append((x, y))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        xx, yy = x + dx, y + dy
                        if not (0 <= xx < w and 0 <= yy < h) or px[xx, yy][3] == 0:
                            continue
                        c = px[xx, yy][:3]
                        if c in W_SKIN:
                            touch = True
                        elif c in W_DARK and (xx, yy) not in seen:
                            seen.add((xx, yy)); st.append((xx, yy))
            if touch:
                for x, y in comp:
                    px[x, y] = _HX(W_HAIR[W_DARK[px[x, y][:3]]]) + (255,)
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if c[3] and c[:3] in tm:
                px[x, y] = tm[c[:3]] + (255,)
    return fr


def build_warrior(war, t):
    """모험가: Calciumtrice 의 "4 Direction Animated Warrior" (CC-BY 4.0). 5등신 검사, 네 방향 · 서기 12 · 걷기 8 · 베기 6 · 쓰러짐 14. 칸 64."""
    im = Image.open(os.path.join(war, 'warrior_6.png')).convert('RGBA')
    C = 64
    cell = lambda r, c: warrior_frame(im.crop((c * C, r * C, c * C + C, r * C + C)), t)
    order = [18, 12, 6, 0]                                   # 시트 줄: 뒤 (위), 왼쪽, 앞 (아래), 오른쪽
    rows, meta = [], {}
    def add(key, off, n):
        meta[key] = {'row': len(rows), 'n': n, 'dirs': 4}
        rows.extend([[cell(b + off, c) for c in range(n)] for b in order])
    add('idle', 1, 12); add('walk', 3, 8); add('attack', 5, 6)
    meta['hurt'] = {'row': len(rows), 'n': 14, 'dirs': 1}
    rows.append([cell(24, c) for c in range(14)])
    sheet = Image.new('RGBA', (14 * C, len(rows) * C))
    for y, r in enumerate(rows):
        for x, f in enumerate(r):
            sheet.alpha_composite(f, (x * C, y * C))
    sheet.save(os.path.join(OUT, 'adventurer_%d.png' % t), optimize=True)
    return {'cols': 14, 'rows': len(rows), 'cell': C, 'foot': 51, 'scale': 2.4, **meta}


P_TEAM = [{'#4d613c': '#a82a22', '#698e34': '#ff5a44', 'dark': '#5a1512'}, {'#4d613c': '#2458b0', '#698e34': '#48b0ff', 'dark': '#12305e'}]
P_HAIR = {'#6b7b89': '#dcae48', '#555461': '#a87428', '#939388': '#f8e08c', '#26323c': '#6e4a18'}


def build_portrait(port, t):
    """초상화: pebonius 의 "64px portraits" (CC-BY 4.0) 가운데 portrelf. 머리는 금발, 망토는 팀 색."""
    src = Image.open(os.path.join(port, 'portrelf.png')).convert('RGBA'); sp = src.load()
    im = src.copy(); px = im.load()
    hair = {_HX(k): _HX(v) for k, v in P_HAIR.items()}
    # 머리카락 = 머리카락 색 덩어리 가운데 그림 위쪽 (y < 12) 에 닿은 것. 눈동자는 검은 테두리에 갇혀 있어 빠진다
    isH = lambda x, y: 0 <= x < 64 and 0 <= y < 64 and sp[x, y][3] and sp[x, y][:3] in hair
    hset, st = set(), [(x, y) for y in range(12) for x in range(64) if isH(x, y)]
    hset.update(st)
    while st:
        x, y = st.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, y + dy)
            if q not in hset and isH(*q):
                hset.add(q); st.append(q)
    for y in range(64):
        for x in range(64):
            r, g, b, a = sp[x, y]
            if not a:
                continue
            c = (r, g, b)
            k = '#%02x%02x%02x' % c
            if k in P_TEAM[t]:
                px[x, y] = _HX(P_TEAM[t][k]) + (a,)
            elif k == '#26323c' and y >= 44 and (x, y) not in hset:
                px[x, y] = _HX(P_TEAM[t]['dark']) + (a,)       # 망토 그늘
            elif (x, y) in hset:
                px[x, y] = hair[c] + (a,)
    im.save(os.path.join(OUT, 'portrait_%d.png' % t))
    return {'cols': 1, 'rows': 1, 'cell': 64, 'portrait': True}


def defs(src):
    out = {}
    for f in glob.glob(os.path.join(src, 'sheet_definitions', '**', '*.json'), recursive=True):
        out[os.path.basename(f)] = json.load(open(f, encoding='utf-8'))
    return out


LEGACY = '--legacy' in sys.argv
if LEGACY:
    sys.argv.remove('--legacy')


def main():
    src = sys.argv[1]
    os.makedirs(OUT, exist_ok=True)
    D = defs(src)
    used = []

    def L(defname, path, z, variant=None, ramp=None):
        used.append(defname)
        return Layer(src, path, z, variant, ramp)

    meta = {'cell': CELL, 'foot': OFF + 62, 'sheets': {}}
    for t in (0, 1):
        team = 'team%d' % t
        explorer = [
            L('body.json', 'body/bodies/male', 10),
            L('legs_pants.json', 'legs/pants/male', 20, ramp='pants'),
            L('feet_boots_basic.json', 'feet/boots/basic/male', 25, ramp='leather'),
            L('torso_clothes_longsleeve.json', 'torso/clothes/longsleeve/longsleeve/male', 35, ramp='cream'),
            L('torso_clothes_vest.json', 'torso/clothes/vest/male', 55, variant='brown'),
            L('heads_human_male.json', 'head/heads/human/male', 100),
            L('eyes_human.json', 'eyes/human/adult/default', 105),
            L('hair_plain.json', 'hair/plain/adult', 120, ramp='brown_hair'),
            L('hat_bandana2.json', 'hat/cloth/bandana2/adult', 130, ramp=team),
            L('tool_pickaxe.json', 'tools/pickaxe/male', 140),
        ]
        tb = Image.open(os.path.join(src, 'spritesheets/tools/pickaxe/bg.png')).convert('RGBA')
        tf = Image.open(os.path.join(src, 'spritesheets/tools/pickaxe/fg.png')).convert('RGBA')
        if LEGACY:                                         # 옛 규칙 (시안 1 · 2) 의 탐험가 · 궁수 시트는 --legacy 때만
            meta['sheets']['explorer_%d' % t] = build('explorer_%d' % t, explorer, 'tool', (tb, tf))
        archer = [
            L('weapon_ranged_bow_normal.json', 'weapon/ranged/bow/normal/universal/background', 1, variant='light'),
            L('cape_solid.json', 'cape/solid/bg', 5, ramp=team),
            L('quiver.json', 'quiver', 8, variant='quiver'),
            L('hair_ponytail.json', 'hair/ponytail/adult/bg', 9, ramp='blonde'),
            L('body.json', 'body/bodies/female', 10),
            L('legs_skirts_plain.json', 'legs/skirts/plain/thin', 20, ramp=team),
            L('feet_boots_basic.json', 'feet/boots/basic/thin', 25, ramp='leather'),
            L('torso_clothes_blouse_longsleeve.json', 'torso/clothes/blouse_longsleeve/female', 35, variant='white'),
            L('torso_clothes_corset.json', 'torso/clothes/corset/female', 45, variant='leather'),
            L('cape_solid.json', 'cape/solid/fg', 85, ramp=team),
            L('heads_human_female.json', 'head/heads/human/female', 100),
            L('eyes_human.json', 'eyes/human/adult/default', 105),
            L('hair_ponytail.json', 'hair/ponytail/adult/fg', 120, ramp='blonde'),
            L('weapon_ranged_bow_normal.json', 'weapon/ranged/bow/normal/universal/foreground', 140, variant='light'),
        ]
        if LEGACY:
            meta['sheets']['archer_%d' % t] = build('archer_%d' % t, archer, 'shoot')
        adventurer = [                                    # 시안 3 모험가: 단검을 든 탐험가 (팀 색 두건)
            L('weapon_sword_dagger.json', 'weapon/sword/dagger/behind', 9, variant='dagger'),
            L('body.json', 'body/bodies/male', 10),
            L('legs_pants.json', 'legs/pants/male', 20, ramp='pants'),
            L('feet_boots_basic.json', 'feet/boots/basic/male', 25, ramp='leather'),
            L('torso_clothes_longsleeve.json', 'torso/clothes/longsleeve/longsleeve/male', 35, ramp='cream'),
            L('torso_clothes_vest.json', 'torso/clothes/vest/male', 55, variant='brown'),
            L('heads_human_male.json', 'head/heads/human/male', 100),
            L('eyes_human.json', 'eyes/human/adult/default', 105),
            L('hair_plain.json', 'hair/plain/adult', 120, ramp='brown_hair'),
            L('hat_bandana2.json', 'hat/cloth/bandana2/adult', 130, ramp='team%d' % t),
            L('weapon_sword_dagger.json', 'weapon/sword/dagger', 140, variant='dagger'),
        ]
        meta['sheets']['adventurer_%d' % t] = build('adventurer_%d' % t, adventurer, 'slash')
    wumpus = [
        L('body.json', 'body/bodies/muscular', 10, ramp='green'),
        L('heads_troll.json', 'head/heads/troll/adult', 100, ramp='green'),
    ]
    meta['sheets']['wumpus'] = build('wumpus', wumpus, 'slash')
    af = os.path.join(src, 'spritesheets', 'weapon', 'ranged', 'bow', 'arrow', 'shoot', 'arrow.png')
    if LEGACY and os.path.isfile(af):                    # 날아가는 화살: 활시위에 걸린 화살 (오른쪽 줄 7번 칸) 을 잘라 쓴다
        used.append('weapon_ranged_bow_arrow.json')
        a_ = Image.open(af).convert('RGBA').crop((64 * 7 + 28, 64 * 3 + 26, 64 * 7 + 61, 64 * 3 + 33))
        a_.save(os.path.join(OUT, 'arrow.png'))
        meta['sheets']['arrow'] = {'cols': 1, 'rows': 1, 'cell': a_.width}
    deco = sys.argv[2] if len(sys.argv) > 2 else None
    if deco:
        for t in (0, 1):
            meta['sheets']['camp_%d' % t] = build_camp(deco, t)
    cav = sys.argv[3] if len(sys.argv) > 3 else None
    if cav:
        meta['sheets'].update(build_cave(cav))
    mon = sys.argv[4] if len(sys.argv) > 4 else None
    if mon:
        meta['sheets']['wumpus'] = build_golem(mon)
    con = sys.argv[5] if len(sys.argv) > 5 else None
    if con and deco:
        meta['sheets'].update(build_props(con, deco))
    war = sys.argv[6] if len(sys.argv) > 6 else None
    if war:
        for t in (0, 1):
            meta['sheets']['adventurer_%d' % t] = build_warrior(war, t)
    port = sys.argv[7] if len(sys.argv) > 7 else None
    if port:
        for t in (0, 1):
            meta['sheets']['portrait_%d' % t] = build_portrait(port, t)
    json.dump(meta, open(os.path.join(OUT, 'sprites.json'), 'w', encoding='utf-8'), indent=1)

    # 만든 사람 표기
    lines = ['# 스프라이트 출처 (LPC)', '',
             '캐릭터 그림은 Liberated Pixel Cup (LPC) 그림을 합성 · 색칠한 것이다.',
             '원본: https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator', '',
             '레이어마다 아래 라이선스 가운데 하나를 고를 수 있다 (모두 상업적 이용 가능, 만든 사람 표기 필요; CC-BY-SA · GPL 은 같은 조건으로 나눔).', '']
    seen = set()
    for n in dict.fromkeys(used):
        for c in D.get(n, {}).get('credits', []):
            key = (c.get('file'), tuple(c.get('authors', [])))
            if key in seen:
                continue
            seen.add(key)
            lines.append('- `%s` — %s. 라이선스: %s. %s %s' % (c.get('file'), ', '.join(c.get('authors', [])), ', '.join(c.get('licenses', [])),
                                                       ' '.join(c.get('urls', [])), ('(' + c['notes'] + ')') if c.get('notes') else ''))
    if deco:
        lines += ['', '## 야영지: [LPC] Medieval Village Decorations (bluecarrot16 외)', '',
                  'https://opengameart.org/content/lpc-medieval-village-decorations — CC-BY-SA 3.0+. 원본 CREDITS 파일 전문:', '', '```',
                  open(os.path.join(deco, 'CREDITS-decorations-medieval.txt'), encoding='utf-8', errors='replace').read().strip(), '```']
    if con:
        lines += ['', '## 떨어진 금: [LPC] Containers (bluecarrot16 외)', '',
                  'https://opengameart.org/content/lpc-containers — CC-BY-SA 4.0. 원본 CREDITS 파일 전문:', '', '```',
                  open(os.path.join(con, 'container-v4_2', 'CREDITS-container.txt'), encoding='utf-8', errors='replace').read().strip(), '```']
    if mon:
        lines += ['', '## 웜퍼스: LPC Golem', '',
                  'https://opengameart.org/content/lpc-golem — CC-BY 3.0 / CC-BY 4.0 / GPL 2.0 / GPL 3.0 / OGA-BY 3.0.',
                  'Attribute Stephen "Redshrike" Challener as graphic artist and William.Thompsonj as contributor. (이끼 낀 초록색으로 다시 칠함)']
    if cav:
        lines += ['', '## 동굴 바닥 · 벽 · 금맥: LPC Cavern and Ruin Tiles (Tuomo Untinen 외)', '',
                  'https://opengameart.org/content/lpc-cavern-and-ruin-tiles — CC-BY-SA 3.0, GPL 2.0, GPL 3.0. 원본 credits.txt 전문:', '', '```',
                  open(os.path.join(cav, 'credits.txt'), encoding='utf-8', errors='replace').read().strip(), '```']
    if war:
        lines += ['', '## 모험가: 4 Direction Animated Warrior (Calciumtrice)', '',
                  'https://opengameart.org/content/4-direction-animated-warrior — CC-BY 4.0.',
                  'Animated Warrior by Calciumtrice, usable under Creative Commons Attribution 4.0 license. (목도리 · 겉옷을 팀 색으로, 머리를 금발로 다시 칠함)']
    if port:
        lines += ['', '## 초상화: 64px portraits (pebonius)', '',
                  'https://opengameart.org/content/64px-portraits — CC-BY 4.0. by peb / pebonius. (portrelf 를 금발 · 팀 색 망토로 다시 칠함)']
    open(os.path.join(OUT, 'CREDITS.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('ok', {k: (v['cols'], v['rows']) for k, v in meta['sheets'].items()}, 'credits', len(seen))


if __name__ == '__main__':
    main()
