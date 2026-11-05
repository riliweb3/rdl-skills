"""話した動画の文字起こし（任意・無料）：パソコンの中だけで動く faster-whisper を使う

  python rdl.py transcribe me.mp4 [--model small]

- 入れ方：python -m pip install --user faster-whisper（最初の1回だけ、聞き取りの部品を数百MB読み込む）
- 結果は 1行＝1テロップ（24文字まで）にして、動画の隣に <名前>.script.txt で保存。order.json の script にそのまま使える
- 聞き間違い（固有名詞・美容用語）は残るので、必ず本人に見せて直してもらう
- model：small（ふつう・速い）／medium（正確・遅い・メモリ8GB以上）
"""
from __future__ import annotations
import sys, json, subprocess
from pathlib import Path

def split_line(s: str, n=24):
    """24文字を超える行は、読点・句点の後ろで分ける"""
    out = []
    while len(s) > n:
        cut = max((i + 1 for i, c in enumerate(s[:n]) if c in "、。！？ "), default=n)
        out.append(s[:cut].strip()); s = s[cut:]
    if s.strip(): out.append(s.strip())
    return out

def transcribe(video, model="small"):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit(json.dumps({"error": "faster-whisper が入っていません",
                                     "how": f"{Path(sys.executable).name} -m pip install --user faster-whisper"}, ensure_ascii=False))
    m = WhisperModel(model, device="cpu", compute_type="int8")
    # 音は ffmpeg で読む（faster-whisper の音声読み込みは部品の版ずれで落ちることがある）
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    segs, _ = m.transcribe(audio, language="ja", vad_filter=True)
    lines = [l for s in segs for l in split_line(s.text.strip())]
    out = Path(video).with_suffix(".script.txt"); out.write_text("\n".join(lines), encoding="utf-8")
    return out, lines

def main(args):
    model = args[args.index("--model") + 1] if "--model" in args else "small"
    out, lines = transcribe(args[0], model)
    print(json.dumps({"script_file": str(out), "lines": lines}, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    assert split_line("あ" * 30) == ["あ" * 24, "あ" * 6]
    assert split_line("今日は、髪の話をします。乾かし方で艶が変わります") == ["今日は、髪の話をします。", "乾かし方で艶が変わります"]
    main(sys.argv[1:])
