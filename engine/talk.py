"""Talk（話す動画）：自撮りの動画の「間」を自動で削り、台本からテロップと演出をのせる。

- 間の削り方：ffmpeg の silencedetect で無音を見つけ、話している所だけをつなぐ（前後に少し余白を残す）
- テロップ：order["script"]（話した内容の文章。1行＝1テロップ）を、話している時間に文字数の割合で配る
  ※ 文字起こしはしない（Claude は音を聞けない）。台本が無ければテロップなしで作る
- 種類（kind）
    katari：語り。強調語のところで暗転して明朝の文字だけの場面を挟む・フィルムの質感
    tele3d：立体テロップ。強調語が顔の横でくるっと回って出る・マーカーのテロップ
    howto ：ノウハウ解説。「# 見出し」の行で番号つきの章カードを挟む・マーカーのテロップ
"""
from __future__ import annotations
import re, subprocess, math
from pathlib import Path
import numpy as np
from core import (Canvas, Palette, Timeline, FPS, EO, EIO, BACK, clamp, cover, text_layer, paste, band, blank,
                  VideoReader, probe_duration, gray, look)
from formats import Kit, fx_text, scrim, on, WHITE, INK

# ---------------------------------------------------------------- 間を削る
def speech_segments(path, noise_db=-32, min_sil=0.45, pad=0.12, min_len=0.25):
    dur = probe_duration(path)
    out = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-af", f"silencedetect=noise={noise_db}dB:d={min_sil}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    sil = list(zip(starts, ends + [dur] * (len(starts) - len(ends))))
    keep, t = [], 0.0
    for a, z in sil:
        if a - t > 0: keep.append((max(0, t - pad), min(dur, a + pad)))
        t = z
    if dur - t > 0: keep.append((max(0, t - pad), dur))
    merged = []
    for a, z in keep:
        if z - a < min_len: continue
        if merged and a <= merged[-1][1] + 0.05: merged[-1] = (merged[-1][0], max(z, merged[-1][1]))
        else: merged.append((a, z))
    return merged or [(0.0, dur)], dur

class Source:
    """出力の秒 → 元動画の秒 に置き換えて、コマを読む"""
    def __init__(self, path, segs):
        self.path = path; self.segs = segs; self.rd = None; self.pos = -1
        self.map = []; t = 0.0
        for a, z in segs: self.map.append((t, t + (z - a), a)); t += z - a
        self.length = t
    def src_t(self, t):
        for a, z, s in self.map:
            if a <= t < z: return s + (t - a)
        return self.map[-1][2] + (self.map[-1][1] - self.map[-1][0]) - 1 / FPS
    def frame(self, t):
        st = self.src_t(t); fi = int(round(st * FPS))
        if self.rd is None or fi < self.pos or fi - self.pos > FPS * 2:
            if self.rd: self.rd.close()
            self.rd = VideoReader(self.path, fi / FPS); self.pos = fi - 1
        img = self.rd.last
        while self.pos < fi:
            img = self.rd.read(); self.pos += 1
        return img

# ---------------------------------------------------------------- 台本 → テロップの時刻
def plan_lines(script: str, src: Source):
    """script の各行を、話している時間に文字数の割合で配る。'# ' で始まる行は章の見出し"""
    rows = [r.strip() for r in (script or "").splitlines() if r.strip()]
    if not rows: return []
    body = [r for r in rows if not r.startswith("#")]
    total = sum(len(r) for r in body) or 1
    t = 0.0; out = []; chapter = 0
    for r in rows:
        if r.startswith("#"):
            chapter += 1; out.append(("chapter", t, t, r.lstrip("# ").strip(), chapter)); continue
        d = src.length * len(r) / total
        out.append(("line", t, t + d, r, chapter)); t += d
    return out

def split_telop(s, n=16):
    """長いテロップを2行に（読点・助詞の後ろで）"""
    if len(s) <= n: return s
    mid = len(s) // 2
    for k in range(0, mid):
        for i in (mid + k, mid - k):
            if 0 < i < len(s) and s[i - 1] in "、。のをにはがでともへ":
                return s[:i] + "\n" + s[i:]
    return s[:mid] + "\n" + s[mid:]

# ---------------------------------------------------------------- 組み立て
def build(o: dict, pal: Palette):
    kind = o.get("kind", "katari")
    segs, _ = speech_segments(o["video"], o.get("noise_db", -32))
    src = Source(o["video"], segs)
    kit = Kit(o)
    words = [w for w in (o.get("words") or []) if w]
    lines = plan_lines(o.get("script", ""), src)
    hook = o.get("copy")
    L_body = src.length
    tex = o.get("texture") or ("film" if kind == "katari" else "none")
    tl = Timeline(pal, tex)
    sub_face = (o.get("fonts") or {}).get("sub", "gothic")
    if sub_face == "anton": sub_face = "gothic"
    head = kit.head
    x0, top, x1, bottom = Canvas.safe()
    tel_y = bottom - 150

    # 強調語が出てくる行に「見せ場」を作る（多くて3か所）
    accents = []
    for typ, a, z, s, ch in lines:
        if typ != "line": continue
        for w in words:
            if w in s and len(accents) < 3 and all(abs(a - b) > 3 for b, *_ in accents):
                accents.append((a + (z - a) * 0.15, w)); break

    def base_frame(t):
        img = cover(src.frame(t), 1.0, 0.5, 0.45)
        if kind == "katari": img = img * 0.9 + np.repeat(gray(img)[..., None], 3, 2) * 0.1
        for at, w in accents:                                    # 見せ場：寄り＋残像
            k = t - at
            if 0 <= k < 1.2:
                z = 1 + 0.16 * EO(k / 0.35) * (1 - EIO(max(0, k - 0.8) / 0.4))
                img = cover(img, z, 0.5, 0.42)
        return img

    def telop(img, t):
        for typ, a, z, s, ch in lines:
            if typ == "line" and a <= t < z:
                k = t - a
                lay = text_layer(s, sub_face, 64, WHITE if kind == "katari" else INK, fit_w=int((x1 - x0) * 0.94))
                h, w = lay.shape[:2]
                if kind == "katari":
                    img = scrim(img, tel_y, 130, 0.6)
                    return paste(img, lay, Canvas.W / 2, tel_y, 1.0, EO(k / 0.25))
                e = EO(k / 0.3)
                img = band(img, Canvas.W / 2 - w / 2 - 22, tel_y - h / 2 - 12, Canvas.W / 2 - w / 2 - 22 + (w + 44) * e, tel_y + h / 2 + 8, (250, 248, 244), 0.96)
                img = band(img, Canvas.W / 2 - w / 2 - 22, tel_y + h / 2 + 2, Canvas.W / 2 - w / 2 - 22 + (w + 44) * e, tel_y + h / 2 + 12, pal.ac)
                return paste(img, lay, Canvas.W / 2, tel_y, 1.0, EO((k - 0.08) / 0.2))
        return img

    def body(lt, gt):
        t = lt
        img = base_frame(t)
        for at, w in accents:
            k = t - at
            if kind == "tele3d" and 0 <= k < 1.6:                 # 強調語がくるっと回って出る
                lay = text_layer(w, head, 190, pal.ac, fit_w=Canvas.W)
                e = EO(k / 0.5); sx = max(0.03, math.cos((1 - e) * math.pi / 2)) * (1 - EIO(max(0, k - 1.25) / 0.35))
                img = paste(img, lay, Canvas.W / 2, Canvas.H * 0.24, 1.0 + 0.2 * (1 - e), 1.0, sx=max(0.03, sx))
            if kind == "katari" and 0 <= k < 0.9:                 # 暗転して明朝の文字だけの場面（テロップも消す）
                return fx_text(blank(INK), w, "scene", k, pal, "mincho", 230, Canvas.H * 0.44, WHITE, kit.sp)
        for typ, a, z, s, ch in lines:                            # 章カード
            if typ == "chapter" and 0 <= t - a < 1.1:
                k = t - a
                card = blank(pal.bg) * 0.92 + img * 0.08
                return fx_text(card, s, "number", k, pal, head, 110, Canvas.H * 0.42, on(pal.bg), kit.sp, idx=ch - 1)
        img = telop(img, t)
        if hook and t < 1.8:                                      # つかみの一言
            img = scrim(img, Canvas.H * 0.3, 220, 0.5)
            img = fx_text(img, hook, kit.fxs[0] if kit.fxs else "pop", t, pal, head, 120, Canvas.H * 0.3, WHITE, kit.sp)
        return img

    tl.add(0, L_body, body)
    end_d = 2.0
    tl.seq(L_body, end_d, kit.end(), "black")
    o["_segments"] = segs
    return tl, L_body + end_d, {"segments": len(segs), "kept_seconds": round(L_body, 1)}

def mux_audio(o: dict, video_path: Path, L: float):
    """削った後の声をつなぎ、（あれば）BGMを小さく混ぜて、書き出した絵に重ねる。
    入力：0＝書き出した絵／1＝元の自撮り動画（声）／2＝BGM（任意）"""
    segs = o.get("_segments") or [(0.0, probe_duration(o["video"]))]
    fc = "".join(f"[1:a]atrim={a}:{z},asetpts=PTS-STARTPTS[s{i}];" for i, (a, z) in enumerate(segs))
    fc += "".join(f"[s{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1[v0];[v0]apad,atrim=0:{L}[voice]"
    inputs = ["-i", str(video_path), "-i", str(o["video"])]
    if o.get("music"):
        inputs += ["-ss", str(o.get("music_start", 0)), "-i", str(o["music"])]
        fc += f";[2:a]volume=0.12,atrim=0:{L},afade=t=out:st={max(0, L - 1.5)}:d=1.5[bgm];[voice][bgm]amix=inputs=2:duration=first:normalize=0[mix];[mix]loudnorm=I=-14:TP=-1.0[a]"
    else:
        fc += ";[voice]loudnorm=I=-14:TP=-1.0[a]"
    tmp = video_path.with_name(video_path.stem + "_tmp.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-t", str(L), "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(video_path)
