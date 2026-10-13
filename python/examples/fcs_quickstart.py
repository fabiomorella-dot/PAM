"""Simulate an FCS measurement, save it for PAM, correlate and fit it.

    python examples/fcs_quickstart.py

Writes ``fcs_example_1.sim`` (open it in PAM: Load TCSPC data -> "Pam
Simulation Files") and ``fcs_example.png``.
"""
import os
import sys

import numpy as np
from scipy.optimize import curve_fit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pamsim import SimSettings, Species, simulate, correlate_blocks  # noqa: E402

# --- set up exactly like the Sim.m GUI (same names, same units) -------------
settings = SimSettings(
    box_size=[4000, 4000, 6000],  # nm
    freq=1000,                    # kHz sampling of the random walk
    sim_time=30,                  # s
    frames=1,
    seed=42,
    species=[Species(D=50,                  # um^2/s
                     N=40,                  # particles in the box
                     wr=[200] * 4, wz=[1000] * 4,   # nm
                     brightness=[100] * 4,  # kHz
                     LT=[4] * 4)],          # ns
)
print(f"concentration: {settings.concentration_nM():.2f} nM")

result = simulate(settings, progress=True)
print(f"simulated {settings.sim_time} s in {result.elapsed:.1f} s, "
      f"count rate {result.count_rates_khz()[0]:.1f} kHz")
result.save_sim("fcs_example_1.sim")

# --- correlate like PAM's Correlate tab (10 sections) -----------------------
total_ticks = result.header["Frames"] * result.header["FrameTime"]
lags, g, sem, _ = correlate_blocks(result.macrotimes[0], result.macrotimes[0], total_ticks, n_blocks=10)
tau = lags / result.freq_hz


def model(t, n, td, g0, p=1000 / 200):
    return g0 + 1 / n / (1 + t / td) / np.sqrt(1 + t / (p * p * td))


ok = (tau > 2e-6) & (tau < 0.05) & (sem > 0)
(n, td, g0), _ = curve_fit(model, tau[ok], g[ok], p0=[0.1, 2e-4, 0], sigma=sem[ok])
print(f"fit: N = {n:.3f}, tauD = {td * 1e6:.0f} us   "
      f"(theory: N = {40 / (4 * 4 * 6) * np.pi ** 1.5 * 0.04:.3f}, tauD = {0.04 / (4 * 50) * 1e6:.0f} us)")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit(0)

fig, ax = plt.subplots(figsize=(6.4, 4.0), facecolor="#fcfcfb")
ax.set_facecolor("#fcfcfb")
ax.errorbar(tau[ok], g[ok], yerr=sem[ok], fmt="o", ms=3, lw=0.8, alpha=0.8, color="#2a78d6", label="simulated (pamsim)")
ax.plot(tau[ok], model(tau[ok], n, td, g0), lw=2, color="#eb6834", label="3D diffusion fit", zorder=3)
ax.set_xscale("log")
ax.set_xlabel("lag time τ [s]", color="#52514e")
ax.set_ylabel("G(τ)", color="#52514e")
ax.set_title(f"FCS of simulated data: N = {n:.3f}, τD = {td * 1e6:.0f} µs", color="#0b0b0b", fontsize=11)
ax.grid(True, which="major", color="#e6e5e0", lw=0.6)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
ax.tick_params(colors="#52514e")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig("fcs_example.png", dpi=150)
print("wrote fcs_example.png")
