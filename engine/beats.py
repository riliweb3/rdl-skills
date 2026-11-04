"""曲の拍を測る（numpy だけ。librosa 不要）

やり方：音の立ち上がり（オンセット）の強さを出し、BPM と位相を総当たりして、
半拍の格子に立ち上がりが一番よく乗る組を選ぶ。自動の BPM 推定は 2:3 や半分に取り違えやすいので、
範囲（lo〜hi）をこちらで決めて探す。
"""
from __future__ import annotations
import subprocess
import numpy as np

SR = 22050
HOP = 512

def load_audio(path, start=0.0, dur=None) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start)]
    if dur: cmd += ["-t", str(dur)]
    cmd += ["-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.check_output(cmd), np.float32)

def onset_env(y: np.ndarray) -> np.ndarray:
    n = 2048
    if len(y) < n * 2: return np.zeros(1, np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(y, n)[::HOP] * np.hanning(n).astype(np.float32)
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)) * 10)
    d = np.maximum(0, np.diff(mag, axis=0))
    low = int(200 / (SR / n))                                     # 低い音（キック）を重く＝表拍を取りやすく
    flux = d.sum(1) + d[:, :low].sum(1) * 6
    flux = np.concatenate([[0], flux])
    flux = flux - np.convolve(flux, np.ones(16) / 16, "same")       # ゆっくりした変化を引く
    flux = np.maximum(flux, 0)
    return (flux / (flux.max() + 1e-9)).astype(np.float32)

def find_grid(env: np.ndarray, lo=70.0, hi=180.0, step=0.1):
    """(bpm, 最初の拍の秒) を返す。半拍の格子への乗り具合で決める"""
    fr = SR / HOP
    t_end = len(env) / fr
    lag = 1024 / SR                                              # 窓の中心の分だけ遅らせる
    best = (0.0, 120.0, 0.0)
    for bpm in np.arange(lo, hi + 1e-9, step):
        beat = 60.0 / bpm
        for ph in np.arange(0, beat, beat / 24):
            ts = np.arange(ph, t_end, beat / 2)
            idx = (ts * fr).astype(int); idx = idx[idx < len(env)]
            if len(idx) < 8: continue
            on = env[idx]
            sc = on[::2].mean() * 1.0 + on[1::2].mean() * 0.5     # 表拍を重く
            if sc > best[0]: best = (sc, bpm, ph)
    return best[1], (best[2] + lag) % (60.0 / best[1])

def analyze(path, start=0.0, dur=30.0, lo=70.0, hi=180.0):
    y = load_audio(path, start, dur)
    env = onset_env(y)
    bpm, ph = find_grid(env, lo, hi, 0.25)
    bpm, ph = find_grid(env, bpm - 0.5, bpm + 0.5, 0.05)          # 細かく詰める
    return {"bpm": round(float(bpm), 2), "first": round(float(ph), 3)}

def best_section(path, length=15.0, hop=1.0):
    """曲の中で一番にぎやかな length 秒を探す（サビの見当）"""
    y = load_audio(path)
    env = onset_env(y); fr = SR / HOP
    rms = np.sqrt(np.convolve(y ** 2, np.ones(HOP) / HOP, "same")[::HOP])
    n = int(length * fr); score = []
    for s in range(0, max(1, len(env) - n), int(hop * fr)):
        score.append((env[s:s + n].mean() * 0.6 + rms[s:s + n].mean() / (rms.max() + 1e-9) * 0.4, s / fr))
    return max(score)[1] if score else 0.0

if __name__ == "__main__":
    import sys, json
    p = sys.argv[1]
    st = best_section(p, float(sys.argv[2]) if len(sys.argv) > 2 else 15.0)
    r = analyze(p, st, 20.0); r["section_start"] = round(st, 2)
    print(json.dumps(r, ensure_ascii=False))
