"""Make example CSV waveforms for the Simulation mode upload.
    python make_samples.py     ->  qpsk_with_time.csv, two_tone_iq.csv, real_only.csv
"""
import numpy as np

rng = np.random.default_rng(7)

# 1) QPSK, 8 samples per symbol, root-raised-ish shaping by moving average, with a time column (seconds)
fs, sps, nsym = 2_000_000, 8, 2500
sym = (rng.integers(0, 2, nsym) * 2 - 1) + 1j * (rng.integers(0, 2, nsym) * 2 - 1)
x = np.repeat(sym, sps)
x = np.convolve(x, np.ones(sps) / sps, mode="same") / np.sqrt(2)
x += 0.02 * (rng.standard_normal(x.size) + 1j * rng.standard_normal(x.size))
t = np.arange(x.size) / fs
with open("qpsk_with_time.csv", "w") as f:
    f.write("time_s,I,Q\n")
    for a, b in zip(t, x):
        f.write(f"{a:.9f},{b.real:.6f},{b.imag:.6f}\n")

# 2) two tones, no header, no time (needs the sample rate to be entered)
n = 16384
t = np.arange(n) / 1e6
y = 0.7 * np.exp(2j * np.pi * 120e3 * t) + 0.3 * np.exp(-2j * np.pi * 310e3 * t)
np.savetxt("two_tone_iq.csv", np.c_[y.real, y.imag], delimiter=",", fmt="%.6f")

# 3) real-only signal, one column
np.savetxt("real_only.csv", np.cos(2 * np.pi * 50e3 * np.arange(4096) / 1e6), fmt="%.6f", header="I", comments="")
print("written")
