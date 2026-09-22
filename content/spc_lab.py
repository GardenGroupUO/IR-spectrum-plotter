"""Everything the student notebook needs: convert() and zoom().
Students never see this file; the notebook just calls into it.
"""
import warnings
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from spc_reader import read_spc, pretty_label, SPCError
from opus_reader import read_opus, is_opus

# Some matplotlib builds warn about their own internals while drawing text.
warnings.filterwarnings(
    "ignore",
    category=matplotlib.MatplotlibDeprecationWarning,
    message=".*parameter as float.*",
)

# How units are drawn on plots: "unicode" -> cm\u207b\u00b9, "mathtext" -> typeset, "plain" -> cm-1
LABEL_STYLE = "unicode"

spectrum = None   # the spectrum most recently loaded by run()
path = None       # the file it came from
df = None         # the table written to CSV


def ask(prompt, default=""):
    """Show an input box and return what the student typed.

    If this kernel has no input box, fall back to the default instead of
    raising, so the notebook still produces a plot.
    """
    try:
        reply = input(prompt).strip()
    except Exception:
        shown = default if default else "the default"
        print(f"   (no input box available here, using {shown})")
        return default
    return reply or default


# Files that live beside the notebook and are definitely not spectra.
_NOT_SPECTRA = {".ipynb", ".py", ".csv", ".png", ".md", ".txt", ".json", ".jpg", ".pdf"}


def read_spectrum(file_path):
    """Read a spectrum, choosing the reader from the file's own contents.

    Bruker OPUS files are usually named with a number as the extension (.0, .1,
    .17), so the extension cannot be trusted. The first four bytes can.
    """
    if is_opus(file_path):
        return read_opus(file_path)
    return read_spc(file_path)


def looks_like_spectrum(file_path):
    if file_path.suffix.lower() in _NOT_SPECTRA or file_path.name.startswith("."):
        return False
    if file_path.suffix.lower() == ".spc":
        return True
    try:
        head = file_path.open("rb").read(2)
    except OSError:
        return False
    if len(head) < 2:
        return False
    # OPUS magic, or an SPC version byte.
    return head == b"\x0a\x0a" or head[1] in (0x4B, 0x4C, 0x4D)


def _stem():
    """Base name for output files. OPUS extensions are numbers (.0, .17) and part
    of the identity of the file, so they are kept rather than stripped."""
    if path is None:
        return "spectrum"
    return path.name if path.suffix.lower() != ".spc" else path.stem


def _out(tail):
    return path.with_name(_stem() + tail)


def find_spc():
    """Every spectrum file sitting beside the notebook, whatever it is called."""
    return sorted(p for p in Path(".").iterdir() if p.is_file() and looks_like_spectrum(p))


def _plot(spec, title, xlim=None, png=None):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    drew = False
    for x, y, name in zip(spec.xs, spec.ys, spec.trace_names()):
        if xlim is not None:
            lo, hi = min(xlim), max(xlim)
            keep = (x >= lo) & (x <= hi)
            if not keep.any():
                continue
            x, y = x[keep], y[keep]
        ax.plot(x, y, linewidth=1.0, label=pretty_label(name, LABEL_STYLE))
        drew = True

    if not drew:
        plt.close(fig)
        print("Nothing to plot in that range.")
        return

    ax.set_xlabel(pretty_label(spec.x_label, LABEL_STYLE))
    ax.set_ylabel(pretty_label(spec.y_label, LABEL_STYLE))
    ax.set_title(title)
    if "Wavenumber" in spec.x_label or "Raman" in spec.x_label:
        ax.invert_xaxis()
    if spec.n_traces > 1:
        ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.25)
    fig.tight_layout()

    if png is not None:
        # facecolor is set explicitly so the PNG has a white background even if
        # the notebook is being viewed with a dark theme.
        fig.savefig(png, dpi=200, facecolor="white")
        print(f"Saved {png.name}  -- right-click it in the file list to download it.")

    plt.show()


def convert():
    """Pick a .spc file, save it as CSV, and plot it."""
    global spectrum, path, df, view

    files = find_spc()
    if not files:
        print("No .spc files found.")
        print("Drag one onto the file list on the left, then run this cell again.")
        return

    if len(files) == 1:
        choice = files[0]
        print(f"Using the only .spc file here: {choice.name}\n")
    else:
        print("Which file would you like?")
        for i, f in enumerate(files, 1):
            print(f"   {i}. {f.name}")
        reply = ask("\nType a number and press Enter [1]: ", "1")
        try:
            choice = files[int(reply) - 1]
            if int(reply) < 1:
                raise ValueError
        except (ValueError, IndexError):
            choice = files[0]
            print(f"   '{reply}' is not on the list -- using {choice.name}")
        print()

    try:
        spec = read_spectrum(choice)
    except SPCError as err:
        print(f"Could not read {choice.name}:\n   {err}")
        return

    spectrum, path = spec, choice
    view = None                      # a new file starts on the full spectrum
    df = spec.to_dataframe()
    csv_path = _out(".csv")
    df.to_csv(csv_path, index=False)

    print(spec.describe())
    print(f"\nSaved {csv_path.name}  ({len(df):,} rows x {len(df.columns)} columns)")
    _plot(spec, _stem(), png=_out(".png"))


def zoom():
    """Re-plot the loaded spectrum over a range you choose."""
    global view

    if spectrum is None:
        print("Run the 'convert' cell above first, so there is a spectrum to zoom into.")
        return

    x = spectrum.xs[0]
    lo_lim, hi_lim = float(min(x.min(), x.max())), float(max(x.min(), x.max()))
    print(f"This spectrum covers {lo_lim:g} to {hi_lim:g} ({spectrum.x_label}).")

    start = ask("Start of range (or press Enter for the whole spectrum): ")
    if not start:
        view = None
        _plot(spectrum, _stem(), png=_out(".png"))
        print("Showing the whole spectrum again.")
        return

    end = ask("End of range: ")
    try:
        lo, hi = float(start), float(end)
    except ValueError:
        print("   Those did not look like numbers -- showing the whole spectrum.")
        view = None
        _plot(spectrum, _stem(), png=_out(".png"))
        return

    # A zoomed view gets its own file, so it does not overwrite the full plot.
    view = (min(lo, hi), max(lo, hi))
    png = _out(f"_{lo:g}to{hi:g}.png")
    _plot(spectrum, f"{_stem()}   ({lo:g} to {hi:g})", xlim=(lo, hi), png=png)
    print("Peak picking will now work on this range. Run zoom() and press Enter"
          " to go back to the whole spectrum.")


# --------------------------------------------------------------- peak picking
# Defaults chosen to be conservative. Tune them against your own spectra:
# PEAK_SENSITIVITY is a percentage of each spectrum's own absorbance range, so
# it transfers between strong and weak samples; PEAK_FLOOR is an absolute
# backstop in absorbance units so a near-blank spectrum does not report noise.
PEAK_SENSITIVITY = 1.0    # % of (max - min) absorbance
PEAK_FLOOR = 0.005        # absorbance units
PEAK_SMOOTH_CM = 16.0     # smoothing window, in x-axis units (not points)
PEAK_NOISE_K = 4.0        # a peak must clear this many times the noise level
PEAK_TOP_N = 10           # how many peaks get labelled on the plot
PEAK_PICKING = True       # set False to switch peak picking off for the class


def _savgol(y, window, order=2):
    """Savitzky-Golay smoothing. Keeps peak heights better than a moving average."""
    if window <= order + 1 or window >= len(y):
        return y.copy()
    if window % 2 == 0:
        window += 1
    half = window // 2
    z = np.arange(-half, half + 1, dtype=float)
    design = np.vander(z, order + 1, increasing=True)
    coeffs = np.linalg.pinv(design)[0]          # row giving the fitted centre value
    padded = np.pad(y, half, mode="edge")       # edge-pad so the ends are not pulled to zero
    return np.correlate(padded, coeffs, mode="valid")


def _local_maxima(y):
    """Indices of local maxima, with flat tops collapsed to a single index.

    A peak must rise strictly into it and fall strictly out of it, so a flat
    baseline does not register as thousands of maxima. Symmetrically sampled
    and saturated bands give equal adjacent values; those plateaus count once.
    """
    n = len(y)
    idx = []
    i = 1
    while i < n - 1:
        if y[i] > y[i - 1]:
            j = i
            while j + 1 < n and y[j + 1] == y[i]:
                j += 1
            if j + 1 < n and y[j + 1] < y[i]:
                idx.append((i + j) // 2)
            i = j + 1
        else:
            i += 1
    return np.array(idx, dtype=int)


def _prominences(y, idx):
    """Topographic prominence of each local maximum in ``idx``.

    For each peak, walk outwards until the signal rises strictly above the peak
    (or the spectrum ends), tracking the lowest point reached on each side. The
    prominence is the peak height above the higher of those two minima. Equal
    neighbouring values are walked through, not treated as a wall -- otherwise a
    symmetrically sampled band reports zero prominence.
    """
    out = np.empty(len(idx), dtype=float)
    n = len(y)
    for k, i in enumerate(idx):
        h = y[i]

        left_min = h
        j = i - 1
        while j >= 0 and y[j] <= h:
            if y[j] < left_min:
                left_min = y[j]
            j -= 1

        right_min = h
        j = i + 1
        while j < n and y[j] <= h:
            if y[j] < right_min:
                right_min = y[j]
            j += 1

        out[k] = h - max(left_min, right_min)
    return out


def _refine(x, y, i):
    """Sub-grid peak position by fitting a parabola through the three points at i."""
    if i <= 0 or i >= len(y) - 1:
        return float(x[i]), float(y[i])
    y0, y1, y2 = float(y[i - 1]), float(y[i]), float(y[i + 1])
    denom = y0 - 2.0 * y1 + y2
    if denom == 0:
        return float(x[i]), float(y1)
    shift = 0.5 * (y0 - y2) / denom           # in grid steps, within +/- 0.5
    shift = float(np.clip(shift, -1.0, 1.0))
    step = (float(x[i + 1]) - float(x[i - 1])) / 2.0   # signed: x may descend
    return float(x[i]) + shift * step, y1 - 0.25 * (y0 - y2) * shift


def find_peaks(x, y, min_prominence, smooth_cm=PEAK_SMOOTH_CM, min_separation_cm=None):
    """Return (positions, heights, prominences), strongest first.

    Peaks are detected on a smoothed copy so noise does not generate hundreds of
    hits, but positions and heights are read off the original data. Two further
    guards keep the result honest on real spectra:

    * a noise-aware floor -- the noise level is estimated from the difference
      between the raw and smoothed data, and nothing shallower than 3 sigma is
      reported, however generous the sensitivity setting;
    * a minimum separation -- when several candidates sit within one smoothing
      window of each other, only the most prominent survives, which stops a
      single noisy or flat-topped band being reported several times.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    spacing = float(np.median(np.abs(np.diff(x)))) if len(x) > 1 else 1.0
    window = int(round(smooth_cm / spacing)) if spacing > 0 else 0
    if window % 2 == 0:
        window += 1
    window = max(window, 7)
    smoothed = _savgol(y, window)

    # Noise level, estimated from point-to-point scatter in the raw data. The
    # median absolute difference is robust: real bands change smoothly between
    # neighbouring points, so they barely affect it, while noise does.
    diffs = np.diff(y)
    sigma = 1.4826 * float(np.median(np.abs(diffs - np.median(diffs)))) / np.sqrt(2.0)
    floor = max(float(min_prominence), PEAK_NOISE_K * sigma)

    idx = _local_maxima(smoothed)
    if len(idx) == 0:
        return np.array([]), np.array([]), np.array([])

    prom = _prominences(smoothed, idx)
    keep = prom >= floor
    idx, prom = idx[keep], prom[keep]
    if len(idx) == 0:
        return np.array([]), np.array([]), np.array([])

    positions, heights = [], []
    for i in idx:
        px, py = _refine(x, y, i)
        positions.append(px)
        heights.append(py)
    positions = np.array(positions)
    heights = np.array(heights)

    # Strongest first, then drop anything too close to a stronger peak.
    order = np.argsort(prom)[::-1]
    positions, heights, prom = positions[order], heights[order], prom[order]

    separation = min_separation_cm if min_separation_cm is not None else max(smooth_cm, 2 * spacing)
    chosen = []
    for k in range(len(positions)):
        if all(abs(positions[k] - positions[c]) >= separation for c in chosen):
            chosen.append(k)
    chosen = np.array(chosen, dtype=int)

    return positions[chosen], heights[chosen], prom[chosen]


def _plot_peaks(spec, x, y, pos, hgt, top_n, title, png):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(x, y, linewidth=1.0)

    span = float(y.max() - y.min()) or 1.0
    wavenumber = "Wavenumber" in spec.x_label or "Raman" in spec.x_label
    shown = min(top_n, len(pos))

    for k in range(shown):
        peak_x, peak_y = float(pos[k]), float(hgt[k])
        ax.plot([peak_x], [peak_y], marker="v", markersize=5, color="tab:red")
        text = f"{peak_x:.0f}" if wavenumber else f"{peak_x:.4g}"
        # Alternate the offset so labels on neighbouring peaks do not collide.
        ax.annotate(
            text, (peak_x, peak_y), textcoords="offset points",
            xytext=(0, 9 + (k % 2) * 17), rotation=90,
            ha="center", va="bottom", fontsize=8, color="tab:red",
        )

    ax.set_ylim(top=float(y.max()) + 0.32 * span)
    ax.set_xlabel(pretty_label(spec.x_label, LABEL_STYLE))
    ax.set_ylabel(pretty_label(spec.y_label, LABEL_STYLE))
    ax.set_title(title)
    if wavenumber:
        ax.invert_xaxis()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(png, dpi=200, facecolor="white")
    print(f"Saved {png.name}  -- right-click it in the file list to download it.")
    plt.show()


def peaks():
    """Find peaks in the loaded spectrum, label the strongest, and save a table."""
    global peak_table

    if not PEAK_PICKING:
        print("Peak picking is switched off for this notebook.")
        print("(Your instructor can turn it back on: PEAK_PICKING in spc_lab.py)")
        return

    if spectrum is None:
        print("Run the 'convert' cell above first, so there is a spectrum to work on.")
        return

    if spectrum.meta.get("fytype") in (128, 129):
        print("Note: this file's y axis is transmittance or reflectance, so its bands")
        print("point downwards. Peak picking here looks for maxima, so the results")
        print("will not be the bands you expect. Convert to absorbance first.\n")

    x, y = spectrum.xs[0], spectrum.ys[0]
    if spectrum.n_traces > 1:
        print(f"This file has {spectrum.n_traces} traces; using the first one.")

    # Follow the zoom. Thresholds are then worked out from the range on screen,
    # which is the point: a weak band in a quiet region is easily missed when the
    # sensitivity is judged against a huge peak somewhere else in the spectrum.
    if view is None:
        suffix = ""
        where = "the whole spectrum"
    else:
        lo, hi = view
        keep = (x >= lo) & (x <= hi)
        if keep.sum() < 10:
            print(f"\nOnly {int(keep.sum())} points between {lo:g} and {hi:g} -- too few to")
            print("pick peaks from. Zoom to a wider range and try again.")
            return
        x, y = x[keep], y[keep]
        suffix = f"_{lo:g}to{hi:g}"
        where = f"{lo:g} to {hi:g}"
    print(f"Picking peaks in {where}.\n")

    reply = ask(
        f"Sensitivity, as a % of the absorbance range -- smaller finds more "
        f"[{PEAK_SENSITIVITY:g}]: ", str(PEAK_SENSITIVITY))
    try:
        sensitivity = float(reply)
    except ValueError:
        sensitivity = PEAK_SENSITIVITY
        print(f"   '{reply}' is not a number -- using {sensitivity:g}")

    reply = ask(f"How many peaks to label on the plot [{PEAK_TOP_N}]: ", str(PEAK_TOP_N))
    try:
        top_n = max(1, int(float(reply)))
    except ValueError:
        top_n = PEAK_TOP_N
        print(f"   '{reply}' is not a number -- using {top_n}")

    span = float(y.max() - y.min())
    floor = max(sensitivity / 100.0 * span, PEAK_FLOOR)
    pos, hgt, prom = find_peaks(x, y, floor)

    # Tell the student when noise, rather than their setting, is the binding limit.
    diffs = np.diff(y)
    noise = 1.4826 * float(np.median(np.abs(diffs - np.median(diffs)))) / np.sqrt(2.0)
    if PEAK_NOISE_K * noise > floor:
        print(f"\nNote: this spectrum's noise level ({noise:.4g}) sets the limit here,")
        print(f"not your sensitivity. Nothing shallower than {PEAK_NOISE_K * noise:.4g} is")
        print("reported, so a smaller sensitivity will not find more peaks.")

    if len(pos) == 0:
        print(f"\nNo peaks stood out at {sensitivity:g}%. Try a smaller number.")
        return

    # Rounded so the CSV is readable; far beyond any instrument's real precision.
    table = pd.DataFrame({
        "rank": np.arange(1, len(pos) + 1),      # by prominence, strongest first
        spectrum.x_label: np.round(pos, 2),
        spectrum.y_label: np.round(hgt, 5),
        "prominence": np.round(prom, 5),
    })
    # Written high-to-low along the x axis, the way peak lists are usually quoted.
    table = table.sort_values(spectrum.x_label, ascending=False).reset_index(drop=True)
    peak_table = table

    csv_path = _out(f"_peaks{suffix}.csv")
    table.to_csv(csv_path, index=False)

    print(f"\nFound {len(pos)} peaks above {floor:.4g} {spectrum.y_label.lower()}.")
    print(f"Labelling the {min(top_n, len(pos))} strongest.\n")
    head = table.sort_values("rank").head(min(top_n, len(pos)))
    wavenumber = "Wavenumber" in spectrum.x_label or "Raman" in spectrum.x_label
    for _, row in head.iterrows():
        px = row[spectrum.x_label]
        print(f"   {int(row['rank']):>2}.  {px:9.1f}   height {row[spectrum.y_label]:.4f}"
              f"   prominence {row['prominence']:.4f}")

    print(f"\nSaved {csv_path.name}  (all {len(pos)} peaks)")
    _plot_peaks(spectrum, x, y, pos, hgt, top_n,
                f"{_stem()} -- peaks ({where})",
                _out(f"_peaks{suffix}.png"))


peak_table = None   # the most recent peak table, for anyone who wants the numbers
