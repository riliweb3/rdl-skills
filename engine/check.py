"""監督の確認：書き出した動画を数字で測って、コマの一覧を作る

  python rdl.py check video.mp4 [--every 0.5]

出すもの
- sheet.jpg ：0.5秒ごとのコマの一覧（目で見る用）
- 止まって見える所（0.6秒以上ほとんど動かない区間）
- 真っ黒なコマが続く所
- 音量（全体の大きさ LUFS・いちばん大きい所 dBTP）
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parent.parent / "fonts" / "ZenKakuGothicNew-Black.ttf"

def frames(path, fps, w=180):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)], text=True)
    W, H = map(int, out.strip().split(",")[:2]); h = int(w * H / W) // 2 * 2
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3), (W, H)

def stills(path, min_len=0.6):
    f, _ = frames(path, 10, 120)
    d = np.abs(np.diff(f.astype(np.int16), axis=0)).mean(axis=(1, 2, 3))
    res, start = [], None
    for i, v in enumerate(d):
        if v < 0.6:
            start = i if start is None else start
        else:
            if start is not None and (i - start) / 10 >= min_len: res.append((round(start / 10, 1), round(i / 10, 1)))
            start = None
    if start is not None and (len(d) - start) / 10 >= min_len: res.append((round(start / 10, 1), round(len(d) / 10, 1)))
    return res

def loudness(path):
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r); p = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)
    return (float(i[-1]) if i else None), (float(p[-1]) if p else None)

def blacks(path):
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-vf", "blackdetect=d=0.3:pix_th=0.06", "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r)]

def sheet(path, every=0.5, cols=8):
    f, _ = frames(path, 1 / every, 180)
    h, w = f.shape[1:3]; rows = (len(f) + cols - 1) // cols
    im = Image.new("RGB", (cols * (w + 4), rows * (h + 26)), "white"); d = ImageDraw.Draw(im)
    fnt = ImageFont.truetype(str(FONT), 16)
    for i, fr in enumerate(f):
        x, y = (i % cols) * (w + 4), (i // cols) * (h + 26)
        im.paste(Image.fromarray(fr), (x, y + 22)); d.text((x + 3, y + 2), f"{i * every:.1f}s", fill="black", font=fnt)
    out = Path(path).with_name(Path(path).stem + "_sheet.jpg"); im.save(out, quality=86)
    return out

def main(args):
    path = args[0]; every = float(args[args.index("--every") + 1]) if "--every" in args else 0.5
    has_audio = bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip())
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], text=True))
    lufs, peak = loudness(path) if has_audio else (None, None)
    st = stills(path); bl = blacks(path)
    rep = {"sheet": str(sheet(path, every)), "seconds": round(dur, 2), "stills": st, "black": bl, "lufs": lufs, "peak_db": peak, "notes": []}
    if st: rep["notes"].append("止まって見える所があります。意図した『一瞬の静』（0.3〜0.6秒）でなければ、ゆっくり寄せる・文字を少し漂わせる")
    if bl: rep["notes"].append("真っ黒が0.3秒以上続く所があります。暗転のつもりでなければ詰める")
    if lufs is not None and (lufs < -16 or lufs > -11): rep["notes"].append(f"音量 {lufs} LUFS。-14 前後（-16〜-11）に")
    if peak is not None and peak > -0.5: rep["notes"].append("音が割れる手前です（ピークを -1 dB 以下に）")
    if dur > 90: rep["notes"].append("90秒を超えています。リールは60秒以内が見られやすい")
    print(json.dumps(rep, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main(sys.argv[1:])
