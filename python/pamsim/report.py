"""Plain-text summary of a simulation, written next to every simulated file.

PAMsim writes ``<name>_<k>_info.txt`` beside ``<name>_<k>.sim`` as soon as a
file is finished.  It lists the measurement settings (duration, microtime
range, background, FRET, crosstalk, direct excitation) and every species
(name, colours, D, concentration, brightness, lifetime).  From a script::

    r = simulate(settings)
    files = r.save_sim("my_sim_1.sim")
    r.save_info("my_sim_1_info.txt", files=files)

The text uses plain ASCII (um^2/s, ->) so that it reads the same in every
editor and in MATLAB (only species names are written as typed, UTF-8).
Every line is "Key: value".
"""

from __future__ import annotations

import datetime
import os

import numpy as np

WIDTH = 28          # column of the values
_LARGE_R = 1e4      # distances >= this mean "no FRET for this pair" (Sim.m: largeDist)
_FRET_NAMES = {2: "static", 3: "dynamic"}


def _g(v, digits=6):
    return f"{float(v):.{digits}g}"


def _line(key, value, indent=0):
    key = " " * indent + key + ":"
    return f"{key:<{WIDTH}} {value}".rstrip()


def species_brightness(sp, freq_khz):
    """Brightness per colour in kHz (Sim.m: Freq * ExP(i,i) * DetP(i,i) / sum(Cross(:,i)))."""
    if sp.brightness is not None:
        return np.asarray(sp.brightness, float)
    cross = np.array(sp.Cross, float)
    np.fill_diagonal(cross, 1.0)
    return np.array([freq_khz * sp.ExP[i, i] * sp.DetP[i, i] / cross[:, i].sum() for i in range(4)])


def dye_colours(sp, freq_khz):
    """0-based colours whose dye this species carries (brightness > 0 within its colours)."""
    b = species_brightness(sp, freq_khz)
    return [c for c in range(sp.color) if b[c] > 0]


def concentration_text(settings, sp):
    box = np.floor(np.asarray(settings.box_size, float))
    if box[2] > 0:
        return f"{_g(sp.N / np.prod(box) / 1e-24 / 6.022e23 / 1e-9, 4)} nM"
    return f"{_g(sp.N / (box[0] * box[1]) * 1e6, 4)} molecules/um^2 (2D)"


def fret_pairs(sp):
    """Active FRET pairs (donor, acceptor), 0-based: both dyes within the colours, R0 > 0 and a finite R."""
    if sp.fret not in _FRET_NAMES:
        return []
    return [(d, a) for d in range(sp.color) for a in range(d + 1, sp.color)
            if sp.R0[a, d] > 0 and 0 < sp.R[a, d] < _LARGE_R]


def crosstalk_values(sp, freq_khz):
    """{(dye, channel): relative crosstalk} for the dyes this species carries (0-based)."""
    dyes = dye_colours(sp, freq_khz)
    return {(d, c): float(sp.Cross[c, d]) for d in dyes for c in range(sp.color)
            if c != d and sp.Cross[c, d] > 0}


def direct_excitation_values(sp, freq_khz):
    """{(laser, dye): excitation by that laser relative to the dye's own laser} (0-based)."""
    exc = sp.excitation_matrix(freq_khz)
    out = {}
    for d in dye_colours(sp, freq_khz):
        for laser in range(sp.color):
            if laser != d and exc[d, laser] > 0 and exc[d, d] > 0:
                out[(laser, d)] = float(exc[d, laser] / exc[d, d])
    return out


def _pairs_text(values, fmt):
    return ", ".join(fmt.format(a + 1, b + 1) + f" = {_g(v, 4)}" for (a, b), v in sorted(values.items()))


def _matrix_section(lines, title, per_species, fmt, species):
    """'yes (...)' when all species agree on every pair, otherwise one line per species."""
    used = [(sp, v) for sp, v in zip(species, per_species) if v]
    if not used:
        lines.append(_line(title, "no"))
        return
    merged = {}
    for _, vals in used:
        for pair, v in vals.items():
            merged.setdefault(pair, set()).add(round(v, 12))
    if all(len(v) == 1 for v in merged.values()):
        lines.append(_line(title, "yes (" + _pairs_text({p: next(iter(v)) for p, v in merged.items()}, fmt) + ")"))
        return
    lines.append(_line(title, "yes (differs between species)"))
    for sp, vals in used:
        lines.append(_line(sp.name, _pairs_text(vals, fmt), indent=2))


def simulation_info(settings, *, file_name="", seed=None, sim_id="", elapsed=None, count_rates=None,
                    files=None, date=None):
    """The text of the info file (see the module docstring)."""
    freq = float(settings.freq)
    species = list(settings.species)
    n_colours = max((sp.color for sp in species), default=1)
    L = []
    L.append("PAMsim simulation info")
    L.append("=" * 22)
    L.append(_line("File name", file_name or settings.name))
    L.append(_line("Duration", f"{_g(settings.sim_time)} s"))
    L.append(_line("Microtime range", f"{_g(settings.mi_range)} ns"))
    if settings.use_noise:
        noise = np.asarray(settings.noise, float)[:n_colours]
        if np.all(noise == noise[0]):
            bg = f"yes ({_g(noise[0])} kHz per channel)"
        else:
            bg = "yes (" + ", ".join(f"ch{c + 1} = {_g(v)}" for c, v in enumerate(noise)) + " kHz)"
    else:
        bg = "no"
    L.append(_line("Background", bg))
    L.append(_line("Number of species", str(len(species))))

    # FRET: type, R0 and R of every species with an active pair
    fret_sp = [(sp, fret_pairs(sp)) for sp in species]
    fret_sp = [(sp, pairs) for sp, pairs in fret_sp if pairs]
    kinds = sorted({sp.fret for sp, _ in fret_sp})
    L.append(_line("FRET", " and ".join(_FRET_NAMES[k] for k in kinds) if kinds else "no"))
    if fret_sp:
        r0 = {}
        for sp, pairs in fret_sp:
            for d, a in pairs:
                r0.setdefault((d, a), set()).add(float(sp.R0[a, d]))
        common = all(len(v) == 1 for v in r0.values())
        if common:
            L.append(_line("R0", ", ".join(f"{d + 1}->{a + 1} = {_g(next(iter(v)))}"
                                           for (d, a), v in sorted(r0.items())), indent=2))
        for sp, pairs in fret_sp:
            parts = []
            for d, a in pairs:
                R, R0 = float(sp.R[a, d]), float(sp.R0[a, d])
                e = 1.0 / (1.0 + (R / R0) ** 6)
                parts.append(f"{d + 1}->{a + 1} = {_g(R)}" + ("" if common else f" (R0 = {_g(R0)})")
                             + f" (E = {e:.3f})")
            L.append(_line(f"R ({sp.name})", ", ".join(parts), indent=2))
        rates = settings.dynamic_rates
        if 3 in kinds and rates is not None:
            rates = np.asarray(rates, float)
            dyn = [f"{species[i].name} -> {species[j].name} = {_g(rates[i, j])}"
                   for i in range(rates.shape[0]) for j in range(rates.shape[1]) if i != j and rates[i, j] > 0]
            if dyn:
                L.append(_line("Dynamic rates [1/ms]", ", ".join(dyn), indent=2))

    _matrix_section(L, "Crosstalk", [crosstalk_values(sp, freq) for sp in species],
                    "dye {} -> channel {}", species)
    _matrix_section(L, "Direct excitation", [direct_excitation_values(sp, freq) for sp in species],
                    "laser {} -> dye {}", species)

    # species
    for i, sp in enumerate(species, start=1):
        L.append("")
        L.append(f"Species {i}")
        L.append(_line("Name", sp.name, indent=2))
        cols = dye_colours(sp, freq)
        b = species_brightness(sp, freq)
        which = ""
        if n_colours > 1 and cols:
            which = " (colour " + str(cols[0] + 1) + ")" if len(cols) == 1 else \
                " (colours " + ", ".join(str(c + 1) for c in cols) + ")"
        L.append(_line("Number of colours", f"{len(cols)}{which}" if cols else "0 (no dye: brightness 0 in all colours)",
                       indent=2))
        conc = concentration_text(settings, sp)
        lt = (lambda c: f"{_g(sp.LT[c])} ns") if sp.use_lt else (lambda c: "off")
        if len(cols) <= 1:
            L.append(_line("Diffusion coefficient", f"{_g(sp.D)} um^2/s", indent=2))
            L.append(_line("Concentration", conc, indent=2))
            if cols:
                L.append(_line("Brightness", f"{_g(b[cols[0]])} kHz", indent=2))
                L.append(_line("Lifetime", lt(cols[0]), indent=2))
        else:
            for c in cols:
                L.append(_line(f"Diffusion coefficient {c + 1}", f"{_g(sp.D)} um^2/s", indent=2))
                L.append(_line(f"Concentration {c + 1}", conc, indent=2))
                L.append(_line(f"Brightness {c + 1}", f"{_g(b[c])} kHz", indent=2))
                L.append(_line(f"Lifetime {c + 1}", lt(c), indent=2))

    # run details
    L.append("")
    L.append("Run")
    L.append(_line("Date", (date or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M:%S"), indent=2))
    if sim_id:
        L.append(_line("Planner Sim ID", sim_id, indent=2))
    if seed is not None:
        L.append(_line("Seed", str(seed), indent=2))
    if elapsed is not None:
        L.append(_line("Run time", f"{elapsed:.1f} s", indent=2))
    if count_rates is not None:
        L.append(_line("Count rates", ", ".join(f"ch{c + 1} = {r:.4g}" for c, r in enumerate(count_rates)
                                                if r > 0 or c < n_colours) + " kHz", indent=2))
    if files:
        L.append(_line("Files", ", ".join(os.path.basename(str(f)) for f in files), indent=2))
    return "\n".join(L) + "\n"


def data_file_names(files):
    """The data files (.sim / .npz, without the *_irf / *_scat helper files)."""
    names = [os.path.basename(str(f)) for f in files]
    return [n for n in names if n.endswith((".sim", ".npz")) and not n.endswith(("_irf.sim", "_scat.sim"))]


def write_info(path, settings, **kwargs):
    """Write :func:`simulation_info` to ``path``; ``file_name`` defaults to the data files in ``files``."""
    if not kwargs.get("file_name") and kwargs.get("files"):
        kwargs["file_name"] = ", ".join(data_file_names(kwargs["files"]))
    with open(path, "w", encoding="utf-8") as f:
        f.write(simulation_info(settings, **kwargs))
    return str(path)
