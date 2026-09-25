# decision keys — handoff

written 2026-09-22 by fable, from a session with jass. read this, then `docs/research/aula-f75-max-rgb.md`. everything below is either verified on jass's machine, cited, or marked as a guess.

## the idea

the keyboard is a display for a decision model. as you type, the current sentence goes to a local decision model with a handful of typed questions; the answers land on the keys about 60 ms later. the model can point at a key but can never touch your words. nothing pops up, nothing rewrites, the board just knows.

it lives in this repo because the frame pipeline is the same as video-on-keyboard: a source produces an 80-key colour grid, the grid becomes `[idx, r, g, b]` quads, the quads go down the `04 20` real-time stream at ~30 fps. video and decisions are two sources for one player.

the name is open. jass has not picked one.

## why a decision model and not an llm

jev (typesafe ai, hosted) and laya (convai, open weights, apache-2.0) are "system one" models: state in, typed decisions out. three primitives — `choice` (pick from options), `score` (position on a rubric), `noul` (yes/no probability). they do not generate text. that is the point: it makes "the keyboard suggests" possible without "the keyboard corrects", which is the rule jass already enforces in andrew dictate (adr 0020).

laya is the one that ships here. it runs locally. jev is hosted and is only ever a labeler for fine-tuning (see "later").

## state of play, 2026-09-22

verified on jass's m4 (32 gb, macos 27, python 3.14, uv):

| thing | result |
|---|---|
| `laya-mlx` installs and loads | yes, 843 mb download, ~3 min first load (network), then cached |
| one `noul`, warm, p50 | 18.1 ms |
| four questions in one call | 61 ms |
| "parse the jason" → json not a person | 0.89, zero-shot |
| "jason is out today" → json | 0.08, zero-shot |
| "we should we should push" → stumble | 0.18 — missed, needs fine-tune |
| tanglish sentence → language | "english" at 0.05 confidence — useless; english checkpoint only |
| `hidapi` installed in the venv | yes |

## session 2026-09-26

- repo initialised (`git init`, five segmented commits, `commit.gpgsign=false` local because the global key needs a touch). rules in `AGENTS.md`.
- board enumerates over usb-c on this mac: interface 3 is usage page `0xff13`, interface 2 is `0xff68`, matching the research.
- **`04 20` is accepted.** `scripts/f75_probe.py stream` sends the start, five data packets, the zero packet and `04 02`, all as 65-byte feature reports through `hidapi` (leading `0x00` report id). every command gets a sane echo back. acks seen:
  - first run, no unlock: start `04 20 00 01 … 08`, apply `04 02 00 ff`
  - with punkster81's handshake: all four handshake acks `00 01`, start `00 01`, apply `00 00`
  - no unlock again after that: start `00 00`, apply `00 01`
  byte 3 of the ack is stateful, not a success flag. do not gate on it.
- frame cost: ~7 ms per full 80-key frame with no gaps between packets (`--packet-gap 0`), measured over 5 s at a 30 fps target (24.6 fps because the loop slept a fixed 33 ms on top). raw run with no sleep at all: 992 frames in 3 s, no errors from the board. whether the firmware renders every frame at that rate is unknown and irrelevant; the player caps at 30 fps and schedules by wall clock, not by sleep.
- **confirmed on the board.** jass filmed `stream --pattern rows` (IMG_5889): row 0 red, row 1 orange, row 2 yellow, row 3 green, row 4 blue, row 5 purple, esc and space white. every key in its expected row, including backspace, del, pgup, pgdn, end and the arrow cluster. the map in `docs/handoff/f75max-led-map.json` is confirmed. **the f75 max accepts the per-key stream from macos. the project's one unknown is closed.**
- **there is no unlock.** punkster81's "unlock" packet `00 01 5a 1a 03 09 00 01 02 …` is ghost-cr's rtc payload `00 01 5a YY MM DD HH mm SS …` with a fixed date. sending it set jass's board clock to 2026-03-09 00:01:02 (visible on the tft in the video). the stream works with no handshake at all. `scripts/f75_probe.py rtc` sets the clock back to local time with the verified cable sequence; run it after any experiment that touched `04 28`.
- **the board comes back on its own.** after the last stream stops, the firmware first fades the frame out (jass's second video, ~20 s after the last frame: nearly all keys dark, a few holding a fading leftover colour, right alt cyan) and then restores its own lighting mode by itself. jass's photo at board-clock 00:06:37, about a minute after the last frame, shows the full cyan static mode back with no replug. so: the timeout is somewhere between 20 s and 70 s of silence, the player does not need a clean exit command, and restore-on-exit is just "stop sending frames". to hold a static image, keep resending it at a low rate (1 fps is plenty; the firmware holds a frame until the next one).
- keepalive timeout (step 5): answered above. between 20 s and 70 s of no frames, then the firmware takes the board back. exact value not measured.

blocked on 2026-09-22: the f75 max was not connected to this mac (no `0c45:800a` on usb, no `05ac:024f` dongle). nobody has ever sent the `04 20` per-key stream to an f75 max. that is the project's one real unknown and it needs the board plugged in over usb-c.

staged (in `/tmp`, will not survive a reboot — recreate with the commands below):
- `/tmp/laya-bench/.venv` with `laya-mlx` and `hidapi`
- `/tmp/laya-bench/ref/{F75_Initializer,AULA-F108-Driver,Aula-F75-Max-Driver}` shallow clones
- the bench script is saved durably at `scripts/laya_bench.py`

## prior art (checked 2026-09-21)

nobody has built this. closest:
- **keystroke-llm** (Drix10, github, 3 stars): char-level transformer predicts the next key, kreo hive 75 lights the top five by confidence, over reverse-engineered hid on windows/linux. same form (model → per-key brightness, live), different content (next character, no sentence meaning). worth reading for its 10 hz keepalive daemon and its one-by-one led mapping method. https://github.com/Drix10/keystroke-llm
- **logitech patent us 12524076** "personal wellness keyboard using lighting and machine learning": ml sentiment → illumination profile. no product. irrelevant to an open-source toy; mention it in the readme.
- **jev board** (zahle khan on x): an ios keyboard extension where jev picks a widget above the keys. software, no leds. no overlap. https://x.com/zahlekhan/status/2100681083176226921
- jev community catalogs (~155 projects): drones, games, shell history, a swift sdk, jevlike-esp32. nothing drives lighting or reads live typing on hardware.
- laya: the mlx runtime's only demo is snake; `chrisns/laya-mac-serve` is a menu-bar pytorch server at ~40 ms. nothing with keys.
- f75 max per-key from macos: still unclaimed. `keylux-linux` is the non-max sinowealth f75 (`258a:010c`), a different board.
- x is only searchable via what's indexed; a video without a repo could exist. accepted.

## architecture

```
keystroke tap (cgeventtap, input monitoring)
  → sentence buffer (current sentence since last terminal punctuation / enter)
  → on word boundary: laya.predict(sentence, questions)       ~20–60 ms
  → mapper: answers → 80-key colour grid                      pure function
  → hid frame: 04 20 · 5 data packets · 1 zero packet · 04 02  ~35 ms
  → keepalive: resend 04 20 start every 2 s if the board drops out
```

- **runtime, v1:** python. `laya-mlx` is python-only (no swift, no coreml port exists). the keystroke tap can be python via pyobjc/quartz. one process, one permission (input monitoring covers both the tap and the hid driver per VitalyArt's notes).
- **runtime, later:** swift. would need a coreml or mlx-swift port of laya's modernbert-large + 2-layer decision head. nobody has done it; it would be a contribution to the jev-reproductions tracker on hugging face.
- **frame budget:** 80 keys × 4 b = 320 b = 5 packets + 1 zero + 2 acked commands, all 64-byte feature reports on interface 3. at the vendor's 35 ms pacing that is ~28 fps. typing needs far less; render on change, not on a clock, and let the keepalive hold the mode.
- **wired only.** the 2.4g dongle carries whole-board colour only. the research note has the citations.

## the first session (needs the board, wired, no vendor app)

recreate the scratch env:

```sh
mkdir -p /tmp/laya-bench/ref && cd /tmp/laya-bench
uv venv .venv && . .venv/bin/activate
uv pip install laya-mlx hidapi
cd ref
git clone --depth 1 https://github.com/Ghost-CR/F75_Initializer
git clone --depth 1 https://github.com/Punkster81/AULA-F108-Driver
git clone --depth 1 https://github.com/VitalyArt/Aula-F75-Max-Driver
```

then, in order, stopping at the first failure:

1. **enumerate.** `python -c 'import hid; [print(d) for d in hid.enumerate(0x0c45, 0x800a)]'`. expect four interfaces; interface 3 must show `usage_page=0xff13, usage=0x0001`. if the board is missing, check the cable is usb-c data, not the dongle.
2. **whole-board colour, the proven path.** `04 18` → `04 13` + `MM RR GG BB 00 00 00 00 CC BR SP DI 00 00 aa 55` → `04 02` → `04 f0`, 40 ms gaps, 64-byte feature reports, no report id. this is verified on the f75 max from macos by VitalyArt and Ghost-CR. if this works the transport is right. Ghost-CR's `aula_hacky/hid_macos.py` is the iokit transport; `hidapi` should also work.
3. **the unknown: `04 20`.** port `_handshake` and `_send_frame` from `ref/AULA-F108-Driver/aula_f108_pro_final.py` (lines ~94–112). light one key, esc = `0x01`, red. try first **without** the unlock packet (nollieL / hcode10 form: `04 20 00 00 00 00 00 00 08` + get_report, data packets, zero packet, `04 02` + get_report), then **with** Punkster81's handshake (`04 18`, `04 28 …01`, unlock `00 01 5a 1a 03 09 00 01 02 00 01 … aa 55`, `04 02`, 0.2 s). researchers disagree on whether the unlock is required; the f75 max has never been captured.
4. **map.** sweep `0x01..0x7b`, one key at a time, and confirm against `rgb-keyboard.xml`'s 80 `light_index` values (backspace 103, enter 85, space 94, del 119, pgup 118, pgdn 121, end 120, up 101, left 99, down 100, right 102, fn 96; esc 1, f1–f12 2–13, ` 19, 1–0 20–29, tab 37). write the confirmed map to `docs/handoff/f75max-led-map.json`.
5. **hold a frame.** stream a static frame for 60 s. note whether the board drops back to its own mode and after how long; that sets the keepalive interval (hcode10 uses 2 s).
6. **plug in laya.** `scripts/laya_bench.py` already asks four dictation-shaped questions; wire its answers to two keys (`?` and backspace) and type.

if step 3 stays dark both ways: wireshark + usbpcap on a windows vm with the official driver's "real-time lighting" tab, diff against the f108 pro sequence, replay with Ghost-CR's replay tooling. openrgb issue #5326 has three colour captures to cross-check framing.

## mappings, v1, in order

1. **the wash.** one `score` question drives the hue of the main block. probability drives brightness, so an unsure model is a dim keyboard. calibration rendered honestly. this is the demo shot.
2. **the keys that point.** `?` glows when "is this a question" crosses 0.5. backspace pulses when "did you restart mid-sentence". enter warms up when "is this ready to send". the model points; it never edits.
3. **f-row as twelve gauges.** twelve `noul`s, brightness = probability. candidates: mentions money · is a commitment · is a swear · is addressed to a person · is a question · is an apology · names a date · is hedging.
4. **video stays the base layer.** same player, second source.

pick questions by testing, not by taste: run ~20 candidate questions over jass's own sentences (the 488 dictations in `~/Library/Application Support/Andrew Dictate Dev/dictations.jsonl`, field `heard`, are a ready corpus — private, never leave the machine) and keep the ones whose zero-shot answers move. the json/jason one moves. the stumble one does not, yet.

## constraints and taste

- never rewrite. the model chooses colours, not words. this is the whole joke and the whole ethic.
- wired only, one permission (input monitoring), no vendor app running, no accounts, no network at runtime.
- copy lowercase; product-grade tone, one nonchalant nod at most, no meme barrage.
- controls stay quiet: one compact control for "which mapping", not a wall of toggles.
- never run above ~30 fps; a corsair k70 at 60 fps dropped keystrokes (openrgb #2513).
- `04 02` on an incomplete tft stream corrupts firmware state until replug. the per-key stream has no reported equivalent, but treat an interrupted frame as "resend the start packet", not "carry on".

## open questions

- does the f75 max accept `04 20` at all, and with or without the unlock? (step 3)
- keepalive timeout on the max? (step 5)
- firmware fps ceiling; can the 35 ms pacing between data packets be dropped on macos?
- is the sentence buffer per-app (reset on focus change) or global? guess: reset on focus change and on enter.
- what does the board show when nothing is being typed: the last decision, a video, or the firmware's own mode?
- does the multilingual laya checkpoint convert to mlx (the port only ships english)? tanglish needs it.

## later

- **fine-tune loop.** laya is near chance zero-shot on most questions; that is by design ("a fast base to specialise"). label jass's sentences with jev (hosted, ~$0.042 per million input tokens, output free, early access via console.typesafe.ai or vercel ai gateway), review the labels, fine-tune on the kaggle 2×t4 notebook in `NandhaKishorM/laya` (~4–5 h), refit calibration temperatures per question type, ship the checkpoint local. jev is never in the runtime path.
- **swift port** of laya for a proper menu-bar app, and to share the model with andrew dictate (contextual dictionary, language fallback, question-mark detection — same questions, same checkpoint).
- **upstream** an openrgb controller for `0c45:800a` direct mode with the f75 max 80-key layout, from hcode10's fork as a template.

## sources

- research note: `docs/research/aula-f75-max-rgb.md` (42 citations; the protocol bytes above come from there)
- laya: https://huggingface.co/convaiinnovations/laya · https://github.com/NandhaKishorM/laya · mlx port https://github.com/mizorewww/laya-mlx (pypi `laya-mlx`, weights `aac6fef/laya-mlx`)
- jev: https://typesafe.ai/blog/introducing-system-one-models-and-jev · limits and schemas https://dev.to/valyuai/how-to-use-jev-a-practical-guide-to-typesafes-system-one-model-g5e
- prior art: https://github.com/Drix10/keystroke-llm · https://x.com/zahlekhan/status/2100681083176226921 · https://github.com/yibie/awesome-jev · https://huggingface.co/spaces/multimodalart/jev-reproductions-tracker

## the screen, checked 2026-09-26

jass asked whether snake can use the 128x128 screen while it runs. what the references say:

- the screen is not a live display. the only known path uploads an image or gif into a numbered slot: `04 18`, `04 72 slot chunks`, 4096-byte chunks on interface 2 each waited for an ack, `04 02` (ghost-cr protocol reference, vitalyart `AulaDevice.swift uploadDisplayStream`).
- one still picture is a 256-byte header plus 32 KB of rgb565, so 9 chunks. at the vendor's ~65 ms per chunk that is about 0.6 s per picture. up to 255 frames per upload, each frame another 8 chunks.
- slots are stored on the board: vitalyart's factory reset starts by "clearing display memory". every upload is almost certainly a flash write. the per-key stream is ram-only; this is not.
- sending `04 02` on an incomplete upload corrupts firmware state until replug, so an upload must never be cut off by esc or ctrl-c.
- so: a live score or live game view on the screen is out. what fits is one upload at a moment that matters, such as a title card at launch or a score card at game over, and only if jass accepts the flash writes. not built; waiting on that decision.
