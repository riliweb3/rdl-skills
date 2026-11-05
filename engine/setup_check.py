"""道具がそろっているか確かめる（Windows / Mac / クラウド共通）

  python rdl.py env

結果は JSON。足りない物には、その場所での入れ方を添える。
"""
from __future__ import annotations
import json, platform, shutil, subprocess, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def where():
    if os.environ.get("CLAUDE_CODE_REMOTE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "remote" or Path("/root/.ccr").exists():
        return "cloud"
    s = platform.system()
    return {"Windows": "windows", "Darwin": "mac"}.get(s, "linux")

HOW = {
    "ffmpeg": {"windows": "winget install --id Gyan.FFmpeg -e（入れたら Claude Code を開き直す）",
               "mac": "brew install ffmpeg（Homebrew が無ければ https://brew.sh の1行を先に）",
               "linux": "sudo apt-get install -y ffmpeg", "cloud": "sudo apt-get install -y ffmpeg（環境の設定スクリプトに書いておくと毎回入る）"},
    "python": {"windows": "winget install --id Python.Python.3.12 -e", "mac": "brew install python@3.12", "linux": "sudo apt-get install -y python3", "cloud": "（最初から入っています）"},
    "numpy": {"*": f"{Path(sys.executable).name} -m pip install --user numpy pillow"},
    "pillow": {"*": f"{Path(sys.executable).name} -m pip install --user numpy pillow"},
}

def ver(cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.splitlines()[0][:60]
    except Exception: return None

def main():
    w = where(); res = {"where": w, "python": sys.version.split()[0], "ok": [], "missing": [], "how": {}}
    if sys.version_info < (3, 9):
        res["missing"].append("python3.9以上"); res["how"]["python"] = HOW["python"].get(w)
    for mod, key in (("numpy", "numpy"), ("PIL", "pillow")):
        try: __import__(mod); res["ok"].append(key)
        except ImportError: res["missing"].append(key); res["how"][key] = HOW[key]["*"]
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool): res["ok"].append(f"{tool} ({ver([tool, '-version'])})")
        else: res["missing"].append(tool); res["how"]["ffmpeg"] = HOW["ffmpeg"].get(w)
    fonts = sorted(p.name for p in (ROOT / "fonts").glob("*.ttf"))
    (res["ok"] if len(fonts) >= 4 else res["missing"]).append(f"fonts ×{len(fonts)}")
    if shutil.which("ffmpeg"):
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.2", "-c:v", "libx264", "-f", "null", "-"], check=True, timeout=60)
            res["ok"].append("libx264（書き出しできる）")
        except Exception:
            res["missing"].append("libx264"); res["how"]["ffmpeg"] = "H.264 で書き出せる ffmpeg を入れ直す：" + (HOW["ffmpeg"].get(w) or "")
    try: __import__("faster_whisper"); res["ok"].append("文字起こし（faster-whisper）")
    except ImportError: res["optional"] = {"文字起こし（Talk の台本を自動で作る・無料）": f"{Path(sys.executable).name} -m pip install --user faster-whisper"}
    res["ready"] = not res["missing"]
    print(json.dumps(res, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
