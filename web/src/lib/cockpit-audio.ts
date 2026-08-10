/** Shared Web Audio bus for cockpit SFX + SpaceFlyby ambience. Mute sets master gain to 0. */

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let engineOsc: OscillatorNode | null = null;
let engineGain: GainNode | null = null;
let bgmNodes: { osc: OscillatorNode; gain: GainNode }[] = [];
let unlocked = false;
let lastFlybySfx = 0;

function ensureCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (ctx) return ctx;
  const Ctx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return null;
  ctx = new Ctx();
  master = ctx.createGain();
  master.gain.value = 1;
  master.connect(ctx.destination);
  return ctx;
}

export function isCockpitAudioUnlocked() {
  return unlocked;
}

export function unlockCockpitAudio() {
  const c = ensureCtx();
  if (!c || unlocked) return;
  unlocked = true;
  void c.resume();
  startEngineHum();
  startSpaceBgm();
}

export function setCockpitMuted(muted: boolean) {
  if (master) master.gain.value = muted ? 0 : 1;
  mutedFlag = muted;
  for (const fn of muteListeners) fn();
}

let mutedFlag = false;
const muteListeners = new Set<() => void>();

export function getCockpitMuted() {
  return mutedFlag;
}

export function subscribeCockpitMuted(listener: () => void) {
  muteListeners.add(listener);
  return () => {
    muteListeners.delete(listener);
  };
}

export function playClickSfx(kind: "soft" | "clack" | "chirp" | "thud") {
  const c = ensureCtx();
  if (!c || !master || !unlocked || master.gain.value === 0) return;
  void c.resume();
  const o = c.createOscillator();
  const g = c.createGain();
  o.connect(g);
  g.connect(master);
  const now = c.currentTime;
  const map = {
    soft: { f: 520, d: 0.06, t: "sine" as OscillatorType },
    clack: { f: 180, d: 0.08, t: "triangle" as OscillatorType },
    chirp: { f: 880, d: 0.05, t: "sine" as OscillatorType },
    thud: { f: 90, d: 0.12, t: "square" as OscillatorType },
  }[kind];
  o.type = map.t;
  o.frequency.setValueAtTime(map.f, now);
  g.gain.setValueAtTime(0.0001, now);
  g.gain.exponentialRampToValueAtTime(0.12, now + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, now + map.d);
  o.start(now);
  o.stop(now + map.d + 0.02);
}

function startEngineHum() {
  const c = ensureCtx();
  if (!c || !master || engineOsc) return;
  engineOsc = c.createOscillator();
  engineGain = c.createGain();
  engineOsc.type = "sawtooth";
  engineOsc.frequency.value = 42;
  engineGain.gain.value = 0.018;
  engineOsc.connect(engineGain);
  engineGain.connect(master);
  engineOsc.start();
}

/** Soft space pad BGM (procedural). Respects master mute. */
function startSpaceBgm() {
  const c = ensureCtx();
  if (!c || !master || bgmNodes.length) return;
  const freqs = [55, 82.5, 110, 164.8];
  for (const f of freqs) {
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = "sine";
    osc.frequency.value = f;
    g.gain.value = 0.014;
    osc.connect(g);
    g.connect(master);
    osc.start();
    bgmNodes.push({ osc, gain: g });
  }
}

export function playMeteorWhoosh() {
  playFlybyPass("meteor");
}

/** Star / planet / meteor pass-by cue (louder, earlier). */
export function playFlybyPass(kind: "meteor" | "star" | "planet" = "star") {
  const c = ensureCtx();
  if (!c || !master || !unlocked || master.gain.value === 0) return;
  const t = performance.now();
  if (t - lastFlybySfx < 420) return;
  lastFlybySfx = t;
  void c.resume();
  const now = c.currentTime;
  const dur = kind === "meteor" ? 0.42 : 0.55;
  const peak = kind === "meteor" ? 0.16 : kind === "planet" ? 0.11 : 0.13;
  const noise = c.createBufferSource();
  const buf = c.createBuffer(1, Math.floor(c.sampleRate * dur), c.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
  noise.buffer = buf;
  const filt = c.createBiquadFilter();
  filt.type = "bandpass";
  const f0 = kind === "star" ? 1400 : kind === "planet" ? 480 : 900;
  filt.frequency.setValueAtTime(f0, now);
  filt.frequency.exponentialRampToValueAtTime(120, now + dur * 0.9);
  filt.Q.value = 0.7;
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, now);
  g.gain.exponentialRampToValueAtTime(peak, now + 0.03);
  g.gain.exponentialRampToValueAtTime(0.0001, now + dur);
  noise.connect(filt);
  filt.connect(g);
  g.connect(master);
  noise.start(now);
  noise.stop(now + dur + 0.02);
}

export function playNebulaBlip() {
  const c = ensureCtx();
  if (!c || !master || !unlocked || master.gain.value === 0) return;
  void c.resume();
  const now = c.currentTime;
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = "sine";
  o.frequency.setValueAtTime(640 + Math.random() * 320, now);
  o.frequency.exponentialRampToValueAtTime(280, now + 0.12);
  g.gain.setValueAtTime(0.0001, now);
  g.gain.exponentialRampToValueAtTime(0.04, now + 0.015);
  g.gain.exponentialRampToValueAtTime(0.0001, now + 0.14);
  o.connect(g);
  g.connect(master);
  o.start(now);
  o.stop(now + 0.16);
}

export function playDodgeBlip() {
  const c = ensureCtx();
  if (!c || !master || !unlocked || master.gain.value === 0) return;
  void c.resume();
  const now = c.currentTime;
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = "triangle";
  o.frequency.setValueAtTime(1200, now);
  o.frequency.exponentialRampToValueAtTime(400, now + 0.05);
  g.gain.setValueAtTime(0.0001, now);
  g.gain.exponentialRampToValueAtTime(0.025, now + 0.008);
  g.gain.exponentialRampToValueAtTime(0.0001, now + 0.06);
  o.connect(g);
  g.connect(master);
  o.start(now);
  o.stop(now + 0.07);
}
