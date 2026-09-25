"""the hid transport: 80 colours in, one 04 20 frame out.

65-byte feature reports on interface 3 (usage page 0xff13), leading 0x00 report
id. one frame is start, five data packets of 16 [led r g b], a zero packet, apply.
about 7 ms. ram-only. nothing here touches flash. see AGENTS.md.
"""
from __future__ import annotations

import time

import hid

from .layout import KEYS, RGB

VID, PID = 0x0C45, 0x800A
CMD_USAGE_PAGE = 0xFF13
GAP = 0.040  # between commands outside a frame; the vendor's cmd_delaytime is 35 ms


class BoardNotFound(RuntimeError):
    pass


class BoardLost(RuntimeError):
    """the board stopped answering: usually its battery-saving sleep, which starts
    five minutes after the last physical key press even while wired and streaming."""


def _pkt(c1: int, arg: int = 0) -> bytes:
    return bytes([0x04, c1, 0, 0, 0, 0, 0, 0, arg]) + bytes(55)


def _cmd_path() -> bytes:
    for d in hid.enumerate(VID, PID):
        if d["usage_page"] == CMD_USAGE_PAGE:
            return d["path"]
    raise BoardNotFound("f75 max not found on usb. it has to be wired; the dongle carries no per-key data.")


class Board:
    def __init__(self) -> None:
        self.dev = hid.device()
        self.dev.open_path(_cmd_path())
        self.frames = 0

    def close(self) -> None:
        self.dev.close()

    @classmethod
    def wait(cls, timeout: float | None = None, say=print) -> "Board":
        """open the board, waiting for it to appear (for example, waking from sleep)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        told = False
        while True:
            try:
                return cls()
            except (BoardNotFound, OSError):
                if deadline is not None and time.monotonic() >= deadline:
                    raise BoardNotFound("f75 max did not appear on usb. wire it and press any key on it to wake it.")
                if not told:
                    say("waiting for the board. if it is plugged in, press any key on it to wake it.")
                    told = True
                time.sleep(1.0)

    def _set(self, data: bytes) -> None:
        for attempt in range(3):
            try:
                if self.dev.send_feature_report(b"\x00" + data) < 0:
                    raise OSError(self.dev.error())
                return
            except OSError as e:
                if attempt == 2:
                    raise BoardLost(str(e)) from e
                time.sleep(0.02 * (attempt + 1))

    def _get(self) -> bytes | None:
        try:
            r = bytes(self.dev.get_feature_report(0, 65))
            return r[1:] if len(r) == 65 else r
        except OSError:
            return None

    def write(self, colors: dict[str, RGB]) -> None:
        """send one frame. keys missing from `colors` are off."""
        self._set(_pkt(0x20, 0x08))
        self._get()
        quads = bytearray()
        for k in KEYS:
            r, g, b = colors.get(k.name, (0, 0, 0))
            quads += bytes((k.led, r & 0xFF, g & 0xFF, b & 0xFF))
        for i in range(0, len(quads), 64):
            chunk = bytes(quads[i:i + 64])
            self._set(chunk + bytes(64 - len(chunk)))
        self._set(bytes(64))
        self._set(_pkt(0x02))
        self._get()
        self.frames += 1

    def set_clock(self) -> None:
        """set the board's clock to local time (ghost-cr's verified cable sequence)."""
        t = time.localtime()
        payload = bytes([0x00, 0x01, 0x5A, t.tm_year - 2000, t.tm_mon, t.tm_mday,
                         t.tm_hour, t.tm_min, t.tm_sec, 0x00, 0x05, 0x00, 0x00, 0x00, 0xAA, 0x55])
        for data in (_pkt(0x18), _pkt(0x28, 0x01), payload + bytes(64 - len(payload)), _pkt(0x02)):
            self._set(data)
            time.sleep(GAP)
            self._get()
            time.sleep(GAP)
