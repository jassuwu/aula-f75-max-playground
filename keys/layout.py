"""the aula f75 max, 80 keys, as a physical layout.

led: the index the firmware expects in the 04 20 stream. confirmed on the board.
x, w: position and width in key units from the standard 75% layout. approximate,
but good enough for adjacency and for sampling images onto keys.
mac: macos virtual keycode. fn is 63 but only ever arrives as a flags change.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Key:
    name: str
    led: int
    row: int
    x: float
    w: float
    mac: int | None

    @property
    def cx(self) -> float:
        return self.x + self.w / 2


def _row(row: int, spec: list[tuple]) -> list[Key]:
    out = []
    for item in spec:
        name, led, x, w, mac = (item + (1.0, None))[:5] if len(item) < 5 else item
        out.append(Key(name, led, row, float(x), float(w), mac))
    return out


# (name, led, x, w, mac)
ROWS: list[list[Key]] = [
    _row(0, [
        ("esc", 0x01, 0, 1, 53),
        ("f1", 0x02, 1.5, 1, 122), ("f2", 0x03, 2.5, 1, 120), ("f3", 0x04, 3.5, 1, 99), ("f4", 0x05, 4.5, 1, 118),
        ("f5", 0x06, 6, 1, 96), ("f6", 0x07, 7, 1, 97), ("f7", 0x08, 8, 1, 98), ("f8", 0x09, 9, 1, 100),
        ("f9", 0x0A, 10.5, 1, 101), ("f10", 0x0B, 11.5, 1, 109), ("f11", 0x0C, 12.5, 1, 103), ("f12", 0x0D, 13.5, 1, 111),
    ]),
    _row(1, [
        ("`", 0x13, 0, 1, 50),
        ("1", 0x14, 1, 1, 18), ("2", 0x15, 2, 1, 19), ("3", 0x16, 3, 1, 20), ("4", 0x17, 4, 1, 21), ("5", 0x18, 5, 1, 23),
        ("6", 0x19, 6, 1, 22), ("7", 0x1A, 7, 1, 26), ("8", 0x1B, 8, 1, 28), ("9", 0x1C, 9, 1, 25), ("0", 0x1D, 10, 1, 29),
        ("-", 0x1E, 11, 1, 27), ("=", 0x1F, 12, 1, 24), ("backspace", 0x67, 13, 2, 51), ("del", 0x77, 15.25, 1, 117),
    ]),
    _row(2, [
        ("tab", 0x25, 0, 1.5, 48),
        ("q", 0x26, 1.5, 1, 12), ("w", 0x27, 2.5, 1, 13), ("e", 0x28, 3.5, 1, 14), ("r", 0x29, 4.5, 1, 15), ("t", 0x2A, 5.5, 1, 17),
        ("y", 0x2B, 6.5, 1, 16), ("u", 0x2C, 7.5, 1, 32), ("i", 0x2D, 8.5, 1, 34), ("o", 0x2E, 9.5, 1, 31), ("p", 0x2F, 10.5, 1, 35),
        ("[", 0x30, 11.5, 1, 33), ("]", 0x31, 12.5, 1, 30), ("\\", 0x43, 13.5, 1.5, 42), ("pgup", 0x76, 15.25, 1, 116),
    ]),
    _row(3, [
        ("caps", 0x37, 0, 1.75, 57),
        ("a", 0x38, 1.75, 1, 0), ("s", 0x39, 2.75, 1, 1), ("d", 0x3A, 3.75, 1, 2), ("f", 0x3B, 4.75, 1, 3), ("g", 0x3C, 5.75, 1, 5),
        ("h", 0x3D, 6.75, 1, 4), ("j", 0x3E, 7.75, 1, 38), ("k", 0x3F, 8.75, 1, 40), ("l", 0x40, 9.75, 1, 37),
        (";", 0x41, 10.75, 1, 41), ("'", 0x42, 11.75, 1, 39), ("enter", 0x55, 12.75, 2.25, 36), ("pgdn", 0x79, 15.25, 1, 121),
    ]),
    _row(4, [
        ("lshift", 0x49, 0, 2.25, 56),
        ("z", 0x4A, 2.25, 1, 6), ("x", 0x4B, 3.25, 1, 7), ("c", 0x4C, 4.25, 1, 8), ("v", 0x4D, 5.25, 1, 9), ("b", 0x4E, 6.25, 1, 11),
        ("n", 0x4F, 7.25, 1, 45), ("m", 0x50, 8.25, 1, 46), (",", 0x51, 9.25, 1, 43), (".", 0x52, 10.25, 1, 47), ("/", 0x53, 11.25, 1, 44),
        ("rshift", 0x54, 12.25, 1.75, 60), ("up", 0x65, 14.25, 1, 126), ("end", 0x78, 15.25, 1, 119),
    ]),
    _row(5, [
        ("lctrl", 0x5B, 0, 1.25, 59), ("win", 0x5C, 1.25, 1.25, 55), ("lalt", 0x5D, 2.5, 1.25, 58),
        ("space", 0x5E, 3.75, 6.25, 49),
        ("ralt", 0x5F, 10, 1, 61), ("fn", 0x60, 11, 1, 63),
        ("left", 0x63, 13.25, 1, 123), ("down", 0x64, 14.25, 1, 125), ("right", 0x66, 15.25, 1, 124),
    ]),
]

KEYS: list[Key] = [k for row in ROWS for k in row]
BY_NAME: dict[str, Key] = {k.name: k for k in KEYS}
BY_MAC: dict[int, Key] = {k.mac: k for k in KEYS if k.mac is not None}
LED_ORDER: list[int] = [k.led for k in KEYS]
MODIFIERS = {"lshift", "rshift", "lctrl", "lalt", "ralt", "win", "caps", "fn"}
WIDTH = 16.25
HEIGHT = 6

assert len(KEYS) == 80, len(KEYS)
assert len(set(LED_ORDER)) == 80
assert len(BY_NAME) == 80

RGB = tuple[int, int, int]


def neighbor(key: Key, direction: str) -> Key:
    """the key one step away, wrapping at the edges.

    left/right walk along the row. up/down go to the key in the next row whose
    centre is nearest, so the stagger and the wide keys behave physically:
    down from v, b or n lands on space; up from space lands on b.
    """
    row = ROWS[key.row]
    if direction in ("left", "right"):
        i = row.index(key)
        step = 1 if direction == "right" else -1
        return row[(i + step) % len(row)]
    if direction in ("up", "down"):
        step = -1 if direction == "up" else 1
        target = ROWS[(key.row + step) % len(ROWS)]
        return min(target, key=lambda k: abs(k.cx - key.cx))
    raise ValueError(direction)
