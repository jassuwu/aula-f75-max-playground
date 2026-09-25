"""snake on all 80 keys.

the whole board is the field, edges wrap, movement is physical (see
layout.neighbor). arrows steer and are tiles too. score is the length. green
snake, red apple, enter is the restart button after you die.
"""
from __future__ import annotations

import math
import random
from collections import deque

from ..layout import RGB, Key, neighbor

HEAD = (40, 255, 40)
TAIL = (0, 50, 0)
APPLE = (255, 0, 0)
FLASH = (255, 255, 255)
DEAD = (70, 0, 0)
RESTART = (255, 255, 255)

START = ("a", "s", "d")          # tail to head
START_SPEED = 3.0                # steps per second
SPEED_PER_APPLE = 1.06
MAX_SPEED = 8.0
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}
ARROWS = set(OPPOSITE)


def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _scale(c: RGB, k: float) -> RGB:
    return tuple(int(v * k) for v in c)


class _Mute:
    def play(self, name: str, n: int = 0) -> None:
        pass


class Snake:
    keys = "capture"

    def __init__(self, rng: random.Random | None = None, sound=None) -> None:
        self.rng = rng or random.Random()
        self.sound = sound or _Mute()

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self, layout) -> None:
        self.layout = layout
        self.reset()

    def stop(self) -> None:
        pass

    def reset(self) -> None:
        by = self.layout.BY_NAME
        self.body: deque[Key] = deque(by[n] for n in START)   # tail .. head
        self.direction = "right"
        self.queued: deque[str] = deque(maxlen=2)
        self.apples = 0
        self.apple: Key | None = None
        self.apple_at = 0.0          # when the next apple appears
        self.state = "waiting"       # waiting | running | dying | dead | won
        self.step_at = 0.0
        self.flash_head = 0
        self.flash_key: Key | None = None
        self.flash_key_frames = 0
        self.dying_t = 0.0
        self.t = 0.0
        self._spawn_apple()

    # ── input ────────────────────────────────────────────────────────────────
    def on_key(self, key: Key, down: bool) -> None:
        if not down:
            return
        if self.state in ("dead", "won"):
            if key.name == "enter":
                self.reset()
                self.sound.play("start")
            return
        if key.name in ARROWS:
            self.flash_key, self.flash_key_frames = key, 2
            last = self.queued[-1] if self.queued else self.direction
            if key.name == OPPOSITE[last]:
                return
            if key.name != last:
                self.queued.append(key.name)
            if self.state == "waiting":
                self.state = "running"
                self.step_at = self.t + 1.0 / self.speed
                self.sound.play("start")

    # ── rules ────────────────────────────────────────────────────────────────
    @property
    def speed(self) -> float:
        return min(MAX_SPEED, START_SPEED * SPEED_PER_APPLE ** self.apples)

    @property
    def head(self) -> Key:
        return self.body[-1]

    @property
    def length(self) -> int:
        return len(self.body)

    def _spawn_apple(self) -> None:
        taken = set(self.body)
        free = [k for k in self.layout.KEYS if k not in taken]
        self.apple = self.rng.choice(free) if free else None

    def step(self) -> None:
        if self.queued:
            self.direction = self.queued.popleft()
        nxt = neighbor(self.head, self.direction)
        eating = nxt is self.apple
        body = set(self.body)
        if not eating:
            body.discard(self.body[0])      # the tail moves out of the way
        if nxt in body:
            self.state = "dying"
            self.dying_t = self.t
            self.sound.play("die")
            return
        self.body.append(nxt)
        if eating:
            self.apples += 1
            self.flash_head = 2
            self.apple = None
            self.apple_at = self.t + 0.25
            if self.length == len(self.layout.KEYS):
                self.state = "won"
                self.sound.play("win")
            else:
                self.sound.play("eat", self.apples - 1)
        else:
            self.body.popleft()

    # ── frame ────────────────────────────────────────────────────────────────
    def tick(self, t: float, dt: float) -> dict[str, RGB] | None:
        self.t = t
        if self.state == "running":
            while t >= self.step_at and self.state == "running":
                self.step()
                self.step_at += 1.0 / self.speed
            if self.apple is None and t >= self.apple_at and self.state == "running":
                self._spawn_apple()
        if self.state == "dying" and t - self.dying_t >= 0.6:
            self.state = "dead"
        return self.render(t)

    def render(self, t: float) -> dict[str, RGB]:
        frame: dict[str, RGB] = {}
        if self.state == "dying":
            # two red flashes: on 0-150 ms, off, on 300-450 ms, off
            phase = (t - self.dying_t) % 0.3
            if phase < 0.15:
                frame = {k.name: APPLE for k in self.layout.KEYS}
            return frame
        if self.state == "dead":
            for k in self.body:
                frame[k.name] = DEAD
            pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 2 * math.pi))
            frame["enter"] = _scale(RESTART, pulse)
            return frame
        n = self.length
        for i, k in enumerate(self.body):
            frame[k.name] = _lerp(TAIL, HEAD, i / max(1, n - 1))
        if self.state == "won":
            pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 2 * math.pi))
            frame["enter"] = _scale(RESTART, pulse)
            return frame
        if self.flash_head > 0:
            frame[self.head.name] = FLASH
            self.flash_head -= 1
        if self.apple is not None:
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * 2 * math.pi * 0.8))
            frame[self.apple.name] = _scale(APPLE, pulse)
        if self.flash_key is not None and self.flash_key_frames > 0:
            frame[self.flash_key.name] = FLASH
            self.flash_key_frames -= 1
        return frame
