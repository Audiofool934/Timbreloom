const statusNames = { queued: "Queued", running: "Processing", complete: "Complete", cancelled: "Stopped", error: "Failed" };

export function renderHistoryList({ element, jobs, selectedId, endpoint, emptyText, formatDate, readError, showError, onOpen, onRename, onDelete, openDisabled = false }) {
  element.replaceChildren();
  if (!jobs.length) {
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = emptyText;
    element.append(empty);
    return;
  }
  for (const job of jobs) {
    const id = job.job_id || job.id;
    const row = document.createElement("article");
    row.className = "history-item";
    row.dataset.jobId = id;
    if (id === selectedId) row.classList.add("is-active");
    const open = document.createElement("button");
    open.type = "button";
    open.className = "transcript-list-item history-open";
    open.disabled = openDisabled;
    open.setAttribute("aria-label", `Open ${job.title}`);
    open.setAttribute("aria-pressed", String(id === selectedId));
    if (openDisabled) open.title = "Wait for the current generation to finish before opening another recording.";
    const title = document.createElement("strong");
    title.textContent = job.title;
    const meta = document.createElement("span");
    meta.textContent = `${job.voice_name} · ${statusNames[job.status] || job.status}`;
    const date = document.createElement("small");
    date.textContent = formatDate(job.created_at);
    open.append(title, meta, date);
    open.addEventListener("click", () => onOpen(id).catch(error => showError(error.message)));
    const actions = document.createElement("div");
    actions.className = "history-actions";
    for (const action of ["rename", "delete"]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `history-action${action === "delete" ? " danger-text" : ""}`;
      button.textContent = action === "rename" ? "Rename" : "Delete";
      button.setAttribute("aria-label", `${button.textContent} ${job.title}`);
      if (action === "delete" && ["queued", "running"].includes(job.status)) {
        button.disabled = true;
        button.title = "Stop this job and wait for it to finish before deleting it.";
      }
      button.addEventListener("click", () => manageItem({ job, id, action, endpoint, readError, onRename, onDelete, showError }));
      actions.append(button);
    }
    row.append(open, actions);
    element.append(row);
  }
}

function manageItem({ job, id, action, endpoint, readError, onRename, onDelete, showError }) {
  const dialog = document.querySelector("#historyDialog");
  if (dialog.open) return;
  const form = document.querySelector("#historyDialogForm");
  const input = document.querySelector("#historyTitleInput");
  const cancel = document.querySelector("#historyDialogCancel");
  const submit = document.querySelector("#historyDialogSubmit");
  const error = document.querySelector("#historyDialogError");
  const deleting = action === "delete";
  document.querySelector("#historyDialogTitle").textContent = deleting ? "Delete this recording?" : "Rename recording";
  document.querySelector("#historyDialogDescription").textContent = deleting
    ? `“${job.title}” will be removed from history, along with its stored source and generated files. Saved voices and files you already exported are kept. This cannot be undone.`
    : "Give this recording a name you can find again.";
  document.querySelector("#historyTitleField").hidden = deleting;
  input.disabled = deleting;
  input.value = job.title;
  error.hidden = true;
  submit.textContent = deleting ? "Delete recording" : "Save name";
  submit.classList.toggle("danger-button", deleting);
  submit.disabled = cancel.disabled = false;
  let busy = false;
  const dismiss = () => dialog.close();
  const preventBusyCancel = event => { if (busy) event.preventDefault(); };
  const save = async event => {
    event.preventDefault();
    if (busy) return;
    if (!deleting && !input.value.trim()) {
      error.textContent = "Enter a name for this recording.";
      error.hidden = false;
      input.focus();
      return;
    }
    busy = true;
    submit.disabled = cancel.disabled = true;
    error.hidden = true;
    try {
      const response = await fetch(`${endpoint}/${id}`, deleting ? { method: "DELETE" } : {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: input.value.trim() }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const updated = await response.json();
      dialog.close();
      try { await (deleting ? onDelete(id) : onRename(updated)); }
      catch (failure) { showError(failure.message); }
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      busy = false;
      submit.disabled = cancel.disabled = false;
    }
  };
  form.addEventListener("submit", save);
  cancel.addEventListener("click", dismiss);
  dialog.addEventListener("cancel", preventBusyCancel);
  dialog.addEventListener("close", () => {
    form.removeEventListener("submit", save);
    cancel.removeEventListener("click", dismiss);
    dialog.removeEventListener("cancel", preventBusyCancel);
  }, { once: true });
  dialog.showModal();
  if (deleting) cancel.focus();
  else { input.focus(); input.select(); }
}
