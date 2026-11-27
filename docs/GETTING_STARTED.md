# 시작하기

이 문서를 따라 하면 10분 안에 첫 경기를 보고, 내 봇을 만들어 겨뤄 볼 수 있다.

## 1. 준비

- **Python 3.8 이상**. 다른 패키지는 필요 없다. 확인: `python --version`
- **브라우저** (Chrome · Edge · Firefox). 리플레이를 볼 때 쓴다. 리플레이 파일 하나에 화면에 필요한 것이 다 들어 있어서 인터넷 없이도 열린다.

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
python -m wumpus run starter starter --open
```

```
맵 temple_gate (24x24, 대칭 H) | 푸른 원정대 (starter) 승리 - 1000라운드 끝, 바친 금
라운드 1000 | 바친 금 289 : 432 | 6.6초
  붉은 원정대 starter: 차례당 평균 0.27 ms, 최대 4.9 ms | 연산 (차례당) 평균 861, 최대 6,646
  푸른 원정대 starter: 차례당 평균 0.29 ms, 최대 4.0 ms | 연산 (차례당) 평균 937, 최대 5,878
리플레이: replays/starter-vs-starter-temple_gate-s1.json
뷰어    : replays/starter-vs-starter-temple_gate-s1.html
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
2. **팀끼리 나눌 것은 `memory` (정수 16칸)** 에 적는다.
3. **연산 한도가 있다.** 유닛마다 한 차례에 연산 10,000 (첫 차례만 200,000) 을 쓴다. 남겨도 쌓이지 않고, 넘은 차례는 행동이 버려진다. 불러올 수 있는 모듈도 정해져 있다 ([규칙 11절](RULES.md)). `check` · `scrim` 결과의 '연산' 줄을 본다.
4. **모험가는 자기 칸만 느낀다.** 벽 · 구덩이 · 금 · 웜퍼스 · 다른 모험가는 보이지 않고, 지각 (`view.breeze` · `stench` · `glitter` · `bump` · `footsteps` · `hurt` · `screams` · `warmth` · `cries`) 으로만 추론한다. 적 야영지 위치도 알려 주지 않는다 (맵 대칭과 열기로 찾는다).
5. **처음에는 모험가가 없다.** 야영지가 금고 20 으로 첫 모험가를 뽑는다. 다음 모험가 값 20 이 다시 모이려면 오래 걸리니, 첫 모험가를 잃지 않는 것이 중요하다.
6. **화살은 한 발.** 웜퍼스는 화살로만 쓰러진다 (보물 30). 악취로 굴을 추론해 쏜다.

자세한 API 는 [봇 API](API.md), 규칙은 [게임 규칙](RULES.md) 에 있다.

## 4. 고치고 시험하는 순서

```bash
python -m wumpus check mybot                  # 1) 코드 검사 · 오류 · 시간 점검 (양쪽 진영 한 판씩)
python -m wumpus run mybot starter --open     # 2) 한 판을 눈으로 본다
python -m wumpus scrim mybot starter          # 3) 맵 10개 x 양쪽 진영 = 20판으로 실력을 잰다
```

**디버그 기록**: `debug.mark(x, y, 'green')`, `debug.path(칸들)`, `debug.say('글')` 을 부르면 리플레이 .json 의 프레임 `d` 에 남는다. 경기 결과에는 영향이 없다. 추론이 맞는지 확인할 때 쓴다. 리플레이 화면에서는 모험가 머리 위의 **지각 아이콘**으로 그 순간 무엇을 느꼈는지 볼 수 있다.

고칠 때마다 `scrim` 으로 예전 봇과 겨뤄 보자. 예전 봇은 폴더째 복사해 두면 된다:

```bash
python -m wumpus new mybot_v1 --from mybot     # 지금 봇을 mybot_v1 로 보관
# mybot 을 고친 뒤
python -m wumpus scrim mybot mybot_v1          # 새 봇이 정말 나아졌나?
```

## 5. 더 볼 것

- 시작용 봇 `bots/starter/main.py` 의 `TODO`: 구덩이 위치 추론, 덜 위험한 칸 고르기, 발소리로 적 위치 추론, 화살로 적을 쏠 때, 금을 얼마나 들고 돌아갈지, 야영지 공격 시점. 막 복사한 봇은 시작용 봇과 20판에서 10승 10패다. 여기서부터 올린다.
- 기본 점검: `python -m unittest discover tests`
