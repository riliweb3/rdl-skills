"""美容室の動画の型（Style / Brand / 爆速）。注文（order）から場面の並びを組む。

どの型も「長さ（15/30/60秒）に合わせて、場面の長さを自動で伸び縮みさせる」作り。
文字の出方・切り替えは注文で選ばれた物を順番に使う（3つまで）。
"""
from __future__ import annotations
import math, random
import numpy as np
from core import (Canvas, Palette, Timeline, FPS, EO, EI, EIO, BACK, clamp, load_photo, cover, contain, look,
                  text_layer, paste, band, label, blank, kaleido, chroma, gray, hard, duo, _resize, mask_of)

def lum(c): return float(np.asarray(c, np.float32) @ np.array([0.299, 0.587, 0.114], np.float32))
WHITE = np.array([248, 246, 242], np.float32); INK = np.array([10, 10, 10], np.float32)
def on(bgcol): return INK if lum(bgcol) > 150 else WHITE          # 地の色に対して読める文字色

def scrim(img, cy, h, k=0.55):
    """文字の後ろだけ、上下にぼけた暗い帯を敷いて読めるようにする"""
    H = img.shape[0]; y = np.arange(H, dtype=np.float32)[:, None, None]
    m = (np.exp(-((y - cy) / max(h, 1)) ** 2) * k).astype(np.float32)
    return img * (1 - m)

TEMPO = {"slow": 1.35, "normal": 1.0, "fast": 0.68, "bakusoku": 0.42}

# ================================================================ 文字の出方
def fx_text(base, s, fx, lt, pal, face="mincho", size=150, cy=None, col=None, sp=1.0, idx=0, sub=None, sub_face="anton"):
    """base の上に文字 s を fx の出方で重ねる。cy は文字の中心の高さ（省略で画面の少し上）"""
    W, H = Canvas.W, Canvas.H
    x0, top, x1, bottom = Canvas.safe()
    col = pal.fg if col is None else col
    cy = cy if cy is not None else H * 0.42
    cx = W / 2
    d = 0.55 * sp                                        # 入りの長さ
    k = lt / max(d, 1e-6)
    lay = text_layer(s, face, size, col, fit_w=int((x1 - x0) * 0.92))
    if fx == "up":
        e = EO(k); base = paste(base, lay, cx, cy + H * 0.06 * (1 - e), 1.0, e)
    elif fx == "pop":
        base = paste(base, lay, cx, cy, max(0.01, BACK(k)), clamp(k * 3))
    elif fx == "type":
        n = int(len(s) * clamp(lt / max(0.07 * sp * len(s), 1e-6))) + (1 if lt > 0 else 0)
        full = text_layer(s, face, size, col, fit_w=int((x1 - x0) * 0.92), align="left")
        part = text_layer(s[:n], face, size, col, fit_w=int((x1 - x0) * 0.92), align="left") if n < len(s) else full
        fh, fw = full.shape[:2]; ph, pw = part.shape[:2]
        base = paste(base, part, cx - fw / 2 + pw / 2, cy - fh / 2 + ph / 2)
    elif fx == "big":
        side = [-1, 1][idx % 2]
        e = EO(k * 0.9)
        if len(s) <= 2:                                   # 1〜2文字：特大ではみ出したまま止める
            big = text_layer(s, face, int(W * 0.62), col, fit_w=W * 3)
            base = paste(base, big, cx + side * W * 0.16 * e, cy, (2.0 - 0.58 * e) * 0.9)
        else:                                             # 長い言葉：大きく入って画面に収まる
            base = paste(base, lay, cx, cy, 1.0 + 0.55 * (1 - e), clamp(k * 4))
    elif fx == "spin":
        e = EO(k); sx = max(0.02, math.cos((1 - e) * math.pi / 2))
        base = paste(base, lay, cx, cy, 1.0, clamp(k * 2), sx=sx)
    elif fx == "scene":
        base = blank(pal.bg)                              # 明朝の文字場面：暗転した地に文字だけ
        tr = int(size * 0.5 * (1 - EO(k * 0.7)))
        lay2 = text_layer(s, face, size, col, fit_w=int((x1 - x0) * 0.92), track=tr // 4 * 4)
        base = paste(base, lay2, cx, cy, 1.0, EO(k))
    elif fx == "number":
        num = text_layer(f"{idx + 1:02d}", "anton", int(size * 0.9), pal.ac)
        e = EO(k)
        base = paste(base, num, cx, cy - lay.shape[0] / 2 - num.shape[0] * 0.55, 1.0, e)
        base = paste(base, lay, cx, cy + H * 0.03 * (1 - EO(k - 0.25)), 1.0, EO(k - 0.25))
    elif fx == "marker":
        e = EO(k)
        h, w = lay.shape[:2]
        base = band(base, cx - w / 2 - 10, cy + h * 0.05, cx - w / 2 - 10 + (w + 20) * e, cy + h / 2 - 6, pal.ac, 0.95)
        base = paste(base, lay, cx, cy)
    else:
        base = paste(base, lay, cx, cy, 1.0, EO(k))
    if sub:
        sl = text_layer(sub, sub_face, int(size * 0.32), col)
        base = paste(base, sl, cx, cy + lay.shape[0] / 2 + sl.shape[0] * 0.9, 1.0, EO((lt - d * 0.6) / d))
    return base

# ================================================================ 部品
class Kit:
    """注文の設定を持って、場面の部品を作る"""
    def __init__(self, order: dict):
        self.o = order
        self.pal = Palette.of(order.get("colors"))
        self.sp = TEMPO.get(order.get("tempo", "normal"), 1.0)
        self.fxs = order.get("textfx") or ["up"]
        self.trs = order.get("trans") or ["cut"]
        fonts = order.get("fonts") or {}
        self.head = fonts.get("head", "mincho"); self.subf = fonts.get("sub", "anton")
        self._fi = 0; self._ti = 0
    def fx(self):
        f = self.fxs[self._fi % len(self.fxs)]; self._fi += 1; return f
    def tr(self):
        t = self.trs[self._ti % len(self.trs)]; self._ti += 1; return t

    # 写真1枚の場面（ゆっくり寄せ続けて止めない）
    def photo(self, path, mode="color", fit="contain", zoom=1.0, cy=0.42, push=0.06, punch=0.0, lab=None, text=None, fx=None,
              tsize=140, tcy=None, sub=None, idx=0, dim=None):
        a = load_photo(path)
        pal = self.pal; sp = self.sp; head = self.head; subf = self.subf
        def fn(lt, gt, a=a):
            z = zoom * (1 + push * lt / 3) * (1 + punch * (1 - EO(lt / 0.32)))
            img = contain(a, z) if fit == "contain" else cover(a, z, 0.5, cy)
            img = look(img, mode, pal)
            if dim: img = img * dim
            if lab: img = label(img, lab, 70, int(Canvas.H * 0.09), 56)
            if text:
                ty = tcy if tcy is not None else Canvas.H * 0.42
                img = scrim(img, ty, tsize * 1.6)
                img = fx_text(img, text, fx or "up", lt, pal, head, tsize, tcy, col=WHITE, sp=sp, idx=idx, sub=sub, sub_face=subf)
            return img
        return fn

    def card(self, s, fx=None, bg=None, col=None, size=150, sub=None, idx=0, photo=None, cy=None):
        pal = self.pal; sp = self.sp; head = self.head; subf = self.subf
        a = load_photo(photo) if photo else None
        fx = fx or "up"
        def fn(lt, gt):
            if a is not None:
                img = cover(a, 1.08 + 0.03 * lt, 0.5, 0.4) * 0.38
                c = WHITE if col is None else col
            else:
                img = blank(pal.bg if bg is None else bg)
                c = (pal.fg if lum(pal.fg) - lum(pal.bg if bg is None else bg) else on(pal.bg)) if col is None else col
            return fx_text(img, s, fx, lt, pal, head, size, cy, c, sp, idx, sub, subf)
        return fn

    def split(self, left, right, labs=("BEFORE", "AFTER")):
        a, b = load_photo(left), load_photo(right)
        pal = self.pal
        def fn(lt, gt):
            W, H = Canvas.W, Canvas.H
            out = np.concatenate([cover(a, 1.0 + 0.02 * lt, 0.5, 0.42, W // 2, H), cover(b, 1.0 + 0.02 * lt, 0.5, 0.42, W - W // 2, H)], 1)
            out = band(out, W // 2 - 3, 0, W // 2 + 3, H, (255, 255, 255))
            out = label(out, labs[0], 50, int(H * 0.09), 48)
            out = label(out, labs[1], W // 2 + 50, int(H * 0.09), 48, fg=(8, 8, 8), bg=pal.ac)
            return out
        return fn

    def triptych(self, paths, labs=("FRONT", "SIDE", "BACK")):
        ims = [load_photo(p) for p in paths]
        def fn(lt, gt):
            W, H = Canvas.W, Canvas.H; cw = W // len(ims); out = []
            for i, a in enumerate(ims):
                e = EO((lt - i * 0.12) / 0.5)
                col = cover(a, 1.0, 0.5, 0.42, cw, H) * e
                out.append(col)
            out = np.concatenate(out, 1)
            if out.shape[1] < W: out = np.concatenate([out, np.zeros((H, W - out.shape[1], 3), np.float32)], 1)
            for i, l in enumerate(labs[:len(ims)]):
                out = label(out, l, i * cw + 24, int(H * 0.09), 40)
            return out
        return fn

    def end(self):
        o = self.o; pal = self.pal; head = self.head; subf = self.subf; sp = self.sp
        name = o.get("salon") or "hair salon"
        cta = o.get("cta") or "ご予約はプロフィールから"
        def fn(lt, gt):
            img = blank(pal.bg)
            img = fx_text(img, name, "pop", lt, pal, head, 120, Canvas.H * 0.42, sp=sp)
            sl = text_layer(cta, "gothic", 44, on(pal.ac))
            img = band(img, Canvas.W / 2 - sl.shape[1] / 2 - 24, Canvas.H * 0.53 - 10, Canvas.W / 2 + sl.shape[1] / 2 + 24, Canvas.H * 0.53 + sl.shape[0] + 6, pal.ac, EO((lt - 0.3) / 0.4))
            return paste(img, sl, Canvas.W / 2, Canvas.H * 0.53 + sl.shape[0] / 2 - 2, 1.0, EO((lt - 0.35) / 0.4))
        return fn

    def flash(self, col):
        return lambda lt, gt: blank(col)

    def popgrid(self, path, n=2, cycle_paths=None, cycle=0):
        pal = self.pal
        combos = [(pal.ac, np.array([250, 240, 230], np.float32)), (np.array([22, 36, 92], np.float32), pal.fg),
                  (np.array([8, 8, 8], np.float32), np.array([245, 243, 238], np.float32)), (pal.fg, pal.ac)]
        paths = cycle_paths or [path]
        ims = [load_photo(p) for p in paths]
        def fn(lt, gt):
            W, H = Canvas.W, Canvas.H; cw, ch = W // n, H // n; out = np.zeros((H, W, 3), np.float32)
            sh = int(lt * FPS / cycle) if cycle else 0
            for i in range(n * n):
                a = ims[(i + sh) % len(ims)]
                g = hard(gray(cover(a, 1.0, 0.5, 0.4, cw, ch)), 8)
                lo, hi = combos[(i + i // n) % 4]
                out[(i // n) * ch:(i // n + 1) * ch, (i % n) * cw:(i % n + 1) * cw] = duo(g, lo * 0.9, hi)
            return out
        return fn

    def kaleido(self, path):
        a = load_photo(path)
        def fn(lt, gt):
            return np.repeat((hard(gray(kaleido(cover(a, 1.0 + 0.1 * lt, 0.5, 0.4))), 7) * 255)[..., None], 3, 2)
        return fn

    def bigword(self, s, i, photo=None):
        """特大の1〜2文字。はみ出したまま止める（左右を毎回変える）。写真を渡すと字の中が写真で透ける"""
        pal = self.pal; head = self.head
        a = load_photo(photo) if photo else None
        side = [-1, 1, -1, 1][i % 4]; up = [1, -1, -1, 1][i % 4]
        bgc = [pal.ac, np.array([8, 8, 8], np.float32), pal.fg, np.array([8, 8, 8], np.float32)][i % 4]
        fgc = [pal.fg, pal.ac, np.array([8, 8, 8], np.float32), np.array([245, 243, 238], np.float32)][i % 4]
        def fn(lt, gt):
            W, H = Canvas.W, Canvas.H
            lay = text_layer(s, head, int(W * 0.66), fgc, fit_w=W * 4)
            e = EO(lt * FPS / 7)
            sc = 2.0 - 0.58 * e
            cx = W / 2 + side * W * 0.17 * e; cy = H * 0.44 + up * H * 0.05 * e
            if a is not None:
                img = look(cover(a, 1.12, 0.5, 0.4), "bw")
                m = mask_of(lay, cx, cy, sc)
                inside = 255 - img if int(gt * FPS) % 4 < 2 else img
                return img * (1 - m) + (fgc * 0.7 + inside * 0.3) * m
            return paste(blank(bgc), lay, cx, cy, sc)
        return fn

# ================================================================ 長さに合わせて並べる
def lay_out(tl: Timeline, parts, total, end_fn, end_dur=2.0):
    """parts＝[(重み, 関数, 切り替え)] を total 秒に収まるよう伸び縮みさせて並べ、最後に締めを置く"""
    body = max(1.0, total - end_dur)
    wsum = sum(p[0] for p in parts) or 1
    t = 0.0
    for w, fn, tr in parts:
        d = body * w / wsum
        t = tl.seq(t, d, fn, tr)
    tl.seq(t, total - t, end_fn, "black")
    return tl

def photos_of(order, key=None):
    ph = order.get("photos") or []
    if isinstance(ph, dict):
        return ph.get(key) if key else list(ph.values())
    return ph

# ================================================================ Style（髪を見せる）
def style_ba(order, tl, kit, L):
    ph = order.get("photos") or {}
    before = ph.get("before") if isinstance(ph, dict) else ph[0]
    after = ph.get("after") if isinstance(ph, dict) else ph[1]
    extra = (ph.get("more") or []) if isinstance(ph, dict) else ph[2:]
    copy = order.get("copy") or "ビフォーアフター"
    tr = kit.trs
    reveal = "slider" if "slider" in tr else kit.tr()
    parts = [
        (1.6, kit.card(copy, kit.fx(), photo=after), None),
        (1.6, kit.photo(before, "color", lab="BEFORE"), kit.tr()),
        (2.4, kit.photo(after, "color", lab="AFTER"), reveal),
        (2.0, kit.split(before, after), kit.tr()),
    ]
    for i, p in enumerate(extra or [after]):
        parts.append((1.0, kit.photo(p, "color", fit="cover", zoom=1.25, cy=0.3, punch=0.18), kit.tr()))
    parts.append((1.6, kit.photo(after, "color", text=copy, fx=kit.fx(), dim=0.75, tcy=Canvas.H * 0.7, tsize=110), kit.tr()))
    return lay_out(tl, parts, L, kit.end())

def style_turn(order, tl, kit, L):
    ph = order.get("photos") or {}
    f, s, b = (ph.get("front"), ph.get("side"), ph.get("back")) if isinstance(ph, dict) else (ph + ph + ph)[:3]
    copy = order.get("copy") or "360°"
    parts = [(1.5, kit.card(copy, kit.fx(), photo=f), None)]
    for p, l in ((f, "FRONT"), (s, "SIDE"), (b, "BACK")):
        parts.append((1.5, kit.photo(p, "color", lab=l), "turn" if "turn" in kit.trs else kit.tr()))
    parts.append((2.0, kit.triptych([f, s, b]), kit.tr()))
    for i, p in enumerate([f, s, b, f, s, b]):          # 拍に合わせた三面の連打
        parts.append((0.3, kit.photo(p, "color", fit="cover", zoom=1.1, punch=0.12), None))
    parts.append((1.6, kit.photo(f, "color", text=copy, fx=kit.fx(), dim=0.7, tcy=Canvas.H * 0.7, tsize=110), kit.tr()))
    return lay_out(tl, parts, L, kit.end())

def style_process(order, tl, kit, L):
    ph = photos_of(order)
    lines = order.get("lines") or [f"STEP {i + 1}" for i in range(len(ph))]
    copy = order.get("copy") or "施術の流れ"
    parts = [(1.4, kit.card(copy, kit.fx(), photo=ph[-1]), None)]
    steps = ph[:-1] if len(ph) > 1 else ph
    for i, p in enumerate(steps):
        parts.append((1.6, kit.photo(p, "color", fit="cover", text=lines[i] if i < len(lines) else "", fx="number" if "number" in kit.fxs else kit.fx(),
                                     tsize=90, tcy=Canvas.H * 0.68, idx=i, dim=0.8), kit.tr()))
    parts.append((2.0, kit.photo(ph[-1], "color", lab="FINISH"), kit.tr()))
    return lay_out(tl, parts, L, kit.end())

# ================================================================ Brand（お店を伝える）
def brand_menu(order, tl, kit, L):
    ph = photos_of(order); words = order.get("words") or ["新"]
    copy = order.get("copy") or "NEW MENU"; lines = order.get("lines") or []
    pal = kit.pal
    parts = [(0.12, kit.flash(pal.ac), None), (0.08, kit.flash((8, 8, 8)), None), (0.1, kit.flash((245, 245, 245)), None)]
    for i, w in enumerate(words[:3]):
        parts.append((1.0, kit.bigword(w, i, ph[i % len(ph)] if i % 2 else None), "flash" if "flash" in kit.trs else kit.tr()))
        for j in range(3):
            p = ph[(i * 3 + j) % len(ph)]
            parts.append((0.35, kit.photo(p, ["bw", "duo", "color"][j % 3], fit="cover", zoom=1.15, punch=0.25), None))
    parts.append((1.8, kit.card(copy, kit.fx(), size=150), kit.tr()))
    for i, l in enumerate(lines[:3]):
        parts.append((1.3, kit.card(l, kit.fx(), size=96, idx=i, photo=ph[i % len(ph)]), kit.tr()))
    parts.append((1.8, kit.photo(ph[0], "color", text=copy, fx=kit.fx(), dim=0.7, tcy=Canvas.H * 0.7, tsize=110), kit.tr()))
    return lay_out(tl, parts, L, kit.end())

def brand_recruit(order, tl, kit, L):
    ph = photos_of(order); lines = order.get("lines") or ["一緒に働く仲間を募集しています"]
    copy = order.get("copy") or "RECRUIT"
    half = max(1, len(ph) // 2)
    parts = [(1.4, kit.card(copy, kit.fx(), photo=ph[0]), None)]
    for i, p in enumerate(ph[:half]):                     # 前半：モノクロ
        parts.append((1.2, kit.photo(p, "gray", fit="cover", text=lines[i % len(lines)] if i < len(lines) else None, fx=kit.fx(), tsize=86, tcy=Canvas.H * 0.68, idx=i), kit.tr()))
    for i, p in enumerate(ph[half:] or ph):               # 後半：いきなりカラー
        parts.append((1.3, kit.photo(p, "color", fit="cover", punch=0.12), "mono" if i == 0 else kit.tr()))
    msg = order.get("message") or (lines[-1] if lines else copy)
    parts.append((2.0, kit.card(msg, kit.fx(), size=110, photo=ph[-1]), kit.tr()))
    return lay_out(tl, parts, L, kit.end())

def brand_review(order, tl, kit, L):
    ph = photos_of(order); quotes = order.get("lines") or ["また来たいと思えるお店でした"]
    copy = order.get("copy") or "お客様の声"
    parts = [(1.4, kit.card(copy, kit.fx(), photo=ph[0]), None)]
    for i, q in enumerate(quotes):
        text, who = (q.split("|") + [""])[:2]
        parts.append((2.4, kit.card(f"「{text.strip()}」", kit.fx(), size=96, sub=who.strip() or None, idx=i, photo=ph[i % len(ph)]), kit.tr()))
    return lay_out(tl, parts, L, kit.end())

def brand_bakusoku(order, tl, kit, L, beat=None):
    """爆速カット：1〜3コマの連打・はみ出す特大の文字・4面/16面・万華鏡。曲があれば拍に合わせる"""
    ph = photos_of(order); words = order.get("words") or ["髪", "艶", "今"]
    pal = kit.pal
    bt = beat or 0.34
    def f(n): return n / FPS
    t = 0.0
    def put(d, fn, trn=None):
        nonlocal t; t = tl.seq(t, d, fn, trn)
    def rapid(d, items, steps):
        nonlocal t; z = t + d; i = 0
        while t < z - 1e-6:
            n = steps[min(i, len(steps) - 1)]; e = min(z, t + f(n)); tl.add(t, e, items[i % len(items)]); t = e; i += 1
    W_ = lambda: kit.flash((245, 243, 238)); B_ = lambda: kit.flash((8, 8, 8))
    modes = ["bw", "neg", "duo", "bw", "duo2", "neg"]
    rapid(bt * 0.5, [W_(), B_()], [1, 2, 1, 1])
    i = 0
    end_at = L - 1.8
    while t < end_at - 0.5:
        w = words[i % len(words)]
        put(bt * 1.0, kit.bigword(w, i, ph[i % len(ph)] if i % 3 == 2 else None))
        shots = [kit.photo(ph[(i * 4 + j) % len(ph)], modes[(i + j) % 6], fit="cover", zoom=[1.1, 1.9][j % 2], cy=0.32, punch=0.3) for j in range(5)] + [W_()]
        rapid(min(bt * 2, end_at - t), shots, [3, 2, 2, 1, 2, 1, 1, 1, 1, 1])
        if t >= end_at - 0.3: break
        extra = i % 3
        if extra == 0: put(min(bt, end_at - t), kit.popgrid(ph[i % len(ph)], 2))
        elif extra == 1: put(min(bt, end_at - t), kit.popgrid(None, 4, ph, cycle=2))
        else: put(min(bt, end_at - t), kit.kaleido(ph[(i + 1) % len(ph)]))
        i += 1
    rapid(max(0.2, end_at - t), [W_(), B_()], [1, 1, 2, 1, 1])
    tl.seq(t, L - t, kit.end(), None)
    return tl

FORMATS = {
    ("style", "ba"): style_ba, ("style", "turn"): style_turn, ("style", "process"): style_process,
    ("brand", "menu"): brand_menu, ("brand", "recruit"): brand_recruit, ("brand", "review"): brand_review,
    ("brand", "bakusoku"): brand_bakusoku,
}
