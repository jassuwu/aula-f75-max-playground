"""tiny chiptune sound effects, synthesized at startup, played off the game loop.

no files, no dependencies beyond appkit. every effect is a list of notes
(frequency hz, seconds) rendered as a soft square wave. playback happens on a
worker thread so a slow audio device never stalls a frame.
"""
from __future__ import annotations

import io
import math
import queue
import struct
import threading
import wave

RATE = 44100
VOLUME = 0.12

Note = tuple[float, float]  # frequency (0 = rest), seconds


def _render(notes: list[Note], duty: float = 0.5, glide: bool = False) -> bytes:
    out = bytearray()
    phase = 0.0
    for idx, (f, dur) in enumerate(notes):
        n = int(RATE * dur)
        f_next = notes[idx + 1][0] if glide and idx + 1 < len(notes) else f
        for i in range(n):
            k = i / max(1, n)
            freq = f + (f_next - f) * k if glide else f
            attack = min(1.0, i / 90)
            release = min(1.0, (n - i) / 400)
            if freq <= 0:
                v = 0.0
            else:
                phase = (phase + freq / RATE) % 1.0
                v = 1.0 if phase < duty else -1.0
            out += struct.pack("<h", int(v * attack * release * VOLUME * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(out))
    return buf.getvalue()


def _hz(semitones_from_a4: float) -> float:
    return 440.0 * 2 ** (semitones_from_a4 / 12)


# a major pentatonic, climbing: the eat blip rises as the snake grows
_PENTA = [0, 2, 4, 7, 9]


def _eat_pitch(n: int) -> float:
    octave, step = divmod(min(n, 14), 5)
    return _hz(3 + 12 * octave + _PENTA[step])  # starts on c5


def _effects() -> dict[str, bytes]:
    fx = {
        "start": _render([(_hz(3), 0.05), (_hz(10), 0.07)], duty=0.25),
        "die": _render([(_hz(-2), 0.12), (_hz(-7), 0.12), (_hz(-14), 0.28)], duty=0.5, glide=True),
        "win": _render([(_hz(3), 0.08), (_hz(7), 0.08), (_hz(10), 0.08), (_hz(15), 0.3)], duty=0.25),
        "silence": _render([(0, 0.02)]),
    }
    for n in range(15):
        p = _eat_pitch(n)
        fx[f"eat{n}"] = _render([(p, 0.04), (p * 1.5, 0.06)], duty=0.25)
    return fx


class Sound:
    """fire-and-forget effects. `play("eat", 7)` picks the pitch for 7 apples."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._q: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        if enabled:
            self._thread = threading.Thread(target=self._run, name="keys-sound", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        from AppKit import NSSound
        from Foundation import NSData

        sounds = {}
        for name, wav in _effects().items():
            data = NSData.dataWithBytes_length_(wav, len(wav))
            sounds[name] = NSSound.alloc().initWithData_(data)
        sounds["silence"].play()  # wake the audio device before the first real effect
        while True:
            name = self._q.get()
            if name is None:
                return
            s = sounds.get(name)
            if s is None:
                continue
            if s.isPlaying():
                s.stop()
            s.play()

    def play(self, name: str, n: int = 0) -> None:
        if not self.enabled:
            return
        self._q.put(f"eat{min(n, 14)}" if name == "eat" else name)

    def close(self) -> None:
        if self._thread is not None:
            self._q.put(None)
            self._thread.join(1)
