# 웜퍼스 워즈 (Wumpus Wars)

인공지능개론 배틀코드형 과제 게임이다. 수업의 **웜퍼스 월드 (Wumpus World)** 를 두 팀 대전으로 옮겼다. 학생은 **봇 코드**만 짠다. 경기 중에 사람은 아무것도 하지 않고, 봇의 판단만으로 승부가 난다.

![경기 장면](docs/images/hero.jpg)

## 한눈에 보는 규칙

- 두 원정대가 어두운 동굴에서 금을 캐 **야영지**에 바친다.
- 유닛은 검을 든 **모험가** 하나뿐이다. 한 턴에 **이동 또는 공격 하나**, 공격은 상하좌우 옆 칸만.
- 모험가는 **자기 칸만 느낀다.** 구덩이 · 웜퍼스 · 금맥 · 적은 보이지 않는다. 지각을 기억하고 추론해서 알아낸다.
- **적 야영지를 부수면** 바로 이긴다. 못 부수면 **1000 라운드** 끝에 바친 금이 많은 쪽이 이긴다.
- 웜퍼스는 **잠들어 있다.** 치면 깨어나 5 라운드 동안 옆의 한 명을 친다. 쓰러뜨리면 금 20 이 떨어진다.

모험가가 차례마다 자기 칸에서 느끼는 것 (지각):

| 지각 | 뜻 | 추론 예 |
|---|---|---|
| 바람 | 상하좌우에 구덩이가 있다 | 바람이 없으면 옆 칸 넷은 구덩이가 아니다 |
| 악취 | 상하좌우에 웜퍼스 굴이 있다 | 악취가 없으면 옆 칸 넷은 굴이 아니다 |
| 반짝임 | 이 칸에 금맥이나 떨어진 금 | 반짝이면 캔다 |
| 부딪힘 | 지난 이동이 막혔다 | 발소리도 없으면 그쪽은 벽이다 |
| 발소리 | 상하좌우의 다른 모험가 수 (팀 구분 없음) | 기억한 팀원 수보다 많으면 적이 옆에 있다 |
| 아픔 | 지난 차례 뒤 받은 피해 | 누군가 옆에서 쳤다 |
| 비명 | 쓰러진 웜퍼스 수 (맵 전체) | 누군가 웜퍼스를 잡았다 |

![지각 아이콘](docs/images/percepts.jpg)

리플레이 뷰어는 모험가마다 **지금 느끼는 지각을 머리 위 아이콘**으로 띄운다 (위 그림: 부딪힘 · 발소리). 동굴은 어둡고 모험가 발밑만 밝다. 봇이 아는 세상이 그만큼 좁기 때문이다.

## 수업과의 대응

| 이 게임 | 수업 (웜퍼스 월드) | 쓰게 되는 AI 기법 |
|---|---|---|
| 숨은 구덩이와 바람 | Pit · Breeze | 명제논리 추론, 지식 베이스 |
| 웜퍼스와 악취 · 금과 반짝임 | Wumpus · Stench · Glitter | 명제논리 추론, 모델 검사 |
| 벽과 부딪힘 · 웜퍼스의 비명 | Bump · Scream | 지각 기록, 믿음 갱신 |
| 자기 칸만 느끼는 모험가 | 부분 관측 | 믿음 상태, 탐사 |
| 보이지 않는 적 (발소리 · 아픔) | 지각 추론 | 가설 지우기, 팀 공유 지식 |
| 숨은 맵 대칭 | 1차 술어 논리 | 대칭 후보 지우기 |
| 금 캐기 · 길 찾기 | 탐색 | BFS · A* · 위험 비용 |
| 모험가 여럿에게 금맥 나누기 | CSP | 배정 · 제약 만족 |

## 바로 해 보기

Python 3.8 이상이면 된다. 다른 설치는 없다 (표준 라이브러리만 쓴다).

```bash
git clone <이 저장소 주소> wumpus_wars
cd wumpus_wars

python -m wumpus run starter random --open      # 경기 하나. 끝나면 브라우저에 리플레이가 열린다
python -m wumpus new mybot                      # bots/mybot/main.py 를 만든다 (시작용 봇 복사)
python -m wumpus scrim mybot starter            # 맵 10개에서 양쪽 진영으로 겨루고 승패를 센다
```

`pip install -e .` 로 설치하면 `python -m wumpus` 대신 `wumpus` 만 써도 된다.

## 들어 있는 봇

| 봇 | 하는 일 |
|---|---|
| `bots/starter` | **시작용 봇.** 바람도 악취도 없는 칸으로 안전한 칸을 넓히며 탐험하고, 반짝이면 캐고, 아는 길로 돌아와 바친다. 부딪힘으로 벽을 배우고, 아프면 반격한다. `TODO` 부터 고쳐 쓴다 |
| `bots/random` | 무작위 봇 (기준선) |
| `bots/logic` | 추론 예시 봇. 팀 공유 메모리로 팀원 위치를 나눠 발소리에서 적을 가려내고, 후반에는 적 야영지를 친다 |

미리 만든 리플레이는 [`demo/`](demo) 에 있다. `.html` 파일을 브라우저로 열면 된다.

| 파일 | 내용 |
|---|---|
| `demo/starter_vs_random.html` | 시작용 봇 vs 무작위 봇. 1000 라운드 끝에 417 : 261 |
| `demo/logic_vs_starter.html` | 추론 봇 vs 시작용 봇. 추론 봇이 254 라운드에 야영지를 부순다 |

## 설명서

| 문서 | 내용 |
|---|---|
| [시작하기](docs/GETTING_STARTED.md) | 설치, 첫 경기, 내 봇 만들기, 고치고 시험하는 순서 |
| [게임 규칙](docs/RULES.md) | 목표 · 맵 · 모험가 · 지각 · 구덩이 · 웜퍼스 · 금 · 야영지 · 행동 · 차례 순서 · 모든 수치 |
| [봇 API](docs/API.md) | `turn(me, view, memory)`, 지각, 행동, 공유 메모리, 디버그 표시 |
| [스크림 도구](docs/SCRIM.md) | 여러 맵 묶음 대전, 승률 · 시간 · 오류 보기, CSV |
| [리플레이 도구](docs/REPLAY.md) | 리플레이 파일, 뷰어 화면, 머리 위 지각 아이콘, 팀 시야, .json 형식 |
| [맵](docs/MAPS.md) | 맵 목록 · 그림 보기 · 새 맵 만들기 · 맵 파일 형식 |

PDF 문서 (인쇄용, 학위논문 양식). `python -X utf8 tools/md2thesis.py all` 로 위 마크다운에서 다시 만든다.

| 문서 | 내용 |
|---|---|
| [게임 규칙서](docs/pdf/rulebook.pdf) | 게임 규칙 전체, 그림, 수치 일람 (21쪽) |
| [봇 API 가이드북](docs/pdf/api_guidebook.pdf) | 시작하기 · 봇 API · 스크림 · 리플레이 · 맵 (27쪽) |

## 명령 한눈에

| 명령 | 하는 일 |
|---|---|
| `python -m wumpus run 봇A 봇B [--map 맵] [--open]` | 경기 하나 + 리플레이 (`replays/`) |
| `python -m wumpus scrim 봇A 봇B [--maps all] [--seeds 1-3]` | 여러 맵에서 양쪽 진영으로 겨루고 승패표 |
| `python -m wumpus view 리플레이.json` | 리플레이를 뷰어로 연다 |
| `python -m wumpus viewer` | 빈 뷰어 (json 을 끌어다 놓아 연다) |
| `python -m wumpus maps [list / show 맵 / gen]` | 맵 목록 · 글자 그림 · 새 맵 |
| `python -m wumpus new 이름` | 새 봇 폴더 |
| `python -m wumpus check 봇` | 봇 점검 (불러오기 · 오류 · 차례 시간) |

## 저장소 구성

```
wumpus/            게임 패키지
  api.py           봇이 쓰는 API 와 규칙 수치
  engine.py        게임 엔진 (같은 봇 · 맵 · 시드면 같은 결과)
  maps.py          대칭 맵 생성기, 맵 파일 읽기 · 쓰기
  replay.py        리플레이 저장, 뷰어 html 만들기
  cli.py           명령줄 도구 (run · scrim · view · maps · new · check)
  viewer/          리플레이 뷰어 (viewer.html, 3D 화면 view3d.js, LPC 그림 sprites/)
bots/              starter · random · logic
maps/              맵 10개 (*.json)
demo/              미리 만든 리플레이
docs/              설명서, 그림 (images/), PDF (pdf/)
tools/             PDF 조판 (md2thesis.py · thesis.py), LPC 그림 합성 (lpc_build.py), 재미 지표 (funstats.py)
tests/             기본 점검 (python -m unittest discover tests)
```

## 쓴 오픈소스

- 3D 뷰어: [three.js](https://threejs.org) 0.160 (MIT 라이선스). 인터넷 (jsDelivr CDN) 에서 불러온다. 인터넷이 없으면 6초 뒤 비상용 2D 그림으로 바뀐다.
- 글꼴: Cinzel, Noto Serif KR (SIL Open Font License, Google Fonts).
- 캐릭터 · 야영지 · 웜퍼스 · 동굴 그림: [Liberated Pixel Cup (LPC)](https://lpc.opengameart.org) 공개 그림 (CC-BY-SA 3.0 / 4.0, GPL, OGA-BY, CC-BY). 합성 도구 `tools/lpc_build.py`, 만든 사람 표기 [`wumpus/viewer/sprites/CREDITS.md`](wumpus/viewer/sprites/CREDITS.md).
- 효과음은 코드로 만들었다.
