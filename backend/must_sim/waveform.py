"""CSV waveform import and the data the plots need.

Accepted files (comma, semicolon, tab or space separated; optional header):
    1 column   -> I only (real signal)
    2 columns  -> I, Q
    3 columns  -> time, I, Q
With a header, columns are found by name (time/t, i/real/in-phase, q/imag/quadrature).
Units in a time header such as "time_us", "t (ms)" are honoured; no unit means seconds.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np

MAX_BYTES = 50 * 1024 * 1024
MAX_PLOT_POINTS = 4000
HEAD_SAMPLES = 10000  # raw samples shown first, so the waveform shape is readable
_UNITS = {"s": 1.0, "sec": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9}


class WaveformError(Exception):
    pass


@dataclass
class Parsed:
    name: str
    i: np.ndarray
    q: np.ndarray | None
    t: np.ndarray | None  # seconds, relative to the first sample
    file_rate: float | None  # sample rate worked out from the time column
    warnings: list[str] = field(default_factory=list)
    columns: str = ""


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _role(name: str) -> tuple[str | None, float]:
    n = name.strip().strip('"').lower()
    unit = 1.0
    m = re.search(r"[\(\[_ ](s|sec|ms|us|µs|ns)[\)\]]?$", n)
    if m:
        unit = _UNITS.get(m.group(1), 1.0)
    leaf = n.split("/")[-1].split(".")[-1].strip(" _")
    base = re.split(r"[\(\[]", leaf)[0].strip(" _")
    base = re.sub(r"_(s|sec|ms|us|µs|ns)$", "", base)

    if base in ("n", "index", "idx", "sample", "samples", "sample_index",
                "sample in buffer", "sample in window", "sample_in_buffer", "sample_in_window", "trigger"):
        return "index", 1.0
    if base in ("t", "time", "timestamp", "time_stamp"):
        return "t", unit
    if (base in ("i", "in-phase", "inphase", "in_phase", "real", "re", "idata", "i_data", "ich", "i_ch", "i_out", "iout")
            or re.search(r"(^|_)(i|i_out|inphase|idata|re|real)$", base)):
        return "i", 1.0
    if (base in ("q", "quadrature", "imag", "imaginary", "im", "qdata", "q_data", "qch", "q_ch", "q_out", "qout")
            or re.search(r"(^|_)(q|q_out|quadrature|qdata|im|imag)$", base)):
        return "q", 1.0
    return None, 1.0


def parse_csv(raw: bytes, name: str = "waveform.csv") -> Parsed:
    if len(raw) > MAX_BYTES:
        raise WaveformError(f"File is {len(raw) / 1e6:.0f} MB. The limit is {MAX_BYTES // 1_000_000} MB.")
    text = raw.decode("utf-8-sig", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise WaveformError("The file is empty.")

    first = lines[0]
    counts = {",": first.count(","), ";": first.count(";"), "\t": first.count("\t")}
    delim = max(counts, key=counts.get)
    if counts[delim] == 0:
        delim = None  # whitespace or a single column
    tokens = [t.strip() for t in (first.split(delim) if delim else first.split())]
    has_header = any(not _is_number(t) for t in tokens)

    start_row = 0
    if has_header:
        start_row = 1
        # Skip additional non-numeric header/metadata lines (e.g. Vivado ILA "Radix - ..." row)
        while start_row < len(lines):
            row_str = lines[start_row].strip()
            if not row_str or row_str.startswith("#"):
                start_row += 1
                continue
            row_tokens = [t.strip() for t in (row_str.split(delim) if delim else row_str.split())]
            if any(not _is_number(t) for t in row_tokens):
                start_row += 1
            else:
                break

    body = lines[start_row:]
    if not body:
        raise WaveformError("The file has a header but no data rows.")

    try:
        data = np.loadtxt(io.StringIO("\n".join(body)), delimiter=delim, ndmin=2, dtype=np.float64)
    except ValueError as e:
        raise WaveformError(f"Could not read the numbers in this file: {e}. Every data row needs the same number of numeric columns.")
    if data.shape[0] < 2:
        raise WaveformError("The file needs at least 2 samples.")
    if not np.all(np.isfinite(data)):
        bad = int(np.count_nonzero(~np.isfinite(data)))
        raise WaveformError(f"{bad} values are not finite numbers (NaN or infinity). Remove or fix them and upload again.")

    ncols = data.shape[1]
    warnings: list[str] = []
    idx = {"t": None, "i": None, "q": None}
    time_scale = 1.0
    if has_header:
        unrecognised = []
        for c, tok in enumerate(tokens[:ncols]):
            role, unit = _role(tok)
            if role in idx and idx[role] is None:
                idx[role] = c
                if role == "t":
                    time_scale = unit
            elif role is None:
                leaf = tok.split("/")[-1].split(".")[-1].strip()
                unrecognised.append(leaf)
        if unrecognised:
            if len(unrecognised) <= 2:
                for u in unrecognised:
                    warnings.append(f"Ignored auxiliary column '{u}'.")
            else:
                warnings.append(f"Ignored {len(unrecognised)} auxiliary columns (only I and Q are used).")
    if idx["i"] is None:  # no usable names: go by position
        if has_header and any(v is not None for v in idx.values()):
            raise WaveformError("Found some named columns but no I column. Name the in-phase column 'I' (or 'real').")
        order = {1: ("i",), 2: ("i", "q"), 3: ("t", "i", "q")}.get(ncols)
        if order is None:
            order = ("t", "i", "q")
            warnings.append(f"The file has {ncols} columns. Using the first three as time, I, Q.")
        idx = {"t": None, "i": None, "q": None}
        for c, role in enumerate(order):
            idx[role] = c

    i = data[:, idx["i"]].copy()
    q = data[:, idx["q"]].copy() if idx["q"] is not None else None
    t = None
    file_rate = None
    if idx["t"] is not None:
        tt = data[:, idx["t"]] * time_scale
        dt = np.diff(tt)
        med = float(np.median(dt))
        if med <= 0:
            warnings.append("Time column is not increasing, so it is ignored.")
        else:
            if float(np.max(np.abs(dt - med))) / med > 0.01:
                warnings.append("Time stamps are not evenly spaced. The sample rate uses the median spacing.")
            t = tt - tt[0]
            file_rate = 1.0 / med

    cols = "time, I, Q" if (t is not None and q is not None) else "I, Q" if q is not None else "time, I" if t is not None else "I"
    return Parsed(name=name, i=i, q=q, t=t, file_rate=file_rate, warnings=warnings, columns=cols)


def _pick_indices(i: np.ndarray, q: np.ndarray | None, max_points: int) -> np.ndarray:
    """Min/max decimation: keep each bucket's lowest and highest sample of I and Q so
    short peaks never disappear from the plot."""
    n = len(i)
    if n <= max_points:
        return np.arange(n)
    buckets = max_points // 4
    edges = np.linspace(0, n, buckets + 1, dtype=np.int64)
    keep = set()
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        for arr in (i, q):
            if arr is None:
                continue
            seg = arr[a:b]
            keep.add(int(a + np.argmin(seg)))
            keep.add(int(a + np.argmax(seg)))
        keep.add(int(a))
    return np.array(sorted(keep), dtype=np.int64)


def _spectrum(i: np.ndarray, q: np.ndarray | None, fs: float) -> dict | None:
    n = len(i)
    if n < 16:
        return None
    x = i + 1j * q if q is not None else i.astype(np.float64)
    seg = 1 << int(np.floor(np.log2(min(n, 65536))))
    seg = max(seg, 16)
    hop = seg // 2
    starts = np.arange(0, n - seg + 1, hop)
    if len(starts) > 32:
        starts = starts[np.linspace(0, len(starts) - 1, 32, dtype=np.int64)]
    win = np.hanning(seg)
    acc = None
    for s in starts:
        block = x[s : s + seg]
        block = block * win
        f = np.fft.fft(block) if q is not None else np.fft.rfft(block)
        p = np.abs(f) ** 2
        acc = p if acc is None else acc + p
    psd = acc / len(starts)
    if q is not None:
        psd = np.fft.fftshift(psd)
        freq = np.fft.fftshift(np.fft.fftfreq(seg, d=1.0 / fs))
    else:
        freq = np.fft.rfftfreq(seg, d=1.0 / fs)
    peak = float(np.max(psd))
    if peak <= 0:
        return None
    db = 10 * np.log10(np.maximum(psd / peak, 1e-12))
    # max-pool for display so narrow carriers stay visible
    if len(db) > MAX_PLOT_POINTS:
        k = int(np.ceil(len(db) / MAX_PLOT_POINTS))
        m = (len(db) // k) * k
        db_p = db[:m].reshape(-1, k).max(axis=1)
        fr_p = freq[:m].reshape(-1, k).mean(axis=1)
        db, freq = db_p, fr_p
    return {"freq": freq.tolist(), "db": np.round(db, 2).tolist(), "complex": q is not None, "segment": seg, "averages": int(len(starts))}


def _detect_frequencies(i: np.ndarray, fs: float | None, spectrum: dict | None = None) -> dict | None:
    """Detect dominant / FSK frequencies using zero-crossing periods, with FFT peak fallback."""
    if len(i) < 16:
        return None
    scale = fs if fs else 1.0

    i_centered = i - np.mean(i)
    zc = np.where(np.diff(np.sign(i_centered)))[0]
    if len(zc) >= 4:
        hp = np.diff(zc)
        hp = hp[hp > 1]
        if len(hp) > 0:
            vals, counts = np.unique(hp, return_counts=True)
            order = np.argsort(counts)[::-1]
            sig_vals = vals[order][counts[order] >= 0.10 * counts[order][0]]
            periods = np.sort(sig_vals) * 2.0
            clusters: list[list[float]] = []
            for p in periods:
                if not clusters or abs(p - clusters[-1][-1]) / clusters[-1][-1] > 0.25:
                    clusters.append([float(p)])
                else:
                    clusters[-1].append(float(p))
            rep = sorted([float(np.mean(c)) for c in clusters])
            if len(rep) == 2 and (rep[1] / rep[0]) >= 1.3:
                f_high = float(scale / rep[0])
                f_low = float(scale / rep[1])
                return {
                    "is_fsk": True,
                    "f_high": f_high,
                    "f_low": f_low,
                    "center": float((f_high + f_low) / 2.0),
                    "deviation": float((f_high - f_low) / 2.0),
                    "period_high": float(rep[0]),
                    "period_low": float(rep[1]),
                }
            elif len(rep) == 1:
                f = float(scale / rep[0])
                return {
                    "is_fsk": False,
                    "center": f,
                    "f_high": f,
                    "f_low": f,
                    "deviation": 0.0,
                    "period": float(rep[0]),
                }

    if spectrum is not None:
        freq = np.array(spectrum["freq"])
        db = np.array(spectrum["db"])
        peak_idx = int(np.argmax(db))
        f_peak = float(abs(freq[peak_idx]))
        if f_peak > 0:
            return {
                "is_fsk": False,
                "center": f_peak,
                "f_high": f_peak,
                "f_low": f_peak,
                "deviation": 0.0,
                "period": float(scale / f_peak),
            }
    return None


def analyze(p: Parsed, sample_rate: float | None = None) -> dict:
    """Everything the UI plots. sample_rate overrides the one found in the file."""
    n = len(p.i)
    fs = None
    source = None
    if sample_rate:
        fs, source = float(sample_rate), "user"
    elif p.file_rate:
        fs, source = float(p.file_rate), "file"

    if p.t is not None and source == "file":
        x_full = p.t
    elif fs:
        x_full = np.arange(n) / fs
    else:
        x_full = np.arange(n, dtype=np.float64)

    sel = _pick_indices(p.i, p.q, MAX_PLOT_POINTS)
    h = min(n, HEAD_SAMPLES)
    head = {"x": x_full[:h].tolist(), "i": p.i[:h].tolist(), "q": p.q[:h].tolist() if p.q is not None else None}
    scatter = None
    if p.q is not None:
        step = max(1, n // 3000)
        scatter = {"i": p.i[::step].tolist(), "q": p.q[::step].tolist()}

    peak = float(max(np.max(np.abs(p.i)), np.max(np.abs(p.q)) if p.q is not None else 0.0))
    rms_i = float(np.sqrt(np.mean(p.i**2)))
    rms_q = float(np.sqrt(np.mean(p.q**2))) if p.q is not None else None
    spectrum = _spectrum(p.i, p.q, fs if fs else 1.0)
    frequency = _detect_frequencies(p.i, fs, spectrum)

    warnings = list(p.warnings)
    if fs is None:
        warnings.append("No sample rate in the file. Enter it to get time in seconds and frequency in Hz.")
    return {
        "name": p.name,
        "n_samples": n,
        "columns": p.columns,
        "has_q": p.q is not None,
        "sample_rate": fs,
        "sample_rate_source": source,
        "duration_s": (n / fs) if fs else None,
        "x_is_time": fs is not None,
        "time": {"x": x_full[sel].tolist(), "i": p.i[sel].tolist(), "q": p.q[sel].tolist() if p.q is not None else None, "decimated": bool(len(sel) < n), "points": int(len(sel)), "head": head},
        "spectrum": spectrum,
        "frequency": frequency,
        "constellation": scatter,
        "stats": {"peak": peak, "rms_i": rms_i, "rms_q": rms_q, "dc_i": float(np.mean(p.i)), "dc_q": float(np.mean(p.q)) if p.q is not None else None},
        "warnings": warnings,
    }


def to_int16(p: Parsed) -> tuple[np.ndarray, np.ndarray, float]:
    """Scale to the int16 range for sending. Returns I, Q and the full-scale value used."""
    full = float(max(np.max(np.abs(p.i)), np.max(np.abs(p.q)) if p.q is not None else 0.0))
    if full == 0:
        raise WaveformError("All samples are zero. There is nothing to send.")
    ii = np.round(p.i / full * 32767).astype(np.int16)
    qq = np.round(p.q / full * 32767).astype(np.int16) if p.q is not None else np.zeros_like(ii)
    return ii, qq, full
