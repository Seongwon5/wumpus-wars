"""리플레이 파일 (.json) 과 뷰어 (.html) 만들기.

리플레이 .json 은 경기의 모든 라운드를 담는다. 뷰어 .html 은 그 json 을 품은 파일 하나라서
브라우저로 바로 열리고, 다른 사람에게 그대로 보낼 수 있다.
"""
import json
import os
import pathlib
import webbrowser

VIEWER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viewer')


def _template():
    with open(os.path.join(VIEWER_DIR, 'viewer.html'), encoding='utf-8') as f:
        tpl = f.read()
    with open(os.path.join(VIEWER_DIR, 'view3d.js'), encoding='utf-8') as f:
        js = f.read()
    sp = os.path.join(VIEWER_DIR, 'sprites')
    if os.path.isfile(os.path.join(sp, 'sprites.json')):          # LPC 캐릭터 시트를 html 안에 넣는다
        import base64
        meta = json.load(open(os.path.join(sp, 'sprites.json'), encoding='utf-8'))
        img = {n: 'data:image/png;base64,' + base64.b64encode(open(os.path.join(sp, n + '.png'), 'rb').read()).decode()
               for n in meta['sheets']}
        js = 'window.SPRITES = ' + json.dumps({'meta': meta, 'img': img}) + ';' + chr(10) + js
    return tpl.replace('/*VIEW3D_JS*/', js, 1)


def save_json(replay, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(replay, f, ensure_ascii=False, separators=(',', ':'))


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_html(replay, path):
    """리플레이를 품은 뷰어 html 을 쓴다. replay 가 None 이면 빈 뷰어 (json 을 끌어다 놓아 연다)."""
    html = _template()
    if replay is not None:
        data = json.dumps(replay, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
        html = html.replace('/*REPLAY_DATA*/', data, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path


def open_in_browser(path):
    webbrowser.open(pathlib.Path(os.path.abspath(path)).as_uri())
