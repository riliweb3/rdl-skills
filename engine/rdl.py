"""RDL Skills の入口（コマンド）

  python rdl.py env                         道具がそろっているか確かめる
  python rdl.py board  order.json           絵コンテ（コマの一覧画像）を作る
  python rdl.py make   order.json [--preview]   動画を書き出す（選んだサイズ全部）
  python rdl.py check  video.mp4            監督の確認（コマ一覧・止まり・音量）
  python rdl.py beats  song.mp3 [秒]        曲の拍とサビの位置を測る

order.json の書き方は skills/make/order.md を見る。
"""
from __future__ import annotations
import json, sys, time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:                                                   # Windows の画面でも日本語が化けないように
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import core
from core import Canvas, Palette, Timeline, render, board, FPS

def load_order(p: Path) -> dict:
    o = json.loads(p.read_text(encoding="utf-8"))
    base = p.parent
    def fix(v):                                       # 相対パスは order.json の場所から
        if isinstance(v, str) and (v.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".mp4", ".mov", ".m4a", ".mp3", ".wav"))):
            q = Path(v); return str(q if q.is_absolute() else (base / q))
        if isinstance(v, list): return [fix(x) for x in v]
        if isinstance(v, dict): return {k: fix(x) for k, x in v.items()}
        return v
    for k in ("photos", "video", "music"):
        if k in o: o[k] = fix(o[k])
    o.setdefault("tempo", "normal"); o.setdefault("length", 15); o.setdefault("sizes", ["9:16"])
    out = Path(o.get("out", "out")); o["out"] = str(out if out.is_absolute() else base / out)   # 出力も order.json の場所から
    return o

def build(o: dict) -> tuple[Timeline, float, dict]:
    pal = Palette.of(o.get("colors"))
    L = float(o.get("length", 15))
    info = {}
    if o.get("type") == "talk":
        import talk
        tl, L, info = talk.build(o, pal)
        return tl, L, info
    import formats
    kit = formats.Kit(o)
    tl = Timeline(pal, o.get("texture", "none"))
    key = (o.get("type"), o.get("kind"))
    fn = formats.FORMATS.get(key)
    if not fn:
        raise SystemExit(f"この種類はまだありません：{key}。使えるのは {sorted(formats.FORMATS)}")
    if key == ("brand", "bakusoku") and o.get("music"):
        import beats
        st = o.get("music_start")
        if st is None:
            st = beats.best_section(o["music"], L)
        r = beats.analyze(o["music"], st, L + 4)
        o["music_start"] = round(st + r["first"], 3)
        info = {"bpm": r["bpm"], "music_start": o["music_start"]}
        fn(o, tl, kit, L, beat=60.0 / r["bpm"])
        tl.lead = 2 / FPS                              # 絵を2コマ先に出す（文字が読める瞬間を拍の頭に）
    else:
        fn(o, tl, kit, L)
    return tl, L, info

def cmd_board(order_path, extra=None):
    o = load_order(Path(order_path))
    Canvas.set(o["sizes"][0])
    tl, L, info = build(o)
    times = []
    for s in tl.scenes:
        if s.z - s.a < 0.25: continue
        if s.z - s.a > 3.0:                                  # 長い場面は1.2秒ごとに見る
            times += [round(x, 2) for x in np.arange(s.a + 0.5, s.z - 0.1, 1.2)]
        else:
            times.append(round(s.a + min(0.6, (s.z - s.a) * 0.6), 2))
    if len(times) > 36: times = times[:: max(1, len(times) // 36)]
    out = Path(o["out"]); out.mkdir(parents=True, exist_ok=True)
    p = board(tl, times, out / "board.jpg")
    print(json.dumps({"board": str(p), "scenes": len(tl.scenes), "length": L, **info}, ensure_ascii=False))

def cmd_make(order_path, preview=False):
    o = load_order(Path(order_path))
    out = Path(o["out"]); out.mkdir(parents=True, exist_ok=True)
    name = o.get("name", "rdl")
    made = []
    for ratio in o["sizes"]:
        Canvas.set(ratio)
        core._text_cache.clear()
        tl, L, info = build(o)
        tag = ratio.replace(":", "x")
        f = out / f"{name}_{tag}{'_preview' if preview else ''}.mp4"
        t0 = time.time(); print(f"書き出し中：{f.name}（{L:.1f}秒）")
        music = o.get("music") if o.get("type") != "talk" else None
        render(tl, f, L, music, o.get("music_start", 0.0), preview, lufs=float(o.get("lufs", -14)))
        if o.get("type") == "talk":
            import talk; talk.mux_audio(o, f, L)
        print(f"  できました（{time.time() - t0:.0f}秒）")
        made.append(str(f))
    print(json.dumps({"videos": made}, ensure_ascii=False))

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    c = sys.argv[1]
    if c == "env":
        import setup_check; setup_check.main()
    elif c == "board":
        cmd_board(sys.argv[2])
    elif c == "make":
        cmd_make(sys.argv[2], "--preview" in sys.argv)
    elif c == "check":
        import check; check.main(sys.argv[2:])
    elif c == "beats":
        import beats
        L = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0
        st = beats.best_section(sys.argv[2], L); r = beats.analyze(sys.argv[2], st, L + 4); r["section_start"] = round(st, 2)
        print(json.dumps(r, ensure_ascii=False))
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
