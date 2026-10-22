import assert from "node:assert/strict";
import { test } from "node:test";
import { PCMResampler } from "../static/pcm-resampler.js";

for (const rate of [44100, 48000, 16000]) {
  test(`capture at ${rate} Hz preserves duration and samples across render quanta`, () => {
    const input = Float32Array.from({length: rate}, (_, i) => Math.sin(i / rate * 440 * Math.PI * 2) * .5);
    const packets = [];
    const stream = new PCMResampler(rate);
    for (let i = 0; i < input.length; i += 128) stream.push(input.subarray(i, i + 128), value => packets.push(value));
    stream.flush(value => packets.push(value));
    assert.equal(packets.reduce((sum, value) => sum + value.byteLength, 0), 32000);
    const actual = Buffer.concat(packets.map(value => Buffer.from(value)));
    const whole = [];
    const control = new PCMResampler(rate);
    control.push(input, value => whole.push(Buffer.from(value)));
    control.flush(value => whole.push(Buffer.from(value)));
    assert.deepEqual(actual, Buffer.concat(whole));
    assert.ok(actual.readInt16LE(20) > 1000);
  });
}

test("stop flushes a short final packet in little-endian PCM", () => {
  const stream = new PCMResampler(48000);
  const output = [];
  stream.push(new Float32Array(300).fill(.5), value => output.push(value));
  assert.equal(output.length, 0);
  stream.flush(value => output.push(value));
  assert.equal(output[0].byteLength, 200);
  assert.equal(new DataView(output[0]).getInt16(0, true), 16384);
  stream.flush(value => output.push(value));
  assert.equal(output.length, 1);
});
