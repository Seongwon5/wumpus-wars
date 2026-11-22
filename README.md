# 웜퍼스 워즈 (Wumpus Wars)

인공지능개론 배틀코드형 과제 게임이다. 학생은 **봇 코드**를 짠다. 경기 중에 사람은 아무것도 하지 않고, 봇의 판단만으로 승부가 난다.

두 원정대의 **모험가**들이 어두운 동굴에서 금을 캐 나른다. 모험가는 **자기 칸만 느낀다** (바람 · 악취 · 반짝임 · 부딪힘 · 발소리 · 아픔 · 비명). 구덩이 · 웜퍼스 · 금 · 적은 모두 기억과 추론으로 알아내야 한다. 수업의 웜퍼스 월드를 두 팀 대전으로 옮긴 게임이다.

![경기 장면](docs/images/hero.png)

| 이 게임 | 수업 (Wumpus 세계) | 쓰게 되는 AI 기법 |
|---|---|---|
| 숨은 구덩이와 바람 | Pit · Breeze | 명제논리 추론, 지식 베이스 |
| 숨은 맵 대칭 | 1차 술어 논리 | 대칭 후보 지우기, 전칭 예화 |
| 웜퍼스와 악취 · 금과 반짝임 | Wumpus · Stench · Glitter | 명제논리 추론, 모델 검사 |
| 자기 칸만 느끼는 모험가 | 부분 관측 | 믿음 상태, 지식 베이스, 탐사 |
| 보이지 않는 적 (발소리 · 아픔) | 지각 추론 | 가설 지우기, 팀 공유 지식 |
| 금 캐기 · 길 찾기 | 탐색 | BFS · A* · 위험 비용 |
| 모험가 여럿에게 금맥 나누기 | CSP | 배정 · 제약 만족 |

## 바로 해 보기

Python 3.8 이상이면 된다. 다른 설치는 없다 (표준 라이브러리만 쓴다).

```bash
git clone <이 저장소 주소> wumpus_wars
cd wumpus_wars

python -m wumpus run logic random --open        # 경기 하나. 끝나면 브라우저에 리플레이가 열린다
python -m wumpus new mybot                      # bots/mybot/main.py 를 만든다 (시작용 봇 복사)
python -m wumpus scrim mybot logic              # 맵 10개에서 양쪽 진영으로 겨루고 승패를 센다
```

`pip install -e .` 로 설치하면 `python -m wumpus` 대신 `wumpus` 만 써도 된다.

미리 만든 리플레이는 [`demo/`](demo) 에 있다. `.html` 파일을 브라우저로 열면 된다.

| 파일 | 내용 |
|---|---|
| `demo/starter_vs_random.html` | 시작용 봇 vs 무작위 봇. 1000 라운드 끝에 417 : 261 |
| `demo/logic_vs_starter.html` | 예시 추론 봇 vs 시작용 봇. 추론 봇이 273 라운드에 야영지를 부순다 |

## 설명서

| 문서 | 내용 |
|---|---|
| [시작하기](docs/GETTING_STARTED.md) | 설치, 첫 경기, 내 봇 만들기, 고치고 시험하는 순서 |
| [게임 규칙](docs/RULES.md) | 맵 · 구덩이 · 바람 · 금맥 · 유닛 · 전투 · 승리 조건 · 모든 수치 |
| [봇 API](docs/API.md) | `turn(me, view, memory)`, 지각, 행동, 공유 메모리, 디버그 기록 |
| [스크림 도구](docs/SCRIM.md) | 여러 맵 묶음 대전, 승률 · 시간 · 오류 보기, CSV |
| [리플레이 도구](docs/REPLAY.md) | 리플레이 파일, 3D · 2D 뷰어 사용법, 봇의 머릿속 보기 |
| [맵](docs/MAPS.md) | 맵 목록 · 그림 보기 · 새 맵 만들기 · 맵 파일 형식 |

PDF 문서 (인쇄용):

| 문서 | 내용 |
|---|---|
| [게임 규칙서](docs/pdf/rulebook.pdf) | 규칙 전체, 설명 그림, 수치 일람, 용어 (25쪽) |
| [봇 API 가이드북](docs/pdf/api_guidebook.pdf) | API 참조, 개발 도구, 리플레이 도구, 봇 작성 안내 (33쪽) |
| [과제 제안서](docs/pdf/proposal.pdf) | 배틀코드형 과제 제안과 평가 방식 (23쪽) |

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
  viewer/          리플레이 뷰어 (viewer.html, 3D 는 view3d.js)
bots/
  starter/main.py  시작용 봇 (복사해서 고쳐 쓴다)
  random/main.py   무작위 봇 (기준선)
  logic/main.py    추론 예시 봇 (명제논리 · 대칭 추론 · A*)
maps/              맵 10개 (*.json)
demo/              미리 만든 리플레이
docs/              설명서와 그림
tests/             기본 점검 (python -m unittest discover tests)
```

## 쓴 오픈소스

- 3D 뷰어: [three.js](https://threejs.org) 0.160 (MIT 라이선스). 인터넷 (jsDelivr CDN) 에서 불러온다. 인터넷이 없으면 2D 뷰로 저절로 바뀐다.
- 글꼴: Cinzel, Noto Serif KR (SIL Open Font License, Google Fonts).
- 캐릭터 · 야영지 · 웜퍼스 · 동굴 그림: [Liberated Pixel Cup (LPC)](https://lpc.opengameart.org) 공개 그림 (CC-BY-SA 3.0 / 4.0, GPL, OGA-BY, CC-BY). 합성 도구 `tools/lpc_build.py`, 만든 사람 표기 [`wumpus/viewer/sprites/CREDITS.md`](wumpus/viewer/sprites/CREDITS.md).
- 효과음은 코드로 만들었다.
