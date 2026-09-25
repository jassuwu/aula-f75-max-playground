"""keys <source>: put a source on the board."""
from __future__ import annotations

import argparse
import sys

from .board import Board, BoardNotFound
from .tap import TapUnavailable


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="keys", description="the f75 max as an 80-key display")
    ap.add_argument("--seconds", type=float, default=None, help="stop after this long (default: run until esc is held)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snake", help="snake on the whole board. arrows steer, hold esc to quit")
    sub.add_parser("rows", help="test pattern: one colour per row")
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
        elif args.cmd == "snake":
            from .sources.snake import Snake
            run(Snake(), seconds=args.seconds)
    except (BoardNotFound, TapUnavailable) as e:
        sys.exit(f"keys: {e}")
