"""docs 의 마크다운을 학위논문 양식 PDF 로 찍는다 (규칙서 · API 가이드북).

python -X utf8 tools/md2thesis.py rulebook      # docs/pdf/rulebook.pdf
python -X utf8 tools/md2thesis.py guidebook     # docs/pdf/api_guidebook.pdf
python -X utf8 tools/md2thesis.py all

마크다운 한 파일이면 `##` 가 장, `###` 가 절이다. 여러 파일이면 파일 하나가 장, `##` 가 절, `###` 가 소절이다.
표는 바로 위 제목을 캡션으로, `![캡션](images/그림)` 은 번호 붙은 그림이 된다. 장 · 절 앞의 번호 (`3.`) 는 떼고 새로 매긴다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thesis import Doc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')

REFS = ('<div class="refs">'
        '<p>Russell, S. and Norvig, P. (2021). <i>Artificial Intelligence: A Modern Approach</i>, 4th ed. Pearson. 제 7 장 (논리적 에이전트, Wumpus 세계).</p>'
        '<p>Yob, G. (1973). Hunt the Wumpus. <i>Creative Computing</i>.</p>'
        '<p>MIT Battlecode. https://battlecode.org</p>'
        '<p>Liberated Pixel Cup (LPC). https://lpc.opengameart.org (CC-BY-SA 3.0 / 4.0, GPL, OGA-BY)</p>'
        '<p>three.js. https://threejs.org (MIT License)</p>'
        '<p>웜퍼스 워즈 저장소. https://github.com/Seongwon5/wumpus-wars</p></div>')

BOOKS = {
    'rulebook': dict(
        files=['RULES.md'], out='rulebook.pdf',
        title='웜퍼스 워즈 게임 규칙서', etitle='Wumpus Wars: Official Rulebook',
        abstract=[
            '본 규칙서는 인공지능개론 기말 과제용 봇 대전 게임 「웜퍼스 워즈 (Wumpus Wars)」의 규칙을 정리한 문서이다. 이 게임은 수업에서 다루는 웜퍼스 월드 (Wumpus World) 를 두 팀이 겨루는 게임으로 옮긴 것으로, 학생은 사람이 직접 조작하지 않고 자기 팀 모험가를 움직이는 봇 프로그램만을 작성한다.',
            '유닛은 검을 든 모험가 한 가지뿐이며, 모험가는 자기 칸만 느낀다. 바람 · 악취 · 반짝임 · 부딪힘 · 비명이라는 교과서의 다섯 지각에, 두 팀 게임을 위한 발소리 · 아픔 · 열기 · 외침을 더했다. 적 야영지의 위치도 알려 주지 않으므로 맵 대칭과 열기로 찾아야 한다. 구덩이 · 웜퍼스 · 금맥 · 적 모험가는 화면에 보이지 않으므로, 봇은 지각을 기억하고 추론하여 안전한 길과 금의 위치를 알아내야 한다.',
            '경기는 적 야영지를 부수거나 1000 라운드가 끝났을 때 바친 금이 많은 쪽이 이긴다. 본 문서는 목표, 맵, 모험가, 지각, 구덩이, 웜퍼스, 금, 야영지, 행동, 차례 순서, 공유 메모리, 공정성을 차례로 다루고, 마지막 장에 모든 수치를 정리한다.',
        ],
        keywords='웜퍼스 월드, 명제논리, 부분 관측, 지각 추론, 봇 대전, 배틀코드'),
    'guidebook': dict(
        files=['GETTING_STARTED.md', 'API.md', 'SCRIM.md', 'REPLAY.md', 'MAPS.md'], out='api_guidebook.pdf',
        title='웜퍼스 워즈 봇 API 가이드북', etitle='Wumpus Wars: Bot API Guidebook',
        abstract=[
            '본 가이드북은 「웜퍼스 워즈」의 봇을 작성하는 데 필요한 모든 것을 정리한 문서이다. 봇은 Python 파일 하나이며, 엔진이 모험가와 야영지마다 차례가 올 때 `turn(me, view, memory)` 함수를 불러 행동 하나를 받는다.',
            '제 1 장은 설치와 첫 경기, 내 봇을 만들고 고치는 순서를 안내한다. 제 2 장은 봇 API 를 다룬다: 모험가가 자기 칸에서 받는 아홉 가지 지각, 행동, 팀 공유 메모리, 디버그 표시, 도우미 함수, 오류와 시간 규칙이다. 제 3 장과 제 4 장은 여러 맵에서 승률을 재는 스크림 도구와 경기를 다시 보는 리플레이 뷰어를, 제 5 장은 맵 파일과 맵 생성기를 설명한다.',
        ],
        keywords='봇 API, 지각, 공유 메모리, 스크림, 리플레이, 웜퍼스 월드'),
}


def strip_no(t):
    return re.sub(r'^\d+(\.\d+)*\.?\s+', '', t.strip())


def clean(t):
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)          # 링크는 글자만
    return t


def parse_table(lines):
    rows = [[clean(c.strip()) for c in l.strip().strip('|').split('|')] for l in lines if not re.match(r'^\s*\|[\s:|-]+\|\s*$', l)]
    n = max(len(r) for r in rows)
    rows = [r + [''] * (n - len(r)) for r in rows]
    return rows[0], rows[1:]


def feed(d, path, multi):
    lines = open(path, encoding='utf-8').read().splitlines()
    cap = ''                                                  # 표 캡션으로 쓸 가장 가까운 제목
    para = []

    pre = []                                                  # 첫 장 앞의 머리말: 첫 장 제목 바로 뒤에 넣는다 (쪽 하나를 혼자 차지하지 않게)

    def flush():
        if para:
            t = clean(' '.join(x.strip() for x in para))
            (pre.append(t) if not multi and not d.heads else d.p(t))
            para.clear()

    i = 0
    while i < len(lines):
        l = lines[i]
        m = re.match(r'^(#{1,4})\s+(.*)', l)
        if m:
            flush()
            lvl, t = len(m.group(1)), strip_no(clean(m.group(2)).replace('`', ''))
            if multi:
                {1: d.chapter, 2: d.section, 3: d.sub}.get(lvl, d.sub)(t)
            elif lvl == 1:
                pass                                          # 문서 제목은 표지에
            else:
                {2: d.chapter, 3: d.section, 4: d.sub}[lvl](t)
                if pre:
                    d.p(*pre)
                    pre.clear()
            cap = t
            i += 1
            continue
        if l.startswith('```'):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].startswith('```'):
                j += 1
            d.code('\n'.join(lines[i + 1:j]))
            i = j + 1
            continue
        if l.strip().startswith('|'):
            flush()
            j = i
            while j < len(lines) and lines[j].strip().startswith('|'):
                j += 1
            head, rows = parse_table(lines[i:j])
            d.table(cap, head, rows)
            i = j
            continue
        m = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)', l.strip())
        if m:
            flush()
            d.fig(os.path.basename(m.group(2)), m.group(1), '150mm')
            i += 1
            continue
        if re.match(r'^\s*([-*]|\d+\.)\s+', l):
            flush()
            ordered = bool(re.match(r'^\s*\d+\.', l))
            items = []
            while i < len(lines) and (re.match(r'^\s*([-*]|\d+\.)\s+', lines[i]) or (lines[i].startswith('  ') and lines[i].strip() and items)):
                if re.match(r'^\s*([-*]|\d+\.)\s+', lines[i]):
                    items.append(clean(re.sub(r'^\s*([-*]|\d+\.)\s+', '', lines[i])))
                else:
                    items[-1] += ' ' + clean(lines[i].strip())
                i += 1
            d.ul(items, ordered)
            continue
        if not l.strip():
            flush()
        elif l.strip().startswith('>'):
            flush()
            d.note('참고', clean(l.strip().lstrip('> ')))
        else:
            para.append(l)
        i += 1
    flush()


def build(name):
    b = BOOKS[name]
    d = Doc(b['title'], b['etitle'], '인공지능개론 기말 과제 자료', '제 0.3 판', '2026년 11월')
    d.abstract, d.keywords = b['abstract'], b['keywords']
    multi = len(b['files']) > 1
    for f in b['files']:
        feed(d, os.path.join(DOCS, f), multi)
    d.chapter('참고문헌', unnumbered=True)
    d.raw(REFS)
    out = os.path.join(DOCS, 'pdf', b['out'])
    d.build(out, name)
    return out


if __name__ == '__main__':
    for n in (BOOKS if sys.argv[1:] in ([], ['all']) else sys.argv[1:]):
        build(n)
