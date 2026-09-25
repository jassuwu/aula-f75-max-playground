"""turn phone clips of the board into stabilized sdr mp4s for youtube and linkedin.

run with opencv and numpy on demand, they are not runtime deps of `keys`:

  uv run --with opencv-python-headless --with numpy python scripts/demo_video.py analyze IN
  uv run ... scripts/demo_video.py preview IN --at 5 60 120
  uv run ... scripts/demo_video.py render IN OUT [--layout snake|bad-apple]

hdr (iphone hlg, bt.2020) is converted to sdr bt.709 by videotoolbox. stabilization
tracks features frame to frame, fits a similarity per frame with ransac, and
smooths the camera path with a wide gaussian, so the board holds still and only
slow drift survives. the path is cached next to the input as <in>.path.npz.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

VT = ("scale_vt=w={w}:h={h}:color_matrix=bt709:color_primaries=bt709:color_transfer=bt709,"
      "hwdownload,format=p010le,scale=in_color_matrix=bt709:out_color_matrix=bt709,format={fmt},fps={fps}")


def probe(path: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {"w": s["width"], "h": s["height"], "fps": round(int(num) / int(den)),
            "duration": float(j["format"]["duration"])}


def decode(path: str, w: int, h: int, fps: int, fmt: str, start: float = 0.0, length: float | None = None):
    """yield raw frames (gray or bgr24) at a constant rate, rotation metadata ignored."""
    cmd = ["ffmpeg", "-v", "error", "-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld",
           "-noautorotate", "-ss", f"{start:.3f}"]
    if length is not None:
        cmd += ["-t", f"{length:.3f}"]
    cmd += ["-i", path, "-an", "-vf", VT.format(w=w, h=h, fmt=fmt, fps=fps), "-f", "rawvideo", "-"]
    ch = 1 if fmt == "gray" else 3
    size = w * h * ch
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=size * 2)
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            a = np.frombuffer(buf, np.uint8)
            yield a.reshape(h, w) if ch == 1 else a.reshape(h, w, 3)
    finally:
        p.kill()
        p.wait()


def half(n: int) -> int:
    return (n // 2) & ~1


# ── analysis ───────────────────────────────────────────────────────────────────
# the board's lit keys move with the content, so generic feature tracking follows
# the snake, not the camera. instead track anchors that never change: the tft
# screen (saturated colour), the f3 indicator (red) and right alt (cyan), each on
# its own chroma map so white or green content can't be mistaken for them.

def chroma(img: np.ndarray, kind: str) -> np.ndarray:
    b, g, r = (img[..., i].astype(np.int16) for i in range(3))
    if kind == "red":
        m = r - np.maximum(g, b)
    elif kind == "cyan":
        m = np.minimum(g, b) - r
    elif kind == "sat":
        m = np.max(img, 2).astype(np.int16) - np.min(img, 2)
    else:
        raise ValueError(kind)
    return np.clip(m, 0, 255).astype(np.uint8)


def similarity(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """least-squares rotation + uniform scale + translation mapping src points to dst."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    den = (a ** 2).sum()
    c = (a[:, 0] * b[:, 0] + a[:, 1] * b[:, 1]).sum() / den
    s_ = (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum() / den
    R = np.array([[c, -s_], [s_, c]])
    t = mu_d - R @ mu_s
    return np.array([[R[0, 0], R[0, 1], t[0]], [R[1, 0], R[1, 1], t[1]], [0, 0, 1]])


def subpixel(res: np.ndarray, x: int, y: int) -> tuple[float, float]:
    def fit(m1, c0, p1):
        d = m1 - 2 * c0 + p1
        return 0.0 if abs(d) < 1e-9 else 0.5 * (m1 - p1) / d
    dx = fit(res[y, x - 1], res[y, x], res[y, x + 1]) if 0 < x < res.shape[1] - 1 else 0.0
    dy = fit(res[y - 1, x], res[y, x], res[y + 1, x]) if 0 < y < res.shape[0] - 1 else 0.0
    return x + dx, y + dy


def find(mapref: np.ndarray, tpl: np.ndarray, cx: float, cy: float, r: int) -> tuple[float, float, float]:
    th, tw = tpl.shape
    x0, y0 = int(round(cx - tw / 2 - r)), int(round(cy - th / 2 - r))
    x0, y0 = max(0, x0), max(0, y0)
    win = mapref[y0:y0 + th + 2 * r, x0:x0 + tw + 2 * r]
    if win.shape[0] < th + 2 or win.shape[1] < tw + 2 or win.max() < 25:
        return cx, cy, 0.0
    res = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, (bx, by) = cv2.minMaxLoc(res)
    fx, fy = subpixel(res, bx, by)
    return x0 + fx + tw / 2, y0 + fy + th / 2, float(score)


def blob_centre(m: np.ndarray, cx: float, cy: float, r: int, thr: int, min_area: int):
    """centre of the bounding box of the largest bright blob near (cx, cy), or None."""
    x0, y0 = max(0, int(cx - r)), max(0, int(cy - r))
    win = m[y0:int(cy + r), x0:int(cx + r)]
    if win.size == 0:
        return None
    n, _, stats, _ = cv2.connectedComponentsWithStats((win > thr).astype(np.uint8))
    if n < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh, area = stats[i]
    if area < min_area:
        return None
    return x0 + x + bw / 2, y0 + y + bh / 2


THRESH = {"gray": 140, "red": 60, "cyan": 40, "screen": 40}
CLOSE = np.ones((9, 9), np.uint8)


def anchor_map(img: np.ndarray, kind: str) -> np.ndarray:
    if kind == "gray":
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if kind == "screen":
        # the tft's coloured ui, with its separate icons and digits merged into one shape;
        # white-lit keys are unsaturated and drop out
        m = np.where(img.max(2) > 70, chroma(img, "sat"), 0).astype(np.uint8)
        return cv2.morphologyEx(m, cv2.MORPH_CLOSE, CLOSE)
    return chroma(img, kind)


def analyze(path: str, fps: int, start: float, length: float | None, anchors: list, ref_t: float,
            use: set) -> dict:
    """track each anchor as the bounding-box centre of its glowing blob, so a screen
    whose contents change or a key whose glow flickers still gives a steady point."""
    info = probe(path)
    W, H = info["w"], info["h"]
    w, h = half(W), half(H)
    ref = next(decode(path, w, h, fps, "bgr24", start + ref_t, 1.0))
    refs = []
    for name, kind, (ax, ay), (rw, _) in anchors:
        c = blob_centre(anchor_map(ref, kind), ax, ay, rw, THRESH[kind], 30)
        if c is None:
            raise SystemExit(f"anchor {name} not found near {ax},{ay} in the reference frame")
        refs.append((name, kind, c[0], c[1], rw))
    T = np.eye(3)
    Ts, scores, obs = [], [], []
    first = True
    for i, f in enumerate(decode(path, w, h, fps, "bgr24", start, length)):
        src, dst, sc, ob = [], [], {}, {}
        for name, kind, cx, cy, rw in refs:
            px, py = (T @ np.array([cx, cy, 1.0]))[:2]
            c = blob_centre(anchor_map(f, kind), px, py, rw * (2 if first else 1), THRESH[kind], 30)
            sc[name] = 1.0 if c is not None else 0.0
            ob[name] = c if c is not None else (np.nan, np.nan)
            if c is not None and name in use:
                src.append((cx, cy))
                dst.append(c)
        if len(src) >= 2:
            T = similarity(np.array(src), np.array(dst))
        elif len(src) == 1:
            pred = (T @ np.array([src[0][0], src[0][1], 1.0]))[:2]
            T = T.copy()
            T[:2, 2] += np.array(dst[0]) - pred
        first = False
        Ts.append(T.copy())
        scores.append([sc[r[0]] for r in refs])
        obs.append([ob[r[0]] for r in refs])
        if (i + 1) % 600 == 0:
            print(f"  tracked {i + 1} frames", flush=True)
    D = np.diag([W / w, H / h, 1.0])
    Tf = np.array([D @ t @ np.linalg.inv(D) for t in Ts])
    return {"T": Tf, "scores": np.array(scores), "obs": np.array(obs, dtype=float) * np.array([W / w, H / h]),
            "names": np.array([r[0] for r in refs]),
            "ref": np.array([[r[2] * W / w, r[3] * H / h] for r in refs]), "W": W, "H": H, "fps": fps}


def interp_nan(x: np.ndarray) -> np.ndarray:
    x = x.copy()
    for j in range(x.shape[1]):
        bad = np.isnan(x[:, j])
        if bad.all():
            raise SystemExit("an anchor was never seen")
        x[bad, j] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), x[~bad, j])
    return x


def despike(x: np.ndarray, win: int = 31, tol: float = 12.0) -> np.ndarray:
    """drop readings that jump away from their own running median (a blob briefly
    latching onto something else), leaving nan for interp_nan to fill."""
    x = x.copy()
    good = ~np.isnan(x).any(1)
    idx = np.flatnonzero(good)
    if len(idx) < win:
        return x
    v = x[idx]
    pad = win // 2
    vp = np.pad(v, ((pad, pad), (0, 0)), mode="edge")
    med = np.median(np.lib.stride_tricks.sliding_window_view(vp, win, axis=0), axis=2)
    bad = np.hypot(*(v - med).T) > tol
    x[idx[bad]] = np.nan
    return x


def pivot_path(d: dict, pivot: str, lever: str, fps: int) -> np.ndarray:
    """camera path from one precise anchor (position, every frame) and the direction
    to a second anchor (rotation and zoom, smoothed over a second to drop blob noise)."""
    names = list(d["names"])
    ip, il = names.index(pivot), names.index(lever)
    praw = despike(d["obs"][:, ip])
    p = interp_nan(praw)
    p0, l0 = d["ref"][ip], d["ref"][il]
    # fill gaps in the pivot-to-lever direction, not in the lever's absolute position:
    # the direction barely changes while the camera moves, the position does
    v = interp_nan(despike(d["obs"][:, il]) - praw)
    sig = fps * 1.0
    r = int(3 * sig)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    k /= k.sum()
    v = np.stack([np.convolve(np.pad(v[:, i], r, mode="reflect"), k, mode="valid") for i in range(2)], 1)
    v0 = l0 - p0
    ang = np.arctan2(v[:, 1], v[:, 0]) - np.arctan2(v0[1], v0[0])
    sca = np.hypot(*v.T) / np.hypot(*v0)
    out = np.zeros((len(p), 3, 3))
    for i in range(len(p)):
        c, s_ = sca[i] * np.cos(ang[i]), sca[i] * np.sin(ang[i])
        R = np.array([[c, -s_], [s_, c]])
        t = p[i] - R @ p0
        out[i] = [[R[0, 0], R[0, 1], t[0]], [R[1, 0], R[1, 1], t[1]], [0, 0, 1]]
    return out


def smooth_path(C: np.ndarray, sigma: float) -> np.ndarray:
    """gaussian-smooth tx, ty, angle and log scale of each cumulative transform."""
    th = np.unwrap(np.arctan2(C[:, 1, 0], C[:, 0, 0]))
    ls = np.log(np.hypot(C[:, 0, 0], C[:, 1, 0]))
    tx, ty = C[:, 0, 2], C[:, 1, 2]
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()

    def g(x):
        return np.convolve(np.pad(x, r, mode="reflect"), k, mode="valid")

    th, ls, tx, ty = g(th), g(ls), g(tx), g(ty)
    s = np.exp(ls)
    S = np.zeros_like(C)
    S[:, 0, 0], S[:, 0, 1], S[:, 0, 2] = s * np.cos(th), -s * np.sin(th), tx
    S[:, 1, 0], S[:, 1, 1], S[:, 1, 2] = s * np.sin(th), s * np.cos(th), ty
    S[:, 2, 2] = 1
    return S


def warps(C: np.ndarray, S: np.ndarray, W: int, H: int, zoom: float) -> np.ndarray:
    Z = np.array([[zoom, 0, W / 2 * (1 - zoom)], [0, zoom, H / 2 * (1 - zoom)], [0, 0, 1]])
    return np.array([Z @ S[i] @ np.linalg.inv(C[i]) for i in range(len(C))])


def needed_zoom(C: np.ndarray, S: np.ndarray, W: int, H: int, q: float = 0.98) -> float:
    """zoom about the centre so the output is covered by the warped frame in q of frames."""
    corners = np.array([[0, 0, 1], [W, 0, 1], [W, H, 1], [0, H, 1]], dtype=float).T
    zs = []
    for i in range(len(C)):
        Wi = np.linalg.inv(S[i] @ np.linalg.inv(C[i]))   # output -> input
        lo, hi = 1.0, 1.6
        for _ in range(20):
            z = (lo + hi) / 2
            Z = np.array([[z, 0, W / 2 * (1 - z)], [0, z, H / 2 * (1 - z)], [0, 0, 1]])
            src = (Wi @ np.linalg.inv(Z) @ corners)
            src = src[:2] / src[2]
            inside = (src[0] >= 0).all() and (src[0] <= W).all() and (src[1] >= 0).all() and (src[1] <= H).all()
            hi, lo = (z, lo) if inside else (hi, z)
        zs.append(hi)
    return float(np.quantile(zs, q))


def load_or_analyze(args, fps: int) -> dict:
    import hashlib
    spec = "|".join([f"{args.start:.2f}", str(args.length), f"{args.ref:.2f}", *sorted(args.use), *args.anchor])
    key = hashlib.sha1(spec.encode()).hexdigest()[:10]
    cache = Path(args.input + f".{key}.anchors.npz")
    if cache.exists():
        d = dict(np.load(cache, allow_pickle=True))
        return {k: (v.item() if v.shape == () else v) for k, v in d.items()}
    anchors = []
    for spec in args.anchor:
        name, kind, x, y, tw, th = spec.split(":")
        anchors.append((name, kind, (float(x), float(y)), (int(tw), int(th))))
    d = analyze(args.input, fps, args.start, args.length, anchors, args.ref, set(args.use))
    np.savez(cache, **d)
    return d


# ── layouts ────────────────────────────────────────────────────────────────────
def crush(img: np.ndarray, black: int) -> np.ndarray:
    if black <= 0:
        return img
    lut = np.clip((np.arange(256) - black) * 255.0 / (255 - black), 0, 255).astype(np.uint8)
    return cv2.LUT(img, lut)


class Snake:
    """the stabilized clip centred on a 1920x1080 black canvas."""
    size = (1920, 1080)

    def __init__(self, W: int, H: int, black: int) -> None:
        self.W, self.H, self.black = W, H, black
        self.x, self.y = (1920 - W) // 2, (1080 - H) // 2

    def compose(self, frame: np.ndarray, t: float) -> np.ndarray:
        out = np.zeros((1080, 1920, 3), np.uint8)
        out[self.y:self.y + self.H, self.x:self.x + self.W] = crush(frame, self.black)
        return out


class BadApple:
    """the original video above the board, both on black. the board region is
    cropped from the stabilized frame and scaled into the lower part."""
    size = (1920, 1080)

    def __init__(self, W: int, H: int, black: int, original: str, offset: float, crop: tuple, pip_h: int) -> None:
        self.black, self.offset = black, offset
        self.cx0, self.cy0, self.cx1, self.cy1 = crop           # board region in the stabilized frame
        self.pip_h = pip_h
        self.pip_w = round(pip_h * 4 / 3) & ~1
        gap = 28
        top = 32
        avail_h = 1080 - top - pip_h - gap - 24
        cw, ch = self.cx1 - self.cx0, self.cy1 - self.cy0
        s = min(avail_h / ch, 1880 / cw)
        self.bw, self.bh = round(cw * s) & ~1, round(ch * s) & ~1
        self.bx, self.by = (1920 - self.bw) // 2, top + pip_h + gap
        self.px, self.py = (1920 - self.pip_w) // 2, top
        self.orig = decode_plain(original, self.pip_w, self.pip_h, 30)
        self.orig_index = -1
        self.orig_frame = np.zeros((self.pip_h, self.pip_w, 3), np.uint8)

    def _orig_at(self, t: float) -> np.ndarray:
        want = int(round((t - self.offset) * 30))
        while self.orig_index < want:
            f = next(self.orig, None)
            if f is None:
                break
            self.orig_frame, self.orig_index = f, self.orig_index + 1
        return self.orig_frame if want >= 0 else np.zeros_like(self.orig_frame)

    def compose(self, frame: np.ndarray, t: float) -> np.ndarray:
        out = np.zeros((1080, 1920, 3), np.uint8)
        board = crush(frame[self.cy0:self.cy1, self.cx0:self.cx1], self.black)
        out[self.by:self.by + self.bh, self.bx:self.bx + self.bw] = cv2.resize(board, (self.bw, self.bh),
                                                                              interpolation=cv2.INTER_AREA)
        pip = self._orig_at(t)
        out[self.py:self.py + self.pip_h, self.px:self.px + self.pip_w] = pip
        cv2.rectangle(out, (self.px - 2, self.py - 2), (self.px + self.pip_w + 1, self.py + self.pip_h + 1),
                      (70, 70, 70), 2, lineType=cv2.LINE_AA)
        return out


def decode_plain(path: str, w: int, h: int, fps: int):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", f"fps={fps},scale={w}:{h}:flags=lanczos",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    size = w * h * 3
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=size * 2)
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            p.wait()
            return
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)


# ── commands ───────────────────────────────────────────────────────────────────
def prepare(args) -> tuple[dict, np.ndarray, float]:
    info = probe(args.input)
    fps = args.fps or info["fps"]
    d = load_or_analyze(args, fps)
    C, sc, names = d["T"], d["scores"], list(d["names"])
    if args.model == "pivot":
        C = pivot_path(d, args.pivot, args.lever, fps)
    elif args.model == "translate":
        # position only, from the one anchor that measures cleanly. rotation from a second
        # anchor disagreed with a third by up to 3 degrees (perspective changes as the phone
        # tilts), so it is left alone: a slow lean of a degree or two reads as natural.
        ip = list(d["names"]).index(args.pivot)
        p = interp_nan(despike(d["obs"][:, ip]))
        C = np.repeat(np.eye(3)[None], len(p), 0)
        C[:, :2, 2] = p - d["ref"][ip]
    if args.hold > 0:
        # anchors are unreliable before this (the board still in its own lighting): hold still
        n = min(len(C) - 1, int(round(args.hold * fps)))
        C = C.copy()
        C[:n] = C[n]
    for j, n in enumerate(names):
        print(f"anchor {n}: matched in {(sc[:, j] >= 0.55).mean() * 100:.0f}% of frames, median score {np.median(sc[:, j]):.2f}")
    ref = d["ref"]
    for j, n in enumerate(names):
        ok = sc[:, j] >= 0.55
        pred = np.einsum("nij,j->ni", C[:, :2, :2], ref[j]) + C[:, :2, 2]
        res = d["obs"][:, j] - pred
        jit = np.hypot(*np.diff(res[ok], axis=0).T) if ok.sum() > 2 else np.array([np.nan])
        tag = "used" if n in args.use else "held out"
        print(f"  {n} ({tag}): residual median {np.median(np.hypot(*res[ok].T)):.2f}px, frame-to-frame jitter median {np.median(jit):.2f}px, 95th {np.quantile(jit, 0.95):.2f}px")
    sig = args.sigma * fps
    S = np.repeat(np.median(C, axis=0)[None], len(C), 0) if args.sigma <= 0 else smooth_path(C, sig)
    dev = np.hypot(*(C[:, :2, 2] - S[:, :2, 2]).T)
    print(f"camera motion removed: median {np.median(dev):.1f}px, 95th pct {np.quantile(dev, 0.95):.1f}px, max {dev.max():.1f}px")
    z = args.zoom if args.zoom else min(1.25, needed_zoom(C, S, d["W"], d["H"]))
    print(f"zoom {z:.3f}", flush=True)
    return d, warps(C, S, d["W"], d["H"], z), fps


def cmd_analyze(args) -> None:
    prepare(args)


def cmd_preview(args) -> None:
    d, Ws, fps = prepare(args)
    want = {int(round(t * fps)) for t in args.at}
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(decode(args.input, d["W"], d["H"], fps, "bgr24", args.start, args.length)):
        if i in want:
            st = cv2.warpAffine(f, Ws[i][:2], (d["W"], d["H"]), flags=cv2.INTER_CUBIC)
            cv2.imwrite(str(outdir / f"stab_{i / fps:07.2f}.jpg"), cv2.resize(st, (d["W"] // 2, d["H"] // 2)))
            cv2.imwrite(str(outdir / f"raw_{i / fps:07.2f}.jpg"), cv2.resize(f, (d["W"] // 2, d["H"] // 2)))
        if i > max(want):
            break
    print("previews in", outdir)


def cmd_render(args) -> None:
    d, Ws, fps = prepare(args)
    W, H = d["W"], d["H"]
    if args.layout == "bad-apple":
        crop = tuple(int(v) for v in args.crop.split(","))
        layout = BadApple(W, H, args.black, args.original, args.orig_offset, crop, args.pip_h)
    else:
        layout = Snake(W, H, args.black)
    ow, oh = layout.size
    enc = ["ffmpeg", "-y", "-v", "error", "-stats",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{ow}x{oh}", "-r", str(fps), "-i", "-"]
    if args.layout == "bad-apple":
        ms = int(round(args.orig_offset * 1000))
        enc += ["-i", args.original, "-map", "0:v", "-map", "1:a:0",
                "-af", f"adelay={ms}:all=1,apad,aresample=48000"]
    else:
        enc += ["-ss", f"{args.start:.3f}", "-i", args.input, "-map", "0:v", "-map", f"1:{args.audio_stream}",
                "-af", "aresample=48000"]
    enc += ["-shortest", "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf), "-profile:v", "high",
            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", args.output]
    if args.frames:
        a, b = (int(v) for v in args.frames.split(":"))
        enc = [x for x in enc if x != "-shortest"]
        enc.insert(enc.index(args.output), "-frames:v")
        enc.insert(enc.index(args.output), str(b - a))
    else:
        a, b = 0, len(Ws)
    p = subprocess.Popen(enc, stdin=subprocess.PIPE)
    n = 0
    for i, f in enumerate(decode(args.input, W, H, fps, "bgr24", args.start, args.length)):
        if i >= min(len(Ws), b):
            break
        if i < a:
            if hasattr(layout, "_orig_at"):
                layout._orig_at(i / fps)
            continue
        st = cv2.warpAffine(f, Ws[i][:2], (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
        p.stdin.write(np.ascontiguousarray(layout.compose(st, i / fps)).tobytes())
        n += 1
    p.stdin.close()
    p.wait()
    print(f"wrote {n} frames to {args.output}")
    if p.returncode:
        sys.exit(p.returncode)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("analyze", "preview", "render"):
        s = sub.add_parser(name)
        s.add_argument("input")
        if name == "render":
            s.add_argument("output")
            s.add_argument("--layout", choices=("snake", "bad-apple"), default="snake")
            s.add_argument("--crf", type=int, default=17)
            s.add_argument("--audio-stream", default="a:0", help="ffmpeg stream spec for the clip's own audio")
            s.add_argument("--original", default="media/bad-apple.mp4")
            s.add_argument("--orig-offset", type=float, default=0.0, help="seconds into the output where the original starts")
            s.add_argument("--crop", default="0,0,1920,1080", help="board region x0,y0,x1,y1 in the stabilized frame")
            s.add_argument("--pip-h", type=int, default=360)
            s.add_argument("--frames", default=None, help="a:b, render only these frames (a quick check; audio is not trimmed)")
        if name == "preview":
            s.add_argument("--at", type=float, nargs="+", required=True)
            s.add_argument("--outdir", default="/tmp/demo-preview")
        s.add_argument("--fps", type=int, default=None)
        s.add_argument("--start", type=float, default=0.0)
        s.add_argument("--length", type=float, default=None)
        s.add_argument("--sigma", type=float, default=3.0,
                       help="seconds of gaussian smoothing on the camera path; 0 locks the shot completely")
        s.add_argument("--anchor", action="append", required=True,
                       help="name:kind:x:y:w:h at half resolution in the reference frame; kind is gray, screen, red or cyan")
        s.add_argument("--ref", type=float, default=0.0, help="reference frame, seconds after --start")
        s.add_argument("--hold", type=float, default=0.0, help="hold the camera still for the first N seconds")
        s.add_argument("--model", choices=("pivot", "translate", "similarity"), default="pivot")
        s.add_argument("--pivot", default="tft", help="anchor that gives position every frame")
        s.add_argument("--lever", default="f3", help="anchor that gives rotation and zoom, smoothed")
        s.add_argument("--use", nargs="+", default=None, help="anchors used for the estimate (default: all)")
        s.add_argument("--zoom", type=float, default=None)
        s.add_argument("--black", type=int, default=10, help="crush values below this to black")
    args = ap.parse_args()
    if args.use is None:
        args.use = [a.split(":")[0] for a in args.anchor]
    {"analyze": cmd_analyze, "preview": cmd_preview, "render": cmd_render}[args.cmd](args)


if __name__ == "__main__":
    main()
