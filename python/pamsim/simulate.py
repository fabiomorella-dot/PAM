"""Python equivalent of ``Do_PointSim`` in PAM's ``Sim.m``.

Prepares the kernel input exactly like Sim.m does (unit conversions, crosstalk
matrix, FRET rates, lifetimes in microtime bins, ...), runs all particles in
parallel threads (the numba kernel releases the GIL), and assembles the
photons per detection channel.
"""

from __future__ import annotations

import os
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, List, Union

import numpy as np

from ._kernel import EX_THRESHOLD, initial_position, simulate_particle
from ._rng import make_state
from .params import SimSettings, Species

MI_BINS = 2 ** 13            # Sim.m: MI_Bins = 2^13
MI_BINS_NOISE_BASIC = 4 * 2 ** 14 + 1  # Sim.m (basic mode with noise)
BACKGROUND_LABEL = 255
_LARGE_DIST = np.tril(np.full((4, 4), 10000.0), -1)  # Sim.m: "largeDist"


def _mround(x):
    """MATLAB round (half away from zero)."""
    return np.sign(x) * np.floor(np.abs(x) + 0.5)


# --------------------------------------------------------------------------
# result container
# --------------------------------------------------------------------------
@dataclass
class SimResult:
    #: photon macrotimes per channel in sampling ticks (float64, sorted)
    macrotimes: List[np.ndarray]
    #: photon microtimes per channel (uint16)
    microtimes: List[np.ndarray]
    #: per photon: laser<<6 | excited dye<<4 | emitting dye<<2 | channel;
    #: 255 marks background photons
    labels: List[np.ndarray]
    header: dict
    settings: SimSettings
    elapsed: float = 0.0
    mode: str = "basic"
    #: seed that was actually used (pass it as ``settings.seed`` to reproduce)
    seed: int = 0
    _kernel_info: dict = field(default_factory=dict, repr=False)

    @property
    def n_channels(self):
        return len(self.macrotimes)

    @property
    def freq_hz(self):
        return self.header["Freq"]

    def times_s(self, channel):
        """Macrotimes of one channel in seconds."""
        return self.macrotimes[channel] / self.freq_hz

    def count_rates_khz(self):
        t = self.header["Frames"] * self.header["FrameTime"] / self.freq_hz
        return [len(m) / t / 1e3 for m in self.macrotimes]

    def save_sim(self, path, irf=None, scatter=None):
        """Write a ``.sim`` file that PAM loads ("Pam Simulation Files").

        In advanced mode Sim.m also writes ``*_irf.sim`` (and ``*_scat.sim``
        when noise is on); ``irf``/``scatter`` default to doing the same.
        """
        from .io import save_sim
        return save_sim(self, path, irf=irf, scatter=scatter)

    def save_npz(self, path):
        from .io import save_npz
        return save_npz(self, path)


# --------------------------------------------------------------------------
# kernel input preparation
# --------------------------------------------------------------------------
def _crosstalk(sp: Species):
    cs = sp.Cross.copy()
    np.fill_diagonal(cs, 1.0)  # Sim.m: SimData.Species(i).Cross(1:5:16) = 1
    detp = sp.DetP
    with np.errstate(divide="ignore", invalid="ignore"):
        cross = np.diag(detp)[None, :] / detp * cs  # Cross(j,k) = DetP(k,k)/DetP(j,k)*Cross(j,k)
    return cross


def _cross_cdf(cross):
    """Kernel form of the crosstalk matrix: cdf[m, n] over channels n for dye m."""
    ct = cross.T
    with np.errstate(invalid="ignore", divide="ignore"):
        cum = np.cumsum(ct, axis=1)
        tot = cum[:, 3:4]
        use = (tot[:, 0] - 1.0) > 1e-5
        cdf = cum / tot
    cdf = np.where(np.isfinite(cdf), cdf, 1.0)
    return cdf, use


def _validate_map(settings, map_type, BS, frames):
    """Mirror of Sim.m's map checks; returns (map_type, maps[F, X, Y], dynamic)."""
    dummy = np.ones((1, 1, 1))
    if map_type == 1:
        return 1, dummy, False
    if map_type not in (2, 3, 4, 5, 6, 7, 8):
        return 1, dummy, False
    maps = settings.maps
    if maps is None:
        warnings.warn(f"map type {map_type} selected but no map given: using free diffusion")
        return 1, dummy, False
    maps = np.asarray(maps, dtype=float)
    if maps.ndim == 2:
        maps = maps[None]
    nx, ny = int(BS[0]), int(BS[1])
    if maps.shape[1] < nx or maps.shape[2] < ny:
        warnings.warn("map is smaller than the box: using free diffusion (as Sim.m)")
        return 1, dummy, False
    dynamic = map_type in (6, 7)
    if dynamic and maps.shape[0] < frames:
        warnings.warn("moving maps need one map per frame: using free diffusion (as Sim.m)")
        return 1, dummy, False
    maps = maps[: (frames if dynamic else 1), :nx, :ny].copy()
    maps[np.isnan(maps)] = 1.0
    return map_type, np.ascontiguousarray(maps), dynamic


def _focus_arrays(sp: Species):
    wr = np.zeros(4)
    wz = np.zeros(4)
    shift = np.zeros((4, 3))
    c = sp.color
    wr[:c] = sp.wr[:c]
    wz[:c] = sp.wz[:c]
    shift[:c, 0] = sp.dX[:c]
    shift[:c, 1] = sp.dY[:c]
    shift[:c, 2] = sp.dZ[:c]
    with np.errstate(divide="ignore"):
        inv_wr2 = np.where(wr > 0, 2.0 / wr ** 2, np.inf)
        inv_wz2 = np.where(wz > 0, 2.0 / wz ** 2, np.inf)
    return wr, wz, inv_wr2, inv_wz2, shift


def _build_basic(settings: SimSettings, sp: Species, mi_bins):
    freq_khz = settings.freq
    exp_ = sp.excitation_matrix(freq_khz)
    exp_[sp.color:, :] = 0.0
    if sp.fret == 2:
        with np.errstate(divide="ignore", invalid="ignore"):
            fret = (sp.R0 / sp.R) ** 6
        np.fill_diagonal(fret, 1.0)
    else:
        fret = np.eye(4)
    fret[sp.color:, :] = 0.0
    cross = _crosstalk(sp)
    cdf, use = _cross_cdf(cross)
    lt = sp.LT / settings.mi_range * mi_bins if sp.use_lt else np.zeros(4)
    return dict(
        sigma_d=np.array([np.sqrt(2 * sp.D * 1e6 / (freq_khz * 1e3))]),
        exp_=exp_.T[None].copy(), rates0=fret.T[None].copy(), detp=sp.DetP.T[None].copy(),
        blp=sp.BlP.T[None].copy(), cross_cdf=cdf[None].copy(), cross_use=use[None].copy(),
        lt=np.asarray(lt, float)[None].copy(),
        mode=0, irf_mean=0.0, irf_sd=0.0, use_aniso=False, p_aniso=np.zeros((1, 1, 1)),
        dist=np.zeros((1, 4, 4)), sigma_dist=np.zeros((1, 4, 4)), r0=np.zeros((1, 4, 4)),
        linker=0.0, het_step=0, dyn_cdf=np.ones((1, 1)), dyn_step=0,
    )


def _build_advanced(settings: SimSettings, mi_bins):
    sps = settings.species
    S = len(sps)
    freq_khz = settings.freq
    freq_hz = freq_khz * 1e3
    exp_ = np.zeros((S, 4, 4)); detp = np.zeros((S, 4, 4)); blp = np.zeros((S, 4, 4))
    cdf = np.zeros((S, 4, 4)); use = np.zeros((S, 4), bool); lt = np.zeros((S, 4))
    dist = np.zeros((S, 4, 4)); sig = np.zeros((S, 4, 4)); r0 = np.zeros((S, 4, 4))
    rates0 = np.zeros((S, 4, 4))
    any_lt = any(s.use_lt for s in sps) or settings.use_aniso
    for i, sp in enumerate(sps):
        e = sp.excitation_matrix(freq_khz)
        e[sp.color:, :] = 0.0
        exp_[i] = e.T
        detp[i] = sp.DetP.T
        blp[i] = sp.BlP.T
        c, u = _cross_cdf(_crosstalk(sp))
        cdf[i] = c; use[i] = u
        if any_lt:
            lt[i] = sp.LT / settings.mi_range * mi_bins
        d = _LARGE_DIST if sp.fret == 1 else sp.R
        rr0 = sp.R0.copy()
        rr0[sp.color:, :] = 0.0
        with np.errstate(divide="ignore", invalid="ignore"):
            rates = np.where(rr0 > 0, (rr0 / d) ** 6, 0.0)
        np.fill_diagonal(rates, 1.0)
        dist[i] = d.T; sig[i] = sp.distance_width.T; r0[i] = rr0.T; rates0[i] = rates.T

    # anisotropy: probability of a photon to be detected in the parallel channel
    p_aniso = np.zeros((1, 1, 1))
    if settings.use_aniso:
        t = np.arange(1, mi_bins + 1)
        p_aniso = np.zeros((S, 4, mi_bins))
        for i, sp in enumerate(sps):
            for c in range(4):
                a0, rho, rinf = sp.aniso[c, 0], sp.aniso[c, 1] / settings.mi_range * mi_bins, sp.aniso[c, 2]
                with np.errstate(divide="ignore"):
                    r = (a0 - rinf) * np.exp(-t / rho) + rinf
                p_aniso[i, c] = (2 * r + 1) / 3

    # dynamics
    dyn_step = 0
    dyn_cdf = np.ones((S, S))
    if any(s.fret == 3 for s in sps):
        rates = np.zeros((S, S)) if settings.dynamic_rates is None else np.array(settings.dynamic_rates, float)
        rates = rates.reshape(S, S).copy()
        np.fill_diagonal(rates, 0.0)
        if np.any(rates != 0):
            rates = rates * 1e3 / freq_hz
            dyn_step = int(_mround(0.1 / rates.max()))
            p = rates * dyn_step
            p[np.isnan(p)] = 0
            for i in range(S):
                p[i, i] = 1 - p[i].sum()  # diagonal is zero at this point
            dyn_cdf = np.cumsum(p, axis=1)

    irf_mean = 4 * mi_bins / settings.mi_range * settings.irf_width / 1000
    irf_sd = mi_bins * settings.irf_width / 1000 / settings.mi_range if settings.use_irf else 1.0
    het_step = int(settings.heterogeneity_update * 1e-3 * freq_hz) if settings.use_fret_width else 0
    return dict(
        sigma_d=np.array([np.sqrt(2 * s.D * 1e6 / freq_hz) for s in sps]),
        exp_=exp_, rates0=rates0, detp=detp, blp=blp, cross_cdf=cdf, cross_use=use, lt=lt,
        mode=1, irf_mean=irf_mean, irf_sd=irf_sd, use_aniso=bool(settings.use_aniso), p_aniso=p_aniso,
        dist=dist, sigma_dist=sig, r0=r0,
        linker=float(settings.linker_width) if settings.use_linker_width else 0.0,
        het_step=het_step, dyn_cdf=dyn_cdf, dyn_step=dyn_step,
    )


def _geometry(settings: SimSettings, sp_focus: Species, phys: dict, map_type, maps, BS):
    """Focus arrays, per-state cut-offs and fast-forward slabs."""
    wr, wz, inv_wr2, inv_wz2, shift = _focus_arrays(sp_focus)
    exp_ = phys["exp_"]
    qmax = float(np.max(maps)) if map_type == 2 else 1.0
    S = exp_.shape[0]
    laser_on = (wr > 0) & (wz > 0) & np.any(exp_ > 0, axis=(0, 2))
    lmax = np.full((S, 4), -np.inf)
    for s in range(S):
        for j in range(4):
            m = exp_[s, j].max() * qmax
            if laser_on[j] and m > 0:
                lmax[s, j] = np.log(m / EX_THRESHOLD)

    step = settings.pixel_size.astype(float)
    pixel = settings.pixels.astype(float)
    x0 = -pixel[0] * step[0] / 2
    y0 = -pixel[1] * step[1] / 2
    fx = (0.0, 0.0); fy = (0.0, 0.0)
    if settings.scan_type == 2:
        fx = (x0, x0 + pixel[0] * step[0]); fy = (y0, y0 + pixel[1] * step[1])
    elif settings.scan_type == 3:
        fx = (x0, x0 + pixel[0] * step[0])

    slab_lo = np.zeros((4, 3)); slab_hi = np.zeros((4, 3))
    laser_ff = np.zeros(4, bool)
    hb = BS / 2
    for j in range(4):
        L = lmax[:, j].max()
        if not (laser_on[j] and L > 0):
            continue
        hx = np.sqrt(L / inv_wr2[j]); hz = np.sqrt(L / inv_wz2[j])
        slab_lo[j, 0] = hb[0] - shift[j, 0] + fx[0] - hx; slab_hi[j, 0] = hb[0] - shift[j, 0] + fx[1] + hx
        slab_lo[j, 1] = hb[1] - shift[j, 1] + fy[0] - hx; slab_hi[j, 1] = hb[1] - shift[j, 1] + fy[1] + hx
        slab_lo[j, 2] = hb[2] - shift[j, 2] - hz; slab_hi[j, 2] = hb[2] - shift[j, 2] + hz
        if BS[2] <= 0 and abs(shift[j, 2]) >= hz:
            continue  # 2D: this laser can never excite anything
        laser_ff[j] = True
    return dict(inv_wr2=inv_wr2, inv_wz2=inv_wz2, shift=shift, laser_on=laser_on, lmax=lmax,
                slab_lo=slab_lo, slab_hi=slab_hi, laser_ff=laser_ff)


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------
def simulate(settings: SimSettings, progress: Union[bool, Callable[[int, int], None]] = False) -> SimResult:
    """Run a point / line / raster simulation (Sim.m scan types 1-4)."""
    if settings.scan_type == 5:
        raise NotImplementedError("camera simulations (scan type 5) are not ported")
    t_start = time.perf_counter()
    BS = np.floor(settings.box_size).astype(float)
    freq_hz = settings.freq * 1e3
    simtime = int(_mround(settings.sim_time * freq_hz))
    frames = int(settings.frames)
    frame_ticks = int(_mround(simtime / frames))
    step = settings.pixel_size.astype(float)
    pixel = settings.pixels.astype(float)
    scan_ticks = np.array([settings.times[0] * freq_hz * 1e-6, settings.times[1] * freq_hz * 1e-3])
    seed = int(settings.seed) if settings.seed is not None else int(np.random.SeedSequence().entropy)
    advanced = settings.advanced
    mi_bins = MI_BINS

    # one "job" per kernel configuration: basic -> one per species, advanced -> one
    jobs = []
    if not advanced:
        for i, sp in enumerate(settings.species):
            map_type, maps, dyn_maps = _validate_map(settings, sp.barrier, BS, frames)
            phys = _build_basic(settings, sp, mi_bins)
            geo = _geometry(settings, sp, phys, map_type, maps, BS)
            jobs.append((phys, geo, map_type, maps, dyn_maps, [(i, i, j, 0) for j in range(sp.N)]))
    else:
        map_type, maps, dyn_maps = _validate_map(settings, settings.species[0].barrier, BS, frames)
        phys = _build_advanced(settings, mi_bins)
        geo = _geometry(settings, settings.species[0], phys, map_type, maps, BS)
        parts = []
        for i, sp in enumerate(settings.species):
            parts += [(i, i, j, i) for j in range(sp.N)]
        jobs.append((phys, geo, map_type, maps, dyn_maps, parts))

    tasks = []
    for phys, geo, map_type, maps, dyn_maps, parts in jobs:
        ff = bool(settings.fast_forward and map_type in (1, 2))
        for (species_idx, _, particle_idx, state0) in parts:
            tasks.append((phys, geo, map_type, maps, dyn_maps, ff, species_idx, particle_idx, state0))

    def run(task):
        phys, geo, map_type, maps, dyn_maps, ff, species_idx, particle_idx, state0 = task
        rng = make_state(np.random.SeedSequence(seed, spawn_key=(species_idx, particle_idx)))
        pos = initial_position(rng, BS, map_type, maps)
        return simulate_particle(
            rng, pos, state0, frames, frame_ticks, BS,
            int(settings.scan_type), step, pixel, scan_ticks,
            phys["sigma_d"],
            geo["inv_wr2"], geo["inv_wz2"], geo["shift"], geo["laser_on"], geo["lmax"],
            phys["exp_"], phys["rates0"], phys["detp"], phys["blp"], phys["cross_cdf"],
            phys["cross_use"], phys["lt"],
            phys["mode"], mi_bins, phys["irf_mean"], phys["irf_sd"], phys["use_aniso"], phys["p_aniso"],
            phys["dist"], phys["sigma_dist"], phys["r0"], phys["linker"], phys["het_step"],
            phys["dyn_cdf"], phys["dyn_step"],
            map_type, maps, dyn_maps,
            ff, float(settings.ff_z), geo["slab_lo"], geo["slab_hi"], geo["laser_ff"],
            bool(settings.reset_bleaching_each_frame), 4096)

    n_threads = settings.n_threads or os.cpu_count() or 1
    results = [None] * len(tasks)
    report = _progress_reporter(progress, len(tasks))
    if tasks:
        # numba compiles thread-safely: the first call compiles, the others wait
        with ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = {pool.submit(run, t): k for k, t in enumerate(tasks)}
            for done, fut in enumerate(as_completed(futures), start=1):
                results[futures[fut]] = fut.result()
                report(done)

    out = _assemble(settings, results, advanced, simtime, mi_bins, seed)
    elapsed = time.perf_counter() - t_start
    mt, mi, lab, mi_bins_header = out
    header = _header(settings, frames, frame_ticks, freq_hz, mi_bins_header, seed)
    return SimResult(macrotimes=mt, microtimes=mi, labels=lab, header=header, settings=settings,
                     elapsed=elapsed, mode="advanced" if advanced else "basic", seed=seed,
                     _kernel_info=dict(mi_bins=mi_bins, seed=seed, simtime=simtime,
                                       irf_mean=jobs[0][0]["irf_mean"] if jobs else 0.0,
                                       irf_sd=jobs[0][0]["irf_sd"] if jobs else 0.0))


def _progress_reporter(progress, total):
    if callable(progress):
        return lambda done: progress(done, total)
    if not progress:
        return lambda done: None
    t0 = time.perf_counter()

    def rep(done):
        if done == total or done % max(1, total // 50) == 0:
            sys.stderr.write(f"\rsimulating particles: {done}/{total}  ({time.perf_counter() - t0:.1f} s)")
            if done == total:
                sys.stderr.write("\n")
            sys.stderr.flush()
    return rep


def _assemble(settings, results, advanced, simtime, mi_bins, seed):
    if results:
        mt = np.concatenate([r[0] for r in results])
        mi = np.concatenate([r[1] for r in results])
        lab = np.concatenate([r[2] for r in results])
        pol = np.concatenate([r[3] for r in results])
    else:
        mt = np.zeros(0, np.int64); mi = np.zeros(0, np.uint16)
        lab = np.zeros(0, np.uint8); pol = np.zeros(0, np.uint8)
    det = lab & 3
    aniso = advanced and settings.use_aniso
    n_chan = 8 if aniso else 4
    rng = np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(2 ** 31,)))
    chan_mt, chan_mi, chan_lab = [], [], []
    for c in range(n_chan):
        sel = (det == (c % 4))
        if aniso:
            sel &= pol == (1 if c >= 4 else 0)
        m, i_, l_ = mt[sel].astype(np.float64), mi[sel], lab[sel]
        if aniso and c >= 4:  # Sim.m: discard half of the perpendicular photons
            keep = rng.random(m.size) < 0.5
            m, i_, l_ = m[keep], i_[keep], l_[keep]
        chan_mt.append(m); chan_mi.append(i_); chan_lab.append(l_)

    mi_bins_header = mi_bins
    if settings.use_noise:
        noise_bins = mi_bins
        if not advanced:
            noise_bins = mi_bins_header = MI_BINS_NOISE_BASIC
        for c in range(n_chan):
            ix = c % 4
            if settings.noise[ix] > 0 and chan_mt[ix].size > 0:
                rate = settings.noise[ix] * 1e3 / (settings.freq * 1e3)  # photons per tick
                n = rng.poisson(rate * simtime)
                t = np.sort(rng.random(n) * simtime)
                nmi = np.clip(_mround(noise_bins * rng.random(n)), 0, 65535).astype(np.uint16)
                chan_mt[c] = np.concatenate([chan_mt[c], t])
                chan_mi[c] = np.concatenate([chan_mi[c], nmi])
                chan_lab[c] = np.concatenate([chan_lab[c], np.full(n, BACKGROUND_LABEL, np.uint8)])

    for c in range(n_chan):
        order = np.argsort(chan_mt[c], kind="stable")
        chan_mt[c] = chan_mt[c][order]
        chan_mi[c] = chan_mi[c][order]
        chan_lab[c] = chan_lab[c][order]
    return chan_mt, chan_mi, chan_lab, mi_bins_header


def _header(settings, frames, frame_ticks, freq_hz, mi_bins, seed):
    from .io import general_struct, species_struct
    return {
        "Frames": float(frames),
        "FrameTime": float(frame_ticks),
        "Pixels": float(settings.pixels[0]),
        "Lines": float(settings.pixels[1]),
        "Freq": float(freq_hz),
        "MI_Bins": float(mi_bins),
        "Info": {"General": general_struct(settings, seed), "Species": [species_struct(s) for s in settings.species]},
    }
