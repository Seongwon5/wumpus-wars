"""연산 한도 (유닛마다 차례당 한도, 첫 차례는 넉넉히) · 허용 모듈 · 시간 안전망 시험."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wumpus.engine import Game  # noqa: E402
from wumpus.maps import load_map  # noqa: E402
from wumpus.api import OPS_TURN, OPS_FIRST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, 'maps', 'temple_gate.json')


def src(name):
    return open(os.path.join(ROOT, 'bots', name, 'main.py'), encoding='utf-8').read()


IDLE = "def turn(me, view, memory):\n    return None\n"       # 상대 자리를 채우는 봇 (아무것도 안 한다)


def play(a, b, rounds=None, ops=True, time_limit=None):
    from wumpus import engine
    old = engine.MAX_ROUNDS
    if rounds:
        engine.MAX_ROUNDS = rounds
    try:
        return Game(load_map(MAP), [a, b], ['a', 'b'], seed=1, ops_limit=ops, time_limit_ms=time_limit).play()
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
        rep = play(INFINITE, IDLE, rounds=30)
        errs = errors(rep)
        self.assertTrue(errs and all('연산 한도 초과' in e[2] for e in errs))
        self.assertEqual(rep['meta']['rounds'], 30)            # 경기는 끝까지 돈다
        self.assertGreater(rep['meta']['ops'][0]['over'], 0)
        self.assertLessEqual(rep['meta']['ops'][0]['max'], OPS_TURN + 1)

    def test_bare_except_cannot_escape(self):
        rep = play(SWALLOW, IDLE, rounds=10)
        self.assertGreater(rep['meta']['ops'][0]['over'], 0)
        self.assertEqual(rep['meta']['rounds'], 10)

    def test_same_game_with_or_without_meter(self):
        on = play(src('starter'), IDLE, rounds=200)
        off = play(src('starter'), IDLE, rounds=200, ops=False)
        self.assertEqual(on['meta']['score'], off['meta']['score'])
        self.assertEqual([f['u'] for f in on['frames']], [f['u'] for f in off['frames']])
        self.assertEqual(on['meta']['ops'][0]['over'], 0)
        self.assertIsNone(off['meta']['ops'])

    def test_ops_left_decreases(self):
        rep = play(PROBE, IDLE, rounds=5)
        msg = [e[2] for e in errors(rep) if 'ValueError' in e[2]][0]
        a, b = map(int, msg.split(': ')[1].split())
        self.assertGreater(a, b)
        self.assertGreaterEqual(a - b, 50)                    # 반복 50번은 적어도 50줄
        self.assertLessEqual(a, OPS_TURN)                     # 세 번째 차례: 첫 차례 몫은 이미 끝났다

    def test_starter_fits_budget(self):
        rep = play(src('starter'), src('starter'), rounds=300)
        self.assertEqual(rep['meta']['ops'][0]['over'], 0)
        self.assertEqual(rep['meta']['ops'][1]['over'], 0)


    def test_one_line_loops_are_counted(self):
        # 한 줄에 몰아 쓴 반복도 도는 만큼 센다 (줄만 세면 공짜가 된다)
        for body in ("for i in range(40000): pass", "i = 0\n    while i < 40000: i += 1", "a = [i for i in range(40000)]",
                     "a = sum(i for i in range(40000))", "a = list(map(lambda i: i, range(40000)))"):
            bot = "n = [0]\ndef turn(me, view, memory):\n    n[0] += 1\n    if n[0] < 2:\n        return None\n    " + body + "\n"
            rep = play(bot, IDLE, rounds=4)
            self.assertGreater(rep['meta']['ops'][0]['over'], 0, body)

    def test_first_turn_is_generous_and_nothing_accumulates(self):
        # 첫 차례 (불러오기 + 첫 turn) 는 OPS_FIRST 까지, 그 뒤로는 쉬어도 쌓이지 않고 늘 OPS_TURN
        bot = ("table = [i for i in range(60000)]\n"
               "n = [0]\n"
               "def turn(me, view, memory):\n"
               "    n[0] += 1\n"
               "    if n[0] == 1 or n[0] == 30:\n"
               "        for i in range(20000):\n"
               "            pass\n"
               "    return None\n")
        rep = play(bot, IDLE, rounds=3)
        self.assertEqual(rep['meta']['ops'][0]['over'], 0)          # 불러오기 6만 + 첫 차례 6만 < 20만
        rep = play(bot, IDLE, rounds=40)
        self.assertGreater(rep['meta']['ops'][0]['over'], 0)        # 29 차례를 쉬었어도 30번째의 6만은 넘는다
        self.assertGreater(OPS_FIRST, OPS_TURN)

    def test_only_allowed_modules_and_no_exec(self):
        for line, word in (("import os", "모듈"), ("import numpy", "모듈"), ("exec('x = 1')", "exec"), ("open('x')", "open")):
            rep = play(line + "\ndef turn(me, view, memory):\n    return None\n", IDLE, rounds=2)
            bad = rep['meta']['rejected'][0]                    # 코드 검사에 걸려 경기 없이 진다
            self.assertTrue(bad and word in bad[0], (line, bad[:1]))
            self.assertEqual(rep['meta']['winner'], 1)
        rep = play("e = exec\ne('x = 1')\ndef turn(me, view, memory):\n    return None\n", IDLE, rounds=2)
        self.assertIn('NameError', errors(rep)[0][2])           # 검사를 비껴가도 내장 함수에 없다
        ok = "import math, heapq, random\nfrom collections import deque\nfrom wumpus.api import Move\ndef turn(me, view, memory):\n    return None\n"
        self.assertEqual(errors(play(ok, IDLE, rounds=2)), [])

    def test_time_safety_net(self):
        # 내장 함수에 큰 일을 시키면 연산으로는 조금만 세지만, 시간 안전망이 그 차례를 버린다
        bot = "def turn(me, view, memory):\n    sum(range(3 * 10**6))\n    return None\n"
        rep = play(bot, IDLE, rounds=3, time_limit=5)
        self.assertTrue(any('시간 초과' in e[2] for e in errors(rep)))
        self.assertGreater(rep['meta']['time_ms'][0]['over'], 0)


if __name__ == '__main__':
    unittest.main()
