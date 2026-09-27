// the soundtrack for the life demo, written from what the board did.
//
//   node score.mjs life-events.json out.wav
//
// every birth on the board is a bell, pitched by where the key sits: left to right climbs a
// c major pentatonic, each row up adds two steps, so the f-row is the top of the range and
// the bottom row the bottom. every death is a muted pluck an octave down. a mass death is a
// low thud. the drums only play while the board is running, and the tempo is the board's:
// 75 bpm, so one generation is one sixteenth. the grid is anchored on the moment the whole
// board lit up (28.3 s), which is the drop. events snap to the nearest 32nd, so every note
// lands within 50 ms of its key.

import './audio-globals.mjs';
import { OfflineAudioContext } from 'node-web-audio-api';
import * as SD from 'superdough';
import { readFileSync, writeFileSync } from 'node:fs';

const [, , IN = 'life-events.json', OUT = 'life-score.wav'] = process.argv;
const { events, keys } = JSON.parse(readFileSync(IN, 'utf8'));

const SR = 48000;
const LENGTH = 56;                       // the cut is 54 s; the rest is reverb tail, trimmed at mux
const CPS = 75 / 240;
const S16 = 0.2, BEAT = 0.8, BAR = 3.2;
const BAR0 = 28.3 - 9 * BAR;             // bar 9 starts on the drop
const barAt = (n) => BAR0 + n * BAR;
const snap = (t) => Math.round((t - BAR0) / 0.1) * 0.1 + BAR0;

// ── harmony ───────────────────────────────────────────────────────────────────
const A = { root: 45, pad: [57, 60, 64, 67] };   // am7
const F = { root: 41, pad: [53, 57, 60, 64] };   // fmaj7
const C = { root: 48, pad: [55, 60, 62, 64] };   // cadd9
const G = { root: 43, pad: [55, 59, 62, 67] };   // g
//            0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16
const PROG = [A, A, F, C, G, A, F, C, G, A, F, C, G, A, F, G, A];
const chordAt = (t) => PROG[Math.max(0, Math.min(PROG.length - 1, Math.floor((t - BAR0) / BAR)))];

// sections, by bar: intro (drawing, paused), run (the clock starts), drop, breakdown, final
const section = (n) => (n <= 4 ? 'intro' : n <= 8 ? 'run' : n <= 11 ? 'drop' : n <= 13 ? 'break' : 'final');

const PENT = [0, 2, 4, 7, 9];
function pitch(name) {
  const k = keys[name];
  const d = Math.round(k.x * 6) + (5 - k.row) * 2;
  return 48 + 12 * Math.floor(d / 5) + PENT[d % 5];
}

// ── voices ────────────────────────────────────────────────────────────────────
const voices = [];
const play = (t, dur, v) => { if (t >= 0 && t < LENGTH) voices.push([t, dur, v]); };

const bell = (t, note, pan, gain) => play(t, 0.9, {
  s: 'sine', note, fmi: 1.1, fmh: 2, attack: 0.002, decay: 0.7, sustain: 0, release: 0.3,
  gain, pan, orbit: 1, room: 0.35, size: 0.6, delay: 0.22, delaytime: 0.6, delayfeedback: 0.3,
});
const pluck = (t, note, pan, gain) => play(t, 0.16, {
  s: 'triangle', note, attack: 0.002, decay: 0.12, sustain: 0, release: 0.04, cutoff: 900,
  gain, pan, orbit: 3,
});
const thud = (t, gain) => play(t, 0.5, {
  s: 'sine', note: 33, penv: 12, pdecay: 0.08, attack: 0.001, decay: 0.45, sustain: 0, gain, orbit: 4,
});
const kick = (t, gain = 0.9) => play(t, 0.4, {
  s: 'sine', note: 31, penv: 24, pdecay: 0.05, attack: 0.001, decay: 0.34, sustain: 0, gain, orbit: 4,
});
const hat = (t, gain) => play(t, 0.05, {
  s: 'white', attack: 0.001, decay: 0.028, sustain: 0, hcutoff: 8000, gain, orbit: 4,
});
const openhat = (t, gain) => play(t, 0.3, {
  s: 'white', attack: 0.001, decay: 0.22, sustain: 0, hcutoff: 7000, gain, orbit: 4,
});
const snare = (t, gain = 0.5) => {
  play(t, 0.2, { s: 'white', attack: 0.001, decay: 0.15, sustain: 0, hcutoff: 1600, gain, orbit: 5, room: 0.25, size: 0.4 });
  play(t, 0.1, { s: 'triangle', note: 50, penv: 7, pdecay: 0.03, attack: 0.001, decay: 0.07, sustain: 0, gain: gain * 0.6, orbit: 5 });
};
const bass = (t, dur, note, gain = 0.38) => play(t, dur, {
  s: 'sawtooth', note, attack: 0.005, decay: 0.2, sustain: 0.45, release: 0.08, cutoff: 520, resonance: 4,
  gain, orbit: 6,
});
// the pad: each chord tone as a slightly detuned saw and triangle pair, dark and pushed back
const pad = (t, dur, chord, gain) => chord.pad.forEach((note, i) => {
  const pan = 0.3 + 0.4 * (i / 3);
  play(t, dur, { s: 'sawtooth', note: note - 0.07, attack: 0.9, decay: 0.4, sustain: 0.8, release: 1.4, cutoff: 850,
    hcutoff: 160, gain, pan, orbit: 2, room: 0.6, size: 0.85 });
  play(t, dur, { s: 'triangle', note: note + 0.07, attack: 0.9, decay: 0.4, sustain: 0.8, release: 1.4,
    gain: gain * 1.2, pan: 1 - pan, orbit: 2, room: 0.6, size: 0.85 });
});
const stab = (t, chord, gain) => chord.pad.forEach((note, i) => play(t, 0.4, {
  s: 'sawtooth', note: note + 12, attack: 0.004, decay: 0.3, sustain: 0, release: 0.5, cutoff: 2400,
  gain, pan: 0.2 + 0.6 * (i / 3), orbit: 2, room: 0.6, size: 0.85,
}));
const crash = (t, gain) => play(t, 2.6, {
  s: 'white', attack: 0.001, decay: 2.4, sustain: 0, hcutoff: 4500, gain, orbit: 7, room: 0.45, size: 0.8,
});
const riser = (t, dur, gain) => play(t, dur, {
  s: 'pink', attack: dur * 0.95, decay: 0.01, sustain: 1, release: 0.04, cutoff: 600, lpenv: 5,
  lpattack: dur, lpdecay: 0.01, lpsustain: 1, hcutoff: 300, gain, orbit: 7, room: 0.45, size: 0.8,
});

// ── the arrangement ───────────────────────────────────────────────────────────
for (let n = 0; n < PROG.length; n++) {
  const t0 = barAt(n), ch = PROG[n], sec = section(n);
  const padGain = { intro: 0.035, run: 0.035, drop: 0.045, break: 0.045, final: 0.045 }[sec];
  pad(Math.max(0, t0), BAR + (t0 < 0 ? t0 : 0), ch, padGain);

  if (sec === 'intro') continue;                          // drawing: the taps are the whole melody

  // the generation clock: a tick on every sixteenth while the board runs
  const busy = sec === 'drop' || sec === 'final';
  for (let s = 0; s < 16; s++) {
    const t = t0 + s * S16;
    if (n === 16 && s >= 8) break;                        // last bar: the clock stops, the chord rings
    const acc = s % 4 === 0 ? 1 : s % 2 === 0 ? 0.6 : 0.4;
    hat(t, (busy ? 0.22 : 0.14) * acc);
  }

  if (sec === 'run') {
    bass(t0, 1.4, ch.root);
    bass(t0 + 2.5 * BEAT, 0.35, ch.root + 7, 0.3);
    if (n >= 7) { snare(t0 + BEAT, 0.28); snare(t0 + 3 * BEAT, 0.28); }
    if (n === 8) {                                         // the build into the drop
      riser(t0 + BEAT, 3 * BEAT, 0.3);
      for (let s = 8; s < 16; s++) snare(t0 + s * S16, 0.12 + 0.03 * (s - 8));
      for (let s = 0; s < 8; s++) snare(t0 + 3 * BEAT + s * 0.1, 0.26 + 0.03 * s);
    }
  }

  if (busy) {
    const steps = n === 16 ? 8 : 16;
    for (const s of [0, 7, 10]) if (s < steps) kick(t0 + s * S16);
    for (const s of [4, 12]) if (s < steps) snare(t0 + s * S16);
    if (steps === 16) openhat(t0 + 14 * S16, 0.12);
    // bass in eighths, root with an octave lift on the offbeats of beat 3
    const line = [0, 0, 0, 0, 0, 12, 0, 7];
    for (let e = 0; e < steps / 2; e++) bass(t0 + e * 2 * S16, 0.32, ch.root + line[e], e % 2 ? 0.28 : 0.38);
  }

  if (sec === 'break') {
    bass(t0, BAR * 0.9, ch.root, 0.3);
    if (n === 13) {                                        // pick the energy back up into the final bars
      kick(t0, 0.7);
      for (let s = 12; s < 16; s++) snare(t0 + s * S16, 0.15 + 0.05 * (s - 12));
      riser(t0 + 2 * BEAT, 2 * BEAT, 0.2);
    }
  }
}

// the drop: the whole board lights up at once
const DROP = barAt(9);
kick(DROP, 1.0); thud(DROP, 0.8); crash(DROP, 0.3); stab(DROP, A, 0.08);

// ── the board itself ──────────────────────────────────────────────────────────
const slots = new Map();
for (const e of events) {
  const t = snap(e.t);
  const key = t.toFixed(2);
  if (!slots.has(key)) slots.set(key, { t, births: [], deaths: [] });
  slots.get(key)[e.kind === 'birth' ? 'births' : 'deaths'].push(e.key);
}
let nb = 0, nd = 0;
for (const { t, births, deaths } of slots.values()) {
  if (births.length) {
    // distinct pitches, spread across the range when a whole board is dealt at once
    const ps = [...new Map(births.map((k) => [pitch(k), k])).entries()].sort((a, b) => a[0] - b[0]);
    const cap = 5;
    const pick = ps.length <= cap ? ps : Array.from({ length: cap }, (_, i) => ps[Math.round(i * (ps.length - 1) / (cap - 1))]);
    const g = 0.2 / Math.sqrt(pick.length);
    for (const [note, k] of pick) bell(t, note, 0.12 + 0.76 * keys[k].x, g);
    nb += pick.length;
    if (births.length >= 12 && Math.abs(t - DROP) > 0.2) stab(t, chordAt(t), 0.06);   // a deal
  }
  if (deaths.length) {
    const ps = [...new Set(deaths)].slice(0, 3);
    for (const k of ps) pluck(t, pitch(k) - 12, 0.12 + 0.76 * keys[k].x, 0.3 / Math.sqrt(ps.length));
    nd += ps.length;
    if (deaths.length >= 8) thud(t, 0.45);
  }
}

// ── render ────────────────────────────────────────────────────────────────────
const ctx = new OfflineAudioContext(2, Math.ceil(SR * LENGTH), SR);
SD.setAudioContext(ctx);
SD.registerSynthSounds();
const SOLO = process.env.SOLO ? process.env.SOLO.split(',') : null;   // e.g. SOLO=sawtooth,sine for a quick layer check
if (SOLO) voices.splice(0, voices.length, ...voices.filter(([, , v]) => SOLO.includes(v.s)));
voices.sort((a, b) => a[0] - b[0]);
const res = await Promise.allSettled(voices.map(([t, dur, v]) => SD.superdough(v, t, dur, CPS, t * CPS)));
const bad = res.filter((r) => r.status === 'rejected');
if (bad.length) console.warn(`${bad.length}/${voices.length} voices failed, first: ${String(bad[0].reason).slice(0, 160)}`);
const buf = await ctx.startRendering();

const L = buf.getChannelData(0), R = buf.getChannelData(1);
let peak = 0;
for (let i = 0; i < L.length; i++) peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
const gain = peak > 0 ? 0.89 / peak : 1;
const out = Buffer.alloc(44 + L.length * 4);
out.write('RIFF', 0); out.writeUInt32LE(36 + L.length * 4, 4); out.write('WAVE', 8); out.write('fmt ', 12);
out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20); out.writeUInt16LE(2, 22); out.writeUInt32LE(SR, 24);
out.writeUInt32LE(SR * 4, 28); out.writeUInt16LE(4, 32); out.writeUInt16LE(16, 34); out.write('data', 36);
out.writeUInt32LE(L.length * 4, 40);
for (let i = 0, o = 44; i < L.length; i++, o += 4) {
  out.writeInt16LE(Math.round(Math.max(-1, Math.min(1, L[i] * gain)) * 32767), o);
  out.writeInt16LE(Math.round(Math.max(-1, Math.min(1, R[i] * gain)) * 32767), o + 2);
}
writeFileSync(OUT, out);
console.log(`wrote ${OUT}: ${voices.length} voices (${nb} bells, ${nd} plucks), raw peak ${peak.toFixed(2)}`);
