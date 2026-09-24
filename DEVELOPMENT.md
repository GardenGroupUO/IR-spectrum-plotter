# Development notes

A JupyterLite site where chemistry students drag in a GRAMS/AI `.spc` file or a Bruker
OPUS file and get a CSV, a plot, and a peak list. Everything runs in the browser via
Pyodide. Live site and student-facing usage instructions are in [README.md](README.md).

## Layout

- `content/` — the only files students see: `spc_to_csv.ipynb`, `spc_lab.py`, `spc_reader.py`, `opus_reader.py`
- `tools/build_notebook.py` — **the notebook is generated; edit this, not the .ipynb**
- `tools/make_test_spc.py` — writes synthetic `.spc` files in each supported variant
- `static/custom.css` + `static/custom.js` + `tools/inject_custom_assets.py` — the green
  per-cell "Run" button in the `[ ]:` gutter. See constraint 10 below.

## Build and test

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tools/build_notebook.py content/spc_to_csv.ipynb
jupyter lite build --contents content --output-dir dist
python tools/inject_custom_assets.py dist
python -m http.server -d dist 8000     # must be http://, not file://
```

Delete `.jupyterlite.doit.db` if a rebuild seems to ignore edits.

**Browser caching while iterating locally.** `jupyter-lite.json`, `index.html`, and
`custom.js`/`custom.css` are all plain files served with no cache-control headers, so a
browser that has already visited `localhost:8000` once can keep serving stale copies after
a rebuild, even past a normal reload. If a change doesn't seem to take effect, use a
private/incognito window, a fresh port, or clear the site's storage and service workers
(DevTools → Application → Storage → "Clear site data") before concluding the build is
wrong. This cost real time during development of the Run button below — twice.

## Constraints that are easy to break

1. **Pyodide only preloads packages named in the notebook cell itself.** Each cell starts
   with `import matplotlib, numpy, pandas`. It looks redundant and is not — the kernel
   calls `loadPackagesFromImports()` on the cell source, and imports inside `spc_lab.py`
   are invisible to it. Any new third-party package must be named in the cell too.
2. **No scipy, no new runtime dependencies.** The SPC parser and the peak finder are both
   pure numpy on purpose, so nothing is downloaded at runtime and the notebook works
   offline once loaded.
3. **Each notebook cell must stand alone** (its own imports, runnable in any order). An
   earlier hidden setup cell caused `OSError: File '()' not found` when students ran a
   cell without it — IPython's automagic turned the undefined `run()` into `%run`.
4. **Avoid mathtext in plot labels.** Pyodide's matplotlib emits deprecation warnings from
   its Agg backend. `pretty_label()` defaults to Unicode superscripts instead.
5. **Files baked into `content/` cannot be deleted from the JupyterLite file panel.** They
   are served statically. For local testing, upload under a different name.
6. Old-format SPC files (`fversn` 0x4D) are deliberately unsupported, with a clear error.
7. **File format is decided by magic bytes, never by extension.** Bruker OPUS files are
   named with a number as the extension (`.0`, `.17`), so `find_spc()` sniffs the first two
   bytes of every file in the folder instead of globbing. `read_spectrum()` dispatches to
   `read_opus` or `read_spc`.
8. **Output names keep an OPUS extension**, because `.17` identifies the measurement:
   `Benzoic_acid_14_23.17` → `Benzoic_acid_14_23.17.csv`. `.spc` files drop theirs. See
   `_stem()` / `_out()` in `spc_lab.py`.
9. **`input()` prompts were verified working on GitHub Pages** (jupyterlite-pyodide-kernel
   0.8.6, tested via `zoom()` and `peaks()` on the live deployed site): typed values are
   accepted and take effect, even though `window.crossOriginIsolated` is `false` there and
   `SharedArrayBuffer` is unavailable (GitHub Pages cannot send the `COOP`/`COEP` headers
   that would require). This kernel version's stdin does not need it. If you upgrade
   `jupyterlite-pyodide-kernel`, re-check `zoom()` on the deployed link, since a future
   version could reintroduce a `SharedArrayBuffer` dependency; `ask()` in `spc_lab.py`
   silently falls back to the default and prints a notice if that ever happens, so nothing
   breaks, but prompts would stop being interactive.
10. **The per-cell "Run" button lives in the `[ ]:` prompt gutter, not JupyterLab's own
    per-cell toolbar, deliberately.** JupyterLab does have a built-in per-cell toolbar
    (top-right of the active cell — duplicate, move, insert, delete), addable to via
    `@jupyterlab/cell-toolbar-extension:plugin`'s `toolbar` setting. That was the first
    approach here, and it worked, but that toolbar hides itself (`jp-toolbar-overlap` class
    forcing `display: none`) whenever the cell isn't wide enough to fit it without covering
    code — which is often, especially with the file browser panel open. Forcing it visible
    with CSS just moves the problem: the toolbar then renders on top of the cell's own code
    on narrow windows. The `[ ]:` gutter is never hidden and never overlaps code (it is its
    own flex column, code starts to its right), so that's where `static/custom.js` inserts
    the button instead, walking `.jp-InputArea-prompt` elements directly since there is no
    supported extension point for this in a static JupyterLite build. A `MutationObserver`
    re-attaches it as cells are added; each click resolves its own cell's live index rather
    than a cached one, via `window.jupyterapp` (exposed globally because
    `exposeAppInBrowser: true` is set in `jupyter-lite.json`).

    Note for future reference: **a `jupyter-lite.json` at the project root only patches
    `dist/jupyter-lite.json`.** It does not reach `dist/lab/jupyter-lite.json` (or any
    other app's) — even though simple keys like `appName` appear to work everywhere, since
    those are baked into every app's `index.html` by a separate step that isn't how
    `settingsOverrides` is delivered. Overriding a JupyterLab *settings* key for the `lab`
    app specifically needs the source file at `<project-root>/lab/jupyter-lite.json`
    instead (jupyterlite_core only merges config files it finds at the root or in a folder
    matching a known app name — see the warning text in `jupyterlite_core`'s
    `addons/lite.py`). Not currently used by anything in this repo, since the toolbar
    approach it would have supported was replaced by the gutter button above, but it's the
    thing to reach for if a future JupyterLab *setting* (not a DOM/CSS change) needs
    overriding.
11. **JupyterLab's settings system cannot recolour an icon**, which is part of why the
    button above is custom DOM rather than a settings-driven toolbar item. The only
    supported "theme CSS override" mechanism
    (`@jupyterlab/apputils-extension:themes`) covers fonts and the error-output background
    only (`additionalProperties: false` in its schema — check
    `dist/build/schemas/@jupyterlab/apputils-extension/themes.json` after a build if this
    ever needs re-verifying). `static/custom.css` and `static/custom.js` are copied into
    `dist/lab/` and linked from `dist/lab/index.html` by `tools/inject_custom_assets.py`,
    which must run after every `jupyter lite build` (and does, in
    `.github/workflows/deploy.yml`).

`opus_reader.py` handles Bruker OPUS: magic `0x0A0AFEFE`, a 12-byte-per-entry block
directory, float32 data blocks each paired with a status block at `type | 0x0010` carrying
NPT/FXV/LXV. Absorbance (`0x100F`) is preferred when a file holds several block kinds;
the rest are listed in `meta['other_blocks']`. Both readers return the same `Spectrum`
object, so everything downstream is format-agnostic — keep it that way when adding formats.

Likely next formats, if asked: JCAMP-DX (`.dx`, `.jdx` — plain text, starts `##TITLE=`)
and Thermo OMNIC `.spa`.

## Peak picking

Tunables at the top of `spc_lab.py`: `PEAK_SENSITIVITY`, `PEAK_FLOOR`, `PEAK_NOISE_K`,
`PEAK_SMOOTH_CM`, `PEAK_TOP_N`, `PEAK_PICKING`.

Thresholds were calibrated against synthetic spectra; `PEAK_NOISE_K = 4` was the value that
held the peak count at exactly the number of real bands from clean data up to 0.02
absorbance noise. Re-check it against real instrument files before changing it.

Never add automatic functional-group assignment. Deliberate pedagogical choice.

**Known limitation:** a saturated, flat-topped band can be reported as two peaks at its
shoulders, an artifact of smoothing a clipped signal. The real band is always among the
results, but the peak count may come out one higher than expected. Spectra that are not
saturated are unaffected.

## Testing

There is no test suite yet. Verify changes by generating fixtures with
`tools/make_test_spc.py` and running the notebook headlessly with `nbclient`, including
`allow_stdin=False` to exercise the fallback when `input()` is unavailable.
