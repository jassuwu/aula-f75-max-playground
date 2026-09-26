"""conway's game of life on all 80 keys.

each key is a cell. neighbours come from the geometry (layout.neighbors): the
keys either side in the row and the keys in the rows above and below, wrapping,
that come within half a key of it. a staggered key gets six or seven, space
gets seventeen, so the wide keys are hard to keep alive. birth on three,
survival on two or three, the usual rules on an unusual grid.

the board is the editor. tap a key to toggle it, space pauses, enter deals a
random board, backspace clears and pauses so you can draw. a running board that
has settled into a still life or a short loop is dealt again after a moment.
new cells are white and cool to blue as they age; a cell that dies glows red
for a beat. f3 blinks red on its own whatever we send, so that cell lies.
"""
from __future__ import annotations

import math
import random
from collections import Counter, deque

from ..layout import RGB, Key

GPS = 5.0            # generations per second
DENSITY = 0.35       # of a dealt board
FADE = 0.25          # seconds a dead cell glows
SETTLE = 3           # generations from white to the settled blue
HISTORY = 6          # a loop this short counts as settled
STALE = 4.0          # seconds a settled running board is left before it is dealt again

BORN = (225, 240, 255)
ALIVE = (30, 110, 255)
EMBER = (220, 40, 50)
PAUSED = (255, 255, 255)
CONTROLS = {"esc", "space", "enter", "backspace"}


def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _scale(c: RGB, k: float) -> RGB:
    return tuple(int(v * k) for v in c)


class Life:
    keys = "capture"

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self, layout) -> None:
        self.layout = layout
        self.graph: dict[Key, list[Key]] = {k: layout.neighbors(k) for k in layout.KEYS}
        self.t = 0.0
        self.alive: set[Key] = set()
        self.age: dict[Key, int] = {}
        self.dying: dict[Key, float] = {}     # key -> when it died
        self.history: deque[frozenset[Key]] = deque(maxlen=HISTORY)
        self.stale_since: float | None = None
        self.paused = False
        self.gen = 0
        self.deal()

    def stop(self) -> None:
        pass

    def deal(self) -> None:
        for k in self.alive:
            self.dying[k] = self.t
        self.alive = {k for k in self.layout.KEYS if self.rng.random() < DENSITY}
        self.age = {k: 0 for k in self.alive}
        self._touched()
        self.paused = False
        self.step_at = self.t + 1.0 / GPS

    def clear(self) -> None:
        for k in self.alive:
            self.dying[k] = self.t
        self.alive = set()
        self.age = {}
        self._touched()
        self.paused = True

    def toggle(self, key: Key) -> None:
        if key in self.alive:
            self.alive.discard(key)
            self.age.pop(key, None)
            self.dying[key] = self.t
        else:
            self.alive.add(key)
            self.age[key] = 0
            self.dying.pop(key, None)
        self._touched()

    def _touched(self) -> None:
        """the board changed by hand: forget what looked settled."""
        self.history.clear()
        self.stale_since = None

    # ── input ────────────────────────────────────────────────────────────────
    def on_key(self, key: Key, down: bool) -> None:
        if not down:
            return
        if key.name == "space":
            self.paused = not self.paused
            if not self.paused:
                self.step_at = self.t + 1.0 / GPS
        elif key.name == "enter":
            self.deal()
        elif key.name == "backspace":
            self.clear()
        elif key.name not in CONTROLS:
            self.toggle(key)

    # ── rules ────────────────────────────────────────────────────────────────
    @property
    def population(self) -> int:
        return len(self.alive)

    def step(self) -> None:
        counts: Counter[Key] = Counter()
        for k in self.alive:
            counts.update(self.graph[k])
        nxt = {k for k, c in counts.items() if c == 3 or (c == 2 and k in self.alive)}
        for k in self.alive - nxt:
            self.dying[k] = self.t
        self.age = {k: self.age.get(k, -1) + 1 for k in nxt}
        self.alive = nxt
        self.gen += 1
        state = frozenset(nxt)
        if state in self.history:
            if self.stale_since is None:
                self.stale_since = self.t
        else:
            self.stale_since = None
        self.history.append(state)

    # ── frame ────────────────────────────────────────────────────────────────
    def tick(self, t: float, dt: float) -> dict[str, RGB] | None:
        self.t = t
        if not self.paused:
            if t - self.step_at > 1.0:          # we were away (board asleep): don't replay the gap
                self.step_at = t
            while t >= self.step_at and not self.paused:
                self.step()
                self.step_at += 1.0 / GPS
            if self.stale_since is not None and t - self.stale_since >= STALE:
                self.deal()
        return self.render(t)

    def render(self, t: float) -> dict[str, RGB]:
        frame: dict[str, RGB] = {}
        for k, died in list(self.dying.items()):
            left = 1.0 - (t - died) / FADE
            if left <= 0 or k in self.alive:
                del self.dying[k]
                continue
            frame[k.name] = _scale(EMBER, left)
        for k in self.alive:
            frame[k.name] = _lerp(BORN, ALIVE, min(1.0, self.age[k] / SETTLE))
        if self.paused:
            pulse = 0.2 + 0.4 * (0.5 + 0.5 * math.sin(t * 2 * math.pi))
            frame["space"] = _scale(PAUSED, pulse)
        return frame
