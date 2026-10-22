import { formatRecordingTime, recordingErrorMessage } from "./audio-recorder.js?v=6";
import { createInputMeter } from "./input-meter.js?v=1";

export function createTranscriptFollower(transcript, button) {
  const doc = transcript.ownerDocument;
  let following = true;
  let lastTop = transcript.scrollTop;
  const atBottom = () => transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight <= 4;
  function refreshButton() {
    // Do not remove a focused button after keyboard activation.
    button.hidden = following && doc.activeElement !== button;
    button.textContent = following ? "Following latest" : "Jump to latest";
  }
  function pause() {
    if (transcript.scrollHeight <= transcript.clientHeight) return;
    following = false;
    refreshButton();
  }
  transcript.addEventListener("scroll", () => {
    if (transcript.scrollTop < lastTop - 1) following = false;
    if (atBottom()) following = true;
    lastTop = transcript.scrollTop;
    refreshButton();
  }, { passive: true });
  transcript.addEventListener("wheel", (event) => { if (event.deltaY < 0) pause(); }, { passive: true });
  transcript.addEventListener("keydown", (event) => {
    if (["ArrowUp", "PageUp", "Home"].includes(event.key) || (event.key === " " && event.shiftKey)) pause();
  });
  button.addEventListener("click", () => {
    following = true;
    lastTop = transcript.scrollTop;
    const reduced = doc.defaultView.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    transcript.scrollTo({ top: transcript.scrollHeight, behavior: reduced ? "instant" : "smooth" });
    refreshButton();
  });
  button.addEventListener("blur", refreshButton);
  refreshButton();
  return {
    update(render) {
      // Read the position before replacing text, including a scroll whose event has not fired yet.
      if (transcript.scrollTop < lastTop - 1) following = false;
      const top = transcript.scrollTop;
      render();
      transcript.scrollTop = following ? transcript.scrollHeight : top;
      lastTop = transcript.scrollTop;
      refreshButton();
    },
    reset() {
      following = true;
      transcript.scrollTop = lastTop = 0;
      refreshButton();
    },
  };
}

export function createLiveTranscription({ beforeStart, getOptions, onSaved, onBusy }) {
  const panel = document.getElementById("asrLiveControls");
  const startButton = document.getElementById("asrLiveStart");
  const stopButton = document.getElementById("asrLiveStop");
  const status = document.getElementById("asrLiveStatus");
  const timer = document.getElementById("asrLiveTimer");
  const transcript = document.getElementById("asrLiveTranscript");
  const stable = document.getElementById("asrLiveStable");
  const draft = document.getElementById("asrLiveDraft");
  const placeholder = document.getElementById("asrLivePlaceholder");
  const recording = document.getElementById("asrLiveRecording");
  const inputMeter = createInputMeter({ panel, before: transcript });
  const followButton = document.createElement("button");
  followButton.id = "asrLiveFollow";
  followButton.type = "button";
  followButton.className = "live-follow-button";
  followButton.setAttribute("aria-controls", transcript.id);
  transcript.after(followButton);
  const follower = createTranscriptFollower(transcript, followButton);
  let state = "idle";
  let generation = 0;
  let socket, stream, context, source, processor, timerId, startedAt, flushDone;

  function setState(next, message) {
    state = next;
    panel.dataset.state = next;
    status.textContent = message;
    const busy = ["preparing", "listening", "stopping", "finalizing"].includes(next);
    startButton.hidden = busy;
    stopButton.hidden = !busy;
    stopButton.disabled = next === "stopping" || next === "finalizing";
    stopButton.textContent = next === "preparing" ? "Cancel start" : next === "stopping" ? "Saving transcript..."
      : next === "finalizing" ? "Finishing..." : "Stop and save";
    onBusy(busy);
  }

  async function releaseCapture() {
    inputMeter.stop();
    window.clearInterval(timerId);
    const capture = { stream, context, source, processor };
    stream = context = source = processor = null;
    capture.stream?.getTracks().forEach(track => track.stop());
    capture.source?.disconnect();
    if (capture.processor) {
      await new Promise(resolve => {
        const timeout = window.setTimeout(resolve, 300);
        flushDone = () => { window.clearTimeout(timeout); resolve(); };
        capture.processor.port.postMessage({ type: "flush" });
      });
      capture.processor.port.onmessage = null;
      capture.processor.disconnect();
    }
    if (capture.context) await capture.context.close().catch(() => {});
  }

  async function stop(message = "Microphone off. Finishing and saving your transcript...") {
    if (!["preparing", "listening"].includes(state)) return;
    const wasPreparing = state === "preparing";
    setState("stopping", message);
    ++generation;
    await releaseCapture();
    if (state !== "stopping") return;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "stop" }));
    else {
      const connection = socket;
      socket = null;
      connection?.close();
      setState("idle", wasPreparing ? "Ready when you are." : "Connection closed. Received audio was kept on this Mac.");
    }
  }

  async function start() {
    if (["preparing", "listening", "stopping", "finalizing"].includes(state)) return;
    const request = ++generation;
    setState("preparing", "Checking the local model...");
    recording.hidden = true;
    stable.textContent = draft.textContent = "";
    follower.reset();
    placeholder.hidden = false;
    timer.textContent = "00:00";
    let acquired;
    try {
      const available = await beforeStart();
      if (request !== generation) return;
      if (!available) {
        setState("idle", "Download the selected model from Models to use live transcription.");
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext || !window.AudioWorkletNode) {
        throw new Error("Live microphone capture is unavailable here. You can still record or import a file.");
      }
      status.textContent = "Allow microphone access to start.";
      acquired = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false });
      if (request !== generation) { acquired.getTracks().forEach(track => track.stop()); return; }
      stream = acquired;
      context = new AudioContext();
      await context.audioWorklet.addModule("/static/live-audio-worklet.js?v=1");
      await context.resume();
      if (request !== generation) return;
      const options = getOptions();
      status.textContent = `Preparing ${options.name}. Start speaking when Listening appears.`;
      const connection = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/asr/live`);
      socket = connection;
      connection.onopen = () => {
        connection.send(JSON.stringify({ type: "start", model: options.model, language: options.language,
          prompt: options.prompt, sample_rate: 16000 }));
        if (request !== generation) connection.send(JSON.stringify({ type: "stop" }));
      };
      connection.onmessage = async ({ data }) => {
        if (socket !== connection) return;
        const event = JSON.parse(data);
        if (event.job_id) window.localStorage.setItem("timbreloomCurrentAsrJob", event.job_id);
        if (event.type === "ready" && request === generation && state === "preparing") {
          try {
            source = context.createMediaStreamSource(stream);
            processor = new AudioWorkletNode(context, "timbreloom-live-audio", { channelCount: 1 });
            processor.port.onmessage = ({ data: packet }) => {
              if (packet.type === "flushed") { flushDone?.(); return; }
              if (connection.readyState === WebSocket.OPEN) {
                if (connection.bufferedAmount > 320000) {
                  void stop("Connection is too slow. Stopping and saving received audio...");
                  return;
                }
                connection.send(packet.pcm);
              }
            };
            source.connect(processor);
            processor.connect(context.destination); // Processor outputs silence, never microphone feedback.
            void inputMeter.start({ stream, context, source });
            for (const track of stream.getTracks()) track.onended = () => void stop("Microphone disconnected. Saving received audio...");
            startedAt = performance.now();
            timerId = window.setInterval(() => { timer.textContent = formatRecordingTime((performance.now() - startedAt) / 1000); }, 500);
            setState("listening", "Listening on this Mac. Words appear with a short delay.");
          } catch (error) {
            void stop(error.message);
          }
        } else if (event.type === "partial") {
          follower.update(() => {
            stable.textContent = event.text;
            draft.textContent = (event.text && event.draft ? " " : "") + event.draft;
            placeholder.hidden = Boolean(event.text || event.draft);
          });
        } else if (event.type === "stopping") {
          void stop(event.message);
        } else if (["complete", "error", "cancelled"].includes(event.type)) {
          ++generation;
          socket = null;
          // Keep the next session blocked until this session has finished updating shared UI.
          setState("finalizing", event.transcript_id ? "Microphone off. Opening saved transcript..." : "Microphone off. Finishing...");
          await releaseCapture();
          window.localStorage.removeItem("timbreloomCurrentAsrJob");
          connection.close();
          let message = event.warning || event.message || (event.type === "cancelled" ? "Start cancelled. Ready when you are." : "Saved to Transcripts. You can edit and export the text below.");
          if (event.audio_url) { recording.href = event.audio_url; recording.hidden = false; }
          if (event.transcript_id) {
            try { await onSaved(event.transcript_id); }
            catch { message = "Transcript saved. Use Refresh transcripts to open it when the connection returns."; }
          }
          setState(event.type === "complete" ? "saved" : event.type === "cancelled" ? "idle" : "error", message);
        }
      };
      connection.onclose = async () => {
        if (socket !== connection) return;
        socket = null;
        ++generation;
        await releaseCapture();
        setState("error", "Connection closed. Received audio is being saved on this Mac. Refresh Transcripts to check it.");
      };
    } catch (error) {
      if (request !== generation) return;
      await releaseCapture();
      setState("error", error.name === "NotAllowedError" || error.name === "NotFoundError" ? recordingErrorMessage(error) : error.message);
    }
  }

  startButton.addEventListener("click", start);
  stopButton.addEventListener("click", () => void stop());
  window.addEventListener("pagehide", () => { stream?.getTracks().forEach(track => track.stop()); socket?.close(); void releaseCapture(); });
  return { stop, get busy() { return ["preparing", "listening", "stopping", "finalizing"].includes(state); } };
}
