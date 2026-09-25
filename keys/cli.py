"""keys <source>: put a source on the board."""
from __future__ import annotations

import argparse
import sys

from .board import Board, BoardNotFound
from .tap import TapUnavailable


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="keys", description="the f75 max as an 80-key display")
    ap.add_argument("--quiet", action="store_true", help="no sound")
    ap.add_argument("--seconds", type=float, default=None, help="stop after this long (default: run until esc is held)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snake", help="snake on the whole board. arrows steer, hold esc to quit")
    sub.add_parser("rows", help="test pattern: one colour per row")
    pl = sub.add_parser("play", help="play a video on the keys, synced to its audio. hold esc to stop")
    pl.add_argument("file")
    pl.add_argument("--fit", choices=("stretch", "fill", "fit"), default="stretch")
    sub.add_parser("clock", help="set the board's clock to local time")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "clock":
            b = Board()
            try:
                b.set_clock()
            finally:
                b.close()
            print("clock set")
            return
        from .loop import run
        if args.cmd == "rows":
            from .sources.pattern import Rows
            run(Rows(), seconds=args.seconds)
        elif args.cmd == "play":
            from .sources.video import Video
            run(Video(args.file, fit=args.fit, audio=not args.quiet), seconds=args.seconds)
        elif args.cmd == "snake":
            from .sound import Sound
            from .sources.snake import Snake
            sound = Sound(enabled=not args.quiet)
            try:
                run(Snake(sound=sound), seconds=args.seconds)
            finally:
                sound.close()
    except (BoardNotFound, TapUnavailable, FileNotFoundError) as e:
        sys.exit(f"keys: {e}")
