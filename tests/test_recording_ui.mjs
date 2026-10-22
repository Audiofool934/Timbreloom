import assert from "node:assert/strict";
import { test } from "node:test";
import { measureInput, createInputMeter } from "../static/input-meter.js";
import { createTranscriptFollower, createLiveTranscription } from "../static/live-transcription.js";

class Element extends EventTarget {
  constructor(doc) { super(); this.ownerDocument = doc; }
  children = [];
  attributes = {};
  style = {};
  dataset = {};
  hidden = false;
  textWrites = 0;
  _text = "";
  set textContent(value) { this._text = value; this.textWrites++; }
  get textContent() { return this._text; }
  setAttribute(key, value) { this.attributes[key] = value; }
  append(...children) { this.children.push(...children); }
  after() {}
  insertBefore(child, before) {
    const index = this.children.indexOf(before);
    if (index < 0) this.children.push(child);
    else this.children.splice(index, 0, child);
  }
  scrollHeight = 500;
  clientHeight = 200;
  _scrollTop = 300;
  get scrollTop() { return this._scrollTop; }
  set scrollTop(value) { this._scrollTop = Math.max(0, Math.min(value, this.scrollHeight - this.clientHeight)); }
  scrollTo(options) { this.lastScroll = options; this.scrollTop = options.top; }
}

function event(type, values = {}) { return Object.assign(new Event(type), values); }

function fixture() {
  let now = 0;
  let amplitude = 0;
  let frameId = 0;
  const frames = new Map();
  const contexts = [];
  const observers = [];
  const source = {
    connected: new Set(["pcm processor"]), disconnected: [],
    connect(node) { this.connected.add(node); },
    disconnect(node) {
      this.disconnected.push(node);
      if (node) this.connected.delete(node);
      else this.connected.clear();
    },
  };
  class Context {
    constructor() { contexts.push(this); }
    closes = 0;
    suspends = 0;
    resumes = 0;
    analysers = [];
    createMediaStreamSource() { return source; }
    createAnalyser() {
      const analyser = { disconnects: 0, fftSize: 0,
        getFloatTimeDomainData(buffer) { buffer.fill(amplitude); },
        disconnect() { this.disconnects++; },
      };
      this.analysers.push(analyser);
      return analyser;
    }
    async resume() { this.resumes++; }
    async suspend() { this.suspends++; }
    async close() { this.closes++; }
  }
  const doc = new EventTarget();
  doc.hidden = false;
  doc.activeElement = null;
  doc.createElement = () => new Element(doc);
  doc.defaultView = {
    AudioContext: Context,
    performance: { now: () => now },
    requestAnimationFrame(callback) { frames.set(++frameId, callback); return frameId; },
    cancelAnimationFrame(id) { frames.delete(id); },
    matchMedia: () => ({ matches: true }),
    MutationObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe() {}
      disconnect() { this.disconnected = true; }
    },
  };
  const panel = new Element(doc);
  const meter = createInputMeter({ panel });
  const element = panel.children[0];
  const [heading, track, hint] = element.children;
  return { doc, panel, meter, element, track, hint, value: heading.children[1], source, contexts, Context, frames, observers,
    step(time, sample = amplitude) {
      now = time; amplitude = sample;
      const callbacks = [...frames.values()]; frames.clear();
      callbacks.forEach(callback => callback(time));
    },
  };
}

test("meter measures RMS in dBFS and detects clipping independently from average loudness", () => {
  const sine = Float32Array.from({ length: 4096 }, (_, i) => 0.5 * Math.sin(i / 4096 * 2 * Math.PI));
  const result = measureInput(sine);
  assert.ok(Math.abs(result.rms - 0.5 / Math.SQRT2) < 0.00001);
  assert.ok(Math.abs(result.db + 9.0309) < 0.001);
  assert.equal(result.clipping, false);
  const impulse = new Float32Array(2048);
  impulse[0] = 1;
  assert.equal(measureInput(impulse).clipping, true);
  assert.ok(measureInput(impulse).db < -30);
  assert.deepEqual(measureInput([]), { rms: 0, peak: 0, db: -60, level: 0, peakLevel: 0, clipping: false });
});

test("meter gives sustained silence feedback and never displays fabricated input", async () => {
  const f = fixture();
  await f.meter.start({ stream: {} });
  f.step(100, 0);
  assert.equal(f.element.dataset.inputState, "listening");
  assert.equal(f.track.children[0].style.transform, "scaleX(0)");
  f.step(3700, 0);
  assert.equal(f.element.dataset.inputState, "silent");
  assert.equal(f.track.attributes["aria-valuenow"], "-60");
  f.step(3800, 0.1);
  assert.equal(f.element.dataset.inputState, "signal");
  const announcements = f.hint.textWrites;
  f.step(3900, 0);
  f.step(4000, 0.08);
  assert.equal(f.hint.textWrites, announcements, "Short speech pauses must not cause repeated live announcements");
  f.step(4100, 1);
  assert.equal(f.element.dataset.inputState, "clipping");
  f.step(4700, 0.1);
  assert.equal(f.element.dataset.inputState, "clipping", "A brief clipped peak must remain readable");
  f.step(5400, 0.1);
  assert.equal(f.element.dataset.inputState, "signal");
  f.meter.stop();
  assert.equal(f.element.hidden, true);
  assert.equal(f.frames.size, 0);
  assert.equal(f.contexts[0].closes, 1);
});

test("hiding and stopping the live meter preserves the shared PCM audio graph and context", async () => {
  const f = fixture();
  const context = new f.Context();
  await f.meter.start({ stream: {}, context, source: f.source });
  assert.equal(f.contexts.length, 1, "Live capture must not create another context");
  f.doc.hidden = true;
  f.doc.dispatchEvent(new Event("visibilitychange"));
  assert.equal(f.frames.size, 0);
  assert.equal(context.analysers[0].disconnects, 1);
  assert.deepEqual([...f.source.connected], ["pcm processor"]);
  assert.equal(context.suspends, 0);
  f.doc.hidden = false;
  f.doc.dispatchEvent(new Event("visibilitychange"));
  assert.equal(f.frames.size, 1);
  f.meter.stop();
  assert.equal(context.closes, 0);
  assert.deepEqual([...f.source.connected], ["pcm processor"]);
  assert.ok(f.source.disconnected.every(Boolean), "Never disconnect all outputs from a borrowed source");
});

test("stopping while an owned context is resuming releases it and prevents a late meter start", async () => {
  const f = fixture();
  let resume;
  f.Context.prototype.resume = () => new Promise(resolve => { resume = resolve; });
  const pending = f.meter.start({ stream: {} });
  f.meter.stop();
  resume();
  await pending;
  assert.equal(f.contexts[0].closes, 1);
  assert.equal(f.frames.size, 0);
  assert.equal(f.element.hidden, true);
});

test("hiding a recording panel suspends only the meter and restores it without another context", async () => {
  const f = fixture();
  await f.meter.start({ stream: {} });
  f.panel.hidden = true;
  f.observers[0].callback();
  assert.equal(f.frames.size, 0);
  assert.equal(f.contexts[0].suspends, 1);
  assert.equal(f.contexts[0].closes, 0);
  f.panel.hidden = false;
  f.observers[0].callback();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.frames.size, 1);
  assert.equal(f.contexts.length, 1);
  f.meter.stop();
  assert.equal(f.observers[0].disconnected, true);
});

test("a failed meter releases its owned context without failing recording", async () => {
  const f = fixture();
  f.Context.prototype.createMediaStreamSource = () => { throw new Error("No input node"); };
  await f.meter.start({ stream: {} });
  assert.equal(f.contexts[0].closes, 1);
  assert.equal(f.element.dataset.inputState, "unavailable");
  assert.equal(f.frames.size, 0);
});

test("live text follows at the bottom but preserves upward reading, including keyboard input before scroll", () => {
  const f = fixture();
  const transcript = new Element(f.doc);
  const button = new Element(f.doc);
  const follower = createTranscriptFollower(transcript, button);
  follower.update(() => { transcript.scrollHeight += 100; });
  assert.equal(transcript.scrollTop, 400);
  assert.equal(button.hidden, true);
  transcript.dispatchEvent(event("keydown", { key: "PageUp" }));
  follower.update(() => { transcript.scrollHeight += 100; });
  assert.equal(transcript.scrollTop, 400, "New text must not override a pending keyboard scroll");
  assert.equal(button.hidden, false);
  transcript.scrollTop = 100;
  transcript.dispatchEvent(new Event("scroll"));
  follower.update(() => { transcript.scrollHeight += 100; });
  assert.equal(transcript.scrollTop, 100);
  f.doc.activeElement = button;
  button.dispatchEvent(new Event("click"));
  assert.equal(transcript.lastScroll.behavior, "instant");
  assert.equal(transcript.scrollTop, 600);
  assert.equal(f.doc.activeElement, button);
  assert.equal(button.hidden, false, "Jump must not remove the focused control");
  f.doc.activeElement = null;
  button.dispatchEvent(new Event("blur"));
  assert.equal(button.hidden, true);
});

test("a scroll before its event arrives pauses following and reaching the bottom resumes it", () => {
  const f = fixture();
  const transcript = new Element(f.doc);
  const button = new Element(f.doc);
  const follower = createTranscriptFollower(transcript, button);
  transcript.scrollTop = 120;
  follower.update(() => { transcript.scrollHeight += 100; });
  assert.equal(transcript.scrollTop, 120);
  transcript.scrollTop = transcript.scrollHeight;
  transcript.dispatchEvent(new Event("scroll"));
  follower.update(() => { transcript.scrollHeight += 100; });
  assert.equal(transcript.scrollTop, 500);
  assert.equal(button.hidden, true);
});

for (const refreshFails of [false, true]) test(`live completion keeps controls busy until transcript loading ${refreshFails ? "fails" : "finishes"}`, async () => {
  const f = fixture();
  const names = ["asrLiveControls", "asrLiveStart", "asrLiveStop", "asrLiveStatus", "asrLiveTimer",
    "asrLiveTranscript", "asrLiveStable", "asrLiveDraft", "asrLivePlaceholder", "asrLiveRecording"];
  const nodes = Object.fromEntries(names.map(name => { const node = new Element(f.doc); node.id = name; return [name, node]; }));
  f.doc.getElementById = id => nodes[id];
  let finishSaved;
  let failSaved;
  let savedEntered = false;
  let trackStops = 0;
  const saved = new Promise((resolve, reject) => { finishSaved = resolve; failSaved = reject; });
  const sockets = [];
  class LiveContext extends f.Context {
    audioWorklet = { async addModule() {} };
  }
  class Socket {
    static OPEN = 1;
    readyState = 1;
    constructor() { sockets.push(this); queueMicrotask(() => this.onopen?.()); }
    send() {}
    close() { this.readyState = 3; }
  }
  const replacements = {
    document: f.doc,
    window: Object.assign(f.doc.defaultView, { AudioContext: LiveContext, AudioWorkletNode: class {},
      setInterval: () => 1, clearInterval() {}, setTimeout, clearTimeout,
      localStorage: { setItem() {}, removeItem() {} }, addEventListener() {},
    }),
    AudioContext: LiveContext,
    WebSocket: Socket,
    location: { protocol: "http:", host: "127.0.0.1:7865" },
    navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop() { trackStops++; } }] }) } },
  };
  const originals = new Map(Object.keys(replacements).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  let completion;
  try {
    for (const [key, value] of Object.entries(replacements)) Object.defineProperty(globalThis, key, { configurable: true, value });
    const busyStates = [];
    const controller = createLiveTranscription({
      beforeStart: async () => true,
      getOptions: () => ({ model: "whisper", name: "Whisper", language: "en", prompt: "" }),
      onBusy: busy => busyStates.push(busy),
      onSaved: async () => { savedEntered = true; await saved; },
    });
    nodes.asrLiveStart.dispatchEvent(new Event("click"));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sockets.length, 1);
    completion = sockets[0].onmessage({ data: JSON.stringify({ type: "complete", transcript_id: "first" }) });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(savedEntered, true);
    assert.equal(controller.busy, true, "The previous onSaved must finish before a new session can start");
    assert.equal(nodes.asrLiveControls.dataset.state, "finalizing");
    assert.equal(nodes.asrLiveStart.hidden, true);
    assert.equal(trackStops, 1, "The microphone must be released before waiting for the transcript UI");
    assert.equal(f.contexts[0].closes, 1);
    await controller.stop("Leaving the workspace");
    assert.equal(nodes.asrLiveControls.dataset.state, "finalizing", "Leaving during finalization must not reset or cancel completion");
    nodes.asrLiveStart.dispatchEvent(new Event("click"));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sockets.length, 1, "An activation during saved-transcript loading must not acquire another microphone");
    if (refreshFails) failSaved(new Error("Connection interrupted while refreshing transcripts"));
    else finishSaved();
    await completion;
    assert.equal(controller.busy, false);
    assert.equal(nodes.asrLiveControls.dataset.state, "saved");
    assert.equal(busyStates.at(-1), false);
    if (refreshFails) assert.match(nodes.asrLiveStatus.textContent, /Use Refresh transcripts/);
  } finally {
    finishSaved();
    await completion;
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  }
});
