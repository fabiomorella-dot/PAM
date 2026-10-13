"""Port of PAM's ``CrossCorrelation.m`` and the ``Do_CCF.c`` MEX file.

``cross_correlation`` takes the same arguments as the MATLAB function and
returns the same arrays.  ``correlate_blocks`` additionally does what PAM's
*Correlate* tab does for point data: split the photon stream into time
sections, correlate every section and return mean and standard error.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from numba import njit

TIME_BINS_SIZE = 10  # CrossCorrelation.m: Time_Bins_Size


# --------------------------------------------------------------------------
# Do_CCF.c
# --------------------------------------------------------------------------
@njit(cache=True, nogil=True)
def _correlate_block(t1, w1, n1, t2, w2, n2, number_per_block, minimal_offset, corr, base):
    p2_min = 0
    for p1 in range(n1):
        lower = minimal_offset + t1[p1]
        upper = lower + number_per_block
        start = p2_min
        for p2 in range(start, n2):
            if t2[p2] >= upper:
                break
            if t2[p2] >= lower:
                corr[base + t2[p2] - lower] += w1[p1] * w2[p2]
            else:
                p2_min += 1


@njit(cache=True, nogil=True)
def _bin_neighbors(t, w, n):
    for i in range(n):
        t[i] //= 2
    for i in range(1, n):
        if t[i] == t[i - 1]:
            w[i] += w[i - 1]
            w[i - 1] = 0.0


@njit(cache=True, nogil=True)
def _prune_zeros(t, w, n):
    k = 0
    for i in range(n):
        if w[i] == 0.0:
            continue
        w[k] = w[i]
        t[k] = t[i]
        k += 1
    return k


@njit(cache=True, nogil=True)
def do_ccf(macrotimes_1, macrotimes_2, weights_1, weights_2, block_size, number_of_blocks):
    """``fast_MT`` from Do_CCF.c; returns the raw (unnormalised) correlation
    of length ``1 + number_of_blocks * block_size``.  Inputs are not modified."""
    corr = np.zeros(1 + number_of_blocks * block_size)
    if number_of_blocks == 0:
        return corr
    t1 = macrotimes_1.copy(); t2 = macrotimes_2.copy()
    w1 = weights_1.copy(); w2 = weights_2.copy()
    n1 = t1.shape[0]; n2 = t2.shape[0]
    _correlate_block(t1, w1, n1, t2, w2, n2, block_size + 1, 0, corr, 0)
    base = 1
    binning_factor = 1
    for _ in range(1, number_of_blocks):
        base += block_size
        _correlate_block(t1, w1, n1, t2, w2, n2, block_size, block_size + 1, corr, base)
        for i in range(block_size):
            corr[base + i] /= binning_factor
        binning_factor *= 2
        _bin_neighbors(t1, w1, n1)
        _bin_neighbors(t2, w2, n2)
        n1 = _prune_zeros(t1, w1, n1)
        n2 = _prune_zeros(t2, w2, n2)
    return corr


# --------------------------------------------------------------------------
# CrossCorrelation.m
# --------------------------------------------------------------------------
def _mround(x):
    x = np.asarray(x, dtype=float)
    return np.sign(x) * np.floor(np.abs(x) + 0.5)


def time_axis(maxtime, mode=1):
    """Pseudo-logarithmic lag axis [0, 1..20, 22:2:40, 44:4:80, ...] (incl. 0)."""
    if mode == 1:
        exponent = int(math.floor(math.log2(maxtime / TIME_BINS_SIZE)) + 1)
    else:
        exponent = int(math.ceil(math.log2(float(np.max(maxtime)))))
    exponent = max(exponent, 0)
    size = TIME_BINS_SIZE * exponent
    k = np.arange(size)
    t = 2.0 ** np.floor(k / TIME_BINS_SIZE - 1)
    t[t < 1] = 1
    return np.concatenate([[0.0], np.cumsum(t)]), exponent


def _raw_ccf(d1, d2, w1, w2, exponent):
    return do_ccf(_mround(d1).astype(np.int64), _mround(d2).astype(np.int64),
                  np.asarray(w1, np.float64), np.asarray(w2, np.float64), TIME_BINS_SIZE, exponent)


def _countrates(d1, d2, w1, w2, maxtime, timeaxis):
    """Weights of photons that have a partner at each lag (Countrate1/2 in the .m file)."""
    d1 = np.asarray(d1, float); d2 = np.asarray(d2, float)
    c1 = np.cumsum(w1)
    c2 = np.concatenate([[0.0], np.cumsum(w2)])
    stop = np.searchsorted(d1, maxtime - timeaxis, side="right")    # count of d1 <= maxtime - tau
    start = np.searchsorted(d2, timeaxis, side="left")              # first index with d2 >= tau
    cr1 = np.where(stop > 0, c1[np.maximum(stop - 1, 0)] if c1.size else 0.0, 0.0)
    cr2 = np.where(start < d2.size, c2[-1] - c2[np.minimum(start, d2.size)], 0.0)
    return cr1, cr2


def cross_correlation(data1, data2, maxtime, weights1=None, weights2=None, mode=1,
                      n_threads=None, rng=None):
    """Python version of ``[Cor_Array, Timeaxis] = CrossCorrelation(...)``.

    Parameters are the same as in MATLAB: ``data1``/``data2`` are lists of
    sorted photon macrotime arrays (one entry per block, or per burst for
    mode 2/3), ``maxtime`` is the block length (mode 1) or an array of burst
    durations (mode 2/3).  All times in macrotime ticks.

    Returns ``(cor_array, timeaxis)``:
    mode 1 -> array (n_lags, n_blocks); mode 2 -> (n_lags, 50) bootstrap
    samples; mode 3 -> list with one curve per burst.
    """
    if isinstance(data1, np.ndarray) and data1.dtype != object:
        data1 = [data1]
    if isinstance(data2, np.ndarray) and data2.dtype != object:
        data2 = [data2]
    n = len(data1)
    if weights1 is None or len(weights1) == 0:
        weights1 = [np.ones(len(d)) for d in data1]
        weights2 = [np.ones(len(d)) for d in data2]
    maxtime = np.asarray(maxtime, dtype=float)
    timeaxis, exponent = time_axis(float(maxtime) if mode == 1 else maxtime, mode)

    def one(i):
        if len(data1[i]) and len(data2[i]):
            return _raw_ccf(data1[i], data2[i], weights1[i], weights2[i], exponent)
        return np.zeros(0)

    workers = n_threads or os.cpu_count() or 1
    if n > 1 and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            cor = list(pool.map(one, range(n)))
    else:
        cor = [one(i) for i in range(n)]

    # remove the zero-delay correlation for backwards compatibility
    timeaxis = timeaxis[1:]
    cor = [c[1:] for c in cor]

    if mode == 1:
        norm = maxtime - timeaxis
        if np.all(norm < 0):  # same (vector) condition as the .m file
            norm = 0
        out = []
        for i in range(n):
            if cor[i].size == 0:
                out.append(cor[i])
                continue
            cr1, cr2 = _countrates(data1[i], data2[i], weights1[i], weights2[i], maxtime, timeaxis)
            with np.errstate(divide="ignore", invalid="ignore"):
                out.append(cor[i] / norm / (cr1 / (maxtime - timeaxis)) / (cr2 / (maxtime - timeaxis)) - 1)
        length = max(c.size for c in out)
        arr = np.zeros((length, n))
        for i, c in enumerate(out):
            arr[:c.size, i] = c
        return arr, timeaxis[:length]

    # burstwise modes 2 and 3
    norms, cr1s, cr2s = [], [], []
    for i in range(n):
        nm = maxtime[i] - timeaxis + 1
        nm[nm < 0] = 0
        c1, c2 = _countrates(data1[i], data2[i], weights1[i], weights2[i], maxtime[i], timeaxis)
        norms.append(nm); cr1s.append(c1); cr2s.append(c2)
    cor = [c if c.size else np.zeros(timeaxis.size) for c in cor]
    if mode == 3:
        with np.errstate(divide="ignore", invalid="ignore"):
            return [c * nm / a / b - 1 for c, nm, a, b in zip(cor, norms, cr1s, cr2s)], timeaxis
    rng = rng or np.random.default_rng()
    bootstrap = 50
    selected = rng.integers(0, n, size=(n, bootstrap))
    res = np.zeros((timeaxis.size, bootstrap))
    norms = np.array(norms); cr1s = np.array(cr1s); cr2s = np.array(cr2s); cor = np.array(cor)
    for b in range(bootstrap):
        sel = selected[:, b]
        with np.errstate(divide="ignore", invalid="ignore"):
            r = cor[sel].sum(0) * norms[sel].sum(0) / cr1s[sel].sum(0) / cr2s[sel].sum(0) - 1
        r[~np.isfinite(r)] = -1
        last = np.nonzero(r != -1)[0]
        r[(last[-1] + 1 if last.size else 0):] = 0
        res[:, b] = r
    nz = np.nonzero(res.sum(1))[0]
    keep = nz[-1] + 1 if nz.size else 0
    return res[:keep], timeaxis[:keep]


def correlate_blocks(mt1, mt2, total_time, n_blocks=10, divider=1, weights1=None, weights2=None):
    """Correlate two photon streams like PAM's *Correlate* tab.

    ``mt1``/``mt2`` are sorted macrotimes (ticks), ``total_time`` the
    measurement length in ticks.  The data is cut into ``n_blocks`` sections
    of equal length, each section is correlated, and the mean curve and its
    standard error of the mean are returned together with the lag times in
    ticks: ``(lags, mean, sem, curves)``.
    """
    edges = np.ceil(np.linspace(0, total_time, n_blocks + 1))
    maxtime = np.ceil(np.max(np.diff(edges))) / divider
    d1, d2, ww1, ww2 = [], [], [], []
    mt1 = np.asarray(mt1, float); mt2 = np.asarray(mt2, float)
    for j in range(n_blocks):
        s1 = (mt1 >= edges[j]) & (mt1 < edges[j + 1])
        s2 = (mt2 >= edges[j]) & (mt2 < edges[j + 1])
        d1.append(np.floor((mt1[s1] - edges[j]) / divider))
        d2.append(np.floor((mt2[s2] - edges[j]) / divider))
        if weights1 is not None:
            ww1.append(np.asarray(weights1)[s1]); ww2.append(np.asarray(weights2)[s2])
    valid = [k for k in range(n_blocks) if len(d1[k]) and len(d2[k])]
    d1 = [d1[k] for k in valid]; d2 = [d2[k] for k in valid]
    if weights1 is not None:
        ww1 = [ww1[k] for k in valid]; ww2 = [ww2[k] for k in valid]
    curves, lags = cross_correlation(d1, d2, maxtime, ww1 or None, ww2 or None)
    mean = curves.mean(axis=1)
    sem = curves.std(axis=1, ddof=1) / np.sqrt(curves.shape[1]) if curves.shape[1] > 1 else np.zeros_like(mean)
    return lags * divider, mean, sem, curves
