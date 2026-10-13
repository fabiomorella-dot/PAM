"""FCS check: fit simulated autocorrelations and compare with theory.

Runs pamsim (with and without fast-forward) and PAM's original kernel on the
same free-diffusion setup, fits a 3D diffusion model with offset and compares
N and tau_D with N = c*pi^1.5*wr^2*wz and tau_D = wr^2/(4D).

Run:  python validation/check_fcs.py [--no-original]
"""
import argparse
import os
import sys
import time

import numpy as np
from scipy.optimize import curve_fit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pamsim import SimSettings, Species, simulate, correlate_blocks  # noqa: E402

D, WR, WZ, N = 50.0, 200.0, 1000.0, 40
BOX = np.array([4000.0, 4000.0, 6000.0])


def fit(mt, total_ticks, freq_hz):
    lags, g, sem, _ = correlate_blocks(mt, mt, total_ticks, n_blocks=10)
    tau = lags / freq_hz
    model = lambda t, n, td, g0: g0 + 1 / n / (1 + t / td) / np.sqrt(1 + t / ((WZ / WR) ** 2 * td))  # noqa: E731
    ok = (tau > 2e-6) & (tau < 0.05) & (sem > 0)
    p, _ = curve_fit(model, tau[ok], g[ok], p0=[0.1, 2e-4, 0], sigma=sem[ok])
    return p


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-original", action="store_true")
    ap.add_argument("--runs", type=int, default=6)
    args = ap.parse_args()
    variants = ["pamsim, fast-forward", "pamsim, step-by-step"] + ([] if args.no_original else ["original C++"])
    for label in variants:
        out = []
        t0 = time.time()
        for seed in range(args.runs):
            s = SimSettings(box_size=BOX, sim_time=8, frames=1, freq=1000, seed=seed,
                            fast_forward=(label == "pamsim, fast-forward"),
                            species=[Species(D=D, N=N, wr=[WR] * 4, wz=[WZ] * 4, brightness=[100] * 4)])
            if label == "original C++":
                from validation.reference import ref_simulate
                mt = np.sort(ref_simulate(s, seed=seed)[0])
            else:
                mt = simulate(s).macrotimes[0]
            out.append(fit(mt, s.sim_time * 1e6, 1e6))
        out = np.array(out)
        se = out.std(axis=0, ddof=1) / np.sqrt(len(out))
        print(f"{label:22s} N = {out[:, 0].mean():.4f} +- {se[0]:.4f}   "
              f"tauD = {out[:, 1].mean() * 1e6:6.1f} +- {se[1] * 1e6:4.1f} us   ({time.time() - t0:.0f} s)")
    n_th = N / np.prod(BOX * 1e-3) * np.pi ** 1.5 * (WR * 1e-3) ** 2 * WZ * 1e-3
    print(f"{'theory':22s} N = {n_th:.4f}             tauD = {(WR * 1e-3) ** 2 / (4 * D) * 1e6:6.1f} us")
