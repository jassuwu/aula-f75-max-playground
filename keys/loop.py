"""the player: one board, one source, a 30 hz tick by wall clock.

a source is anything with these four methods and one attribute:

    keys: str | None      "capture" (swallow everything), "observe", or None
    start(layout) -> None
    on_key(key, down) -> None
    tick(t, dt) -> dict[str, rgb] | None    None means "no change"
    stop() -> None
    done: bool            optional; set it to end the run (a video that finished)

holding esc for a second always stops the source and hands the keys back,
before the source sees the event. when frames stop the firmware fades the last
one out and restores its own lighting within about a minute; nothing to do.
"""
from __future__ import annotations

import queue
import time
from typing import Protocol

from . import layout
from .board import Board, BoardLost
from .layout import RGB, Key
from .tap import Tap

FPS = 30
HOLD = 1.0       # resend an unchanged frame this often so the firmware keeps the board
ESC_HOLD = 1.0   # seconds of esc to quit


class Source(Protocol):
    keys: str | None

    def start(self, lay) -> None: ...
    def on_key(self, key: Key, down: bool) -> None: ...
    def tick(self, t: float, dt: float) -> dict[str, RGB] | None: ...
    def stop(self) -> None: ...


RETRY = 1.0      # seconds between attempts to reopen a board that dropped out


def run(source: Source, fps: int = FPS, board: Board | None = None, seconds: float | None = None,
        wait: float | None = 300.0, say=print) -> None:
    board = board or Board.wait(wait, say=say)
    events: queue.Queue[tuple[Key, bool, float]] = queue.Queue()
    tap = None
    if source.keys:
        tap = Tap(lambda k, d, t: events.put((k, d, t)), capture=(source.keys == "capture"))
        tap.start()
    source.start(layout)
    period = 1.0 / fps
    esc_since: float | None = None
    last_sent = 0.0
    last_frame: dict[str, RGB] = {}
    t0 = time.monotonic()
    prev = t0
    retry_at = 0.0
    n = 0
    try:
        while True:
            now = time.monotonic()
            while True:
                try:
                    key, down, _ = events.get_nowait()
                except queue.Empty:
                    break
                if key.name == "esc":
                    esc_since = now if down else None
                source.on_key(key, down)
            if esc_since is not None and now - esc_since >= ESC_HOLD:
                break
            if seconds is not None and now - t0 >= seconds:
                break
            if getattr(source, "done", False):
                break
            frame = source.tick(now - t0, now - prev)
            prev = now
            if frame is not None:
                last_frame = frame
            if board is None and now >= retry_at:
                try:
                    board = Board()
                    say("the board is back.")
                    last_sent = 0.0
                except Exception:
                    retry_at = now + RETRY
            if board is not None and (frame is not None or now - last_sent >= HOLD):
                try:
                    board.write(last_frame)
                    last_sent = now
                except BoardLost:
                    say("the board stopped answering. it sleeps five minutes after the last key press; "
                        "press any key on it to wake it.")
                    try:
                        board.close()
                    except Exception:
                        pass
                    board = None
                    retry_at = now + RETRY
            n += 1
            target = t0 + n * period
            sleep = target - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
            else:
                n = int((time.monotonic() - t0) / period)  # fell behind: drop, don't queue
    except KeyboardInterrupt:
        pass
    finally:
        source.stop()
        if tap is not None:
            tap.stop()
        if board is not None:
            board.close()
