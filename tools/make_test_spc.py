"""Generate synthetic .spc files covering each variant the reader claims to support."""
import struct
import numpy as np

HEAD = "<4BI2dI4BI9s9sH8f130s30s2I2BHf48sfIfB187s"
SUB = "<BbHfffIIf4s"


def header(ftflgs, fexp, fnpts, ffirst, flast, fnsub, fxtype, fytype, comment=b""):
    return struct.pack(
        HEAD,
        ftflgs, 0x4B, 0, fexp & 0xFF,
        fnpts, ffirst, flast, fnsub,
        fxtype, fytype, 0, 0,
        (2024 << 20) | (3 << 16) | (14 << 11) | (9 << 6) | 30,
        b"4 cm-1", b"FT-IR",
        0,
        *([0.0] * 8),
        comment.ljust(130, b"\x00"), b"\x00" * 30,
        0, 0, 0, 0, 0, 1.0,
        b"\x00" * 48, 0.0, 0, 0.0, 0, b"\x00" * 187,
    )


def sub(subexp, npts, subtime=0.0, subindx=0):
    return struct.pack(SUB, 0, subexp, subindx, subtime, 0.0, 0.0, npts, 0, 0.0, b"\x00" * 4)


def spectrum(x):
    """A plausible IR-ish trace: baseline plus a few gaussian bands."""
    y = 0.05 + np.zeros_like(x)
    for centre, height, width in [(1750, 0.8, 18), (2950, 0.45, 40), (1100, 0.6, 25)]:
        y += height * np.exp(-0.5 * ((x - centre) / width) ** 2)
    return y


def write_float_even(path):
    """Evenly spaced X, IEEE float Y, single trace."""
    n = 1024
    x = np.linspace(4000.0, 400.0, n)
    y = spectrum(x)
    blob = header(0x00, -128, n, 4000.0, 400.0, 1, 1, 2, b"Synthetic float FT-IR")
    blob += sub(-128, n) + y.astype("<f4").tobytes()
    open(path, "wb").write(blob)
    return x, y


def write_fixed32(path):
    """Evenly spaced X, 32-bit fixed-point Y -- what most GRAMS files look like."""
    n = 512
    x = np.linspace(400.0, 4000.0, n)
    y = spectrum(x)
    exp = 2
    scale = 2.0 ** exp / 2 ** 32
    raw = np.round(y / scale).astype("<i4")
    blob = header(0x00, exp, n, 400.0, 4000.0, 1, 1, 2, b"Synthetic fixed-point")
    blob += sub(exp, n) + raw.tobytes()
    open(path, "wb").write(blob)
    return x, raw.astype(float) * scale


def write_fixed16(path):
    """16-bit fixed-point Y (TSPREC)."""
    n = 256
    x = np.linspace(400.0, 4000.0, n)
    y = spectrum(x)
    exp = 2
    scale = 2.0 ** exp / 2 ** 16
    raw = np.round(y / scale).astype("<i2")
    blob = header(0x01, exp, n, 400.0, 4000.0, 1, 1, 2)
    blob += sub(exp, n) + raw.tobytes()
    open(path, "wb").write(blob)
    return x, raw.astype(float) * scale


def write_xvals(path):
    """Shared but unevenly spaced X array (TXVALS)."""
    n = 300
    x = np.sort(np.random.default_rng(0).uniform(400, 4000, n))
    y = spectrum(x)
    blob = header(0x80, -128, n, x[0], x[-1], 1, 1, 2)
    blob += x.astype("<f4").tobytes()
    blob += sub(-128, n) + y.astype("<f4").tobytes()
    open(path, "wb").write(blob)
    return x.astype("<f4").astype(float), y


def write_multi(path, n_traces=5):
    """Several traces on one shared X grid (kinetics-style)."""
    n = 400
    x = np.linspace(4000.0, 400.0, n)
    blob = header(0x04, -128, n, 4000.0, 400.0, n_traces, 1, 2, b"Kinetics run")
    ys = []
    for i in range(n_traces):
        y = spectrum(x) * (1.0 - 0.15 * i)
        ys.append(y)
        blob += sub(-128, n, subtime=float(i * 30)) + y.astype("<f4").tobytes()
    open(path, "wb").write(blob)
    return x, ys


def write_xyxy(path, n_traces=3):
    """Each subfile carries its own X array (TXYXYS)."""
    blob = header(0x40 | 0x04, -128, 0, 0.0, 0.0, n_traces, 1, 2)
    out = []
    for i in range(n_traces):
        n = 120 + 30 * i
        x = np.linspace(400.0 + 50 * i, 4000.0, n)
        y = spectrum(x)
        out.append((x.astype("<f4").astype(float), y))
        blob += sub(-128, n, subtime=float(i))
        blob += x.astype("<f4").tobytes() + y.astype("<f4").tobytes()
    open(path, "wb").write(blob)
    return out


if __name__ == "__main__":
    import os, sys

    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    write_float_even(f"{out}/float_even.spc")
    write_fixed32(f"{out}/fixed32.spc")
    write_fixed16(f"{out}/fixed16.spc")
    write_xvals(f"{out}/xvals.spc")
    write_multi(f"{out}/multi.spc")
    write_xyxy(f"{out}/xyxy.spc")
    print("wrote fixtures to", out)
