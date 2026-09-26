"""a soft generative soundtrack for the demo clips, rendered to a wav.

  uv run --with numpy python scripts/demo_music.py OUT.wav --seconds 57 [--seed 1]

no samples, no dependencies beyond numpy. a slow four-chord pad, a sub root, and
sparse plucks on a pentatonic that come and go like cells: the scale degrees are
a ring of eleven cells running a one-dimensional life, and a pluck sounds when a
cell is born. quiet by design; it sits under the picture rather than on top of it.
"""
from __future__ import annotations

import argparse
import struct
import wave

import numpy as np

RATE = 48000
BPM = 84
STEP = 60 / BPM                         # quarter notes
BAR = STEP * 4
CHORDS = [                              # semitones from a2, four bars each: am9, fmaj7, cmaj7, g6
    (0, 3, 7, 10, 14), (-4, 0, 3, 7, 12), (-9, -5, -2, 3, 7), (-2, 2, 5, 9, 12)]
SCALE = [0, 3, 5, 7, 10, 12, 15, 17, 19, 22, 24]   # a minor pentatonic, two octaves up from a3
A2 = 110.0


def hz(semi: float, base: float = A2) -> float:
    return base * 2 ** (semi / 12)


def env(n: int, a: float, d: float, s: float = 0.0, r: float = 0.0) -> np.ndarray:
    t = np.arange(n) / RATE
    e = np.minimum(1.0, t / max(a, 1e-4))
    dec = np.exp(-(t - a) / max(d, 1e-4))
    e = np.where(t > a, s + (1 - s) * dec, e)
    if r > 0:
        tail = np.minimum(1.0, (t[-1] - t) / r)
        e = e * tail
    return e


def pad(chord, seconds: float) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    out = np.zeros((n, 2))
    for semi in chord:
        f = hz(semi + 12)
        for det, pan in ((-0.4, 0.3), (0.0, 0.5), (0.4, 0.7)):
            v = np.sin(2 * np.pi * f * (1 + det / 1200) * t + np.random.rand() * 6.28)
            v += 0.3 * np.sin(2 * np.pi * 2 * f * (1 + det / 1200) * t)
            out[:, 0] += v * (1 - pan)
            out[:, 1] += v * pan
    tremolo = 1 + 0.08 * np.sin(2 * np.pi * 0.17 * t)
    return out * env(n, 2.5, 4.0, 0.7, 2.5)[:, None] * tremolo[:, None] * 0.045


def sub(semi: int, seconds: float) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    v = np.sin(2 * np.pi * hz(semi - 12) * t)
    return np.stack([v, v], 1) * env(n, 0.8, 6.0, 0.6, 1.5)[:, None] * 0.11


def pluck(semi: int, pan: float, vel: float) -> np.ndarray:
    n = int(1.6 * RATE)
    t = np.arange(n) / RATE
    f = hz(semi, 220.0)
    v = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 6) \
        + 0.12 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t * 9)
    v *= env(n, 0.004, 0.45) * np.exp(-t * 1.2)
    return np.stack([v * (1 - pan), v * pan], 1) * vel * 0.16


def life_melody(steps: int, rng: np.random.Generator, width: int = 11) -> list[list[int]]:
    """a 1-d game of life over the scale degrees, births only: the degrees whose
    cell was born this step. the neighbourhood is two either side, born with 3,
    survive with 2 or 3. the ring is re-dealt when it dies out or sits still,
    like the board."""
    cells = rng.random(width) < 0.35
    seen: list[tuple] = []
    out = []
    prev = np.zeros(width, bool)
    for _ in range(steps):
        out.append([i for i in range(width) if cells[i] and not prev[i]])
        prev = cells
        nb = sum(np.roll(cells, k) for k in (-2, -1, 1, 2))
        nxt = np.where(cells, (nb == 2) | (nb == 3), nb == 3)
        key = tuple(nxt)
        if not nxt.any() or key in seen[-4:]:
            nxt = rng.random(width) < 0.35
            seen = []
        seen.append(key)
        cells = nxt
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--seconds", type=float, default=57.0)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    np.random.seed(args.seed)
    total = int(args.seconds * RATE)
    mix = np.zeros((total + RATE * 4, 2))

    def place(sig: np.ndarray, at: float) -> None:
        i = int(at * RATE)
        n = min(len(sig), len(mix) - i)
        if n > 0:
            mix[i:i + n] += sig[:n]

    # pad and sub: one chord every four bars, overlapping a little
    t = 0.0
    c = 0
    while t < args.seconds:
        chord = CHORDS[c % len(CHORDS)]
        place(pad(chord, 4 * BAR + 2.5), t)
        place(sub(chord[0], 4 * BAR), t)
        t += 4 * BAR
        c += 1

    # plucks: the births of a one-dimensional life, one a step, now and then two
    steps = int(args.seconds / STEP)
    rows = life_melody(steps, rng)
    for s, row in enumerate(rows):
        if not row or rng.random() < 0.3:
            continue
        rng.shuffle(row)
        for i in row[:2 if rng.random() < 0.2 else 1]:
            semi = SCALE[i]
            pan = 0.25 + 0.5 * i / 10
            vel = 0.55 + 0.45 * rng.random()
            place(pluck(semi, pan, vel), s * STEP + rng.random() * 0.012)

    out = mix[:total]
    fade_in = np.minimum(1.0, np.arange(total) / (1.0 * RATE))
    fade_out = np.minimum(1.0, (total - np.arange(total)) / (2.5 * RATE))
    out = out * (fade_in * fade_out)[:, None]
    out = out / max(1e-9, np.abs(out).max()) * 0.7     # peak at -3 dbfs, about -16 lufs
    with wave.open(args.output, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((out * 32767).astype("<i2").tobytes())
    print(f"wrote {args.output}: {args.seconds:.0f}s, {len(rows)} steps, {sum(bool(r) for r in rows)} with notes")


if __name__ == "__main__":
    main()
