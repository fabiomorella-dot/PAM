"""Reference implementation built from PAM's ORIGINAL code, for validation.

* ``build()`` compiles the unmodified ``DifSim_mac.cpp`` / ``DifSim_ani_mac.cpp``
  (repository root) against a tiny MEX stand-in (``mex_shim/``) and
  ``Do_CCF.c`` as shared libraries.
* ``ref_simulate()`` re-creates the ``Do_PointSim`` loop of Sim.m around these
  kernels: one kernel call per particle and frame, inputs built directly
  from the Sim.m source (MATLAB column-major order) - independently of
  pamsim's own conversion code.  Only deviation: every (particle, frame)
  call gets its own seed (Sim.m uses ``seed+k+j``, which repeats streams).
* ``ref_do_ccf()`` calls ``fast_MT`` from Do_CCF.c, ``matlab_cross_correlation``
  is a literal transcription of CrossCorrelation.m (mode 1).
"""
import ctypes
import os
import subprocess

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
BUILD = os.path.join(HERE, "build")
_WRAPPER = """#include "mex.h"
#include "{src}"
extern "C" int ref_call(int nrhs, double **in_data, int64_t *in_n, int nlhs, void **out_data, int64_t *out_n) {{
    mxArray ins[64]; const mxArray *prhs[64]; mxArray *plhs[8] = {{0}};
    for (int i = 0; i < nrhs; i++) {{ ins[i].data = in_data[i]; ins[i].n = in_n[i]; prhs[i] = &ins[i]; }}
    mexFunction(nlhs, plhs, nrhs, prhs);
    for (int i = 0; i < nlhs; i++) {{ out_data[i] = plhs[i]->data; out_n[i] = plhs[i]->n; delete plhs[i]; }}
    return 0;
}}
extern "C" void ref_free(void *p) {{ free(p); }}
"""


def build(force=False):
    """Compile the original kernels; returns the build directory."""
    os.makedirs(BUILD, exist_ok=True)
    for name, src in (("DifSim", "DifSim_mac.cpp"), ("DifSim_ani", "DifSim_ani_mac.cpp")):
        lib = os.path.join(BUILD, f"lib{name}.so")
        if os.path.exists(lib) and not force:
            continue
        wrapper = os.path.join(BUILD, f"{name}_ref.cpp")
        with open(wrapper, "w") as f:
            f.write(_WRAPPER.format(src=src))
        subprocess.run(["g++", "-O2", "-DNDEBUG", "-shared", "-fPIC", "-w",
                        "-I" + os.path.join(HERE, "mex_shim"), "-I" + REPO, "-o", lib, wrapper], check=True)
    lib = os.path.join(BUILD, "libdoccf.so")
    if force or not os.path.exists(lib):
        subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-o", lib, os.path.join(REPO, "Do_CCF.c")], check=True)
    return BUILD


_libs = {}


def _lib(name):
    if name not in _libs:
        build()
        lib = ctypes.CDLL(os.path.join(BUILD, f"lib{name}.so"))
        if name == "doccf":
            P = ctypes.POINTER
            lib.fast_MT.argtypes = [P(ctypes.c_uint64), P(ctypes.c_uint64), P(ctypes.c_double),
                                    P(ctypes.c_double), ctypes.c_uint64, ctypes.c_uint64,
                                    ctypes.c_uint64, ctypes.c_uint64, P(ctypes.c_double)]
        else:
            lib.ref_free.argtypes = [ctypes.c_void_p]
        _libs[name] = lib
    return _libs[name]


def call_mex(name, args, nlhs, out_types):
    lib = _lib(name)
    arrs = [np.ascontiguousarray(np.asarray(a, dtype=np.float64).ravel(order="F")) for a in args]
    n = len(arrs)
    in_ptrs = (ctypes.c_void_p * n)(*[a.ctypes.data for a in arrs])
    in_n = (ctypes.c_int64 * n)(*[a.size for a in arrs])
    out_ptrs = (ctypes.c_void_p * nlhs)()
    out_n = (ctypes.c_int64 * nlhs)()
    lib.ref_call(n, in_ptrs, in_n, nlhs, out_ptrs, out_n)
    outs = []
    for i in range(nlhs):
        dt = np.dtype(out_types[i])
        cnt = out_n[i]
        if cnt:
            buf = (ctypes.c_char * (cnt * dt.itemsize)).from_address(out_ptrs[i])
            outs.append(np.frombuffer(bytes(buf), dtype=dt).copy())
        else:
            outs.append(np.zeros(0, dt))
        lib.ref_free(out_ptrs[i])
    return outs


def _cross(sp):
    DetP = sp.DetP
    Cs = sp.Cross.copy()
    np.fill_diagonal(Cs, 1)
    Cross = np.zeros((4, 4))
    with np.errstate(divide="ignore", invalid="ignore"):
        for j in range(4):
            for k in range(4):
                Cross[j, k] = DetP[k, k] / DetP[j, k] * Cs[j, k]
    return Cross


def _focus(sp):
    wr = np.zeros(4); wz = np.zeros(4); dX = np.zeros(4); dY = np.zeros(4); dZ = np.zeros(4)
    c = sp.color
    wr[:c] = sp.wr[:c]; wz[:c] = sp.wz[:c]; dX[:c] = sp.dX[:c]; dY[:c] = sp.dY[:c]; dZ[:c] = sp.dZ[:c]
    return wr, wz, dX, dY, dZ


def ref_simulate(s, seed=1, maps=None):
    """Simulate with the original kernels.  Returns raw (macrotimes, microtimes,
    channel bits, polarization) of all photons (unsorted, like Sim.m)."""
    BS = np.floor(np.asarray(s.box_size, float))
    Freq = s.freq * 1000
    Simtime = np.round(s.sim_time * Freq)
    Frames = s.frames
    Frametime = np.round(Simtime / Frames)
    Step = np.array([s.pixel_size[0], s.pixel_size[1]], float)
    Pixel = np.array([s.pixels[0], s.pixels[1]], float)
    ScanTicks = np.array([s.times[0] * Freq * 1e-6, s.times[1] * Freq * 1e-3])
    rng = np.random.default_rng(seed)
    MI_Bins = 2 ** 13
    Map = np.ones((1, 1)) if maps is None else np.asarray(maps, float)
    kseed = seed * 100003
    out = []
    if not s.advanced:
        for sp in s.species:
            D = np.sqrt(2 * sp.D * 1e6 / Freq)
            ExP = sp.excitation_matrix(s.freq)
            if sp.fret == 2:
                with np.errstate(divide="ignore", invalid="ignore"):
                    FRET = (sp.R0 / sp.R) ** 6
                np.fill_diagonal(FRET, 1)
            else:
                FRET = np.eye(4)
            LT = sp.LT / s.mi_range * MI_Bins if sp.use_lt else np.zeros(4)
            ExP[sp.color:, :] = 0
            FRET[sp.color:, :] = 0
            wr, wz, dX, dY, dZ = _focus(sp)
            for j in range(sp.N):
                Pos = (BS - 1) * rng.random(3)
                if sp.barrier == 3:
                    while Map[int(np.floor(Pos[0])), int(np.floor(Pos[1]))] == 0:
                        Pos = (BS - 1) * rng.random(3)
                for k in range(Frames):
                    kseed += 1
                    ph, mi, ch, Pos = call_mex("DifSim", [
                        Frametime, BS, s.scan_type, Step, Pixel, ScanTicks, D, Pos,
                        wr, wz, dX, dY, dZ, ExP, sp.DetP, sp.BlP, LT, FRET, _cross(sp),
                        kseed % 2 ** 32, sp.barrier, Map], 4, ["f8", "u2", "u1", "f8"])
                    out.append((ph + k * Frametime, mi, ch, np.zeros(ph.size, np.uint8)))
    else:
        sps = s.species
        S = len(sps)
        IRFshift = 4 * MI_Bins / s.mi_range * s.irf_width / 1000
        IRFwidth = MI_Bins * s.irf_width / 1000 / s.mi_range if s.use_irf else 1
        wr, wz, dX, dY, dZ = _focus(sps[0])
        ExP_lin = np.concatenate([np.where(np.arange(4)[:, None] < sp.color, sp.excitation_matrix(s.freq), 0).ravel("F")
                                  for sp in sps])
        DetP_lin = np.concatenate([sp.DetP.ravel("F") for sp in sps])
        Cross_lin = np.concatenate([_cross(sp).ravel("F") for sp in sps])
        BlP_lin = np.concatenate([sp.BlP.ravel("F") for sp in sps])
        het = s.heterogeneity_update * 1e-3 * Freq if s.use_fret_width else 0
        linker = s.linker_width if s.use_linker_width else 0
        anyLT = any(sp.use_lt for sp in sps)
        D = np.array([np.sqrt(2 * sp.D * 1e6 / Freq) for sp in sps])
        LT = np.concatenate([sp.LT / s.mi_range * MI_Bins if (anyLT or s.use_aniso) else np.zeros(4) for sp in sps])
        large = np.array([[0, 0, 0, 0], [1e4, 0, 0, 0], [1e4, 1e4, 0, 0], [1e4, 1e4, 1e4, 0]])
        Dist = np.concatenate([(large if sp.fret == 1 else sp.R).ravel("F") for sp in sps])
        sigmaR = np.concatenate([sp.distance_width.ravel("F") for sp in sps])
        R0 = []
        for sp in sps:
            r0 = sp.R0.ravel("F").copy()
            for j in range(sp.color + 1, 5):
                for k in range(1, 5):
                    r0[(k - 1) * 4 + j - 1] = 0
            R0.append(r0)
        R0 = np.concatenate(R0)
        aniso = np.concatenate([sp.aniso.T.ravel("F") for sp in sps])
        aniso[1::4] = aniso[1::4] / s.mi_range * MI_Bins
        t = np.arange(1, MI_Bins + 1)
        p_aniso = []
        for i in range(S):
            for j in range(4):
                b = 16 * i + 4 * j
                with np.errstate(divide="ignore"):
                    r = (aniso[b] - aniso[b + 2]) * np.exp(-t / aniso[b + 1]) + aniso[b + 2]
                p_aniso.append((2 * r + 1) / 3)
        p_aniso = np.concatenate(p_aniso)
        pTrans = np.eye(S)
        DynamicStep = 0
        if any(sp.fret == 3 for sp in sps) and s.dynamic_rates is not None:
            DynRates = np.array(s.dynamic_rates, float).copy()
            np.fill_diagonal(DynRates, 0)
            if np.any(DynRates):
                DynRates = DynRates * 1e3 / Freq
                DynamicStep = np.round(0.1 / DynRates.max())
                pTrans = DynRates * DynamicStep
                for i in range(S):
                    pTrans[i, i] = 1 - pTrans[i].sum()
        p = pTrans.ravel("C")
        for i, sp in enumerate(sps):
            for j in range(sp.N):
                Pos = (BS - 1) * rng.random(3)
                state = i
                for k in range(Frames):
                    kseed += 1
                    ph, mi, ch, pol, Pos, st = call_mex("DifSim_ani", [
                        Frametime, BS, s.scan_type, Step, Pixel, ScanTicks, 1,
                        [IRFshift, IRFwidth], MI_Bins, D, Pos, wr, wz, dX, dY, dZ,
                        ExP_lin, DetP_lin, BlP_lin, LT, p_aniso, Dist, sigmaR, linker,
                        R0, het, Cross_lin, S, p, state, DynamicStep, kseed % 2 ** 32,
                        sps[0].barrier, Map], 6, ["f8", "u2", "u1", "u1", "f8", "u1"])
                    state = int(st[0])
                    out.append((ph + k * Frametime, mi, ch, pol))
    if not out:
        return np.zeros(0), np.zeros(0, np.uint16), np.zeros(0, np.uint8), np.zeros(0, np.uint8)
    return tuple(np.concatenate([o[i] for o in out]) for i in range(4))


def ref_do_ccf(t1, t2, w1, w2, block_size, n_blocks):
    """Call ``fast_MT`` from Do_CCF.c."""
    lib = _lib("doccf")
    P = ctypes.POINTER
    t1 = np.ascontiguousarray(t1, np.uint64).copy(); t2 = np.ascontiguousarray(t2, np.uint64).copy()
    w1 = np.ascontiguousarray(w1, np.float64).copy(); w2 = np.ascontiguousarray(w2, np.float64).copy()
    out = np.zeros(1 + n_blocks * block_size)
    lib.fast_MT(t1.ctypes.data_as(P(ctypes.c_uint64)), t2.ctypes.data_as(P(ctypes.c_uint64)),
                w1.ctypes.data_as(P(ctypes.c_double)), w2.ctypes.data_as(P(ctypes.c_double)),
                block_size, n_blocks, t1.size, t2.size, out.ctypes.data_as(P(ctypes.c_double)))
    return out


def matlab_cross_correlation(Data1, Data2, Maxtime):
    """Literal transcription of CrossCorrelation.m (mode 1, unit weights)."""
    Weights1 = [np.ones(len(d)) for d in Data1]
    Weights2 = [np.ones(len(d)) for d in Data2]
    Exp = int(np.floor(np.log2(Maxtime / 10)) + 1)
    Timeaxis = 2.0 ** np.floor((np.arange(1, 10 * Exp + 1) - 1) / 10 - 1)
    Timeaxis[Timeaxis < 1] = 1
    Timeaxis = np.cumsum(np.concatenate([[0], Timeaxis]))
    Cor = [ref_do_ccf(np.round(d1), np.round(d2), w1, w2, 10, Exp)
           for d1, d2, w1, w2 in zip(Data1, Data2, Weights1, Weights2)]
    Timeaxis = Timeaxis[1:]
    Cor = [c[1:] for c in Cor]
    Norm = Maxtime - Timeaxis
    out = []
    for i in range(len(Cor)):
        W1 = np.cumsum(Weights1[i]); W2 = np.concatenate([[0], np.cumsum(Weights2[i])])
        CR1 = np.zeros(Timeaxis.size); CR2 = np.zeros(Timeaxis.size)
        for j in range(Timeaxis.size):
            stop = np.nonzero(Data1[i] <= Maxtime - Timeaxis[j])[0]
            start = np.nonzero(Data2[i] >= Timeaxis[j])[0]
            CR1[j] = W1[stop[-1]] / (Maxtime - Timeaxis[j]) if stop.size else 0
            CR2[j] = (W2[-1] - W2[start[0]]) / (Maxtime - Timeaxis[j]) if start.size else 0
        with np.errstate(divide="ignore", invalid="ignore"):
            out.append(Cor[i] / Norm / CR1 / CR2 - 1)
    return np.array(out).T, Timeaxis
