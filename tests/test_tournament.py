"""토너먼트: 더블 일리미네이션 대진표 · 시드 · 스위스 짝짓기 · 작은 토너먼트를 끝까지."""
import collections
import json
import os
import random
import shutil
import tempfile
import unittest
import zipfile

from wumpus import tournament as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def play_random(n, seed):
    B = T.build_bracket(n)
    T._mark_structural_byes(B, n)
    T._layout(B)
    seeds = list(range(n))
    rng = random.Random(seed)
    losses = collections.Counter()
    played = 0
    while True:
        ready = T._resolve(B, seeds)
        if not ready:
            break
        for mid in ready:
            m = B['matches'][mid]
            a, b = m['teams']
            assert m['shown'], mid
            assert losses[a] < 2 and losses[b] < 2
            w = a if rng.random() < .5 else b
            m.update(winner=w, loser=b if w == a else a)
            losses[m['loser']] += 1
            played += 1
    return B, losses, played


class Bracket(unittest.TestCase):
    def test_everyone_out_after_two_losses(self):
        for n in (2, 3, 5, 8, 13, 16, 31, 73):
            for s in range(10):
                B, losses, played = play_random(n, s)
                self.assertIn('winner', B['matches']['GF2'])
                alive = [t for t in range(n) if losses[t] < 2]
                self.assertEqual(len(alive), 1, (n, s))
                self.assertEqual(B['matches']['GF2']['winner'], alive[0])
                self.assertIn(played, (2 * n - 2, 2 * n - 1))     # 결승 리셋이 있으면 한 경기 더

    def test_top_seeds_get_byes(self):
        n = 73
        B = T.build_bracket(n)
        T._mark_structural_byes(B, n)
        self.assertEqual(B['size'], 128)
        bye_seeds = set()
        for mid in B['wb'][0]:
            m = B['matches'][mid]
            a, b = m['src'][0]['seed'], m['src'][1]['seed']
            if not m['shown']:
                bye_seeds.add(min(a, b))
        self.assertEqual(bye_seeds, set(range(1, 128 - n + 1)))    # 예선 1~55위가 부전승

    def test_seed_one_and_two_meet_only_in_final(self):
        pos = T._seed_positions(16)
        self.assertEqual(pos[:2], [1, 16])
        self.assertLess(pos.index(1), 8)
        self.assertGreaterEqual(pos.index(2), 8)


class Swiss(unittest.TestCase):
    def test_pairs_without_rematch(self):
        cfg = {'teams': [{'id': i, 'name': str(i)} for i in range(9)], 'maps': [{}] * 3, 'seed': 1}
        st = {'games': {}, 'swiss': []}
        met = set()
        rng = random.Random(3)
        for r in range(4):
            rnd = T._swiss_pair(cfg, st, r)
            self.assertEqual(sum(1 for p in rnd if p['b'] is None), 1)   # 홀수: 부전승 하나
            for p in rnd:
                if p['b'] is None:
                    continue
                key = frozenset((p['a'], p['b']))
                self.assertNotIn(key, met)
                met.add(key)
                for gid in p['games']:
                    st['games'][gid]['res'] = {'winner': rng.choice([0, 1, -1]), 'score': [1, 1], 'rounds': 1, 'reason': ''}
            st['swiss'].append(rnd)
        table, _, byes = T._swiss_table(cfg, st)
        self.assertEqual(sorted(r['team'] for r in table), list(range(9)))
        self.assertTrue(all(b <= 1 for b in byes))


class EndToEnd(unittest.TestCase):
    def test_small_tournament(self):
        tmp = tempfile.mkdtemp(prefix='wwt_')
        try:
            bots = os.path.join(tmp, 'bots')
            for nm in ('kim', 'lee', 'park'):
                os.makedirs(os.path.join(bots, nm))
                shutil.copyfile(os.path.join(ROOT, 'bots', 'starter', 'main.py'), os.path.join(bots, nm, 'main.py'))
            tdir = os.path.join(tmp, 't')
            cfg = T.create(tdir, bots, name='작은 대회', n_maps=1, swiss_rounds=1, seed=5)
            self.assertEqual(len(os.listdir(os.path.join(tdir, 'maps'))), 1)
            r = T.Runner(tdir, jobs=4, log=None)
            r.run()
            self.assertEqual(r.st['phase'], 'done')
            self.assertIn(r.st['champion'], (0, 1, 2))
            for gid, g in r.st['games'].items():
                self.assertIn('res', g)
                self.assertTrue(os.path.isfile(os.path.join(tdir, 'replays', gid + '.js')))
            out = T.pack(tdir, hide='GF')
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
            self.assertIn('작은 대회/index.html', names)
            self.assertIn('작은 대회/viewer.html', names)
            self.assertFalse(any('/bots/' in n for n in names))         # 학생 코드는 넣지 않는다
            d = T._read_data(tdir)
            self.assertEqual(d['hide'], 'GF')
            self.assertEqual(len(d['config']['teams']), 3)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
