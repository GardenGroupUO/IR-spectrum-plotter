"""Regenerate content/spc_to_csv.ipynb.  Usage: python tools/build_notebook.py content/spc_to_csv.ipynb"""
import json
import sys

def md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": s.strip("\n").splitlines(True)}

def code(s, hidden=False):
    meta = {"jupyter": {"source_hidden": True}} if hidden else {}
    return {"cell_type": "code", "execution_count": None, "metadata": meta,
            "outputs": [], "source": s.strip("\n").splitlines(True)}

cells = [
md("""
# IR spectrum plotter

Turn an IR spectrum, either a **GRAMS/AI `.spc`** file or a **Bruker OPUS** file, into a
CSV file and a plot. This code runs in your browser and you don't need to install
anything.

### What to do

1. **Drag your spectrum file onto the file list on the left.** Wait for it to appear.
   OPUS files are often named with a number instead of a file extension (e.g. `sample.0`,
   `sample.17`). That's normal, so just drag it in as is. (If the panel is hidden, click
   the folder icon in the top-left corner.)
2. Run each cell below by clicking the green arrow next to it, and answer the questions
   in the boxes that appear. (`Shift` + `Enter` also works.) You can run the cells in any
   order, as many times as you like.
3. Your CSV shows up in the same file list. **Right-click it, then Download,** to keep it.
4. The plot is also saved as a PNG image in the same file list. Right-click it, then
   Download, to keep that too.
"""),

md("""
## Step 1: Convert and plot

Run this cell. If there is more than one spectrum file, it will ask which one you want.
"""),

code("""# JupyterLite only fetches packages named in this cell, so list them here.
import matplotlib, numpy, pandas  # noqa: F401

from spc_lab import convert

convert()"""),

md("""
## Step 2: Zoom in (optional)

Run this cell to look at part of the spectrum more closely. It will ask for the start and
end of the range, in the units shown on the x axis. Press Enter without typing anything to
see the whole spectrum again. You can run this as many times as you like.
"""),

code("""import matplotlib, numpy, pandas  # noqa: F401

from spc_lab import zoom

zoom()"""),

md("""
## Step 3: Peak picking (optional)

Run this cell to find the peaks and label the strongest ones. It asks two things:

* **Sensitivity:** how prominent a bump has to be before it counts, as a percentage of
  the spectrum's absorbance range. Smaller finds more. Start at 1 and adjust.
* **How many to label:** only the strongest are drawn on the plot, so it stays readable.
  The saved table always contains every peak found.

**This works on whatever Step 2 is showing.** On the full spectrum it picks peaks across
the whole range. After zooming, it picks peaks inside that range only, judging sensitivity
against what is on screen. This makes it easier to pull out a weak band sitting near a
strong one. Run Step 2 and press Enter to go back to the whole spectrum.

You get `..._peaks.csv` and `..._peaks.png`, named after the range so zoomed results do not
overwrite the full ones.
"""),

code("""import matplotlib, numpy, pandas  # noqa: F401

from spc_lab import peaks

peaks()"""),

md("""
---

## If something goes wrong

**"No spectrum files found":** the file has to be dropped onto the file list panel on the
left, not into the notebook itself. Then run Step 1 again.

**"This is an old-format SPC file":** only for `.spc` files. It came from a pre-1996
version of GRAMS. Open it in GRAMS and re-save it, and it will read fine.

**"Unrecognised SPC version byte":** only for `.spc` files. The file probably is not an
SPC file, or it has been renamed. Check that it still opens in GRAMS.

**"This is not an OPUS file":** only for files with a numeric extension (`.0`, `.17`,
...). Its first bytes do not match the OPUS format. Check that it still opens in OPUS.

**"No spectrum was found in this OPUS file":** the file only holds instrument settings, or
a kind of data block this reader does not handle.

**"It looks truncated" / "ends inside ..." / "block directory is unreadable":** the copy
is incomplete, for either file type. Copy it off the instrument again.

**Peak picking finds far too many or too few:** change the sensitivity. Smaller numbers
find more peaks. If everything is noise, the spectrum may need a better baseline first.

**The plot looks like noise:** some instruments store interferograms rather than finished
spectra. Check the `y axis` line printed by Step 1.

Your files live in this browser tab's private storage. Clearing your browsing data removes
them, so download any CSV you want to keep.
"""),
]

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python (Pyodide)", "language": "python", "name": "python"},
        "language_info": {
            "name": "python", "version": "3.11", "mimetype": "text/x-python",
            "file_extension": ".py", "codemirror_mode": {"name": "ipython", "version": 3},
            "pygments_lexer": "ipython3", "nbconvert_exporter": "python",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

for i, cell in enumerate(nb["cells"]):
    cell["id"] = f"cell-{i:02d}"

out = sys.argv[1] if len(sys.argv) > 1 else "content/spc_to_csv.ipynb"
with open(out, "w") as fh:
    json.dump(nb, fh, indent=1, ensure_ascii=False)
    fh.write("\n")
print("wrote", out)
