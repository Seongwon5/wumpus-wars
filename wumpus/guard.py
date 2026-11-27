"""제출 코드 검사. 봇 파일은 엔진에 실리기 전에 반드시 이 검사를 거친다 (engine.Game 이 부른다).

봇은 엔진과 같은 파이썬 안에서 돈다. 그래서 봇이 엔진 속 (숨은 구덩이 · 점수 · 상대 유닛) 이나 컴퓨터의
파일에 닿는 길을 코드 모양으로 미리 막는다. 걸리면 그 봇은 실격이다 (경기를 하지 않고 진다).

금지 목록 (check 가 돌려주는 글에 줄 번호와 함께 나온다):
- 밑줄 두 개로 시작하는 속성 · 이름 (`x.__class__`, `__builtins__` ...). 클래스 안의 `def __init__` 같은 메서드 정의는 된다.
- 실행 틀 · 제너레이터 속을 보는 속성 (`gi_frame`, `f_back`, `tb_frame` ...), `mro`, 문자열 `.format` · `.format_map`
  (글자 넣기는 f-string 이나 % 를 쓴다).
- `getattr` `setattr` `delattr` `vars` `globals` `locals` `type` `dir` `eval` `exec` `compile` `open` `input` 부르기.
  (같은 이름의 자기 변수 · 함수를 만들어 쓰는 것은 된다. 종류 확인은 isinstance 를 쓴다.)
- 허용 목록 (api.ALLOWED_IMPORTS) 밖의 import, 상대 import, `from wumpus import` 의 api 밖의 이름.
- async / await, `__del__` 정의.

이 검사만으로 완전하지는 않다. 엔진도 봇에게 복사본만 주고, 봇이 돌려준 값은 종류를 엄격히 본다 (engine.py).
"""
import ast

from .api import ALLOWED_IMPORTS

MAX_SOURCE = 500_000            # 봇 파일 크기 한도 (글자 수)

BANNED_ATTRS = frozenset((
    'gi_frame', 'gi_code', 'gi_yieldfrom', 'gi_running', 'gi_suspended',
    'cr_frame', 'cr_code', 'cr_await', 'cr_origin', 'cr_running', 'cr_suspended',
    'ag_frame', 'ag_code', 'ag_await', 'ag_running', 'ag_suspended',
    'f_back', 'f_globals', 'f_locals', 'f_builtins', 'f_code', 'f_trace', 'f_generator', 'f_lineno', 'f_lasti',
    'tb_frame', 'tb_next', 'tb_lasti', 'tb_lineno',
    'mro', 'format', 'format_map',
))
BANNED_CALLS = frozenset((
    'getattr', 'setattr', 'delattr', 'vars', 'globals', 'locals', 'type', 'dir',
    'eval', 'exec', 'compile', 'open', 'input', 'breakpoint', 'exit', 'quit', 'help',
))
CLASS_DUNDER_OK = frozenset(('__slots__', '__match_args__', '__hash__'))   # 클래스 몸통에서 값을 줄 수 있는 이름


def _bad_attr(name):
    return name.startswith('__') or name in BANNED_ATTRS


def check(source, limit=20):
    """봇 소스를 검사해 걸린 것의 목록 (글) 을 돌려준다. 빈 목록이면 통과."""
    if not isinstance(source, str):
        return ['봇 소스가 글이 아니다']
    if len(source) > MAX_SOURCE:
        return [f'봇 파일이 너무 크다 ({len(source):,} 글자, 한도 {MAX_SOURCE:,})']
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f'{e.lineno or 0}번 줄: 문법 오류: {e.msg}']
    except Exception as e:                      # 너무 깊은 식 · 이상한 글자
        return [f'읽을 수 없는 코드: {type(e).__name__}']

    out = []

    def bad(node, msg):
        out.append(f"{getattr(node, 'lineno', 0)}번 줄: {msg}")

    # 봇이 스스로 만든 이름 (변수 · 함수 · 인자). 금지 함수와 이름이 같아도 자기 것을 부르는 것은 된다
    own = set()
    class_methods, class_assigns = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            own.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            own.add(node.name)
        elif isinstance(node, ast.arg):
            own.add(node.arg)
        elif isinstance(node, ast.alias):
            own.add(node.asname or node.name.split('.')[0])
        if isinstance(node, ast.ClassDef):
            for b in node.body:
                if isinstance(b, ast.FunctionDef):
                    class_methods.add(id(b))
                elif isinstance(b, (ast.Assign, ast.AnnAssign)):
                    for t in (b.targets if isinstance(b, ast.Assign) else [b.target]):
                        if isinstance(t, ast.Name) and t.id in CLASS_DUNDER_OK:
                            class_assigns.add(id(t))

    def bound(node, name, what):
        if name and name.startswith('__'):
            bad(node, f"밑줄 두 개로 시작하는 {what} '{name}' 은 쓸 수 없다")

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if _bad_attr(node.attr):
                bad(node, f"속성 '.{node.attr}' 은 쓸 수 없다")
        elif isinstance(node, ast.Name):
            if node.id.startswith('__') and id(node) not in class_assigns:
                bad(node, f"이름 '{node.id}' 은 쓸 수 없다")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in BANNED_CALLS and f.id not in own:
                bad(node, f"'{f.id}()' 는 쓸 수 없다")
        elif isinstance(node, ast.MatchClass):
            for k in node.kwd_attrs:
                if _bad_attr(k):
                    bad(node, f"match 의 속성 '{k}' 은 쓸 수 없다")
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
            bound(node, node.name, '이름')
        elif isinstance(node, ast.MatchMapping):
            bound(node, node.rest, '이름')
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    bad(node, f"'{a.name}' 모듈은 쓸 수 없다 (쓸 수 있는 것: {', '.join(ALLOWED_IMPORTS[1:])})")
                bound(node, a.asname, '이름')
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module not in ALLOWED_IMPORTS:
                bad(node, f"'{'.' * node.level}{node.module or ''}' 모듈은 쓸 수 없다 (쓸 수 있는 것: {', '.join(ALLOWED_IMPORTS[1:])})")
            if node.module == 'wumpus' and any(a.name != 'api' for a in node.names):
                bad(node, "wumpus 에서는 api 만 불러올 수 있다 (from wumpus.api import ...)")
            for a in node.names:
                bound(node, a.name, '이름')
                bound(node, a.asname, '이름')
        elif isinstance(node, (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await)):
            bad(node, 'async / await 는 쓸 수 없다')
        elif isinstance(node, ast.comprehension):
            if node.is_async:
                bad(node.target, 'async / await 는 쓸 수 없다')
        elif isinstance(node, ast.FunctionDef):
            if node.name == '__del__':
                bad(node, "'__del__' 은 정의할 수 없다")
            elif id(node) not in class_methods:
                bound(node, node.name, '함수 이름')
        elif isinstance(node, ast.ClassDef):
            bound(node, node.name, '클래스 이름')
        elif isinstance(node, ast.arg):
            bound(node, node.arg, '인자 이름')
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for n in node.names:
                bound(node, n, '이름')
        elif isinstance(node, ast.ExceptHandler):
            bound(node, node.name, '이름')
        elif isinstance(node, ast.keyword):
            bound(node, node.arg, '인자 이름')
    seen, uniq = set(), []
    for m in out:
        if m not in seen:
            seen.add(m)
            uniq.append(m)

    def line_no(m):
        return int(m.split('번', 1)[0]) if m[0].isdigit() else 0

    uniq.sort(key=line_no)
    if len(uniq) > limit:
        uniq = uniq[:limit] + [f'... 그 밖에 {len(uniq) - limit}건']
    return uniq


def has_turn(source):
    """맨 바깥에 turn 함수 정의가 있나 (점검 도구용)."""
    try:
        tree = ast.parse(source)
    except Exception:
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name == 'turn' for n in tree.body)
