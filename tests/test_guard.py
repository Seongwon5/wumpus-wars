"""제출 코드 검사 (guard) 와 엔진의 가두기 시험: 봇이 엔진 속 · 상대 봇 · 다음 판에 닿지 못해야 한다."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wumpus import api, engine, guard  # noqa: E402
from wumpus.engine import Game  # noqa: E402
from wumpus.maps import load_map  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, 'maps', 'temple_gate.json')
IDLE = "def turn(me, view, memory):\n    return None\n"


def play(a, b=IDLE, rounds=6):
    old = engine.MAX_ROUNDS
    engine.MAX_ROUNDS = rounds
    try:
        g = Game(load_map(MAP), [a, b], ['a', 'b'], seed=1)
        return g, g.play()
    finally:
        engine.MAX_ROUNDS = old


def errors(rep):
    return [e[2] for f in rep['frames'] for e in f['e'] if e[0] == 'err']


def bot(body, head=''):
    return head + "def turn(me, view, memory):\n" + ''.join('    ' + ln + '\n' for ln in body.split('\n'))


class Guard(unittest.TestCase):
    def test_shipped_bots_pass(self):
        src = open(os.path.join(ROOT, 'bots', 'starter', 'main.py'), encoding='utf-8').read()
        self.assertEqual(guard.check(src), [])

    def test_rejects(self):
        bad = [
            "x = (1).__class__",
            "def turn(me, view, memory):\n    return view.__dict__",
            "y = __builtins__",
            "import os",
            "from . import x",
            "import wumpus.engine",
            "z = getattr(1, 'real')",
            "t = type(1)",
            "g = globals()",
            "def gen():\n    yield 1\nq = gen().gi_frame",
            "try:\n    1 / 0\nexcept Exception as e:\n    f = e.tb_frame",
            "s = '{0.x}'.format(1)",
            "class A:\n    pass\nm = A.mro()",
            "async def f():\n    pass",
            "class A:\n    def __del__(self):\n        pass",
            "match 1:\n    case int(__class__=c):\n        pass",
            "def f(:",
        ]
        for src in bad:
            self.assertTrue(guard.check(src), src)

    def test_allows_ordinary_code(self):
        ok = [
            "class K:\n    __slots__ = ('a', '_b')\n    def __init__(self):\n        self.a = 1\n        self._b = 2\n    def __lt__(self, o):\n        return self.a < o.a\n",
            "import heapq\nfrom collections import deque, namedtuple\nP = namedtuple('P', 'x y')\np = P(1, 2)._replace(x=3)\n",
            "dir = 'N'\ntype = 3\ndef input(x):\n    return x\nv = input(type)\n",
            "f_score = {}\ns = f'{1 + 1} {\"a\"!r}'\nt = '%d' % 3\n",
            "def gen():\n    yield 1\nxs = list(gen())\n",
        ]
        for src in ok:
            self.assertEqual(guard.check(src), [], src)

    def test_rejected_bot_forfeits_without_running(self):
        g, rep = play("import os\nraise SystemError('ran')\n" + IDLE)
        self.assertEqual(rep['meta']['winner'], 1)
        self.assertIn('실격', rep['meta']['reason'])
        self.assertTrue(rep['meta']['rejected'][0])
        self.assertEqual(errors(rep), [])               # 코드를 실행하지 않았다
        g, rep = play("import os\n" + IDLE, "import sys\n" + IDLE)
        self.assertEqual(rep['meta']['winner'], -1)


class Isolation(unittest.TestCase):
    def test_view_holds_no_game(self):
        g, rep = play(IDLE)
        v = engine.View(g, g.units[0])
        for val in vars(v).values():
            self.assertNotIsInstance(val, (Game, engine.Unit))
        self.assertFalse(hasattr(v, '_g'))

    def test_engine_tables_are_copies(self):
        src = ("from wumpus.api import DIRS, COST, HP, RULES\n"
               "DIRS['N'] = (0, -5)\nCOST['explorer'] = 0\nHP['camp'] = 1\nRULES['agent'] = False\n" + IDLE)
        before = (dict(api.DIRS), dict(api.COST), dict(api.HP), dict(api.RULES))
        g, rep = play(src)
        self.assertEqual(errors(rep), [])
        self.assertEqual((api.DIRS, api.COST, api.HP, api.RULES), before)

    def test_classes_are_frozen(self):
        src = "from wumpus.api import Move\ndef turn(me, view, memory):\n    Move.d = 'N'\n"
        g, rep = play(src, rounds=2)
        self.assertTrue(all('TypeError' in e for e in errors(rep)) and errors(rep))
        self.assertEqual(api.Move('E').d, 'E')
        with self.assertRaises(TypeError):
            engine.View.tile = None
        with self.assertRaises(AttributeError):
            api.debug.extra = 1

    def test_modules_are_per_unit(self):
        src = ("import math, collections, heapq\n"
               "math.shared = 1\ncollections.Counter.shared = 1\nheapq.merge.shared = 1\n" + IDLE)
        import collections
        import heapq
        import math
        g, rep = play(src)
        self.assertEqual(errors(rep), [])
        self.assertFalse(hasattr(math, 'shared'))
        self.assertFalse(hasattr(collections.Counter, 'shared'))
        self.assertFalse(hasattr(heapq.merge, 'shared'))

    def test_builtins_are_per_unit_and_trimmed(self):
        seen = {}
        orig = engine._make_importer

        def spy():
            f = orig()
            seen.setdefault('n', 0)
            seen['n'] += 1
            return f
        engine._make_importer = spy
        try:
            g, rep = play(IDLE)
        finally:
            engine._make_importer = orig
        bs = [u.ns['__builtins__'] for u in g.bases + g.units]
        self.assertEqual(len({id(b) for b in bs}), len(bs))      # 유닛마다 다른 사전
        for name in api.BLOCKED_BUILTINS + ('SystemExit', 'KeyboardInterrupt', 'memoryview', 'license'):
            self.assertNotIn(name, bs[0])

    def test_removed_tools_are_missing(self):
        src = ("import operator, functools, random\n"
               "names = [n for m in (operator, functools, random) for n in ('attrgetter', 'methodcaller', 'update_wrapper', 'wraps', 'SystemRandom') if hasattr(m, n)]\n"
               "def turn(me, view, memory):\n    raise ValueError(','.join(names) or 'none')\n")
        g, rep = play(src, rounds=1)
        self.assertEqual(set(errors(rep)), {'ValueError: none'})

    def test_useful_tools_still_work(self):
        src = ("import math, heapq, itertools, functools, random, bisect, operator, copy\n"
               "from collections import deque, defaultdict, Counter, namedtuple, OrderedDict\n"
               "from wumpus.api import *\n"
               "import wumpus.api as wa\n"
               "P = namedtuple('P', 'x y')\n"
               "@functools.lru_cache(maxsize=None)\n"
               "def sq(n):\n    return n * n\n"
               "def turn(me, view, memory):\n"
               "    h = []\n    heapq.heappush(h, (2, 'b'))\n    heapq.heappush(h, (1, 'a'))\n"
               "    c = Counter('aab')\n    d = deque([1, 2])\n    d.appendleft(0)\n"
               "    k = sorted([(2, 1), (1, 2)], key=operator.itemgetter(1))\n"
               "    r = random.Random(3).randint(1, 6) + random.randint(1, 6)\n"
               "    z = copy.deepcopy({'a': [1]})\n"
               "    ok = (heapq.heappop(h)[1] == 'a' and c['a'] == 2 and d[0] == 0 and k[0] == (2, 1) and sq(3) == 9\n"
               "          and math.floor(2.5) == 2 and bisect.bisect([1, 3], 2) == 1 and list(itertools.islice(itertools.count(), 2)) == [0, 1]\n"
               "          and functools.reduce(operator.add, [1, 2]) == 3 and P(1, 2).y == 2 and cheb(0, 0, 2, 1) == 2\n"
               "          and wa.DIRS['N'] == (0, -1) and isinstance(Move('N'), Move) and ops_left() > 0 and z == {'a': [1]})\n"
               "    raise ValueError('ok' if ok else 'broken')\n")
        g, rep = play(src, rounds=1)
        self.assertEqual(set(errors(rep)), {'ValueError: ok'})


class StrictReturn(unittest.TestCase):
    def test_bot_objects_are_not_called_by_engine(self):
        head = ("from wumpus.api import Move\n"
                "hits = []\n"
                "class D(str):\n"
                "    def __hash__(self):\n        hits.append('hash')\n        return 1\n"
                "    def __eq__(self, o):\n        hits.append('eq')\n        return True\n"
                "class N:\n"
                "    def __int__(self):\n        hits.append('int')\n        return 7\n"
                "    def __index__(self):\n        hits.append('index')\n        return 7\n"
                "class M(Move):\n    pass\n"
                "class E(Exception):\n"
                "    def __str__(self):\n        hits.append('str')\n        return 'x'\n")
        body = ("if hits:\n    raise ValueError('called ' + hits[0])\n"
                "memory[0] = N()\nmemory[1] = 5\n"
                "if me.round == 1:\n    return Move(D('N'))\n"
                "if me.round == 2:\n    return M('N')\n"
                "if me.round == 3:\n    return (Move(['N']),)\n"
                "if me.round == 4:\n    raise E()\n"
                "return 3")
        g, rep = play(bot(body, head), rounds=6)
        errs = errors(rep)
        self.assertFalse([e for e in errs if 'called' in e], errs)
        self.assertTrue(errs and all(e == 'E' for e in errs), errs)       # 4라운드의 예외만, 글은 클래스 이름뿐
        self.assertEqual(g.memory[0][:2], [0, 5])
        self.assertEqual(rep['meta']['rounds'], 6)

    def test_base_exception_does_not_stop_the_match(self):
        g, rep = play(bot("raise BaseException('boom')"), rounds=3)
        self.assertEqual(rep['meta']['rounds'], 3)
        self.assertTrue(errors(rep))

    def test_debug_marks_are_sanitized(self):
        import json
        head = "from wumpus.api import debug\nclass X:\n    pass\n"
        body = "debug.mark(1, 2, 'red')\ndebug.marks.append([X(), 1, 'red'])\ndebug.texts = [X(), 'hi']\ndebug.lines = X()"
        g, rep = play(bot(body, head), rounds=2)
        json.dumps(rep)
        d = [f['d'] for f in rep['frames'] if 'd' in f]
        self.assertTrue(d)
        for fr in d:
            for v in fr.values():
                self.assertEqual(v.get('m'), [[1, 2, 'red']])
                self.assertEqual(v.get('t'), ['hi'])
                self.assertNotIn('l', v)


class Runner(unittest.TestCase):
    def test_hung_game_is_killed_and_blamed(self):
        from wumpus import cli
        import tempfile
        d = tempfile.mkdtemp(prefix='ww_guard_')
        hang = os.path.join(d, 'hang.py')
        with open(hang, 'w', encoding='utf-8') as f:     # 연산으로 세지 않는 내장 함수 안에서 끝나지 않는 일
            f.write("import itertools\ndef turn(me, view, memory):\n    if me.team == 1:\n        return sum(itertools.count())\n")
        idle = os.path.join(d, 'idle.py')
        with open(idle, 'w', encoding='utf-8') as f:
            f.write(IDLE)
        tasks = [([idle, hang], MAP, 1, 0, None, None, True), ([idle, idle], MAP, 1, 0, None, None, True)]
        old = engine.MAX_ROUNDS
        res = cli._run_games(tasks, 2, 8)
        self.assertEqual(res[0]['winner'], 0)
        self.assertIn('실격', res[0]['reason'])
        self.assertEqual(res[1]['winner'], -1)           # 멀쩡한 판은 끝까지 돈다
        self.assertEqual(engine.MAX_ROUNDS, old)


if __name__ == '__main__':
    unittest.main()
