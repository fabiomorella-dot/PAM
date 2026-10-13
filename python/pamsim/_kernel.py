"""Numba port of PAM's C++ simulation kernels (DifSim.cpp / DifSim_ani.cpp).

One kernel covers both MEX files:

* ``mode == 0`` reproduces ``DifSim`` (basic simulation, one species at a time),
* ``mode == 1`` reproduces ``DifSim_ani`` (IRF, anisotropy, FRET distance
  heterogeneity, linker fluctuations, dynamic interconversion between species).

Matrix layout follows the C++ code (``index = 16*state + 4*row + col``), i.e.
every 4x4 array passed in here is the *transpose* of the MATLAB matrix of the
same name (MATLAB is column-major).  ``simulate.py`` does that conversion.

The physics per sampling tick is unchanged.  What is new:

* All frames of one particle run in one call (the MATLAB code calls the MEX
  file once per frame and per particle and preallocates ``4*FrameTicks``
  photons for each call).
* Optional *fast-forward*: while a particle is provably far from every
  excitation volume (where the C++ code never generates photons because
  ``Ex <= 1e-4``), many diffusion steps are combined into one Gaussian jump.
  A sum of n Gaussian steps is exactly Gaussian with variance n*sigma^2, and
  n is chosen with the reflection principle such that the chance of entering
  the emission region during the jump is below 4*Q(ff_z) (~5e-12 for the
  default ff_z = 7).
"""

import math

import numpy as np
from numba import njit

from ._rng import geometric, normal, uniform

EX_THRESHOLD = 1e-4  # C++: "Only roll if Excitation is larger than 0.01%"
_MAX_U16 = 65535


@njit(cache=True)
def _grow(arr, n):
    out = np.empty(2 * arr.shape[0] + 16, dtype=arr.dtype)
    out[:n] = arr[:n]
    return out


@njit(cache=True, inline="always")
def _map_index(x, nx):
    i = int(math.floor(x))
    if i < 0:
        return 0
    if i >= nx:
        return nx - 1
    return i


@njit(cache=True)
def _map_value(maps, frame, x, y):
    return maps[frame, _map_index(x, maps.shape[1]), _map_index(y, maps.shape[2])]


@njit(cache=True)
def _move(rng, pos, new, box, sigma, map_type, maps, mframe, active, is3d):
    """One diffusion step including periodic boundaries and barrier maps."""
    while True:
        if map_type != 8:
            new[0] = pos[0] + sigma * normal(rng)
            new[1] = pos[1] + sigma * normal(rng)
        else:  # position dependent diffusion
            f = math.sqrt(_map_value(maps, mframe, pos[0], pos[1]))
            new[0] = pos[0] + f * sigma * normal(rng)
            new[1] = pos[1] + f * sigma * normal(rng)
        if is3d:
            new[2] = pos[2] + sigma * normal(rng)
        else:
            new[2] = 0.0

        # particle exits border: put it back on the other side and unbleach
        if (new[0] < 0.0 or new[0] > box[0] or new[1] < 0.0 or new[1] > box[1]
                or new[2] < 0.0 or new[2] > box[2]):
            for p in range(4):
                active[p] = True
            for a in range(3):
                if box[a] > 0.0:
                    new[a] = new[a] - box[a] * math.floor(new[a] / box[a])

        accept = True
        if map_type == 3 or map_type == 6 or map_type == 4 or map_type == 7:
            mnew = _map_value(maps, mframe, new[0], new[1])
            # restricted zones (3,6): accept if allowed, otherwise fall through
            # to the barrier rule exactly like the C++ switch statement does
            if not ((map_type == 3 or map_type == 6) and mnew != 0.0):
                mold = _map_value(maps, mframe, pos[0], pos[1])
                diff = mnew - mold
                prob = 1.0 if diff == 0.0 else uniform(rng)
                accept = prob >= abs(diff)
        elif map_type == 5:
            mnew = _map_value(maps, mframe, new[0], new[1])
            mold = _map_value(maps, mframe, pos[0], pos[1])
            diff = mnew - mold
            prob = 0.0 if diff == 0.0 else uniform(rng)
            if diff < 0.0:
                accept = prob >= abs(np.fmod(mnew, 1.0) - np.fmod(mold, 1.0))
            else:
                accept = prob >= (math.floor(mnew) - math.floor(mold)) / 10000.0
        if accept:
            pos[0] = new[0]
            pos[1] = new[1]
            pos[2] = new[2]
            return


@njit(cache=True)
def _torus_gap(p, lo, hi, b):
    """Distance from p to the interval [lo, hi] on a circle of length b."""
    width = hi - lo
    if width >= b:
        return 0.0
    d = p - lo
    d = d - b * math.floor(d / b)
    if d <= width:
        return 0.0
    return min(d - width, b - d)


@njit(cache=True)
def _safe_ticks(pos, sigma, box, is3d, slab_lo, slab_hi, laser_ff, ff_z, any_bleached):
    """Number of ticks the particle can certainly (up to 4*Q(ff_z)) spend dark."""
    big = 4.0e18
    if sigma <= 0.0:
        sigma = 1e-300
    best_n = big
    for j in range(4):
        if not laser_ff[j]:
            continue
        g = 0.0
        naxes = 3 if is3d else 2
        for a in range(naxes):
            ga = _torus_gap(pos[a], slab_lo[j, a], slab_hi[j, a], box[a])
            if ga > g:
                g = ga
        if g <= 0.0:
            return 0
        n = (g / (ff_z * sigma)) ** 2
        if n < best_n:
            best_n = n
    if any_bleached:
        # crossing the box border unbleaches; do not jump over a border
        w = big
        naxes = 3 if is3d else 2
        for a in range(naxes):
            wa = min(pos[a], box[a] - pos[a])
            if wa < w:
                w = wa
        n = (w / (ff_z * sigma)) ** 2
        if n < best_n:
            best_n = n
    if best_n >= big:
        return int(big)
    return int(best_n)


@njit(cache=True)
def _follow_moving_map(pos, maps, frame):
    """Sim.m (map types 6/7): if the zone under the particle changed between
    frames, move the particle to the nearest pixel carrying its old zone value."""
    old = _map_value(maps, frame - 1, pos[0], pos[1])
    if _map_value(maps, frame, pos[0], pos[1]) == old:
        return
    best = np.inf
    bx = -1
    by = -1
    for ix in range(maps.shape[1]):
        for iy in range(maps.shape[2]):
            if maps[frame, ix, iy] == old:
                d = (ix + 0.5 - pos[0]) ** 2 + (iy + 0.5 - pos[1]) ** 2
                if d < best:
                    best = d
                    bx = ix
                    by = iy
    if bx >= 0:
        pos[0] = bx + 0.5
        pos[1] = by + 0.5


@njit(cache=True)
def _redraw_distances(rng, R, rates, dist, sigma_dist, r0):
    S = dist.shape[0]
    for s in range(S):
        for a in range(4):
            for b in range(4):
                if sigma_dist[s, a, b] > 0.0:
                    R[s, a, b] = dist[s, a, b] + sigma_dist[s, a, b] * normal(rng)
                    rates[s, a, b] = (r0[s, a, b] / R[s, a, b]) ** 6


@njit(cache=True, nogil=True)
def simulate_particle(
        rng, pos, state,
        n_frames, frame_ticks, box,
        scan_type, step, pixel, scan_ticks,
        sigma_d,
        inv_wr2, inv_wz2, shift, laser_on, lmax,
        exp_, rates0, detp, blp, cross_cdf, cross_use, lt,
        mode, mi_bins, irf_mean, irf_sd, use_aniso, p_aniso,
        dist, sigma_dist, r0, linker, het_step,
        dyn_cdf, dyn_step,
        map_type, maps, dynamic_maps,
        fast_forward, ff_z, slab_lo, slab_hi, laser_ff,
        reset_bleach_each_frame, capacity):
    """Simulate one particle for ``n_frames * frame_ticks`` sampling ticks.

    Returns (macrotimes[int64 ticks], microtimes[uint16], label[uint8],
    polarization[uint8], final_state).  ``label`` packs
    laser<<6 | excited dye<<4 | emitting dye<<2 | detection channel,
    exactly as the C++ ``Channel`` output.
    """
    # private, padded copy of the RNG state: avoids false sharing of cache
    # lines between threads (the state is written several times per tick)
    st = np.zeros(16, dtype=np.uint64)
    st[:4] = rng[0][:4]
    rng = (st, np.zeros(16))

    S = exp_.shape[0]
    is3d = box[2] > 0.0
    hb0 = box[0] / 2.0
    hb1 = box[1] / 2.0
    hb2 = box[2] / 2.0
    x0 = -pixel[0] * step[0] / 2.0
    y0 = -pixel[1] * step[1] / 2.0

    mt = np.empty(capacity, dtype=np.int64)
    mi_out = np.empty(capacity, dtype=np.uint16)
    lab = np.empty(capacity, dtype=np.uint8)
    pol_out = np.empty(capacity, dtype=np.uint8)
    nph = 0

    active = np.ones(4, dtype=np.bool_)
    new = np.zeros(3)
    fret = np.zeros(4)
    R = dist.copy()
    rates = rates0.copy()
    dyn_on = dyn_step > 0 and S > 1
    het_on = het_step > 0
    quench = map_type == 2
    mi_offset_pie = mi_bins // 4

    for frame in range(n_frames):
        offset = frame * frame_ticks
        mframe = frame if dynamic_maps else 0
        if reset_bleach_each_frame:
            for p in range(4):
                active[p] = True
        if dynamic_maps and frame > 0:
            _follow_moving_map(pos, maps, frame)
        i = 0
        while i < frame_ticks:
            sigma = sigma_d[state]

            # ---------------------------------------------- fast-forward
            if fast_forward:
                any_bleached = not (active[0] and active[1] and active[2] and active[3])
                n = _safe_ticks(pos, sigma, box, is3d, slab_lo, slab_hi,
                                laser_ff, ff_z, any_bleached)
                if n >= 2:
                    rem = frame_ticks - i
                    if n > rem:
                        n = rem
                    if dyn_on:
                        next_dyn = ((i + dyn_step - 1) // dyn_step) * dyn_step
                        if n > next_dyn - i + 1:
                            n = next_dyn - i + 1
                if n >= 2:
                    last = i + n - 1
                    sj = sigma * math.sqrt(n)
                    new[0] = pos[0] + sj * normal(rng)
                    new[1] = pos[1] + sj * normal(rng)
                    new[2] = pos[2] + sj * normal(rng) if is3d else 0.0
                    if (new[0] < 0.0 or new[0] > box[0] or new[1] < 0.0 or new[1] > box[1]
                            or new[2] < 0.0 or new[2] > box[2]):
                        for p in range(4):
                            active[p] = True
                        for a in range(3):
                            if box[a] > 0.0:
                                new[a] = new[a] - box[a] * math.floor(new[a] / box[a])
                    pos[0] = new[0]
                    pos[1] = new[1]
                    pos[2] = new[2]
                    if dyn_on and last % dyn_step == 0:
                        u = uniform(rng)
                        s2 = 0
                        while s2 < S - 1 and not (u <= dyn_cdf[state, s2]):
                            s2 += 1
                        state = s2
                    if het_on and (i % het_step == 0 or last // het_step != i // het_step):
                        _redraw_distances(rng, R, rates, dist, sigma_dist, r0)
                    i = last + 1
                    continue

            # ---------------------------------------------- particle movement
            _move(rng, pos, new, box, sigma, map_type, maps, mframe, active, is3d)

            # ---------------------------------------------- focus movement
            fx = 0.0
            fy = 0.0
            if scan_type == 2:  # raster scan
                fx = np.fmod(i / scan_ticks[0], pixel[0]) * step[0] + x0
                fy = np.fmod(i / scan_ticks[1], pixel[1]) * step[1] + y0
            elif scan_type == 3:  # line scan
                fx = np.fmod(i / scan_ticks[0], pixel[0]) * step[0] + x0

            # ---------------------------------------------- dynamic step
            if dyn_on and i % dyn_step == 0:
                u = uniform(rng)
                s2 = 0
                while s2 < S - 1 and not (u <= dyn_cdf[state, s2]):
                    s2 += 1
                state = s2

            # ---------------------------------------------- heterogeneity step
            if het_on and i % het_step == 0:
                _redraw_distances(rng, R, rates, dist, sigma_dist, r0)

            # ---------------------------------------------- photon generation
            qv = 1.0
            if quench:
                qv = _map_value(maps, mframe, pos[0], pos[1])
            for j in range(4):  # laser (PIE)
                if not laser_on[j]:
                    continue
                dx = pos[0] - hb0 + shift[j, 0] - fx
                dy = pos[1] - hb1 + shift[j, 1] - fy
                dz = pos[2] - hb2 + shift[j, 2]
                arg = (dx * dx + dy * dy) * inv_wr2[j] + dz * dz * inv_wz2[j]
                if not (arg < lmax[state, j]):
                    continue  # Ex <= 1e-4 for every dye: C++ never rolls here
                gauss = math.exp(-arg)
                for k in range(4):  # excited dye (direct excitation)
                    e = exp_[state, j, k]
                    if not (active[k] and e > 0.0):
                        continue
                    ex = e * gauss * qv
                    if not (ex > EX_THRESHOLD):
                        continue
                    if not (uniform(rng) < ex):
                        continue

                    # ------------------------------ emitting dye (FRET)
                    if mode == 0:
                        mi = (j * 16384 + 1) & 0xFFFF
                    else:
                        mi = 0
                    m = k
                    while True:
                        for p in range(m, 4):
                            fret[p] = rates[state, m, p] if active[p] else 0.0
                        for p in range(m + 1, 4):
                            fret[p] += fret[p - 1]
                        if lt[state, m] > 0.0:
                            if mode == 1 and linker > 0.0:
                                for p in range(m, 4):
                                    if active[p]:
                                        if r0[state, m, p] > 0.0:
                                            rl = R[state, m, p] + linker * normal(rng)
                                            fret[p] = (r0[state, m, p] / rl) ** 6
                                        else:
                                            fret[p] = rates[state, m, p]
                                    else:
                                        fret[p] = 0.0
                                for p in range(m + 1, 4):
                                    fret[p] += fret[p - 1]
                            mi = (mi + geometric(rng, fret[3] / lt[state, m], _MAX_U16)) & 0xFFFF
                        if fret[3] - 1.0 > 1e-4:  # FRET is feasible
                            tot = fret[3]
                            u = uniform(rng)
                            p = m
                            while p < 3 and not (u <= fret[p] / tot):
                                p += 1
                            if p == m:
                                break  # no FRET occurred
                            m = p
                        else:
                            break

                    pol = 0
                    if mode == 1:
                        mi = mi % mi_bins
                        if use_aniso:
                            pol = 0 if uniform(rng) < p_aniso[state, m, mi] else 1
                        v = irf_mean + irf_sd * normal(rng) + 0.5
                        mi = (mi + (int(v) & 0xFFFF)) & 0xFFFF
                        mi = (mi + j * mi_offset_pie) & 0xFFFF
                        if mi < 1:
                            mi = 1
                        mi = mi % mi_bins

                    # ------------------------------ bleaching
                    bp = blp[state, k, m]
                    if bp > 0.0 and uniform(rng) < bp:
                        active[m] = False
                    if not active[m]:
                        continue

                    # ------------------------------ detection channel
                    if cross_use[state, m]:
                        u = uniform(rng)
                        n = 0
                        while n < 3 and not (u <= cross_cdf[state, m, n]):
                            n += 1
                    else:
                        n = m
                    d = detp[state, m, n]
                    if d > 1e-5 and uniform(rng) < d:
                        if nph >= mt.shape[0]:
                            mt = _grow(mt, nph)
                            mi_out = _grow(mi_out, nph)
                            lab = _grow(lab, nph)
                            pol_out = _grow(pol_out, nph)
                        mt[nph] = offset + i
                        mi_out[nph] = mi
                        lab[nph] = (j << 6) | (k << 4) | (m << 2) | n
                        pol_out[nph] = pol
                        nph += 1
            i += 1

    return mt[:nph].copy(), mi_out[:nph].copy(), lab[:nph].copy(), pol_out[:nph].copy(), state


@njit(cache=True, nogil=True)
def initial_position(rng, box, map_type, maps):
    """Uniform start position; restricted-zone maps (3, 6) reject forbidden pixels."""
    pos = np.zeros(3)
    while True:
        pos[0] = box[0] * uniform(rng)
        pos[1] = box[1] * uniform(rng)
        pos[2] = box[2] * uniform(rng) if box[2] > 0.0 else 0.0
        if map_type == 3 or map_type == 6:
            if _map_value(maps, 0, pos[0], pos[1]) == 0.0:
                continue
        return pos
