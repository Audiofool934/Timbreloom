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
const modeButtons = [...document.querySelectorAll(".mode-button")];
const cloneView = document.querySelector("#cloneView");
const asrView = document.querySelector("#asrView");
const asrForm = document.querySelector("#asrForm");
const asrMedia = document.querySelector("#asrMedia");
const asrDropzone = document.querySelector("#asrDropzone");
const asrFileTitle = document.querySelector("#asrFileTitle");
const asrFileMeta = document.querySelector("#asrFileMeta");
const asrLanguage = document.querySelector("#asrLanguage");
const asrPrompt = document.querySelector("#asrPrompt");
const asrStartButton = document.querySelector("#asrStartButton");
const asrButtonText = document.querySelector("#asrButtonText");
const asrProgressCard = document.querySelector("#asrProgressCard");
const asrProgressTitle = document.querySelector("#asrProgressTitle");
const asrProgressText = document.querySelector("#asrProgressText");
const asrProgressTrack = document.querySelector("#asrProgressTrack");
const asrProgressFill = document.querySelector("#asrProgressFill");
const asrProgressPercent = document.querySelector("#asrProgressPercent");
const asrProgressMeta = document.querySelector("#asrProgressMeta");
const asrCancelButton = document.querySelector("#asrCancelButton");
const refreshTranscriptsButton = document.querySelector("#refreshTranscripts");
const transcriptList = document.querySelector("#transcriptList");
const transcriptEditor = document.querySelector("#transcriptEditor");
const transcriptTitle = document.querySelector("#transcriptTitle");
const transcriptMeta = document.querySelector("#transcriptMeta");
const transcriptAudio = document.querySelector("#transcriptAudio");
const exportTxt = document.querySelector("#exportTxt");
const exportSrt = document.querySelector("#exportSrt");
const exportVtt = document.querySelector("#exportVtt");
const selectionCount = document.querySelector("#selectionCount");
const selectionDuration = document.querySelector("#selectionDuration");
const saveTranscriptButton = document.querySelector("#saveTranscriptButton");
const transcriptVoiceName = document.querySelector("#transcriptVoiceName");
const createVoiceFromTranscript = document.querySelector("#createVoiceFromTranscript");
const transcriptVoiceStatus = document.querySelector("#transcriptVoiceStatus");
const geminiStatus = document.querySelector("#geminiStatus");
const geminiPunctuation = document.querySelector("#geminiPunctuation");
const geminiCleanup = document.querySelector("#geminiCleanup");
const geminiTranslate = document.querySelector("#geminiTranslate");
const geminiTargetLanguage = document.querySelector("#geminiTargetLanguage");
const geminiActionStatus = document.querySelector("#geminiActionStatus");
const selectAllSegments = document.querySelector("#selectAllSegments");
const transcriptSegments = document.querySelector("#transcriptSegments");

let voices = [];
let statusTimer;
let previewTimer;
let pollTimer;
let currentJobId = null;
let asrPollTimer;
let currentAsrJobId = null;
let transcripts = [];
let currentTranscript = null;
let geminiConfigured = false;
const selectedTranscriptSegments = new Set();
const dirtyTranscriptSegments = new Set();
const segmentRows = new Map();

function switchView(view) {
  const isAsr = view === "asr";
  cloneView.hidden = isAsr;
  asrView.hidden = !isAsr;
  for (const button of modeButtons) {
    const active = button.dataset.view === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active.toString());
  }
  window.localStorage.setItem("timbreloomView", view);
}

for (const button of modeButtons) {
  button.addEventListener("click", () => switchView(button.dataset.view));
}

switchView(window.localStorage.getItem("timbreloomView") === "asr" ? "asr" : "clone");

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

function setModelState(status, detail, label = "") {
  modelState.dataset.state = status;
  if (status === "ready") {
    modelStateText.textContent = label || "本地模型已就绪";
  } else if (status === "loading") {
    modelStateText.textContent = label || "正在准备本地模型";
  } else if (status === "error") {
    modelStateText.textContent = label || "模型加载失败";
    modelState.title = detail || "";
  } else {
    modelStateText.textContent = label || "本地模型按需加载";
  }
}

async function refreshHealth() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const health = await response.json();
    if (health.active_local_workload === "asr") {
      setModelState("loading", "", "Whisper 正在本地转录");
    } else if (health.active_local_workload === "tts") {
      setModelState("loading", "", "Qwen 正在生成音频");
    } else {
      setModelState(health.model_status, health.error);
    }
    updateProviders(health.providers || []);
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

function updateProviders(providerList) {
  const gemini = providerList.find((provider) => provider.id === "gemini-text");
  geminiConfigured = Boolean(gemini && gemini.configured);
  geminiStatus.textContent = geminiConfigured ? "已配置" : "未配置";
  geminiStatus.dataset.state = geminiConfigured ? "ready" : "missing";
  updateTranscriptSelection();
}

async function loadProviders() {
  try {
    const response = await fetch("/api/providers", { cache: "no-store" });
    if (!response.ok) throw new Error(await readError(response));
    const payload = await response.json();
    updateProviders(payload.providers || []);
  } catch (error) {
    geminiStatus.textContent = "检查失败";
    geminiStatus.dataset.state = "error";
  }
}

function updateAsrFile(file) {
  if (!file) {
    asrDropzone.classList.remove("has-file");
    asrFileTitle.textContent = "拖入音频或视频";
    asrFileMeta.textContent = "本地处理 · 不上传云端";
    return;
  }
  asrDropzone.classList.add("has-file");
  asrFileTitle.textContent = file.name;
  asrFileMeta.textContent = `${formatBytes(file.size)} · 等待本地转录`;
}

asrMedia.addEventListener("change", () => updateAsrFile(asrMedia.files[0]));

for (const eventName of ["dragenter", "dragover"]) {
  asrDropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    asrDropzone.classList.add("is-dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  asrDropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    asrDropzone.classList.remove("is-dragging");
  });
}

asrDropzone.addEventListener("drop", (event) => {
  const files = event.dataTransfer.files;
  if (!files.length) return;
  const transfer = new DataTransfer();
  transfer.items.add(files[0]);
  asrMedia.files = transfer.files;
  updateAsrFile(files[0]);
});

function renderAsrJob(job) {
  const percent = Math.max(0, Math.min(100, Math.round(job.progress * 100)));
  const titles = {
    queued: "任务已建立",
    probing: "正在检查媒体",
    preparing: "正在准备音频",
    transcribing: "Whisper 正在转录",
    saving: "正在保存时间戳",
    complete: "转录完成",
    cancelled: "任务已停止",
    error: "任务没有完成",
  };
  asrProgressTitle.textContent = titles[job.phase] || "正在本地转录";
  asrProgressText.textContent = job.message;
  asrProgressPercent.textContent = `${percent}%`;
  asrProgressFill.style.width = `${percent}%`;
  asrProgressTrack.setAttribute("aria-valuenow", percent.toString());
  asrProgressMeta.textContent = job.duration_seconds
    ? `${job.source_filename} · ${formatDuration(job.duration_seconds)}`
    : job.source_filename || "等待媒体检查";
}

function resetAsrControls() {
  currentAsrJobId = null;
  window.localStorage.removeItem("timbreloomCurrentAsrJob");
  window.clearTimeout(asrPollTimer);
  asrStartButton.disabled = false;
  asrButtonText.textContent = "开始本地转录";
  asrCancelButton.disabled = false;
  asrCancelButton.textContent = "停止任务";
}

async function pollAsrJob() {
  if (!currentAsrJobId) return;
  try {
    const response = await fetch(`/api/asr/jobs/${currentAsrJobId}`, { cache: "no-store" });
    if (!response.ok) throw new Error(await readError(response));
    const job = await response.json();
    renderAsrJob(job);
    if (job.status === "complete") {
      asrProgressCard.hidden = true;
      const transcriptId = job.result.id;
      resetAsrControls();
      await loadTranscripts(transcriptId);
      await loadTranscript(transcriptId, true);
      return;
    }
    if (job.status === "error" || job.status === "cancelled") {
      asrProgressCard.hidden = true;
      showError(job.error || job.message);
      resetAsrControls();
      return;
    }
    asrPollTimer = window.setTimeout(pollAsrJob, 900);
  } catch (error) {
    asrProgressCard.hidden = true;
    showError(error.message);
    resetAsrControls();
  }
}

asrForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (currentAsrJobId) return;
  const file = asrMedia.files[0];
  if (!file) {
    showError("请选择需要转录的音频或视频。");
    return;
  }
  errorCard.hidden = true;
  asrProgressCard.hidden = false;
  asrStartButton.disabled = true;
  asrButtonText.textContent = "转录进行中";

  const payload = new FormData();
  payload.append("media", file);
  payload.append("language", asrLanguage.value);
  payload.append("initial_prompt", asrPrompt.value);
  renderAsrJob({
    phase: "queued",
    message: "正在把媒体保存在本地项目中",
    progress: 0,
    source_filename: file.name,
    duration_seconds: 0,
  });

  try {
    const response = await fetch("/api/asr/jobs", { method: "POST", body: payload });
    if (!response.ok) throw new Error(await readError(response));
    const job = await response.json();
    currentAsrJobId = job.job_id;
    window.localStorage.setItem("timbreloomCurrentAsrJob", currentAsrJobId);
    renderAsrJob(job);
    asrPollTimer = window.setTimeout(pollAsrJob, 500);
  } catch (error) {
    asrProgressCard.hidden = true;
    showError(error.message);
    resetAsrControls();
  }
});

asrCancelButton.addEventListener("click", async () => {
  if (!currentAsrJobId) return;
  asrCancelButton.disabled = true;
  asrCancelButton.textContent = "正在停止";
  try {
    const response = await fetch(`/api/asr/jobs/${currentAsrJobId}/cancel`, { method: "POST" });
    if (!response.ok) throw new Error(await readError(response));
    renderAsrJob(await response.json());
  } catch (error) {
    showError(error.message);
  }
});

async function restoreAsrJob() {
  const savedJobId = window.localStorage.getItem("timbreloomCurrentAsrJob");
  if (!savedJobId) return;
  try {
    const response = await fetch(`/api/asr/jobs/${savedJobId}`, { cache: "no-store" });
    if (!response.ok) throw new Error("转录任务无法恢复。");
    const job = await response.json();
    currentAsrJobId = savedJobId;
    asrProgressCard.hidden = false;
    asrStartButton.disabled = true;
    asrButtonText.textContent = "转录进行中";
    renderAsrJob(job);
    if (job.status === "complete") {
      asrProgressCard.hidden = true;
      resetAsrControls();
      await loadTranscripts(job.result.id);
      await loadTranscript(job.result.id);
    } else if (job.status === "error" || job.status === "cancelled") {
      asrProgressCard.hidden = true;
      resetAsrControls();
    } else {
      asrPollTimer = window.setTimeout(pollAsrJob, 500);
    }
  } catch {
    window.localStorage.removeItem("timbreloomCurrentAsrJob");
  }
}

function formatTranscriptDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function renderTranscriptList(preferredId = "") {
  transcriptList.replaceChildren();
  if (!transcripts.length) {
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = "还没有转录记录。";
    transcriptList.append(empty);
    return;
  }

  for (const transcript of transcripts) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "transcript-list-item";
    if (transcript.id === (preferredId || currentTranscript?.id)) {
      button.classList.add("is-active");
    }
    const title = document.createElement("strong");
    title.textContent = transcript.title || transcript.source_filename;
    const meta = document.createElement("span");
    meta.textContent = `${formatDuration(transcript.duration_seconds)} · ${transcript.segment_count} 段`;
    const date = document.createElement("small");
    date.textContent = formatTranscriptDate(transcript.created_at);
    button.append(title, meta, date);
    button.addEventListener("click", () => loadTranscript(transcript.id, true));
    transcriptList.append(button);
  }
}

async function loadTranscripts(preferredId = "") {
  const response = await fetch("/api/transcripts", { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response));
  const payload = await response.json();
  transcripts = payload.transcripts || [];
  renderTranscriptList(preferredId);
}

refreshTranscriptsButton.addEventListener("click", async () => {
  try {
    await loadTranscripts(currentTranscript?.id || "");
  } catch (error) {
    showError(error.message);
  }
});

function formatTimecode(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(total / 60);
  const remainder = total - minutes * 60;
  return `${minutes.toString().padStart(2, "0")}:${remainder.toFixed(1).padStart(4, "0")}`;
}

function selectedSegmentsInOrder() {
  if (!currentTranscript) return [];
  return currentTranscript.segments.filter((segment) => selectedTranscriptSegments.has(segment.id));
}

function selectionIsContiguous(selected) {
  if (!currentTranscript || !selected.length) return false;
  const indices = selected.map((segment) => currentTranscript.segments.indexOf(segment));
  return indices.every((index, position) => position === 0 || index === indices[position - 1] + 1);
}

function updateTranscriptSelection() {
  const selected = selectedSegmentsInOrder();
  const total = currentTranscript?.segments.length || 0;
  selectAllSegments.checked = total > 0 && selected.length === total;
  selectAllSegments.indeterminate = selected.length > 0 && selected.length < total;

  if (!selected.length) {
    selectionCount.textContent = "尚未选择片段";
    selectionDuration.textContent = "选择连续的 2 至 30 秒可保存为音色";
  } else {
    const contiguous = selectionIsContiguous(selected);
    const duration = selected[selected.length - 1].end - selected[0].start;
    selectionCount.textContent = `已选择 ${selected.length} 段`;
    selectionDuration.textContent = contiguous
      ? `${formatTimecode(selected[0].start)} 至 ${formatTimecode(selected[selected.length - 1].end)} · ${duration.toFixed(1)} 秒`
      : "所选片段不连续，不能保存为音色";
  }

  const contiguous = selectionIsContiguous(selected);
  const duration = selected.length ? selected[selected.length - 1].end - selected[0].start : 0;
  const validVoiceRange = contiguous && duration >= 2 && duration <= 30;
  createVoiceFromTranscript.disabled = !validVoiceRange || !transcriptVoiceName.value.trim();

  const geminiReady = geminiConfigured && selected.length === 1;
  geminiPunctuation.disabled = !geminiReady;
  geminiCleanup.disabled = !geminiReady;
  geminiTranslate.disabled = !geminiReady;
}

function markSegmentDirty(segmentId) {
  dirtyTranscriptSegments.add(segmentId);
  saveTranscriptButton.disabled = false;
  saveTranscriptButton.textContent = `保存 ${dirtyTranscriptSegments.size} 处修改`;
}

function renderTranscript(transcript) {
  currentTranscript = transcript;
  selectedTranscriptSegments.clear();
  dirtyTranscriptSegments.clear();
  segmentRows.clear();
  transcriptSegments.replaceChildren();
  transcriptEditor.hidden = false;
  transcriptTitle.textContent = transcript.title || transcript.source_filename;
  transcriptMeta.textContent = `${formatDuration(transcript.duration_seconds)} · ${transcript.language.toUpperCase()} · ${transcript.segments.length} 段 · ${transcript.model}`;
  transcriptAudio.src = `${transcript.audio_url}?v=${Date.now()}`;
  exportTxt.href = transcript.export_urls.txt;
  exportSrt.href = transcript.export_urls.srt;
  exportVtt.href = transcript.export_urls.vtt;
  saveTranscriptButton.disabled = true;
  saveTranscriptButton.textContent = "保存文字修改";
  transcriptVoiceStatus.textContent = "";
  geminiActionStatus.textContent = "";

  for (const segment of transcript.segments) {
    const row = document.createElement("article");
    row.className = "transcript-segment";
    row.dataset.segmentId = segment.id;

    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "segment-check";
    check.setAttribute("aria-label", `选择 ${formatTimecode(segment.start)} 的片段`);
    check.addEventListener("change", () => {
      if (check.checked) selectedTranscriptSegments.add(segment.id);
      else selectedTranscriptSegments.delete(segment.id);
      row.classList.toggle("is-selected", check.checked);
      updateTranscriptSelection();
    });

    const timeButton = document.createElement("button");
    timeButton.type = "button";
    timeButton.className = "segment-time";
    timeButton.textContent = `${formatTimecode(segment.start)}\n${formatTimecode(segment.end)}`;
    timeButton.addEventListener("click", () => {
      transcriptAudio.currentTime = segment.start;
      transcriptAudio.play().catch(() => {});
    });

    const textarea = document.createElement("textarea");
    textarea.rows = 3;
    textarea.value = segment.text;
    textarea.setAttribute("aria-label", `${formatTimecode(segment.start)} 的转录文字`);
    textarea.addEventListener("input", () => {
      segment.text = textarea.value;
      markSegmentDirty(segment.id);
    });

    row.append(check, timeButton, textarea);
    transcriptSegments.append(row);
    segmentRows.set(segment.id, { row, check, textarea });
  }
  renderTranscriptList(transcript.id);
  updateTranscriptSelection();
}

async function loadTranscript(transcriptId, shouldScroll = false) {
  try {
    const response = await fetch(`/api/transcripts/${transcriptId}`, { cache: "no-store" });
    if (!response.ok) throw new Error(await readError(response));
    renderTranscript(await response.json());
    if (shouldScroll) {
      transcriptEditor.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (error) {
    showError(error.message);
  }
}

selectAllSegments.addEventListener("change", () => {
  if (!currentTranscript) return;
  selectedTranscriptSegments.clear();
  for (const segment of currentTranscript.segments) {
    const row = segmentRows.get(segment.id);
    row.check.checked = selectAllSegments.checked;
    row.row.classList.toggle("is-selected", selectAllSegments.checked);
    if (selectAllSegments.checked) selectedTranscriptSegments.add(segment.id);
  }
  updateTranscriptSelection();
});

transcriptVoiceName.addEventListener("input", updateTranscriptSelection);

async function saveTranscriptChanges() {
  if (!currentTranscript || !dirtyTranscriptSegments.size) return true;
  const updates = [...dirtyTranscriptSegments].map((segmentId) => ({
    id: segmentId,
    text: segmentRows.get(segmentId).textarea.value,
  }));
  saveTranscriptButton.disabled = true;
  saveTranscriptButton.textContent = "正在保存";
  try {
    const response = await fetch(`/api/transcripts/${currentTranscript.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segments: updates }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const payload = await response.json();
    currentTranscript = { ...currentTranscript, ...payload.transcript };
    dirtyTranscriptSegments.clear();
    saveTranscriptButton.textContent = "文字已保存";
    window.setTimeout(() => {
      if (!dirtyTranscriptSegments.size) saveTranscriptButton.textContent = "保存文字修改";
    }, 1400);
    return true;
  } catch (error) {
    showError(error.message);
    saveTranscriptButton.disabled = false;
    saveTranscriptButton.textContent = `保存 ${dirtyTranscriptSegments.size} 处修改`;
    return false;
  }
}

saveTranscriptButton.addEventListener("click", saveTranscriptChanges);

createVoiceFromTranscript.addEventListener("click", async () => {
  if (!currentTranscript) return;
  const selected = selectedSegmentsInOrder();
  transcriptVoiceStatus.textContent = "";
  createVoiceFromTranscript.disabled = true;
  createVoiceFromTranscript.textContent = "正在保存音色";
  try {
    if (!(await saveTranscriptChanges())) return;
    const payload = new FormData();
    payload.append("name", transcriptVoiceName.value);
    payload.append("segment_ids", JSON.stringify(selected.map((segment) => segment.id)));
    const response = await fetch(`/api/transcripts/${currentTranscript.id}/voices`, {
      method: "POST",
      body: payload,
    });
    if (!response.ok) throw new Error(await readError(response));
    const result = await response.json();
    transcriptVoiceStatus.textContent = `已保存音色「${result.voice.name}」。`;
    await loadVoices(result.voice.id);
  } catch (error) {
    transcriptVoiceStatus.textContent = error.message;
  } finally {
    createVoiceFromTranscript.textContent = "从所选片段保存音色";
    updateTranscriptSelection();
  }
});

async function runGemini(task) {
  if (!currentTranscript) return;
  const selected = selectedSegmentsInOrder();
  if (selected.length !== 1) return;
  const actionNames = {
    punctuation: "补充标点",
    cleanup: "整理断句",
    translate: `翻译为${geminiTargetLanguage.value}`,
  };
  const confirmed = window.confirm(
    `将当前选中的一段文字发送到 Gemini 进行${actionNames[task]}。不会上传音频，云端调用可能产生费用。是否继续？`,
  );
  if (!confirmed) return;
  if (!(await saveTranscriptChanges())) return;

  const buttons = [geminiPunctuation, geminiCleanup, geminiTranslate];
  buttons.forEach((button) => { button.disabled = true; });
  geminiActionStatus.textContent = `正在使用 Gemini ${actionNames[task]}…`;
  try {
    const response = await fetch(`/api/transcripts/${currentTranscript.id}/gemini`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        segment_id: selected[0].id,
        task,
        target_language: task === "translate" ? geminiTargetLanguage.value : "",
        confirm_cloud: true,
      }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const result = await response.json();
    const row = segmentRows.get(result.segment_id);
    row.textarea.value = result.text;
    selected[0].text = result.text;
    markSegmentDirty(result.segment_id);
    geminiActionStatus.textContent = "Gemini 结果已放入编辑框，尚未保存。";
  } catch (error) {
    geminiActionStatus.textContent = error.message;
  } finally {
    updateTranscriptSelection();
  }
}

geminiPunctuation.addEventListener("click", () => runGemini("punctuation"));
geminiCleanup.addEventListener("click", () => runGemini("cleanup"));
geminiTranslate.addEventListener("click", () => runGemini("translate"));

Promise.all([
  refreshHealth(),
  loadProviders(),
  loadVoices(),
  restoreJob(),
  loadTranscripts(),
  restoreAsrJob(),
]).catch((error) => {
  showError(error.message);
});
statusTimer = window.setInterval(refreshHealth, 2500);
