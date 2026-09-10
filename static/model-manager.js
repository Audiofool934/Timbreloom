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
  const pending = new Set();
  const active = new Set(["downloading", "verifying", "installing"]);
  let timer;
  let refreshing;
  let previousReady = "";

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };

  for (const [view, modelId] of [["clone", "qwen"], ["vc", "seed-vc"], ["asr", "whisper"], ["dub", "qwen"]]) {
    const banner = element("section", "model-required");
    banner.hidden = true;
    const copy = element("div");
    const title = element("strong");
    const description = element("p", "", "模型单独下载，准备好后即可离线使用。现有资料仍可查看与编辑。");
    const button = element("button", "quiet-button", "选择下载");
    button.type = "button";
    button.addEventListener("click", () => open(modelId));
    copy.append(title, description);
    banner.append(copy, button);
    document.querySelector(`#${view}View > .hero, #${view}View > .asr-hero`).after(banner);
    banners.set(view, { banner, title, button, modelId });
  }

  function buildCard(model) {
    const card = element("article", "model-download-card");
    card.id = `model-${model.id}`;
    const heading = element("div", "model-download-heading");
    const title = element("div");
    title.append(element("p", "model-purpose", model.purpose), element("h3", "", model.name));
    const size = element("span", "model-download-size", formatModelBytes(model.bytes));
    heading.append(title, size);
    const description = element("p", "model-download-description", model.description);
    const progress = element("progress");
    progress.max = model.bytes;
    progress.setAttribute("aria-label", `${model.name} 下载进度`);
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
    sources.append(element("summary", "", "来源与许可"));
    for (const source of model.sources) {
      const line = element("p");
      const link = element("a", "", source.repository);
      link.href = `https://huggingface.co/${source.repository}/tree/${source.revision}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      line.append(link, document.createTextNode(` · ${source.license || "详见模型说明"}`));
      sources.append(line);
    }
    card.append(heading, description, progress, bottom, sources);
    catalog.append(card);
    cards.set(model.id, { card, progress, message, amount, button });
  }

  function render(payload) {
    document.querySelector("#modelDirectory").textContent = payload.directory;
    for (const model of payload.models) {
      models.set(model.id, model);
      if (!cards.has(model.id)) buildCard(model);
      const { card, progress, message, amount, button } = cards.get(model.id);
      card.dataset.state = model.state;
      progress.value = model.downloaded_bytes;
      progress.hidden = !active.has(model.state) && !["paused", "error"].includes(model.state);
      message.textContent = model.message;
      amount.textContent = model.ready ? "已保存在本机" : `${formatModelBytes(model.downloaded_bytes)} / ${formatModelBytes(model.bytes)}`;
      button.disabled = model.ready || pending.has(model.id) || model.state === "installing";
      button.textContent = model.ready ? "已下载" : active.has(model.state) ? "暂停" : model.state === "paused" ? "继续下载" : model.state === "error" ? "重试下载" : `下载 ${formatModelBytes(model.bytes)}`;
      button.setAttribute("aria-label", `${button.textContent} ${model.name}`);
    }
    for (const { banner, title, button, modelId } of banners.values()) {
      const model = models.get(modelId);
      if (!model) continue;
      banner.hidden = model.ready;
      title.textContent = active.has(model.state) ? `${model.name} 正在下载` : `${model.purpose}需要 ${model.name}`;
      button.textContent = active.has(model.state) ? "查看下载" : "选择下载";
    }
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

  async function refresh() {
    if (refreshing) return refreshing;
    refreshing = (async () => {
      try {
        const response = await fetch("/api/models", { cache: "no-store" });
        if (!response.ok) throw new Error("无法读取模型状态，请重试连接。");
        render(await response.json());
        error.hidden = true;
        return true;
      } catch (failure) {
        error.textContent = failure.message || "无法连接本地服务，请稍后重试。";
        error.hidden = false;
        clearTimeout(timer);
        if (dialog.open) timer = window.setTimeout(refresh, 3000);
        return false;
      } finally { refreshing = null; }
    })();
    return refreshing;
  }

  async function transfer(modelId) {
    if (pending.has(modelId)) return;
    pending.add(modelId);
    cards.get(modelId).button.disabled = true;
    try {
      const action = active.has(models.get(modelId).state) ? "pause" : "download";
      const response = await fetch(`/api/models/${modelId}/${action}`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "暂时无法下载，请重试。");
      render(payload);
      error.hidden = true;
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      pending.delete(modelId);
      const model = models.get(modelId);
      cards.get(modelId).button.disabled = model.ready || model.state === "installing";
    }
  }

  async function open(modelId) {
    if (!dialog.open) dialog.showModal();
    await refresh();
    if (modelId && cards.has(modelId)) {
      cards.get(modelId).card.scrollIntoView({ block: "nearest" });
      cards.get(modelId).button.focus({ preventScroll: true });
    }
  }

  document.querySelector("#manageModelsButton").addEventListener("click", () => open());
  document.querySelector("#closeModelManager").addEventListener("click", () => dialog.close());
  window.addEventListener("timbreloom-open-models", () => open());
  window.addEventListener("beforeunload", () => clearTimeout(timer));
  refresh();
  return {
    open,
    async ensure(modelId) {
      if (models.get(modelId)?.ready) return true;
      if (await refresh() && models.get(modelId)?.ready) return true;
      await open(modelId);
      return false;
    },
  };
}
