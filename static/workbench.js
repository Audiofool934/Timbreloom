// Shared workspace controls. They never change stored projects or audio jobs.
export function installWorkbench() {
  installLibrarySearch();
  installEditorFocus();
  document.querySelectorAll('textarea').forEach(field => {
    field.spellcheck = true;
  });
}

function installLibrarySearch() {
  for (const [id, label] of [
    ['cloneJobList', 'speech history'], ['vcJobList', 'conversion history'],
    ['transcriptList', 'transcripts'], ['dubProjectList', 'projects'],
  ]) {
    const list = document.getElementById(id);
    if (!list) continue;
    const controls = document.createElement('div');
    controls.className = 'library-search';
    const input = document.createElement('input');
    input.type = 'search'; input.id = `${id}Search`;
    input.placeholder = `Search ${label}`;
    input.setAttribute('aria-label', `Search ${label}`);
    input.setAttribute('aria-controls', id);
    const count = document.createElement('span');
    count.className = 'library-count';
    count.id = `${id}Count`;
    count.setAttribute('role', 'status');
    input.setAttribute('aria-describedby', count.id);
    controls.append(input, count);
    const empty = document.createElement('p');
    empty.className = 'library-no-results'; empty.hidden = true;
    empty.textContent = 'No matches. Try another name or clear the search.';
    list.before(controls); list.after(empty);
    const filter = () => {
      const query = input.value.trim().toLocaleLowerCase();
      const rows = [...list.children].filter(row => row.matches('.history-item, .transcript-list-item'));
      let visible = 0;
      for (const row of rows) {
        row.hidden = Boolean(query && !row.textContent.toLocaleLowerCase().includes(query));
        if (!row.hidden) visible++;
      }
      const text = query ? `${visible} of ${rows.length}` : `${rows.length} saved`;
      if (count.textContent !== text) count.textContent = text;
      empty.hidden = !query || visible > 0 || rows.length === 0;
      controls.hidden = rows.length === 0 && !query;
    };
    input.addEventListener('input', filter);
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape' && input.value) {
        event.preventDefault(); event.stopPropagation(); input.value = ''; filter();
      }
    });
    new MutationObserver(filter).observe(list, { childList: true, subtree: true, characterData: true });
    filter();
  }
}

function installEditorFocus() {
  for (const [id, editorId, setupSelector] of [
    ['asr', 'transcriptEditor', '.asr-workspace'], ['dub', 'dubEditor', '.dub-intake-grid'],
  ]) {
    const view = document.getElementById(`${id}View`);
    const editor = document.getElementById(editorId);
    const setup = view?.querySelector(setupSelector);
    if (!editor || !setup) continue;
    setup.id ||= `${id}Setup`;
    const bar = document.createElement('div');
    bar.className = 'editor-focus-bar'; bar.hidden = editor.hidden;
    const hint = document.createElement('span');
    hint.textContent = 'Keep the words in view.';
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'quiet-button editor-focus-button';
    button.id = `${id}FocusEditor`;
    button.textContent = 'Focus editor';
    button.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-controls', setup.id);
    bar.append(hint, button); editor.before(bar);
    const reset = () => {
      setup.hidden = false; button.setAttribute('aria-pressed', 'false');
      button.textContent = 'Focus editor'; hint.textContent = 'Keep the words in view.';
      view.classList.remove('editor-focused');
    };
    button.addEventListener('click', () => {
      const focus = button.getAttribute('aria-pressed') !== 'true';
      setup.hidden = focus;
      button.setAttribute('aria-pressed', String(focus));
      button.textContent = focus ? 'Show import & library' : 'Focus editor';
      hint.textContent = focus ? 'Your import settings and library are kept.' : 'Keep the words in view.';
      view.classList.toggle('editor-focused', focus);
      bar.scrollIntoView({ block: 'start', behavior: 'instant' });
      button.focus({ preventScroll: true });
    });
    new MutationObserver(() => {
      bar.hidden = editor.hidden;
      if (editor.hidden) reset();
    }).observe(editor, { attributes: true, attributeFilter: ['hidden'] });
    // Native import and model controls must remain reachable while editing.
    setup.addEventListener('focusin', () => { if (setup.hidden) reset(); });
    view.addEventListener('timbreloom-reveal-setup', reset);
  }
}
