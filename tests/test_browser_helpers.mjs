import assert from "node:assert/strict";
import { test } from "node:test";
import { createProgressiveAudioPlayer } from "../static/audio-player.js";
import { readJob, JobConnectionError } from "../static/job-client.js";

class Element extends EventTarget {
  hidden = true;
  disabled = false;
  textContent = "";
}
class Audio extends Element {
  paused = true;
  ended = false;
  src = "";
  load() {
    this.ended = false;
    queueMicrotask(() => this.dispatchEvent(new Event("loadedmetadata")));
  }
  async play() {
    this.paused = false;
    this.dispatchEvent(new Event("play"));
  }
  pause() {
    this.paused = true;
    this.dispatchEvent(new Event("pause"));
  }
  getAttribute() { return this.src; }
  removeAttribute() { this.src = ""; }
  finish() {
    this.paused = true;
    this.ended = true;
    this.dispatchEvent(new Event("ended"));
  }
}

const flush = () => new Promise(resolve => setImmediate(resolve));
const chunk = (index) => ({index, audio_url: `/chunk-${index}.wav`});

test("playback waits for the next immutable chunk and follows when it arrives", async () => {
  globalThis.window = { setTimeout };
  const audio = new Audio();
  const card = new Element();
  const status = new Element();
  const toggle = new Element();
  const player = createProgressiveAudioPlayer({card, audio, status, toggle, waitingLabel: "Waiting"});
  player.update({chunks: [chunk(1)], total: 2, complete: false}, "job-a");
  await flush();
  await audio.play();
  audio.finish();
  assert.match(status.textContent, /等待第 2 段/);
  player.update({chunks: [chunk(1), chunk(2)], total: 2, complete: true}, "job-a");
  await flush();
  assert.match(audio.src, /^\/chunk-2.wav/);
  assert.equal(audio.paused, false);
  audio.finish();
  assert.equal(toggle.textContent, "从头连续播放");
});

test("paused playback stays paused when more chunks arrive", async () => {
  globalThis.window = { setTimeout };
  const audio = new Audio();
  const player = createProgressiveAudioPlayer({card: new Element(), audio,
    status: new Element(), toggle: new Element(), waitingLabel: "Waiting"});
  player.update({chunks: [chunk(1)], total: 2, complete: false}, "job-a");
  await flush();
  await audio.play();
  audio.pause();
  await flush();
  player.update({chunks: [chunk(1), chunk(2)], total: 2, complete: true}, "job-a");
  assert.equal(audio.paused, true);
  assert.match(audio.src, /^\/chunk-1.wav/);
});

test("polling distinguishes a temporary outage from a deleted job", async () => {
  const previous = globalThis.fetch;
  try {
    globalThis.fetch = async () => { throw new TypeError("connection refused"); };
    await assert.rejects(readJob("/api/jobs/a"), JobConnectionError);
    globalThis.fetch = async () => new Response("unavailable", {status: 503});
    await assert.rejects(readJob("/api/jobs/a"), JobConnectionError);
    globalThis.fetch = async () => Response.json({detail: "missing"}, {status: 404});
    await assert.rejects(readJob("/api/jobs/a"), error =>
      !(error instanceof JobConnectionError) && error.message === "missing");
    globalThis.fetch = async () => Response.json({status: "complete"});
    assert.deepEqual(await readJob("/api/jobs/a"), {status: "complete"});
  } finally {
    globalThis.fetch = previous;
  }
});

test("switching workflows cancels recording and releases microphone tracks", async () => {
  const { createAudioRecorder, cancelRecordingOutside } = await import("../static/audio-recorder.js");
  globalThis.window = { setTimeout, setInterval, clearInterval };
  let stopped = 0;
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const previousRecorder = globalThis.MediaRecorder;
  Object.defineProperty(globalThis, "navigator", {configurable: true, value: {
    mediaDevices: {getUserMedia: async () => ({getTracks: () => [{stop: () => stopped++}]})},
  }});
  globalThis.MediaRecorder = class {
    static isTypeSupported() { return true; }
    state = "inactive";
    start() { this.state = "recording"; }
    stop() { this.state = "inactive"; this.onstop?.(); }
  };
  try {
    const status = new Element();
    const controller = createAudioRecorder({view: "clone", input: {},
      panel: {classList: {toggle() {}}, dataset: {}}, status, timer: new Element(),
      startButton: new Element(), stopButton: new Element(), cancelButton: new Element(),
      preview: new Audio(), maxSeconds: 30, idleMessage: "Idle", onFile() {},
    });
    await controller.start();
    cancelRecordingOutside("clone");
    assert.equal(stopped, 0);
    cancelRecordingOutside("asr");
    assert.equal(stopped, 1);
    assert.match(status.textContent, /录音已取消/);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "navigator", descriptor);
    else delete globalThis.navigator;
    globalThis.MediaRecorder = previousRecorder;
  }
});

test("leaving a workflow during microphone permission never starts a late recording", async () => {
  const { createAudioRecorder, cancelRecordingOutside } = await import("../static/audio-recorder.js");
  globalThis.window = { setTimeout, setInterval, clearInterval };
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const previousRecorder = globalThis.MediaRecorder;
  let grant;
  let stopped = 0;
  let started = 0;
  Object.defineProperty(globalThis, "navigator", {configurable: true, value: {
    mediaDevices: {getUserMedia: () => new Promise(resolve => { grant = resolve; })},
  }});
  globalThis.MediaRecorder = class {
    static isTypeSupported() { return true; }
    state = "inactive";
    start() { started++; this.state = "recording"; }
    stop() { this.state = "inactive"; this.onstop?.(); }
  };
  let controller;
  try {
    const status = new Element();
    const startButton = new Element();
    controller = createAudioRecorder({view: "clone", input: {},
      panel: {classList: {toggle() {}}, dataset: {}}, status, timer: new Element(),
      startButton, stopButton: new Element(), cancelButton: new Element(),
      preview: new Audio(), maxSeconds: 30, idleMessage: "Idle", onFile() {},
    });
    const pending = controller.start();
    cancelRecordingOutside("asr");
    grant({getTracks: () => [{stop: () => stopped++}]});
    await pending;
    assert.equal(started, 0);
    assert.equal(stopped, 1);
    assert.equal(startButton.disabled, false);
    assert.match(status.textContent, /录音已取消/);
  } finally {
    controller?.cancel();
    if (descriptor) Object.defineProperty(globalThis, "navigator", descriptor);
    else delete globalThis.navigator;
    globalThis.MediaRecorder = previousRecorder;
  }
});
