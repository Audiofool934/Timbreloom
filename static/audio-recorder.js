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
    return window.timbreloomDesktop ? "未获得麦克风权限，请允许 Timbreloom 使用麦克风后重试。" : "没有获得麦克风权限，请在浏览器中允许后重试。";
  }
  if (error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError") {
    return "没有找到可用麦克风。";
  }
  if (error?.name === "NotReadableError" || error?.name === "TrackStartError") {
    return "麦克风正被其他应用占用，请关闭占用后重试。";
  }
  return `无法开始录音：${error?.message || "未知错误"}`;
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
    startButton.textContent = "开始录音";
    status.textContent = idleMessage;
    timer.textContent = "00:00";
  }

  function cancel(message = "录音已取消，原有文件没有改变。") {
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
      status.textContent = "录音太短，没有替换原有文件，请重新录制。";
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
    status.textContent = `已录制 ${elapsedSeconds.toFixed(1)} 秒 · 可试听或直接继续`;
    startButton.textContent = "重新录音";
  }

  function stop() {
    if (!recorder || recorder.state === "inactive") return;
    stopButton.disabled = true;
    status.textContent = "正在整理录音...";
    recorder.stop();
  }

  async function start() {
    if (!recordingSupported) {
      status.textContent = "当前浏览器不支持麦克风录音，请继续选择文件。";
      return;
    }
    if (startButton.disabled || recorder?.state === "recording") return;
    if (activeRecordingController && activeRecordingController !== controller) {
      activeRecordingController.cancel("已在另一个入口开始录音。上一次录音已取消。");
    }

    const request = ++permissionRequest;
    activeRecordingController = controller;
    startButton.disabled = true;
    panel.dataset.state = "requesting";
    status.textContent = "正在请求麦克风权限...";
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
      status.textContent = "正在录音 · 说完后点击停止并使用";
      timer.textContent = "00:00";
      timerId = window.setInterval(() => {
        const elapsedSeconds = (performance.now() - startedAt) / 1000;
        timer.textContent = formatRecordingTime(elapsedSeconds);
        if (elapsedSeconds >= maxSeconds) {
          status.textContent = "已到最长录音时间，正在自动停止...";
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
    status.textContent = "当前浏览器不支持麦克风录音，请继续选择文件。";
  }
  startButton.addEventListener("click", start);
  stopButton.addEventListener("click", stop);
  cancelButton.addEventListener("click", () => cancel());
  return controller;
}

export function cancelRecordingOutside(view) {
  if (activeRecordingController && activeRecordingController.view !== view) {
    activeRecordingController.cancel("切换页面，录音已取消。");
  }
}

export function cancelActiveRecording() {
  if (activeRecordingController) activeRecordingController.cancel();
}

export function cancelRecordingFor(view, message) {
  if (activeRecordingController?.view === view) activeRecordingController.cancel(message);
}
