# aula f75 max — can we play video on it?

## verdict

possible with work, wired only. nothing shipped today drives the F75 Max's per-key LEDs from a computer (no OpenRGB controller [20][22], no SignalRGB plugin [27], no macOS tool [8][9]), but the board belongs to a Sonix 0c45:800a firmware family shared with the AULA/Epomaker F108 Pro and F98 Pro, and that family has a reverse-engineered real-time per-key stream (`04 20`) that runs at ~30 fps on the F108 Pro from Windows [14][15][19]. the official F75 Max driver exposes a "Real-time Lighting" mode [1], the F75 Max LED index map is sitting in the driver's layout file and lines up with the F108 Pro map [1][14], and the wired 0xff13 feature-report channel is already proven from macOS via IOKit for mode commands [8]. what's missing is anyone running that stream on an actual F75 Max. budget a few evenings of hidapi/IOKit work and one unknown (an unlock handshake), not a fresh reverse-engineering project. wireless per-key is out [7][17]; the 128x128 TFT is a documented zero-RE fallback for uploaded clips, not live streaming [6].

## what the keyboard exposes

- two boards share the "AULA F75" name. the non-Max F75 is a Sinowealth 8051 board at 258a:010c with a 520-byte feature-report protocol [24][32]. the F75 Max is a different platform: wired 0c45:800a (Sonix/Microdia VID), 2.4G dongle 05ac:024f [1][8][13]. everything below is about the Max unless stated.
- MCU is reported as Sonix SN32F2xx (Sonix ISP flasher, board id HFD80CP100 also seen on Ajazz AK820 Pro) [13]; no firmware dump confirms it, and SonixQMK has no aula board, so treat as medium confidence [38].
- wired HID topology: interface 0 keyboard, 1 media, 2 vendor usage page 0xff68 (4097-byte output reports, 65-byte input — TFT bulk channel), 3 vendor usage page 0xff13 (65-byte feature/input/output — command channel) [4][8][39]. 2.4G dongle: 32-byte interrupt reports on usage pages 0xff59/0xff60 [4][8].
- official software: Windows-only "AULA F75 Max Driver" v1.0.0.5 (DeviceDriver.exe + config.xml + layouts/rgb-keyboard.xml), hosted by Epomaker/AulaGear [1][2][3]. no macOS build, no SDK, not listed in AULA HUB [2][40]. it locks the HID interface while running [14][42].
- config.xml: product "AULA F75Max", cmd_delaytime=35 ms, firmware version 106; rgb-keyboard.xml: 80 keys, light_index == key_index, 15x6 grid; menu flags user_light=1 custom_light=1 music=1 screen=1 [1].
- per-key modes exist in the vendor UI: "User Lighting", "Real-time Lighting", "Music Rhythm", "Custom Light" [1]. the vendor strings also say "keyboard settings are not supported in Bluetooth mode for now" [1][7].
- wired vs wireless: the dongle only exposes 32-byte pipes; the vendor binary classifies interfaces by report length and never assigns a bulk handle to a 32-byte interface, so TFT upload is a no-op over 2.4G [7]. every published per-key path is wired interface 3 [14][15][19]. NollieL (SignalRGB plugin author): "some keyboards with very low 2.4G bandwidth do not have real-time RGB capability" [17]. wireless carries whole-board mode/colour/brightness/speed/direction, battery, game mode only [7][8].

## openrgb status

- F75 Max: not supported. issue #5326 "[New Device] AULA F75 Max Keyboard" open since 2025-12-08, no labels, no linked MR, with three pcapng captures (green/blue/red) from the Windows app [20]. no code for 0c45:800a in master; MR search for "AULA" returns only Sinowealth work [22]. issues #5253 (F108Pro) and #4595 (F98 Pro) report the same 0c45:800a and are also open [21].
- best lead: hcode10's out-of-tree fork adds Controllers/AulaF108Pro/ for 0c45:800a on interface 3 / 0xff13 with a Direct per-LED mode (104 LEDs), "converted from SignalRGB JavaScript code", keepalive re-sending the start packet every 2 s [19]. not merged.
- non-Max F75 (258a:010c): one researcher found a merged Sinowealth Keyboard10c controller in master (MR !3062, Off + Direct modes, model_id 0xCD = "AULA F75") [23][24]; two others reported issue #4232 as still open/unimplemented [26], and the merge date was given as both 2025-11-28 and 2026-04-15 [23]. the controller source exists in master [24], so treat it as supported. on macOS detection is broken in master; MR !3412 (open since 2026-07-23) fixes a hard-coded 3-collection check [25]. irrelevant to the Max but easy to confuse.

## signalrgb status

- no official plugin: the public signal-plugins repo has no 0x0c45/0x800a match and no AULA/Epomaker folder [27]. SignalRGB is Windows-only, so it is not a macOS route regardless [30].
- SignalRGB tracker: #604/#611 are F75 (non-Max) captures [28]; #772 "Adding Aula F108 Pro" (closed 2026-06-03) has a USBPcap of the official app over the same 05ac:024f dongle switching "User Lighting" — the best public lead for per-key over 2.4G, but the thread and attachments need a GitLab login [29].
- community: NollieL's "Aula F98Pro.js" targets 0x0c45/0x800a, Validate() on interface 3, usage 0x0001, usage page 0xff13; it is the origin of the per-key stream protocol below [15]. an F108 Pro owner reports it lights the board with some LEDs mapped wrong [16]. "Aula F75 Max.js" (someguy2312) is an AI-edited copy of it, comment says "verify these IDs match your F75 Max", unverified on hardware [18].
- NollieL's "Aula & Mchose Series.js" covers the non-Max F75 (258a:010c, one 520-byte report per frame) and will not match the Max [33].

## reverse-engineering status

repos (all wired protocol on 0xff13 unless noted):
- VitalyArt/Aula-F75-Max-Driver — Swift, macOS (IOKit) + Linux + Android, MIT. mode/brightness/speed/direction/colour, battery, clock sync, 128x128 image/GIF upload. no per-key. proves IOHIDDeviceSetReport(kIOHIDReportTypeFeature, id 0, 64 B) + GetReport on 0xff13 from macOS; needs Input Monitoring [8].
- mastercoder26/Aula-F75-Max-OSX — Objective-C menu-bar mirror of RoseWaveStudio's (now 404) app; same capability set, no per-key [9].
- Ghost-CR/F75_Initializer (fork of Simon-Martens) — Python transports for macOS IOKit/Windows/Linux, PROTOCOL_REFERENCE.md, verified pcapng captures, RTC sync, TFT upload, pcap replay tooling [4][5][42].
- schiz0x00/keyboard-screen — TFT protocol doc plus Ghidra decompile of DeviceDriver.exe (wireless-re.md) [6][7].
- Antik79/Aula-F75-Max-Web — WebHID port (Chromium), constants file confirms usage pages and lengths [10].
- parsiya/f108-pro (Go) and Punkster81/AULA-F108-Driver (Python, Windows DeviceIoControl) — same 0c45:800a family, F108 Pro hardware; these are where per-key is implemented [11][12][14].
- not-nullptr/openajazz (Rust) — lists "AULA F75 Max (RGB and time sync)" alongside AJAZZ AK820/AK35i, same 04 18 -> payload -> 04 02 pattern [31].

what's known of the protocol:
- framing: 64-byte feature reports, no report ID (Windows sends 65 with leading 0x00); `04 18` begin -> mode-specific select -> payload -> `04 02` apply -> `04 f0` finish; ~35-40 ms between steps; readback-marked commands need a GET_FEATURE (byte[3]=0x01 ack) or later commands are silently ignored; many payloads end with `aa 55` [4][5][11][12].
- whole-board RGB (verified on F75 Max): `04 13` then `MM RR GG BB 00 00 00 00 CC BR SP DI 00 00 aa 55`; 20 firmware modes 0x00-0x13 [5][8].
- per-key persistent "User Lighting" (F108 Pro, flash write, slow): `04 23` byte[8]=0x09, then a 576-byte buffer of [light_index,R,G,B] x144 with trailer, `04 02`, `04 f0` [12][14].
- per-key real-time stream (F108 Pro, ~30 fps): NollieL/hcode10 version: `04 20 00 00 00 00 00 00 08` + get_report, then 64-byte packets of 16 [idx,R,G,B] quads (7 packets for 97-104 LEDs), one zero packet, `04 02` + get_report; hcode10 re-sends the start every 2 s as keepalive [15][19]. Punkster81 additionally does a one-time handshake first: `04 18` (+get), `04 28` byte[8]=01 (+get), unlock packet `00 01 5a 1a 03 09 00 01 02 00 01 ... aa 55` (+get), `04 02` (+get), 0.2 s sleep; then 35 ms per frame with data packets sent back-to-back [14]. researchers disagree on whether the unlock is required; the F75 Max's `04 20` bytes have never been captured [4][20].
- LED index map: Punkster81's confirmed F108 Pro map (Esc 0x01, F1-F12 0x02-0x0d, ` 0x13, 1-0 0x14-0x1d, Backspace 0x67, Tab 0x25, Enter 0x55, Space 0x5e, Del 0x77, PgUp 0x76, PgDn 0x79, End 0x78, Up 0x65 ...) matches the F75 Max rgb-keyboard.xml light_index values decimal-for-hex (Backspace 103, Enter 85, Space 94, Del 119, PgUp 118, PgDn 121, End 120, Up 101, Left 99, Down 100, Right 102, Fn 96) [1][14]. two researchers called the map unknown; it is unknown only in the sense of untested — the layout file gives all 80 indices.
- TFT (wired only): `04 18`, `04 72` (slot at byte 2, chunk count LE u16 at 8-9), 4096-byte output reports on 0xff68 each acked by 128 bytes, `04 02` commit; payload = 256-byte header (frame count, one delay byte per frame in ~2 ms units) + frames x 128x128x2 RGB565 LE; max 255 frames; vendor paces ~65 ms/chunk; `04 02` on an incomplete stream corrupts firmware state (replug to recover) [6][10].
- wireless 32-byte packet (dongle, 0xff60): `05 10 00 MM R G B ... CC BR SP DI 00 00 aa 55 ...`, byte-sum checksum at 31; `0f` commit; VitalyArt/RoseWave have R/B swapped per the decompile [7][8].

## how video-on-keyboard pipelines work

- shape is the same everywhere: decode -> resize/area-average to the key grid -> pack one frame -> one SDK call or HID write per frame, paced to source fps. AULA F3261 (258a:0049): python hidapi + OpenCV, hand-coded key rectangles, one 382-byte feature report per frame [34]. Corsair iCUE: pl_mpeg + point-sample per LED + CorsairSetLedsColorsAsync per frame, Windows only [35]. Logitech: cv2.resize to 21x6 INTER_AREA + LogiLedSetLightingFromBitmap, Windows only [36]. precompute variant: pack frames offline to a binary, stream at ~31 fps [41].
- nobody publishes measured fps; they run at source rate (~30) [34][35][36]. OpenRGB issue #2513: a Corsair K70 in Direct mode at 60 fps dropped keystrokes, fine at 1 fps — keep to ~30 [37].
- F75 Max frame cost: 80 keys x 4 B = 320 B = 5 data packets + 1 zero packet + 2 command/ack round trips, all 64-byte feature reports (control transfers) on interface 3. Punkster81 sustains 35 ms/frame for 104 keys (7 packets) on the F108 Pro [14]; firmware ceiling on the Max is unmeasured.
- on macOS: IOHIDManager on interface 3 (usage page 0xff13), IOHIDDeviceSetReport feature id 0 + IOHIDDeviceGetReport for acks [8]; or hidapi with the same calls. Input Monitoring prompt expected [8][9].

## recommended path

1. wired USB-C, no vendor app running. enumerate with `hidapi` / IOKit and confirm interface 3 shows usage page 0xff13, usage 0x0001 [8][15]. reuse Ghost-CR's macOS transport or VitalyArt's Swift HID layer as the starting point [8][42].
2. sanity check the channel with the known-good whole-board sequence (`04 18` -> `04 13` -> mode payload -> `04 02` -> `04 f0`, 40 ms gaps) [5][8]. if that works, the transport is right.
3. port Punkster81's `04 20` stream (handshake + per-frame loop) to macOS; try it first without the unlock packet (NollieL/hcode10 form), then with [14][15][19]. send a single lit key at index 0x01 (Esc), then sweep 0x01..0x7b to confirm the rgb-keyboard.xml map [1][14].
4. if nothing lights: capture the official Windows driver's "Real-time Lighting" and "User Lighting" tabs with Wireshark + USBPcap on a Windows box/VM, diff against the F108 Pro sequence, and replay the pcapng with Ghost-CR's replay tooling [1][4][20][42]. OpenRGB #5326 already has three colour captures to cross-check framing [20].
5. build the player: ffmpeg/OpenCV decode -> area-average onto the 15x6 grid using the layout file's positions -> pack [idx,R,G,B] -> 5 packets + zero + `04 02` per frame at 30 fps, keepalive start packet if the board drops out [14][19][34].
6. once stable, upstream: OpenRGB controller for 0c45:800a with a Direct mode (hcode10's fork is a template; add an F75 Max layout keyed on the 80-index map) [19][20].
7. fallback if per-key stays dead: pre-render the clip to <=255 frames of 128x128 RGB565 and upload to a TFT slot (~2040 chunks at ~65 ms each for a full clip, so minutes of upload before playback) [6][10].

## open questions

- has `04 20` ever been sent to an F75 Max? verified only on F98 Pro/F108 Pro [14][15][16]. the unlock packet and the 2 s keepalive timeout are both uncharacterised on the Max [14][19].
- firmware fps ceiling and whether the 35 ms vendor pacing can be dropped between data packets on macOS [1][14].
- does the dongle's 0xff59 usage page carry the 64-byte command set (which would enable wireless streaming)? only 32-byte 0xff60 traffic is documented; SignalRGB #772's dongle capture might answer it but is login-gated [8][29].
- does the official app's "Real-time Lighting" use `04 20` with the same bytes, and what does "Music Rhythm" send? unknown; no capture exists [1][4].
- is the MCU really SN32F2xx and reflashable (SonixQMK)? unconfirmed; would need a dump [13][38].
- OpenRGB/SignalRGB comment threads for #5326, #2513, #772 could not be read (GitLab 401) — there may be unpublished progress [20][29][37].

## sources

1. https://cdn.shopify.com/s/files/1/0552/2803/9264/files/AULA_F75_Max_Gasket_Mechanical_Keyboard_Driver_1.0.0.5.zip
2. https://epomaker.com/blogs/software/epomaker-x-aula-f75-max-driver
3. https://aulagear.com/blogs/software/aula-f75-max
4. https://github.com/Ghost-CR/F75_Initializer/blob/main/PROTOCOL_REFERENCE.md
5. https://github.com/Ghost-CR/F75_Initializer/blob/main/docs/captures/RGB_MODE_REFERENCE.md
6. https://github.com/schiz0x00/keyboard-screen/blob/main/docs/protocol.md
7. https://github.com/schiz0x00/keyboard-screen/blob/main/docs/wireless-re.md
8. https://github.com/VitalyArt/Aula-F75-Max-Driver
9. https://github.com/mastercoder26/Aula-F75-Max-OSX
10. https://github.com/Antik79/Aula-F75-Max-Web/blob/HEAD/src/lib/protocol/constants.ts
11. https://github.com/parsiya/f108-pro
12. https://github.com/parsiya/f108-pro/blob/main/ai-docs/hid-protocol.md
13. https://github.com/parsiya/f108-pro/blob/main/ai-docs/device-info.md
14. https://github.com/Punkster81/AULA-F108-Driver/blob/main/aula_f108_pro_final.py
15. https://github.com/NollieL/SignalRgb_CN_Key/blob/main/Aula%20F98Pro.js
16. https://github.com/NollieL/SignalRgb_CN_Key/issues/30
17. https://github.com/NollieL/SignalRgb_CN_Key/issues/13
18. https://github.com/someguy2312/for-signalrgb-aula-f75-max/blob/main/Aula%20F75%20Max.js
19. https://github.com/hcode10/OpenRGB-With-AulaF108Pro-support/blob/master/Controllers/AulaF108Pro/AulaF108ProController.cpp
20. https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/5326
21. https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/5253
22. https://gitlab.com/CalcProgrammer1/OpenRGB/-/merge_requests?search=AULA&scope=all&state=all
23. https://gitlab.com/CalcProgrammer1/OpenRGB/-/merge_requests/3062
24. https://gitlab.com/CalcProgrammer1/OpenRGB/-/tree/master/Controllers/SinowealthController/SinowealthKeyboard10cController
25. https://gitlab.com/CalcProgrammer1/OpenRGB/-/merge_requests/3412
26. https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/4232
27. https://gitlab.com/signalrgb/signal-plugins/-/tree/master/Plugins
28. https://gitlab.com/signalrgb/signal-plugins/-/issues/604
29. https://gitlab.com/signalrgb/signal-plugins/-/work_items/772
30. https://www.signalrgb.com/
31. https://github.com/not-nullptr/openajazz
32. https://xevrion.dev/blogs/aula-f75-linux-reverse-engineering
33. https://github.com/NollieL/SignalRgb_CN_Key
34. https://github.com/LFARMAN/AULA-Apple/blob/HEAD/FinalNoIf.py
35. https://github.com/Aliremu/Keyboard-Bad-Apple/blob/HEAD/KeyboardBadApple.cpp
36. https://github.com/Kolya080808/Logitech-G-Hub-Keyboards---Bad-apple/blob/HEAD/script.py
37. https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/2513
38. https://github.com/SonixQMK/qmk_firmware
39. https://github.com/wsc92/malicious-keyboard-security-analysis
40. https://www.aulastar.com/aula-hub/
41. https://github.com/bad-apple-lab/Bad-Apple-4-Memory-RGB/blob/main/run.py
42. https://github.com/Simon-Martens/F75_Initializer
