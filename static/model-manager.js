export function formatModelBytes(bytes) {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
  return `${Math.round(bytes / 1e3)} KB`;
}

export function installModelManager() {
  const dialog = document.querySelector("#modelManager");
  const catalog = document.querySelector("#modelCatalog");
  const error = document.querySelector("#modelDownloadError");
  const cards = new Map();
  const models = new Map();
  const banners = new Map();
  const pending = new Map();
  const active = new Set(["downloading", "verifying", "installing"]);
  const stateLabels = {
    ready: "Ready offline", missing: "Not downloaded", downloading: "Downloading",
    verifying: "Verifying", installing: "Installing", paused: "Paused", error: "Needs attention",
  };
  const actionLabels = {
    downloading: "Pause download", verifying: "Pause download", installing: "Installing…",
    paused: "Resume download", error: "Retry download",
  };
  let timer;
  let refreshing;
  let previousReady = "";
  let returnFocus;
  let openRequest = 0;

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };

  const header = element("div", "model-manager-header");
  const intro = dialog.querySelector(".model-manager-intro");
  intro.id = "modelManagerDescription";
  dialog.setAttribute("aria-describedby", intro.id);
  header.append(dialog.querySelector(".model-manager-heading"), dialog.querySelector("h2"), intro);
  const overview = element("div", "model-manager-overview");
  const readyCount = element("strong", "", "Loading model status…");
  const downloadedSize = element("span");
  overview.append(readyCount, downloadedSize);
  header.append(overview, error);
  dialog.prepend(header);
  catalog.setAttribute("role", "list");
  catalog.setAttribute("aria-label", "Available models");
  const storage = dialog.querySelector(".model-manager-storage");
  const location = element("details", "model-storage-location");
  location.append(element("summary", "", "Model storage location"), document.querySelector("#modelDirectory"));
  storage.firstElementChild.replaceWith(location);

  for (const [view, modelId] of [["clone", "qwen"], ["vc", "seed-vc"], ["asr", "whisper"], ["dub", "qwen"]]) {
    const banner = element("section", "model-required");
    banner.hidden = true;
    const copy = element("div");
    const title = element("strong");
    const description = element("p", "", "Download the model to use this feature offline. You can still view and edit your library.");
    const button = element("button", "quiet-button", "Choose models");
    button.type = "button";
    button.addEventListener("click", () => open(banners.get(view).modelId));
    copy.append(title, description);
    banner.append(copy, button);
    document.querySelector(`#${view}View > .hero, #${view}View > .asr-hero`).after(banner);
    banners.set(view, { banner, title, button, modelId });
  }

  function buildCard(model) {
    const card = element("article", "model-download-card");
    card.id = `model-${model.id}`;
    card.tabIndex = -1;
    card.setAttribute("role", "listitem");
    const heading = element("div", "model-download-heading");
    const title = element("div");
    const name = element("h3", "", model.name);
    name.id = `${card.id}-title`;
    card.setAttribute("aria-labelledby", name.id);
    title.append(element("p", "model-purpose", model.purpose), name);
    const metadata = element("div", "model-download-metadata");
    const badge = element("span", "model-state-badge");
    const size = element("span", "model-download-size", formatModelBytes(model.bytes));
    size.title = "Total download size";
    metadata.append(badge, size);
    heading.append(title, metadata);
    const description = element("p", "model-download-description", model.description);
    const progress = element("progress");
    progress.max = model.bytes;
    progress.setAttribute("aria-label", `${model.name} download progress`);
    const bottom = element("div", "model-download-bottom");
    const status = element("div", "model-download-status");
    const message = element("p");
    message.setAttribute("role", "status");
    const amount = element("small");
    status.append(message, amount);
    const button = element("button", "quiet-button model-download-action");
    button.type = "button";
    button.addEventListener("click", () => transfer(model.id));
    bottom.append(status, button);
    const sources = element("details", "model-download-sources");
    sources.append(element("summary", "", "Sources and licenses"));
    for (const source of model.sources) {
      const line = element("p");
      const link = element("a", "", source.repository);
      link.href = source.url || `https://huggingface.co/${source.repository}/tree/${source.revision}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      line.append(link, document.createTextNode(` · ${source.license || "See the model documentation"}`));
      sources.append(line);
    }
    card.append(heading, description, progress, bottom, sources);
    catalog.append(card);
    cards.set(model.id, { card, progress, message, amount, button, badge });
  }

  function renderCard(model) {
    const { card, progress, message, amount, button, badge } = cards.get(model.id);
    const state = model.ready ? "ready" : model.state;
    const downloaded = Math.min(Math.max(0, model.downloaded_bytes || 0), model.bytes);
    const percent = model.bytes > 0 ? Math.floor(downloaded / model.bytes * 100) : 0;
    card.dataset.state = state;
    badge.textContent = stateLabels[state] || "Not downloaded";
    progress.value = downloaded;
    progress.hidden = model.ready || (!active.has(state) && !["paused", "error"].includes(state));
    progress.setAttribute("aria-valuetext", `${percent}% · ${formatModelBytes(downloaded)} of ${formatModelBytes(model.bytes)}`);
    if (message.textContent !== model.message) message.textContent = model.message;
    amount.textContent = model.ready ? "Saved on this Mac" : downloaded > 0 || active.has(state)
      ? `${percent}% · ${formatModelBytes(downloaded)} of ${formatModelBytes(model.bytes)}`
      : "Download once, then use offline";
    if (model.ready && document.activeElement === button) card.focus({ preventScroll: true });
    button.hidden = model.ready;
    button.disabled = pending.has(model.id) || state === "installing";
    button.dataset.primary = String(!active.has(state));
    button.textContent = pending.has(model.id)
      ? (pending.get(model.id) === "pause" ? "Pausing…" : "Starting…")
      : (actionLabels[state] || "Download");
    button.setAttribute("aria-label", `${button.textContent} ${model.name}`);
  }

  function render(payload) {
    document.querySelector("#modelDirectory").textContent = payload.directory;
    for (const model of payload.models) {
      models.set(model.id, model);
      if (!cards.has(model.id)) buildCard(model);
      renderCard(model);
    }
    const readyModels = payload.models.filter(model => model.ready).length;
    const activeModels = payload.models.filter(model => active.has(model.state)).length;
    const totalDownloaded = payload.models.reduce((total, model) => total + (model.downloaded_bytes || 0), 0);
    readyCount.textContent = `${readyModels} of ${payload.models.length} ready`;
    downloadedSize.textContent = `${formatModelBytes(totalDownloaded)} downloaded${activeModels ? ` · ${activeModels} in progress` : ""}`;
    renderBanners();
    const ready = payload.models.map(model => `${model.id}:${model.ready}`).join(",");
    if (ready !== previousReady) {
      previousReady = ready;
      window.dispatchEvent(new Event("timbreloom-models-changed"));
    }
    clearTimeout(timer);
    if (dialog.open || payload.models.some(model => active.has(model.state))) {
      timer = window.setTimeout(refresh, payload.models.some(model => active.has(model.state)) ? 1000 : 5000);
    }
  }

  function renderBanners() {
    for (const { banner, title, button, modelId } of banners.values()) {
      const model = models.get(modelId);
      if (!model) continue;
      banner.hidden = model.ready;
      title.textContent = active.has(model.state) ? `Downloading ${model.name}` : `${model.purpose} requires ${model.name}`;
      button.textContent = active.has(model.state) ? "View download" : "Choose models";
    }
  }

  async function refresh() {
    if (refreshing) return refreshing;
    refreshing = (async () => {
      try {
        const response = await fetch("/api/models", { cache: "no-store" });
        if (!response.ok) throw new Error("Cannot read model status. Retry the connection.");
        render(await response.json());
        error.hidden = true;
        return true;
      } catch (failure) {
        if (!models.size) readyCount.textContent = "Model status unavailable";
        error.textContent = failure.message || "Cannot connect to the local service. Try again shortly.";
        error.hidden = false;
        clearTimeout(timer);
        if (dialog.open) timer = window.setTimeout(refresh, 3000);
        return false;
      } finally { refreshing = null; }
    })();
    return refreshing;
  }

  async function transfer(modelId) {
    const model = models.get(modelId);
    if (pending.has(modelId) || model.ready || model.state === "installing") return;
    const action = active.has(model.state) ? "pause" : "download";
    pending.set(modelId, action);
    renderCard(model);
    try {
      const response = await fetch(`/api/models/${modelId}/${action}`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Cannot download right now. Try again.");
      render(payload);
      error.hidden = true;
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      pending.delete(modelId);
      renderCard(models.get(modelId));
    }
  }

  async function open(modelId) {
    const request = ++openRequest;
    if (!dialog.open) {
      returnFocus = document.activeElement;
      dialog.showModal();
    }
    await refresh();
    if (!dialog.open || request !== openRequest) return;
    if (modelId && cards.has(modelId)) {
      const { card, button } = cards.get(modelId);
      card.scrollIntoView({ block: "nearest" });
      (button.hidden || button.disabled ? card : button).focus({ preventScroll: true });
    }
  }

  document.querySelector("#manageModelsButton").addEventListener("click", () => open());
  document.querySelector("#closeModelManager").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    openRequest += 1;
    if (![...models.values()].some(model => active.has(model.state))) clearTimeout(timer);
    if (returnFocus?.isConnected && !returnFocus.disabled) returnFocus.focus({ preventScroll: true });
    returnFocus = null;
  });
  window.addEventListener("timbreloom-open-models", () => open());
  window.addEventListener("beforeunload", () => clearTimeout(timer));
  refresh();
  return {
    open,
    setRequiredModel(view, modelId) {
      banners.get(view).modelId = modelId;
      renderBanners();
    },
    async ensure(modelId) {
      if (models.get(modelId)?.ready) return true;
      if (await refresh() && models.get(modelId)?.ready) return true;
      await open(modelId);
      return false;
    },
  };
}
