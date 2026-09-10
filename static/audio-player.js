export function createProgressiveAudioPlayer({ card, audio, status, toggle, waitingLabel }) {
  let chunks = [];
  let total = 0;
  let cursor = 0;
  let follow = false;
  let awaitingNext = false;
  let complete = false;
  let streamKind = "generated";
  let jobKey = "";
  let internalSourceChange = false;

  function statusText() {
    if (!chunks.length) return waitingLabel;
    if (streamKind === "source") {
      return audio.paused ? "原始音轨已准备，可以边转录边听。" : "正在播放原始音轨，转录在后台继续。";
    }
    if (awaitingNext) return `已听到当前进度，等待第 ${cursor + 1} 段生成。`;
    const current = Math.min(cursor + 1, chunks.length);
    const state = audio.paused ? "可播放" : "正在连续播放";
    return `已生成 ${chunks.length} / ${total || chunks.length} 段 · ${state}第 ${current} 段。`;
  }

  function updateUi() {
    status.textContent = statusText();
    toggle.disabled = chunks.length === 0;
    if (!chunks.length) {
      toggle.textContent = waitingLabel;
    } else if (!audio.paused && follow) {
      toggle.textContent = "暂停连续播放";
    } else if (streamKind === "source") {
      toggle.textContent = audio.ended ? "重新播放原声" : "播放原声";
    } else if (audio.ended && complete) {
      toggle.textContent = "从头连续播放";
    } else {
      toggle.textContent = "连续播放已完成部分";
    }
  }

  async function loadChunk(index, autoplay = false) {
    if (index < 0 || index >= chunks.length) return;
    cursor = index;
    awaitingNext = false;
    const chunk = chunks[index];
    const separator = chunk.audio_url.includes("?") ? "&" : "?";
    internalSourceChange = true;
    audio.src = `${chunk.audio_url}${separator}stream=${encodeURIComponent(jobKey)}`;
    audio.load();
    window.setTimeout(() => { internalSourceChange = false; }, 250);
    updateUi();
    if (autoplay) {
      try {
        await audio.play();
      } catch {
        follow = false;
        updateUi();
      }
    }
  }

  audio.addEventListener("play", () => {
    follow = true;
    awaitingNext = false;
    updateUi();
  });
  audio.addEventListener("loadedmetadata", () => {
    internalSourceChange = false;
  });
  audio.addEventListener("pause", () => {
    queueMicrotask(() => {
      if (!internalSourceChange && !audio.ended) follow = false;
      updateUi();
    });
  });
  audio.addEventListener("ended", () => {
    if (cursor + 1 < chunks.length) {
      loadChunk(cursor + 1, follow);
      return;
    }
    if (follow && !complete) {
      cursor = chunks.length;
      awaitingNext = true;
    } else {
      follow = false;
    }
    updateUi();
  });
  audio.addEventListener("error", () => {
    if (!audio.getAttribute("src")) return;
    follow = false;
    status.textContent = "这一段暂时无法播放，可以等待下一次进度刷新后重试。";
    toggle.textContent = "重试播放";
  });

  toggle.addEventListener("click", async () => {
    if (!chunks.length) return;
    if (!audio.paused) {
      follow = false;
      audio.pause();
      updateUi();
      return;
    }
    follow = true;
    if (cursor >= chunks.length || audio.ended || !audio.getAttribute("src")) {
      await loadChunk(cursor >= chunks.length || complete ? 0 : cursor, true);
      return;
    }
    try {
      await audio.play();
    } catch {
      follow = false;
      updateUi();
    }
  });

  return {
    update(stream, nextJobKey) {
      if (!stream) return;
      if (jobKey !== nextJobKey) {
        this.reset(false);
        jobKey = nextJobKey;
      }
      chunks = Array.isArray(stream.chunks) ? stream.chunks : [];
      total = Number(stream.total || chunks.length);
      complete = Boolean(stream.complete);
      streamKind = stream.kind || "generated";
      card.hidden = complete && chunks.length === 0;
      if (card.hidden) return;
      if (!audio.getAttribute("src") && chunks.length) loadChunk(0, false);
      if (awaitingNext && cursor < chunks.length) loadChunk(cursor, follow);
      updateUi();
    },
    reset(hide = true) {
      chunks = [];
      total = 0;
      cursor = 0;
      follow = false;
      awaitingNext = false;
      complete = false;
      streamKind = "generated";
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      toggle.disabled = true;
      toggle.textContent = waitingLabel;
      status.textContent = waitingLabel;
      if (hide) card.hidden = true;
    },
  };
}
