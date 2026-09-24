// Add a Colab-style "Run" button to every code cell's prompt gutter ([ ]:),
// always visible regardless of window width. See custom.css for why this
// lives here instead of in JupyterLab's built-in (and width-sensitive)
// per-cell toolbar.
//
// There's no extension API for this in a static JupyterLite build, so it
// works directly against the DOM: a MutationObserver adds the button to any
// code cell's prompt that doesn't have one yet (notebooks add/remove/reorder
// cells constantly), and each click resolves its own cell's *current* index
// at click time -- never a cached one -- via `window.jupyterapp`, which
// JupyterLite exposes globally because jupyter-lite.json sets
// "exposeAppInBrowser": true.
(function () {
  const RUN_ICON =
    '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">' +
    '<path fill="currentColor" d="M8 5v14l11-7z"/></svg>';

  function findNotebookPanel(cellNode) {
    const app = window.jupyterapp;
    if (!app) return null;
    const current = app.shell.currentWidget;
    if (current && current.content && Array.isArray(current.content.widgets)) {
      if (current.content.widgets.some((w) => w.node === cellNode || w.node.contains(cellNode))) {
        return current;
      }
    }
    // fall back to scanning every open document if the click didn't happen
    // in the front-most tab
    const iter = app.shell.widgets ? app.shell.widgets('main') : [];
    for (const w of iter) {
      if (w.content && Array.isArray(w.content.widgets)) {
        if (w.content.widgets.some((cw) => cw.node === cellNode || cw.node.contains(cellNode))) {
          return w;
        }
      }
    }
    return null;
  }

  function runCell(promptNode) {
    const cellNode = promptNode.closest('.jp-Cell');
    if (!cellNode) return;
    const panel = findNotebookPanel(cellNode);
    if (!panel) return;
    const index = panel.content.widgets.findIndex((w) => w.node === cellNode);
    if (index === -1) return;
    panel.content.activeCellIndex = index;
    window.jupyterapp.commands.execute('notebook:run-cell-and-select-next');
  }

  function attachButtons() {
    const prompts = document.querySelectorAll(
      '.jp-CodeCell .jp-InputArea-prompt:not([data-ir-run-attached])',
    );
    prompts.forEach((prompt) => {
      prompt.setAttribute('data-ir-run-attached', '1');
      const btn = document.createElement('button');
      btn.className = 'ir-run-button';
      btn.type = 'button';
      btn.title = 'Run this cell';
      btn.setAttribute('aria-label', 'Run this cell');
      btn.innerHTML = RUN_ICON;
      btn.addEventListener('click', (evt) => {
        evt.preventDefault();
        evt.stopPropagation();
        runCell(prompt);
      });
      prompt.prepend(btn);
    });
  }

  attachButtons();
  new MutationObserver(attachButtons).observe(document.body, {
    childList: true,
    subtree: true,
  });
})();
