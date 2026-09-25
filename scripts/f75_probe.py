"""probe the aula f75 max per-key real-time stream (04 20) over usb.

ram-only: nothing here writes the board's flash. see AGENTS.md.

usage:
  python scripts/f75_probe.py enumerate
  python scripts/f75_probe.py stream [--unlock] [--seconds N] [--pattern esc|rows]
"""
from __future__ import annotations

import argparse
import sys
import time

import hid

VID, PID = 0x0C45, 0x800A
CMD_USAGE_PAGE = 0xFF13
GAP = 0.040  # vendor cmd_delaytime is 35 ms
PACKET_GAP = 0.005  # between data packets inside a frame; --packet-gap overrides

# f75 max, 80 keys, led index per key. derived from punkster81's f108 pro map,
# which matches the f75 max rgb-keyboard.xml light_index values on every
# key checked (see docs/research). rows top to bottom, left to right.
ROWS = [
    [("esc", 0x01)] + [(f"f{i}", 0x01 + i) for i in range(1, 13)],
    [("`", 0x13)] + [(str(d), 0x13 + i) for i, d in enumerate("1234567890", 1)]
    + [("-", 0x1E), ("=", 0x1F), ("backspace", 0x67), ("del", 0x77)],
    [("tab", 0x25)] + [(c, 0x26 + i) for i, c in enumerate("qwertyuiop")]
    + [("[", 0x30), ("]", 0x31), ("\\", 0x43), ("pgup", 0x76)],
    [("caps", 0x37)] + [(c, 0x38 + i) for i, c in enumerate("asdfghjkl")]
    + [(";", 0x41), ("'", 0x42), ("enter", 0x55), ("pgdn", 0x79)],
    [("lshift", 0x49)] + [(c, 0x4A + i) for i, c in enumerate("zxcvbnm,./")]
    + [("rshift", 0x54), ("up", 0x65), ("end", 0x78)],
    [("lctrl", 0x5B), ("win", 0x5C), ("lalt", 0x5D), ("space", 0x5E),
     ("ralt", 0x5F), ("fn", 0x60), ("left", 0x63), ("down", 0x64), ("right", 0x66)],
]
KEYS = {name: idx for row in ROWS for name, idx in row}
assert len(KEYS) == 80, len(KEYS)

UNLOCK_REALTIME = bytes(
    [0x00, 0x01, 0x5A, 0x1A, 0x03, 0x09, 0x00, 0x01, 0x02, 0x00, 0x01]
    + [0x00] * 51 + [0xAA, 0x55]
)


def pkt(c0: int, c1: int, arg: int = 0) -> bytes:
    return bytes([c0, c1, 0, 0, 0, 0, 0, 0, arg]) + bytes(55)


def cmd_path() -> bytes:
    for d in hid.enumerate(VID, PID):
        if d["usage_page"] == CMD_USAGE_PAGE:
            return d["path"]
    sys.exit("f75 max command interface (usage page 0xff13) not found; is it wired?")


class Board:
    def __init__(self) -> None:
        self.dev = hid.device()
        self.dev.open_path(cmd_path())
        self.log: list[str] = []

    def close(self) -> None:
        self.dev.close()

    def set(self, data: bytes, label: str = "") -> None:
        assert len(data) == 64, len(data)
        for attempt in range(3):
            try:
                n = self.dev.send_feature_report(b"\x00" + data)
                if n < 0:
                    raise OSError(self.dev.error())
                return
            except OSError as e:
                if attempt == 2:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def get(self) -> bytes | None:
        try:
            r = bytes(self.dev.get_feature_report(0, 65))
            return r[1:] if len(r) == 65 else r
        except OSError as e:
            return None

    def cmd(self, c1: int, arg: int = 0, label: str = "") -> bytes | None:
        self.set(pkt(0x04, c1, arg))
        time.sleep(GAP)
        ack = self.get()
        shown = ack[:12].hex(" ") if ack else "no reply"
        print(f"  04 {c1:02x} arg={arg:02x} -> {shown}", flush=True)
        time.sleep(GAP)
        return ack

    def handshake(self) -> None:
        print("handshake (punkster81 form, with unlock):")
        self.cmd(0x18)
        self.cmd(0x28, 0x01)
        self.set(UNLOCK_REALTIME)
        time.sleep(GAP)
        ack = self.get()
        print(f"  unlock -> {ack[:12].hex(' ') if ack else 'no reply'}", flush=True)
        self.cmd(0x02)
        time.sleep(0.2)

    def frame(self, colors: dict[int, tuple[int, int, int]], verbose: bool = False) -> None:
        """one frame: start, 5 data packets of 16 [idx r g b], zero packet, apply."""
        self.set(pkt(0x04, 0x20, 0x08))
        time.sleep(GAP if verbose else PACKET_GAP)
        a1 = self.get()
        entries = [(idx, *colors.get(idx, (0, 0, 0))) for idx in KEYS.values()]
        for i in range(0, len(entries), 16):
            chunk = entries[i:i + 16]
            data = bytes(b for e in chunk for b in e)
            self.set(data + bytes(64 - len(data)))
            time.sleep(PACKET_GAP)
        self.set(bytes(64))
        time.sleep(PACKET_GAP)
        self.set(pkt(0x04, 0x02))
        time.sleep(GAP if verbose else PACKET_GAP)
        a2 = self.get()
        if verbose:
            print(f"  04 20 start -> {a1[:12].hex(' ') if a1 else 'no reply'}")
            print(f"  04 02 apply -> {a2[:12].hex(' ') if a2 else 'no reply'}", flush=True)


ROW_COLORS = [(255, 0, 0), (255, 90, 0), (255, 220, 0), (0, 255, 0), (0, 80, 255), (180, 0, 255)]


def pattern(name: str) -> dict[int, tuple[int, int, int]]:
    if name == "esc":
        return {KEYS["esc"]: (255, 0, 0)}
    if name == "rows":
        out = {idx: ROW_COLORS[r] for r, row in enumerate(ROWS) for _, idx in row}
        out[KEYS["esc"]] = (255, 255, 255)
        out[KEYS["space"]] = (255, 255, 255)
        return out
    if name == "off":
        return {}
    sys.exit(f"unknown pattern {name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("enumerate")
    sub.add_parser("rtc", help="set the board clock to local time")
    s = sub.add_parser("stream")
    s.add_argument("--unlock", action="store_true")
    s.add_argument("--seconds", type=float, default=5.0)
    s.add_argument("--pattern", default="esc")
    s.add_argument("--fps", type=float, default=20.0)
    s.add_argument("--packet-gap", type=float, default=5.0, help="ms between packets inside a frame")
    args = ap.parse_args()

    if args.cmd == "enumerate":
        for d in hid.enumerate(VID, PID):
            print(d["interface_number"], hex(d["usage_page"]), hex(d["usage"]), d["path"])
        return

    if args.cmd == "rtc":
        b = Board()
        try:
            rtc_sync(b)
        finally:
            b.close()
        return

    global PACKET_GAP
    PACKET_GAP = args.packet_gap / 1000.0
    b = Board()
    try:
        if args.unlock:
            b.handshake()
        colors = pattern(args.pattern)
        print(f"first frame ({args.pattern}), verbose:")
        t0 = time.perf_counter()
        b.frame(colors, verbose=True)
        print(f"  frame time {1000 * (time.perf_counter() - t0):.0f} ms")
        n = 0
        end = time.time() + args.seconds
        period = 1.0 / args.fps
        t0 = time.perf_counter()
        while time.time() < end:
            b.frame(colors)
            n += 1
            time.sleep(period)
        dt = time.perf_counter() - t0
        print(f"streamed {n} frames in {dt:.1f}s ({n / dt:.1f} fps incl. sleep)")
    finally:
        b.close()




def rtc_sync(b: "Board") -> None:
    """set the board's clock to local time. ghost-cr's verified cable sequence:
    04 18, 04 28 01, `00 01 5a YY MM DD HH mm SS 00 05 .. aa 55`, 04 02.
    note: punkster81's 'unlock' packet is this same format with a fixed date,
    which is why sending it set the clock to 2026-03-09 00:01:02."""
    t = time.localtime()
    payload = bytes([0x00, 0x01, 0x5A, t.tm_year - 2000, t.tm_mon, t.tm_mday,
                     t.tm_hour, t.tm_min, t.tm_sec, 0x00, 0x05, 0x00, 0x00, 0x00, 0xAA, 0x55])
    payload += bytes(64 - len(payload))
    print(f"rtc sync -> {t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}")
    b.cmd(0x18)
    b.cmd(0x28, 0x01)
    b.set(payload)
    time.sleep(GAP)
    ack = b.get()
    print(f"  rtc payload -> {ack[:12].hex(' ') if ack else 'no reply'}")
    time.sleep(GAP)
    b.cmd(0x02)


if __name__ == "__main__":
    main()
