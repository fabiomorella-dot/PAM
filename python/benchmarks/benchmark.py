"""Timing: original PAM kernels vs pamsim.

The "original" column runs the unmodified C++ kernels of PAM (compiled
natively by validation/reference.py) exactly the way Sim.m calls them: one
call per particle and frame, single threaded.  It therefore measures only
the compiled kernel; MATLAB's own overhead (parfor start-up, timers, growing
cell arrays) comes on top in a real Sim.m run.  With the Parallel Computing
Toolbox, Sim.m distributes particles over cores like pamsim does.

Run:  python benchmarks/benchmark.py [--no-original] [--quick]
"""
import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pamsim import SimSettings, Species, simulate  # noqa: E402


def scenarios(quick):
    t = 2.0 if quick else 10.0
    yield ("Sim.m defaults (D=1 um2/s, N=10, 5 um box, 1 MHz)",
           SimSettings(sim_time=t, frames=10))
    yield ("solution FCS (D=100 um2/s, N=50, 100 kHz brightness)",
           SimSettings(sim_time=t, frames=10, species=[Species(D=100, N=50, brightness=[100] * 4)]))
    exp_ = np.eye(4) * 0.1; exp_[1, 0] = 0.005
    cross = np.eye(4); cross[1, 0] = 0.05
    sp = Species(D=100, N=20, color=2, fret=2, ExP=exp_, Cross=cross, LT=[4, 3.5, 1, 1],
                 aniso=np.tile([0.38, 1.0, 0.05, 1.0], (4, 1)))
    yield ("smFRET PIE, 2 colours, IRF + anisotropy (advanced kernel)",
           SimSettings(sim_time=t, frames=10, use_irf=True, use_aniso=True, species=[sp]))


def time_port(s, threads, ff):
    s.n_threads = threads
    s.fast_forward = ff
    simulate(s)  # make sure everything is compiled
    t0 = time.perf_counter()
    r = simulate(s)
    return time.perf_counter() - t0, sum(len(m) for m in r.macrotimes)


def time_original(s):
    from validation.reference import ref_simulate
    t0 = time.perf_counter()
    mt = ref_simulate(s, seed=1)[0]
    return time.perf_counter() - t0, mt.size


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-original", action="store_true")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    ncpu = os.cpu_count()
    rows = []
    for name, s in scenarios(args.quick):
        print(f"\n{name}  ({s.sim_time:g} s simulated)")
        res = {}
        if not args.no_original:
            res["original C++, 1 core"] = time_original(s)
        res["pamsim, 1 core, step-by-step"] = time_port(s, 1, False)
        res["pamsim, 1 core, fast-forward"] = time_port(s, 1, True)
        res[f"pamsim, {ncpu} cores, fast-forward"] = time_port(s, ncpu, True)
        ref = res.get("original C++, 1 core", (None,))[0]
        for k, (t, n) in res.items():
            sp = f"  x{ref / t:6.1f}" if ref else ""
            print(f"  {k:36s} {t:8.2f} s   {n:9d} photons{sp}")
        rows.append((name, res))
