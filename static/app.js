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
const dubView = document.querySelector("#dubView");
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
const createDubForm = document.querySelector("#createDubForm");
const dubTranscriptSelect = document.querySelector("#dubTranscriptSelect");
const dubTitleInput = document.querySelector("#dubTitleInput");
const dubDefaultVoice = document.querySelector("#dubDefaultVoice");
const dubTargetLanguage = document.querySelector("#dubTargetLanguage");
const createDubButton = document.querySelector("#createDubButton");
const refreshDubProjects = document.querySelector("#refreshDubProjects");
const dubProjectList = document.querySelector("#dubProjectList");
const dubEditor = document.querySelector("#dubEditor");
const dubProjectTitleInput = document.querySelector("#dubProjectTitleInput");
const dubProjectLanguage = document.querySelector("#dubProjectLanguage");
const dubProjectMeta = document.querySelector("#dubProjectMeta");
const dubSourceVideo = document.querySelector("#dubSourceVideo");
const dubSourceAudio = document.querySelector("#dubSourceAudio");
const dubSaveButton = document.querySelector("#dubSaveButton");
const dubExportButton = document.querySelector("#dubExportButton");
const dubExportButtonText = document.querySelector("#dubExportButtonText");
const dubOriginalAudioField = document.querySelector("#dubOriginalAudioField");
const dubOriginalAudioGain = document.querySelector("#dubOriginalAudioGain");
const dubTimelineTrack = document.querySelector("#dubTimelineTrack");
const dubTimelineSummary = document.querySelector("#dubTimelineSummary");
const dubSelectionCount = document.querySelector("#dubSelectionCount");
const dubEditorStatus = document.querySelector("#dubEditorStatus");
const dubGenerateSelected = document.querySelector("#dubGenerateSelected");
const dubRetryFailed = document.querySelector("#dubRetryFailed");
const dubGenerateAll = document.querySelector("#dubGenerateAll");
const dubProgressCard = document.querySelector("#dubProgressCard");
const dubProgressTitle = document.querySelector("#dubProgressTitle");
const dubProgressText = document.querySelector("#dubProgressText");
const dubProgressTrack = document.querySelector("#dubProgressTrack");
const dubProgressFill = document.querySelector("#dubProgressFill");
const dubProgressPercent = document.querySelector("#dubProgressPercent");
const dubProgressMeta = document.querySelector("#dubProgressMeta");
const dubCurrentText = document.querySelector("#dubCurrentText");
const dubCancelButton = document.querySelector("#dubCancelButton");
const dubExportResult = document.querySelector("#dubExportResult");
const dubExportSummary = document.querySelector("#dubExportSummary");
const dubExportMp4 = document.querySelector("#dubExportMp4");
const dubExportWav = document.querySelector("#dubExportWav");
const dubExportSrt = document.querySelector("#dubExportSrt");
const dubGeminiStatus = document.querySelector("#dubGeminiStatus");
const dubGeminiTargetLanguage = document.querySelector("#dubGeminiTargetLanguage");
const dubGeminiTranslate = document.querySelector("#dubGeminiTranslate");
const dubSelectAll = document.querySelector("#dubSelectAll");
const dubSegments = document.querySelector("#dubSegments");

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
let dubProjects = [];
let currentDubProject = null;
let currentDubJobId = null;
let dubPollTimer;
let dubProjectDirty = false;
const selectedDubSegments = new Set();
const dirtyDubSegments = new Set();
const dubSegmentRows = new Map();
const dubPreviewAudio = new Audio();

function switchView(view) {
  cloneView.hidden = view !== "clone";
  asrView.hidden = view !== "asr";
  dubView.hidden = view !== "dub";
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

const savedView = window.localStorage.getItem("timbreloomView");
switchView(["clone", "asr", "dub"].includes(savedView) ? savedView : "clone");

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
  populateDubVoiceOptions();
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
  dubGeminiStatus.textContent = geminiConfigured ? "已配置" : "未配置";
  dubGeminiStatus.dataset.state = geminiConfigured ? "ready" : "missing";
  updateTranscriptSelection();
  updateDubControls();
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
    dubGeminiStatus.textContent = "检查失败";
    dubGeminiStatus.dataset.state = "error";
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
  populateDubTranscriptOptions();
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

function populateDubVoiceOptions() {
  const previous = dubDefaultVoice.value;
  dubDefaultVoice.replaceChildren(new Option("选择已保存音色", ""));
  for (const voice of voices) {
    dubDefaultVoice.add(new Option(voice.name, voice.id));
  }
  if (previous && voices.some((voice) => voice.id === previous)) {
    dubDefaultVoice.value = previous;
  }
}

function populateDubTranscriptOptions() {
  const previous = dubTranscriptSelect.value;
  dubTranscriptSelect.replaceChildren(new Option("选择转录记录", ""));
  for (const transcript of transcripts) {
    dubTranscriptSelect.add(
      new Option(
        `${transcript.title || transcript.source_filename} · ${transcript.segment_count} 段`,
        transcript.id,
      ),
    );
  }
  if (previous && transcripts.some((transcript) => transcript.id === previous)) {
    dubTranscriptSelect.value = previous;
  }
}

function renderDubProjectList(preferredId = "") {
  dubProjectList.replaceChildren();
  if (!dubProjects.length) {
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = transcripts.length
      ? "还没有配音项目。"
      : "先在本地转录中建立一份带时间戳的转录。";
    dubProjectList.append(empty);
    return;
  }

  const activeId = preferredId || currentDubProject?.id || "";
  for (const project of dubProjects) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "transcript-list-item";
    button.classList.toggle("is-active", project.id === activeId);
    const title = document.createElement("strong");
    title.textContent = project.title;
    const meta = document.createElement("span");
    meta.textContent = `${project.source_has_video ? "视频" : "音频"} · ${project.ready_count} / ${project.segment_count} 段已生成`;
    const state = document.createElement("small");
    state.textContent = project.failed_count
      ? `${project.failed_count} 段失败 · ${formatTranscriptDate(project.updated_at)}`
      : formatTranscriptDate(project.updated_at);
    button.append(title, meta, state);
    button.addEventListener("click", () => loadDubProject(project.id, true));
    dubProjectList.append(button);
  }
}

async function loadDubProjects(preferredId = "") {
  const response = await fetch("/api/dub/projects", { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response));
  const payload = await response.json();
  dubProjects = payload.projects || [];
  const storedId = window.localStorage.getItem("timbreloomDubProject") || "";
  const candidate = preferredId || currentDubProject?.id || storedId;
  const selectedId = dubProjects.some((project) => project.id === candidate)
    ? candidate
    : dubProjects[0]?.id || "";
  renderDubProjectList(selectedId);
  if (selectedId && currentDubProject?.id !== selectedId) {
    await loadDubProject(selectedId);
  } else if (!selectedId) {
    currentDubProject = null;
    dubEditor.hidden = true;
  }
}

function dubStatusCopy(segment) {
  const render = segment.render;
  const labels = {
    missing: "未生成",
    stale: "需要更新",
    rendering: "生成中",
    ready: "可试听",
    error: "生成失败",
  };
  let detail = labels[render.status] || render.status;
  if (render.status === "ready") {
    detail = render.overflow_seconds > 0.05
      ? `超出原时长 ${render.overflow_seconds.toFixed(1)} 秒`
      : `${render.duration_seconds.toFixed(1)} 秒 · 时间槽内`;
  } else if (render.status === "error" && render.error) {
    detail = render.error;
  }
  return { label: labels[render.status] || render.status, detail };
}

function markDubDirty(segmentId = "") {
  if (segmentId) dirtyDubSegments.add(segmentId);
  else dubProjectDirty = true;
  updateDubControls();
}

function updateDubControls() {
  const project = currentDubProject;
  const active = Boolean(currentDubJobId);
  const selectedCount = selectedDubSegments.size;
  const dirtyCount = dirtyDubSegments.size + (dubProjectDirty ? 1 : 0);
  const segments = project?.segments || [];
  const failedCount = segments.filter((segment) => segment.render.status === "error").length;
  const allReady = segments.length > 0
    && segments.every((segment) => segment.render.status === "ready");

  dubSelectionCount.textContent = selectedCount
    ? `已选择 ${selectedCount} / ${segments.length} 段`
    : "尚未选择片段";
  if (active) {
    dubEditorStatus.textContent = "配音生成正在运行，进度会持久保存";
  } else if (dirtyCount) {
    dubEditorStatus.textContent = `${dirtyCount} 处修改尚未保存`;
  } else if (failedCount) {
    dubEditorStatus.textContent = `${failedCount} 个失败片段可以独立重试`;
  } else {
    const readyCount = segments.filter((segment) => segment.render.status === "ready").length;
    dubEditorStatus.textContent = `${readyCount} / ${segments.length} 段可以使用缓存`;
  }

  dubSaveButton.disabled = !project || !dirtyCount || active;
  dubSaveButton.textContent = dirtyCount ? `保存 ${dirtyCount} 处修改` : "保存修改";
  dubGenerateSelected.disabled = !project || !selectedCount || active;
  dubGenerateAll.disabled = !project || active;
  dubRetryFailed.disabled = !project || !failedCount || active;
  dubExportButton.disabled = !project || !allReady || Boolean(dirtyCount) || active;
  dubOriginalAudioGain.disabled = active;
  dubGeminiTranslate.disabled = !project || selectedCount !== 1 || !geminiConfigured || active;
  dubSelectAll.checked = segments.length > 0 && selectedCount === segments.length;
  dubSelectAll.indeterminate = selectedCount > 0 && selectedCount < segments.length;
  for (const row of dubSegmentRows.values()) {
    row.regenerate.disabled = active;
  }
}

function activeDubSourcePlayer() {
  return currentDubProject?.source_has_video && !dubSourceVideo.hidden
    ? dubSourceVideo
    : dubSourceAudio;
}

function seekDubSource(seconds) {
  const player = activeDubSourcePlayer();
  player.currentTime = seconds;
  player.play().catch(() => {});
}

function renderDubTimeline(project) {
  dubTimelineTrack.replaceChildren();
  const duration = Math.max(0.001, Number(project.duration_seconds) || 0);
  const readyCount = project.segments.filter((segment) => segment.render.status === "ready").length;
  const overlapCount = project.segments.filter(
    (segment) => segment.render.overlap_next_seconds > 0.05,
  ).length;
  dubTimelineSummary.textContent = overlapCount
    ? `${readyCount} / ${project.segments.length} 已生成 · ${overlapCount} 处重叠`
    : `${readyCount} / ${project.segments.length} 已生成 · ${formatDuration(duration)}`;

  for (const segment of project.segments) {
    const left = Math.min(100, Math.max(0, (segment.start / duration) * 100));
    const slotDuration = Math.max(0, segment.end - segment.start);
    const slotWidth = Math.max(0.35, Math.min(100 - left, (slotDuration / duration) * 100));
    const slot = document.createElement("button");
    slot.type = "button";
    slot.className = "dub-timeline-slot";
    slot.style.left = `${left}%`;
    slot.style.width = `${slotWidth}%`;
    slot.dataset.status = segment.render.status;
    slot.setAttribute(
      "aria-label",
      `${formatTimecode(segment.start)} 到 ${formatTimecode(segment.end)}，${dubStatusCopy(segment).detail}`,
    );
    slot.title = `${formatTimecode(segment.start)} · ${dubStatusCopy(segment).detail}`;
    slot.addEventListener("click", () => seekDubSource(segment.start));
    dubTimelineTrack.append(slot);

    if (segment.render.duration_seconds > 0) {
      const renderWidth = Math.max(
        0.35,
        Math.min(100 - left, (segment.render.duration_seconds / duration) * 100),
      );
      const rendered = document.createElement("span");
      rendered.className = `dub-timeline-render is-${segment.render.status}`;
      if (segment.render.overlap_next_seconds > 0.05) rendered.classList.add("has-overlap");
      rendered.style.left = `${left}%`;
      rendered.style.width = `${renderWidth}%`;
      dubTimelineTrack.append(rendered);
    }
  }
}

function dubExportSummaryCopy(result) {
  const output = result.mp4_url ? "MP4、WAV 和 SRT" : "WAV 和 SRT";
  const warnings = result.warning_count
    ? `，${result.warning_count} 段超过原时间槽，完整语音未截断`
    : "";
  if (result.mp4_url) {
    const gain = Math.round((result.original_audio_gain || 0) * 100);
    const mix = gain ? `，原声保留 ${gain}%` : "，原声已静音";
    return `${output} 已导出${mix}${warnings}。`;
  }
  return `${output} 已按原时间线导出${warnings}。`;
}

function startDubPolling(job) {
  currentDubJobId = job.job_id;
  window.localStorage.setItem(
    "timbreloomCurrentDubJob",
    JSON.stringify({ projectId: job.project_id, jobId: job.job_id }),
  );
  dubProgressCard.hidden = false;
  renderDubJob(job);
  window.clearTimeout(dubPollTimer);
  dubPollTimer = window.setTimeout(pollDubJob, 500);
  updateDubControls();
}

function renderDubProject(project) {
  currentDubProject = project;
  window.localStorage.setItem("timbreloomDubProject", project.id);
  selectedDubSegments.clear();
  dirtyDubSegments.clear();
  dubProjectDirty = false;
  dubSegmentRows.clear();
  dubSegments.replaceChildren();
  dubEditor.hidden = false;
  dubProjectTitleInput.value = project.title;
  dubProjectLanguage.value = project.target_language;
  const mediaKind = project.source_has_video ? "VIDEO" : "AUDIO";
  dubProjectMeta.textContent = `${mediaKind} · ${formatDuration(project.duration_seconds)} · ${project.source_language.toUpperCase()} · ${project.segments.length} 段 · ${project.source_filename}`;
  dubOriginalAudioField.hidden = !project.source_has_video;
  dubExportButtonText.textContent = project.source_has_video
    ? "导出 MP4 + WAV + SRT"
    : "导出 WAV + SRT";
  if (project.source_has_video) {
    dubSourceAudio.pause();
    dubSourceAudio.src = `${project.source_audio_url}?v=${Date.now()}`;
    dubSourceAudio.hidden = true;
    dubSourceVideo.hidden = false;
    dubSourceVideo.src = `${project.source_media_url}?v=${Date.now()}`;
  } else {
    dubSourceVideo.pause();
    dubSourceVideo.removeAttribute("src");
    dubSourceVideo.hidden = true;
    dubSourceAudio.hidden = false;
    dubSourceAudio.src = `${project.source_audio_url}?v=${Date.now()}`;
  }
  dubExportResult.hidden = true;
  dubExportMp4.hidden = true;
  renderDubTimeline(project);

  const latestExport = project.exports?.at(-1);
  if (latestExport) {
    dubExportWav.href = latestExport.wav_url;
    dubExportSrt.href = latestExport.srt_url;
    if (latestExport.mp4_url) {
      dubExportMp4.href = latestExport.mp4_url;
      dubExportMp4.hidden = false;
      dubOriginalAudioGain.value = String(latestExport.original_audio_gain || 0);
    }
    dubExportSummary.textContent = dubExportSummaryCopy(latestExport);
    dubExportResult.hidden = false;
  }

  for (const segment of project.segments) {
    const row = document.createElement("article");
    row.className = "dub-segment";
    row.dataset.status = segment.render.status;
    row.dataset.segmentId = segment.id;

    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "segment-check";
    check.setAttribute("aria-label", `选择 ${formatTimecode(segment.start)} 的配音片段`);
    check.addEventListener("change", () => {
      if (check.checked) selectedDubSegments.add(segment.id);
      else selectedDubSegments.delete(segment.id);
      row.classList.toggle("is-selected", check.checked);
      updateDubControls();
    });

    const timeButton = document.createElement("button");
    timeButton.type = "button";
    timeButton.className = "segment-time";
    timeButton.textContent = `${formatTimecode(segment.start)}\n${formatTimecode(segment.end)}`;
    timeButton.addEventListener("click", () => seekDubSource(segment.start));

    const source = document.createElement("div");
    source.className = "dub-source-copy";
    const sourceLabel = document.createElement("span");
    sourceLabel.textContent = "原始 ASR";
    const sourceText = document.createElement("p");
    sourceText.textContent = segment.source_text;
    source.append(sourceLabel, sourceText);

    const editor = document.createElement("div");
    editor.className = "dub-segment-editor";
    const textarea = document.createElement("textarea");
    textarea.rows = 3;
    textarea.value = segment.active_text;
    textarea.setAttribute("aria-label", `${formatTimecode(segment.start)} 的配音文字`);
    textarea.addEventListener("input", () => {
      segment.active_text = textarea.value;
      markDubDirty(segment.id);
    });
    const voice = document.createElement("select");
    voice.setAttribute("aria-label", `${formatTimecode(segment.start)} 的配音音色`);
    voice.add(new Option("未分配音色", ""));
    for (const item of voices) voice.add(new Option(item.name, item.id));
    voice.value = segment.voice_id || "";
    voice.addEventListener("change", () => {
      segment.voice_id = voice.value || null;
      markDubDirty(segment.id);
    });
    editor.append(textarea, voice);

    const render = document.createElement("div");
    render.className = "dub-render-cell";
    const status = dubStatusCopy(segment);
    const badge = document.createElement("strong");
    badge.className = "dub-status-badge";
    badge.textContent = status.label;
    const detail = document.createElement("small");
    detail.textContent = status.detail;
    const actions = document.createElement("div");
    actions.className = "dub-row-actions";
    const play = document.createElement("button");
    play.type = "button";
    play.className = "micro-button";
    play.textContent = "试听";
    play.disabled = !segment.render.audio_url;
    play.addEventListener("click", () => {
      dubPreviewAudio.src = `${segment.render.audio_url}?v=${Date.now()}`;
      dubPreviewAudio.play().catch((error) => showError(error.message));
    });
    const regenerate = document.createElement("button");
    regenerate.type = "button";
    regenerate.className = "micro-button";
    regenerate.textContent = segment.render.status === "ready" ? "重新生成" : "生成此段";
    regenerate.addEventListener("click", () => startDubJob("selected", [segment.id]));
    actions.append(play, regenerate);
    render.append(badge, detail, actions);

    row.append(check, timeButton, source, editor, render);
    dubSegments.append(row);
    dubSegmentRows.set(segment.id, { row, check, textarea, voice, regenerate });
  }

  renderDubProjectList(project.id);
  const lastJob = project.last_job;
  if (lastJob && ["queued", "running"].includes(lastJob.status)) {
    startDubPolling(lastJob);
  } else {
    currentDubJobId = null;
    window.localStorage.removeItem("timbreloomCurrentDubJob");
    dubProgressCard.hidden = true;
  }
  updateDubControls();
}

async function loadDubProject(projectId, shouldScroll = false) {
  const response = await fetch(`/api/dub/projects/${projectId}`, { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response));
  renderDubProject(await response.json());
  if (shouldScroll) dubEditor.scrollIntoView({ behavior: "smooth", block: "start" });
}

createDubForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  createDubButton.disabled = true;
  try {
    const response = await fetch("/api/dub/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript_id: dubTranscriptSelect.value,
        title: dubTitleInput.value,
        target_language: dubTargetLanguage.value,
        default_voice_id: dubDefaultVoice.value,
      }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const payload = await response.json();
    dubTitleInput.value = "";
    await loadDubProjects(payload.project.id);
    await loadDubProject(payload.project.id, true);
  } catch (error) {
    showError(error.message);
  } finally {
    createDubButton.disabled = false;
  }
});

refreshDubProjects.addEventListener("click", () => {
  loadDubProjects(currentDubProject?.id || "").catch((error) => showError(error.message));
});

dubProjectTitleInput.addEventListener("input", () => {
  if (!currentDubProject) return;
  currentDubProject.title = dubProjectTitleInput.value;
  markDubDirty();
});

dubProjectLanguage.addEventListener("change", () => {
  if (!currentDubProject) return;
  currentDubProject.target_language = dubProjectLanguage.value;
  markDubDirty();
});

async function saveDubChanges() {
  if (!currentDubProject) return false;
  if (!dubProjectDirty && !dirtyDubSegments.size) return true;
  const projectId = currentDubProject.id;
  const updates = [...dirtyDubSegments].map((segmentId) => {
    const segment = currentDubProject.segments.find((item) => item.id === segmentId);
    return {
      id: segmentId,
      active_text: segment.active_text,
      voice_id: segment.voice_id,
    };
  });
  dubSaveButton.disabled = true;
  dubSaveButton.textContent = "正在保存";
  try {
    const response = await fetch(`/api/dub/projects/${projectId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: currentDubProject.title,
        target_language: currentDubProject.target_language,
        segments: updates,
      }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const payload = await response.json();
    renderDubProject(payload.project);
    await loadDubProjects(projectId);
    return true;
  } catch (error) {
    showError(error.message);
    updateDubControls();
    return false;
  }
}

dubSaveButton.addEventListener("click", saveDubChanges);

dubSelectAll.addEventListener("change", () => {
  if (!currentDubProject) return;
  selectedDubSegments.clear();
  for (const segment of currentDubProject.segments) {
    const row = dubSegmentRows.get(segment.id);
    row.check.checked = dubSelectAll.checked;
    row.row.classList.toggle("is-selected", dubSelectAll.checked);
    if (dubSelectAll.checked) selectedDubSegments.add(segment.id);
  }
  updateDubControls();
});

function renderDubJob(job) {
  const percent = Math.max(0, Math.min(100, Math.round(job.progress * 100)));
  const titles = {
    queued: "任务已保存",
    rendering: "正在逐段生成",
    complete: "所选片段已完成",
    partial: "部分片段需要重试",
    cancelled: "任务已停止",
    error: "任务异常停止",
  };
  dubProgressTitle.textContent = titles[job.phase] || "正在生成配音";
  dubProgressText.textContent = job.message;
  dubProgressPercent.textContent = `${percent}%`;
  dubProgressFill.style.width = `${percent}%`;
  dubProgressTrack.setAttribute("aria-valuenow", percent.toString());
  dubProgressMeta.textContent = `${job.processed} / ${job.total} 段 · 新生成 ${job.generated} · 缓存 ${job.cached} · 失败 ${job.failed}`;
  dubCurrentText.textContent = job.current_text || "";
}

async function startDubJob(mode, segmentIds = []) {
  if (!currentDubProject || currentDubJobId) return;
  const projectId = currentDubProject.id;
  const requestedIds = [...segmentIds];
  if (!(await saveDubChanges())) return;
  try {
    const response = await fetch(`/api/dub/projects/${projectId}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, segment_ids: requestedIds }),
    });
    if (!response.ok) throw new Error(await readError(response));
    startDubPolling(await response.json());
  } catch (error) {
    showError(error.message);
  }
}

async function pollDubJob() {
  if (!currentDubProject || !currentDubJobId) return;
  const projectId = currentDubProject.id;
  const jobId = currentDubJobId;
  try {
    const response = await fetch(`/api/dub/projects/${projectId}/jobs/${jobId}`, {
      cache: "no-store",
    });
    if (!response.ok) throw new Error(await readError(response));
    const job = await response.json();
    renderDubJob(job);
    if (["complete", "partial", "cancelled", "error"].includes(job.status)) {
      currentDubJobId = null;
      window.localStorage.removeItem("timbreloomCurrentDubJob");
      dubProgressCard.hidden = true;
      await loadDubProject(projectId);
      await loadDubProjects(projectId);
      if (job.status === "error") showError(job.error || job.message);
      return;
    }
    dubPollTimer = window.setTimeout(pollDubJob, 800);
  } catch (error) {
    currentDubJobId = null;
    dubProgressCard.hidden = true;
    showError(error.message);
    updateDubControls();
  }
}

dubGenerateSelected.addEventListener("click", () => {
  startDubJob("selected", [...selectedDubSegments]);
});
dubGenerateAll.addEventListener("click", () => startDubJob("all"));
dubRetryFailed.addEventListener("click", () => startDubJob("failed"));

dubSourceVideo.addEventListener("error", () => {
  if (!currentDubProject?.source_has_video) return;
  dubSourceVideo.hidden = true;
  dubSourceAudio.hidden = false;
  dubEditorStatus.textContent = "浏览器无法预览该视频编码，已切换为源音频预览";
});

dubCancelButton.addEventListener("click", async () => {
  if (!currentDubProject || !currentDubJobId) return;
  dubCancelButton.disabled = true;
  try {
    const response = await fetch(
      `/api/dub/projects/${currentDubProject.id}/jobs/${currentDubJobId}/cancel`,
      { method: "POST" },
    );
    if (!response.ok) throw new Error(await readError(response));
    renderDubJob(await response.json());
  } catch (error) {
    showError(error.message);
  } finally {
    dubCancelButton.disabled = false;
  }
});

dubExportButton.addEventListener("click", async () => {
  if (!currentDubProject) return;
  if (!(await saveDubChanges())) return;
  dubExportButton.disabled = true;
  dubExportButtonText.textContent = currentDubProject.source_has_video
    ? "正在封装视频..."
    : "正在导出...";
  dubEditorStatus.textContent = currentDubProject.source_has_video
    ? "正在混合音轨并封装 MP4"
    : "正在写入时间线音频和字幕";
  try {
    const response = await fetch(`/api/dub/projects/${currentDubProject.id}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        original_audio_gain: currentDubProject.source_has_video
          ? Number(dubOriginalAudioGain.value)
          : 0,
      }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const result = (await response.json()).export;
    dubExportWav.href = result.wav_url;
    dubExportSrt.href = result.srt_url;
    if (result.mp4_url) {
      dubExportMp4.href = result.mp4_url;
      dubExportMp4.hidden = false;
    } else {
      dubExportMp4.hidden = true;
    }
    dubExportSummary.textContent = dubExportSummaryCopy(result);
    dubExportResult.hidden = false;
    await loadDubProject(currentDubProject.id);
  } catch (error) {
    showError(error.message);
  } finally {
    dubExportButtonText.textContent = currentDubProject?.source_has_video
      ? "导出 MP4 + WAV + SRT"
      : "导出 WAV + SRT";
    updateDubControls();
  }
});

dubGeminiTranslate.addEventListener("click", async () => {
  if (!currentDubProject || selectedDubSegments.size !== 1) return;
  const segmentId = [...selectedDubSegments][0];
  const confirmed = window.confirm(
    `将当前一段配音文字发送到 Gemini 翻译为${dubGeminiTargetLanguage.value}。不会上传音频，云端调用可能产生费用。是否继续？`,
  );
  if (!confirmed || !(await saveDubChanges())) return;
  dubGeminiTranslate.disabled = true;
  try {
    const response = await fetch(`/api/dub/projects/${currentDubProject.id}/gemini`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        segment_id: segmentId,
        task: "translate",
        target_language: dubGeminiTargetLanguage.value,
        confirm_cloud: true,
      }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const result = await response.json();
    const segment = currentDubProject.segments.find((item) => item.id === result.segment_id);
    const row = dubSegmentRows.get(result.segment_id);
    segment.active_text = result.text;
    row.textarea.value = result.text;
    markDubDirty(result.segment_id);
    dubEditorStatus.textContent = "Gemini 翻译已放入配音文字，尚未保存";
  } catch (error) {
    showError(error.message);
  } finally {
    updateDubControls();
  }
});

Promise.all([
  refreshHealth(),
  loadProviders(),
  loadVoices(),
  restoreJob(),
  loadTranscripts(),
  restoreAsrJob(),
]).then(() => loadDubProjects()).catch((error) => {
  showError(error.message);
});
statusTimer = window.setInterval(refreshHealth, 2500);
