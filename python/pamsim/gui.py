"""Graphical interface for pamsim, modelled on PAM's Sim.m window.

Start with   python -m pamsim.gui   (or   python run_gui.py   in the python
folder).  Set the parameters, choose an output folder and press Start: the
simulated files (``<name>_1.sim``, ``<name>_2.sim``, ...) open in PAM via
Load TCSPC data -> "Pam Simulation Files".
"""

from __future__ import annotations

import copy
import json
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

import numpy as np

from .params import SimSettings, Species
from .simulate import SimulationCancelled, simulate

SCAN_TYPES = ["Point measurement", "Raster scan", "Line scan", "Circle scan (simulated as point)"]
FRET_TYPES = ["No FRET", "Static FRET", "Dynamic FRET"]
BARRIERS = ["1: Free diffusion", "2: Quenching map", "3: Restricted zones",
            "4: Barriers (equal transition prob.)", "5: Barriers (unequal transition prob.)",
            "6: Moving restricted zones", "7: Moving barriers", "8: Position dependent diffusion"]
MATRICES = {
    "Excitation probability  ExP[dye, laser]": ("ExP", "dye", "laser"),
    "Crosstalk  Cross[channel, dye]": ("Cross", "channel", "dye"),
    "Detection probability  DetP[channel, dye]": ("DetP", "channel", "dye"),
    "Bleaching probability  BlP[em. dye, ex. dye]": ("BlP", "em. dye", "ex. dye"),
}
COLOR_COLUMNS = [("Brightness", "kHz"), ("wr", "nm"), ("wz", "nm"), ("dX", "nm"), ("dY", "nm"),
                 ("dZ", "nm"), ("Lifetime", "ns"), ("r0", ""), ("rho", "ns"), ("r_inf", "")]
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # validated categorical slots 1-4


def _f(text, name):
    try:
        return float(str(text).strip())
    except ValueError:
        raise ValueError(f"'{name}' must be a number (got '{text}')") from None


def _fmt(v):
    v = float(v)
    return f"{v:g}"


class SimGUI:
    def __init__(self, root):
        self.root = root
        root.title("pamsim - Simulate photon data")
        self.settings = SimSettings(seed=None, species=[Species()])
        self.sel = 0
        self.matrix_key = list(MATRICES)[0]
        self.queue = queue.Queue()
        self.cancel = None
        self.worker = None
        self.last_result = None
        self.v = {}  # general variables

        style = ttk.Style(root)
        if sys.platform.startswith("linux") and "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Head.TLabel", font=("TkDefaultFont", 10, "bold"))

        main = ttk.Frame(root, padding=6)
        main.pack(fill="both", expand=True)
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        bottom = ttk.Frame(main)
        bottom.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)

        self._build_general(left)
        self._build_species(right)
        self._build_run(bottom)
        self._load_general()
        self._refresh_species_list()
        self._load_species()
        root.after(100, self._poll)

    # ------------------------------------------------------------- widgets
    def _var(self, key, value=""):
        self.v[key] = tk.StringVar(value=value)
        return self.v[key]

    def _row(self, parent, row, label, keys, unit="", width=8):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=2, pady=1)
        for i, k in enumerate(keys):
            ttk.Entry(parent, textvariable=self._var(k), width=width).grid(row=row, column=1 + i, padx=1, pady=1)
        ttk.Label(parent, text=unit).grid(row=row, column=4, sticky="w", padx=2)

    def _build_general(self, parent):
        g = ttk.LabelFrame(parent, text="General", padding=4)
        g.pack(fill="x")
        self._row(g, 0, "Box size (x, y, z)", ["bs0", "bs1", "bs2"], "nm  (z = 0: 2D)")
        self._row(g, 1, "Sampling frequency", ["freq"], "kHz")
        self._row(g, 2, "Simulation time", ["time"], "s")
        self._row(g, 3, "Frames", ["frames"])
        self._row(g, 4, "Seed", ["seed"], "empty = random")
        self._row(g, 5, "Microtime range", ["mirange"], "ns")

        s = ttk.LabelFrame(parent, text="Scanning", padding=4)
        s.pack(fill="x", pady=(4, 0))
        ttk.Label(s, text="Scan type").grid(row=0, column=0, sticky="w", padx=2)
        self.scan_cb = ttk.Combobox(s, values=SCAN_TYPES, state="readonly", width=30)
        self.scan_cb.grid(row=0, column=1, columnspan=3, sticky="w", pady=1)
        self._row(s, 1, "Pixels / lines", ["px0", "px1"])
        self._row(s, 2, "Pixel size (x, y)", ["sz0", "sz1"], "nm")
        self._row(s, 3, "Pixel time, line time", ["t0", "t1"], "us, ms")

        n = ttk.LabelFrame(parent, text="Background", padding=4)
        n.pack(fill="x", pady=(4, 0))
        self.use_noise = tk.BooleanVar()
        ttk.Checkbutton(n, text="Apply noise per channel [kHz]", variable=self.use_noise).grid(
            row=0, column=0, columnspan=5, sticky="w")
        for i in range(4):
            ttk.Entry(n, textvariable=self._var(f"noise{i}"), width=7).grid(row=1, column=i, padx=1)

        o = ttk.LabelFrame(parent, text="Output", padding=4)
        o.pack(fill="x", pady=(4, 0))
        ttk.Label(o, text="Folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(o, textvariable=self._var("folder", os.getcwd()), width=28).grid(row=0, column=1, columnspan=2, sticky="we")
        ttk.Button(o, text="...", width=3, command=self._choose_folder).grid(row=0, column=3)
        ttk.Label(o, text="File name").grid(row=1, column=0, sticky="w")
        ttk.Entry(o, textvariable=self._var("name"), width=20).grid(row=1, column=1, sticky="w")
        ttk.Label(o, text="Number of files").grid(row=2, column=0, sticky="w")
        ttk.Entry(o, textvariable=self._var("nfiles", "1"), width=6).grid(row=2, column=1, sticky="w")
        ttk.Label(o, text="Format").grid(row=3, column=0, sticky="w")
        self.fmt = ttk.Combobox(o, values=[".sim (PAM)", ".npz (numpy)", "both"], state="readonly", width=14)
        self.fmt.current(0)
        self.fmt.grid(row=3, column=1, sticky="w")
        self.save_setup = tk.BooleanVar(value=True)
        ttk.Checkbutton(o, text="Also save the setup (.json)", variable=self.save_setup).grid(
            row=4, column=0, columnspan=3, sticky="w")
        b = ttk.Frame(parent)
        b.pack(fill="x", pady=(4, 0))
        ttk.Button(b, text="Load setup...", command=self._load_setup).pack(side="left")
        ttk.Button(b, text="Save setup...", command=self._save_setup).pack(side="left", padx=4)

    def _build_advanced(self, parent):
        a = ttk.LabelFrame(parent, text="Advanced (uses the DifSim_ani kernel)", padding=4)
        a.pack(fill="x", pady=(0, 6), anchor="w")
        self.use_irf = tk.BooleanVar(); self.use_aniso = tk.BooleanVar()
        self.use_fw = tk.BooleanVar(); self.use_lw = tk.BooleanVar()
        ttk.Checkbutton(a, text="IRF, width [ps]", variable=self.use_irf).grid(row=0, column=0, sticky="w")
        ttk.Entry(a, textvariable=self._var("irf"), width=8).grid(row=0, column=1)
        ttk.Checkbutton(a, text="Anisotropy (8 channels: par + perp)", variable=self.use_aniso).grid(
            row=1, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(a, text="Distance width, update [ms]", variable=self.use_fw).grid(row=2, column=0, sticky="w")
        ttk.Entry(a, textvariable=self._var("hetupd"), width=8).grid(row=2, column=1)
        ttk.Checkbutton(a, text="Linker width", variable=self.use_lw).grid(row=3, column=0, sticky="w")
        ttk.Entry(a, textvariable=self._var("linker"), width=8).grid(row=3, column=1)

        m = ttk.LabelFrame(parent, text="Barrier / quenching map (1 px = 1 nm)", padding=4)
        m.pack(fill="x", pady=(0, 6), anchor="w")
        self.map_label = ttk.Label(m, text="no map loaded", width=34)
        self.map_label.grid(row=0, column=0, sticky="w")
        ttk.Button(m, text="Load map...", command=self._load_map).grid(row=0, column=1, padx=2)
        ttk.Button(m, text="Clear", command=self._clear_map).grid(row=0, column=2)

        p = ttk.LabelFrame(parent, text="Performance", padding=4)
        p.pack(fill="x", pady=(0, 6), anchor="w")
        self.ff = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text="Fast-forward far from the focus", variable=self.ff).grid(row=0, column=0, sticky="w")
        ttk.Label(p, text="Threads").grid(row=0, column=1, padx=(10, 2))
        ttk.Entry(p, textvariable=self._var("threads", str(os.cpu_count() or 1)), width=4).grid(row=0, column=2)
        self.reset_bleach = tk.BooleanVar()
        ttk.Checkbutton(p, text="Unbleach at every frame (like Sim.m)", variable=self.reset_bleach).grid(
            row=1, column=0, columnspan=3, sticky="w")


    def _build_species(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x")
        lf = ttk.LabelFrame(top, text="Species", padding=4)
        lf.pack(side="left", fill="y")
        self.sp_list = tk.Listbox(lf, height=6, width=18, exportselection=False)
        self.sp_list.grid(row=0, column=0, columnspan=3)
        self.sp_list.bind("<<ListboxSelect>>", self._on_select_species)
        ttk.Button(lf, text="Add", width=6, command=self._add_species).grid(row=1, column=0, pady=2)
        ttk.Button(lf, text="Copy", width=6, command=self._copy_species).grid(row=1, column=1)
        ttk.Button(lf, text="Delete", width=6, command=self._delete_species).grid(row=1, column=2)

        pf = ttk.LabelFrame(top, text="Selected species", padding=4)
        pf.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.sv = {k: tk.StringVar() for k in ("name", "D", "N")}
        ttk.Label(pf, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(pf, textvariable=self.sv["name"], width=18).grid(row=0, column=1, sticky="w")
        ttk.Label(pf, text="Colours").grid(row=0, column=2, sticky="e", padx=(8, 2))
        self.color_cb = ttk.Combobox(pf, values=["1", "2", "3", "4"], state="readonly", width=4)
        self.color_cb.grid(row=0, column=3, sticky="w")
        self.color_cb.bind("<<ComboboxSelected>>", lambda e: self._update_color_rows())
        ttk.Label(pf, text="D [um^2/s]").grid(row=1, column=0, sticky="w")
        ttk.Entry(pf, textvariable=self.sv["D"], width=10).grid(row=1, column=1, sticky="w")
        ttk.Label(pf, text="Particles N").grid(row=1, column=2, sticky="e", padx=(8, 2))
        ent = ttk.Entry(pf, textvariable=self.sv["N"], width=8)
        ent.grid(row=1, column=3, sticky="w")
        self.conc = ttk.Label(pf, text="")
        self.conc.grid(row=1, column=4, sticky="w", padx=6)
        self.sv["N"].trace_add("write", lambda *a: self._update_conc())
        for k in ("bs0", "bs1", "bs2"):
            self.v[k].trace_add("write", lambda *a: self._update_conc())
        ttk.Label(pf, text="FRET").grid(row=2, column=0, sticky="w")
        self.fret_cb = ttk.Combobox(pf, values=FRET_TYPES, state="readonly", width=14)
        self.fret_cb.grid(row=2, column=1, sticky="w")
        self.fret_cb.bind("<<ComboboxSelected>>", lambda e: self._update_dyn_table())
        ttk.Label(pf, text="Map type").grid(row=2, column=2, sticky="e", padx=(8, 2))
        self.barrier_cb = ttk.Combobox(pf, values=BARRIERS, state="readonly", width=34)
        self.barrier_cb.grid(row=2, column=3, columnspan=2, sticky="w")
        self.use_lt = tk.BooleanVar()
        ttk.Checkbutton(pf, text="Use lifetime", variable=self.use_lt).grid(row=3, column=0, columnspan=2, sticky="w")

        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True, pady=(6, 0))

        # per colour table
        cf = ttk.Frame(nb, padding=4)
        nb.add(cf, text="Colours / focus / lifetime")
        for j, (name, unit) in enumerate(COLOR_COLUMNS):
            ttk.Label(cf, text=f"{name}\n[{unit}]" if unit else f"{name}\n", justify="center").grid(row=0, column=j + 1, padx=1)
        self.cvars = [[tk.StringVar() for _ in COLOR_COLUMNS] for _ in range(4)]
        self.cent = []
        for i in range(4):
            ttk.Label(cf, text=f"Colour {i + 1}").grid(row=i + 1, column=0, sticky="w")
            row = []
            for j in range(len(COLOR_COLUMNS)):
                e = ttk.Entry(cf, textvariable=self.cvars[i][j], width=8)
                e.grid(row=i + 1, column=j + 1, padx=1, pady=1)
                row.append(e)
            self.cent.append(row)
        ttk.Label(cf, text="Brightness sets the diagonal of ExP like in Sim.m (peak count rate of one molecule).\n"
                           "r0, rho, r_inf are only used with anisotropy switched on.",
                  foreground="#52514e").grid(row=6, column=0, columnspan=11, sticky="w", pady=(6, 0))

        # matrices
        mf = ttk.Frame(nb, padding=4)
        nb.add(mf, text="Excitation / crosstalk / detection / bleaching")
        self.mat_cb = ttk.Combobox(mf, values=list(MATRICES), state="readonly", width=44)
        self.mat_cb.current(0)
        self.mat_cb.grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 4))
        self.mat_cb.bind("<<ComboboxSelected>>", self._on_matrix_change)
        self.mvars = [[tk.StringVar() for _ in range(4)] for _ in range(4)]
        self.mrow_lbl = [ttk.Label(mf, text="") for _ in range(4)]
        self.mcol_lbl = [ttk.Label(mf, text="") for _ in range(4)]
        for j in range(4):
            self.mcol_lbl[j].grid(row=1, column=j + 1)
        for i in range(4):
            self.mrow_lbl[i].grid(row=i + 2, column=0, sticky="w", padx=(0, 4))
            for j in range(4):
                ttk.Entry(mf, textvariable=self.mvars[i][j], width=10).grid(row=i + 2, column=j + 1, padx=1, pady=1)
        self.mat_note = ttk.Label(mf, text="", foreground="#52514e")
        self.mat_note.grid(row=6, column=0, columnspan=5, sticky="w", pady=(6, 0))

        # FRET
        ff = ttk.Frame(nb, padding=4)
        nb.add(ff, text="FRET / dynamics")
        self.fvars = {}
        pairs = [(1, 0), (2, 0), (3, 0), (2, 1), (3, 1), (3, 2)]
        for c, (title, key) in enumerate((("Foerster radius R0", "R0"), ("Distance R", "R"),
                                          ("Distance width sigma", "distance_width"))):
            ttk.Label(ff, text=title, style="Head.TLabel").grid(row=0, column=2 * c, columnspan=2, sticky="w", padx=(0 if c == 0 else 12, 0))
            for r, (a, d) in enumerate(pairs):
                ttk.Label(ff, text=f"{d + 1} -> {a + 1}").grid(row=r + 1, column=2 * c, sticky="e", padx=(0 if c == 0 else 12, 2))
                var = tk.StringVar()
                ttk.Entry(ff, textvariable=var, width=8).grid(row=r + 1, column=2 * c + 1, pady=1)
                self.fvars[(key, a, d)] = var
        ttk.Label(ff, text="donor -> acceptor (colour numbers); same unit for R0, R, sigma and linker width",
                  foreground="#52514e").grid(row=8, column=0, columnspan=6, sticky="w", pady=(4, 0))
        self.dyn_frame = ttk.LabelFrame(ff, text="Dynamic interconversion rates [1/ms], from (row) -> to (column)", padding=4)
        self.dyn_frame.grid(row=9, column=0, columnspan=6, sticky="we", pady=(8, 0))
        self.dyn_vars = []
        self.dyn_values = np.zeros((1, 1))

        af = ttk.Frame(nb, padding=4)
        nb.add(af, text="Advanced / maps / performance")
        self._build_advanced(af)

    def _build_run(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x")
        self.start_btn = ttk.Button(bar, text="Start", width=10, command=self._start_stop)
        self.start_btn.pack(side="left")
        self.plot_btn = ttk.Button(bar, text="Plot last result", command=self._plot, state="disabled")
        self.plot_btn.pack(side="left", padx=6)
        self.progress = ttk.Progressbar(bar, mode="determinate", maximum=1.0)
        self.progress.pack(side="left", fill="x", expand=True, padx=6)
        self.status = ttk.Label(bar, text="ready", width=40)
        self.status.pack(side="left")
        self.log = tk.Text(parent, height=7, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, pady=(4, 0))

    # ------------------------------------------------------------- model <-> widgets
    def _load_general(self):
        s = self.settings
        for i in range(3):
            self.v[f"bs{i}"].set(_fmt(s.box_size[i]))
        self.v["freq"].set(_fmt(s.freq)); self.v["time"].set(_fmt(s.sim_time))
        self.v["frames"].set(str(int(s.frames)))
        self.v["seed"].set("" if s.seed is None else str(s.seed))
        self.v["mirange"].set(_fmt(s.mi_range))
        self.scan_cb.current(max(0, min(3, int(s.scan_type) - 1)))
        for i in range(2):
            self.v[f"px{i}"].set(_fmt(s.pixels[i])); self.v[f"sz{i}"].set(_fmt(s.pixel_size[i]))
            self.v[f"t{i}"].set(_fmt(s.times[i]))
        self.use_noise.set(bool(s.use_noise))
        for i in range(4):
            self.v[f"noise{i}"].set(_fmt(s.noise[i]))
        self.use_irf.set(bool(s.use_irf)); self.v["irf"].set(_fmt(s.irf_width))
        self.use_aniso.set(bool(s.use_aniso))
        self.use_fw.set(bool(s.use_fret_width)); self.v["hetupd"].set(_fmt(s.heterogeneity_update))
        self.use_lw.set(bool(s.use_linker_width)); self.v["linker"].set(_fmt(s.linker_width))
        self.ff.set(bool(s.fast_forward)); self.reset_bleach.set(bool(s.reset_bleaching_each_frame))
        self.v["name"].set(s.name)
        if s.dynamic_rates is not None:
            self.dyn_values = np.array(s.dynamic_rates, float)
        self._show_map()

    def _store_general(self):
        s = self.settings
        s.box_size = np.array([_f(self.v[f"bs{i}"].get(), "box size") for i in range(3)])
        s.freq = _f(self.v["freq"].get(), "frequency")
        s.sim_time = _f(self.v["time"].get(), "simulation time")
        s.frames = max(1, int(_f(self.v["frames"].get(), "frames")))
        seed = self.v["seed"].get().strip()
        s.seed = int(_f(seed, "seed")) if seed else None
        s.mi_range = _f(self.v["mirange"].get(), "microtime range")
        s.scan_type = self.scan_cb.current() + 1
        s.pixels = np.array([_f(self.v[f"px{i}"].get(), "pixels") for i in range(2)])
        s.pixel_size = np.array([_f(self.v[f"sz{i}"].get(), "pixel size") for i in range(2)])
        s.times = np.array([_f(self.v["t0"].get(), "pixel time"), _f(self.v["t1"].get(), "line time"),
                            s.times[2]])
        s.use_noise = self.use_noise.get()
        s.noise = np.array([_f(self.v[f"noise{i}"].get(), "noise") for i in range(4)])
        s.use_irf = self.use_irf.get(); s.irf_width = _f(self.v["irf"].get(), "IRF width")
        s.use_aniso = self.use_aniso.get()
        s.use_fret_width = self.use_fw.get(); s.heterogeneity_update = _f(self.v["hetupd"].get(), "update time")
        s.use_linker_width = self.use_lw.get(); s.linker_width = _f(self.v["linker"].get(), "linker width")
        s.fast_forward = self.ff.get(); s.reset_bleaching_each_frame = self.reset_bleach.get()
        s.n_threads = max(1, int(_f(self.v["threads"].get(), "threads")))
        s.name = self.v["name"].get().strip() or "Simulation"
        self._store_dyn()
        n = len(s.species)
        s.dynamic_rates = self.dyn_values[:n, :n].copy() if np.any(self.dyn_values[:n, :n]) else None

    def _load_species(self):
        sp = self.settings.species[self.sel]
        self.sv["name"].set(sp.name); self.sv["D"].set(_fmt(sp.D)); self.sv["N"].set(str(int(sp.N)))
        self.color_cb.current(sp.color - 1)
        self.fret_cb.current(sp.fret - 1)
        self.barrier_cb.current(sp.barrier - 1)
        self.use_lt.set(bool(sp.use_lt))
        bright = sp.brightness if sp.brightness is not None else np.diag(sp.ExP) * self.settings.freq
        cols = [bright, sp.wr, sp.wz, sp.dX, sp.dY, sp.dZ, sp.LT, sp.aniso[:, 0], sp.aniso[:, 1], sp.aniso[:, 2]]
        for i in range(4):
            for j, c in enumerate(cols):
                self.cvars[i][j].set(_fmt(c[i]))
        for (key, a, d), var in self.fvars.items():
            var.set(_fmt(getattr(sp, key)[a, d]))
        self._load_matrix()
        self._update_color_rows()
        self._update_conc()
        self._update_dyn_table()

    def _store_species(self):
        sp = self.settings.species[self.sel]
        sp.name = self.sv["name"].get().strip() or f"Species {self.sel + 1}"
        sp.D = _f(self.sv["D"].get(), "D")
        sp.N = max(0, int(_f(self.sv["N"].get(), "N")))
        sp.color = self.color_cb.current() + 1
        sp.fret = self.fret_cb.current() + 1
        sp.barrier = self.barrier_cb.current() + 1
        sp.use_lt = self.use_lt.get()
        vals = np.array([[_f(self.cvars[i][j].get(), COLOR_COLUMNS[j][0]) for j in range(len(COLOR_COLUMNS))]
                         for i in range(4)])
        sp.brightness = vals[:, 0].copy()
        sp.wr, sp.wz, sp.dX, sp.dY, sp.dZ, sp.LT = (vals[:, k].copy() for k in range(1, 7))
        sp.aniso = sp.aniso.copy()
        sp.aniso[:, 0:3] = vals[:, 7:10]
        for (key, a, d), var in self.fvars.items():
            getattr(sp, key)[a, d] = _f(var.get(), key)
        self._store_matrix()

    def _load_matrix(self):
        attr, rlab, clab = MATRICES[self.matrix_key]
        m = getattr(self.settings.species[self.sel], attr)
        for i in range(4):
            self.mrow_lbl[i].configure(text=f"{rlab} {i + 1}")
            self.mcol_lbl[i].configure(text=f"{clab} {i + 1}")
            for j in range(4):
                self.mvars[i][j].set(_fmt(m[i, j]))
        notes = {"ExP": "Diagonal is set from the Brightness column; off-diagonal = direct excitation of a dye by another laser.",
                 "Cross": "Relative crosstalk of a dye's photons into other channels (diagonal is always 1).",
                 "DetP": "Probability that an emitted photon of a dye is detected in a channel (0..1).",
                 "BlP": "Probability per emitted photon that the dye bleaches (it recovers when leaving the box)."}
        self.mat_note.configure(text=notes[attr])

    def _store_matrix(self):
        attr, _, _ = MATRICES[self.matrix_key]
        sp = self.settings.species[self.sel]
        m = np.array([[_f(self.mvars[i][j].get(), attr) for j in range(4)] for i in range(4)])
        setattr(sp, attr, m)

    def _on_matrix_change(self, _event=None):
        try:
            self._store_matrix()
        except ValueError as err:
            messagebox.showerror("Invalid value", str(err))
            self.mat_cb.set(self.matrix_key)
            return
        self.matrix_key = self.mat_cb.get()
        self._load_matrix()

    def _update_color_rows(self):
        n = self.color_cb.current() + 1
        for i in range(4):
            for e in self.cent[i]:
                e.configure(state="normal" if i < n else "disabled")

    def _update_conc(self):
        try:
            n = float(self.sv["N"].get())
            bs = [float(self.v[f"bs{i}"].get()) for i in range(3)]
            vol = np.prod([b for b in bs if b > 0])
            if bs[2] > 0:
                c = n / vol / 1e-24 / 6.022e23 / 1e-9
                self.conc.configure(text=f"= {c:.3g} nM")
            else:
                self.conc.configure(text=f"= {n / vol * 1e6:.3g} /um^2")
        except (ValueError, ZeroDivisionError):
            self.conc.configure(text="")

    def _store_dyn(self):
        for i, row in enumerate(self.dyn_vars):
            for j, var in enumerate(row):
                if i != j:
                    self.dyn_values[i, j] = _f(var.get(), "dynamic rate")

    def _update_dyn_table(self):
        n = len(self.settings.species)
        if self.dyn_vars:
            try:
                self._store_dyn()
            except ValueError:
                pass
        old = self.dyn_values
        self.dyn_values = np.zeros((n, n))
        k = min(n, old.shape[0])
        self.dyn_values[:k, :k] = old[:k, :k]
        for w in self.dyn_frame.winfo_children():
            w.destroy()
        names = [s.name for s in self.settings.species]
        dynamic = any(s.fret == 3 for s in self.settings.species) or self.fret_cb.current() == 2
        if not dynamic or n < 2:
            ttk.Label(self.dyn_frame, text="Set FRET to 'Dynamic FRET' and add >= 2 species "
                                           "(each species is one state).", foreground="#52514e").grid(row=0, column=0)
            self.dyn_vars = []
            return
        self.dyn_vars = [[tk.StringVar(value=_fmt(self.dyn_values[i, j])) for j in range(n)] for i in range(n)]
        for j in range(n):
            ttk.Label(self.dyn_frame, text=names[j][:10]).grid(row=0, column=j + 1)
        for i in range(n):
            ttk.Label(self.dyn_frame, text=names[i][:10]).grid(row=i + 1, column=0, sticky="w")
            for j in range(n):
                e = ttk.Entry(self.dyn_frame, textvariable=self.dyn_vars[i][j], width=8)
                e.grid(row=i + 1, column=j + 1, padx=1, pady=1)
                if i == j:
                    e.configure(state="disabled")

    # ------------------------------------------------------------- species list
    def _refresh_species_list(self):
        self.sp_list.delete(0, "end")
        for sp in self.settings.species:
            self.sp_list.insert("end", sp.name)
        self.sp_list.selection_clear(0, "end")
        self.sp_list.selection_set(self.sel)

    def _safe_store(self):
        try:
            self._store_species()
            return True
        except ValueError as err:
            messagebox.showerror("Invalid value", str(err))
            return False

    def _on_select_species(self, _event=None):
        cur = self.sp_list.curselection()
        if not cur or cur[0] == self.sel:
            return
        if not self._safe_store():
            self._refresh_species_list()
            return
        self.sel = cur[0]
        self._refresh_species_list()
        self._load_species()

    def _add_species(self):
        if not self._safe_store():
            return
        self.settings.species.append(Species(name=f"Species {len(self.settings.species) + 1}"))
        self.sel = len(self.settings.species) - 1
        self._refresh_species_list()
        self._load_species()

    def _copy_species(self):
        if not self._safe_store():
            return
        sp = copy.deepcopy(self.settings.species[self.sel])
        sp.name = f"Species {len(self.settings.species) + 1}"
        self.settings.species.append(sp)
        self.sel = len(self.settings.species) - 1
        self._refresh_species_list()
        self._load_species()

    def _delete_species(self):
        if len(self.settings.species) <= 1:
            return
        del self.settings.species[self.sel]
        self.sel = max(0, self.sel - 1)
        self._refresh_species_list()
        self._load_species()

    # ------------------------------------------------------------- files
    def _choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.v["folder"].get() or os.getcwd())
        if d:
            self.v["folder"].set(d)

    def _load_map(self):
        path = filedialog.askopenfilename(filetypes=[("Maps", "*.npy *.mat *.txt *.csv *.tif *.tiff"), ("All", "*.*")])
        if not path:
            return
        try:
            self.settings.maps = load_map_file(path)
        except Exception as err:  # noqa: BLE001
            messagebox.showerror("Could not load map", str(err))
            return
        self._show_map(os.path.basename(path))

    def _clear_map(self):
        self.settings.maps = None
        self._show_map()

    def _show_map(self, name=None):
        m = self.settings.maps
        if m is None:
            self.map_label.configure(text="no map loaded")
        else:
            shape = " x ".join(str(x) for x in np.shape(m))
            self.map_label.configure(text=f"{name or 'map'}  ({shape})")

    def _load_setup(self):
        path = filedialog.askopenfilename(filetypes=[("Setup (pamsim or Sim.m JSON)", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            s = SimSettings.load_json(path)
        except Exception as err:  # noqa: BLE001
            messagebox.showerror("Could not load setup", str(err))
            return
        s.maps = self.settings.maps
        self.settings = s
        self.sel = 0
        self.dyn_values = np.array(s.dynamic_rates, float) if s.dynamic_rates is not None else np.zeros((1, 1))
        self._load_general()
        self._refresh_species_list()
        self._load_species()
        self._log(f"loaded setup {path}")

    def _save_setup(self):
        try:
            self._store_species(); self._store_general()
        except ValueError as err:
            messagebox.showerror("Invalid value", str(err)); return
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile=self.settings.name + ".json")
        if path:
            save_setup(self.settings, path)
            self._log(f"saved setup {path}")

    # ------------------------------------------------------------- run
    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start_stop(self):
        if self.worker is not None and self.worker.is_alive():
            self.cancel.set()
            self.status.configure(text="stopping...")
            return
        try:
            self._store_species()
            self._store_general()
            nfiles = max(1, int(_f(self.v["nfiles"].get(), "number of files")))
        except ValueError as err:
            messagebox.showerror("Invalid value", str(err))
            return
        folder = self.v["folder"].get().strip() or os.getcwd()
        if not os.path.isdir(folder):
            messagebox.showerror("Output folder", f"Folder does not exist:\n{folder}")
            return
        self.cancel = threading.Event()
        fmt = self.fmt.current()
        job = (copy.deepcopy(self.settings), folder, nfiles, fmt, self.save_setup.get())
        self.worker = threading.Thread(target=self._run, args=job, daemon=True)
        self.start_btn.configure(text="Stop")
        self.progress["value"] = 0
        self.worker.start()

    def _run(self, settings, folder, nfiles, fmt, save_json):
        q = self.queue
        try:
            for k in range(nfiles):
                s = copy.deepcopy(settings)
                if settings.seed is not None:
                    s.seed = settings.seed + k
                q.put(("status", f"file {k + 1}/{nfiles}: preparing (first run compiles, ~15 s)"))

                def progress(done, total, k=k):
                    q.put(("progress", (k + done / total) / nfiles,
                           f"file {k + 1}/{nfiles}: particle {done}/{total}"))
                r = simulate(s, progress=progress, cancel=self.cancel)
                base = os.path.join(folder, f"{s.name}_{k + 1}")
                written = []
                if fmt in (0, 2):
                    written += r.save_sim(base + ".sim")
                if fmt in (1, 2):
                    written.append(r.save_npz(base + ".npz"))
                if save_json:
                    save_setup(s, base + "_setup.json", seed=r.seed)
                    written.append(base + "_setup.json")
                rates = ", ".join(f"{x:.2f}" for x in r.count_rates_khz())
                q.put(("log", f"{os.path.basename(base)}: {r.elapsed:.1f} s, seed {r.seed}, "
                              f"{sum(len(m) for m in r.macrotimes)} photons, count rates [kHz]: {rates}\n"
                              f"   wrote: " + ", ".join(os.path.basename(w) for w in written)))
                q.put(("result", r))
            q.put(("done", "finished"))
        except SimulationCancelled:
            q.put(("done", "stopped"))
        except Exception:  # noqa: BLE001
            q.put(("error", traceback.format_exc()))

    def _poll(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status.configure(text=msg[1])
                elif kind == "progress":
                    self.progress["value"] = msg[1]
                    self.status.configure(text=msg[2])
                elif kind == "log":
                    self._log(msg[1])
                elif kind == "result":
                    self.last_result = msg[1]
                    self.plot_btn.configure(state="normal")
                elif kind == "done":
                    self.status.configure(text=msg[1])
                    if msg[1] == "finished":
                        self.progress["value"] = 1.0
                    self.start_btn.configure(text="Start")
                elif kind == "error":
                    self._log(msg[1])
                    self.status.configure(text="error (see log)")
                    self.start_btn.configure(text="Start")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _plot(self):
        r = self.last_result
        if r is None:
            return
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            from matplotlib.figure import Figure
        except ImportError:
            messagebox.showinfo("Plot", "Install matplotlib to plot:  python -m pip install matplotlib")
            return
        from .correlation import correlate_blocks
        win = tk.Toplevel(self.root)
        win.title("Last simulation")
        fig = Figure(figsize=(9, 3.6), dpi=100, facecolor="#fcfcfb")
        ax1 = fig.add_subplot(1, 2, 1); ax2 = fig.add_subplot(1, 2, 2)
        total = r.header["Frames"] * r.header["FrameTime"]
        chans = [c for c in range(min(r.n_channels, 4)) if r.macrotimes[c].size]
        binw = max(1, int(r.freq_hz * 1e-3))  # 1 ms bins
        nb = int(total // binw) + 1
        for c in chans:
            tr = np.bincount((r.macrotimes[c] // binw).astype(np.int64), minlength=nb)[:nb]
            t = np.arange(nb) * binw / r.freq_hz
            ax1.plot(t, tr / (binw / r.freq_hz) / 1e3, lw=0.7, alpha=0.85, color=PALETTE[c], label=f"channel {c + 1}")
        ax1.set_xlabel("time [s]"); ax1.set_ylabel("count rate [kHz] (1 ms bins)")
        ax1.set_title("Intensity trace", fontsize=10)
        curves = [(c, c, f"auto {c + 1}") for c in chans[:2]]
        if len(chans) >= 2:
            curves.append((chans[0], chans[1], f"cross {chans[0] + 1}x{chans[1] + 1}"))
        for k, (a, b, lab) in enumerate(curves):
            try:
                lags, g, sem, _ = correlate_blocks(r.macrotimes[a], r.macrotimes[b], total, n_blocks=10)
            except Exception:  # noqa: BLE001 - e.g. too few photons
                continue
            ok = lags > 0
            ax2.plot(lags[ok] / r.freq_hz, g[ok], lw=2, color=PALETTE[k], label=lab)
        ax2.set_xscale("log"); ax2.set_xlabel("lag time [s]"); ax2.set_ylabel("G(tau)")
        ax2.set_title("Correlation (10 sections)", fontsize=10)
        for ax in (ax1, ax2):
            ax.set_facecolor("#fcfcfb")
            ax.grid(True, color="#e6e5e0", lw=0.6)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            if len(ax.lines) >= 2:
                ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        NavigationToolbar2Tk(canvas, win)
        canvas.get_tk_widget().pack(fill="both", expand=True)


def save_setup(settings, path, seed=None):
    s = copy.copy(settings)
    s.maps = None  # maps are not stored in the JSON
    d = s.to_dict()
    if seed is not None:
        d["seed"] = int(seed)
    with open(path, "w") as f:
        json.dump(d, f, indent=2)


def load_map_file(path):
    """Load a barrier/quenching map: 2D (x, y) or 3D (frames, x, y) array."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".npy":
        m = np.load(path)
    elif ext == ".mat":
        from scipy.io import loadmat
        d = loadmat(path)
        cands = [v for k, v in d.items() if not k.startswith("__") and isinstance(v, np.ndarray)
                 and v.dtype != object and v.ndim in (2, 3)]
        if not cands:
            raise ValueError("no 2D/3D numeric variable in the .mat file")
        m = cands[0]
        if m.ndim == 3:  # MATLAB stacks frames in the 3rd dimension
            m = np.moveaxis(m, 2, 0)
    elif ext in (".tif", ".tiff"):
        from PIL import Image, ImageSequence
        with Image.open(path) as im:
            frames = [np.array(f, dtype=float).T for f in ImageSequence.Iterator(im)]
        m = frames[0] if len(frames) == 1 else np.stack(frames)
    else:
        m = np.loadtxt(path, delimiter="," if ext == ".csv" else None)
    m = np.asarray(m, dtype=float)
    if m.ndim not in (2, 3):
        raise ValueError(f"map must be 2D or 3D, got shape {m.shape}")
    return m


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    root = tk.Tk()
    SimGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
