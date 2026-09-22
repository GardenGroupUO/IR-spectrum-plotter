# SPC → CSV → plot, in the browser

A JupyterLite site where students drag a GRAMS/AI `.spc` file onto the file panel,
run a few cells, and get a CSV plus a plot. No Python install, no accounts, no
server-side processing — the whole thing runs in the browser tab.

```
├── content/                  # everything students see
│   ├── spc_to_csv.ipynb      # the notebook
│   ├── spc_reader.py         # the SPC parser it imports
│   └── example_spectrum.spc  # a sample file so the notebook works before they upload
├── requirements.txt          # build-time only
├── jupyter-lite.json         # site config
└── .github/workflows/deploy.yml
```

`spc_reader.py` and `spc_lab.py` must sit in the same folder as the notebook — it imports both.

## How the notebook is arranged

Each code cell is three short lines:

```python
import matplotlib, numpy, pandas  # noqa: F401

from spc_lab import convert
convert()
```

Everything else — imports, plotting, error handling — lives in `spc_lab.py`, which
students never open.

Each cell imports what it needs, so **they work in any order and after a kernel restart**.
An earlier version kept the machinery in a hidden setup cell, which broke the moment
anyone ran a cell without running the hidden one first: `run()` was then undefined, and
IPython's automagic reinterpreted it as the `%run` magic, producing the baffling
`OSError: File '()' not found`. Self-contained cells remove that trap, and the function is
called `convert()` rather than `run()` so it cannot collide with `%run` at all.

**Do not delete that `import matplotlib, numpy, pandas` line**, unused as it looks. The
Pyodide kernel decides which packages to download by running `loadPackagesFromImports()`
over *the cell's own source*. Imports inside `spc_lab.py` are invisible to it, so without
that line the cell fails with `ModuleNotFoundError: No module named 'matplotlib'`. Any new
third-party package used by `spc_lab.py` has to be named in the cell too.

Values are asked for with plain `input()` prompts rather than typed into the code, so
nobody has to edit a variable to pick a file or a zoom range. No `ipywidgets` involved,
which keeps the build simple and avoids a runtime package download.

**One caveat to test before class.** The Pyodide kernel implements `input()` through
`SharedArrayBuffer`, which browsers only expose on cross-origin-isolated pages. GitHub
Pages cannot send the `COOP`/`COEP` headers that requires. There is a fallback path in the
kernel and it may well work anyway — but it depends on the browser and how you host the
site, so open the deployed link and run `zoom()` once to check.

If the prompts do not appear, nothing breaks: `ask()` catches the failure, prints
`(no input box available here, using the default)` and carries on, so `run()` still
converts the file and plots it. To get interactive prompts in that case you would need a
host that can set those two headers — Netlify or Cloudflare Pages can, GitHub Pages
cannot.

Regenerate the notebook after editing `tools/build_notebook.py`:

```bash
python tools/build_notebook.py content/spc_to_csv.ipynb
```

## Build and preview locally

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

jupyter lite build --contents content --output-dir dist
python -m http.server -d dist 8000
```

Then open <http://localhost:8000/lab/index.html>.

**It has to be served over `http://` or `https://`.** Opening `dist/index.html` straight
off disk with a `file://` URL will not work: JupyterLite needs a service worker to make
dragged-in files visible to the Python kernel, and browsers don't register service
workers on `file://`.

A rebuild is only needed when you change something in `content/`. Delete
`.jupyterlite.doit.db` if a rebuild ever seems to ignore your edits.

## Publish for students

Push this repo to GitHub, then in **Settings ▸ Pages** set *Source* to **GitHub Actions**.
The included workflow builds and deploys on every push to `main`, and the site lands at
`https://<user>.github.io/<repo>/lab/index.html`.

That is the link to hand out. Anything that serves static files works equally well —
Netlify, Cloudflare Pages, S3, or your campus web space — just upload `dist/`.

To send students straight to the notebook rather than the JupyterLab shell:

```
https://<user>.github.io/<repo>/notebooks/index.html?path=spc_to_csv.ipynb
```

## What students get out

`convert()` writes two files next to the `.spc`, both named after it:

- `<name>.csv` — the data
- `<name>.png` — the plot at 200 dpi on a white background, good enough to drop into a lab
  report without screenshotting

`peaks()` adds `<name>_peaks.csv` and `<name>_peaks.png`.

`zoom()` saves each zoomed view under its own name, e.g. `benzoic_1600to1900.png`, so
earlier plots are not overwritten. Zooming to the full spectrum rewrites the plain
`<name>.png`.

Right-click any of them in the file list to download.

## Peak picking

`peaks()` finds maxima, labels the strongest on a plot, and writes every one it found to
`<name>_peaks.csv` (position, height, prominence, and rank by prominence). It deliberately
does **not** assign functional groups — assignment depends on context a lookup table
cannot see, and a confidently wrong "C=O stretch" is worse for learning than a bare
wavenumber.

How it works, and what you may want to tune at the top of `spc_lab.py`:

| Constant | Default | What it does |
| --- | --- | --- |
| `PEAK_SENSITIVITY` | 1.0 | Prominence floor as a % of the spectrum's own absorbance range, so it transfers between strong and weak samples |
| `PEAK_FLOOR` | 0.005 | Absolute backstop in absorbance units, so a near-blank spectrum does not report noise |
| `PEAK_NOISE_K` | 4.0 | A peak must also clear this many times the measured noise level |
| `PEAK_SMOOTH_CM` | 16.0 | Smoothing window in cm⁻¹, converted to points from the actual spacing |
| `PEAK_TOP_N` | 10 | How many peaks get labelled on the plot |
| `PEAK_PICKING` | True | Set `False` to switch peak picking off entirely |

`peaks()` works on **whatever `zoom()` is currently showing**. On the full spectrum it
scans everything; after a zoom it scans that range only, and judges sensitivity and noise
against the data in the window. That is the useful case: a weak band next to a dominant one
is easy to miss when the threshold is set by a peak elsewhere in the spectrum. In testing,
zooming to a quiet region dropped the prominence floor from 0.012 to 0.005 absorbance.
Zoomed results are saved as `<name>_peaks_1500to1650.csv`/`.png` so they do not overwrite
the full-spectrum ones. `zoom()` then Enter returns to the whole spectrum.

Detection runs on a Savitzky-Golay smoothed copy, but positions and heights are read off
the raw data, with a parabolic fit across the three points at each maximum giving sub-grid
positions — on a 16 cm⁻¹ grid that cut the position error from 6 cm⁻¹ to 0.5 cm⁻¹.
Prominence is computed directly in numpy, so **no scipy download is needed**.

The noise level is estimated from point-to-point scatter in the raw data. This matters:
sensitivity alone could not cope with noisy spectra during testing, and adding the noise
guard took a synthetic spectrum with seven bands from 40-odd spurious peaks down to
exactly seven, unchanged from clean data up to a noise level of 0.02 absorbance. When the
noise floor is the binding limit rather than the sensitivity setting, `peaks()` says so,
because otherwise lowering sensitivity appears to do nothing.

**Calibrate against your own spectra before class.** These defaults were tuned on
synthetic data. The number worth checking is `PEAK_NOISE_K`: too low and student ATR
spectra with poor contact will produce noise peaks, too high and genuine weak bands vanish.

**Known limitation.** A saturated, flat-topped band can be reported as two peaks at its
shoulders, an artifact of smoothing a clipped signal. The real band is always among the
results, but the peak count may be one higher than expected. Spectra that are not
saturated are unaffected.

## Supported formats

Files are identified by their contents, not their extension, so students can drag in
whatever the instrument produced.

**Thermo Galactic SPC** (`.spc`) — see the parser notes below.

**Bruker OPUS** — what a Bruker Alpha, Tensor or Vertex writes by default. These are named
with a *number* as the extension (`.0`, `.1`, `.17`), because OPUS increments it on each
save; the reader sniffs the magic bytes instead of trusting the name. Absorbance is used
when a file holds several block types (single-channel and interferogram blocks are noted
in the summary but not exported). Instrument, resolution, scan count, date and sample name
are read from the parameter blocks. Tested against real Alpha files at 1 and 2 cm⁻¹.

Output files keep an OPUS numeric extension, since it identifies the measurement:
`Benzoic_acid_14_23.17` produces `Benzoic_acid_14_23.17.csv`.

## What the parser handles

`spc_reader.py` is a from-scratch implementation of the Galactic SPC format that needs
only numpy, so nothing has to be downloaded at runtime. It has been tested against
generated files covering:

- current-format files (`fversn` 0x4B little-endian, 0x4C big-endian)
- 32-bit fixed point, 16-bit fixed point (`TSPREC`), and IEEE float Y values
- evenly spaced X, a shared uneven X array (`TXVALS`), and per-trace X (`TXYXYS`)
- multi-trace files — kinetics, GC-IR, maps — where every trace is returned
- axis types and labels, so CSV columns come out as e.g. `Wavenumber (cm-1)`

Axis labels are stored in plain ASCII (`cm-1`) so CSV headers open cleanly in Excel.
For plots, `pretty_label()` converts them to real superscripts:

```python
pretty_label("Wavenumber (cm-1)")             # 'Wavenumber (cm⁻¹)'      (default)
pretty_label("Wavenumber (cm-1)", "mathtext") # 'Wavenumber (cm$\mathregular{^{-1}}$)'
pretty_label("Wavenumber (cm-1)", "plain")    # unchanged
```

Set `LABEL_STYLE` in the notebook's first cell to switch. Micrometres (`um` → µm) are
handled too.

`unicode` is the default deliberately. Matplotlib's mathtext renderer produces slightly
nicer typography, but on some builds — including the one Pyodide ships — it emits a burst
of `MatplotlibDeprecationWarning: The x parameter as float was deprecated` messages from
inside matplotlib's own Agg backend. Plots are unaffected, but a screenful of warnings
looks like a broken notebook to a student. The Unicode superscripts avoid that code path
entirely. The notebook also filters those specific warnings, so either style stays quiet;
unrelated warnings still come through.

**Old-format files (`fversn` 0x4D, pre-1996 GRAMS) are not supported.** The reader says so
plainly rather than returning nonsense. Re-saving from GRAMS fixes it. If you have a pile
of old files and can't re-save them, add `spc_spectra` to the mix instead — the notebook's
first cell would then need `import piplite; await piplite.install("spc_spectra")`, which
does require students to be online.

Before the first class, run two or three of your real instrument files through it and
compare against GRAMS. The format has a lot of vendor-specific corners, and your files are
the only ones that matter.

`tools/make_test_spc.py` writes synthetic `.spc` files in each supported variant if you
want to test without instrument data.

## Things worth telling students

- Files live in that browser tab's private storage. Clearing browsing data wipes them, so
  download any CSV worth keeping (right-click it in the file list → Download).
- Nothing leaves their machine — useful to say out loud if the data is unpublished.
- First load pulls down the Python runtime and takes a few seconds; after that it is
  cached. On a lecture-hall wifi, have them open the link before you start talking.
- Very large files (tens of MB) are slow to drag in, since they go through browser storage.
