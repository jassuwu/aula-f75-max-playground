"""play a video file on the keys, synced to its own audio.

ffmpeg decodes to a small rgb grid shaped like the key area; each key is the
average of its real rectangle (layout.RECTS), done in linear light so edges and
greys look right on leds. the audio clock drives the frame index, so the keys
stay locked to the music. esc-hold stops it; other keys pass through.
"""
from __future__ import annotations

import math
import os
import subprocess
import tempfile

from ..layout import ASPECT, KEYS, RECTS

GRID_H = 50
GRID_W = round(GRID_H * ASPECT)   # 129 for the f75 max
FPS = 30
FITS = ("stretch", "fill", "fit")


def _lin(v: int) -> int:
    c = v / 255
    c = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return round(255 * c)


TO_LINEAR = bytes(_lin(v) for v in range(256))


class Sampler:
    """averages a packed rgb24 grid (w x h) over every key's rectangle."""

    def __init__(self, w: int = GRID_W, h: int = GRID_H) -> None:
        self.w, self.h = w, h
        self.spans: dict[str, list[tuple[int, int]]] = {}
        self.count: dict[str, int] = {}
        for k in KEYS:
            l, t, r, b = RECTS[k.name]
            x0, x1 = int(l * w), max(int(l * w) + 1, math.ceil(r * w))
            y0, y1 = int(t * h), max(int(t * h) + 1, math.ceil(b * h))
            x1, y1 = min(x1, w), min(y1, h)
            self.spans[k.name] = [((y * w + x0) * 3, (y * w + x1) * 3) for y in range(y0, y1)]
            self.count[k.name] = (x1 - x0) * (y1 - y0)

    def sample(self, frame: bytes) -> dict[str, tuple[int, int, int]]:
        lin = frame.translate(TO_LINEAR)
        out = {}
        for name, spans in self.spans.items():
            r = g = b = 0
            for a, z in spans:
                row = lin[a:z]
                r += sum(row[0::3])
                g += sum(row[1::3])
                b += sum(row[2::3])
            n = self.count[name]
            out[name] = (r // n, g // n, b // n)
        return out


def _filter(fit: str) -> str:
    w, h = GRID_W, GRID_H
    if fit == "stretch":
        return f"scale={w}:{h}:flags=area"
    if fit == "fill":
        return f"scale={w}:-2:flags=area,crop={w}:{h}"
    if fit == "fit":
        return f"scale=-2:{h}:flags=area,pad={w}:{h}:(ow-iw)/2:0:black"
    raise ValueError(fit)


class _WallClock:
    def __init__(self) -> None:
        self.t0: float | None = None

    def start(self, now: float) -> None:
        self.t0 = now

    def position(self, now: float) -> float:
        return now - (self.t0 or now)

    def finished(self) -> bool:
        return False

    def stop(self) -> None:
        pass


class _AudioClock:
    """plays the file's audio through nssound and reads its position as the clock."""

    def __init__(self, path: str) -> None:
        fd, self.tmp = tempfile.mkstemp(suffix=".m4a", prefix="keys-audio-")
        os.close(fd)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-vn", "-c:a", "aac", "-b:a", "192k", self.tmp],
                       check=True)
        from AppKit import NSSound
        self.sound = NSSound.alloc().initWithContentsOfFile_byReference_(self.tmp, True)
        if self.sound is None:
            raise RuntimeError("could not load the audio track")
        self.started = False

    def start(self, now: float) -> None:
        self.sound.play()
        self.started = True

    def position(self, now: float) -> float:
        return float(self.sound.currentTime())

    def finished(self) -> bool:
        return self.started and not self.sound.isPlaying()

    def stop(self) -> None:
        self.sound.stop()
        try:
            os.unlink(self.tmp)
        except OSError:
            pass


class Video:
    keys = "observe"

    def __init__(self, path: str, fit: str = "stretch", audio: bool = True) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        self.path, self.fit, self.audio = path, fit, audio
        self.done = False

    def start(self, layout) -> None:
        self.sampler = Sampler()
        self.frame_bytes = GRID_W * GRID_H * 3
        self.clock = _AudioClock(self.path) if self.audio else _WallClock()
        self.proc = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-i", self.path, "-an", "-vf", f"fps={FPS},{_filter(self.fit)}",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, bufsize=self.frame_bytes * 4)
        self.index = -1
        self.current = self._read()          # block until ffmpeg is ready, then start the music
        self.started = False

    def _read(self) -> bytes | None:
        data = self.proc.stdout.read(self.frame_bytes)
        if not data or len(data) < self.frame_bytes:
            return None
        self.index += 1
        return data

    def on_key(self, key, down) -> None:
        pass

    def tick(self, t: float, dt: float):
        if not self.started:
            self.clock.start(t)
            self.started = True
            return self.sampler.sample(self.current)
        if self.clock.finished():
            self.done = True
            return None
        target = int(self.clock.position(t) * FPS)
        if target <= self.index:
            return None
        frame = self.current
        while self.index < target:
            frame = self._read()
            if frame is None:
                self.done = True
                return None
        self.current = frame
        return self.sampler.sample(frame)

    def stop(self) -> None:
        self.clock.stop()
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(2)
