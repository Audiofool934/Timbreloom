import { createProgressiveAudioPlayer } from "./audio-player.js?v=2";
import { createAudioRecorder, cancelRecordingOutside, cancelActiveRecording, cancelRecordingFor } from "./audio-recorder.js?v=4";
import { createDubbingWorkspace } from "./dubbing.js?v=4";
import { readJob, JobConnectionError } from "./job-client.js?v=2";
import { installDesktop, notifyDesktop } from "./desktop.js?v=6";
import { installModelManager } from "./model-manager.js?v=2";
import { countLabel } from "./text-format.js?v=1";

const form = document.querySelector("#cloneForm");
const audioInput = document.querySelector("#referenceAudio");
const referenceText = document.querySelector("#referenceText");
const dropzone = document.querySelector("#dropzone");
const fileTitle = document.querySelector("#fileTitle");
const fileMeta = document.querySelector("#fileMeta");
const cloneRecorderPanel = document.querySelector("#cloneRecorder");
const cloneRecordStatus = document.querySelector("#cloneRecordStatus");
const cloneRecordTimer = document.querySelector("#cloneRecordTimer");
const cloneRecordStart = document.querySelector("#cloneRecordStart");
const cloneRecordStop = document.querySelector("#cloneRecordStop");
const cloneRecordCancel = document.querySelector("#cloneRecordCancel");
const cloneRecordPreview = document.querySelector("#cloneRecordPreview");
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
const cloneStreamCard = document.querySelector("#cloneStreamCard");
const cloneStreamStatus = document.querySelector("#cloneStreamStatus");
const cloneStreamToggle = document.querySelector("#cloneStreamToggle");
const cloneStreamAudio = document.querySelector("#cloneStreamAudio");
const resultCard = document.querySelector("#resultCard");
const errorCard = document.querySelector("#errorCard");
const errorText = document.querySelector("#errorText");
const audioPlayer = document.querySelector("#audioPlayer");
const downloadLink = document.querySelector("#downloadLink");
const modelState = document.querySelector("#modelState");
const modelStateText = document.querySelector("#modelStateText");
const modeButtons = [...document.querySelectorAll(".mode-button")];
const cloneView = document.querySelector("#cloneView");
const vcView = document.querySelector("#vcView");
const asrView = document.querySelector("#asrView");
const dubView = document.querySelector("#dubView");
const vcForm = document.querySelector("#vcForm");
const vcMedia = document.querySelector("#vcMedia");
const vcDropzone = document.querySelector("#vcDropzone");
const vcFileTitle = document.querySelector("#vcFileTitle");
const vcFileMeta = document.querySelector("#vcFileMeta");
const vcRecorderPanel = document.querySelector("#vcRecorder");
const vcRecordStatus = document.querySelector("#vcRecordStatus");
const vcRecordTimer = document.querySelector("#vcRecordTimer");
const vcRecordStart = document.querySelector("#vcRecordStart");
const vcRecordStop = document.querySelector("#vcRecordStop");
const vcRecordCancel = document.querySelector("#vcRecordCancel");
const vcRecordPreview = document.querySelector("#vcRecordPreview");
const vcVoiceSelect = document.querySelector("#vcVoiceSelect");
const vcRights = document.querySelector("#vcRights");
const vcEngineState = document.querySelector("#vcEngineState");
const vcStartButton = document.querySelector("#vcStartButton");
const vcButtonText = document.querySelector("#vcButtonText");
const refreshVcJobs = document.querySelector("#refreshVcJobs");
const vcJobList = document.querySelector("#vcJobList");
const vcProgressCard = document.querySelector("#vcProgressCard");
const vcProgressTitle = document.querySelector("#vcProgressTitle");
const vcProgressText = document.querySelector("#vcProgressText");
const vcProgressTrack = document.querySelector("#vcProgressTrack");
const vcProgressFill = document.querySelector("#vcProgressFill");
const vcProgressPercent = document.querySelector("#vcProgressPercent");
const vcProgressMeta = document.querySelector("#vcProgressMeta");
const vcCancelButton = document.querySelector("#vcCancelButton");
const vcRetryButton = document.querySelector("#vcRetryButton");
const vcStreamCard = document.querySelector("#vcStreamCard");
const vcStreamStatus = document.querySelector("#vcStreamStatus");
const vcStreamToggle = document.querySelector("#vcStreamToggle");
const vcStreamAudio = document.querySelector("#vcStreamAudio");
const vcResultCard = document.querySelector("#vcResultCard");
const vcSourceLabel = document.querySelector("#vcSourceLabel");
const vcOutputLabel = document.querySelector("#vcOutputLabel");
const vcSourceAudio = document.querySelector("#vcSourceAudio");
const vcSourceVideo = document.querySelector("#vcSourceVideo");
const vcOutputAudio = document.querySelector("#vcOutputAudio");
const vcDownloadAudio = document.querySelector("#vcDownloadAudio");
const vcDownloadVideo = document.querySelector("#vcDownloadVideo");
const vcDurationMetric = document.querySelector("#vcDurationMetric");
const vcVoiceMetric = document.querySelector("#vcVoiceMetric");
const vcTimeMetric = document.querySelector("#vcTimeMetric");
const vcRtfMetric = document.querySelector("#vcRtfMetric");
const asrForm = document.querySelector("#asrForm");
const asrMedia = document.querySelector("#asrMedia");
const asrDropzone = document.querySelector("#asrDropzone");
const asrFileTitle = document.querySelector("#asrFileTitle");
const asrFileMeta = document.querySelector("#asrFileMeta");
const asrRecorderPanel = document.querySelector("#asrRecorder");
const asrRecordStatus = document.querySelector("#asrRecordStatus");
const asrRecordTimer = document.querySelector("#asrRecordTimer");
const asrRecordStart = document.querySelector("#asrRecordStart");
const asrRecordStop = document.querySelector("#asrRecordStop");
const asrRecordCancel = document.querySelector("#asrRecordCancel");
const asrRecordPreview = document.querySelector("#asrRecordPreview");
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
const asrStreamCard = document.querySelector("#asrStreamCard");
const asrStreamStatus = document.querySelector("#asrStreamStatus");
const asrStreamToggle = document.querySelector("#asrStreamToggle");
const asrStreamAudio = document.querySelector("#asrStreamAudio");
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
let vcJobs = [];
let currentVcJobId = null;
let vcPollTimer;
let vcProviderReady = false;
let vcJobRunning = false;
let transcripts = [];
let currentTranscript = null;
let geminiConfigured = false;
const selectedTranscriptSegments = new Set();
const dirtyTranscriptSegments = new Set();
const segmentRows = new Map();
let cloneRecorderController;
let vcRecorderController;
let asrRecorderController;

const cloneStreamPlayer = createProgressiveAudioPlayer({
  card: cloneStreamCard,
  audio: cloneStreamAudio,
  status: cloneStreamStatus,
  toggle: cloneStreamToggle,
  waitingLabel: "Waiting for first segment",
});
const vcStreamPlayer = createProgressiveAudioPlayer({
  card: vcStreamCard,
  audio: vcStreamAudio,
  status: vcStreamStatus,
  toggle: vcStreamToggle,
  waitingLabel: "Waiting for first segment",
});
const asrStreamPlayer = createProgressiveAudioPlayer({
  card: asrStreamCard,
  audio: asrStreamAudio,
  status: asrStreamStatus,
  toggle: asrStreamToggle,
  waitingLabel: "Preparing audio track",
});
function switchView(view) {
  cancelRecordingOutside(view);
  cloneView.hidden = view !== "clone";
  vcView.hidden = view !== "vc";
  asrView.hidden = view !== "asr";
  dubView.hidden = view !== "dub";
  for (const button of modeButtons) {
    const active = button.dataset.view === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active.toString());
  }
  window.localStorage.setItem("timbreloomView", view);
  notifyDesktop("view", { view });
}

for (const button of modeButtons) {
  button.addEventListener("click", () => switchView(button.dataset.view));
}

const savedView = window.localStorage.getItem("timbreloomView");
switchView(["clone", "vc", "asr", "dub"].includes(savedView) ? savedView : "clone");

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(seconds) {
  const rounded = Math.max(0, Math.round(Number(seconds) || 0));
  if (rounded < 60) return `${rounded} sec`;
  const minutes = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return remaining ? `${minutes} min ${remaining} sec` : `${minutes} min`;
}

function updateFile(file) {
  if (!file) {
    dropzone.classList.remove("has-file");
    fileTitle.textContent = "Drop a recording or choose a file";
    fileMeta.textContent = "WAV, M4A, MP3, FLAC · Up to 40 MB";
    return;
  }
  dropzone.classList.add("has-file");
  fileTitle.textContent = file.name;
  fileMeta.textContent = `${formatBytes(file.size)} · Kept on this Mac`;
  if (!voiceName.value.trim()) {
    voiceName.value = file.name.replace(/\.[^.]+$/, "");
  }
}

cloneRecorderController = createAudioRecorder({
  view: "clone",
  input: audioInput,
  panel: cloneRecorderPanel,
  status: cloneRecordStatus,
  timer: cloneRecordTimer,
  startButton: cloneRecordStart,
  stopButton: cloneRecordStop,
  cancelButton: cloneRecordCancel,
  preview: cloneRecordPreview,
  maxSeconds: 30,
  idleMessage: "Up to 30 seconds · Recorded on this Mac",
  onFile: updateFile,
});

vcRecorderController = createAudioRecorder({
  view: "vc",
  input: vcMedia,
  panel: vcRecorderPanel,
  status: vcRecordStatus,
  timer: vcRecordTimer,
  startButton: vcRecordStart,
  stopButton: vcRecordStop,
  cancelButton: vcRecordCancel,
  preview: vcRecordPreview,
  maxSeconds: 30 * 60,
  idleMessage: "Up to 30 minutes · Preview after recording",
  onFile: updateVcFile,
});

asrRecorderController = createAudioRecorder({
  view: "asr",
  input: asrMedia,
  panel: asrRecorderPanel,
  status: asrRecordStatus,
  timer: asrRecordTimer,
  startButton: asrRecordStart,
  stopButton: asrRecordStop,
  cancelButton: asrRecordCancel,
  preview: asrRecordPreview,
  maxSeconds: 8 * 60 * 60,
  idleMessage: "Up to 8 hours · Transcribe after recording",
  onFile: updateAsrFile,
});

audioInput.addEventListener("change", () => {
  cloneRecorderController.clearPreview();
  updateFile(audioInput.files[0]);
});

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
  cloneRecorderController.clearPreview();
  updateFile(files[0]);
});

function selectedVoice() {
  return voices.find((voice) => voice.id === voiceSelect.value) || null;
}

function applyVoiceMode() {
  const voice = selectedVoice();
  const usesSavedVoice = Boolean(voice);
  if (usesSavedVoice) cancelRecordingFor("clone", "Switched to a saved voice. Recording canceled.");
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
    savedVoiceMeta.textContent = `${voice.duration_seconds.toFixed(1)} sec reference · ${voice.original_filename}`;
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
  voiceSelect.replaceChildren(new Option("Upload a new recording", ""));
  for (const voice of voices) {
    voiceSelect.add(new Option(`${voice.name} · ${voice.duration_seconds.toFixed(1)} sec`, voice.id));
  }
  if (previous && voices.some((voice) => voice.id === previous)) {
    voiceSelect.value = previous;
  }
  applyVoiceMode();
  populateVcVoiceOptions();
  dubWorkspace.populateVoices();
}

voiceSelect.addEventListener("change", applyVoiceMode);

saveVoiceButton.addEventListener("click", async () => {
  voiceSaveStatus.textContent = "";
  const file = audioInput.files[0];
  if (!file || !referenceText.value.trim() || !voiceName.value.trim()) {
    voiceSaveStatus.textContent = "Choose a recording, then enter its exact transcript and a voice name.";
    return;
  }

  const payload = new FormData();
  payload.append("name", voiceName.value);
  payload.append("reference_text", referenceText.value);
  payload.append("reference_audio", file);
  saveVoiceButton.disabled = true;
  saveVoiceButton.textContent = "Saving";

  try {
    const response = await fetch("/api/voices", { method: "POST", body: payload });
    if (!response.ok) throw new Error(await readError(response));
    const result = await response.json();
    voiceSaveStatus.textContent = `Saved voice: ${result.voice.name}.`;
    await loadVoices(result.voice.id);
  } catch (error) {
    voiceSaveStatus.textContent = error.message;
  } finally {
    saveVoiceButton.disabled = false;
    saveVoiceButton.textContent = "Save voice";
  }
});

deleteVoiceButton.addEventListener("click", async () => {
  const voice = selectedVoice();
  if (!voice) return;
  if (!window.confirm(`Delete the voice ${voice.name}?`)) return;
  try {
    const response = await fetch(`/api/voices/${voice.id}`, { method: "DELETE" });
    if (!response.ok) throw new Error(await readError(response));
    await loadVoices();
  } catch (error) {
    showError(error.message);
  }
});

targetText.addEventListener("input", () => {
  targetCount.textContent = targetText.value.length.toLocaleString("en-US");
  window.clearTimeout(previewTimer);
  if (!targetText.value.trim()) {
    segmentEstimate.textContent = "Waiting for text";
    return;
  }
  segmentEstimate.textContent = "Estimating";
  previewTimer = window.setTimeout(refreshSegmentPreview, 450);
});

async function refreshSegmentPreview() {
  const payload = new FormData();
  payload.append("target_text", targetText.value);
  try {
    const response = await fetch("/api/segments/preview", { method: "POST", body: payload });
    if (!response.ok) throw new Error(await readError(response));
    const preview = await response.json();
    segmentEstimate.textContent = `About ${countLabel(preview.segments, "segment")} · ${formatDuration(preview.estimated_duration_seconds)}`;
  } catch (error) {
    segmentEstimate.textContent = error.message;
  }
}

function setModelState(status, detail, label = "") {
  modelState.dataset.state = status;
  if (status === "ready") {
    modelStateText.textContent = label || "Local model ready";
  } else if (status === "loading") {
    modelStateText.textContent = label || "Preparing local model";
  } else if (status === "error") {
    modelStateText.textContent = label || "Model loading failed";
    modelState.title = detail || "";
  } else if (status === "missing") {
    modelStateText.textContent = "Download models when needed";
  } else {
    modelStateText.textContent = label || "Local models load when needed";
  }
  notifyDesktop("status", { state: status, label: modelStateText.textContent });
}

async function refreshHealth() {
  try {
    const response = await fetch("/api/health?library=false", { cache: "no-store" });
    if (!response.ok) throw new Error("Local service disconnected");
    const health = await response.json();
    if (health.active_local_workload === "asr") {
      setModelState("loading", "", "Whisper is transcribing locally");
    } else if (health.active_local_workload === "voice-conversion") {
      setModelState("loading", "", "Seed-VC is converting a voice");
    } else if (health.active_local_workload === "tts") {
      setModelState("loading", "", "Qwen is generating audio");
    } else {
      setModelState(health.model_status, health.error);
    }
    updateProviders(health.providers || []);
  } catch (error) {
    setModelState("error", error.message, "Local service disconnected");
  } finally {
    clearTimeout(statusTimer);
    statusTimer = window.setTimeout(refreshHealth, document.hidden ? 30000 : 5000);
  }
}

async function readError(response) {
  try {
    const body = await response.json();
    return body.detail || "Request failed.";
  } catch {
    return `Request failed with status ${response.status}.`;
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
  buttonText.textContent = "Generate speech";
  cancelButton.disabled = false;
  cancelButton.textContent = "Stop job";
}

function renderJob(job) {
  const percent = Math.max(0, Math.min(100, Math.round(job.progress * 100)));
  const phaseTitles = {
    queued: "Job created",
    preparing: "Preparing the reference voice",
    generating: "Generating segments",
    assembling: "Joining the full audio",
    complete: "Generation complete",
    cancelled: "Job stopped",
    error: "Job stopped",
  };
  progressTitle.textContent = phaseTitles[job.phase] || "Generating";
  progressText.textContent = job.message;
  progressPercent.textContent = `${percent}%`;
  progressSegments.textContent = job.segment_total
    ? `${job.segments_completed} / ${countLabel(job.segment_total, "segment")} complete`
    : "Calculating segments";
  currentSegmentText.textContent = job.current_text || "";
  progressFill.style.width = `${percent}%`;
  progressTrack.setAttribute("aria-valuenow", percent.toString());
  if (job.stream) {
    cloneStreamPlayer.update(job.stream, job.job_id || currentJobId || "clone-pending");
  }
}

function showResult(result) {
  const cacheBuster = `?v=${Date.now()}`;
  audioPlayer.src = result.audio_url + cacheBuster;
  downloadLink.href = result.audio_url;
  downloadLink.download = result.filename;
  document.querySelector("#durationMetric").textContent = formatDuration(result.audio_duration_seconds);
  document.querySelector("#segmentMetric").textContent = countLabel(result.segment_count, "segment");
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
    const job = await readJob(`/api/jobs/${currentJobId}`);
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
    if (error instanceof JobConnectionError && currentJobId) {
      progressCard.hidden = false;
      progressTitle.textContent = "Waiting for local service to reconnect";
      progressText.textContent = error.message;
      pollTimer = window.setTimeout(pollJob, 1500);
      return;
    }
    progressCard.hidden = true;
    showError(error.message);
    resetJobControls();
  }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
  if (!await modelManager.ensure("qwen")) return;
  if (currentJobId) return;
  errorCard.hidden = true;
  resultCard.hidden = true;
  progressCard.hidden = false;
  cloneStreamPlayer.reset();
  generateButton.disabled = true;
  buttonText.textContent = "Generating";

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
    message: "Splitting text at natural breaks, preserving every word",
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
  cancelButton.textContent = "Stopping";
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
  currentJobId = savedJobId;
  progressCard.hidden = false;
  generateButton.disabled = true;
  buttonText.textContent = "Generating";
  await pollJob();
}

function populateVcVoiceOptions() {
  const previous = vcVoiceSelect.value || window.localStorage.getItem("timbreloomVcVoice") || "";
  vcVoiceSelect.replaceChildren(new Option("Choose a saved voice", ""));
  for (const voice of voices) {
    vcVoiceSelect.add(new Option(`${voice.name} · ${voice.duration_seconds.toFixed(1)} sec`, voice.id));
  }
  if (previous && voices.some((voice) => voice.id === previous)) {
    vcVoiceSelect.value = previous;
  }
  updateVcControls();
}

function updateVcControls() {
  vcStartButton.disabled = vcJobRunning || !vcProviderReady || !voices.length;
  if (!vcProviderReady) {
    vcButtonText.textContent = "Seed-VC is not ready";
  } else if (!voices.length) {
    vcButtonText.textContent = "Save a voice first";
  } else if (vcJobRunning) {
    vcButtonText.textContent = "Converting voice";
  } else {
    vcButtonText.textContent = "Convert voice";
  }
}

vcVoiceSelect.addEventListener("change", () => {
  window.localStorage.setItem("timbreloomVcVoice", vcVoiceSelect.value);
});

function updateVcFile(file) {
  if (!file) {
    vcDropzone.classList.remove("has-file");
    vcFileTitle.textContent = "Drop an audio or video performance";
    vcFileMeta.textContent = "Includes TS, M2TS, MTS · Keeps timing, pauses, and expression";
    return;
  }
  vcDropzone.classList.add("has-file");
  vcFileTitle.textContent = file.name;
  vcFileMeta.textContent = `${formatBytes(file.size)} · Processed on this Mac`;
}

vcMedia.addEventListener("change", () => {
  vcRecorderController.clearPreview();
  updateVcFile(vcMedia.files[0]);
});

for (const eventName of ["dragenter", "dragover"]) {
  vcDropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    vcDropzone.classList.add("is-dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  vcDropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    vcDropzone.classList.remove("is-dragging");
  });
}

vcDropzone.addEventListener("drop", (event) => {
  const files = event.dataTransfer.files;
  if (!files.length) return;
  const transfer = new DataTransfer();
  transfer.items.add(files[0]);
  vcMedia.files = transfer.files;
  vcRecorderController.clearPreview();
  updateVcFile(files[0]);
});

function renderVcResult(job) {
  if (job.status !== "complete" || !job.result) {
    vcResultCard.hidden = true;
    return;
  }
  const result = job.result;
  vcResultCard.hidden = false;
  vcSourceLabel.textContent = job.source_filename;
  vcOutputLabel.textContent = `${job.voice_name} · ${result.diffusion_steps} steps · ${countLabel(result.chunk_count || 1, "segment")}`;
  vcSourceAudio.hidden = job.source_has_video;
  vcSourceVideo.hidden = !job.source_has_video;
  if (job.source_has_video) {
    vcSourceAudio.removeAttribute("src");
    vcSourceVideo.src = job.source_url;
  } else {
    vcSourceVideo.removeAttribute("src");
    vcSourceAudio.src = job.source_url;
  }
  vcOutputAudio.src = result.audio_url;
  vcDownloadAudio.href = result.audio_url;
  vcDownloadVideo.hidden = !result.video_url;
  if (result.video_url) vcDownloadVideo.href = result.video_url;
  vcDurationMetric.textContent = formatDuration(result.duration_seconds);
  vcVoiceMetric.textContent = job.voice_name;
  vcTimeMetric.textContent = formatDuration(result.generation_seconds);
  const elapsedRatio = Number(result.generation_seconds) / Number(result.duration_seconds);
  vcRtfMetric.textContent = Number.isFinite(elapsedRatio) ? `${elapsedRatio.toFixed(2)} × duration` : "-";
}

function renderVcJob(job) {
  const percent = Math.max(0, Math.min(100, Math.round(Number(job.progress || 0) * 100)));
  const titles = {
    queued: "Job created",
    probing: "Checking media",
    preparing: "Preparing source audio",
    chunking: "Planning long audio segments",
    converting: "Converting voice",
    stitching: "Joining audio segments",
    muxing: "Adding audio to video",
    complete: "Voice conversion complete",
    cancelled: "Job stopped",
    error: "Job did not complete",
  };
  vcProgressCard.hidden = job.status === "complete";
  vcProgressTitle.textContent = titles[job.phase] || "Converting voice";
  vcProgressText.textContent = job.error || job.message;
  vcProgressPercent.textContent = `${percent}%`;
  vcProgressFill.style.width = `${percent}%`;
  vcProgressTrack.setAttribute("aria-valuenow", percent.toString());
  const chunkProgress = job.chunk_total > 1
    ? ` · Segment ${Math.max(1, job.current_chunk)}/${job.chunk_total}`
    : "";
  vcProgressMeta.textContent = job.duration_seconds
    ? `${job.source_filename} · ${formatDuration(job.duration_seconds)} · ${job.voice_name}${chunkProgress}`
    : `${job.source_filename} · ${job.voice_name}`;
  vcJobRunning = job.status === "queued" || job.status === "running";
  vcCancelButton.hidden = !vcJobRunning;
  vcCancelButton.disabled = false;
  vcCancelButton.textContent = "Stop job";
  vcRetryButton.hidden = !["error", "cancelled"].includes(job.status);
  if (job.stream) vcStreamPlayer.update(job.stream, job.id);
  updateVcControls();
  renderVcResult(job);
}

function renderVcJobList() {
  vcJobList.replaceChildren();
  if (!vcJobs.length) {
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = "No voice conversions yet.";
    vcJobList.append(empty);
    return;
  }
  const statusNames = {
    queued: "Queued",
    running: "Processing",
    complete: "Complete",
    cancelled: "Stopped",
    error: "Failed",
  };
  for (const job of vcJobs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "transcript-list-item";
    if (job.id === currentVcJobId) button.classList.add("is-active");
    const title = document.createElement("strong");
    title.textContent = job.source_filename;
    const meta = document.createElement("span");
    meta.textContent = `${job.voice_name} · ${statusNames[job.status] || job.status}`;
    const date = document.createElement("small");
    date.textContent = formatTranscriptDate(job.created_at);
    button.append(title, meta, date);
    button.addEventListener("click", () => openVcJob(job.id));
    vcJobList.append(button);
  }
}

async function loadVcJobs() {
  const response = await fetch("/api/voice-conversions", { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response));
  const payload = await response.json();
  vcJobs = payload.conversions || [];
  renderVcJobList();
}

async function openVcJob(jobId, keepPolling = true) {
  window.clearTimeout(vcPollTimer);
  const response = await fetch(`/api/voice-conversions/${jobId}`, { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response));
  const job = await response.json();
  currentVcJobId = job.id;
  window.localStorage.setItem("timbreloomCurrentVcJob", job.id);
  errorCard.hidden = true;
  renderVcJob(job);
  await loadVcJobs();
  if (keepPolling && ["queued", "running"].includes(job.status)) {
    vcPollTimer = window.setTimeout(pollVcJob, 700);
  }
  return job;
}

async function pollVcJob() {
  if (!currentVcJobId) return;
  try {
    const job = await openVcJob(currentVcJobId, false);
    if (["queued", "running"].includes(job.status)) {
      vcPollTimer = window.setTimeout(pollVcJob, 700);
    } else if (job.status === "error") {
      showError(job.error || job.message);
    }
  } catch (error) {
    vcJobRunning = false;
    updateVcControls();
    showError(error.message);
  }
}

vcForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!await modelManager.ensure("seed-vc")) return;
  const file = vcMedia.files[0];
  if (!file || !vcVoiceSelect.value || !vcRights.checked) {
    showError("Choose source media and a target voice, then confirm usage permission.");
    return;
  }
  const preset = document.querySelector('input[name="vcPreset"]:checked')?.value || "balanced";
  const payload = new FormData();
  payload.append("media", file);
  payload.append("voice_id", vcVoiceSelect.value);
  payload.append("preset", preset);
  payload.append("confirm_rights", "true");
  vcJobRunning = true;
  vcResultCard.hidden = true;
  vcStreamPlayer.reset();
  errorCard.hidden = true;
  updateVcControls();
  try {
    const response = await fetch("/api/voice-conversions", { method: "POST", body: payload });
    if (!response.ok) throw new Error(await readError(response));
    const job = await response.json();
    currentVcJobId = job.id;
    window.localStorage.setItem("timbreloomCurrentVcJob", job.id);
    renderVcJob(job);
    await loadVcJobs();
    vcPollTimer = window.setTimeout(pollVcJob, 500);
  } catch (error) {
    vcJobRunning = false;
    updateVcControls();
    showError(error.message);
  }
});

vcCancelButton.addEventListener("click", async () => {
  if (!currentVcJobId) return;
  vcCancelButton.disabled = true;
  vcCancelButton.textContent = "Stopping";
  try {
    const response = await fetch(`/api/voice-conversions/${currentVcJobId}/cancel`, { method: "POST" });
    if (!response.ok) throw new Error(await readError(response));
    renderVcJob(await response.json());
  } catch (error) {
    showError(error.message);
  }
});

vcRetryButton.addEventListener("click", async () => {
  if (!currentVcJobId) return;
  vcRetryButton.disabled = true;
  try {
    const response = await fetch(`/api/voice-conversions/${currentVcJobId}/retry`, { method: "POST" });
    if (!response.ok) throw new Error(await readError(response));
    const job = await response.json();
    renderVcJob(job);
    vcPollTimer = window.setTimeout(pollVcJob, 500);
  } catch (error) {
    showError(error.message);
  } finally {
    vcRetryButton.disabled = false;
  }
});

refreshVcJobs.addEventListener("click", () => {
  loadVcJobs().catch((error) => showError(error.message));
});

async function restoreVcJob() {
  const jobId = window.localStorage.getItem("timbreloomCurrentVcJob");
  if (!jobId) return;
  try {
    await openVcJob(jobId);
  } catch {
    window.localStorage.removeItem("timbreloomCurrentVcJob");
  }
}

function updateProviders(providerList) {
  const gemini = providerList.find((provider) => provider.id === "gemini-text");
  const seedVc = providerList.find((provider) => provider.id === "local-seed-vc");
  vcProviderReady = Boolean(seedVc && seedVc.configured);
  vcEngineState.textContent = vcProviderReady
    ? "Isolated runtime · Offline conversion"
    : "Runtime missing · Run setup_seed_vc.sh";
  updateVcControls();
  geminiConfigured = Boolean(gemini && gemini.configured);
  geminiStatus.textContent = geminiConfigured ? "Configured" : "Not configured";
  geminiStatus.dataset.state = geminiConfigured ? "ready" : "missing";
  dubWorkspace.updateProvider(geminiConfigured);
  updateTranscriptSelection();
}

async function loadProviders() {
  try {
    const response = await fetch("/api/providers", { cache: "no-store" });
    if (!response.ok) throw new Error(await readError(response));
    const payload = await response.json();
    updateProviders(payload.providers || []);
  } catch (error) {
    vcProviderReady = false;
    vcEngineState.textContent = "Seed-VC status check failed";
    updateVcControls();
    geminiStatus.textContent = "Check failed";
    geminiStatus.dataset.state = "error";
    dubWorkspace.updateProvider(false, true);
  }
}

function updateAsrFile(file) {
  if (!file) {
    asrDropzone.classList.remove("has-file");
    asrFileTitle.textContent = "Drop audio or video here";
    asrFileMeta.textContent = "Processed locally · No cloud upload";
    return;
  }
  asrDropzone.classList.add("has-file");
  asrFileTitle.textContent = file.name;
  asrFileMeta.textContent = `${formatBytes(file.size)} · Ready to transcribe locally`;
}

asrMedia.addEventListener("change", () => {
  asrRecorderController.clearPreview();
  updateAsrFile(asrMedia.files[0]);
});

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
  asrRecorderController.clearPreview();
  updateAsrFile(files[0]);
});

function renderAsrJob(job) {
  const percent = Math.max(0, Math.min(100, Math.round(job.progress * 100)));
  const titles = {
    queued: "Job created",
    probing: "Checking media",
    preparing: "Preparing audio",
    transcribing: "Whisper is transcribing",
    saving: "Saving timestamps",
    complete: "Transcription complete",
    cancelled: "Job stopped",
    error: "Job did not complete",
  };
  asrProgressTitle.textContent = titles[job.phase] || "Transcribing locally";
  asrProgressText.textContent = job.message;
  asrProgressPercent.textContent = `${percent}%`;
  asrProgressFill.style.width = `${percent}%`;
  asrProgressTrack.setAttribute("aria-valuenow", percent.toString());
  asrProgressMeta.textContent = job.duration_seconds
    ? `${job.source_filename} · ${formatDuration(job.duration_seconds)}`
    : job.source_filename || "Waiting for media check";
  if (job.stream) asrStreamPlayer.update(job.stream, job.job_id);
}

function resetAsrControls() {
  currentAsrJobId = null;
  window.localStorage.removeItem("timbreloomCurrentAsrJob");
  window.clearTimeout(asrPollTimer);
  asrStartButton.disabled = false;
  asrButtonText.textContent = "Transcribe";
  asrCancelButton.disabled = false;
  asrCancelButton.textContent = "Stop job";
}

async function pollAsrJob() {
  if (!currentAsrJobId) return;
  try {
    const job = await readJob(`/api/asr/jobs/${currentAsrJobId}`);
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
    if (error instanceof JobConnectionError && currentAsrJobId) {
      asrProgressCard.hidden = false;
      asrProgressTitle.textContent = "Waiting for local service to reconnect";
      asrProgressText.textContent = error.message;
      asrPollTimer = window.setTimeout(pollAsrJob, 1500);
      return;
    }
    asrProgressCard.hidden = true;
    showError(error.message);
    resetAsrControls();
  }
}

asrForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!await modelManager.ensure("whisper")) return;
  if (currentAsrJobId) return;
  const file = asrMedia.files[0];
  if (!file) {
    showError("Choose audio or video to transcribe.");
    return;
  }
  errorCard.hidden = true;
  asrProgressCard.hidden = false;
  asrStreamPlayer.reset();
  asrStartButton.disabled = true;
  asrButtonText.textContent = "Transcribing";

  const payload = new FormData();
  payload.append("media", file);
  payload.append("language", asrLanguage.value);
  payload.append("initial_prompt", asrPrompt.value);
  renderAsrJob({
    phase: "queued",
    message: "Saving media in the local project",
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
  asrCancelButton.textContent = "Stopping";
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
  currentAsrJobId = savedJobId;
  asrProgressCard.hidden = false;
  asrStartButton.disabled = true;
  asrButtonText.textContent = "Transcribing";
  await pollAsrJob();
}

function formatTranscriptDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
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
    empty.textContent = "No transcripts yet.";
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
    meta.textContent = `${formatDuration(transcript.duration_seconds)} · ${countLabel(transcript.segment_count, "segment")}`;
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
  dubWorkspace.populateTranscripts();
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
    selectionCount.textContent = "No segments selected";
    selectionDuration.textContent = "Select 2 to 30 consecutive seconds to save a voice";
  } else {
    const contiguous = selectionIsContiguous(selected);
    const duration = selected[selected.length - 1].end - selected[0].start;
    selectionCount.textContent = `${countLabel(selected.length, "segment")} selected`;
    selectionDuration.textContent = contiguous
      ? `${formatTimecode(selected[0].start)} to ${formatTimecode(selected[selected.length - 1].end)} · ${duration.toFixed(1)} sec`
      : "Select consecutive segments to save a voice";
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
  saveTranscriptButton.textContent = `Save ${countLabel(dirtyTranscriptSegments.size, "change")}`;
}

function renderTranscript(transcript) {
  currentTranscript = transcript;
  selectedTranscriptSegments.clear();
  dirtyTranscriptSegments.clear();
  segmentRows.clear();
  transcriptSegments.replaceChildren();
  transcriptEditor.hidden = false;
  transcriptTitle.textContent = transcript.title || transcript.source_filename;
  transcriptMeta.textContent = `${formatDuration(transcript.duration_seconds)} · ${transcript.language.toUpperCase()} · ${countLabel(transcript.segments.length, "segment")} · ${transcript.model}`;
  transcriptAudio.src = `${transcript.audio_url}?v=${Date.now()}`;
  exportTxt.href = transcript.export_urls.txt;
  exportSrt.href = transcript.export_urls.srt;
  exportVtt.href = transcript.export_urls.vtt;
  saveTranscriptButton.disabled = true;
  saveTranscriptButton.textContent = "Save text changes";
  transcriptVoiceStatus.textContent = "";
  geminiActionStatus.textContent = "";

  for (const segment of transcript.segments) {
    const row = document.createElement("article");
    row.className = "transcript-segment";
    row.dataset.segmentId = segment.id;

    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "segment-check";
    check.setAttribute("aria-label", `Select segment at ${formatTimecode(segment.start)}`);
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
    textarea.setAttribute("aria-label", `Transcript text at ${formatTimecode(segment.start)}`);
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
  saveTranscriptButton.textContent = "Saving";
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
    saveTranscriptButton.textContent = "Text saved";
    window.setTimeout(() => {
      if (!dirtyTranscriptSegments.size) saveTranscriptButton.textContent = "Save text changes";
    }, 1400);
    return true;
  } catch (error) {
    showError(error.message);
    saveTranscriptButton.disabled = false;
    saveTranscriptButton.textContent = `Save ${countLabel(dirtyTranscriptSegments.size, "change")}`;
    return false;
  }
}

saveTranscriptButton.addEventListener("click", saveTranscriptChanges);

createVoiceFromTranscript.addEventListener("click", async () => {
  if (!currentTranscript) return;
  const selected = selectedSegmentsInOrder();
  transcriptVoiceStatus.textContent = "";
  createVoiceFromTranscript.disabled = true;
  createVoiceFromTranscript.textContent = "Saving voice";
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
    transcriptVoiceStatus.textContent = `Saved voice: ${result.voice.name}.`;
    await loadVoices(result.voice.id);
  } catch (error) {
    transcriptVoiceStatus.textContent = error.message;
  } finally {
    createVoiceFromTranscript.textContent = "Save selection as voice";
    updateTranscriptSelection();
  }
});

async function runGemini(task) {
  if (!currentTranscript) return;
  const selected = selectedSegmentsInOrder();
  if (selected.length !== 1) return;
  const actionNames = {
    punctuation: "add punctuation",
    cleanup: "clean up text",
    translate: `translate into ${geminiTargetLanguage.value}`,
  };
  const confirmed = window.confirm(
    `Send the selected text to Gemini to ${actionNames[task]}? Audio will not be uploaded. Cloud usage may incur charges.`,
  );
  if (!confirmed) return;
  if (!(await saveTranscriptChanges())) return;

  const buttons = [geminiPunctuation, geminiCleanup, geminiTranslate];
  buttons.forEach((button) => { button.disabled = true; });
  geminiActionStatus.textContent = `Asking Gemini to ${actionNames[task]}…`;
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
    geminiActionStatus.textContent = "Gemini results are in the editor. Save to keep your changes.";
  } catch (error) {
    geminiActionStatus.textContent = error.message;
  } finally {
    updateTranscriptSelection();
  }
}

geminiPunctuation.addEventListener("click", () => runGemini("punctuation"));
geminiCleanup.addEventListener("click", () => runGemini("cleanup"));
geminiTranslate.addEventListener("click", () => runGemini("translate"));

window.addEventListener("beforeunload", () => {
  cancelActiveRecording();
});

const modelManager = installModelManager();
window.addEventListener("timbreloom-models-changed", refreshHealth);
const dubWorkspace = createDubbingWorkspace({
  getVoices: () => voices,
  getTranscripts: () => transcripts,
  isGeminiConfigured: () => geminiConfigured,
  ensureTtsModel: () => modelManager.ensure("qwen"),
  formatDuration, formatTranscriptDate, formatTimecode, readError, showError,
});

Promise.all([
  refreshHealth(),
  loadProviders(),
  loadVoices(),
  loadVcJobs(),
  restoreVcJob(),
  restoreJob(),
  loadTranscripts(),
  restoreAsrJob(),
]).then(() => dubWorkspace.loadProjects()).catch((error) => {
  showError(error.message);
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) { clearTimeout(statusTimer); refreshHealth(); }
});
installDesktop({
  switchView,
  hasUnsavedEdits: () => dirtyTranscriptSegments.size > 0 || dubWorkspace.hasUnsavedChanges(),
});
