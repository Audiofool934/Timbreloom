let activeRecordingController = null;

function formatRecordingTime(seconds) {
  const wholeSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(wholeSeconds / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  const remaining = wholeSeconds % 60;
  const minuteText = String(minutes).padStart(2, "0");
  const secondText = String(remaining).padStart(2, "0");
  return hours ? `${String(hours).padStart(2, "0")}:${minuteText}:${secondText}` : `${minuteText}:${secondText}`;
}

function recordingFormat() {
  const candidates = [
    { mimeType: "audio/mp4;codecs=mp4a.40.2", extension: "m4a" },
    { mimeType: "audio/mp4", extension: "m4a" },
    { mimeType: "audio/webm;codecs=opus", extension: "webm" },
    { mimeType: "audio/webm", extension: "webm" },
  ];
  if (typeof MediaRecorder.isTypeSupported !== "function") return candidates.at(-1);
  return candidates.find(({ mimeType }) => MediaRecorder.isTypeSupported(mimeType)) || { mimeType: "", extension: "webm" };
}

function recordingFilename(extension) {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace("T", "-").slice(0, 15);
  return `recording-${stamp}.${extension}`;
}

function recordingErrorMessage(error) {
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return window.timbreloomDesktop ? "Microphone permission is required. Allow Timbreloom to use the microphone and try again." : "Microphone permission is required. Allow access in your browser and try again.";
  }
  if (error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError") {
    return "No microphone is available.";
  }
  if (error?.name === "NotReadableError" || error?.name === "TrackStartError") {
    return "Another app is using the microphone. Close it and try again.";
  }
  return `Cannot start recording: ${error?.message || "Unknown error"}`;
}

export function createAudioRecorder({
  view,
  input,
  panel,
  status,
  timer,
  startButton,
  stopButton,
  cancelButton,
  preview,
  maxSeconds,
  idleMessage,
  onFile,
}) {
  const recordingSupported = Boolean(navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined");
  let recorder = null;
  let stream = null;
  let chunks = [];
  let startedAt = 0;
  let timerId = null;
  let previewUrl = "";
  let previewSeconds = 0;
  let permissionRequest = 0;

  function releaseStream() {
    if (stream) {
      for (const track of stream.getTracks()) track.stop();
    }
    stream = null;
  }

  function clearTimer() {
    window.clearInterval(timerId);
    timerId = null;
  }

  function setRecordingControls(recording) {
    panel.classList.toggle("is-recording", recording);
    panel.dataset.state = recording ? "recording" : "idle";
    startButton.hidden = recording;
    stopButton.hidden = !recording;
    cancelButton.hidden = !recording;
    stopButton.disabled = false;
  }

  function clearPreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = "";
    previewSeconds = 0;
    preview.pause();
    preview.removeAttribute("src");
    preview.hidden = true;
    preview.load();
    startButton.textContent = "Record";
    status.textContent = idleMessage;
    timer.textContent = "00:00";
  }

  function cancel(message = "Recording canceled. The previous file is unchanged.") {
    permissionRequest++;
    startButton.disabled = false;
    clearTimer();
    if (recorder && recorder.state !== "inactive") {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.onerror = null;
      recorder.stop();
    }
    recorder = null;
    chunks = [];
    releaseStream();
    setRecordingControls(false);
    status.textContent = message;
    timer.textContent = previewUrl ? formatRecordingTime(previewSeconds) : "00:00";
    if (activeRecordingController === controller) activeRecordingController = null;
  }

  function finishRecording() {
    const elapsedSeconds = Math.max(0, (performance.now() - startedAt) / 1000);
    clearTimer();
    releaseStream();
    setRecordingControls(false);

    const format = recordingFormat();
    const mimeType = recorder?.mimeType || format.mimeType || "audio/webm";
    const extension = mimeType.includes("mp4") ? "m4a" : "webm";
    const blob = new Blob(chunks, { type: mimeType });
    recorder = null;
    chunks = [];
    if (activeRecordingController === controller) activeRecordingController = null;

    if (!blob.size || elapsedSeconds < 0.25) {
      status.textContent = "The recording is too short. The previous file is unchanged. Record again.";
      return;
    }

    const file = new File([blob], recordingFilename(extension), { type: mimeType, lastModified: Date.now() });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    onFile(file);

    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(blob);
    previewSeconds = elapsedSeconds;
    preview.src = previewUrl;
    preview.hidden = false;
    timer.textContent = formatRecordingTime(elapsedSeconds);
    status.textContent = `Recorded ${elapsedSeconds.toFixed(1)} sec · Preview or continue`;
    startButton.textContent = "Record again";
  }

  function stop() {
    if (!recorder || recorder.state === "inactive") return;
    stopButton.disabled = true;
    status.textContent = "Preparing recording...";
    recorder.stop();
  }

  async function start() {
    if (!recordingSupported) {
      status.textContent = "This browser does not support microphone recording. Choose a file instead.";
      return;
    }
    if (startButton.disabled || recorder?.state === "recording") return;
    if (activeRecordingController && activeRecordingController !== controller) {
      activeRecordingController.cancel("Recording started elsewhere. The previous recording was canceled.");
    }

    const request = ++permissionRequest;
    activeRecordingController = controller;
    startButton.disabled = true;
    panel.dataset.state = "requesting";
    status.textContent = "Requesting microphone permission...";
    try {
      const acquiredStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
        video: false,
      });
      if (request !== permissionRequest) {
        for (const track of acquiredStream.getTracks()) track.stop();
        return;
      }
      stream = acquiredStream;
      const format = recordingFormat();
      const recorderOptions = { audioBitsPerSecond: 128000 };
      if (format.mimeType) recorderOptions.mimeType = format.mimeType;
      try {
        recorder = new MediaRecorder(stream, recorderOptions);
      } catch {
        recorder = new MediaRecorder(stream);
      }
      chunks = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onstop = finishRecording;
      recorder.onerror = (event) => { cancel(recordingErrorMessage(event.error)); panel.dataset.state = "error"; };
      recorder.start(250);
      startedAt = performance.now();
      activeRecordingController = controller;
      setRecordingControls(true);
      status.textContent = "Recording · Select Stop and use when finished";
      timer.textContent = "00:00";
      timerId = window.setInterval(() => {
        const elapsedSeconds = (performance.now() - startedAt) / 1000;
        timer.textContent = formatRecordingTime(elapsedSeconds);
        if (elapsedSeconds >= maxSeconds) {
          status.textContent = "Maximum recording time reached. Stopping automatically...";
          stop();
        }
      }, 250);
    } catch (error) {
      if (request !== permissionRequest) return;
      releaseStream();
      if (activeRecordingController === controller) activeRecordingController = null;
      status.textContent = recordingErrorMessage(error);
      panel.dataset.state = "error";
    } finally {
      if (request === permissionRequest) startButton.disabled = false;
    }
  }

  const controller = { view, start, stop, cancel, clearPreview };
  panel.dataset.recordingSupported = recordingSupported.toString();
  if (!recordingSupported) {
    startButton.disabled = true;
    panel.dataset.state = "unavailable";
    status.textContent = "This browser does not support microphone recording. Choose a file instead.";
  }
  startButton.addEventListener("click", start);
  stopButton.addEventListener("click", stop);
  cancelButton.addEventListener("click", () => cancel());
  return controller;
}

export function cancelRecordingOutside(view) {
  if (activeRecordingController && activeRecordingController.view !== view) {
    activeRecordingController.cancel("Recording canceled after switching workspaces.");
  }
}

export function cancelActiveRecording() {
  if (activeRecordingController) activeRecordingController.cancel();
}

export function cancelRecordingFor(view, message) {
  if (activeRecordingController?.view === view) activeRecordingController.cancel(message);
}
