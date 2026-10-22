const FLOOR_DB = -60;

export function measureInput(samples) {
  let sum = 0;
  let peak = 0;
  for (const sample of samples) {
    const magnitude = Math.abs(Number.isFinite(sample) ? sample : 0);
    sum += magnitude * magnitude;
    peak = Math.max(peak, magnitude);
  }
  const rms = samples.length ? Math.sqrt(sum / samples.length) : 0;
  const db = Math.max(FLOOR_DB, Math.min(0, 20 * Math.log10(rms || Number.MIN_VALUE)));
  const peakDb = Math.max(FLOOR_DB, Math.min(0, 20 * Math.log10(peak || Number.MIN_VALUE)));
  return { rms, peak, db, level: (db - FLOOR_DB) / -FLOOR_DB,
    peakLevel: (peakDb - FLOOR_DB) / -FLOOR_DB, clipping: peak >= 0.985 };
}

// The meter only observes capture. It never changes the stream or routes it to speakers.
export function createInputMeter({ panel, before }) {
  const doc = panel?.ownerDocument;
  if (!doc?.createElement) return { start() {}, stop() {} };
  const win = doc.defaultView;
  const element = doc.createElement("div");
  element.className = "recording-input-meter";
  element.hidden = true;
  const heading = doc.createElement("div");
  heading.className = "input-meter-heading";
  const label = doc.createElement("span");
  label.textContent = "Microphone input";
  const value = doc.createElement("span");
  value.className = "input-meter-value";
  value.setAttribute("aria-hidden", "true");
  heading.append(label, value);
  const track = doc.createElement("div");
  track.className = "input-meter-track";
  track.setAttribute("role", "meter");
  track.setAttribute("aria-label", "Microphone input level");
  track.setAttribute("aria-valuemin", String(FLOOR_DB));
  track.setAttribute("aria-valuemax", "0");
  const fill = doc.createElement("span");
  fill.className = "input-meter-fill";
  const peak = doc.createElement("span");
  peak.className = "input-meter-peak";
  track.append(fill, peak);
  const hint = doc.createElement("p");
  hint.className = "input-meter-hint";
  hint.setAttribute("role", "status");
  hint.setAttribute("aria-live", "polite");
  hint.setAttribute("aria-atomic", "true");
  element.append(heading, track, hint);
  panel.insertBefore(element, before || null);

  let capture = null;
  let analyser = null;
  let frame = null;
  let samples = null;
  let lastPaint = -Infinity;
  let lastReading = -Infinity;
  let lastSignal = 0;
  let clipUntil = 0;
  let peakUntil = 0;
  let heldPeak = 0;
  let hasSignal = false;
  let generation = 0;
  let visibilityObserver = null;
  const isHidden = () => doc.hidden || panel.hidden || Boolean(panel.closest?.("[hidden]"))
    || Boolean(panel.getClientRects && !panel.getClientRects().length);

  function setHint(state, message) {
    if (element.dataset.inputState === state) return;
    element.dataset.inputState = state;
    hint.textContent = message;
  }

  function resetReading() {
    fill.style.transform = "scaleX(0)";
    peak.style.left = "0%";
    value.textContent = "< -60 dBFS";
    track.setAttribute("aria-valuenow", String(FLOOR_DB));
    track.setAttribute("aria-valuetext", "No sound detected");
  }

  function disconnect() {
    if (frame !== null) win.cancelAnimationFrame(frame);
    frame = null;
    if (analyser) {
      // A borrowed source can also feed the live PCM processor. Disconnect only this branch.
      try { capture?.source.disconnect(analyser); } catch { /* Already disconnected. */ }
      analyser.disconnect();
      analyser = null;
    }
  }

  function draw(now) {
    if (!capture || !analyser || doc.hidden) { disconnect(); return; }
    frame = win.requestAnimationFrame(draw);
    if (now - lastPaint < 65) return;
    lastPaint = now;
    analyser.getFloatTimeDomainData(samples);
    const reading = measureInput(samples);
    if (reading.db > -55) { lastSignal = now; hasSignal = true; }
    if (reading.clipping) clipUntil = now + 1200;
    if (reading.peakLevel >= heldPeak || now > peakUntil) {
      heldPeak = reading.peakLevel;
      peakUntil = now + 600;
    }
    fill.style.transform = `scaleX(${reading.level})`;
    peak.style.left = `${heldPeak * 100}%`;
    if (now < clipUntil) setHint("clipping", "Input is clipping. Lower the input level or move back.");
    else if (now - lastSignal > 3500) setHint("silent", "No sound detected. Try speaking or check your microphone.");
    else if (hasSignal) setHint("signal", "Sound detected. Keep a comfortable distance from the microphone.");
    else setHint("listening", "Listening for sound...");
    if (now - lastReading >= 500) {
      lastReading = now;
      const db = Math.round(reading.db);
      value.textContent = db <= FLOOR_DB ? "< -60 dBFS" : `${db} dBFS`;
      track.setAttribute("aria-valuenow", String(db));
      track.setAttribute("aria-valuetext", reading.db <= FLOOR_DB ? "No sound detected" : `${Math.abs(db)} decibels below full scale`);
    }
  }

  function connect() {
    if (!capture || analyser || isHidden()) return;
    analyser = capture.context.createAnalyser();
    analyser.fftSize = 2048;
    samples = new Float32Array(analyser.fftSize);
    capture.source.connect(analyser);
    lastPaint = lastReading = -Infinity;
    lastSignal = win.performance.now();
    frame = win.requestAnimationFrame(draw);
  }

  async function visibilityChanged() {
    const current = capture;
    if (!current) return;
    if (isHidden()) {
      disconnect();
      resetReading();
      if (current.owned) await current.context.suspend().catch(() => {});
    } else {
      if (current.owned) await current.context.resume().catch(() => {});
      if (capture === current) connect();
    }
  }

  function stop() {
    ++generation;
    disconnect();
    const previous = capture;
    capture = null;
    visibilityObserver?.disconnect();
    visibilityObserver = null;
    doc.removeEventListener("visibilitychange", visibilityChanged);
    if (previous?.owned) {
      previous.source?.disconnect();
      void previous.context.close().catch(() => {});
    }
    element.hidden = true;
    resetReading();
  }

  async function start({ stream, context, source }) {
    stop();
    const request = generation;
    element.hidden = false;
    setHint("listening", "Listening for sound...");
    clipUntil = peakUntil = heldPeak = 0;
    hasSignal = false;
    try {
      const owned = !context;
      const audioContext = context || new win.AudioContext();
      capture = { context: audioContext, source: null, owned };
      capture.source = source || audioContext.createMediaStreamSource(stream);
      if (owned) await audioContext.resume();
      if (request !== generation) return;
      doc.addEventListener("visibilitychange", visibilityChanged);
      if (win.MutationObserver) {
        visibilityObserver = new win.MutationObserver(() => { void visibilityChanged(); });
        for (let ancestor = panel; ancestor; ancestor = ancestor.parentElement) {
          visibilityObserver.observe(ancestor, { attributes: true, attributeFilter: ["hidden", "class", "style"] });
        }
      }
      connect();
      if (isHidden() && owned) await audioContext.suspend();
    } catch {
      if (request !== generation) return;
      stop();
      element.hidden = false;
      setHint("unavailable", "Input level is unavailable. Recording can continue.");
    }
  }

  resetReading();
  return { start, stop };
}
