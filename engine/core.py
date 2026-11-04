"""RDL Skills — 描画エンジンの中心（numpy + Pillow + ffmpeg だけで動く。Windows / Mac / クラウド共通）

考え方：動画は「場面（scene）」の並び。場面は (秒 → 1コマの絵) を返す関数を持つ。
絵は numpy の float32 配列 (H, W, 3)・値は 0〜255。
"""
from __future__ import annotations
import math, random, subprocess, shutil
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"
FONTS = {
    "mincho": FONT_DIR / "ZenOldMincho-Black.ttf",       # 上品・語り・特大の漢字
    "gothic": FONT_DIR / "ZenKakuGothicNew-Black.ttf",   # 読みやすい・テロップ
    "maru":   FONT_DIR / "ZenMaruGothic-Bold.ttf",       # やわらか
    "anton":  FONT_DIR / "Anton-Regular.ttf",            # 英字ラベル（日本語は入っていないのでゴシックで補う）
}
FPS = 30
SIZES = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080)}

# ---------------------------------------------------------------- 画面の大きさ（書き出すサイズごとに切り替える）
class Canvas:
    W, H = 1080, 1920
    @classmethod
    def set(cls, ratio: str):
        cls.W, cls.H = SIZES.get(ratio, SIZES["9:16"])
    @classmethod
    def safe(cls):
        """大事な文字を置いてよい範囲（左, 上, 右, 下）。リールは下420px・端60pxに置かない"""
        W, H = cls.W, cls.H
        bottom = 420 if H >= 1900 else int(H * 0.08)
        return 60, int(H * 0.07), W - 60, H - bottom

def blank(col) -> np.ndarray:
    return np.ones((Canvas.H, Canvas.W, 3), np.float32) * np.asarray(col, np.float32)

# ---------------------------------------------------------------- 色
def hex2rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)

@dataclass
class Palette:
    bg: np.ndarray
    fg: np.ndarray
    ac: np.ndarray
    @classmethod
    def of(cls, d: dict | None):
        d = d or {}
        return cls(hex2rgb(d.get("bg", "#0b0b0b")), hex2rgb(d.get("fg", "#ffffff")), hex2rgb(d.get("accent", "#e2261a")))

# ---------------------------------------------------------------- 緩急（等速は使わない）
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def EO(x):            # expo.out：一気に動いてピタッと止まる
    x = clamp(x); return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)
def EI(x):            # expo.in：ためてから一気に出ていく
    x = clamp(x); return 0.0 if x <= 0 else 2 ** (10 * x - 10)
def EIO(x):           # expo.inOut
    x = clamp(x)
    if x in (0.0, 1.0): return x
    return 2 ** (20 * x - 10) / 2 if x < 0.5 else (2 - 2 ** (-20 * x + 10)) / 2
def BACK(x, s=1.9):   # 少し行き過ぎて戻る（ポン）
    x = clamp(x) - 1; return 1 + (s + 1) * x ** 3 + s * x ** 2

# ---------------------------------------------------------------- 写真・動画
_photo_cache: dict = {}
def load_photo(path) -> np.ndarray:
    key = str(path)
    if key not in _photo_cache:
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        if max(im.size) > 2400:
            im.thumbnail((2400, 2400), Image.LANCZOS)
        _photo_cache[key] = np.asarray(im, np.float32)
    return _photo_cache[key]

def _resize(a: np.ndarray, w: int, h: int, box=None) -> np.ndarray:
    im = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    return np.asarray(im.resize((max(1, w), max(1, h)), Image.BILINEAR, box=box), np.float32)

def cover(a: np.ndarray, zoom=1.0, cx=0.5, cy=0.42, W=None, H=None) -> np.ndarray:
    """画面いっぱいに切り抜く（zoom>1 で寄る。cx, cy は寄る中心＝髪は少し上）"""
    W = W or Canvas.W; H = H or Canvas.H
    h, w = a.shape[:2]
    s = max(W / w, H / h) * zoom
    cw, ch = W / s, H / s
    x0 = clamp(cx * w - cw / 2, 0, w - cw); y0 = clamp(cy * h - ch / 2, 0, h - ch)
    return _resize(a, W, H, box=(x0, y0, x0 + cw, y0 + ch))

def contain(a: np.ndarray, zoom=1.0, W=None, H=None, dim=0.55) -> np.ndarray:
    """髪を枠で切らない見せ方：写真全体を入れて、余白は同じ写真をぼかして暗くした物で埋める"""
    W = W or Canvas.W; H = H or Canvas.H
    back = cover(a, 1.0, W=W // 8, H=H // 8)
    back = np.asarray(Image.fromarray(back.astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR), np.float32) * dim
    h, w = a.shape[:2]
    s = min(W / w, H / h) * zoom
    nw, nh = int(w * s), int(h * s)
    fg = _resize(a, nw, nh)
    out = back.copy()
    x0, y0 = (W - nw) // 2, (H - nh) // 2
    xs, ys = max(0, x0), max(0, y0); xe, ye = min(W, x0 + nw), min(H, y0 + nh)
    out[ys:ye, xs:xe] = fg[ys - y0:ye - y0, xs - x0:xe - x0]
    return out

def probe_size(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height:stream_side_data=rotation", "-of", "csv=p=0", str(path)], text=True)
    nums = [x for x in out.replace("\n", ",").split(",") if x.strip().lstrip("-").isdigit()]
    w, h = int(nums[0]), int(nums[1])
    if len(nums) > 2 and abs(int(nums[2])) in (90, 270):
        w, h = h, w
    return w, h

def probe_duration(path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], text=True).strip())

class VideoReader:
    """動画を1コマずつ読む（ffmpeg のパイプ。行ったり来たりしない用途向け）"""
    def __init__(self, path, start=0.0, fps=FPS, max_side=1080):
        w, h = probe_size(path)
        s = min(1.0, max_side / max(w, h)); self.w, self.h = int(w * s) // 2 * 2, int(h * s) // 2 * 2
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", str(start), "-i", str(path), "-vf",
                                   f"fps={fps},scale={self.w}:{self.h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.n = self.w * self.h * 3; self.last = np.zeros((self.h, self.w, 3), np.float32)
    def read(self) -> np.ndarray:
        buf = self.p.stdout.read(self.n)
        if buf and len(buf) == self.n:
            self.last = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3).astype(np.float32)
        return self.last
    def close(self):
        try: self.p.kill()
        except Exception: pass

# ---------------------------------------------------------------- 見た目（写真の色の変え方）
def gray(a): return a @ np.array([0.299, 0.587, 0.114], np.float32)
def hard(g, k=9.0, m=0.5): return 1 / (1 + np.exp(-k * (g / 255 - m)))      # 白黒の強いコントラスト（0〜1）
def duo(m, lo, hi): m = np.repeat(m[..., None].astype(np.float32), 3, 2); return lo * (1 - m) + hi * m             # 2色のベタ
def look(a: np.ndarray, mode: str, pal: Palette | None = None) -> np.ndarray:
    pal = pal or Palette.of(None)
    if mode == "color": return a
    if mode == "soft":  return a * 0.55 + np.repeat(gray(a)[..., None], 3, 2) * 0.25 + 18
    if mode == "bw":    return np.repeat((hard(gray(a)) * 255)[..., None], 3, 2)
    if mode == "gray":  return np.repeat(gray(a)[..., None], 3, 2)
    if mode == "neg":   return np.repeat(((1 - hard(gray(a))) * 255)[..., None], 3, 2)
    if mode == "duo":   return duo(hard(gray(a), 7), pal.bg * 0.6, pal.ac)
    if mode == "duo2":  return duo(hard(gray(a), 7), pal.ac * 0.35, pal.fg)
    if mode == "dark":  return a * 0.42
    return a

def chroma(rgb, d=12):
    o = rgb.copy(); o[..., 0] = np.roll(rgb[..., 0], d, 1); o[..., 2] = np.roll(rgb[..., 2], -d, 1); return o

# ---------------------------------------------------------------- 文字
_font_cache: dict = {}
def font(name: str, size: int):
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONTS.get(name, FONTS["gothic"])), size)
    return _font_cache[key]

NO_START = set("、。，．・：；？！ー」』）】〕ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ…")
import re as _re
_TOK = _re.compile(r"[A-Za-z0-9¥$€%&'.,:+\-/]+ ?|.", _re.S)
def _kind(c):
    o = ord(c)
    if 0x3040 <= o <= 0x309F: return "h"            # ひらがな
    if 0x30A0 <= o <= 0x30FF: return "k"            # カタカナ
    if 0x4E00 <= o <= 0x9FFF: return "c"            # 漢字
    return "o"
GOOD_AFTER = set("、。！？!?・」』）") | set("のをにはがでとへもや")
def _good_break(prev: str, nxt: str) -> bool:
    """ここで改行してよいか（文節の切れ目らしい所）"""
    if not prev or not nxt: return True
    a, b = prev[-1], nxt[0]
    if b in NO_START: return False
    if a in GOOD_AFTER or a == " ": return True
    if a in "おご" and _kind(b) == "c": return False   # お店・ご予約 は切らない
    ka, kb = _kind(a), _kind(b)
    return (ka == "h" and kb in "ck") or (ka == "c" and kb == "k") or (ka == "k" and kb == "c")   # 文字の種類の切り替わり

def wrap_jp(text: str, f, max_w: int, track: int = 0) -> list[str]:
    """日本語の折り返し。文節の切れ目（句読点・助詞のあと・ひらがな→漢字）で切る。英単語は途中で切らない。改行 \\n はそのまま"""
    def w(s): return f.getlength(s) + track * max(0, len(s) - 1)
    lines = []
    for para in text.split("\n"):
        toks = _TOK.findall(para); cur = []
        for tok in toks:
            if w("".join(cur) + tok.rstrip()) <= max_w or not "".join(cur).strip() or tok[0] in NO_START:
                cur.append(tok); continue
            cut = None                                   # 行の後半にある、いちばん後ろの良い切れ目まで戻る
            for i in range(len(cur) - 1, 0, -1):
                if w("".join(cur[:i])) < max_w * 0.45: break
                if _good_break("".join(cur[:i]), "".join(cur[i:]) + tok):
                    cut = i; break
            if cut:
                lines.append("".join(cur[:cut]).rstrip()); cur = cur[cut:] + [tok]
            else:
                lines.append("".join(cur).rstrip()); cur = [tok.lstrip()]
        lines.append("".join(cur).rstrip())
    return lines

def has_jp(s: str) -> bool:
    return any(ord(c) > 0x2E7F for c in s)

@dataclass
class Text:
    """文字の板（RGBA）。fit_w に収まるよう自動で縮める"""
    s: str
    face: str = "gothic"
    size: int = 120
    col: np.ndarray = field(default_factory=lambda: np.array([255, 255, 255], np.float32))
    fit_w: int | None = None
    vertical: bool = False
    line_gap: float = 0.18
    track: int = 0
    align: str = "center"
    def render(self) -> np.ndarray:
        face = self.face
        if face == "anton" and has_jp(self.s):
            face = "gothic"                      # 英字の字体に日本語は無い
        size = self.size
        fit_w = self.fit_w or int(Canvas.W * 0.86)
        for _ in range(30):
            f = font(face, size)
            if self.vertical:
                lines = [self.s]; break
            lines = wrap_jp(self.s, f, fit_w, self.track)
            bad = any(not _good_break(lines[i], lines[i + 1]) for i in range(len(lines) - 1))
            if (len(lines) <= 3 and not bad) or size < max(40, self.size * 0.5): break
            size = int(size * 0.92)                     # 変な所で切れるなら少し小さくして収める
        f = font(face, size)
        if self.vertical:
            boxes = [f.getbbox(c) for c in self.s]
            cw = max((b[2] - b[0]) for b in boxes) if boxes else size
            hh = sum(size + self.track for _ in self.s)
            im = Image.new("L", (cw + 20, hh + 20), 0); d = ImageDraw.Draw(im); y = 10
            for c, b in zip(self.s, boxes):
                d.text((10 + (cw - (b[2] - b[0])) / 2 - b[0], y - b[1] + (size - (b[3] - b[1])) / 2), c, font=f, fill=255); y += size + self.track
        else:
            lh = int(size * (1 + self.line_gap))
            widths = [f.getlength(l) + self.track * max(0, len(l) - 1) for l in lines]
            tw = int(max(widths)) + 20; th = lh * len(lines) + int(size * 0.35)
            im = Image.new("L", (tw, th), 0); d = ImageDraw.Draw(im)
            asc = f.getmetrics()[0]
            for i, (l, w) in enumerate(zip(lines, widths)):
                x = (tw - w) / 2 if self.align == "center" else 10
                if self.track:
                    for c in l:
                        d.text((x, i * lh + 6), c, font=f, fill=255); x += f.getlength(c) + self.track
                else:
                    d.text((x, i * lh + 6), l, font=f, fill=255)
        m = np.asarray(im, np.float32) / 255
        rgba = np.zeros(m.shape + (4,), np.float32); rgba[..., :3] = self.col; rgba[..., 3] = m
        return rgba

_text_cache: dict = {}
def text_layer(s, face="gothic", size=120, col=(255, 255, 255), fit_w=None, vertical=False, track=0, align="center") -> np.ndarray:
    key = (s, face, size, tuple(np.asarray(col).tolist()), fit_w, vertical, track, Canvas.W, align)
    if key not in _text_cache:
        if len(_text_cache) > 400: _text_cache.clear()
        _text_cache[key] = Text(s, face, size, np.asarray(col, np.float32), fit_w, vertical, track=track, align=align).render()
    return _text_cache[key]

def paste(base: np.ndarray, layer: np.ndarray, cx: float, cy: float, scale=1.0, alpha=1.0, sx=None) -> np.ndarray:
    """RGBA の板を、中心 (cx, cy) に倍率 scale で重ねる（画面からはみ出してよい）。sx は横だけの倍率（くるっと回る用）"""
    if alpha <= 0.003 or scale <= 0.01: return base
    h, w = layer.shape[:2]
    nw, nh = max(1, int(w * scale * (sx if sx is not None else 1))), max(1, int(h * scale))
    if (nw, nh) != (w, h):
        im = Image.fromarray((layer * [1, 1, 1, 255]).clip(0, 255).astype(np.uint8), "RGBA").resize((nw, nh), Image.BILINEAR)
        lay = np.asarray(im, np.float32); lay[..., 3] /= 255
    else:
        lay = layer
    H, W = base.shape[:2]
    x0, y0 = int(cx - nw / 2), int(cy - nh / 2)
    xs, ys = max(0, x0), max(0, y0); xe, ye = min(W, x0 + nw), min(H, y0 + nh)
    if xs >= xe or ys >= ye: return base
    part = lay[ys - y0:ye - y0, xs - x0:xe - x0]
    a = np.repeat(part[..., 3:4] * np.float32(alpha), 3, 2)
    out = base.copy()
    out[ys:ye, xs:xe] = out[ys:ye, xs:xe] * (1 - a) + part[..., :3] * a
    return out

def mask_of(layer: np.ndarray, cx, cy, scale=1.0) -> np.ndarray:
    """板の形だけを画面サイズの 0〜1 のマスクにする（写真を文字の形に抜く用）"""
    lay = layer.copy(); lay[..., :3] = 255
    return paste(np.zeros((Canvas.H, Canvas.W, 3), np.float32), lay, cx, cy, scale) / 255

def band(base, x0, y0, x1, y1, col, alpha=1.0):
    H, W = base.shape[:2]
    x0, x1 = int(clamp(x0, 0, W)), int(clamp(x1, 0, W)); y0, y1 = int(clamp(y0, 0, H)), int(clamp(y1, 0, H))
    if x1 > x0 and y1 > y0:
        base = base.copy(); base[y0:y1, x0:x1] = base[y0:y1, x0:x1] * (1 - alpha) + np.asarray(col, np.float32) * alpha
    return base

def label(base, s, x, y, size=54, fg=(245, 243, 238), bg=(8, 8, 8), face="anton"):
    """黒い帯の小さなラベル（BEFORE / FRONT など）。x, y は左上"""
    bgv = np.asarray(bg, np.float32)
    if float(bgv @ np.array([0.299, 0.587, 0.114])) < 90 and float(np.asarray(fg, np.float32).mean()) < 90:
        fg = (245, 243, 238)                                  # 暗い帯に暗い字にならないように
    if float(bgv @ np.array([0.299, 0.587, 0.114])) > 170 and float(np.asarray(fg, np.float32).mean()) > 170:
        fg = (8, 8, 8)
    lay = text_layer(s, face, size, fg, fit_w=Canvas.W)
    h, w = lay.shape[:2]
    base = band(base, x - 16, y - 8, x + w + 4, y + h + 2, bg)
    return paste(base, lay, x + w / 2 - 6, y + h / 2 - 4)

# ---------------------------------------------------------------- 質感（最前面は「たまに・薄く」）
_noise: dict = {}
def grain(rgb, gt, amt=6.0):
    """フィルムの粒（あらかじめ作った4枚を順に使う＝速い）"""
    key = rgb.shape[:2]
    if key not in _noise:
        h, w = key; rng = np.random.default_rng(3)
        _noise[key] = [np.repeat(np.repeat(np.repeat(rng.normal(0, 1, ((h + 1) // 2, (w + 1) // 2, 1)).astype(np.float32), 2, 0), 2, 1)[:h, :w], 3, 2) for _ in range(4)]
    return rgb + _noise[key][int(gt * FPS) % 4] * np.float32(amt)

_vig: dict = {}
def vignette(rgb, k=0.28):
    key = rgb.shape[:2]
    if key not in _vig:
        h, w = key; y, x = np.ogrid[:h, :w]
        d = ((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2
        _vig[key] = np.repeat((1 - k * np.clip(d - 0.25, 0, 1))[..., None].astype(np.float32), 3, 2)   # 3色ぶんの形にしておく（速い）
    return rgb * _vig[key]

_dots: dict = {}
def riso(rgb, pal: Palette):
    key = rgb.shape[:2]
    if key not in _dots:
        h, w = key; y, x = np.mgrid[:h, :w]
        _dots[key] = np.repeat(((np.sin(x * 0.9) * np.sin(y * 0.9)) * 0.5 + 0.5).astype(np.float32)[..., None], 3, 2)
    lum = np.repeat(gray(rgb)[..., None], 3, 2) / 255
    ink = (lum > _dots[key] * 0.9).astype(np.float32)
    out = rgb * 0.82 + ink * 255 * 0.12
    out[..., 0] = np.roll(out[..., 0], 3, 1)       # 版ずれ
    return out

def texture(rgb, mode, gt, pal):
    if mode == "film":  return vignette(grain(rgb, gt, 7))
    if mode == "riso":  return grain(riso(rgb, pal), gt, 4)
    return grain(rgb, gt, 2.5)                      # 何もなしでも、うっすら粒を足すとベタっとしない

# ---------------------------------------------------------------- 場面と書き出し
@dataclass
class Scene:
    a: float                  # 開始（秒）
    z: float                  # 終了（秒）
    fn: callable              # fn(lt 場面内の秒, gt 全体の秒) -> 絵
    trans: str | None = None  # この場面の入り方
    tdur: float = 0.0

class Timeline:
    def __init__(self, pal: Palette, tex="none", lead=0.0):
        self.scenes: list[Scene] = []; self.pal = pal; self.tex = tex; self.lead = lead
    def add(self, a, z, fn, trans=None, tdur=None):
        self.scenes.append(Scene(a, z, fn, trans, tdur if tdur is not None else default_tdur(trans))); return z
    def seq(self, t, dur, fn, trans=None, tdur=None):
        return self.add(t, t + dur, fn, trans, tdur)
    @property
    def end(self): return max((s.z for s in self.scenes), default=0.0)
    def frame(self, gt: float) -> np.ndarray:
        gt += self.lead
        for i, s in enumerate(self.scenes):
            if s.a <= gt < s.z:
                lt = gt - s.a
                img = s.fn(lt, gt)
                if s.trans and lt < s.tdur and i > 0:
                    p = self.scenes[i - 1]
                    prev = p.fn(min(p.z - p.a - 1 / FPS, lt + (p.z - p.a) - 1 / FPS), gt)
                    img = TRANS[s.trans](prev, img, lt / max(s.tdur, 1e-6), self.pal, gt)
                return img
        return blank(self.pal.bg)
    def out(self, gt) -> np.ndarray:
        return texture(self.frame(gt), self.tex, gt, self.pal).clip(0, 255).astype(np.uint8)

# ---------------------------------------------------------------- 場面の切り替え（組み合わせ可）
def default_tdur(t):
    return {"black": 0.36, "wipe": 0.3, "slider": 0.9, "zoom": 0.4, "turn": 0.36, "flash": 0.2, "mono": 0.6,
            "kaleido": 0.36, "trail": 0.3, "cut": 0.0}.get(t or "cut", 0.0)

def tr_black(a, b, k, pal, gt):
    return a * (1 - EIO(k * 2)) if k < 0.5 else b * EIO((k - 0.5) * 2)
def tr_wipe(a, b, k, pal, gt):
    W = a.shape[1]; x = int(W * EIO(k)); out = a.copy(); out[:, :x] = b[:, :x]
    return band(out, x - 10, 0, x, a.shape[0], pal.ac)
def tr_slider(a, b, k, pal, gt):
    W = a.shape[1]; x = int(W * (1 - EIO(k))); out = b.copy(); out[:, :x] = a[:, :x]
    out = band(out, x - 4, 0, x + 4, a.shape[0], (255, 255, 255))
    return out
def tr_zoom(a, b, k, pal, gt):
    z = 1 + 0.28 * (1 - EO(k)); H, W = b.shape[:2]
    return cover(b, z, 0.5, 0.5, W, H) if z > 1.002 else b
def tr_turn(a, b, k, pal, gt):
    H, W = a.shape[:2]; src = a if k < 0.5 else b; sx = abs(math.cos(k * math.pi))
    out = blank(pal.bg); nw = max(2, int(W * sx))
    return paste(out, np.concatenate([src, np.ones(src.shape[:2] + (1,), np.float32)], 2), W / 2, H / 2, 1.0, sx=nw / W)
def tr_flash(a, b, k, pal, gt):
    i = int(k * 6)
    return [blank(pal.ac), blank((8, 8, 8)), blank((245, 245, 245)), b, blank(pal.ac), b][min(i, 5)]
def tr_mono(a, b, k, pal, gt):
    g = np.repeat(gray(b)[..., None], 3, 2)
    if k < 0.12: return 255 - g
    e = EO((k - 0.12) / 0.88); return g * (1 - e) + b * e
def tr_kaleido(a, b, k, pal, gt):
    return kaleido(b if k > 0.5 else a)
def tr_trail(a, b, k, pal, gt):
    e = EO(k); return b * (0.35 + 0.65 * e) + a * (0.65 - 0.65 * e)
TRANS = {"black": tr_black, "wipe": tr_wipe, "slider": tr_slider, "zoom": tr_zoom, "turn": tr_turn,
         "flash": tr_flash, "mono": tr_mono, "kaleido": tr_kaleido, "trail": tr_trail}

def kaleido(rgb):
    H, W = rgb.shape[:2]
    q = _resize(cover(rgb, 1.25, 0.5, 0.4, W, H), W // 2, H // 2)
    top = np.concatenate([q, q[:, ::-1]], 1); full = np.concatenate([top, top[::-1]], 0)
    return full[:H, :W] if full.shape[0] >= H else cover(full, 1.0, W=W, H=H)

def render(tl: Timeline, out_path: Path, dur: float, music=None, music_start=0.0, preview=False, lufs=-14.0, log=print):
    """1コマずつ描いて ffmpeg に流す。音楽があれば最後1.2秒でフェードアウトし、音量をそろえる"""
    W, H = Canvas.W, Canvas.H
    sc = 0.5 if preview else 1.0
    ow, oh = int(W * sc) // 2 * 2, int(H * sc) // 2 * 2
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if music:
        cmd += ["-ss", str(music_start), "-t", str(dur), "-i", str(music)]
    cmd += ["-vf", f"scale={ow}:{oh}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28" if preview else "18", "-preset", "veryfast" if preview else "medium"]
    if music:
        cmd += ["-af", f"afade=t=out:st={max(0, dur - 1.2)}:d=1.2,loudnorm=I={lufs}:TP=-1.0", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-movflags", "+faststart", str(out_path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(round(dur * FPS))
    for i in range(n):
        p.stdin.write(tl.out(i / FPS).tobytes())
        if log and i % 90 == 0: log(f"  {i}/{n}コマ")
    p.stdin.close(); p.wait()
    if p.returncode != 0:
        raise RuntimeError("ffmpeg の書き出しに失敗しました")
    return out_path

def board(tl: Timeline, times, out_path: Path, cols=6):
    """絵コンテ（指定した秒のコマを並べた一覧画像）"""
    tw = 240; th = int(tw * Canvas.H / Canvas.W)
    rows = (len(times) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 6), rows * (th + 34)), "white"); d = ImageDraw.Draw(sheet)
    for i, t in enumerate(times):
        im = Image.fromarray(tl.out(t)).resize((tw, th))
        x, y = (i % cols) * (tw + 6), (i // cols) * (th + 34)
        sheet.paste(im, (x, y + 28)); d.text((x + 4, y + 4), f"{t:.2f}s", fill="black", font=font("gothic", 20))
    sheet.save(out_path, quality=88)
    return out_path

def need(tool: str) -> bool:
    return shutil.which(tool) is not None
