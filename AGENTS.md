# keyboard-video

the AULA F75 Max (usb `0c45:800a`) as an 80-key colour display driven from a mac. the board is both the screen and the controller: every source is a function from time and key events to 80 colours.

read `docs/handoff/decision-keys.md` first, then `docs/research/aula-f75-max-rgb.md` for the protocol bytes and citations.

## rules

- **never write to the board's flash.** the persistent "user lighting" command (`04 23`) and anything that saves a mode or profile are off limits. only the real-time stream (`04 20`) and the plain mode commands.
- **never flash firmware.** no isp tools, no bootloader, no dumps. this is the only way to brick the board and it is not in scope.
- **nothing typed leaves the machine.** the key tap is a keylogger in mechanism. no network at runtime, no keystrokes written to disk. a source keeps in memory only what it needs for the current frame.
- **one process owns the board.** the command interface opens exclusively; a second program gets `open failed` until the first exits.
- **f3 and right alt misbehave in the stream (2026-09-26).** f3 is overridden red by the firmware whatever we send. right alt ignores its documented index 95; `scripts/find_led.py` sweeps for the real one.
- **wired only.** the 2.4g dongle carries whole-board colour, not per-key.
- **cap at 30 fps.** faster has dropped keystrokes on other boards (openrgb #2513).
- **an interrupted frame means resend the start packet**, never carry on mid-frame.
- **restore on exit is free.** when frames stop, the firmware fades the last frame out and takes the board back within about a minute. a source that wants to hold a static image resends it at a low rate. a source that quits just stops sending. never fight the firmware for the board.
- **never send punkster81's "unlock" packet.** it is a clock write (`00 01 5a YY MM DD …`), not an unlock. the stream needs no handshake. `scripts/f75_probe.py rtc` fixes the clock if something did.
- copy lowercase, product-grade tone. one compact control for "which source", not a wall of toggles.

## layout

80 keys, 15 columns by 6 rows with gaps. the led index for each key is in `docs/handoff/f75max-led-map.json` once the map sweep has been run against the real board; until then the vendor layout file's `light_index` values in the research note are the best guess.
