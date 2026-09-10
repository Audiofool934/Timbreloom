import { installDesktopAudio } from "./desktop-audio.js?v=2";

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
    ["clone", "声音克隆", "选择一个音色，把想说的话写下来。"],
    ["vc", "原声换色", "保留表演的节奏、停顿与情绪，只改变声音的质感。"],
    ["asr", "本地转录", "从一段声音开始，留下可编辑的文字与字幕。"],
    ["dub", "配音项目", "逐句打磨台词与声音，让配音回到画面的时间线上。"],
  ];
  for (const [id, title, description] of headings) {
    const section = byId(`${id}View`);
    section.querySelector("h1").textContent = title;
    section.querySelector(".lede").textContent = description;
  }
  const labels = {
    "LOCAL ARCHIVE": "保存在这台 Mac", "LOCAL CONVERSION ARCHIVE": "保存在这台 Mac", "LOCAL DUB ARCHIVE": "保存在这台 Mac",
    "SAVED VOICE": "已保存音色", "LONG-FORM GENERATION": "语音生成", "GENERATED LOCALLY": "本地生成",
    "LOCAL TRANSCRIPTION": "音频转录", "EDITABLE TRANSCRIPT": "文字与字幕", "CREATE VOICE": "从片段保存音色",
    "PERSISTENT DUB PROJECT": "配音工作台", "ORIGINAL TIMECODE MAP": "原始时间线", "CAST & VOICE ASSIGNMENT": "音色分配",
    "PERSISTENT SEGMENT RENDER": "片段生成", "TIMELINE EXPORT READY": "导出完成", "LIVE PLAYBACK": "连续试听",
    "GEMINI · OPTIONAL CLOUD": "Gemini · 可选云端", "GEMINI TRANSLATION · OPTIONAL CLOUD": "Gemini · 可选云端",
    "NATIVE SPEECH-TO-SPEECH": "音色转换", "PERFORMANCE PRESERVED": "保留原始表演", "LOCAL VOICE CONVERSION": "音色转换", "VOICE CONVERSION COMPLETE": "转换完成",
  };
  document.querySelectorAll(".result-kicker, .action-label, .stream-kicker, .saved-label").forEach((element) => {
    const label = labels[element.textContent.trim()];
    if (!label) return;
    const text = [...element.childNodes].find((node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
    if (text) text.textContent = label;
  });
  document.querySelector("#asrForm .local-engine-note p").textContent = "本地识别 · 带词级时间戳";
  byId("vcRtfMetric").previousElementSibling.textContent = "耗时 / 时长";
  document.querySelector(".target-panel h2").textContent = "生成文稿";
  document.querySelector(".target-panel .panel-heading p").textContent = "按标点自然分段，长文也可以连续生成。";
  byId("targetText").placeholder = "写下一句话，或粘贴一整篇文稿。\n\n用标点和换行，安排声音的停顿。";
  document.querySelector(".prosody-guide summary strong").textContent = "标点与停顿";
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
  for (const [id, name] of [["dubRoleName", "新角色名称"], ["dubRoleVoice", "新角色音色"], ["dubApplyRole", "应用角色"]]) {
    byId(id)?.setAttribute("aria-label", name);
  }
  document.querySelectorAll(".dropzone input").forEach((input) => {
    input.setAttribute("aria-label", input.closest(".dropzone").querySelector("strong").textContent);
  });
  for (const [id, title] of [["generateButton", "生成语音 · ⌘↩"], ["vcStartButton", "开始换色 · ⌘↩"],
    ["asrStartButton", "开始转录 · ⌘↩"], ["saveTranscriptButton", "保存文字修改 · ⌘S"], ["dubSaveButton", "保存项目 · ⌘S"]]) {
    byId(id)?.setAttribute("title", title);
  }

  // Library empty states remain connected to the real import and creation workflows.
  for (const [id, symbol, title, hint, label, action] of [
    ["vcJobList", "waveform", "还没有换色作品", "导入原始录音，选择音色后开始。", "导入录音", () => window.timbreloomCommands.openFile()],
    ["transcriptList", "text.alignleft", "声音会在这里变成文字", "导入音频或视频，完成的转录会自动保留。", "导入媒体", () => window.timbreloomCommands.openFile()],
    ["dubProjectList", "rectangle.stack", "开始你的第一个配音项目", "先准备一份转录，再为台词选择声音。", "前往本地转录", () => window.timbreloomCommands.selectView("asr")],
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
  dismiss.setAttribute("aria-label", "关闭错误提示"); dismiss.append(icon("xmark"));
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
      const inputs = { clone: "referenceAudio", vc: "vcMedia", asr: "asrMedia", dub: "dubBundleImport" };
      byId(inputs[view]).click();
    },
    primaryAction() {
      if (document.querySelector("dialog[open]")) return;
      const buttons = { clone: "generateButton", vc: "vcStartButton", asr: "asrStartButton", dub: byId("dubEditor").hidden ? "createDubButton" : "dubGenerateAll" };
      const button = byId(buttons[currentView()]);
      if (button && !button.disabled && button.getClientRects().length) button.click();
    },
    save() {
      const saved = saveDraft();
      const view = currentView();
      const button = byId(view === "dub" ? "dubSaveButton" : "saveTranscriptButton");
      if (["asr", "dub"].includes(view) && button && !button.disabled && button.getClientRects().length) button.click();
      else announce(saved ? "文字草稿已保存在这台 Mac" : "草稿暂时无法保存，请保留窗口");
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
