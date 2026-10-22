const LANGUAGE_NAMES = { auto: "Auto-detect", en: "English", zh: "Chinese", ja: "Japanese", ko: "Korean",
  de: "German", fr: "French", es: "Spanish", it: "Italian", pt: "Portuguese", ru: "Russian" };

export function installAsrModels(manager) {
  const select = document.getElementById("asrModel");
  const language = document.getElementById("asrLanguage");
  const prompt = document.getElementById("asrPrompt");
  const description = document.getElementById("asrModelDescription");
  const manage = document.getElementById("asrManageModel");
  let models = [];
  let busy = false;
  let refreshing;
  let retry;
  let preferredLanguage = language.value;
  let selected = window.localStorage.getItem("timbreloomAsrModel") || "whisper";

  const current = () => models.find(model => model.id === selected);
  function render() {
    const model = current();
    if (!model) return;
    select.value = selected;
    select.disabled = busy;
    language.replaceChildren(...model.languages.map(value => new Option(LANGUAGE_NAMES[value] || value, value)));
    language.value = model.languages.includes(preferredLanguage) ? preferredLanguage : model.languages[0];
    language.disabled = busy || model.languages.length === 1;
    prompt.disabled = busy || !model.supports_hints;
    document.getElementById("asrHintsAvailability").textContent = model.supports_hints ? "Optional" : "Unavailable for this model";
    prompt.placeholder = model.supports_hints ? "Names, technical terms, project names" : "Not supported by this model";
    description.textContent = model.description;
    document.getElementById("asrEngineName").textContent = model.name;
    document.getElementById("asrEngineDetail").textContent = `${model.timestamps === "word" ? "Word" : "Segment"} timestamps · Offline processing`;
    manage.textContent = model.ready ? "Manage models" : "Download model";
    manager.setRequiredModel("asr", selected);
  }

  async function refresh() {
    if (refreshing) return refreshing;
    refreshing = (async () => {
      try {
        const response = await fetch("/api/asr/models", { cache: "no-store" });
        if (!response.ok) throw new Error("Cannot read transcription models. Check the local service and try again.");
        const payload = await response.json();
        models = payload.models;
        window.clearTimeout(retry);
        if (!current()) selected = payload.default;
        select.replaceChildren(...models.map(model => new Option(`${model.name}${model.ready ? "" : " · Download needed"}`, model.id)));
        render();
      } catch (error) {
        description.textContent = error.message;
        window.clearTimeout(retry);
        retry = window.setTimeout(refresh, 2000);
      } finally { refreshing = null; }
    })();
    return refreshing;
  }

  select.addEventListener("change", () => {
    selected = select.value;
    window.localStorage.setItem("timbreloomAsrModel", selected);
    render();
  });
  language.addEventListener("change", () => { preferredLanguage = language.value; });
  manage.addEventListener("click", () => manager.open(selected));
  window.addEventListener("timbreloom-models-changed", refresh);
  window.addEventListener("beforeunload", () => window.clearTimeout(retry));
  const ready = refresh();
  return {
    ready,
    setBusy(value) { busy = value; render(); },
    settings() {
      const model = current();
      if (!model) throw new Error("Transcription models are still loading. Try again shortly.");
      return { model: selected, name: model.name, language: language.value, prompt: model.supports_hints ? prompt.value : "" };
    },
  };
}
