"""내장 함수 · 연산자도 한 일만큼 센다 (엔진 1.1.0).

ops.py 는 봇이 실행한 줄 · 반복 · 함수 호출을 센다. 그런데 `sum(xs)` · `sorted(xs)` · `set_a - set_b` · `x in 리스트`
처럼 C 로 짠 내장 기능 안에서 도는 일은 줄 하나로만 세어져서, 직접 짠 반복보다 수천 배 싸게 같은 일을 할 수 있었다.

그래서 봇 코드를 코드 검사 (guard) 뒤에 조금 바꿔 쓴다. 무거울 수 있는 곳만 아래 도우미를 거치게 하고,
도우미는 다루는 원소 수만큼 연산을 더한 뒤 원래 일을 그대로 한다 (결과 · 예외는 바꾸지 않는다).

- 내장 함수:  sum min max any all list tuple set frozenset dict sorted, heapq 의 heapify nlargest nsmallest
              → 원소 수 (sorted 는 n · log2 n). 길이를 모르는 반복자 (map · filter · zip · itertools ...) 는 꺼낼 때마다 1.
- 메서드:     list.sort (n log n), index · count · copy · remove · insert · extend, set 의 union · difference ...,
              dict.update, str.join · split · replace · find ... → 다루는 원소 수.
- 연산자:     `in` (리스트 · 튜플 · 문자열은 길이, 집합 · 사전은 1), 컨테이너 · 문자열의 + - * | & ^ → 원소 수,
              슬라이스 `xs[a:b]` → 잘라 낸 길이. 숫자끼리의 연산은 비용을 더하지 않는다.
- 비용은 **일을 하기 전에** 더한다. 그래서 `[0] * 10**9` 같은 코드는 메모리를 쓰기 전에 한도에서 끊긴다.

도우미 이름은 밑줄 두 개로 시작하므로 봇은 쓰거나 덮어쓸 수 없다 (guard 가 막는다).
남는 틈: 내장 함수를 다른 이름에 담아 부르기 (`s = sorted; s(xs)`), `functools.reduce(operator.add, xs)` 처럼
C 함수끼리만 도는 반복. 이런 곳은 시간 안전망이 막는다.
"""
import ast
import heapq
import math
import operator
import types
from collections import deque

from .ops import meter

# ---------------------------------------------------------------- 비용 매기기
_SIZED = (list, tuple, set, frozenset, dict, str, bytes, bytearray, deque, range,
          type({}.keys()), type({}.values()), type({}.items()))
_NUM = (int, float, bool, complex)


def _charge(n):
    m = meter()
    if m.active and n > 0:
        m.count += n
        if m.count > m.limit:
            from .ops import OpsExceeded
            raise OpsExceeded()


def _n(x):
    """원소 수 (길이를 모르면 0)."""
    if isinstance(x, _SIZED):
        return len(x)
    return 0


def _nlogn(n):
    return n * max(1, math.ceil(math.log2(n + 1)))


def _counted(it):
    for v in it:
        _charge(1)
        yield v


def _feed(x):
    """함수에 넘길 반복 가능한 것: 길이를 알면 그만큼 미리 더하고 그대로, 모르면 꺼낼 때마다 1 씩 세는 것으로 감싼다.
    봇이 짠 제너레이터는 이미 재개될 때마다 세어지므로 감싸지 않는다."""
    if isinstance(x, _SIZED):
        _charge(len(x))
        return x
    if isinstance(x, (types.GeneratorType,) + _NUM) or x is None:
        return x
    try:
        it = iter(x)
    except TypeError:
        return x
    return _counted(it)


# 이름으로 부르는 내장 함수 (봇이 같은 이름을 다시 만들었으면 그 함수는 그냥 부른다)
_FEED_FIRST = {id(f): f for f in (sum, min, max, any, all, list, tuple, set, frozenset, dict, heapq.heapify)}
CALL_NAMES = frozenset(('sum', 'min', 'max', 'any', 'all', 'list', 'tuple', 'set', 'frozenset', 'dict', 'sorted',
                        'heapify', 'nlargest', 'nsmallest'))


def ww_call(fn, *args, **kw):
    fid = id(fn)
    if fid in _FEED_FIRST and _FEED_FIRST[fid] is fn and args:
        if fn in (min, max) and len(args) > 1:          # max(a, b) 같은 꼴: 원소 수 = 인자 수
            _charge(len(args))
            return fn(*args, **kw)
        return fn(_feed(args[0]), *args[1:], **kw)
    if fn is sorted and args:
        xs = list(_feed(args[0]))
        _charge(_nlogn(len(xs)))
        return sorted(xs, *args[1:], **kw)
    if fn in (heapq.nlargest, heapq.nsmallest) and len(args) > 1:
        return fn(args[0], _feed(args[1]), *args[2:], **kw)
    return fn(*args, **kw)


# 메서드: 받는 쪽 (receiver) 이 내장 컨테이너 · 문자열 · 허용 모듈일 때만 센다. 봇이 만든 클래스의 같은 이름 메서드는 그냥 부른다
_SELF_N = frozenset(('index', 'count', 'copy', 'remove', 'insert', 'reverse', 'rotate',
                     'split', 'rsplit', 'splitlines', 'replace', 'find', 'rfind', 'rindex', 'strip', 'lstrip', 'rstrip',
                     'lower', 'upper', 'startswith', 'endswith', 'encode', 'translate', 'partition', 'rpartition',
                     'values', 'elements', 'total'))
_ARGS_N = frozenset(('extend', 'extendleft', 'update', 'join', 'fromkeys', 'subtract'))
_BOTH_N = frozenset(('union', 'intersection', 'difference', 'symmetric_difference', 'intersection_update',
                     'difference_update', 'symmetric_difference_update', 'issubset', 'issuperset', 'isdisjoint'))
_HEAP_LOG = frozenset(('heappush', 'heappop', 'heappushpop', 'heapreplace', 'bisect', 'bisect_left', 'bisect_right',
                       'insort', 'insort_left', 'insort_right'))
METHOD_NAMES = (_SELF_N | _ARGS_N | _BOTH_N | _HEAP_LOG
                | frozenset(('sort', 'most_common', 'heapify', 'nlargest', 'nsmallest')))
_RECV = (list, tuple, set, frozenset, dict, str, bytes, bytearray, deque)


def ww_meth(obj, name, *args, **kw):
    f = getattr(obj, name)
    if isinstance(obj, types.ModuleType):               # heapq · bisect (봇이 받은 복사본 모듈)
        if name in ('heapify',) and args:
            _charge(_n(args[0]))
        elif name in ('nlargest', 'nsmallest') and len(args) > 1:
            args = (args[0], _feed(args[1])) + args[2:]
        elif name in _HEAP_LOG and args:
            _charge(1 + math.ceil(math.log2(_n(args[0]) + 1)))
        return f(*args, **kw)
    if not isinstance(obj, _RECV):
        return f(*args, **kw)
    if name == 'sort' or name == 'most_common':
        _charge(_nlogn(_n(obj)))
    elif name in _SELF_N:
        _charge(_n(obj))
    elif name in _ARGS_N:
        args = tuple(_feed(a) for a in args)
        if kw:
            _charge(len(kw))
    elif name in _BOTH_N:
        _charge(_n(obj))
        args = tuple(_feed(a) for a in args)
    return f(*args, **kw)


def _bin_cost(op, a, b):
    if isinstance(a, _NUM) and isinstance(b, _NUM):
        return 0
    if op in (operator.mul, operator.imul):              # [0] * n, 'ab' * n: 결과 길이
        if isinstance(a, int) and not isinstance(a, bool):
            return _n(b) * max(a, 0)
        if isinstance(b, int) and not isinstance(b, bool):
            return _n(a) * max(b, 0)
    return _n(a) + _n(b)


def ww_bin(op, a, b):
    if not (isinstance(a, _NUM) and isinstance(b, _NUM)):
        _charge(_bin_cost(op, a, b))
    return op(a, b)


def ww_in(a, b):
    if isinstance(b, (list, tuple, str, bytes, bytearray, deque, type({}.values()))):
        _charge(len(b))
    return a in b


def ww_slice(x, lo, hi, st):
    r = x[lo:hi:st] if st is not None else x[lo:hi]
    _charge(_n(r))
    return r


HELPERS = {'__ww_call__': ww_call, '__ww_meth__': ww_meth, '__ww_bin__': ww_bin, '__ww_in__': ww_in,
           '__ww_slice__': ww_slice, '__ww_op__': operator}

# ---------------------------------------------------------------- 봇 코드 바꿔 쓰기
_BINOPS = {ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul', ast.BitOr: 'or_', ast.BitAnd: 'and_', ast.BitXor: 'xor'}
_IBINOPS = {ast.Add: 'iadd', ast.Sub: 'isub', ast.Mult: 'imul', ast.BitOr: 'ior', ast.BitAnd: 'iand', ast.BitXor: 'ixor'}


def _name(n):
    return ast.Name(n, ast.Load())


def _op(name):
    return ast.Attribute(_name('__ww_op__'), name, ast.Load())


class _Rewrite(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)
        f = node.func
        if isinstance(f, ast.Name) and f.id in CALL_NAMES:
            new = ast.Call(_name('__ww_call__'), [f] + node.args, node.keywords)
            return ast.copy_location(new, node)
        if isinstance(f, ast.Attribute) and f.attr in METHOD_NAMES:
            new = ast.Call(_name('__ww_meth__'), [f.value, ast.Constant(f.attr)] + node.args, node.keywords)
            return ast.copy_location(new, node)
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) == 1 and isinstance(node.ops[0], (ast.In, ast.NotIn)):
            new = ast.Call(_name('__ww_in__'), [node.left, node.comparators[0]], [])
            if isinstance(node.ops[0], ast.NotIn):
                new = ast.UnaryOp(ast.Not(), new)
            return ast.copy_location(new, node)
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        name = _BINOPS.get(type(node.op))
        if name is None:
            return node
        return ast.copy_location(ast.Call(_name('__ww_bin__'), [_op(name), node.left, node.right], []), node)

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        name = _IBINOPS.get(type(node.op))
        if name is None or not isinstance(node.target, ast.Name):   # xs[i] += 1 같은 꼴은 그대로 (대상을 두 번 평가하지 않게)
            return node
        val = ast.Call(_name('__ww_bin__'), [_op(name), _name(node.target.id), node.value], [])
        return ast.copy_location(ast.Assign([ast.Name(node.target.id, ast.Store())], val), node)

    def visit_Subscript(self, node):
        self.generic_visit(node)
        if isinstance(node.ctx, ast.Load) and isinstance(node.slice, ast.Slice):
            s = node.slice
            parts = [p if p is not None else ast.Constant(None) for p in (s.lower, s.upper, s.step)]
            return ast.copy_location(ast.Call(_name('__ww_slice__'), [node.value] + parts, []), node)
        return node


def rewrite(source, filename):
    """검사를 마친 봇 소스를 비용을 세는 모양으로 바꿔 컴파일한다. 줄 번호는 그대로다."""
    tree = _Rewrite().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return compile(tree, filename, 'exec')
