"""find which stream index drives a key that ignores its documented index.

lights every index in 0x01..0x7b that the layout does not use, one per second,
in green. keys 1..7 on the number row show the index under test in binary
(1 = bit 6, 7 = bit 0), white for a set bit. film the board; any single frame
shows the index and whether the mystery key is green. ram-only.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")
from keys.board import Board, _pkt  # noqa: E402
from keys.layout import KEYS, BY_NAME  # noqa: E402

BITS = ["1", "2", "3", "4", "5", "6", "7"]
USED = {k.led for k in KEYS}
CANDIDATES = [i for i in range(0x01, 0x7C) if i not in USED]
HOLD = 1.0
CYCLES = int(sys.argv[1]) if len(sys.argv) > 1 else 4


def frame(board: Board, extra: int) -> None:
    quads = bytearray()
    for k in KEYS:
        on = k.name in BITS and (extra >> (6 - BITS.index(k.name))) & 1
        quads += bytes((k.led, 255, 255, 255) if on else (k.led, 0, 0, 0))
    quads += bytes((extra, 0, 255, 0))
    board._set(_pkt(0x20, 0x08))
    board._get()
    for i in range(0, len(quads), 64):
        chunk = bytes(quads[i:i + 64])
        board._set(chunk + bytes(64 - len(chunk)))
    board._set(bytes(64))
    board._set(_pkt(0x02))
    board._get()


b = Board()
print(f"{len(CANDIDATES)} candidates: {[hex(c) for c in CANDIDATES]}", flush=True)
try:
    for cycle in range(CYCLES):
        for idx in CANDIDATES:
            end = time.time() + HOLD
            while time.time() < end:
                frame(b, idx)
                time.sleep(0.1)
        print(f"cycle {cycle + 1} done", flush=True)
finally:
    b.close()
