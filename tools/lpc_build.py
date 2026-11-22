"""LPC (Liberated Pixel Cup) 레이어를 합성해 뷰어용 캐릭터 시트를 만든다.

python -X utf8 tools/lpc_build.py <LPC 저장소 폴더> [<decoration_medieval 폴더>]

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
    side = tile(2, 8)                                    # 회색 석벽 (벽돌)
    side.save(os.path.join(OUT, 'wall_side.png'))
    out['wall_side'] = {'cols': 1, 'rows': 1, 'cell': 32, 'tile': True}
    top = Image.eval(tile(11, 9).convert('RGB'), lambda v: min(255, int(v * 1.1))).convert('RGBA')   # 회색 판석 덮개
    top.save(os.path.join(OUT, 'wall_top.png'))
    out['wall_top'] = {'cols': 1, 'rows': 1, 'cell': 32, 'tile': True}
    tile(13, 3).save(os.path.join(OUT, 'pit.png'))      # 칸 하나짜리 낭떠러지 (금빛 테두리 · 갈색 절벽 · 검은 구멍)
    out['pit'] = {'cols': 1, 'rows': 1, 'cell': T, 'tile': True}
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


def defs(src):
    out = {}
    for f in glob.glob(os.path.join(src, 'sheet_definitions', '**', '*.json'), recursive=True):
        out[os.path.basename(f)] = json.load(open(f, encoding='utf-8'))
    return out


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
        meta['sheets']['archer_%d' % t] = build('archer_%d' % t, archer, 'shoot')
    wumpus = [
        L('body.json', 'body/bodies/muscular', 10, ramp='green'),
        L('heads_troll.json', 'head/heads/troll/adult', 100, ramp='green'),
    ]
    meta['sheets']['wumpus'] = build('wumpus', wumpus, 'slash')
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
    if mon:
        lines += ['', '## 웜퍼스: LPC Golem', '',
                  'https://opengameart.org/content/lpc-golem — CC-BY 3.0 / CC-BY 4.0 / GPL 2.0 / GPL 3.0 / OGA-BY 3.0.',
                  'Attribute Stephen "Redshrike" Challener as graphic artist and William.Thompsonj as contributor. (이끼 낀 초록색으로 다시 칠함)']
    if cav:
        lines += ['', '## 동굴 바닥 · 벽 · 금맥: LPC Cavern and Ruin Tiles (Tuomo Untinen 외)', '',
                  'https://opengameart.org/content/lpc-cavern-and-ruin-tiles — CC-BY-SA 3.0, GPL 2.0, GPL 3.0. 원본 credits.txt 전문:', '', '```',
                  open(os.path.join(cav, 'credits.txt'), encoding='utf-8', errors='replace').read().strip(), '```']
    open(os.path.join(OUT, 'CREDITS.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('ok', {k: (v['cols'], v['rows']) for k, v in meta['sheets'].items()}, 'credits', len(seen))


if __name__ == '__main__':
    main()
