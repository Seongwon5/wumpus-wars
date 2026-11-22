# 봇 API

엔진 코드 (`wumpus/api.py`, `wumpus/engine.py`) 와 한 줄씩 맞춰 쓴 참조 문서다. 규칙은 [RULES.md](RULES.md) 에 있다.

## 1. 봇 파일

봇 하나는 폴더 하나다: `bots/<봇이름>/main.py`. 이 파일에 아래 함수가 있어야 한다.

```python
def turn(me, view, memory):
    ...
    return 행동   # Move · Mine · Attack · Spawn 중 하나, 또는 None (쉬기)
```

- 야영지와 모험가가 모두 이 함수를 부른다. 종류는 `me.kind` 로 나눈다 (`CAMP` 또는 `EXPLORER`).
- **모험가마다 파일이 따로 실행된다.** 모험가가 생길 때 파일을 새로 불러 그 모험가 전용 공간에 둔다.
  - 모듈 전역 변수는 그 모험가만의 기억 (지식 베이스) 이다. 크기 제한이 없고, 모험가가 죽으면 사라진다.
  - 팀끼리 나눌 정보는 `memory` 로만 주고받는다.
- 시작은 `python -m wumpus new 내봇` 으로 시작용 봇 (`bots/starter`) 을 복사해서 한다.
- 표준 라이브러리 (`math`, `heapq`, `collections`, `random`, `itertools` …) 는 써도 된다.

불러올 것:

```python
from wumpus.api import (Move, Mine, Attack, Spawn, debug,
                        EXPLORER, CAMP,                        # 종류 (모험가 = EXPLORER)
                        EMPTY, WALL, GOLD, CAMP_TILE,          # 칸 글자 '.' '#' 'G' 'C'
                        DIRS, mirror, cheb, direction_to,      # 도우미
                        COST, CARRY_MAX, MAX_ROUNDS)           # 규칙 수치
```

## 2. 좌표와 방향

- `(x, y)`. x 는 오른쪽, y 는 **아래쪽**으로 커진다. 왼쪽 위가 `(0, 0)`.
- 방향은 네 글자: `'N'` 위 `(0,-1)`, `'E'` 오른쪽 `(1,0)`, `'S'` 아래 `(0,1)`, `'W'` 왼쪽 `(-1,0)`. `DIRS` 사전에 있다.
- 이동과 공격 모두 상하좌우만 된다.

## 3. `me`: 자기 정보

| 속성 | 뜻 |
|---|---|
| `id` | 번호. 경기 안에서 겹치지 않는다. 야영지는 1 (붉은), 2 (푸른) |
| `team` | 0 = 붉은 원정대, 1 = 푸른 원정대 |
| `kind` | `CAMP` 또는 `EXPLORER` (모험가) |
| `x`, `y` | 지금 위치 |
| `hp` | 남은 체력 |
| `carry` | 든 금 |
| `round` | 지금 라운드 (1 ~ 1000) |
| `bank` | 우리 금고 |
| `ops_bank` | 이 차례를 시작할 때 팀 연산 예산 (줄 수) |

`me` 는 복사본이다. 바꿔도 게임에 영향이 없다.

## 4. `view`: 지금 느끼는 것

### 지각 (모험가)

| 속성 | 값 | 뜻 |
|---|---|---|
| `view.breeze` | `True`/`False` | 바람: 상하좌우에 구덩이 |
| `view.stench` | `True`/`False` | 악취: 상하좌우에 살아 있는 웜퍼스 굴 |
| `view.glitter` | `True`/`False` | 반짝임: 이 칸에 금맥이나 떨어진 금 |
| `view.bump` | `True`/`False` | 부딪힘: 지난 이동이 막혔다 (벽 · 맵 끝 · 모험가 · 야영지) |
| `view.footsteps` | 정수 0 ~ 4 | 발소리: 상하좌우의 다른 모험가 수 (팀 구분 없음) |
| `view.hurt` | 정수 | 아픔: 지난 차례 뒤 받은 피해 |
| `view.screams` | 정수 | 비명: 지금까지 쓰러진 웜퍼스 수 (맵 어디서든) |

### 칸 (자기 칸만)

| 함수 | 돌려주는 값 |
|---|---|
| `view.tile(x, y)` | 자기 칸이면 `'.'` 빈 칸 · `'G'` 금맥. 다른 칸은 `None` |
| `view.gold(x, y)` | 자기 칸의 남은 금 (없으면 0). 다른 칸은 `None` |
| `view.loot(x, y)` | 자기 칸의 떨어진 금. 다른 칸은 `None` |
| `view.visible(x, y)` · `view.visible_cells()` | 모험가는 자기 칸 하나뿐 |
| `view.units()` | 모험가는 자기 자신만 (다른 모험가는 발소리로만 안다) |

- 구덩이와 웜퍼스 굴은 어떤 함수로도 보이지 않는다 (밟은 뒤에도).
- **야영지**는 생산 자리를 고르려고 상하좌우 옆 칸까지 본다 (`tile`, `units`).

### 그 밖

| 속성 | 뜻 |
|---|---|
| `view.my_camp`, `view.enemy_camp` | 우리 · 적 야영지 좌표 `(x, y)` |
| `view.width`, `view.height` | 맵 크기 |
| `view.round`, `view.bank`, `view.score`, `view.team` | 라운드, 우리 금고, 우리 점수 (바친 금 합), 팀 번호 |
| `view.unit_count` | 우리 팀 살아 있는 모험가 수 |

## 5. 행동

| 행동 | 누가 | 하는 일 | 무시되는 경우 |
|---|---|---|---|
| `Move(d)` | 모험가 | `d` 쪽으로 한 칸 | 막히면 제자리 (다음 차례에 `view.bump`) |
| `Mine()` | 모험가 | 선 칸의 금맥에서 금 1개 | 금맥이 아닌 칸, 이미 5개를 든 경우 |
| `Attack(x, y)` | 모험가 | 상하좌우 옆 칸을 검으로 친다 (피해 3) | 옆 칸이 아님. 빈 칸 · 팀원이면 헛친다 |
| `Spawn(EXPLORER, d)` | 야영지 | `d` 쪽 옆 칸에 모험가 | 금고 부족, 팀 10명, 그 칸이 맵 밖 · 벽 · 모험가 · 구덩이 |
| `None` | 누구나 | 쉬기 | |

- 안 되는 행동은 **오류 없이 그냥 무시된다.**
- 구덩이 칸으로 `Move` 하면 떨어져 죽는다. 살아 있는 웜퍼스 굴로 `Move` 하면 잡아먹힌다.
- **줍기 (행동 아님):** 떨어진 금이 있는 칸에 들어서면 저절로 줍는다.
- **바침 (행동 아님):** 차례를 마칠 때 자기 야영지와 상하좌우로 맞닿아 있으면 든 금을 저절로 다 바친다.
- **웜퍼스를 치면** 깨어나 5 라운드 동안 옆의 한 명에게 매 라운드 피해 6 을 준다.

## 6. `memory`: 팀 공유 메모리

- 정수 16칸 리스트다. 같은 팀 모험가가 모두 같은 리스트를 본다. 처음엔 모두 0.
- 쓴 값은 **바로 다음에 움직이는 모험가**부터 보인다 (같은 라운드 안에서도).
- 차례가 끝날 때마다 16칸으로 맞추고, 값을 32비트 부호 있는 정수로 자른다. 정수가 아닌 값은 0 이 된다.
- 상대 팀 메모리는 볼 수 없다.
- 512비트다. 맵 한 칸에 1비트도 안 되므로 **맵 전체를 나눌 수는 없다.** 무엇을 나눌지 골라야 한다.
- 예: 칸 좌표 하나는 10비트 (x 5비트 + y 5비트) 면 된다. 정수 한 칸에 좌표 셋, 또는 좌표 하나와 라운드 · 번호를 함께 묶을 수 있다 (`<<` · `>>` · `&` 비트 연산).
- 나누면 좋은 것: 팀원 위치 (발소리에서 적을 가려내려고), 찾은 금맥, 바람 · 악취로 확정한 구덩이 · 굴, 적을 만난 곳.

## 7. 디버그 표시: `debug`

경기 결과에는 영향이 없고, 차례마다 새로 지워진다. 리플레이 .json 의 프레임 `d` 에 남는다.

| 함수 | 뜻 | 한도 (차례마다) |
|---|---|---|
| `debug.mark(x, y, color)` | 칸에 색 칠하기 | 400칸 |
| `debug.path(cells, color)` | 칸 목록을 잇기 | 선 8개, 선마다 200칸 |
| `debug.say(text)` | 글 한 줄 | 8줄, 줄마다 200자 |

색: `'green' 'red' 'yellow' 'blue' 'purple' 'white'` 또는 `'#rrggbb'`.

## 8. 도우미

| 함수 | 뜻 |
|---|---|
| `mirror(sym, x, y, w, h)` | 대칭 `sym` (`'H'` 좌우, `'V'` 상하, `'R'` 180° 회전) 으로 옮긴 칸 |
| `cheb(ax, ay, bx, by)` | 체비셰프 거리 (대각선도 1칸) |
| `direction_to(ax, ay, bx, by)` | 맞닿은 두 칸 사이의 방향 글자. 안 맞닿았으면 `None` |
| `DIRS` | `{'N': (0,-1), 'E': (1,0), 'S': (0,1), 'W': (-1,0)}` |
| `ops_left()` | 이번 차례에 더 쓸 수 있는 줄 수 (연산 한도, 규칙 11절) |

## 9. 연산 한도 · 오류 · 시간 · 재현성

- **연산 한도:** 봇 코드가 실행한 줄 수를 센다. 팀 예산 1,000,000 줄에서 시작해 라운드마다 50,000 줄이 더해지고, 한 차례에는 최대 100,000 줄까지 쓴다. 넘으면 그 줄에서 차례가 끊기고 행동이 버려진다. 자세히는 [규칙 11절](RULES.md).
- 남은 양은 `ops_left()` (이번 차례) 와 `me.ops_bank` (팀 예산) 로 본다. 무거운 계산 (맵 전체 BFS 등) 은 모든 모험가가 매 차례 하지 말고, 결과를 전역 변수에 두고 다시 쓴다.

```python
from wumpus.api import ops_left

def turn(me, view, memory):
    plan = cheap_answer(me, view)          # 먼저 싼 답을 정해 둔다
    if ops_left() > 20000:                 # 여유가 있을 때만 깊게 본다
        plan = deeper_search(me, view) or plan
    return plan
```

- `run` · `scrim` · `check` 는 팀마다 차례당 연산 (평균 · 최대) 과 한도 초과 수를 보여 준다. 개발 중 빠르게 돌리고 싶으면 `--no-ops-limit` 로 셈을 끌 수 있다 (한도 안의 봇은 결과가 같다. 공식 규칙은 아니다).
- `turn` 에서 예외가 나면 그 모험가는 그 차례만 쉰다. 리플레이 사건 목록과 `run` · `scrim` 결과에 오류로 나온다.
- 차례마다 걸린 시간도 잰다. `--time-limit 밀리초` 를 주면 시간 한도도 쓴다 (시간은 컴퓨터마다 달라 공식 규칙은 아니다).
- `random` 모듈은 차례마다 (경기 시드, 라운드, 번호) 로 다시 맞춰진다. 같은 봇 · 맵 · 시드면 결과가 같다.

## 10. 가장 작은 봇

```python
import random
from wumpus.api import Move, Mine, Spawn, EXPLORER, CAMP

def turn(me, view, memory):
    if me.kind == CAMP:
        return Spawn(EXPLORER, random.choice('NESW'))   # 금고가 되면 모험가를 만든다
    if view.glitter and view.gold(me.x, me.y):
        return Mine()                                    # 반짝이면 캔다
    return Move(random.choice('NESW'))                   # 아니면 아무 데나 (구덩이 조심!)
```

`bots/starter/main.py` 는 여기에 더해 "바람도 악취도 없으면 상하좌우는 안전하다" 추론, 벽 기억, 귀환, 반격을 한다. TODO 표시부터 고쳐 보자.
