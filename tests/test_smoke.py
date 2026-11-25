"""기본 점검: python -m unittest discover tests"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wumpus.engine import run_match, resolve_bot           # noqa: E402
from wumpus.maps import load_map, list_maps, generate       # noqa: E402
from wumpus import api                                      # noqa: E402


class Smoke(unittest.TestCase):
    def test_maps_load_and_are_symmetric(self):
        names = list_maps()
        self.assertGreaterEqual(len(names), 5)
        for n in names:
            g = load_map(n)
            for (x, y) in g.walls:
                self.assertIn(api.mirror(g.sym, x, y, g.w, g.h), g.walls)
            for (x, y) in g.traps:
                self.assertIn(api.mirror(g.sym, x, y, g.w, g.h), g.traps)
            self.assertEqual(tuple(g.bases[1]), api.mirror(g.sym, *g.bases[0], g.w, g.h))

    def test_bots_resolve(self):
        path, name = resolve_bot('starter')
        self.assertTrue(path.endswith('main.py'))
        self.assertEqual(name, 'starter')

    def test_deterministic(self):
        a = run_match(load_map('twin_pillars'), ['starter', 'starter'], seed=3)
        b = run_match(load_map('twin_pillars'), ['starter', 'starter'], seed=3)
        self.assertEqual(a['meta']['score'], b['meta']['score'])
        self.assertEqual(a['meta']['rounds'], b['meta']['rounds'])
        self.assertEqual(len(a['frames']), len(b['frames']))

    def test_starter_runs_without_errors(self):
        rep = run_match(load_map('scarab_maze'), ['starter', 'starter'], seed=1)
        errs = [e for fr in rep['frames'] for e in fr['e'] if e[0] == 'err']
        self.assertEqual(errs, [])
        self.assertLessEqual(rep['meta']['rounds'], api.MAX_ROUNDS)

    def test_starter_delivers_gold_on_generated_map(self):
        rep = run_match(generate(5), ['starter', 'starter'], seed=1)
        self.assertGreater(min(rep['meta']['score']), 0)


if __name__ == '__main__':
    unittest.main()
