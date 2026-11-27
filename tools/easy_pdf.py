"""docs/EASY.md 를 A4 두 쪽 인쇄용 PDF (docs/pdf/easy.pdf) 로 찍는다.

    python tools/easy_pdf.py

움직이는 GIF 대신 같은 이름의 PNG (대표 장면) 를 넣는다. Chrome (headless) 과 `markdown` 패키지가 필요하다.
"""
import os
import pathlib
import re
import shutil
import subprocess

import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs'
REPO_URL = 'https://github.com/Seongwon5/wumpus-wars'

CSS = """
@page { size: A4; margin: 13mm 14mm 12mm; }
* { box-sizing: border-box; }
body { font-family: 'Noto Sans CJK KR', 'Malgun Gothic', sans-serif; font-size: 9.2pt; line-height: 1.45; color: #222; margin: 0; }
h1 { font-size: 17pt; margin: 0 0 2mm; color: #3a3029; }
h1 small { font-size: 9pt; font-weight: normal; color: #777; margin-left: 3mm; }
blockquote { margin: 0 0 3mm; padding: 2mm 4mm; background: #f6f0e4; border-left: 1.2mm solid #d6483f; border-radius: 1.5mm; }
blockquote p { margin: 0; }
h2 { font-size: 11.5pt; margin: 2.6mm 0 1.2mm; padding-bottom: .8mm; border-bottom: .4mm solid #e2d6c0; color: #3a3029; clear: both; }
p { margin: 1mm 0; }
ul { margin: 1mm 0; padding-left: 5mm; }
li { margin: .4mm 0; }
img.fig { float: right; width: 43%; margin: 0 0 1.5mm 4mm; border: .3mm solid #ddd; border-radius: 1.5mm; }
p.figp { margin: 0; }
table { border-collapse: collapse; font-size: 8.6pt; margin: 1mm 0; }
th, td { border-bottom: .2mm solid #ddd; padding: .6mm 2mm; text-align: left; vertical-align: top; }
th { background: #f1e9da; }
code { font-family: 'DejaVu Sans Mono', Consolas, 'Noto Sans Mono CJK KR', monospace; font-size: 8.4pt; background: #f3eee6; padding: 0 .8mm; border-radius: .8mm; }
pre { background: #2d2a32; color: #f1ece4; border-radius: 1.5mm; padding: 2mm 3mm; margin: 1.5mm 0; line-height: 1.3; white-space: pre; overflow: hidden; }
pre code { background: none; color: inherit; font-size: 6.9pt; padding: 0; line-height: 1.2; display: block; }
pre.cmd code { font-size: 8pt; }
a { color: #2f5fa8; text-decoration: none; }
.page2 { break-before: page; margin-top: 0; }
.page2 ~ p.figp img.fig { width: 37%; }
.note { font-size: 8.4pt; color: #777; }
"""


def build():
    md = (DOCS / 'EASY.md').read_text(encoding='utf-8')
    html = markdown.markdown(md, extensions=['tables', 'fenced_code'])
    # GIF → 대표 장면 PNG, 오른쪽에 띄운다
    html = re.sub(r'<p><img alt="([^"]*)" src="images/easy/([^"]+)\.gif" /></p>',
                  lambda m: f'<p class="figp"><img class="fig" alt="{m.group(1)}" src="{DOCS}/images/easy/{m.group(2)}.png"></p>', html)
    html = html.replace('<h1>웜퍼스 워즈 쉽게 보기</h1>',
                        f'<h1>웜퍼스 워즈 쉽게 보기<small>움직이는 그림: {REPO_URL} → docs/EASY.md</small></h1>')
    html = html.replace('<h2>4. ', '<h2 class="page2">4. ', 1)          # 2쪽은 4절부터
    # 명령 블록 (bash) 은 조금 크게
    html = re.sub(r'<pre><code class="language-bash">', '<pre class="cmd"><code class="language-bash">', html)
    page = f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{html}</body></html>'
    tmp = ROOT / 'docs' / 'pdf' / '_easy.html'
    tmp.write_text(page, encoding='utf-8')
    out = ROOT / 'docs' / 'pdf' / 'easy.pdf'
    chrome = shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chrome')
    subprocess.run([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-pdf-header-footer',
                    f'--print-to-pdf={out}', tmp.as_uri()], check=True, capture_output=True)
    tmp.unlink()
    print(out)


if __name__ == '__main__':
    build()
