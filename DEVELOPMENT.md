# Development notes

A JupyterLite site where chemistry students drag in a GRAMS/AI `.spc` file or a Bruker
OPUS file and get a CSV, a plot, and a peak list. Everything runs in the browser via
Pyodide. Live site and student-facing usage instructions are in [README.md](README.md).

## Layout

- `content/` — the only files students see: `spc_to_csv.ipynb`, `spc_lab.py`, `spc_reader.py`, `opus_reader.py`
- `tools/build_notebook.py` — **the notebook is generated; edit this, not the .ipynb**
- `tools/make_test_spc.py` — writes synthetic `.spc` files in each supported variant

## Build and test

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tools/build_notebook.py content/spc_to_csv.ipynb
jupyter lite build --contents content --output-dir dist
python -m http.server -d dist 8000     # must be http://, not file://
```

Delete `.jupyterlite.doit.db` if a rebuild seems to ignore edits.

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
9. **`input()` needs `SharedArrayBuffer`, which needs cross-origin isolation.** The Pyodide
   kernel implements blocking `input()` prompts through `SharedArrayBuffer`, and browsers
   only expose that on pages served with `COOP`/`COEP` headers. GitHub Pages cannot send
   those headers, so on the deployed site `input()` may silently fall back to the default
   (see `ask()` in `spc_lab.py`) instead of prompting. Nothing breaks either way, but check
   `zoom()` on the actual deployed link before relying on prompts working live. Netlify and
   Cloudflare Pages can set those headers if interactive prompts turn out to matter.

## Formats

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
