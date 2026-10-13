"""Compare pamsim with PAM's original C++ kernels, scenario by scenario.

For every scenario both implementations are run with several seeds and
compared statistically:

* mean count rate per photon type (laser, excited dye, emitting dye,
  detection channel) and mean microtime per photon type: z-score of the
  difference of the means (|z| > 4 is flagged),
* microtime histograms per photon type (pooled photons): chi-square test.

Run:  python validation/compare_kernels.py  [--reps 12]
"""
import argparse
import os
import sys
import time

import numpy as np
from scipy import stats as st

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pamsim import SimSettings, Species, simulate  # noqa: E402
from validation.reference import ref_simulate  # noqa: E402


def port_raw(s, seed):
    s.seed = seed
    r = simulate(s)
    return (np.concatenate(r.macrotimes), np.concatenate(r.microtimes), np.concatenate(r.labels),
            np.concatenate([np.full(len(m), 1 if c >= 4 else 0, np.uint8) for c, m in enumerate(r.macrotimes)]))


def ref_raw(s, seed, maps):
    mt, mi, ch, pol = ref_simulate(s, seed=seed, maps=maps)
    if s.advanced and s.use_aniso:  # Sim.m discards half of the perpendicular photons
        keep = (pol == 0) | (np.random.default_rng(seed).random(pol.size) < 0.5)
        mt, mi, ch, pol = mt[keep], mi[keep], ch[keep], pol[keep]
    return mt, mi, ch, pol


def label(code):
    return f"[{code >> 6},{(code >> 4) & 3},{(code >> 2) & 3},{code & 3}]"


def summary(raw, T):
    mt, mi, ch, pol = raw
    out = {"rate total": mt.size / T}
    for code in np.unique(ch):
        sel = ch == code
        out["rate " + label(code)] = sel.sum() / T
        out["mi   " + label(code)] = mi[sel].mean()
    if pol.any():
        out["fraction perpendicular"] = pol.mean()
    return out


def compare(name, s, reps, maps=None):
    T = s.sim_time
    t0 = time.time(); R = [ref_raw(s, 100 + k, maps) for k in range(reps)]; tr = time.time() - t0
    t0 = time.time(); P = [port_raw(s, 200 + k) for k in range(reps)]; tp = time.time() - t0
    sr = [summary(r, T) for r in R]; spp = [summary(p, T) for p in P]
    print(f"\n=== {name}   (original: {tr:.1f} s, pamsim: {tp:.1f} s for {reps} runs each)")
    print(f"  {'quantity':26s}{'original':>13s}{'pamsim':>13s}{'z':>8s}")
    worst = 0.0
    for k in sorted(set().union(*sr, *spp)):
        a = np.array([d[k] for d in sr if k in d]); b = np.array([d[k] for d in spp if k in d])
        if k.startswith("rate"):
            a = np.array([d.get(k, 0.0) for d in sr]); b = np.array([d.get(k, 0.0) for d in spp])
        if a.size < 2 or b.size < 2 or (a.mean() == 0 and b.mean() == 0):
            continue
        se = np.sqrt(a.var(ddof=1) / a.size + b.var(ddof=1) / b.size)
        z = (b.mean() - a.mean()) / se if se > 0 else 0.0
        worst = max(worst, abs(z))
        print(f"  {k:26s}{a.mean():13.3f}{b.mean():13.3f}{z:+8.2f}{'   <-- check' if abs(z) > 4 else ''}")
    rmi = np.concatenate([r[1] for r in R]).astype(int); rch = np.concatenate([r[2] for r in R])
    pmi = np.concatenate([p[1] for p in P]).astype(int); pch = np.concatenate([p[2] for p in P])
    pmin = 1.0
    for code in np.unique(rch):
        a = rmi[rch == code]; b = pmi[pch == code]
        if a.size < 200 or b.size < 200:
            continue
        lo, hi = np.percentile(np.concatenate([a, b]), [0.5, 99.5])
        edges = np.linspace(lo, hi + 1, 31)
        ha, _ = np.histogram(a, edges); hb, _ = np.histogram(b, edges)
        ok = (ha + hb) > 10
        chi2, p, dof, _ = st.chi2_contingency(np.vstack([ha[ok], hb[ok]]))
        pmin = min(pmin, p)
        print(f"  microtime histogram {label(code)}: chi2/dof = {chi2 / dof:4.2f}, p = {p:.3f}")
    return worst, pmin


def scenarios():
    base = dict(box_size=[2000, 2000, 3000], sim_time=0.4, frames=2, freq=1000)
    yield "basic: 1 colour, lifetime", SimSettings(**base, species=[Species(D=40, N=4, ExP=np.eye(4) * 0.3, LT=[3] * 4)]), None

    exp_ = np.eye(4) * 0.3; exp_[1, 0] = 0.05          # acceptor directly excited by laser 1
    cross = np.eye(4); cross[1, 0] = 0.1                # donor photons leaking into channel 2
    detp = np.ones((4, 4)); detp[0, 0] = 0.8; detp[1, 1] = 0.6
    sp = Species(D=40, N=4, color=2, fret=2, ExP=exp_, Cross=cross, DetP=detp, LT=[4, 2, 1, 1], dY=[0, 30, 0, 0])
    yield "basic: 2-colour PIE, static FRET, crosstalk, direct exc.", SimSettings(**base, species=[sp]), None

    blp = np.zeros((4, 4)); blp[0, 0] = 2e-3; blp[1, 0] = 5e-3
    yield "basic: photobleaching", SimSettings(**base, species=[Species(D=20, N=4, color=2, fret=2, ExP=np.eye(4) * 0.3, BlP=blp)]), None

    yield "basic: raster scan", SimSettings(box_size=[2000, 2000, 2000], sim_time=0.4, frames=4, scan_type=2,
                                            pixels=[20, 20], pixel_size=[50, 50], times=[250, 5, 0.1],
                                            species=[Species(D=5, N=6, ExP=np.eye(4) * 0.3)]), None

    sp = Species(D=40, N=4, color=2, fret=2, ExP=np.eye(4) * 0.3, LT=[4, 3, 1, 1], aniso=np.tile([0.38, 2.0, 0.05, 1.0], (4, 1)))
    yield "advanced: IRF + anisotropy + sigma(R) + linker", SimSettings(
        **base, use_irf=True, irf_width=300, use_aniso=True, use_fret_width=True, heterogeneity_update=1.0,
        use_linker_width=True, linker_width=6, species=[sp]), None

    R1 = np.zeros((4, 4)); R1[1, 0] = 40
    R2 = np.zeros((4, 4)); R2[1, 0] = 80
    yield "advanced: dynamic 2-state FRET", SimSettings(
        **base, dynamic_rates=np.array([[0, 2.0], [1.0, 0]]),
        species=[Species(name="lo", D=40, N=3, color=2, fret=3, ExP=np.eye(4) * 0.3, R=R1),
                 Species(name="hi", D=20, N=3, color=2, fret=3, ExP=np.eye(4) * 0.3, R=R2)]), None

    yy, xx = np.meshgrid(np.arange(2000), np.arange(2000))
    for name, mp, bt in (("quenching map", np.where(xx < 1000, 1.0, 0.3), 2),
                         ("restricted zones", np.where((xx // 250 + yy // 250) % 2 == 0, 1.0, 0.0), 3),
                         ("transition barrier", np.where(xx < 1000, 0.0, 0.8), 4)):
        yield f"basic: {name}", SimSettings(**base, maps=mp, species=[Species(D=40, N=4, ExP=np.eye(4) * 0.3, barrier=bt)]), mp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=12)
    args = ap.parse_args()
    results = [(name,) + compare(name, s, args.reps, maps) for name, s, maps in scenarios()]
    print("\nSummary (max |z| over all means, smallest histogram p-value):")
    for name, z, p in results:
        print(f"  {name:55s} max|z| = {z:4.2f}   min p = {p:.3f}")
