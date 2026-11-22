"""학위논문 양식 PDF 조판기 (규칙서 · API 가이드북). tools/md2thesis.py 가 docs 의 마크다운을 이것으로 찍는다.

필요: Google Chrome (헤드리스 인쇄), PyMuPDF (pip install pymupdf), 함초롬바탕 또는 바탕 글꼴.

본문을 장 · 절 · 그림 · 표 단위로 적으면, 번호를 저절로 매기고
HTML -> (헤드리스 Chrome) PDF 로 찍은 뒤, PyMuPDF 로 쪽 번호와 목차 쪽수를 채운다.
"""
import html
import os
import subprocess

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import pathlib
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, 'docs', 'images')                      # 그림은 docs/images 에서
HERE = os.path.join(tempfile.gettempdir(), 'wumpus_thesis')           # 중간 html · pdf
CHROME = os.environ.get('CHROME', r"C:\Program Files\Google\Chrome\Application\chrome.exe")

CSS = r"""
@page { size: A4; margin: 30mm 25mm 25mm 30mm; }
@page cover { margin: 0; }
* { box-sizing: border-box; }
html { font-family: "HCR Batang", "함초롬바탕", "Batang", serif; font-size: 10.5pt; line-height: 1.8; color: #111; }
body { margin: 0; }
.mk { color: #fff; font-size: 1px; line-height: 1px; letter-spacing: 0 !important; }
p { margin: 0 0 0.35em; text-align: justify; text-indent: 1em; word-break: keep-all; }
p.ni { text-indent: 0; }
h1.ch { page-break-before: always; text-align: center; font-size: 17pt; font-weight: bold; margin: 18mm 0 12mm; letter-spacing: .05em; line-height: 1.5; }
h1.ch .no { display: block; font-size: 13pt; letter-spacing: .3em; margin-bottom: 2mm; }
h1.fm { page-break-before: always; text-align: center; font-size: 16pt; font-weight: bold; margin: 6mm 0 10mm; letter-spacing: .5em; }
h2.sec { font-size: 13pt; font-weight: bold; margin: 7mm 0 2.5mm; page-break-after: avoid; }
h3.sub { font-size: 11.5pt; font-weight: bold; margin: 5mm 0 2mm; page-break-after: avoid; }
figure { margin: 5mm 0 6mm; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; border: 0.3mm solid #999; }
figure svg { max-width: 100%; }
figcaption { font-size: 9.5pt; margin-top: 2mm; text-align: center; }
.tbl { margin: 5mm 0 6mm; page-break-inside: avoid; }
.tcap { font-size: 9.5pt; text-align: center; margin-bottom: 1.5mm; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; line-height: 1.5; border-top: 0.5mm solid #000; border-bottom: 0.5mm solid #000; }
th { border-bottom: 0.25mm solid #000; padding: 1.4mm 2mm; background: #f1f1f1; font-weight: bold; }
td { border-bottom: 0.1mm solid #bbb; padding: 1.2mm 2mm; vertical-align: top; word-break: keep-all; }
td code, p code, li code { font-family: Consolas, "Malgun Gothic", monospace; font-size: 8.6pt; background: #f3f3f3; padding: 0 .6mm; }
pre { font-family: Consolas, "Malgun Gothic", monospace; font-size: 8.3pt; line-height: 1.45; background: #f6f6f6; border: 0.2mm solid #ccc;
      border-left: 1mm solid #777; padding: 2.5mm 3.5mm; margin: 3mm 0 4mm; white-space: pre-wrap; page-break-inside: avoid; }
ul, ol { margin: 0 0 0.5em 1.2em; padding-left: 1em; }
li { margin: 0.1em 0; text-align: justify; word-break: keep-all; }
.note { border: 0.3mm solid #999; background: #fafafa; padding: 2.5mm 4mm; margin: 3mm 0 4mm; font-size: 9.6pt; page-break-inside: avoid; }
.note b.t { display: block; margin-bottom: 1mm; }
/* 표지 */
.cover { page: cover; height: 297mm; padding: 38mm 28mm 30mm; display: flex; flex-direction: column; align-items: center; text-align: center; }
.cover .kind { font-size: 12pt; letter-spacing: .4em; margin-bottom: 26mm; }
.cover .rule { width: 130mm; border-top: 0.8mm solid #000; border-bottom: 0.25mm solid #000; height: 1.6mm; }
.cover .title { font-size: 25pt; font-weight: bold; margin: 9mm 0 3mm; line-height: 1.45; letter-spacing: .04em; }
.cover .etitle { font-size: 12.5pt; font-style: italic; margin-bottom: 9mm; }
.cover .ver { margin-top: 10mm; font-size: 11pt; }
.cover .spacer { flex: 1; }
.cover .date { font-size: 13pt; letter-spacing: .2em; margin-bottom: 9mm; }
.cover .who { font-size: 13pt; line-height: 2.1; }
.cover .who .line { display: inline-block; min-width: 45mm; border-bottom: 0.25mm solid #000; }
/* 목차 */
.toc { font-size: 10.5pt; }
.toc .row { display: flex; align-items: baseline; margin: 0.25em 0; }
.toc .row .t { flex: none; max-width: 85%; }
.toc .row .d { flex: 1; border-bottom: 0.35mm dotted #333; margin: 0 2mm; transform: translateY(-1.2mm); }
.toc .row .n { flex: none; min-width: 7mm; text-align: right; }
.toc .l1 { font-weight: bold; margin-top: 0.7em; }
.toc .l2 { padding-left: 6mm; }
.toc .l3 { padding-left: 12mm; font-size: 10pt; }
.abs p { text-indent: 1em; }
.kw { margin-top: 5mm; text-indent: 0; }
.refs p { text-indent: -2em; padding-left: 2em; }
"""


def esc(s):
    return html.escape(s, quote=False)


def inline(s):
    """`코드` 와 **굵게** 를 바꾼다. 나머지는 이스케이프."""
    out, i = [], 0
    s = esc(s)
    import re
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    return s


class Doc:
    def __init__(self, title, etitle, kind, version, date):
        self.title, self.etitle, self.kind, self.version, self.date = title, etitle, kind, version, date
        self.parts = []          # 본문 html 조각
        self.heads = []          # (level, text, marker)
        self.figs = []           # (label, caption, marker)
        self.tbls = []
        self.ch_no = 0; self.sec_no = 0; self.sub_no = 0; self.fig_no = 0; self.tbl_no = 0
        self.appendix = False; self.app_letter = 'A'
        self.mk = 0
        self.abstract = []; self.keywords = ''

    def _mark(self):
        self.mk += 1
        return f'zqm{self.mk:03d}zq'

    def chapter(self, title, unnumbered=False):
        m = self._mark()
        if unnumbered:
            self.parts.append(f'<h1 class="ch"><span class="mk">{m}</span>{esc(title)}</h1>')
            self.heads.append((1, title, m))
            self.ch_no_label = None
            return
        if self.appendix:
            lab = self.app_letter; self.app_letter = chr(ord(self.app_letter) + 1)
            no = f'부록 {lab}'
        else:
            self.ch_no += 1; lab = str(self.ch_no); no = f'제 {lab} 장'
        self.cur = lab; self.sec_no = 0; self.fig_no = 0; self.tbl_no = 0
        self.parts.append(f'<h1 class="ch"><span class="mk">{m}</span><span class="no">{no}</span>{esc(title)}</h1>')
        self.heads.append((1, f'{no}  {title}', m))

    def section(self, title):
        self.sec_no += 1; self.sub_no = 0
        m = self._mark(); lab = f'{self.cur}.{self.sec_no}'
        self.parts.append(f'<h2 class="sec"><span class="mk">{m}</span>{lab} {esc(title)}</h2>')
        self.heads.append((2, f'{lab} {title}', m))

    def sub(self, title):
        self.sub_no += 1
        m = self._mark(); lab = f'{self.cur}.{self.sec_no}.{self.sub_no}'
        self.parts.append(f'<h3 class="sub"><span class="mk">{m}</span>{lab} {esc(title)}</h3>')
        self.heads.append((3, f'{lab} {title}', m))

    def p(self, *texts, ni=False):
        for t in texts:
            self.parts.append(f'<p{" class=ni" if ni else ""}>{inline(t)}</p>')

    def ul(self, items, ordered=False):
        tag = 'ol' if ordered else 'ul'
        self.parts.append(f'<{tag}>' + ''.join(f'<li>{inline(i)}</li>' for i in items) + f'</{tag}>')

    def code(self, text):
        self.parts.append(f'<pre>{esc(text.strip(chr(10)))}</pre>')

    def note(self, title, text):
        self.parts.append(f'<div class="note"><b class="t">{esc(title)}</b>{inline(text)}</div>')

    def raw(self, h):
        self.parts.append(h)

    def fig(self, src, caption, width=None, svg=None):
        self.fig_no += 1
        lab = f'[그림 {self.cur}-{self.fig_no}]'
        m = self._mark()
        body = svg if svg else f'<img src="{pathlib.Path(IMG_DIR, src).as_uri()}"' + (f' style="width:{width}"' if width else '') + '>'
        self.parts.append(f'<figure>{body}<figcaption><span class="mk">{m}</span>{lab} {inline(caption)}</figcaption></figure>')
        self.figs.append((lab, caption, m))
        return lab

    def table(self, caption, headers, rows, widths=None):
        self.tbl_no += 1
        lab = f'<표 {self.cur}-{self.tbl_no}>'
        m = self._mark()
        cg = ''
        if widths:
            cg = '<colgroup>' + ''.join(f'<col style="width:{w}">' for w in widths) + '</colgroup>'
        th = ''.join(f'<th>{inline(h)}</th>' for h in headers)
        trs = ''.join('<tr>' + ''.join(f'<td>{inline(str(c))}</td>' for c in r) + '</tr>' for r in rows)
        self.parts.append(f'<div class="tbl"><div class="tcap"><span class="mk">{m}</span>{esc(lab)} {inline(caption)}</div>'
                          f'<table>{cg}<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')
        self.tbls.append((lab, caption, m))
        return lab

    def start_appendix(self):
        self.appendix = True

    # ---------------- 조판 ----------------
    def _page(self, body, name):
        os.makedirs(HERE, exist_ok=True)
        path = os.path.join(HERE, name + '.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>')
        pdf = os.path.join(HERE, name + '.pdf')
        subprocess.run([CHROME, '--headless=new', f'--user-data-dir={HERE}/chprof', '--no-first-run', '--no-pdf-header-footer',
                        '--allow-file-access-from-files', '--virtual-time-budget=6000', f'--print-to-pdf={pdf}', pathlib.Path(path).as_uri()],
                       check=True, capture_output=True, timeout=120)
        return pdf

    def _find(self, pdf, items):
        doc = fitz.open(pdf)
        out = {}
        for pno in range(len(doc)):
            txt = doc[pno].get_text()
            for _, _, m in items:
                if m not in out and m in txt:
                    out[m] = pno
        doc.close()
        return out

    def _front(self, pages):
        def rows(items, cls):
            r = ''
            for it in items:
                lvl, text, m = it if len(it) == 3 and isinstance(it[0], int) else (None, f'{it[0]} {it[1]}', it[2])
                c = cls or f'l{lvl}'
                n = pages.get(m, 0) + 1
                r += f'<div class="row {c}"><span class="t">{inline(text)}</span><span class="d"></span><span class="n">{n}</span></div>'
            return r
        cover = (f'<section class="cover"><div class="kind">{esc(self.kind)}</div><div class="rule"></div>'
                 f'<div class="title">{esc(self.title)}</div><div class="etitle">{esc(self.etitle)}</div><div class="rule"></div>'
                 f'<div class="ver">{esc(self.version)}</div><div class="spacer"></div><div class="date">{esc(self.date)}</div>'
                 f'<div class="who">인공지능개론<br>작성자 &nbsp;2024315734 &nbsp;황 성 원</div></section>')
        absx = ''.join(f'<p>{inline(t)}</p>' for t in self.abstract)
        abstract = (f'<h1 class="fm" style="page-break-before:auto">요 약</h1><div class="abs">{absx}'
                    f'<p class="kw"><b>주제어</b>: {esc(self.keywords)}</p></div>')
        toc = f'<h1 class="fm">목 차</h1><div class="toc">{rows(self.heads, None)}</div>'
        tl = f'<h1 class="fm">표 목차</h1><div class="toc">{rows(self.tbls, "l2")}</div>' if self.tbls else ''
        fl = f'<h1 class="fm">그림 목차</h1><div class="toc">{rows(self.figs, "l2")}</div>' if self.figs else ''
        return cover, abstract + toc + tl + fl

    def build(self, out_pdf, name):
        body_pdf = self._page(''.join(self.parts), name + '_body')
        pages = self._find(body_pdf, self.heads + self.figs + self.tbls)
        missing = [m for *_, m in self.heads + self.figs + self.tbls if m not in pages]
        if missing:
            print('경고: 쪽을 못 찾은 표시', missing[:5])
        cover, front = self._front(pages)
        cover_pdf = self._page(cover, name + '_cover')
        front_pdf = self._page(front, name + '_front')
        out = fitz.open()
        for p in (cover_pdf, front_pdf, body_pdf):
            with fitz.open(p) as d:
                out.insert_pdf(d)
        nc = len(fitz.open(cover_pdf)); nf = len(fitz.open(front_pdf))
        roman = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii']
        for i in range(nc, len(out)):
            pg = out[i]
            lab = roman[i - nc] if i < nc + nf else str(i - nc - nf + 1)
            w = fitz.get_text_length(f'- {lab} -', fontname='tiro', fontsize=10)
            pg.insert_text(((pg.rect.width - w) / 2, pg.rect.height - 12 * 2.835), f'- {lab} -', fontname='tiro', fontsize=10)
        # 책갈피 (PDF 목차)
        toc = [[lvl, text, pages.get(m, 0) + nc + nf + 1] for lvl, text, m in self.heads]
        out.set_toc(toc)
        out.set_metadata({'title': self.title, 'subject': self.etitle, 'creator': 'Wumpus Wars docs builder'})
        out.save(out_pdf, garbage=3, deflate=True)
        print(f'저장: {out_pdf} ({len(out)}쪽: 표지 {nc}, 앞부분 {nf}, 본문 {len(out) - nc - nf})')
