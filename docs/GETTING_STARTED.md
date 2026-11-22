# 시작하기

이 문서를 따라 하면 10분 안에 첫 경기를 보고, 내 봇을 만들어 겨뤄 볼 수 있다.

## 1. 준비

- **Python 3.8 이상**. 다른 패키지는 필요 없다. 확인: `python --version`
- **브라우저** (Chrome · Edge · Firefox). 리플레이를 볼 때 쓴다. 3D 화면은 three.js 를 인터넷에서 불러오므로 인터넷이 있어야 보인다 (없으면 비상용 2D 그림).

```bash
git clone <이 저장소 주소> wumpus_wars
cd wumpus_wars
python -m wumpus --help
```

모든 명령은 **저장소 맨 위 폴더 (`wumpus_wars/`)** 에서 친다.

(선택) `pip install -e .` 로 설치하면 어느 폴더에서나 `wumpus` 명령을 쓸 수 있다. 이 문서는 설치 없이 되는 `python -m wumpus` 로 적는다.

> **Windows 에서 한글이 깨지면** 터미널에서 `chcp 65001` 을 한 번 치거나, 환경 변수 `PYTHONUTF8=1` 을 둔다.

## 2. 첫 경기

```bash
python -m wumpus run logic random --open
```

```
맵 temple_gate (24x24, 대칭 H) | 붉은 원정대 (logic) 승리 - 야영지 파괴
라운드 84 | 바친 금 60 : 15 | 0.2초
  붉은 원정대 logic: 차례당 평균 0.27 ms, 최대 4.6 ms
  푸른 원정대 random: 차례당 평균 0.01 ms, 최대 0.0 ms
리플레이: replays/logic-vs-random-temple_gate-s1.json
뷰어    : replays/logic-vs-random-temple_gate-s1.html
```

- 첫 봇이 **붉은 원정대**, 둘째 봇이 **푸른 원정대**다.
- `--open` 을 붙이면 끝나자마자 브라우저에 리플레이가 열린다. 뷰어 사용법은 [리플레이 도구](REPLAY.md) 에 있다.
- 다른 맵: `--map scarab_maze`. 맵 목록은 `python -m wumpus maps`.

## 3. 내 봇 만들기

```bash
python -m wumpus new mybot
```

`bots/mybot/main.py` 가 생긴다. 시작용 봇 (`bots/starter`) 을 복사한 것이다. 이 파일 하나가 봇 전체다.

```python
def turn(me, view, memory):
    if me.kind == CAMP:
        return camp_turn(me, view, memory)       # 야영지: 모험가를 만든다
    return adventurer_turn(me, view, memory)     # 모험가: 느끼고 · 추론하고 · 캐고 · 싸운다
```

꼭 알아 둘 세 가지:

1. **모험가마다 이 파일이 따로 실행된다.** 모듈 전역 변수는 그 모험가 혼자만의 기억 (지식 베이스) 이다.
2. **팀끼리 나눌 것은 `memory` (정수 64칸)** 에 적는다.
3. **모험가는 자기 칸만 느낀다.** 벽 · 구덩이 · 금 · 웜퍼스 · 다른 모험가는 보이지 않고, 지각 (`view.breeze` · `stench` · `glitter` · `bump` · `footsteps` · `hurt` · `screams`) 으로만 추론한다.

자세한 API 는 [봇 API](API.md), 규칙은 [게임 규칙](RULES.md) 에 있다.

## 4. 고치고 시험하는 순서

```bash
python -m wumpus check mybot                  # 1) 오류 · 시간 점검 (양쪽 진영 한 판씩)
python -m wumpus run mybot random --open      # 2) 한 판을 눈으로 본다
python -m wumpus scrim mybot logic            # 3) 맵 10개 x 양쪽 진영 = 20판으로 실력을 잰다
```

**디버그 기록**: `debug.mark(x, y, 'green')`, `debug.path(칸들)`, `debug.say('글')` 을 부르면 리플레이 .json 의 프레임 `d` 에 남는다. 경기 결과에는 영향이 없다. 추론이 맞는지 확인할 때 쓴다. 리플레이 화면에서는 모험가 머리 위의 **지각 아이콘**으로 그 순간 무엇을 느꼈는지 볼 수 있다.

고칠 때마다 `scrim` 으로 예전 봇과 겨뤄 보자. 예전 봇은 폴더째 복사해 두면 된다:

```bash
python -m wumpus new mybot_v1 --from mybot     # 지금 봇을 mybot_v1 로 보관
# mybot 을 고친 뒤
python -m wumpus scrim mybot mybot_v1          # 새 봇이 정말 나아졌나?
```

## 5. 더 볼 것

- 예시 추론 봇 `bots/logic/main.py`: 명제논리 · 대칭 추론 · A* · 발소리 추론을 쓴다. 일부러 고칠 거리를 남겨 두었다 (공유 지도, 웜퍼스 사냥, CSP 배정, 여러 바람 칸을 엮는 레졸루션).
- 기본 점검: `python -m unittest discover tests`
