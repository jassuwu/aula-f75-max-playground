"""read the game of life back out of a rendered demo, as timed events for the score.

  uv run --with opencv-python-headless --with numpy --with scipy python scripts/score/events.py \
      UNGRADED.mp4 OUT.json --corners 145,125,774,118,152,382,907,378

the input is the stabilized cut *before* the contrast grade (same --start, --length and
anchors as the release render, with --black 0 --gamma 1), because the grade crushes the
key legends that tell a lit key from a neighbour's glow.

1. track the tft screen per frame; it is the one lit thing that is always there.
2. fit the vendor key rectangles to a screen-aligned max projection with a perspective
   transform, seeded from four corner key centres (esc, f12, lctrl, right) read off a
   frame and refined against the glow outlines.
3. per frame, per key: the brightest fifth of a strip over the legend and the cap's
   bottom edge. that is lit only by the key's own led.
4. classify off / newborn white / settled blue / ember red, debounce, and emit births
   (off to lit) and deaths (alive to red). f3 is the firmware's blinker and is dropped.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from keys import layout  # noqa: E402

W, H = 960, 540


def frames(path: str) -> np.ndarray:
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={W}:{H}:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    out = []
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        out.append(np.frombuffer(b, np.uint8).reshape(H, W, 3))
    return np.stack(out)


def track_tft(v: np.ndarray) -> np.ndarray:
    n = len(v)
    pos = np.full((n, 2), np.nan)
    prev = None
    for i in range(n):
        b, r = v[i, ..., 0].astype(np.int16), v[i, ..., 2].astype(np.int16)
        m = (b - r).clip(0, 255).astype(np.uint8)
        m[:, :400] = 0
        m[300:] = 0
        x0 = y0 = 0
        if prev is not None:
            x0, y0 = int(max(0, prev[0] - 40)), int(max(0, prev[1] - 40))
            m = m[y0:y0 + 80, x0:x0 + 80]
        k, _, st, _ = cv2.connectedComponentsWithStats((m > 60).astype(np.uint8))
        if k > 1:
            j = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            if st[j, cv2.CC_STAT_AREA] >= 40:
                x, y, w, h, _ = st[j]
                pos[i] = prev = (x0 + x + w / 2, y0 + y + h / 2)
    idx = np.arange(n)
    ok = ~np.isnan(pos[:, 0])
    for j in range(2):
        pos[~ok, j] = np.interp(idx[~ok], idx[ok], pos[ok, j])
    k = np.exp(-0.5 * (np.arange(-15, 16) / 5) ** 2)
    k /= k.sum()
    return np.stack([np.convolve(np.pad(pos[:, j], 15, mode="edge"), k, mode="valid") for j in range(2)], 1)


def fit_layout(v: np.ndarray, tft: np.ndarray, ref: int, corners: np.ndarray) -> np.ndarray:
    acc = np.zeros((H, W), np.float32)
    for i in range(0, len(v), 2):
        dx, dy = tft[ref] - tft[i]
        acc = np.maximum(acc, cv2.warpAffine(v[i].max(2).astype(np.float32), np.float32([[1, 0, dx], [0, 1, dy]]), (W, H)))
    img = cv2.GaussianBlur(acc, (0, 0), 2.0)
    img /= img.max()
    R = layout.RECTS
    src = np.float32([[(R[n][0] + R[n][2]) / 2, (R[n][1] + R[n][3]) / 2] for n in ("esc", "f12", "lctrl", "right")])
    gap = 0.006

    def score(d):
        Hm = cv2.getPerspectiveTransform(src, np.float32(d.reshape(4, 2)))
        t = np.zeros_like(img)
        for name, (l, tp, r, b) in R.items():
            if name == "f3":
                continue
            q = np.float32([[l - gap, tp - gap], [r + gap, tp - gap], [r + gap, b + gap], [l - gap, b + gap]])[None]
            p = cv2.perspectiveTransform(q, Hm)[0]
            cv2.polylines(t, [np.round(p * 4).astype(np.int32)], True, 1.0, 1, cv2.LINE_AA, shift=2)
        return -(img * t).sum() / max(t.sum(), 1)

    best = None
    for trial in range(6):
        start = corners.ravel() + (np.random.default_rng(trial).normal(0, 6, 8) if trial else 0)
        r = minimize(score, start, method="Nelder-Mead", options={"xatol": 0.2, "fatol": 1e-5, "maxiter": 4000})
        if best is None or r.fun < best.fun:
            best = r
    print(f"layout fit: {-best.fun:.3f}", flush=True)
    return cv2.getPerspectiveTransform(src, np.float32(best.x.reshape(4, 2)))


def sample(v: np.ndarray, tft: np.ndarray, ref: int, Hm: np.ndarray) -> np.ndarray:
    strips = []
    for k in layout.KEYS:
        l, tp, r, b = layout.RECTS[k.name]
        w, h = r - l, b - tp
        q = np.float32([[l + .15 * w, tp + .68 * h], [r - .15 * w, tp + .68 * h],
                        [r - .15 * w, b + .12 * h], [l + .15 * w, b + .12 * h]])[None]
        strips.append(cv2.perspectiveTransform(q, Hm)[0])
    feat = np.zeros((len(v), 80, 3), np.float32)
    for i in range(len(v)):
        d = tft[i] - tft[ref]
        for k, p in enumerate(strips):
            pp = p + d
            x0, y0 = np.maximum(np.floor(pp.min(0)).astype(int), 0)
            x1, y1 = np.ceil(pp.max(0)).astype(int)
            patch = v[i, y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)
            if len(patch):
                mx = patch.max(1)
                feat[i, k] = patch[mx >= np.percentile(mx, 80)].mean(0)
    return feat


def classify(feat: np.ndarray) -> np.ndarray:
    b, g, r = feat[..., 0], feat[..., 1], feat[..., 2]
    lum = feat.max(2)
    lit = np.zeros(lum.shape, bool)
    s = lum[0] > 90
    for i in range(len(lum)):
        s = np.where(s, lum[i] > 65, lum[i] > 90)     # hysteresis
        lit[i] = s
    red = lit & (r > 1.6 * b) & (r > 1.4 * g)
    blue = lit & ~red & (b > 1.35 * r)
    cls = np.zeros(lum.shape, np.uint8)              # 0 off, 1 white, 2 blue, 3 red
    cls[lit & ~red & ~blue] = 1
    cls[blue] = 2
    cls[red] = 3
    cls[:, [k.name for k in layout.KEYS].index("f3")] = 0
    st = cls.copy()
    for i in range(2, len(cls)):                     # a state must hold two frames
        st[i] = np.where(cls[i] == cls[i - 1], cls[i], st[i - 1])
    return st


def events(st: np.ndarray, fps: float) -> list[dict]:
    prev = np.vstack([st[:1], st[:-1]])
    out = []
    last_birth = np.full(80, -1e9)
    died = np.ones(80, bool)
    for i in range(1, len(st)):
        t = (i - 1) / fps                            # debounce reports one frame late
        for k in np.nonzero((prev[i] == 0) & ((st[i] == 1) | (st[i] == 2)))[0]:
            held = bool((st[i:i + 4, k] > 0).all())
            if held and (died[k] or t - last_birth[k] > 0.6):   # hand flicker re-reveals are not births
                out.append({"t": t, "kind": "birth", "key": layout.KEYS[k].name})
                last_birth[k] = t
                died[k] = False
        for k in np.nonzero(((prev[i] == 1) | (prev[i] == 2)) & (st[i] == 3))[0]:
            out.append({"t": t, "kind": "death", "key": layout.KEYS[k].name})
            died[k] = True
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--corners", required=True, help="esc,f12,lctrl,right key centres x,y at 960x540 in the reference frame")
    ap.add_argument("--ref", type=int, default=780, help="reference frame for the layout fit")
    ap.add_argument("--fps", type=float, default=30.0)
    args = ap.parse_args()
    v = frames(args.input)
    print(f"{len(v)} frames", flush=True)
    tft = track_tft(v)
    Hm = fit_layout(v, tft, args.ref, np.float32([float(x) for x in args.corners.split(",")]).reshape(4, 2))
    ev = events(classify(sample(v, tft, args.ref, Hm)), args.fps)
    keys = {k.name: {"row": k.row, "x": (layout.RECTS[k.name][0] + layout.RECTS[k.name][2]) / 2} for k in layout.KEYS}
    Path(args.output).write_text(json.dumps({"fps": args.fps, "frames": len(v), "keys": keys, "events": ev}, indent=0))
    nb = sum(e["kind"] == "birth" for e in ev)
    print(f"wrote {args.output}: {nb} births, {len(ev) - nb} deaths")


if __name__ == "__main__":
    main()
