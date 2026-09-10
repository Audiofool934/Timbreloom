import { createProgressiveAudioPlayer } from "./audio-player.js?v=2";
import { countLabel } from "./text-format.js?v=1";

export function createDubbingWorkspace({
  getVoices, getTranscripts, isGeminiConfigured, formatDuration,
  formatTranscriptDate, formatTimecode, readError, showError, ensureTtsModel = async () => true,
}) {
  const createDubForm = document.querySelector("#createDubForm");
  const dubTranscriptSelect = document.querySelector("#dubTranscriptSelect");
  const dubTitleInput = document.querySelector("#dubTitleInput");
  const dubDefaultVoice = document.querySelector("#dubDefaultVoice");
  const dubTargetLanguage = document.querySelector("#dubTargetLanguage");
  const createDubButton = document.querySelector("#createDubButton");
  const refreshDubProjects = document.querySelector("#refreshDubProjects");
  const dubBundleImport = document.querySelector("#dubBundleImport");
  const dubProjectList = document.querySelector("#dubProjectList");
  const dubEditor = document.querySelector("#dubEditor");
  const dubProjectTitleInput = document.querySelector("#dubProjectTitleInput");
  const dubProjectLanguage = document.querySelector("#dubProjectLanguage");
  const dubProjectMeta = document.querySelector("#dubProjectMeta");
  const dubSourceVideo = document.querySelector("#dubSourceVideo");
  const dubSourceAudio = document.querySelector("#dubSourceAudio");
  const dubSaveButton = document.querySelector("#dubSaveButton");
  const dubBundleDownload = document.querySelector("#dubBundleDownload");
  const dubExportButton = document.querySelector("#dubExportButton");
  const dubExportButtonText = document.querySelector("#dubExportButtonText");
  const dubOriginalAudioField = document.querySelector("#dubOriginalAudioField");
  const dubOriginalAudioGain = document.querySelector("#dubOriginalAudioGain");
  const dubTimelineTrack = document.querySelector("#dubTimelineTrack");
  const dubWaveformShell = document.querySelector("#dubWaveformShell");
  const dubWaveformCanvas = document.querySelector("#dubWaveformCanvas");
  const dubPlayhead = document.querySelector("#dubPlayhead");
  const dubPlayheadTime = document.querySelector("#dubPlayheadTime");
  const dubTimelineSummary = document.querySelector("#dubTimelineSummary");
  const dubQuality = document.querySelector("#dubQuality");
  const dubQualityTitle = document.querySelector("#dubQualityTitle");
  const dubQualitySummary = document.querySelector("#dubQualitySummary");
  const dubRoleName = document.querySelector("#dubRoleName");
  const dubRoleVoice = document.querySelector("#dubRoleVoice");
  const dubRoleSave = document.querySelector("#dubRoleSave");
  const dubApplyRole = document.querySelector("#dubApplyRole");
  const dubApplyRoleButton = document.querySelector("#dubApplyRoleButton");
  const dubSelectionCount = document.querySelector("#dubSelectionCount");
  const dubEditorStatus = document.querySelector("#dubEditorStatus");
  const dubGenerateSelected = document.querySelector("#dubGenerateSelected");
  const dubSplitButton = document.querySelector("#dubSplitButton");
  const dubMergeButton = document.querySelector("#dubMergeButton");
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
  const dubStreamCard = document.querySelector("#dubStreamCard");
  const dubStreamStatus = document.querySelector("#dubStreamStatus");
  const dubStreamToggle = document.querySelector("#dubStreamToggle");
  const dubStreamAudio = document.querySelector("#dubStreamAudio");
  const dubExportResult = document.querySelector("#dubExportResult");
  const dubExportSummary = document.querySelector("#dubExportSummary");
  const dubExportMp4 = document.querySelector("#dubExportMp4");
  const dubExportWav = document.querySelector("#dubExportWav");
  const dubExportSrt = document.querySelector("#dubExportSrt");
  const dubGeminiStatus = document.querySelector("#dubGeminiStatus");
  const dubGeminiTargetLanguage = document.querySelector("#dubGeminiTargetLanguage");
  const dubGeminiTask = document.querySelector("#dubGeminiTask");
  const dubGeminiTranslate = document.querySelector("#dubGeminiTranslate");
  const dubSelectAll = document.querySelector("#dubSelectAll");
  const dubSegments = document.querySelector("#dubSegments");
  let dubProjects = [];
  let currentDubProject = null;
  let currentDubJobId = null;
  let dubPollTimer;
  let currentDubExportJobId = null;
  let dubExportPollTimer;
  let dubProjectDirty = false;
  let dubWaveform = null;
  let dubPlayheadSeconds = 0;
  const selectedDubSegments = new Set();
  const dirtyDubSegments = new Set();
  const dubSegmentRows = new Map();
  const dubPreviewAudio = new Audio();
  const dubStreamPlayer = createProgressiveAudioPlayer({
    card: dubStreamCard,
    audio: dubStreamAudio,
    status: dubStreamStatus,
    toggle: dubStreamToggle,
    waitingLabel: "Waiting for first segment",
  });

  function populateDubVoiceOptions() {
    const previous = dubDefaultVoice.value;
    const previousRoleVoice = dubRoleVoice.value;
    dubDefaultVoice.replaceChildren(new Option("Choose a saved voice", ""));
    dubRoleVoice.replaceChildren(new Option("Choose a voice", ""));
    for (const voice of getVoices()) {
      dubDefaultVoice.add(new Option(voice.name, voice.id));
      dubRoleVoice.add(new Option(voice.name, voice.id));
    }
    if (previous && getVoices().some((voice) => voice.id === previous)) {
      dubDefaultVoice.value = previous;
    }
    if (previousRoleVoice && getVoices().some((voice) => voice.id === previousRoleVoice)) {
      dubRoleVoice.value = previousRoleVoice;
    }
  }

  function populateDubTranscriptOptions() {
    const previous = dubTranscriptSelect.value;
    dubTranscriptSelect.replaceChildren(new Option("Choose a transcript", ""));
    for (const transcript of getTranscripts()) {
      dubTranscriptSelect.add(
        new Option(
          `${transcript.title || transcript.source_filename} · ${countLabel(transcript.segment_count, "segment")}`,
          transcript.id,
        ),
      );
    }
    if (previous && getTranscripts().some((transcript) => transcript.id === previous)) {
      dubTranscriptSelect.value = previous;
    }
  }

  function renderDubProjectList(preferredId = "") {
    dubProjectList.replaceChildren();
    if (!dubProjects.length) {
      const empty = document.createElement("p");
      empty.className = "empty-copy";
      empty.textContent = getTranscripts().length
        ? "No dubbing projects yet."
        : "Create a timestamped transcript in Transcription first.";
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
      meta.textContent = `${project.source_has_video ? "Video" : "Audio"} · ${project.ready_count} / ${countLabel(project.segment_count, "segment")} generated`;
      const state = document.createElement("small");
      state.textContent = project.failed_count
        ? `${countLabel(project.failed_count, "failed segment")} · ${formatTranscriptDate(project.updated_at)}`
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
      missing: "Not generated",
      stale: "Needs update",
      rendering: "Generating",
      ready: "Ready to play",
      error: "Generation failed",
    };
    let detail = labels[render.status] || render.status;
    if (render.status === "ready") {
      if (render.overflow_seconds > 0.05) {
        detail = render.fit_limited
          ? `Safe speed limit reached; still ${render.overflow_seconds.toFixed(1)} sec over`
          : `${render.overflow_seconds.toFixed(1)} sec beyond the original duration`;
      } else if (segment.fit_mode === "slot" && render.natural_overflow_seconds > 0.05) {
        detail = `${render.duration_seconds.toFixed(1)} sec · Safely fitted at ${render.fit_speed.toFixed(2)}x`;
      } else {
        detail = `${render.duration_seconds.toFixed(1)} sec · Within slot`;
      }
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
    const active = Boolean(currentDubJobId || currentDubExportJobId);
    const selectedCount = selectedDubSegments.size;
    const dirtyCount = dirtyDubSegments.size + (dubProjectDirty ? 1 : 0);
    const segments = project?.segments || [];
    const failedCount = segments.filter((segment) => segment.render.status === "error").length;
    const allReady = segments.length > 0
      && segments.every((segment) => segment.render.status === "ready");

    dubSelectionCount.textContent = selectedCount
      ? `${selectedCount} / ${countLabel(segments.length, "segment")} selected`
      : "No segments selected";
    if (active) {
      dubEditorStatus.textContent = "Dubbing is running. Progress is saved automatically.";
    } else if (dirtyCount) {
      dubEditorStatus.textContent = countLabel(dirtyCount, "unsaved change");
    } else if (failedCount) {
      dubEditorStatus.textContent = `${countLabel(failedCount, "failed segment")} can be retried individually`;
    } else {
      const readyCount = segments.filter((segment) => segment.render.status === "ready").length;
      dubEditorStatus.textContent = `${readyCount} / ${countLabel(segments.length, "segment")} cached`;
    }

    dubSaveButton.disabled = !project || !dirtyCount || active;
    dubSaveButton.textContent = dirtyCount ? `Save ${countLabel(dirtyCount, "change")}` : "Save Changes";
    dubGenerateSelected.disabled = !project || !selectedCount || active;
    dubGenerateAll.disabled = !project || active;
    dubRetryFailed.disabled = !project || !failedCount || active;
    dubExportButton.disabled = !project || !allReady || Boolean(dirtyCount) || active;
    dubOriginalAudioGain.disabled = active;
    dubGeminiTranslate.disabled = !project || !selectedCount || selectedCount > 50 || !isGeminiConfigured() || active;
    dubSplitButton.disabled = !project || selectedCount !== 1 || active;
    const selectedOrders = segments
      .filter((segment) => selectedDubSegments.has(segment.id))
      .map((segment) => segment.order)
      .sort((a, b) => a - b);
    const contiguous = selectedOrders.length > 1
      && selectedOrders.every((order, index) => index === 0 || order === selectedOrders[index - 1] + 1);
    dubMergeButton.disabled = !project || !contiguous || active;
    dubApplyRoleButton.disabled = !project || !selectedCount || !dubApplyRole.value || active;
    dubSelectAll.checked = segments.length > 0 && selectedCount === segments.length;
    dubSelectAll.indeterminate = selectedCount > 0 && selectedCount < segments.length;
    for (const row of dubSegmentRows.values()) {
      row.regenerate.disabled = active;
    }
  }

  function setDubSegmentSelection(segmentId, selected, exclusive = false) {
    if (exclusive) selectedDubSegments.clear();
    if (selected) selectedDubSegments.add(segmentId);
    else selectedDubSegments.delete(segmentId);
    for (const [id, row] of dubSegmentRows.entries()) {
      const isSelected = selectedDubSegments.has(id);
      row.check.checked = isSelected;
      row.row.classList.toggle("is-selected", isSelected);
    }
    for (const slot of dubTimelineTrack.querySelectorAll(".dub-timeline-slot")) {
      slot.classList.toggle("is-selected", selectedDubSegments.has(slot.dataset.segmentId));
    }
    updateDubControls();
  }

  function activeDubSourcePlayer() {
    return currentDubProject?.source_has_video && !dubSourceVideo.hidden
      ? dubSourceVideo
      : dubSourceAudio;
  }

  function seekDubSource(seconds) {
    const player = activeDubSourcePlayer();
    dubPlayheadSeconds = Math.max(0, Math.min(Number(currentDubProject?.duration_seconds) || 0, seconds));
    player.currentTime = dubPlayheadSeconds;
    updateDubPlayhead();
  }

  function updateDubPlayhead(seconds = null) {
    if (seconds !== null) dubPlayheadSeconds = seconds;
    const duration = Math.max(0.001, Number(currentDubProject?.duration_seconds) || 0);
    const percent = Math.max(0, Math.min(100, (dubPlayheadSeconds / duration) * 100));
    dubPlayhead.style.left = `${percent}%`;
    dubPlayheadTime.textContent = formatTimecode(dubPlayheadSeconds);
  }

  function drawDubWaveform() {
    const peaks = dubWaveform?.peaks || [];
    const width = Math.max(1, Math.round(dubWaveformShell.clientWidth));
    const height = Math.max(1, Math.round(dubWaveformShell.clientHeight));
    const scale = window.devicePixelRatio || 1;
    dubWaveformCanvas.width = Math.round(width * scale);
    dubWaveformCanvas.height = Math.round(height * scale);
    const context = dubWaveformCanvas.getContext("2d");
    context.setTransform(scale, 0, 0, scale, 0, 0);
    context.clearRect(0, 0, width, height);
    if (!peaks.length) return;
    context.fillStyle = "rgba(70, 82, 64, 0.55)";
    const center = height / 2;
    for (let x = 0; x < width; x += 1) {
      const peak = peaks[Math.min(peaks.length - 1, Math.floor((x / width) * peaks.length))];
      const amplitude = Math.max(1, peak * (height * 0.43));
      context.fillRect(x, center - amplitude, 1, amplitude * 2);
    }
  }

  async function loadDubWaveform(projectId) {
    dubWaveform = null;
    drawDubWaveform();
    const response = await fetch(`/api/dub/projects/${projectId}/waveform?points=1800`, { cache: "no-store" });
    if (!response.ok) throw new Error(await readError(response));
    if (currentDubProject?.id !== projectId) return;
    dubWaveform = await response.json();
    drawDubWaveform();
  }

  function renderDubTimeline(project) {
    dubTimelineTrack.replaceChildren();
    const duration = Math.max(0.001, Number(project.duration_seconds) || 0);
    const readyCount = project.segments.filter((segment) => segment.render.status === "ready").length;
    const overlapCount = project.segments.filter(
      (segment) => segment.render.overlap_next_seconds > 0.05,
    ).length;
    dubTimelineSummary.textContent = overlapCount
      ? `${readyCount} / ${project.segments.length} generated · ${countLabel(overlapCount, "overlap")}`
      : `${readyCount} / ${project.segments.length} generated · ${formatDuration(duration)}`;

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
      slot.dataset.segmentId = segment.id;
      slot.classList.toggle("is-selected", selectedDubSegments.has(segment.id));
      slot.setAttribute(
        "aria-label",
        `${formatTimecode(segment.start)} to ${formatTimecode(segment.end)}, ${dubStatusCopy(segment).detail}`,
      );
      slot.title = `${formatTimecode(segment.start)} · ${dubStatusCopy(segment).detail}`;
      slot.addEventListener("click", (event) => {
        event.stopPropagation();
        setDubSegmentSelection(segment.id, true, true);
        const bounds = dubWaveformShell.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
        seekDubSource(ratio * duration);
        dubSegmentRows.get(segment.id)?.row.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
      dubTimelineTrack.append(slot);

      if (segment.render.duration_seconds > 0) {
        const renderWidth = Math.max(
          0.35,
          Math.min(100 - left, ((segment.render.fitted_duration_seconds || segment.render.duration_seconds) / duration) * 100),
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

  function renderDubQuality(project) {
    const quality = project.quality || { export_ready: false, counts: {}, issue_count: 0 };
    const counts = quality.counts || {};
    const blocking = (counts.missing || 0) + (counts.stale || 0) + (counts.error || 0) + (counts.unassigned || 0);
    const timing = (counts.overlap || 0) + (counts.fit_limited || 0);
    dubQuality.dataset.state = counts.error ? "error" : blocking ? "pending" : timing ? "warning" : "ready";
    dubQualityTitle.textContent = blocking ? "Preparing to export" : timing ? "Ready to export. Check timing." : "Project checks passed";
    const details = [];
    if (counts.unassigned) details.push(`Unassigned: ${counts.unassigned}`);
    if (counts.missing) details.push(`Not generated: ${counts.missing}`);
    if (counts.stale) details.push(`Needs update: ${counts.stale}`);
    if (counts.error) details.push(`Failed: ${counts.error}`);
    if (counts.overlap) details.push(`Overlaps: ${counts.overlap}`);
    if (counts.fit_limited) details.push(`Beyond safe speed limits: ${counts.fit_limited}`);
    dubQualitySummary.textContent = details.length
      ? `${details.join(" · ")}. Duration fitting uses 0.8x to 1.25x speed and never cuts dialogue.`
      : "Every segment has up-to-date audio. No obvious timeline overlaps were detected.";
  }

  function populateDubRoles(project) {
    const previous = dubApplyRole.value;
    dubApplyRole.replaceChildren(new Option("Choose a role", ""));
    for (const role of project.roles || []) {
      const voice = getVoices().find((item) => item.id === role.voice_id);
      dubApplyRole.add(new Option(`${role.name}${voice ? ` · ${voice.name}` : " · No voice assigned"}`, role.id));
    }
    if ((project.roles || []).some((role) => role.id === previous)) dubApplyRole.value = previous;
  }

  function dubExportSummaryCopy(result) {
    const output = result.mp4_url ? "MP4, WAV, and SRT" : "WAV and SRT";
    const warnings = result.warning_count
      ? `; ${countLabel(result.warning_count, "segment")} beyond the original slots, with all speech preserved`
      : "";
    if (result.mp4_url) {
      const gain = Math.round((result.original_audio_gain || 0) * 100);
      const mix = gain ? `; original audio at ${gain}%` : "; original audio muted";
      return `${output} exported${mix}${warnings}.`;
    }
    return `${output} exported along the original timeline${warnings}.`;
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
    const previousProjectId = currentDubProject?.id;
    if (previousProjectId && previousProjectId !== project.id) dubStreamPlayer.reset();
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
    dubBundleDownload.href = `/api/dub/projects/${project.id}/bundle`;
    dubBundleDownload.download = `${project.title || "timbreloom"}.timbreloom`;
    const mediaKind = project.source_has_video ? "VIDEO" : "AUDIO";
    dubProjectMeta.textContent = `${mediaKind} · ${formatDuration(project.duration_seconds)} · ${project.source_language.toUpperCase()} · ${countLabel(project.segments.length, "segment")} · ${project.source_filename}`;
    dubOriginalAudioField.hidden = !project.source_has_video;
    dubExportButtonText.textContent = project.source_has_video
      ? "Export MP4 + WAV + SRT"
      : "Export WAV + SRT";
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
    if (previousProjectId !== project.id) dubPlayheadSeconds = 0;
    updateDubPlayhead();
    populateDubRoles(project);
    renderDubQuality(project);
    renderDubTimeline(project);
    loadDubWaveform(project.id).catch((error) => {
      dubTimelineSummary.textContent = `Waveform could not load · ${error.message}`;
    });

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
      check.setAttribute("aria-label", `Select dubbing segment at ${formatTimecode(segment.start)}`);
      check.addEventListener("change", () => {
        setDubSegmentSelection(segment.id, check.checked);
      });

      const timeButton = document.createElement("button");
      timeButton.type = "button";
      timeButton.className = "segment-time";
      timeButton.textContent = `${formatTimecode(segment.start)}\n${formatTimecode(segment.end)}`;
      timeButton.addEventListener("click", () => {
        setDubSegmentSelection(segment.id, true, true);
        seekDubSource(segment.start);
      });

      const source = document.createElement("div");
      source.className = "dub-source-copy";
      const sourceLabel = document.createElement("span");
      sourceLabel.textContent = "Original ASR";
      const sourceText = document.createElement("p");
      sourceText.textContent = segment.source_text;
      source.append(sourceLabel, sourceText);

      const editor = document.createElement("div");
      editor.className = "dub-segment-editor";
      const textarea = document.createElement("textarea");
      textarea.rows = 3;
      textarea.value = segment.active_text;
      textarea.setAttribute("aria-label", `Dubbing text at ${formatTimecode(segment.start)}`);
      textarea.addEventListener("input", () => {
        segment.active_text = textarea.value;
        markDubDirty(segment.id);
      });
      const timeFields = document.createElement("div");
      timeFields.className = "dub-time-fields";
      const startLabel = document.createElement("label");
      startLabel.textContent = "Start (sec)";
      const startInput = document.createElement("input");
      startInput.type = "number";
      startInput.min = "0";
      startInput.step = "0.01";
      startInput.value = Number(segment.start).toFixed(3);
      const endLabel = document.createElement("label");
      endLabel.textContent = "End (sec)";
      const endInput = document.createElement("input");
      endInput.type = "number";
      endInput.min = "0";
      endInput.step = "0.01";
      endInput.value = Number(segment.end).toFixed(3);
      const updateTiming = () => {
        segment.start = Number(startInput.value);
        segment.end = Number(endInput.value);
        timeButton.textContent = `${formatTimecode(segment.start)}\n${formatTimecode(segment.end)}`;
        markDubDirty(segment.id);
      };
      startInput.addEventListener("input", updateTiming);
      endInput.addEventListener("input", updateTiming);
      startLabel.append(startInput);
      endLabel.append(endInput);
      timeFields.append(startLabel, endLabel);

      const selects = document.createElement("div");
      selects.className = "dub-editor-selects";
      const roleSelect = document.createElement("select");
      roleSelect.setAttribute("aria-label", `Role at ${formatTimecode(segment.start)}`);
      roleSelect.add(new Option("No role", ""));
      for (const role of project.roles || []) roleSelect.add(new Option(role.name, role.id));
      roleSelect.value = segment.role_id || "";
      roleSelect.addEventListener("change", () => {
        const role = (project.roles || []).find((item) => item.id === roleSelect.value);
        segment.role_id = role?.id || null;
        if (role) {
          segment.voice_id = role.voice_id || null;
          voice.value = segment.voice_id || "";
        }
        markDubDirty(segment.id);
      });
      const fit = document.createElement("select");
      fit.setAttribute("aria-label", `Duration fit at ${formatTimecode(segment.start)}`);
      fit.add(new Option("Natural duration", "natural"));
      fit.add(new Option("Fit slot safely", "slot"));
      fit.value = segment.fit_mode || "natural";
      fit.addEventListener("change", () => {
        segment.fit_mode = fit.value;
        markDubDirty(segment.id);
      });
      selects.append(roleSelect, fit);
      const voice = document.createElement("select");
      voice.setAttribute("aria-label", `Dubbing voice at ${formatTimecode(segment.start)}`);
      voice.add(new Option("No voice assigned", ""));
      for (const item of getVoices()) voice.add(new Option(item.name, item.id));
      voice.value = segment.voice_id || "";
      voice.addEventListener("change", () => {
        segment.voice_id = voice.value || null;
        segment.role_id = null;
        roleSelect.value = "";
        markDubDirty(segment.id);
      });
      editor.append(textarea, timeFields, selects, voice);

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
      play.textContent = "Preview";
      play.disabled = !segment.render.audio_url;
      play.addEventListener("click", () => {
        dubPreviewAudio.src = `${segment.render.audio_url}?v=${Date.now()}`;
        dubPreviewAudio.play().catch((error) => showError(error.message));
      });
      const regenerate = document.createElement("button");
      regenerate.type = "button";
      regenerate.className = "micro-button";
      regenerate.textContent = segment.render.status === "ready" ? "Regenerate" : "Generate segment";
      regenerate.addEventListener("click", () => startDubJob("selected", [segment.id]));
      actions.append(play, regenerate);
      render.append(badge, detail, actions);

      row.append(check, timeButton, source, editor, render);
      dubSegments.append(row);
      dubSegmentRows.set(segment.id, {
        row,
        check,
        textarea,
        voice,
        roleSelect,
        fit,
        startInput,
        endInput,
        regenerate,
      });
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
    const lastExportJob = project.last_export_job;
    if (lastExportJob && ["queued", "running"].includes(lastExportJob.status)) {
      startDubExportPolling(lastExportJob);
    } else if (!currentDubJobId) {
      currentDubExportJobId = null;
      window.localStorage.removeItem("timbreloomCurrentDubExportJob");
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

  dubBundleImport.addEventListener("change", async () => {
    const file = dubBundleImport.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("bundle", file);
    dubBundleImport.disabled = true;
    try {
      const response = await fetch("/api/dub/projects/import", { method: "POST", body: formData });
      if (!response.ok) throw new Error(await readError(response));
      const project = (await response.json()).project;
      await loadDubProjects(project.id);
      await loadDubProject(project.id, true);
    } catch (error) {
      showError(error.message);
    } finally {
      dubBundleImport.value = "";
      dubBundleImport.disabled = false;
    }
  });

  dubRoleSave.addEventListener("click", async () => {
    if (!currentDubProject || !dubRoleName.value.trim()) return;
    dubRoleSave.disabled = true;
    try {
      const response = await fetch(`/api/dub/projects/${currentDubProject.id}/roles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: dubRoleName.value, voice_id: dubRoleVoice.value || null }),
      });
      if (!response.ok) throw new Error(await readError(response));
      dubRoleName.value = "";
      renderDubProject((await response.json()).project);
    } catch (error) {
      showError(error.message);
    } finally {
      dubRoleSave.disabled = false;
    }
  });

  dubApplyRole.addEventListener("change", updateDubControls);
  dubApplyRoleButton.addEventListener("click", () => {
    if (!currentDubProject || !dubApplyRole.value) return;
    const role = (currentDubProject.roles || []).find((item) => item.id === dubApplyRole.value);
    if (!role) return;
    for (const segment of currentDubProject.segments) {
      if (!selectedDubSegments.has(segment.id)) continue;
      segment.role_id = role.id;
      segment.voice_id = role.voice_id || null;
      const row = dubSegmentRows.get(segment.id);
      row.roleSelect.value = role.id;
      row.voice.value = role.voice_id || "";
      markDubDirty(segment.id);
    }
    dubEditorStatus.textContent = `Applied ${role.name} to ${countLabel(selectedDubSegments.size, "segment")}. Save to keep changes.`;
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
        role_id: segment.role_id,
        start: segment.start,
        end: segment.end,
        fit_mode: segment.fit_mode,
        gain: segment.gain,
      };
    });
    dubSaveButton.disabled = true;
    dubSaveButton.textContent = "Saving";
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
    for (const slot of dubTimelineTrack.querySelectorAll(".dub-timeline-slot")) {
      slot.classList.toggle("is-selected", dubSelectAll.checked);
    }
    updateDubControls();
  });

  function renderDubJob(job) {
    const percent = Math.max(0, Math.min(100, Math.round(job.progress * 100)));
    const titles = {
      queued: "Job saved",
      rendering: "Generating segments",
      complete: "Selected segments complete",
      partial: "Some segments need a retry",
      cancelled: "Job stopped",
      error: "Job stopped unexpectedly",
      validating: "Checking project",
      fitting: "Fitting duration safely",
      mixing: "Mixing timeline",
      muxing: "Muxing video",
    };
    dubProgressTitle.textContent = titles[job.phase] || "Generating dubbing";
    dubProgressText.textContent = job.message;
    dubProgressPercent.textContent = `${percent}%`;
    dubProgressFill.style.width = `${percent}%`;
    dubProgressTrack.setAttribute("aria-valuenow", percent.toString());
    if (job.kind === "export") {
      dubProgressMeta.textContent = "Job progress is saved in the project and can resume after a refresh or service restart";
      dubCurrentText.textContent = "Safe duration fitting preserves every line";
      dubCancelButton.hidden = true;
    } else {
      dubProgressMeta.textContent = `${job.processed} / ${countLabel(job.total, "segment")} · ${job.generated} new · ${job.cached} cached · ${job.failed} failed`;
      dubCurrentText.textContent = job.current_text || "";
      dubCancelButton.hidden = false;
      if (job.stream) dubStreamPlayer.update(job.stream, job.job_id);
    }
  }

  function startDubExportPolling(job) {
    currentDubExportJobId = job.job_id;
    window.localStorage.setItem(
      "timbreloomCurrentDubExportJob",
      JSON.stringify({ projectId: job.project_id, jobId: job.job_id }),
    );
    dubProgressCard.hidden = false;
    renderDubJob(job);
    window.clearTimeout(dubExportPollTimer);
    dubExportPollTimer = window.setTimeout(pollDubExportJob, 500);
    updateDubControls();
  }

  async function pollDubExportJob() {
    if (!currentDubProject || !currentDubExportJobId) return;
    const projectId = currentDubProject.id;
    const jobId = currentDubExportJobId;
    try {
      const response = await fetch(`/api/dub/projects/${projectId}/export-jobs/${jobId}`, { cache: "no-store" });
      if (!response.ok) throw new Error(await readError(response));
      const job = await response.json();
      renderDubJob(job);
      if (["complete", "error"].includes(job.status)) {
        currentDubExportJobId = null;
        window.localStorage.removeItem("timbreloomCurrentDubExportJob");
        if (job.status === "error") {
          dubProgressCard.hidden = true;
          showError(job.error || job.message);
        } else {
          const result = job.result;
          dubExportWav.href = result.wav_url;
          dubExportSrt.href = result.srt_url;
          dubExportMp4.hidden = !result.mp4_url;
          if (result.mp4_url) dubExportMp4.href = result.mp4_url;
          dubExportSummary.textContent = dubExportSummaryCopy(result);
          dubExportResult.hidden = false;
          dubProgressCard.hidden = true;
        }
        await loadDubProject(projectId);
        await loadDubProjects(projectId);
        return;
      }
      dubExportPollTimer = window.setTimeout(pollDubExportJob, 800);
    } catch (error) {
      currentDubExportJobId = null;
      dubProgressCard.hidden = true;
      showError(error.message);
      updateDubControls();
    }
  }

  async function startDubJob(mode, segmentIds = []) {
    if (!await ensureTtsModel()) return;
    if (!currentDubProject || currentDubJobId) return;
    const projectId = currentDubProject.id;
    const requestedIds = [...segmentIds];
    if (!(await saveDubChanges())) return;
    dubStreamPlayer.reset();
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

  dubWaveformShell.addEventListener("click", (event) => {
    if (!currentDubProject) return;
    const bounds = dubWaveformShell.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    seekDubSource(ratio * currentDubProject.duration_seconds);
  });

  for (const player of [dubSourceAudio, dubSourceVideo]) {
    player.addEventListener("timeupdate", () => {
      if (player !== activeDubSourcePlayer()) return;
      updateDubPlayhead(player.currentTime);
    });
    player.addEventListener("seeked", () => {
      if (player === activeDubSourcePlayer()) updateDubPlayhead(player.currentTime);
    });
  }

  window.addEventListener("resize", drawDubWaveform);

  dubSplitButton.addEventListener("click", async () => {
    if (!currentDubProject || selectedDubSegments.size !== 1) return;
    const segmentId = [...selectedDubSegments][0];
    const segment = currentDubProject.segments.find((item) => item.id === segmentId);
    if (dubPlayheadSeconds <= segment.start || dubPlayheadSeconds >= segment.end) {
      showError("Move the playhead inside the selected segment before splitting.");
      return;
    }
    if (!(await saveDubChanges())) return;
    try {
      const response = await fetch(`/api/dub/projects/${currentDubProject.id}/segments/${segmentId}/split`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ split_at: dubPlayheadSeconds }),
      });
      if (!response.ok) throw new Error(await readError(response));
      renderDubProject((await response.json()).project);
      await loadDubProjects(currentDubProject.id);
    } catch (error) {
      showError(error.message);
    }
  });

  dubMergeButton.addEventListener("click", async () => {
    if (!currentDubProject || selectedDubSegments.size < 2) return;
    const segmentIds = currentDubProject.segments
      .filter((segment) => selectedDubSegments.has(segment.id))
      .map((segment) => segment.id);
    if (!(await saveDubChanges())) return;
    try {
      const response = await fetch(`/api/dub/projects/${currentDubProject.id}/segments/merge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segment_ids: segmentIds }),
      });
      if (!response.ok) throw new Error(await readError(response));
      renderDubProject((await response.json()).project);
      await loadDubProjects(currentDubProject.id);
    } catch (error) {
      showError(error.message);
    }
  });

  dubSourceVideo.addEventListener("error", () => {
    if (!currentDubProject?.source_has_video) return;
    dubSourceVideo.hidden = true;
    dubSourceAudio.hidden = false;
    dubEditorStatus.textContent = "This browser cannot preview the video codec. Switched to source audio.";
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
    dubExportButtonText.textContent = "Creating job...";
    dubEditorStatus.textContent = "Saving a resumable export job";
    try {
      const response = await fetch(`/api/dub/projects/${currentDubProject.id}/export-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          original_audio_gain: currentDubProject.source_has_video
            ? Number(dubOriginalAudioGain.value)
            : 0,
        }),
      });
      if (!response.ok) throw new Error(await readError(response));
      startDubExportPolling(await response.json());
    } catch (error) {
      showError(error.message);
    } finally {
      dubExportButtonText.textContent = currentDubProject?.source_has_video ? "Export MP4 + WAV + SRT" : "Export WAV + SRT";
      updateDubControls();
    }
  });

  dubGeminiTranslate.addEventListener("click", async () => {
    if (!currentDubProject || !selectedDubSegments.size) return;
    const segmentIds = currentDubProject.segments
      .filter((segment) => selectedDubSegments.has(segment.id))
      .map((segment) => segment.id);
    const taskNames = { translate: "translate", punctuation: "add punctuation", cleanup: "clean up text" };
    const task = dubGeminiTask.value;
    const languageCopy = task === "translate" ? ` into ${dubGeminiTargetLanguage.value}` : "";
    const confirmed = window.confirm(
      `Send ${countLabel(segmentIds.length, "selected segment")} to Gemini to ${taskNames[task]}${languageCopy}? Audio will not be uploaded. Cloud usage may incur charges.`,
    );
    if (!confirmed || !(await saveDubChanges())) return;
    dubGeminiTranslate.disabled = true;
    dubEditorStatus.textContent = `Asking Gemini to ${taskNames[task]} each segment. Keep this page open.`;
    try {
      const response = await fetch(`/api/dub/projects/${currentDubProject.id}/gemini-batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segment_ids: segmentIds,
          task,
          target_language: dubGeminiTargetLanguage.value,
          confirm_cloud: true,
        }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const payload = await response.json();
      for (const result of payload.results) {
        const segment = currentDubProject.segments.find((item) => item.id === result.segment_id);
        const row = dubSegmentRows.get(result.segment_id);
        segment.active_text = result.text;
        row.textarea.value = result.text;
        markDubDirty(result.segment_id);
      }
      dubEditorStatus.textContent = `Gemini processed ${countLabel(payload.results.length, "segment")}. Save to keep the results.`;
    } catch (error) {
      showError(error.message);
    } finally {
      updateDubControls();
    }
  });

  return {
    hasUnsavedChanges: () => dirtyDubSegments.size > 0 || dubProjectDirty,
    loadProjects: loadDubProjects,
    populateVoices: populateDubVoiceOptions,
    populateTranscripts: populateDubTranscriptOptions,
    updateProvider(configured, failed = false) {
      dubGeminiStatus.textContent = failed ? "Check failed" : configured ? "Configured" : "Not configured";
      dubGeminiStatus.dataset.state = failed ? "error" : configured ? "ready" : "missing";
      updateDubControls();
    },
  };
}
