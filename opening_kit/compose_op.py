"""4角女神 オープニング（横16:9 と 縦9:16）
1角ソラ → 2角ララン → 3角ミレイ → 4角ロゼ の順に、仕草クリップのキャラが動きながら入ってきて
カシャッと写真（ポラロイド）になって並び、最後に「4角女神！」のロゴと4人のコール。

usage:
  python3 compose_op.py --clips DIR --bgm JINGLE --out OUTDIR [--stills DIR]
  DIR には rose.mp4 / mirei.mp4 / sora.mp4 / laran.mp4（仕草クリップ 480x704）を置くか、
  CLIPS の既定ファイル名（日本語名）をそのまま使う。クリップが無いキャラは stills の透過PNGで代用。
声は同じフォルダの voice/*.wav（voice_op.py で作成）、フォントは ../../youtube/yonkaku/fonts か --fonts。
"""
import os, sys, math, argparse, subprocess, glob, io
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('--clips', default='')
ap.add_argument('--stills', default='')
ap.add_argument('--bg', default='')
ap.add_argument('--bgm', default=os.path.join(HERE, '..', '..', 'yonkaku_bgm', '01_opening_jingle.wav'))
ap.add_argument('--fonts', default=os.path.join(HERE, 'fonts') if os.path.isdir(os.path.join(HERE, 'fonts')) else os.path.join(HERE, '..', '..', 'youtube', 'yonkaku', 'fonts'))
ap.add_argument('--out', default=os.path.join(HERE, 'out'))
ap.add_argument('--only', default='HV')
ap.add_argument('--preview', action='store_true', help='低解像度で確認用')
A = ap.parse_args()
os.makedirs(A.out, exist_ok=True)
FPS = 30
F = lambda n, s: ImageFont.truetype(os.path.join(A.fonts, n), int(s))
DELA, MINCHO, ZEN = 'DelaGothic.ttf', 'ShipporiMinchoB1.ttf', 'ZenKakuGothicNew.ttf'
GOLD, GOLD2 = (233, 196, 106), (255, 231, 160)

# 登場順（1角→4角）。clip: 使う仕草クリップ / ss: 何秒目から使うか / ang: 写真の傾き
CHARS = [
    dict(key='sora', name='ソラ', corner='1角', col=(30, 136, 229), clip=['sora.mp4', 'ソラ_髪をくるくる.mp4'], ss=0.4, still='ソラ.png', ang=-6),
    dict(key='laran', name='ララン', corner='2角', col=(40, 40, 40), clip=['laran.mp4', 'ララン_ヘッドホンをつける.mp4'], ss=0.6, still='ララン.png', ang=5),
    dict(key='mirei', name='ミレイ', corner='3角', col=(251, 192, 45), clip=['mirei.mp4', 'ミレイ_コインをいじる.mp4'], ss=0.3, still='ミレイ.png', ang=-4),
    dict(key='rose', name='ロゼ', corner='4角', col=(229, 57, 53), clip=['rose.mp4', 'ロゼ_メモを取る.mp4'], ss=0.5, still='ロゼ.png', ang=2),
]
T0, STEP, ENTER = 0.35, 1.2, 0.62      # 1人目の入り / 1人あたりの間隔 / 入ってからシャッターまで
T_LOGO = T0 + STEP * 4 + 0.1           # ロゴとコール
DUR = T_LOGO + 2.3
NF = int(ENTER * FPS) + 2


def ease_out(x, p=3): x = min(max(x, 0), 1); return 1 - (1 - x) ** p
def ease_back(x, s=1.6):
    x = min(max(x, 0), 1); x -= 1; return x * x * ((s + 1) * x + s) + 1


# ---------- 素材 ----------
def find_clip(c):
    if not A.clips: return None
    for n in c['clip']:
        p = os.path.join(A.clips, n)
        if os.path.exists(p): return p
    return None


def cut_frames(c):
    """クリップ → 背景抜きフレーム（キャッシュ frames/KEY/）。無ければ静止画を少し揺らす"""
    cache = os.path.join(HERE, 'frames', c['key'])
    files = sorted(glob.glob(cache + '/*.png'))
    if len(files) >= NF: return [Image.open(f).convert('RGBA') for f in files[:NF]]
    clip = find_clip(c)
    if clip:
        from rembg import new_session, remove
        sess = new_session('isnet-anime')
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(c['ss']), '-i', clip, '-vf', f'fps={FPS}', '-frames:v', str(NF),
                              '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True).stdout
        sig = b'\x89PNG\r\n\x1a\n'; os.makedirs(cache, exist_ok=True); out = []
        for i, p in enumerate(raw.split(sig)[1:]):
            im = remove(Image.open(io.BytesIO(sig + p)).convert('RGB'), session=sess, post_process_mask=True)
            im.save(f'{cache}/{i:04d}.png'); out.append(im)
        while len(out) < NF: out.append(out[-1])
        return out
    # 静止画（640x960 などの透過PNG）→ 480x704 の枠に合わせて、ほんの少し揺らす
    p = os.path.join(A.stills, c['still']) if A.stills else ''
    if not os.path.exists(p):
        p = {'sora': 'sora2_cut.png', 'laran': 'laran_a_cut.png', 'mirei': 'mirei1_cut.png', 'rose': 'rose2_cut.png'}[c['key']]
        p = os.path.join(HERE, '..', '..', 'youtube', 'yonkaku', p)
    s = Image.open(p).convert('RGBA'); s = ImageOps.contain(s, (480, 704))
    out = []
    for i in range(NF):
        f = Image.new('RGBA', (480, 704), (0, 0, 0, 0)); a = math.sin(i / NF * math.pi) * 1.5
        r = s.rotate(a, resample=Image.BICUBIC, center=(s.width / 2, s.height))
        f.alpha_composite(r, ((480 - s.width) // 2, 704 - s.height)); out.append(f)
    return out


def gold_text(img, xy, s, font, anchor='mm', shadow=True):
    W, H = img.size
    m = Image.new('L', (W, H), 0); ImageDraw.Draw(m).text(xy, s, font=font, fill=255, anchor=anchor)
    bb = m.getbbox()
    if shadow:
        sh = Image.new('RGBA', (W, H), (0, 0, 0, 0)); sh.putalpha(m.filter(ImageFilter.GaussianBlur(font.size * .06)).point(lambda v: v * .85))
        img.alpha_composite(sh, (int(font.size * .04), int(font.size * .06)))
    gy = Image.linear_gradient('L').resize((W, bb[3] - bb[1] + 1))
    tex = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    tex.paste(Image.composite(Image.new('RGBA', gy.size, (176, 128, 48, 255)), Image.new('RGBA', gy.size, GOLD2 + (255,)), gy), (0, bb[1]))
    tex.putalpha(ImageChops.multiply(tex.getchannel('A'), m)); img.alpha_composite(tex)


def make_logo(w):
    """横長の金ロゴ（4角女神＋金の楕円＋4色の点）"""
    h = int(w * 0.42); L = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    # 暗い下地（読みやすく）
    pl = Image.new('L', (w, h), 0); ImageDraw.Draw(pl).ellipse((w * .03, h * .05, w * .97, h * .95), fill=200)
    L.alpha_composite(Image.merge('RGBA', [Image.new('L', (w, h), 8)] * 3 + [pl.filter(ImageFilter.GaussianBlur(w * .03))]))
    for k, a in ((0.0, 255), (0.025, 120)):
        d.ellipse((w * (.04 + k), h * (.07 + k * 2), w * (.96 - k), h * (.93 - k * 2)), outline=GOLD + (a,), width=max(2, w // 220))
    gold_text(L, (w * .37, h * .5), '4角', F(DELA, h * .52))
    tx = Image.new('RGBA', (w, h), (0, 0, 0, 0)); td = ImageDraw.Draw(tx)
    td.text((w * .72 + 3, h * .52 + 4), '女神', font=F(MINCHO, h * .40), anchor='mm', fill=(0, 0, 0, 170))
    td.text((w * .72, h * .52), '女神', font=F(MINCHO, h * .40), anchor='mm', fill=(250, 242, 226, 255))
    L.alpha_composite(tx)
    r = w * .018
    for (px, py), c in zip(((.1, .28), (.9, .28), (.9, .72), (.1, .72)), [ch['col'] for ch in CHARS]):
        x, y = w * px, h * py; d.ellipse((x - r * 1.3, y - r * 1.3, x + r * 1.3, y + r * 1.3), fill=GOLD + (255,))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(c if c != (40, 40, 40) else (25, 25, 25)) + (255,))
    d.text((w * .5, h * .985), 'YONKAKU  MEGAMI', font=F('Cinzel.ttf', h * .075), anchor='md', fill=GOLD2 + (235,))
    return L


def background(W, H):
    p = A.bg or next(q for q in (os.path.join(HERE, 'bg', 'keibajo.png'), os.path.join(HERE, '..', '..', 'youtube', 'yonkaku', 'bg', 'keibajo.png')) if os.path.exists(q))
    b = Image.open(p).convert('RGB'); b = ImageOps.fit(b, (W, H), centering=(0.5, 0.45))
    b = b.filter(ImageFilter.GaussianBlur(W / 160))
    b = Image.blend(b, Image.new('RGB', (W, H), (8, 10, 22)), 0.55)
    # 周辺を暗く
    v = Image.radial_gradient('L').resize((W, H)); b = Image.composite(Image.new('RGB', (W, H), (0, 0, 0)), b, v.point(lambda x: int(x * .75)))
    return b.convert('RGBA')


def photo(frame, c, w):
    """ポラロイド写真：色の背景＋止めたキャラ＋下の白余白に「1角 ソラ」"""
    pw = int(w * .9); ph = int(pw * 704 / 480); bd = (w - pw) // 2; hb = int(w * .26)
    card = Image.new('RGBA', (w, bd + ph + hb), (250, 248, 242, 255))
    col = c['col']; g = Image.linear_gradient('L').resize((pw, ph))
    inner = Image.composite(Image.new('RGBA', (pw, ph), tuple(int(v * .45) for v in col) + (255,)),
                            Image.new('RGBA', (pw, ph), tuple(min(255, int(v * .8 + 70)) for v in col) + (255,)), g)
    # 斜めの光
    sl = Image.new('L', (pw, ph), 0); ImageDraw.Draw(sl).polygon([(pw * .55, 0), (pw * .85, 0), (pw * .35, ph), (pw * .05, ph)], fill=40)
    inner.alpha_composite(Image.merge('RGBA', [Image.new('L', (pw, ph), 255)] * 3 + [sl]))
    inner.alpha_composite(frame.resize((pw, ph), Image.LANCZOS))
    card.paste(inner, (bd, bd))
    d = ImageDraw.Draw(card); ty = bd + ph + hb * .52
    tc = col if col != (40, 40, 40) else (30, 30, 30)
    d.text((w * .5, ty), f"{c['corner']}  {c['name']}", font=F(DELA, hb * .46), anchor='mm', fill=tc + (255,))
    return card


def with_shadow(card, ang):
    r = card.rotate(ang, resample=Image.BICUBIC, expand=True)
    pad = int(card.width * .08); out = Image.new('RGBA', (r.width + pad * 2, r.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new('RGBA', r.size, (0, 0, 0, 0)); sh.putalpha(r.getchannel('A').point(lambda v: v * .55))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(pad * .45)), (pad + pad // 3, pad + pad // 2))
    out.alpha_composite(r, (pad, pad)); return out


def place(img, layer, cx, cy, s=1.0, alpha=1.0):
    if s != 1.0: layer = layer.resize((max(1, int(layer.width * s)), max(1, int(layer.height * s))), Image.BILINEAR)
    if alpha < 1: layer = layer.copy(); layer.putalpha(layer.getchannel('A').point(lambda v: int(v * alpha)))
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2))) if True else None


def paste_clip(img, layer, cx, cy):
    """はみ出してもOKな貼り付け"""
    x, y = int(cx - layer.width / 2), int(cy - layer.height / 2)
    W, H = img.size; x0, y0 = max(0, x), max(0, y); x1, y1 = min(W, x + layer.width), min(H, y + layer.height)
    if x1 <= x0 or y1 <= y0: return
    img.alpha_composite(layer.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


# ---------- レイアウト ----------
def layout(W, H):
    if W > H:  # 横：左から ソラ・ロゼ・ミレイ・ララン、ロゼを少し大きく一番前
        cw = int(W * .175)
        cw = int(W * .18)
        slots = {'sora': (W * .14, H * .385, 1.0), 'rose': (W * .38, H * .375, 1.08), 'mirei': (W * .62, H * .385, 1.0), 'laran': (W * .86, H * .395, 1.0)}
        logo = (W * .5, H * .865, int(W * .34))
        big_h = H * 1.15; big_y = H * .60
    else:      # 縦：後ろに ソラ・ララン・ミレイ、前の真ん中にロゼ
        cw = int(W * .34)
        slots = {'sora': (W * .2, H * .215, .9), 'laran': (W * .5, H * .185, .9), 'mirei': (W * .8, H * .215, .9), 'rose': (W * .5, H * .565, 1.2)}
        logo = (W * .5, H * .87, int(W * .86))
        big_h = H * .78; big_y = H * .52
    return cw, slots, logo, big_h, big_y


def render(W, H, name):
    cw, slots, (lx, ly, lw), big_h, big_y = layout(W, H)
    bg = background(W, H); logo = make_logo(lw)
    frames = {c['key']: cut_frames(c) for c in CHARS}
    cards = {c['key']: with_shadow(photo(frames[c['key']][-1], c, cw), c['ang']) for c in CHARS}
    z = ['sora', 'laran', 'mirei', 'rose'] if W < H else ['sora', 'mirei', 'laran', 'rose']  # 重なり順（ロゼが一番前）
    ff = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                           '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', os.path.join(A.out, name + '_noaudio.mp4')],
                          stdin=subprocess.PIPE)
    n = int(DUR * FPS)
    rays = None
    for fi in range(n):
        t = fi / FPS; img = bg.copy()
        # ロゴ前の光の帯（各キャラ色）
        for i, c in enumerate(CHARS):
            s = T0 + STEP * i; u = (t - s) / 0.5
            if 0 <= u <= 1.6:
                a = int(150 * math.sin(min(u, 1) * math.pi) if u <= 1 else 0)
                if a > 0:
                    band = Image.new('L', (W, H), 0); x = W * (-.3 + 1.6 * ease_out(u))
                    ImageDraw.Draw(band).polygon([(x - W * .12, 0), (x + W * .05, 0), (x - W * .05, H), (x - W * .22, H)], fill=a)
                    img.alpha_composite(Image.merge('RGBA', [Image.new('L', (W, H), v) for v in c['col']] + [band.filter(ImageFilter.GaussianBlur(W / 60))]))
        # 置き終わった写真
        for k in z:
            i = [c['key'] for c in CHARS].index(k); s = T0 + STEP * i; ts = s + ENTER
            if t < ts: continue
            cx, cy, sc = slots[k]; u = (t - ts) / 0.38
            if u < 1:  # シャッター直後：大きい写真 → 定位置へ
                e = ease_back(u, 1.2); bx, by = (W * .5, big_y) if True else None
                bigs = big_h * .55 / cards[k].height * 1.6
                sc2 = bigs + (sc - bigs) * e
                place(img, cards[k], bx + (cx - bx) * ease_out(u), by + (cy - by) * ease_out(u), sc2 * (1 if W > H else 1))
            else:
                bob = math.sin((t - ts) * 2.2 + i) * H * .003 if t < T_LOGO else 0
                pop = 1 + .04 * math.sin(min(max((t - T_LOGO) / .3, 0), 1) * math.pi)
                place(img, cards[k], cx, cy + bob, sc * pop)
        # 動いて入ってくるキャラ
        for i, c in enumerate(CHARS):
            s = T0 + STEP * i
            if not (s <= t < s + ENTER): continue
            u = (t - s) / ENTER; fr = frames[c['key']][min(int((t - s) * FPS), NF - 1)]
            hh = big_h; ww = hh * 480 / 704; fr = fr.resize((int(ww), int(hh)), Image.BILINEAR)
            fade = Image.linear_gradient('L').resize((fr.width, fr.height)).point(lambda v: 255 if v < 200 else int(255 * (255 - v) / 55))
            fr.putalpha(ImageChops.multiply(fr.getchannel('A'), fade))
            side = -1 if i % 2 == 0 else 1
            x = W * .5 + side * W * .75 * (1 - ease_out(u / .7, 3)); y = big_y + H * .04 * (1 - ease_out(u))
            paste_clip(img, fr, x, y)
        # シャッターの白フラッシュ
        for i in range(4):
            ts = T0 + STEP * i + ENTER; u = (t - ts) / 0.22
            if 0 <= u < 1: img.alpha_composite(Image.new('RGBA', (W, H), (255, 255, 255, int(235 * (1 - u) ** 1.5))))
        # ロゴ
        u = (t - T_LOGO) / 0.35
        if u >= 0:
            if u < 1.3:  # 金の光
                g = Image.radial_gradient('L').resize((W, H)).point(lambda v: max(0, 255 - v * 2))
                a = int(200 * max(0, 1 - u / 1.3))
                img.alpha_composite(Image.merge('RGBA', [Image.new('L', (W, H), v) for v in GOLD2] + [g.point(lambda v: v * a // 255)]))
            sc = 1.9 - .9 * ease_back(u, 1.4) if u < 1 else 1.0
            place(img, logo, lx, ly, sc, min(1, u * 2.5))
            # きらめき
            if u > 1:
                d = ImageDraw.Draw(img); k = (t - T_LOGO - .35)
                for j, (px, py) in enumerate(((-.42, -.3), (.4, .32), (.3, -.38), (-.33, .36))):
                    ph = (k * 2.4 + j * .37) % 1.6
                    if ph < .6:
                        r = lw * .03 * math.sin(ph / .6 * math.pi); x = lx + px * lw; y = ly + py * lw * .42
                        d.polygon([(x, y - r * 2), (x + r * .35, y - r * .35), (x + r * 2, y), (x + r * .35, y + r * .35), (x, y + r * 2),
                                   (x - r * .35, y + r * .35), (x - r * 2, y), (x - r * .35, y - r * .35)], fill=GOLD2 + (255,))
        ff.stdin.write(img.convert('RGB').tobytes())
    ff.stdin.close(); ff.wait()


# ---------- 音 ----------
SR = 48000
def load_wav(p):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def trim(a, th=0.01):
    idx = np.where(np.abs(a) > th)[0]
    return a[max(0, idx[0] - 200): idx[-1] + 2400] if len(idx) else a


def sfx_shutter():
    n = int(SR * .12); rng = np.random.default_rng(1); x = rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * .012))
    y = np.zeros(int(SR * .2)); y[:n] += x * .5; m = int(SR * .07); y[m:m + n] += x * .35  # カシャッ（2回）
    return y


def sfx_whoosh(d=.45):
    n = int(SR * d); rng = np.random.default_rng(2); x = rng.standard_normal(n)
    env = np.sin(np.linspace(0, np.pi, n)) ** 2; out = np.zeros(n); a = 0.0
    for i in range(n):  # だんだん高くなるローパス
        k = .02 + .25 * i / n; a += k * (x[i] - a); out[i] = a
    return out * env * .5


def sfx_boom():
    n = int(SR * .9); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * (55 + 40 * np.exp(-t * 8)) * t) * np.exp(-t * 4.5) * .7)


def mix_audio(name):
    n = int(DUR * SR) + SR; mix = np.zeros(n)
    def add(a, t, g=1.0):
        i = int(t * SR); a = a[:max(0, n - i)]; mix[i:i + len(a)] += a * g
    V = os.path.join(HERE, 'voice')
    for i, c in enumerate(CHARS):
        s = T0 + STEP * i
        add(sfx_whoosh(), s, .5); add(sfx_shutter(), s + ENTER - .02, .9)
        add(trim(load_wav(os.path.join(V, c['key'] + '.wav'))), s + .12, 1.0)
    add(sfx_boom(), T_LOGO, .8)
    call = None
    for c in CHARS:
        a = trim(load_wav(os.path.join(V, 'call_' + c['name'] + '.wav')))
        call = a if call is None else (np.pad(call, (0, max(0, len(a) - len(call)))) + np.pad(a, (0, max(0, len(call) - len(a)))))
    add(call * .45, T_LOGO + .08, 1.0)
    if A.bgm and os.path.exists(A.bgm):
        b = load_wav(A.bgm)[:n]; fade = int(SR * .5); e = min(len(b), int(DUR * SR))
        b = b[:e].copy(); b[-fade:] *= np.linspace(1, 0, fade); add(b, 0, .38)
    mix = mix[:int(DUR * SR)]; mix = mix / max(1.0, np.abs(mix).max() / .95)
    p = os.path.join(A.out, name + '.wav')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', '-', p], input=(mix * 32767).astype(np.int16).tobytes())
    return p


for o in A.only:
    W, H = (1920, 1080) if o == 'H' else (1080, 1920)
    if A.preview: W, H = W // 2, H // 2
    name = 'opening_yoko_16x9' if o == 'H' else 'opening_tate_9x16'
    render(W, H, name); wav = mix_audio(name)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(A.out, name + '_noaudio.mp4'), '-i', wav, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', os.path.join(A.out, name + '.mp4')])
    os.remove(os.path.join(A.out, name + '_noaudio.mp4'))
    print('done', name, round(DUR, 2), 's')
