// Area averaging preserves continuity when capture runs at 44.1 or 48 kHz.
export class PCMResampler {
  constructor(inputRate, outputRate = 16000, packetSize = 1600) {
    this.ratio = inputRate / outputRate;
    this.packetSize = packetSize;
    this.weight = 0;
    this.sum = 0;
    this.packet = [];
  }

  push(samples, emit) {
    for (const sample of samples) {
      let remaining = 1;
      while (remaining > 1e-9) {
        const take = Math.min(remaining, this.ratio - this.weight);
        this.sum += Math.max(-1, Math.min(1, sample)) * take;
        this.weight += take;
        remaining -= take;
        if (this.weight >= this.ratio - 1e-9) {
          this.packet.push(Math.round(this.sum / this.weight * 32767));
          this.weight = 0;
          this.sum = 0;
          if (this.packet.length >= this.packetSize) this.emit(emit);
        }
      }
    }
  }

  emit(callback) {
    if (!this.packet.length) return;
    const buffer = new ArrayBuffer(this.packet.length * 2);
    const view = new DataView(buffer);
    this.packet.forEach((value, index) => view.setInt16(index * 2, value, true));
    this.packet = [];
    callback(buffer);
  }

  flush(callback) {
    if (this.weight) this.packet.push(Math.round(this.sum / this.weight * 32767));
    this.weight = 0;
    this.sum = 0;
    this.emit(callback);
  }
}
