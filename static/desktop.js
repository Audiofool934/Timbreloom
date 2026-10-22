import { installDesktopAudio } from "./desktop-audio.js?v=3";

// The native shell exposes only a small command surface, never local filesystem access.
export function notifyDesktop(type, payload = {}) {
  if (!window.timbreloomDesktop) return;
  window.webkit?.messageHandlers?.timbreloom?.postMessage({ type, ...payload });
}

export function installDesktop({ switchView, hasUnsavedEdits }) {
  if (!window.timbreloomDesktop) return;
  const views = ["clone", "vc", "asr", "dub"];
  const currentView = () => document.querySelector(".mode-button.is-active")?.dataset.view || "clone";
  const byId = (id) => document.getElementById(id);
  const drafts = ["targetText", "referenceText", "voiceName", "asrPrompt"];
  const draftKey = "timbreloomDesktopDrafts.v1";
  const icon = (name) => {
    const span = document.createElement("span");
    span.className = "desktop-icon";
    span.setAttribute("aria-hidden", "true");
    const source = window.timbreloomDesktop.symbols?.[name];
    if (source) span.style.setProperty("--symbol", `url("${source}")`);
    return span;
  };
  try {
    const saved = JSON.parse(localStorage.getItem(draftKey) || "{}");
    for (const id of drafts) {
      if (typeof saved[id] === "string") {
        byId(id).value = saved[id];
        byId(id).dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
  } catch { /* A damaged draft must not block the workbench. */ }
  let draftTimer;
  const saveDraft = () => {
    try {
      localStorage.setItem(draftKey, JSON.stringify(Object.fromEntries(drafts.map((id) => [id, byId(id).value]))));
      return true;
    } catch { return false; }
  };
  drafts.forEach((id) => byId(id).addEventListener("input", () => {
    clearTimeout(draftTimer);
    draftTimer = setTimeout(saveDraft, 300);
  }));
  window.addEventListener("pagehide", saveDraft);

  const headings = [
    ["clone", "Voice cloning", "Choose a voice. Give it something to say."],
    ["vc", "Voice conversion", "Keep the timing, pauses, and expression. Give the performance a new voice."],
    ["asr", "Transcription", "Turn a recording into editable text and subtitles."],
    ["dub", "Dubbing studio", "Refine each line and voice, then bring the dialogue back to the picture."],
  ];
  for (const [id, title, description] of headings) {
    const section = byId(`${id}View`);
    section.querySelector("h1").textContent = title;
    section.querySelector(".lede").textContent = description;
  }
  const labels = {
    "LOCAL ARCHIVE": "Saved on this Mac", "LOCAL CONVERSION ARCHIVE": "Saved on this Mac", "LOCAL DUB ARCHIVE": "Saved on this Mac",
    "SAVED VOICE": "Saved voice", "LONG-FORM GENERATION": "Speech generation", "GENERATED LOCALLY": "Generated locally",
    "LOCAL TRANSCRIPTION": "Transcription", "EDITABLE TRANSCRIPT": "Text and subtitles", "CREATE VOICE": "Save a voice from segments",
    "PERSISTENT DUB PROJECT": "Dubbing studio", "ORIGINAL TIMECODE MAP": "Original timeline", "CAST & VOICE ASSIGNMENT": "Voice assignment",
    "PERSISTENT SEGMENT RENDER": "Segment generation", "TIMELINE EXPORT READY": "Export complete", "LIVE PLAYBACK": "Continuous playback",
    "GEMINI · OPTIONAL CLOUD": "Gemini · Optional cloud", "GEMINI TRANSLATION · OPTIONAL CLOUD": "Gemini · Optional cloud",
    "NATIVE SPEECH-TO-SPEECH": "Voice conversion", "PERFORMANCE PRESERVED": "Original performance preserved", "LOCAL VOICE CONVERSION": "Voice conversion", "VOICE CONVERSION COMPLETE": "Conversion complete",
  };
  document.querySelectorAll(".result-kicker, .action-label, .stream-kicker, .saved-label").forEach((element) => {
    const label = labels[element.textContent.trim()];
    if (!label) return;
    const text = [...element.childNodes].find((node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
    if (text) text.textContent = label;
  });
  document.querySelector("#asrForm .local-engine-note p").textContent = "Local recognition · Word timestamps";
  byId("vcRtfMetric").previousElementSibling.textContent = "Processing / duration";
  document.querySelector(".target-panel h2").textContent = "Your script";
  document.querySelector(".target-panel .panel-heading p").textContent = "Natural breaks for continuous, long-form speech.";
  byId("targetText").placeholder = "Write a sentence or paste a full script.\n\nUse punctuation and paragraph breaks to guide the pauses.";
  document.querySelector(".prosody-guide summary strong").textContent = "Punctuation and pauses";
  document.querySelector(".prosody-guide summary").append(icon("chevron.right"));
  document.querySelectorAll(".button-arrow").forEach((node) => node.replaceChildren(icon("arrow.right")));
  document.querySelectorAll(".upload-icon").forEach((node) => node.replaceChildren(icon("square.and.arrow.down")));
  for (const [id, symbol] of [["refreshTranscripts", "arrow.clockwise"], ["refreshVcJobs", "arrow.clockwise"],
    ["refreshDubProjects", "arrow.clockwise"]]) {
    const button = byId(id);
    if (button) button.replaceChildren(icon(symbol));
  }
  const bundleLabel = byId("dubBundleImport").closest("label");
  bundleLabel.querySelector("span").replaceChildren(icon("square.and.arrow.down"));
  bundleLabel.tabIndex = 0;
  bundleLabel.setAttribute("role", "button");
  bundleLabel.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); byId("dubBundleImport").click(); }
  });
  document.querySelectorAll("button[aria-label]").forEach((button) => { button.title ||= button.getAttribute("aria-label"); });
  for (const [id, name] of [["dubRoleName", "New role name"], ["dubRoleVoice", "New role voice"], ["dubApplyRole", "Apply role"]]) {
    byId(id)?.setAttribute("aria-label", name);
  }
  document.querySelectorAll(".dropzone input").forEach((input) => {
    input.setAttribute("aria-label", input.closest(".dropzone").querySelector("strong").textContent);
  });
  for (const [id, title] of [["generateButton", "Generate speech · ⌘↩"], ["vcStartButton", "Convert voice · ⌘↩"],
    ["asrStartButton", "Transcribe · ⌘↩"], ["saveTranscriptButton", "Save text changes · ⌘S"], ["dubSaveButton", "Save project · ⌘S"]]) {
    byId(id)?.setAttribute("title", title);
  }

  // Library empty states remain connected to the real import and creation workflows.
  for (const [id, symbol, title, hint, label, action] of [
    ["vcJobList", "waveform", "Your next voice starts here", "Import a performance and choose a voice to begin.", "Import Audio", () => window.timbreloomCommands.openFile()],
    ["transcriptList", "text.alignleft", "Make room for the words", "Import audio or video. Finished transcripts are saved automatically.", "Import Media", () => window.timbreloomCommands.openFile()],
    ["dubProjectList", "rectangle.stack", "Start your first dubbing project", "Start with a transcript, then choose voices for the dialogue.", "Open transcription", () => window.timbreloomCommands.selectView("asr")],
  ]) {
    const list = byId(id);
    if (!list) continue;
    const decorate = () => {
      const empty = list.querySelector(".empty-copy:not([data-desktop])");
      if (!empty) return;
      empty.dataset.desktop = "true";
      const strong = document.createElement("strong"); strong.textContent = title;
      const detail = document.createElement("span"); detail.textContent = hint;
      const button = document.createElement("button"); button.type = "button";
      button.className = "quiet-button"; button.textContent = label; button.addEventListener("click", action);
      empty.replaceChildren(icon(symbol), strong, detail, button);
    };
    decorate();
    new MutationObserver(decorate).observe(list, { childList: true });
  }

  const toast = document.createElement("div");
  toast.className = "desktop-toast"; toast.hidden = true; toast.setAttribute("role", "status");
  document.body.append(toast);
  let toastTimer;
  const announce = (text) => {
    clearTimeout(toastTimer); toast.textContent = text; toast.hidden = false;
    toastTimer = setTimeout(() => { toast.hidden = true; }, 2600);
  };
  const dismiss = document.createElement("button");
  dismiss.type = "button"; dismiss.className = "icon-button desktop-error-dismiss";
  dismiss.setAttribute("aria-label", "Dismiss error"); dismiss.append(icon("xmark"));
  dismiss.addEventListener("click", () => { byId("errorCard").hidden = true; });
  byId("errorCard").append(dismiss);

  installDesktopAudio({ icon });

  for (const toolbar of document.querySelectorAll(".transcript-toolbar, .dub-toolbar")) {
    const editor = toolbar.closest(".transcript-editor");
    new ResizeObserver(() => {
      editor.style.setProperty("--toolbar-offset", `${toolbar.getBoundingClientRect().height + 16}px`);
    }).observe(toolbar);
  }

  const positions = new Map();
  window.timbreloomCommands = Object.freeze({
    openModels() { window.dispatchEvent(new Event("timbreloom-open-models")); },
    selectView(view) {
      if (!views.includes(view)) return;
      saveDraft();
      const previous = currentView();
      if (view === previous) { switchView(view); return; }
      positions.set(previous, { top: scrollY, focus: document.activeElement?.id });
      switchView(view);
      const position = positions.get(view);
      window.scrollTo({ top: position?.top || 0, behavior: "instant" });
      const focus = position?.focus && byId(position.focus);
      if (focus && focus.getClientRects().length) focus.focus({ preventScroll: true });
    },
    openFile() {
      const view = currentView();
      if (view === "clone" && byId("voiceSelect").value) {
        // A cancelled panel must leave the saved voice selected and usable.
        const picker = document.createElement("input");
        picker.type = "file"; picker.accept = byId("referenceAudio").accept; picker.hidden = true;
        document.body.append(picker);
        picker.addEventListener("change", () => {
          if (picker.files.length) {
            const select = byId("voiceSelect"); select.value = ""; select.dispatchEvent(new Event("change"));
            byId("referenceAudio").files = picker.files;
            byId("referenceAudio").dispatchEvent(new Event("change", { bubbles: true }));
          }
          picker.remove();
        }, { once: true });
        picker.addEventListener("cancel", () => picker.remove(), { once: true });
        picker.click();
        return;
      }
      if (view === "asr") byId("asrFileMode").click();
      const inputs = { clone: "referenceAudio", vc: "vcMedia", asr: "asrMedia", dub: "dubBundleImport" };
      byId(inputs[view]).click();
    },
    primaryAction() {
      if (document.querySelector("dialog[open]")) return;
      if (currentView() === "asr" && !byId("asrLiveControls").hidden) {
        const liveButton = byId(byId("asrLiveStart").hidden ? "asrLiveStop" : "asrLiveStart");
        if (!liveButton.disabled) liveButton.click();
        return;
      }
      const buttons = { clone: "generateButton", vc: "vcStartButton", asr: "asrStartButton", dub: byId("dubEditor").hidden ? "createDubButton" : "dubGenerateAll" };
      const button = byId(buttons[currentView()]);
      if (button && !button.disabled && button.getClientRects().length) button.click();
    },
    save() {
      const saved = saveDraft();
      const view = currentView();
      const button = byId(view === "dub" ? "dubSaveButton" : "saveTranscriptButton");
      if (["asr", "dub"].includes(view) && button && !button.disabled && button.getClientRects().length) button.click();
      else announce(saved ? "Text draft saved on this Mac" : "Draft could not be saved. Keep this window open.");
    },
    hasUnsavedChanges() {
      saveDraft();
      return hasUnsavedEdits()
        || [...document.querySelectorAll('input[type="file"]')].some((input) => input.files.length > 0)
        || [...document.querySelectorAll(".record-stop")].some((button) => !button.hidden);
    },
  });
  window.timbreloomCommands.selectView(window.timbreloomDesktop.initialView || currentView());
  history.scrollRestoration = "manual";
  window.scrollTo({ top: 0, behavior: "instant" });
  notifyDesktop("ready", { view: currentView() });
}
