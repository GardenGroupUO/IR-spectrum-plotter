"""
opus_reader.py -- reader for Bruker OPUS spectrum files.

OPUS files are what a Bruker instrument (Alpha, Tensor, Vertex ...) writes by
default. They usually have a *number* as their extension -- ``.0``, ``.1``,
``.17`` -- because OPUS increments it each time you save under the same name.

The layout is a block directory rather than one fixed header:

    bytes  0-3    magic 0x0A0AFEFE
           4-11   program version (double)
           12-15  offset of the block directory
           16-19  directory capacity
           20-23  directory entries in use

    each directory entry, 12 bytes: (block type, length in 32-bit words, offset)

Data blocks hold 32-bit floats. Each has a matching "status" block (its type
with bit 4 set) holding the point count and the first and last x values, so the
x axis is reconstructed rather than stored.

Needs only numpy, so it runs in the browser with nothing to download. Returns
the same ``Spectrum`` object as ``spc_reader``, so everything downstream --
CSV export, plotting, peak picking -- works unchanged.

    from opus_reader import read_opus
    s = read_opus("Benzoic_acid_14_23.17")
    s.to_csv("benzoic.csv")
"""

from __future__ import annotations

import struct

import numpy as np

from spc_reader import Spectrum, SPCError

__all__ = ["read_opus", "is_opus", "OpusError"]

MAGIC = 0xFEFE0A0A


class OpusError(SPCError):
    """Raised when a file is not a readable OPUS file."""


# Data block kinds, keyed by the low 16 bits of the block type word. Each has a
# status block at ``kind | 0x0010`` describing its axis.
BLOCK_KINDS = {
    0x100F: ("AB", "Absorbance", 2),
    0x140F: ("TR", "Transmittance", 128),
    0x180F: ("KM", "Kubelka-Munk", 3),
    0x1C0F: ("RF", "Reflectance", 129),
    0x0407: ("ScSm", "Single channel (sample)", 0),
    0x0807: ("ScRf", "Single channel (reference)", 0),
    0x040B: ("IgSm", "Interferogram (sample)", 1),
    0x080B: ("IgRf", "Interferogram (reference)", 1),
}

# Which block to hand back when a file holds several. Absorbance first.
PREFERENCE = [0x100F, 0x140F, 0x180F, 0x1C0F, 0x0407, 0x0807, 0x040B, 0x080B]

X_UNITS = {
    "WN": "Wavenumber (cm-1)",
    "MI": "Wavelength (um)",
    "LGW": "log Wavenumber",
    "PNT": "Data points",
}


def is_opus(source) -> bool:
    """True if this looks like an OPUS file. Cheap enough to use for sniffing."""
    try:
        if isinstance(source, (bytes, bytearray)):
            head = bytes(source[:4])
        elif hasattr(source, "read"):
            pos = source.tell()
            head = source.read(4)
            source.seek(pos)
        else:
            with open(source, "rb") as fh:
                head = fh.read(4)
    except Exception:
        return False
    return len(head) == 4 and struct.unpack("<I", head)[0] == MAGIC


def _read_params(data, offset, size):
    """Parse a parameter block: 3-char name, int16 type, int16 length, value."""
    out = {}
    pos, end = offset, min(offset + size, len(data))
    while pos < end - 4:
        name = data[pos:pos + 3].decode("latin-1", "replace")
        try:
            dtype, words = struct.unpack_from("<hh", data, pos + 4)
        except struct.error:
            break
        pos += 8
        if name == "END":
            break
        if words < 0 or pos + words * 2 > len(data):
            break
        raw = data[pos:pos + words * 2]
        pos += words * 2
        try:
            if dtype == 0:
                out[name] = struct.unpack_from("<i", raw)[0]
            elif dtype == 1:
                out[name] = struct.unpack_from("<d", raw)[0]
            else:
                out[name] = raw.split(b"\x00")[0].decode("latin-1", "replace").strip()
        except (struct.error, IndexError):
            continue
    return out


def read_opus(source) -> Spectrum:
    """Read a Bruker OPUS file.

    ``source`` may be a path, a file-like object, or raw bytes. When the file
    holds several kinds of data, the absorbance spectrum is returned and the
    others are listed in ``spectrum.meta['other_blocks']``.
    """
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    elif hasattr(source, "read"):
        data = source.read()
    else:
        with open(source, "rb") as fh:
            data = fh.read()

    if len(data) < 24:
        raise OpusError(f"File is only {len(data)} bytes -- too short to be an OPUS file.")
    if struct.unpack_from("<I", data, 0)[0] != MAGIC:
        raise OpusError("This is not an OPUS file (its identifying bytes are wrong).")

    version = struct.unpack_from("<d", data, 4)[0]
    dir_start, dir_max, dir_used = struct.unpack_from("<III", data, 12)
    if dir_used <= 0 or dir_start + 12 * dir_used > len(data):
        raise OpusError("The block directory is unreadable -- the file may be truncated.")

    blocks = []
    for i in range(dir_used):
        block_type, words, offset = struct.unpack_from("<III", data, dir_start + 12 * i)
        blocks.append((block_type, words * 4, offset))

    # Every parameter block merged together, for the metadata summary.
    meta_params = {}
    for block_type, size, offset in blocks:
        kind = block_type & 0xFFFF
        if kind in BLOCK_KINDS or block_type == 0x00003400 or size > 4096:
            continue
        if offset + size <= len(data):
            meta_params.update(_read_params(data, offset, size))

    found = {}
    for block_type, size, offset in blocks:
        kind = block_type & 0xFFFF
        if kind not in BLOCK_KINDS or offset + size > len(data):
            continue
        status = next((b for b in blocks if (b[0] & 0xFFFF) == kind | 0x0010), None)
        if status is None:
            continue
        axis = _read_params(data, status[2], status[1])
        npts, first, last = axis.get("NPT"), axis.get("FXV"), axis.get("LXV")
        if not npts or first is None or last is None:
            continue
        available = (len(data) - offset) // 4
        npts = min(int(npts), available, size // 4)
        if npts < 2:
            continue
        y = np.frombuffer(data, dtype="<f4", count=npts, offset=offset).astype(np.float64)
        y = y * float(axis.get("CSF", 1.0) or 1.0)     # y scaling factor
        found[kind] = (np.linspace(float(first), float(last), npts), y, axis)

    if not found:
        raise OpusError(
            "No spectrum was found in this OPUS file. It may hold only settings, "
            "or be a kind of block this reader does not handle."
        )

    chosen = next((k for k in PREFERENCE if k in found), sorted(found)[0])
    x, y, axis = found[chosen]
    short, y_label, fytype = BLOCK_KINDS[chosen]

    date = None
    raw_date, raw_time = meta_params.get("DAT"), meta_params.get("TIM")
    if raw_date:
        date = f"{raw_date} {raw_time.split('(')[0].strip()}" if raw_time else raw_date

    others = [BLOCK_KINDS[k][0] for k in found if k != chosen]
    comment = meta_params.get("SNM") or ""
    resolution = meta_params.get("RES")

    meta = {
        "format": f"Bruker OPUS (version {version:.0f})",
        "block": short,
        "other_blocks": others,
        "instrument": meta_params.get("INS"),
        "scans": meta_params.get("NSS"),
        "experiment": meta_params.get("EXP"),
        "operator": meta_params.get("CNM"),
        "detector": meta_params.get("DTC"),
        "n_points": len(y),
        "n_subfiles": 1,
        "first": float(x[0]),
        "last": float(x[-1]),
        "date": date,
        "comment": comment,
        "resolution": f"{resolution} cm-1" if resolution is not None else "",
        "source": meta_params.get("SRC", ""),
        "fytype": fytype,
        "fxtype": 1 if meta_params.get("DXU", "WN") == "WN" else 0,
        "params": meta_params,
    }

    x_label = X_UNITS.get(str(axis.get("DXU", "WN")).strip(), "Wavenumber (cm-1)")
    return Spectrum([x], [y], meta, [0.0], x_label, y_label)
