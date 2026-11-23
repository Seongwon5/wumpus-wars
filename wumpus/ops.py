"""연산 계량기: 봇 코드가 한 일의 양을 센다 (배틀코드의 바이트코드 한도와 같은 역할).

- 연산 1 = 줄 하나를 실행하기 시작함 / 반복이 한 번 되돌아감 (for · while · 컴프리헨션) /
  함수 · 람다 · 제너레이터가 한 번 시작되거나 재개됨.
  줄만 세면 `for i in r: t += i` 나 `[f(x) for x in xs]` 처럼 한 줄에 몰아 쓴 반복이 공짜가 되므로 뒤의 둘을 더 센다.
- 세는 곳은 봇 파일의 코드와, 봇이 부른 API 함수 (wumpus.api, view.*, me.*) 안이다.
  내장 함수 (sorted, len ...) 안은 세지 않는다 (부른 줄만 센다). 그쪽은 시간 안전망 (api.TIME_SAFETY_MS) 이 막는다.
- 같은 봇 · 같은 맵 · 같은 시드면 센 값도 같다 (시간이 아니라 일의 양을 센다).
- Python 3.12 이상은 sys.monitoring, 그 아래는 sys.settrace 로 센다. 두 방식 · 파이썬 버전에 따라 값이 조금 다를 수
  있다 (공식 기준은 3.12 이상).
- 한도를 넘으면 OpsExceeded 를 그 자리에서 던진다. Exception 이 아니라 BaseException 이므로 봇의
  `except Exception` 에 잡히지 않는다.
"""
import sys
import types


class OpsExceeded(BaseException):
    """봇이 이번 차례의 연산 한도를 넘었다."""


def _walk(code):
    yield code
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield from _walk(c)


class Meter:
    """한 과정 (process) 에 하나. 경기는 차례대로 돌므로 전역 계량기 하나로 충분하다."""

    def __init__(self):
        self.count = 0
        self.limit = 0
        self.active = False
        self.mon = getattr(sys, 'monitoring', None)
        self.tool = None
        self.mask = 0
        if self.mon is not None:
            ev = self.mon.events
            for t in range(6):                      # 비어 있는 도구 번호 하나를 쓴다
                if self.mon.get_tool(t) is None:
                    self.mon.use_tool_id(t, 'wumpus-ops')
                    self.tool = t
                    break
            if self.tool is not None:
                reg = self.mon.register_callback
                reg(self.tool, ev.LINE, self._on_line)
                reg(self.tool, ev.PY_START, self._on_line)          # 함수 · 람다 · 제너레이터 시작
                reg(self.tool, ev.PY_RESUME, self._on_line)         # 제너레이터 재개
                reg(self.tool, ev.JUMP, self._on_jump)              # for 의 되돌아감
                self.mask = ev.LINE | ev.PY_START | ev.PY_RESUME | ev.JUMP
                for name in (('BRANCH',) if sys.version_info < (3, 14) else ('BRANCH_LEFT', 'BRANCH_RIGHT')):   # while 의 되돌아감
                    e = getattr(ev, name, None)
                    if e is not None:
                        reg(self.tool, e, self._on_jump)
                        self.mask |= e
        if self.tool is None:
            self.mon = None
        self.codes = set()                          # 세는 코드 (settrace 일 때 거르는 데 쓴다)
        self.host_done = False

    # --- 봇 코드 등록 (sys.monitoring 일 때) ---
    def watch(self, code):
        for c in _walk(code):
            self.codes.add(c)
            if self.mon is not None:
                self.mon.set_local_events(self.tool, c, self.mask)

    def watch_host(self, *objs):
        """봇이 부를 수 있는 API 함수 · 클래스 메서드도 센다 (한 번만)."""
        if self.host_done:
            return
        self.host_done = True
        for o in objs:
            fns = [o] if isinstance(o, types.FunctionType) else [v for v in vars(o).values() if isinstance(v, (types.FunctionType, property))]
            for f in fns:
                for g in ((f.fget, f.fset) if isinstance(f, property) else (f,)):
                    if g is not None:
                        self.watch(g.__code__)

    # --- 세기 ---
    def _on_line(self, code, arg):
        if self.active:
            self.count += 1
            if self.count > self.limit:
                raise OpsExceeded()

    def _on_jump(self, code, src, dst):
        if self.active and dst < src:               # 뒤로 뛴 것만 (반복)
            self.count += 1
            if self.count > self.limit:
                raise OpsExceeded()

    def _trace_local(self, frame, event, arg):
        if event == 'line' and self.active:         # settrace 의 line 은 같은 줄로 되돌아갈 때도 온다
            self.count += 1
            if self.count > self.limit:
                raise OpsExceeded()
        return self._trace_local

    def _trace_global(self, frame, event, arg):
        if frame.f_code not in self.codes:
            return None
        if self.active:                             # 함수 · 제너레이터 시작 · 재개
            self.count += 1
            if self.count > self.limit:
                raise OpsExceeded()
        return self._trace_local

    def start(self, limit):
        self.count, self.limit, self.active = 0, limit, True
        if self.mon is None:
            sys.settrace(self._trace_global)

    def stop(self):
        self.active = False
        if self.mon is None:
            sys.settrace(None)
        return self.count


_meter = None


def meter():
    global _meter
    if _meter is None:
        _meter = Meter()
    return _meter
