const form = document.querySelector("#cloneForm");
const audioInput = document.querySelector("#referenceAudio");
const referenceText = document.querySelector("#referenceText");
const dropzone = document.querySelector("#dropzone");
const fileTitle = document.querySelector("#fileTitle");
const fileMeta = document.querySelector("#fileMeta");
const voiceSelect = document.querySelector("#voiceSelect");
const uploadVoiceFields = document.querySelector("#uploadVoiceFields");
const savedVoiceCard = document.querySelector("#savedVoiceCard");
const savedVoiceName = document.querySelector("#savedVoiceName");
const savedVoiceMeta = document.querySelector("#savedVoiceMeta");
const savedVoiceTranscript = document.querySelector("#savedVoiceTranscript");
const voiceName = document.querySelector("#voiceName");
const saveVoiceButton = document.querySelector("#saveVoiceButton");
const deleteVoiceButton = document.querySelector("#deleteVoiceButton");
const voiceSaveStatus = document.querySelector("#voiceSaveStatus");
const targetText = document.querySelector("#targetText");
const targetCount = document.querySelector("#targetCount");
const segmentEstimate = document.querySelector("#segmentEstimate");
const language = document.querySelector("#language");
const generateButton = document.querySelector("#generateButton");
const buttonText = document.querySelector("#buttonText");
const progressCard = document.querySelector("#progressCard");
const progressTitle = document.querySelector("#progressTitle");
const progressText = document.querySelector("#progressText");
const progressTrack = document.querySelector("#progressTrack");
const progressFill = document.querySelector("#progressFill");
const progressPercent = document.querySelector("#progressPercent");
const progressSegments = document.querySelector("#progressSegments");
const currentSegmentText = document.querySelector("#currentSegmentText");
const cancelButton = document.querySelector("#cancelButton");
const resultCard = document.querySelector("#resultCard");
const errorCard = document.querySelector("#errorCard");
const errorText = document.querySelector("#errorText");
const audioPlayer = document.querySelector("#audioPlayer");
const downloadLink = document.querySelector("#downloadLink");
const modelState = document.querySelector("#modelState");
const modelStateText = document.querySelector("#modelStateText");

let voices = [];
let statusTimer;
let previewTimer;
let pollTimer;
let currentJobId = null;

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(seconds) {
  const rounded = Math.max(0, Math.round(Number(seconds) || 0));
  if (rounded < 60) return `${rounded} 秒`;
  const minutes = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return remaining ? `${minutes} 分 ${remaining} 秒` : `${minutes} 分钟`;
}

function updateFile(file) {
  if (!file) {
    dropzone.classList.remove("has-file");
    fileTitle.textContent = "拖入录音，或点击选择";
    fileMeta.textContent = "WAV、M4A、MP3、FLAC · 最大 40 MB";
    return;
  }
  dropzone.classList.add("has-file");
  fileTitle.textContent = file.name;
  fileMeta.textContent = `${formatBytes(file.size)} · 已留在本机`;
  if (!voiceName.value.trim()) {
    voiceName.value = file.name.replace(/\.[^.]+$/, "");
  }
}

audioInput.addEventListener("change", () => updateFile(audioInput.files[0]));

for (const eventName of ["dragenter", "dragover"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("is-dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragging");
  });
}

dropzone.addEventListener("drop", (event) => {
  const files = event.dataTransfer.files;
  if (!files.length) return;
  const transfer = new DataTransfer();
  transfer.items.add(files[0]);
  audioInput.files = transfer.files;
  updateFile(files[0]);
});

function selectedVoice() {
  return voices.find((voice) => voice.id === voiceSelect.value) || null;
}

function applyVoiceMode() {
  const voice = selectedVoice();
  const usesSavedVoice = Boolean(voice);
  uploadVoiceFields.hidden = usesSavedVoice;
  savedVoiceCard.hidden = !usesSavedVoice;
  deleteVoiceButton.hidden = !usesSavedVoice;
  audioInput.required = !usesSavedVoice;
  referenceText.required = !usesSavedVoice;
  audioInput.disabled = usesSavedVoice;
  referenceText.disabled = usesSavedVoice;
  window.localStorage.setItem("voiceCloneSelectedVoice", voiceSelect.value);

  if (voice) {
    savedVoiceName.textContent = voice.name;
    savedVoiceMeta.textContent = `${voice.duration_seconds.toFixed(1)} 秒参考录音 · ${voice.original_filename}`;
    savedVoiceTranscript.textContent = voice.transcript_preview;
  }
}

async function loadVoices(preferredId = "") {
  const response = await fetch("/api/voices", { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response));
  const payload = await response.json();
  voices = payload.voices;
  const previous = preferredId
    || voiceSelect.value
    || window.localStorage.getItem("voiceCloneSelectedVoice")
    || "";
  voiceSelect.replaceChildren(new Option("本次上传新录音", ""));
  for (const voice of voices) {
    voiceSelect.add(new Option(`${voice.name} · ${voice.duration_seconds.toFixed(1)} 秒`, voice.id));
  }
  if (previous && voices.some((voice) => voice.id === previous)) {
    voiceSelect.value = previous;
  }
  applyVoiceMode();
}

voiceSelect.addEventListener("change", applyVoiceMode);

saveVoiceButton.addEventListener("click", async () => {
  voiceSaveStatus.textContent = "";
  const file = audioInput.files[0];
  if (!file || !referenceText.value.trim() || !voiceName.value.trim()) {
    voiceSaveStatus.textContent = "请先选择录音，并填写准确文字和音色名称。";
    return;
  }

  const payload = new FormData();
  payload.append("name", voiceName.value);
  payload.append("reference_text", referenceText.value);
  payload.append("reference_audio", file);
  saveVoiceButton.disabled = true;
  saveVoiceButton.textContent = "正在保存";

  try {
    const response = await fetch("/api/voices", { method: "POST", body: payload });
    if (!response.ok) throw new Error(await readError(response));
    const result = await response.json();
    voiceSaveStatus.textContent = `已保存音色「${result.voice.name}」。`;
    await loadVoices(result.voice.id);
  } catch (error) {
    voiceSaveStatus.textContent = error.message;
  } finally {
    saveVoiceButton.disabled = false;
    saveVoiceButton.textContent = "保存音色";
  }
});

deleteVoiceButton.addEventListener("click", async () => {
  const voice = selectedVoice();
  if (!voice) return;
  if (!window.confirm(`确定删除音色「${voice.name}」吗？`)) return;
  try {
    const response = await fetch(`/api/voices/${voice.id}`, { method: "DELETE" });
    if (!response.ok) throw new Error(await readError(response));
    await loadVoices();
  } catch (error) {
    showError(error.message);
  }
});

targetText.addEventListener("input", () => {
  targetCount.textContent = targetText.value.length.toLocaleString("zh-CN");
  window.clearTimeout(previewTimer);
  if (!targetText.value.trim()) {
    segmentEstimate.textContent = "等待输入";
    return;
  }
  segmentEstimate.textContent = "正在估算";
  previewTimer = window.setTimeout(refreshSegmentPreview, 450);
});

async function refreshSegmentPreview() {
  const payload = new FormData();
  payload.append("target_text", targetText.value);
  try {
    const response = await fetch("/api/segments/preview", { method: "POST", body: payload });
    if (!response.ok) throw new Error(await readError(response));
    const preview = await response.json();
    segmentEstimate.textContent = `预计 ${preview.segments} 段，约 ${formatDuration(preview.estimated_duration_seconds)}`;
  } catch (error) {
    segmentEstimate.textContent = error.message;
  }
}

function setModelState(status, detail) {
  modelState.dataset.state = status;
  if (status === "ready") {
    modelStateText.textContent = "模型已就绪";
  } else if (status === "loading") {
    modelStateText.textContent = "正在准备模型";
  } else if (status === "error") {
    modelStateText.textContent = "模型加载失败";
    modelState.title = detail || "";
  } else {
    modelStateText.textContent = "模型等待加载";
  }
}

async function refreshHealth() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const health = await response.json();
    setModelState(health.model_status, health.error);
    if (health.model_status === "ready" || health.model_status === "error") {
      window.clearInterval(statusTimer);
    }
  } catch (error) {
    setModelState("error", error.message);
  }
}

async function readError(response) {
  try {
    const body = await response.json();
    return body.detail || "请求失败。";
  } catch {
    return `请求失败，状态码 ${response.status}。`;
  }
}

function showError(message) {
  errorText.textContent = message;
  errorCard.hidden = false;
  errorCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function resetJobControls() {
  currentJobId = null;
  window.localStorage.removeItem("voiceCloneCurrentJob");
  window.clearTimeout(pollTimer);
  generateButton.disabled = false;
  buttonText.textContent = "开始生成";
  cancelButton.disabled = false;
  cancelButton.textContent = "停止任务";
}

function renderJob(job) {
  const percent = Math.max(0, Math.min(100, Math.round(job.progress * 100)));
  const phaseTitles = {
    queued: "任务已建立",
    preparing: "正在准备参考音色",
    generating: "正在分段生成",
    assembling: "正在拼接完整音频",
    complete: "生成完成",
    cancelled: "任务已停止",
    error: "任务已停止",
  };
  progressTitle.textContent = phaseTitles[job.phase] || "正在生成";
  progressText.textContent = job.message;
  progressPercent.textContent = `${percent}%`;
  progressSegments.textContent = job.segment_total
    ? `已完成 ${job.segments_completed} / ${job.segment_total} 段`
    : "正在计算分段";
  currentSegmentText.textContent = job.current_text || "";
  progressFill.style.width = `${percent}%`;
  progressTrack.setAttribute("aria-valuenow", percent.toString());
}

function showResult(result) {
  const cacheBuster = `?v=${Date.now()}`;
  audioPlayer.src = result.audio_url + cacheBuster;
  downloadLink.href = result.audio_url;
  downloadLink.download = result.filename;
  document.querySelector("#durationMetric").textContent = formatDuration(result.audio_duration_seconds);
  document.querySelector("#segmentMetric").textContent = `${result.segment_count} 段`;
  document.querySelector("#timeMetric").textContent = formatDuration(result.generation_seconds);
  document.querySelector("#memoryMetric").textContent = `${result.peak_memory_gb.toFixed(1)} GB`;
  resultCard.hidden = false;
  progressCard.hidden = true;
  resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  setModelState("ready");
  resetJobControls();
}

async function pollJob() {
  if (!currentJobId) return;
  try {
    const response = await fetch(`/api/jobs/${currentJobId}`, { cache: "no-store" });
    if (!response.ok) throw new Error(await readError(response));
    const job = await response.json();
    renderJob(job);
    if (job.status === "complete") {
      showResult(job.result);
      return;
    }
    if (job.status === "error" || job.status === "cancelled") {
      progressCard.hidden = true;
      showError(job.error || job.message);
      resetJobControls();
      return;
    }
    pollTimer = window.setTimeout(pollJob, 750);
  } catch (error) {
    progressCard.hidden = true;
    showError(error.message);
    resetJobControls();
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (currentJobId) return;
  errorCard.hidden = true;
  resultCard.hidden = true;
  progressCard.hidden = false;
  generateButton.disabled = true;
  buttonText.textContent = "生成进行中";

  const payload = new FormData();
  payload.append("target_text", targetText.value);
  payload.append("language", language.value);
  payload.append("voice_id", voiceSelect.value);
  if (!voiceSelect.value) {
    const file = audioInput.files[0];
    if (file) payload.append("reference_audio", file);
    payload.append("reference_text", referenceText.value);
  }

  renderJob({
    phase: "queued",
    message: "正在执行无丢字语义分段",
    progress: 0,
    segment_total: 0,
    segments_completed: 0,
    current_text: "",
  });

  try {
    const response = await fetch("/api/jobs", { method: "POST", body: payload });
    if (!response.ok) throw new Error(await readError(response));
    const job = await response.json();
    currentJobId = job.job_id;
    window.localStorage.setItem("voiceCloneCurrentJob", currentJobId);
    renderJob(job);
    pollTimer = window.setTimeout(pollJob, 500);
  } catch (error) {
    progressCard.hidden = true;
    showError(error.message);
    resetJobControls();
  }
});

cancelButton.addEventListener("click", async () => {
  if (!currentJobId) return;
  cancelButton.disabled = true;
  cancelButton.textContent = "正在停止";
  try {
    const response = await fetch(`/api/jobs/${currentJobId}/cancel`, { method: "POST" });
    if (!response.ok) throw new Error(await readError(response));
    renderJob(await response.json());
  } catch (error) {
    showError(error.message);
  }
});

async function restoreJob() {
  const savedJobId = window.localStorage.getItem("voiceCloneCurrentJob");
  if (!savedJobId) return;
  try {
    const response = await fetch(`/api/jobs/${savedJobId}`, { cache: "no-store" });
    if (!response.ok) throw new Error("任务无法恢复。");
    const job = await response.json();
    currentJobId = savedJobId;
    errorCard.hidden = true;
    progressCard.hidden = false;
    generateButton.disabled = true;
    buttonText.textContent = "生成进行中";
    renderJob(job);
    if (job.status === "complete") {
      showResult(job.result);
    } else if (job.status === "error" || job.status === "cancelled") {
      progressCard.hidden = true;
      showError(job.error || job.message);
      resetJobControls();
    } else {
      pollTimer = window.setTimeout(pollJob, 500);
    }
  } catch {
    window.localStorage.removeItem("voiceCloneCurrentJob");
  }
}

Promise.all([refreshHealth(), loadVoices(), restoreJob()]).catch((error) => {
  showError(error.message);
});
statusTimer = window.setInterval(refreshHealth, 2500);
