"""맵: 대칭 맵 생성기 (같은 시드면 같은 맵) 와 맵 파일 (maps/*.json) 읽기 · 쓰기."""
import json
import os
import random
from collections import deque

from .api import mirror, cheb, SAFE_RADIUS, DIRS


MAP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'maps')


class GameMap:
    def __init__(self, w, h, sym, walls, ore, traps, bases, seed, name=None):
        self.w, self.h, self.sym = w, h, sym
        self.walls = walls          # set[(x,y)]
        self.ore = ore              # dict[(x,y)] -> 금 양
        self.traps = traps          # set[(x,y)] 구덩이
        self.bases = bases          # [(x,y) 붉은 원정대 야영지, (x,y) 푸른 원정대 야영지]
        self.seed = seed
        self.name = name or f'gen{seed}'

    def to_json(self):
        rows = [''.join('#' if (x, y) in self.walls else '.' for x in range(self.w)) for y in range(self.h)]
        return {
            'format': 'wumpus-map-1', 'name': self.name, 'w': self.w, 'h': self.h, 'sym': self.sym, 'seed': self.seed,
            'rows': rows,
            'gold': [[x, y, a] for (x, y), a in sorted(self.ore.items())],
            'pits': sorted([x, y] for x, y in self.traps),
            'camps': [list(c) for c in self.bases],
        }

    @staticmethod
    def from_json(d):
        walls = {(x, y) for y, row in enumerate(d['rows']) for x, ch in enumerate(row) if ch == '#'}
        return GameMap(d['w'], d['h'], d['sym'], walls, {(x, y): a for x, y, a in d['gold']},
                       {(x, y) for x, y in d['pits']}, [tuple(c) for c in d['camps']], d.get('seed', 0), d.get('name'))

    def ascii(self):
        """글자 그림: # 벽, G 금, P 구덩이, A/B 야영지, . 빈 칸."""
        out = []
        for y in range(self.h):
            row = ''
            for x in range(self.w):
                c = (x, y)
                row += ('A' if c == tuple(self.bases[0]) else 'B' if c == tuple(self.bases[1]) else
                        '#' if c in self.walls else 'P' if c in self.traps else 'G' if c in self.ore else '.')
            out.append(row)
        return '\n'.join(out)


def list_maps(map_dir=MAP_DIR):
    if not os.path.isdir(map_dir):
        return []
    return sorted(f[:-5] for f in os.listdir(map_dir) if f.endswith('.json'))


def load_map(spec, map_dir=MAP_DIR):
    """맵 이름 (maps/ 안), .json 경로, 또는 'gen:시드' (그 자리에서 생성)."""
    if isinstance(spec, GameMap):
        return spec
    spec = str(spec)
    if spec.startswith('gen:'):
        return generate(int(spec[4:]))
    path = spec if spec.endswith('.json') and os.path.exists(spec) else os.path.join(map_dir, spec + '.json')
    if not os.path.exists(path):
        raise FileNotFoundError(f'맵을 찾을 수 없다: {spec} (wumpus maps 로 목록을 본다)')
    with open(path, encoding='utf-8') as f:
        return GameMap.from_json(json.load(f))


def save_map(gmap, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(gmap.to_json(), f, ensure_ascii=False, indent=1)


def _reachable(w, h, start_cells, blocked):
    seen = set(start_cells)
    dq = deque(start_cells)
    while dq:
        x, y = dq.popleft()
        for dx, dy in DIRS.values():
            n = (x + dx, y + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in seen and n not in blocked:
                seen.add(n)
                dq.append(n)
    return seen


def generate(seed, w=None, h=None, sym=None, name=None):
    rng = random.Random(seed)
    for _ in range(500):
        W = w or rng.randint(20, 28)
        H = h or rng.randint(20, 28)
        S = sym or rng.choice('HVR')

        def m(c):
            return mirror(S, c[0], c[1], W, H)

        def inb(c):
            return 0 <= c[0] < W and 0 <= c[1] < H

        # 야영지: 네 귀퉁이 중 하나 근처. 세 대칭이 서로 다른 적 야영지 후보를 만들게 한다.
        corner = rng.randrange(4)
        bx, by = rng.randint(2, 4), rng.randint(2, 4)
        if corner & 1:
            bx = W - 1 - bx
        if corner & 2:
            by = H - 1 - by
        A = (bx, by)
        B = m(A)
        if cheb(*A, *B) < 10:
            continue

        def near_base(c, r):
            return cheb(*c, *A) <= r or cheb(*c, *B) <= r

        walls = set()
        for _ in range(rng.randint(W * H // 55, W * H // 35)):
            x, y = rng.randrange(W), rng.randrange(H)
            horiz = rng.random() < 0.5
            for i in range(rng.randint(2, 5)):
                c = (x + i, y) if horiz else (x, y + i)
                if inb(c) and not near_base(c, SAFE_RADIUS):
                    walls.add(c)
                    walls.add(m(c))

        ore = {}
        for _ in range(rng.randint(5, 8)):
            cx, cy = rng.randrange(W), rng.randrange(H)
            for _ in range(rng.randint(2, 4)):
                c = (cx + rng.randint(-1, 1), cy + rng.randint(-1, 1))
                if inb(c) and c not in walls and m(c) not in walls and not near_base(c, 3):
                    amt = rng.randint(8, 16)
                    ore[c] = amt
                    ore[m(c)] = amt

        traps = set()
        n_half = int(W * H * rng.uniform(0.035, 0.05) / 2)
        for _ in range(n_half):
            c = (rng.randrange(W), rng.randrange(H))
            if c in walls or c in ore or near_base(c, SAFE_RADIUS):
                continue
            traps.add(c)
            traps.add(m(c))

        # 검사: 두 야영지가 안전한 칸으로 이어지고, 금 대부분에 갈 수 있어야 한다.
        blocked = walls | traps | {A, B}
        starts = [(A[0] + dx, A[1] + dy) for dx, dy in DIRS.values()]
        starts = [c for c in starts if inb(c) and c not in blocked]
        reach = _reachable(W, H, starts, blocked)
        b_nbrs = {(B[0] + dx, B[1] + dy) for dx, dy in DIRS.values()}
        if not (reach & b_nbrs):
            continue
        if ore and sum(1 for c in ore if c in reach) < 0.8 * len(ore):
            continue
        return GameMap(W, H, S, walls, ore, traps, [A, B], seed, name)
    raise RuntimeError('맵 생성 실패')
