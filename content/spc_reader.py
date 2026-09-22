"""
spc_reader.py -- a small, dependency-light reader for Thermo Galactic GRAMS/AI
``.spc`` spectroscopy files.

Only needs ``numpy`` (already in Pyodide/JupyterLite), so it runs entirely in the
browser with no packages to download.

Supported
---------
* "New" format files, ``fversn`` = 0x4B (LSB, by far the most common) and
  0x4C (MSB).
* Evenly spaced X, explicit X array (TXVALS), and per-subfile X (TXYXYS).
* 32-bit and 16-bit fixed-point Y, and IEEE float Y.
* Multi-subfile files (kinetics / GC-IR / maps) -- every trace is returned.

Not supported
-------------
* "Old" format files (``fversn`` = 0x4D, pre-1996 GRAMS). Re-save those from
  GRAMS as a current .spc, or install the ``spc_spectra`` package.

Typical use
-----------
    from spc_reader import read_spc
    s = read_spc("sample.spc")
    s.to_dataframe()          # tidy pandas DataFrame
    s.to_csv("sample.csv")
"""

from __future__ import annotations

import datetime
import re
import struct

import numpy as np

__all__ = [
    "read_spc", "Spectrum", "SPCError", "pretty_label", "X_LABELS", "Y_LABELS",
]


class SPCError(Exception):
    """Raised when a file is not a readable SPC file."""


# ---------------------------------------------------------------- flag bits
TSPREC = 0x01  # Y values are 16 bit, not 32 bit
TCGRAM = 0x02  # enables fexper
TMULTI = 0x04  # file contains multiple traces
TRANDM = 0x08  # Z values are random order
TORDRD = 0x10  # Z values are ordered but unevenly spaced
TALABS = 0x20  # axis labels are in fcatxt
TXYXYS = 0x40  # each subfile carries its own X array
TXVALS = 0x80  # one shared, unevenly spaced X array precedes the subfiles

_HEAD = "4BI2dI4BI9s9sH8f130s30s2I2BHf48sfIfB187s"  # 512 bytes
_SUB = "BbHfffIIf4s"  # 32 bytes

X_LABELS = {
    0: "Arbitrary", 1: "Wavenumber (cm-1)", 2: "Wavelength (um)",
    3: "Wavelength (nm)", 4: "Time (s)", 5: "Time (min)", 6: "Frequency (Hz)",
    7: "Frequency (kHz)", 8: "Frequency (MHz)", 9: "Mass (m/z)", 10: "ppm",
    11: "Time (days)", 12: "Time (years)", 13: "Raman shift (cm-1)",
    14: "Energy (eV)", 15: "Label", 16: "Diode number", 17: "Channel",
    18: "Degrees", 19: "Temperature (F)", 20: "Temperature (C)",
    21: "Temperature (K)", 22: "Data points", 23: "Time (ms)",
    24: "Time (us)", 25: "Time (ns)", 26: "Frequency (GHz)", 27: "Length (cm)",
    28: "Length (m)", 29: "Length (mm)", 30: "Time (hours)",
}

Y_LABELS = {
    0: "Arbitrary intensity", 1: "Interferogram", 2: "Absorbance",
    3: "Kubelka-Munk", 4: "Counts", 5: "Volts", 6: "Degrees", 7: "Milliamps",
    8: "Millimeters", 9: "Millivolts", 10: "Log(1/R)", 11: "Percent",
    12: "Intensity", 13: "Relative intensity", 14: "Energy", 16: "Decibel",
    19: "Temperature (F)", 20: "Temperature (C)", 21: "Temperature (K)",
    22: "Index of refraction", 23: "Extinction coefficient", 24: "Real",
    25: "Imaginary", 26: "Complex", 128: "Transmission", 129: "Reflectance",
    130: "Arbitrary or single beam", 131: "Emission",
}


def _clean(raw: bytes) -> str:
    """Trim a fixed-length C string field down to readable text."""
    return raw.split(b"\x00")[0].decode("latin-1", "replace").strip()


def _decode_date(fdate: int):
    """Unpack the SPC bit-packed date word into a datetime (None if unset)."""
    if not fdate:
        return None
    year = fdate >> 20
    month = (fdate >> 16) & 0x0F
    day = (fdate >> 11) & 0x1F
    hour = (fdate >> 6) & 0x1F
    minute = fdate & 0x3F
    try:
        return datetime.datetime(year, max(month, 1), max(day, 1), hour, minute)
    except ValueError:
        return None


_SUPER_RE = re.compile(r"\b(cm|mm|m|nm|um)-1\b")

# Only match "um" standing alone as a unit, never the "um" inside a word
# such as "Wavenumber".
_MICRON_RE = re.compile(r"\bum\b")


def pretty_label(label: str, style: str = "unicode") -> str:
    """Format an axis label for display, turning ``cm-1`` into a superscript.

    The plain label is kept as-is for CSV column headers; this is only for
    drawing on a plot.

    style="unicode"   ->  'Wavenumber (cm\u207b\u00b9)'        real characters, no mathtext
    style="mathtext"  ->  'Wavenumber (cm$^{-1}$)'   typeset by matplotlib
    style="plain"     ->  unchanged

    "unicode" is the default because matplotlib's mathtext renderer emits
    MatplotlibDeprecationWarnings ("the x parameter as float was deprecated")
    from inside its Agg backend on some builds, including the one Pyodide
    ships. The warnings are harmless and the plot is fine, but they clutter a
    student's screen. "mathtext" gives slightly nicer typography if you are
    exporting a figure for publication and don't mind the noise.
    """
    if style == "plain":
        return label

    if style == "unicode":
        out = _SUPER_RE.sub(lambda m: m.group(1) + "\u207b\u00b9", label)
        return _MICRON_RE.sub(lambda _: "\u03bcm", out)

    if style != "mathtext":
        raise ValueError(f"Unknown style {style!r}; use mathtext, unicode or plain.")

    # \mathregular keeps the superscript in the normal (upright, sans) font
    # instead of switching to matplotlib's italic math font.
    out = _SUPER_RE.sub(lambda m: m.group(1) + r"$\mathregular{^{-1}}$", label)
    # lambda so the backslashes are taken literally, not as regex escapes
    return _MICRON_RE.sub(lambda _: r"$\mathregular{\mu}$m", out)


class Spectrum:
    """One SPC file: a shared or per-trace X axis plus one or more Y traces."""

    def __init__(self, xs, ys, meta, z_values, x_label, y_label):
        self.xs = xs                # list of 1-D arrays, one per trace
        self.ys = ys                # list of 1-D arrays, one per trace
        self.meta = meta            # dict of header fields
        self.z_values = z_values    # list of Z (time/index) values, one per trace
        self.x_label = x_label
        self.y_label = y_label

    # ------------------------------------------------------------ helpers
    @property
    def n_traces(self) -> int:
        return len(self.ys)

    @property
    def shares_x(self) -> bool:
        """True when every trace sits on the identical X grid."""
        first = self.xs[0]
        return all(
            x.shape == first.shape and np.array_equal(x, first) for x in self.xs
        )

    def trace_names(self):
        if self.n_traces == 1:
            return [self.y_label]
        # Use the Z axis for names only when it actually varies.
        if len(set(self.z_values)) > 1:
            return [f"{self.y_label} (z={z:g})" for z in self.z_values]
        return [f"{self.y_label} #{i + 1}" for i in range(self.n_traces)]

    # ------------------------------------------------------------- output
    def to_dataframe(self):
        """Wide DataFrame when traces share an X grid, long/tidy otherwise."""
        import pandas as pd

        names = self.trace_names()
        if self.shares_x:
            frame = {self.x_label: self.xs[0]}
            for name, y in zip(names, self.ys):
                frame[name] = y
            return pd.DataFrame(frame)

        parts = [
            pd.DataFrame({self.x_label: x, self.y_label: y, "trace": name})
            for x, y, name in zip(self.xs, self.ys, names)
        ]
        return pd.concat(parts, ignore_index=True)

    def to_csv(self, path, **kwargs):
        kwargs.setdefault("index", False)
        self.to_dataframe().to_csv(path, **kwargs)
        return path

    def describe(self) -> str:
        m = self.meta
        lines = [
            f"format         : {m.get('format', 'SPC')}",
            f"traces         : {self.n_traces}",
            f"points / trace : {', '.join(str(len(y)) for y in self.ys[:5])}"
            + (" ..." if self.n_traces > 5 else ""),
            f"x axis         : {self.x_label}  "
            f"[{self.xs[0][0]:g} -> {self.xs[0][-1]:g}]",
            f"y axis         : {self.y_label}",
        ]
        when = m.get("date")
        if when:
            # SPC gives a datetime; OPUS gives the instrument's own date string.
            shown = when.strftime("%Y-%m-%d %H:%M") if hasattr(when, "strftime") else str(when)
            lines.append(f"collected      : {shown}")
        for key in ("comment", "resolution", "source", "instrument", "scans", "other_blocks"):
            value = m.get(key)
            if value:
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                lines.append(f"{key:<15}: {value}")
        return "\n".join(lines)

    def __repr__(self):
        return (
            f"<Spectrum {self.n_traces} trace(s), "
            f"{len(self.ys[0])} points, x={self.x_label!r}, y={self.y_label!r}>"
        )


def _y_from_bytes(data, offset, npts, exp, sixteen_bit, endian):
    """Turn raw Y bytes into floats, honouring SPC's fixed-point scaling."""
    if exp == -128:  # 0x80 -> values are already IEEE floats
        dtype = np.dtype(endian + "f4")
        y = np.frombuffer(data, dtype=dtype, count=npts, offset=offset)
        return y.astype(np.float64), offset + 4 * npts

    if sixteen_bit:
        dtype = np.dtype(endian + "i2")
        raw = np.frombuffer(data, dtype=dtype, count=npts, offset=offset)
        return raw.astype(np.float64) * (2.0 ** exp / 2 ** 16), offset + 2 * npts

    dtype = np.dtype(endian + "i4")
    raw = np.frombuffer(data, dtype=dtype, count=npts, offset=offset)
    return raw.astype(np.float64) * (2.0 ** exp / 2 ** 32), offset + 4 * npts


def read_spc(source) -> Spectrum:
    """Read an SPC file.

    ``source`` may be a path, a file-like object, or raw ``bytes``.
    """
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    elif hasattr(source, "read"):
        data = source.read()
    else:
        with open(source, "rb") as fh:
            data = fh.read()

    if len(data) < 512:
        raise SPCError(f"File is only {len(data)} bytes -- too short to be an SPC file.")

    fversn = data[1]
    if fversn == 0x4D:
        raise SPCError(
            "This is an old-format SPC file (fversn 0x4D), which this reader does "
            "not handle. Re-save it from GRAMS as a current .spc file, or install "
            "the 'spc_spectra' package."
        )
    if fversn == 0x4C:
        endian = ">"
    elif fversn == 0x4B:
        endian = "<"
    else:
        raise SPCError(
            f"Unrecognised SPC version byte 0x{fversn:02X}. "
            "Is this really a GRAMS .spc file?"
        )

    fields = struct.unpack_from(endian + _HEAD, data, 0)
    ftflgs = fields[0]
    fexper = fields[2]
    fexp = struct.unpack_from(endian + "b", data, 3)[0]  # signed
    fnpts = fields[4]
    ffirst, flast = fields[5], fields[6]
    fnsub = fields[7]
    fxtype, fytype, fztype = fields[8], fields[9], fields[10]
    fdate = fields[12]
    fres, fsource = _clean(fields[13]), _clean(fields[14])
    fcmnt = _clean(fields[24])
    fcatxt = fields[25]

    sixteen_bit = bool(ftflgs & TSPREC)
    per_sub_x = bool(ftflgs & TXYXYS)
    shared_x_array = bool(ftflgs & TXVALS) and not per_sub_x
    n_sub = max(fnsub, 1)

    offset = 512

    # Shared, unevenly spaced X array sits right after the header.
    if shared_x_array:
        need = offset + 4 * fnpts
        if len(data) < need:
            raise SPCError("File ends inside the X axis block -- it looks truncated.")
        shared_x = np.frombuffer(
            data, dtype=np.dtype(endian + "f4"), count=fnpts, offset=offset
        ).astype(np.float64)
        offset = need
    elif fnpts:
        shared_x = np.linspace(ffirst, flast, fnpts)
    else:
        shared_x = None

    # Custom axis labels, when the file supplies them.
    x_label = y_label = None
    if ftflgs & TALABS:
        text = fcatxt.decode("latin-1", "replace")
        labels = [p.strip() for p in text.split("\x00") if p.strip()]
        if len(labels) >= 1:
            x_label = labels[0]
        if len(labels) >= 2:
            y_label = labels[1]
    x_label = x_label or X_LABELS.get(fxtype, f"X (type {fxtype})")
    y_label = y_label or Y_LABELS.get(fytype, f"Y (type {fytype})")

    xs, ys, z_values = [], [], []
    for i in range(n_sub):
        if offset + 32 > len(data):
            if xs:
                break  # ran out of subfiles early; keep what we have
            raise SPCError("File ends before the first subfile header.")

        sub = struct.unpack_from(endian + _SUB, data, offset)
        _subflgs, subexp, _subindx, subtime, _subnext, _subnois, subnpts = sub[:7]
        offset += 32

        npts = subnpts if (per_sub_x and subnpts) else (subnpts or fnpts)
        if not npts:
            raise SPCError("Subfile reports zero data points.")

        if per_sub_x:
            end = offset + 4 * npts
            if len(data) < end:
                raise SPCError("File ends inside a per-subfile X block.")
            x = np.frombuffer(
                data, dtype=np.dtype(endian + "f4"), count=npts, offset=offset
            ).astype(np.float64)
            offset = end
        else:
            x = shared_x if shared_x is not None else np.arange(npts, dtype=float)
            if len(x) != npts:
                x = np.linspace(ffirst, flast, npts)

        # Per-subfile exponent wins when it is set; otherwise fall back to the
        # file-level exponent. 0x80 (-128) means the Y values are IEEE floats.
        exp = fexp if fexp == -128 else (subexp if subexp != 0 else fexp)

        needed = offset + (2 if sixteen_bit and exp != -128 else 4) * npts
        if len(data) < needed:
            raise SPCError(
                f"File ends inside trace {i + 1}'s Y data -- it looks truncated."
            )
        y, offset = _y_from_bytes(data, offset, npts, exp, sixteen_bit, endian)

        xs.append(x)
        ys.append(y)
        z_values.append(float(subtime))

    meta = {
        "format": f"SPC (version 0x{fversn:02X})",
        "fversn": fversn,
        "ftflgs": ftflgs,
        "fexper": fexper,
        "fxtype": fxtype,
        "fytype": fytype,
        "fztype": fztype,
        "n_points": fnpts,
        "n_subfiles": n_sub,
        "first": ffirst,
        "last": flast,
        "date": _decode_date(fdate),
        "comment": fcmnt,
        "resolution": fres,
        "source": fsource,
    }
    return Spectrum(xs, ys, meta, z_values, x_label, y_label)
