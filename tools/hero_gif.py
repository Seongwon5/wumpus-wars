"""README 의 움직이는 대표 그림 (docs/images/hero.gif) 을 만든다.

python -X utf8 tools/hero_gif.py <리플레이.html> [시작 라운드=240] [라운드 수=8]

화면에 띄우지 않는 Chrome (headless) 으로 리플레이를 라운드를 조금씩 넘기며 찍고, GIF 로 묶는다.
- 리플레이 주소 뒤의 `#r=240.5&cam=x,y,거리` 로 라운드 (소수면 라운드 사이) 와 카메라를 정한다.
- 파일을 작게: 앞 장과 눈에 띄게 달라진 점만 다시 그린다 (깜빡이는 잡음은 버린다).
필요: Chrome, Pillow, numpy.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = os.environ.get('CHROME', r'C:\Program Files\Google\Chrome\Application\chrome.exe')
STEP, CAM, SIZE, CROP = 0.125, '11.5,10.5,25', (1600, 1000), (35, 262, 1245, 950)   # 한 장에 0.125 라운드, 지도 칸만 잘라 쓴다
WIDTH, COLORS, TOL, FRAME_MS, JOBS = 800, 256, 14, 80, 4


def shoot(url, out, profile):
    return subprocess.Popen([CHROME, '--headless=new', '--disable-extensions', '--hide-scrollbars', '--user-data-dir=' + profile,
                             '--window-size=%d,%d' % SIZE, '--virtual-time-budget=2500', '--screenshot=' + out, url],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    html = pathlib.Path(sys.argv[1]).resolve().as_uri()
    r0 = float(sys.argv[2]) if len(sys.argv) > 2 else 240
    n = int((float(sys.argv[3]) if len(sys.argv) > 3 else 8) / STEP)
    tmp = tempfile.mkdtemp(prefix='hero_gif_')
    files = [os.path.join(tmp, 'f%03d.png' % i) for i in range(n)]
    for b in range(0, n, JOBS):                                  # 몇 장씩 한꺼번에 찍는다
        ps = [shoot('%s#r=%s&cam=%s' % (html, r0 + i * STEP, CAM), files[i], os.path.join(tmp, 'p%d' % (i % JOBS))) for i in range(b, min(n, b + JOBS))]
        for p in ps:
            p.wait()
    h = round(WIDTH * (CROP[3] - CROP[1]) / (CROP[2] - CROP[0]))
    fr = [Image.open(f).convert('RGB').crop(CROP).resize((WIDTH, h), Image.LANCZOS) for f in files]
    strip = Image.new('RGB', (WIDTH, h * 8))                     # 모든 장이 같은 색을 쓰게 여덟 장으로 팔레트를 만든다
    for k, i in enumerate(range(0, n, max(1, n // 8))[:8]):
        strip.paste(fr[i], (0, h * k))
    pal = strip.quantize(COLORS - 1, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    P = np.array(pal.getpalette()[:(COLORS - 1) * 3], dtype=np.int16).reshape(-1, 3)
    T, frames, shown = COLORS - 1, [], None                      # T = 투명 (앞 장 그대로)
    for f in fr:
        qi = np.array(f.quantize(palette=pal, dither=Image.Dither.NONE))
        rgb = P[qi]
        if shown is None:
            b, shown = qi, rgb.copy()
        else:
            mask = np.abs(rgb - shown).max(axis=2) > TOL
            b = np.where(mask, qi, T)
            shown[mask] = rgb[mask]
        im = Image.fromarray(b.astype(np.uint8), 'P')
        im.putpalette(pal.getpalette())
        frames.append(im)
    out = os.path.join(ROOT, 'docs', 'images', 'hero.gif')
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=FRAME_MS, loop=0, optimize=False, transparency=T, disposal=1)
    print('저장: %s (%d장, %.1f MB)' % (out, n, os.path.getsize(out) / 1e6))


if __name__ == '__main__':
    main()
