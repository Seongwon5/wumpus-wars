"""연산 한도 (봇 코드 실행 줄 수) 시험."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wumpus.engine import Game  # noqa: E402
from wumpus.maps import load_map  # noqa: E402
from wumpus.api import OPS_TURN_MAX, OPS_TURN_MIN  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, 'maps', 'temple_gate.json')


def src(name):
    return open(os.path.join(ROOT, 'bots', name, 'main.py'), encoding='utf-8').read()


def play(a, b, rounds=None, ops=True):
    from wumpus import engine
    old = engine.MAX_ROUNDS
    if rounds:
        engine.MAX_ROUNDS = rounds
    try:
        return Game(load_map(MAP), [a, b], ['a', 'b'], seed=1, ops_limit=ops).play()
    finally:
        engine.MAX_ROUNDS = old


def errors(rep, team_ids=None):
    return [e for f in rep['frames'] for e in f['e'] if e[0] == 'err']


INFINITE = "def turn(me, view, memory):\n    while True:\n        pass\n"
SWALLOW = ("def turn(me, view, memory):\n"
           "    while True:\n"
           "        try:\n"
           "            while True:\n"
           "                pass\n"
           "        except:\n"
           "            pass\n")
PROBE = ("from wumpus.api import ops_left\n"
         "seen = []\n"
         "def turn(me, view, memory):\n"
         "    a = ops_left()\n"
         "    for i in range(50):\n"
         "        pass\n"
         "    b = ops_left()\n"
         "    seen.append((a, b))\n"
         "    if len(seen) == 3:\n"
         "        raise ValueError('%d %d' % seen[-1])\n"
         "    return None\n")


class Ops(unittest.TestCase):
    def test_infinite_loop_is_cut(self):
        rep = play(INFINITE, src('random'), rounds=30)
        errs = errors(rep)
        self.assertTrue(errs and all('연산 한도 초과' in e[2] for e in errs))
        self.assertEqual(rep['meta']['rounds'], 30)            # 경기는 끝까지 돈다
        self.assertGreater(rep['meta']['ops'][0]['over'], 0)
        self.assertLessEqual(rep['meta']['ops'][0]['max'], OPS_TURN_MAX + 1)

    def test_bare_except_cannot_escape(self):
        rep = play(SWALLOW, src('random'), rounds=10)
        self.assertGreater(rep['meta']['ops'][0]['over'], 0)
        self.assertEqual(rep['meta']['rounds'], 10)

    def test_same_game_with_or_without_meter(self):
        on = play(src('starter'), src('random'), rounds=200)
        off = play(src('starter'), src('random'), rounds=200, ops=False)
        self.assertEqual(on['meta']['score'], off['meta']['score'])
        self.assertEqual([f['u'] for f in on['frames']], [f['u'] for f in off['frames']])
        self.assertEqual(on['meta']['ops'][0]['over'], 0)
        self.assertIsNone(off['meta']['ops'])

    def test_ops_left_decreases(self):
        rep = play(PROBE, src('random'), rounds=5)
        msg = [e[2] for e in errors(rep) if 'ValueError' in e[2]][0]
        a, b = map(int, msg.split(': ')[1].split())
        self.assertGreater(a, b)
        self.assertGreaterEqual(a - b, 50)                    # 반복 50번은 적어도 50줄
        self.assertGreaterEqual(a, OPS_TURN_MIN)

    def test_example_bots_fit_budget(self):
        rep = play(src('logic'), src('starter'), rounds=300)
        self.assertEqual(rep['meta']['ops'][0]['over'], 0)
        self.assertEqual(rep['meta']['ops'][1]['over'], 0)


if __name__ == '__main__':
    unittest.main()
