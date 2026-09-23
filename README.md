# IR spectrum plotter

Turn an IR spectrum into a CSV file, a plot, and a peak list, right in your browser.
No install, no account, nothing leaves your computer.

**Use it here:** <https://gardengroupuo.github.io/IR-spectrum-plotter/notebooks/index.html?path=spc_to_csv.ipynb>

## How to use it

1. Open the link above.
2. Drag your spectrum file onto the file list on the left. Wait for it to appear.
   (If the panel is hidden, click the folder icon in the top-left corner.)
3. Run each cell with `Shift` + `Enter`, and answer the questions in the boxes that
   appear. You can run the cells in any order, as many times as you like.
4. Right-click any file it produces (CSV, PNG) in the file list and choose Download
   to save it to your computer.

That's it. The notebook itself has the same instructions, plus a troubleshooting
section for common errors.

## Supported files

- **GRAMS/AI `.spc`** files.
- **Bruker OPUS** files, the format written by default on a Bruker Alpha, Tensor, or
  Vertex. These are usually named with a number instead of a file extension (e.g.
  `sample.0`, `sample.17`), which is normal.

The file type is detected from its contents, not its name, so you can just drag in
whatever your instrument produced.

## What you get out

- `<name>.csv` and `<name>.png`, from the convert step.
- `<name>_peaks.csv` and `<name>_peaks.png`, from the peak-picking step.
- If you zoom in first, the peak files are named after that range instead (e.g.
  `<name>_peaks_1500to1650.csv`), so they don't overwrite the full-spectrum ones.

## Things worth knowing

- Files live in that browser tab's private storage. Clearing your browsing data
  removes them, so download anything you want to keep.
- Nothing is uploaded. Your spectra never leave your computer.
- The first load takes a few seconds while the browser fetches the Python runtime.
  After that it's cached.

## Developing or deploying this yourself

This repo is the source for the site above. If you want to change it, tune the peak
picker, or deploy your own copy, see [DEVELOPMENT.md](DEVELOPMENT.md) for the build steps,
project layout, and the constraints that are easy to break.

Quick start:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tools/build_notebook.py content/spc_to_csv.ipynb
jupyter lite build --contents content --output-dir dist
python -m http.server -d dist 8000     # must be http://, not file://
```

Pushing to `main` on GitHub rebuilds and redeploys the site automatically, via
`.github/workflows/deploy.yml` (once **Settings → Pages → Source** is set to
**GitHub Actions**).
