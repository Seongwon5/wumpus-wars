"""docs 의 마크다운을 PDF 로 바꾼다 (규칙서 · API 안내서 배포용).

python -X utf8 tools/md2pdf.py docs/RULES.md docs/pdf/rulebook.pdf "웜퍼스 워즈 게임 규칙서"

필요: reportlab (pip install reportlab), 한글 글꼴 (Windows 의 맑은 고딕). 게임 자체에는 필요 없다.
지원: # 제목, 문단, - 목록, 1. 목록, 표 (| ... |), ``` 코드 ```, `코드`, **굵게**, [글](주소) 링크 글자.
"""
import html
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_DIR = os.environ.get('WINDIR', r'C:\Windows') + r'\Fonts'
pdfmetrics.registerFont(TTFont('Malgun', os.path.join(FONT_DIR, 'malgun.ttf')))
pdfmetrics.registerFont(TTFont('MalgunB', os.path.join(FONT_DIR, 'malgunbd.ttf')))
pdfmetrics.registerFontFamily('Malgun', normal='Malgun', bold='MalgunB', italic='Malgun', boldItalic='MalgunB')

INK, ACC = colors.HexColor('#2a2018'), colors.HexColor('#9a6a1a')
ST = {
    'title': ParagraphStyle('t', fontName='MalgunB', fontSize=20, leading=26, textColor=ACC, spaceAfter=10),
    'h1': ParagraphStyle('h1', fontName='MalgunB', fontSize=17, leading=23, textColor=ACC, spaceBefore=6, spaceAfter=8),
    'h2': ParagraphStyle('h2', fontName='MalgunB', fontSize=13.5, leading=19, textColor=ACC, spaceBefore=10, spaceAfter=5),
    'h3': ParagraphStyle('h3', fontName='MalgunB', fontSize=11.5, leading=16, textColor=INK, spaceBefore=6, spaceAfter=3),
    'p': ParagraphStyle('p', fontName='Malgun', fontSize=9.6, leading=15, textColor=INK, alignment=TA_LEFT, spaceAfter=4),
    'li': ParagraphStyle('li', fontName='Malgun', fontSize=9.6, leading=14.5, textColor=INK, leftIndent=12, bulletIndent=2, spaceAfter=2),
    'cell': ParagraphStyle('c', fontName='Malgun', fontSize=8.6, leading=12, textColor=INK),
    'cellb': ParagraphStyle('cb', fontName='MalgunB', fontSize=8.6, leading=12, textColor=colors.white),
    'code': ParagraphStyle('code', fontName='Malgun', fontSize=8.2, leading=11.5, textColor=colors.HexColor('#1e2a36'),
                           backColor=colors.HexColor('#eef2f5'), borderPadding=5, leftIndent=4, spaceBefore=3, spaceAfter=7),
}


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', t)                       # 그림은 뺀다
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)                    # 링크는 글자만
    t = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'`([^`]+)`', r'<font color="#7a3a10">\1</font>', t)
    return t


def table(lines, width):
    rows = [[c.strip() for c in l.strip().strip('|').split('|')] for l in lines if not re.match(r'^\s*\|[\s:|-]+\|\s*$', l)]
    n = max(len(r) for r in rows)
    data = [[Paragraph(inline(c), ST['cellb'] if i == 0 else ST['cell']) for c in r + [''] * (n - len(r))] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[width / n] * n, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6a4a1a')),
                           ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f1e6')]),
                           ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#c8b48c')),
                           ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    return t


def convert(src, dst, title):
    lines = open(src, encoding='utf-8').read().splitlines()
    doc = SimpleDocTemplate(dst, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=title)
    W = A4[0] - 36 * mm
    out, i = [], 0
    if title:
        out.append(Paragraph(html.escape(title), ST['title']))
    while i < len(lines):
        l = lines[i]
        if l.startswith('```'):
            j = i + 1
            while j < len(lines) and not lines[j].startswith('```'):
                j += 1
            out.append(Preformatted('\n'.join(lines[i + 1:j]), ST['code']))
            i = j + 1
            continue
        if l.strip().startswith('|'):
            j = i
            while j < len(lines) and lines[j].strip().startswith('|'):
                j += 1
            out.append(table(lines[i:j], W))
            out.append(Spacer(1, 6))
            i = j
            continue
        m = re.match(r'^(#{1,3})\s+(.*)', l)
        if m:
            lvl = len(m.group(1))
            if not (lvl == 1 and title):
                out.append(Paragraph(inline(m.group(2)), ST['h%d' % lvl]))
        elif re.match(r'^\s*[-*]\s+', l):
            ind = len(l) - len(l.lstrip())
            st = ParagraphStyle('li%d' % ind, parent=ST['li'], leftIndent=12 + ind * 5, bulletIndent=2 + ind * 5)
            out.append(Paragraph(inline(re.sub(r'^\s*[-*]\s+', '', l)), st, bulletText='•'))
        elif re.match(r'^\s*\d+\.\s+', l):
            num = re.match(r'^\s*(\d+)\.', l).group(1)
            out.append(Paragraph(inline(re.sub(r'^\s*\d+\.\s+', '', l)), ST['li'], bulletText=num + '.'))
        elif l.strip() and not l.strip().startswith('!['):
            out.append(Paragraph(inline(l), ST['p']))
        i += 1
    doc.build(out)


if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '')
    print('ok', sys.argv[2])
