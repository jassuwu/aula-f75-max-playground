"""a quartz event tap: every key down and key up, on a background run loop.

capture=True swallows events so a game doesn't type into whatever is focused.
that needs the host process trusted for accessibility; listen-only needs input
monitoring. macos prompts once. nothing typed is written anywhere.
"""
from __future__ import annotations

import threading
from typing import Callable

import CoreFoundation as CF
import Quartz as Q

from .layout import BY_MAC, MODIFIERS, Key

Listener = Callable[[Key, bool, float], None]  # key, down, monotonic seconds


class TapUnavailable(RuntimeError):
    pass


class Tap:
    def __init__(self, listener: Listener, capture: bool) -> None:
        self.listener = listener
        self.capture = capture
        self._port = None
        self._loop = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._error: str | None = None
        self._mods_down: set[int] = set()

    def _callback(self, proxy, type_, event, refcon):
        if type_ in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            Q.CGEventTapEnable(self._port, True)
            return event
        code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
        key = BY_MAC.get(code)
        if key is None:
            return None if self.capture else event
        t = Q.CGEventGetTimestamp(event) / 1e9
        if type_ == Q.kCGEventFlagsChanged:
            down = code not in self._mods_down
            if down:
                self._mods_down.add(code)
            else:
                self._mods_down.discard(code)
            self.listener(key, down, t)
            return None if self.capture else event
        if type_ == Q.kCGEventKeyDown:
            if Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat):
                return None if self.capture else event
            self.listener(key, True, t)
        elif type_ == Q.kCGEventKeyUp:
            self.listener(key, False, t)
        return None if self.capture else event

    def _run(self) -> None:
        mask = (Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp)
                | Q.CGEventMaskBit(Q.kCGEventFlagsChanged))
        options = Q.kCGEventTapOptionDefault if self.capture else Q.kCGEventTapOptionListenOnly
        self._port = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, options, mask, self._callback, None)
        if self._port is None:
            self._error = ("could not create the event tap. grant this terminal "
                           + ("accessibility (system settings > privacy & security > accessibility)" if self.capture
                              else "input monitoring (system settings > privacy & security > input monitoring)")
                           + " and run again.")
            self._ready.set()
            return
        source = CF.CFMachPortCreateRunLoopSource(None, self._port, 0)
        self._loop = CF.CFRunLoopGetCurrent()
        CF.CFRunLoopAddSource(self._loop, source, CF.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self._port, True)
        self._ready.set()
        CF.CFRunLoopRun()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="keys-tap", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if self._error:
            raise TapUnavailable(self._error)

    def stop(self) -> None:
        if self._port is not None:
            Q.CGEventTapEnable(self._port, False)
        if self._loop is not None:
            CF.CFRunLoopStop(self._loop)
        if self._thread is not None:
            self._thread.join(2)
