import { PCMResampler } from "./pcm-resampler.js";

class LiveAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.resampler = new PCMResampler(sampleRate);
    this.finished = false;
    this.emit = (pcm) => this.port.postMessage({ type: "pcm", pcm }, [pcm]);
    this.port.onmessage = ({ data }) => {
      if (data.type === "flush") {
        this.finished = true;
        this.resampler.flush(this.emit);
        this.port.postMessage({ type: "flushed" });
      }
    };
  }

  process(inputs) {
    if (!this.finished && inputs[0]?.[0]) this.resampler.push(inputs[0][0], this.emit);
    return !this.finished;
  }
}

registerProcessor("timbreloom-live-audio", LiveAudioProcessor);
