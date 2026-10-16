"""PAMsim - graphical interface for pamsim, modelled on PAM's Sim.m window.

Start it by double-clicking ``PAMsim.pyw`` (or the desktop shortcut made by
``Install_PAMsim.bat``), or with ``python -m pamsim.gui``.  Pick a preset or
set the parameters, choose an output folder and press Start: the simulated
files (``<name>_1.sim``, ...) open in PAM via Load TCSPC data -> "Pam
Simulation Files".
"""

from __future__ import annotations

import copy
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

import numpy as np

from .params import SimSettings, Species
from .report import species_brightness
from .simulate import SimulationCancelled, _crosstalk, simulate

APP = "PAMsim"
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
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
INK2 = "#5d5c58"
LEVEL_COLORS = {"ok": "#0c7a0c", "info": "#2a62a8", "warn": "#a35a00", "error": "#c0302f"}
LEVEL_ICONS = {"ok": "✔", "info": "ℹ", "warn": "⚠", "error": "✖"}

TIPS = {
    "bs": "Size of the simulation box in nm. Particles leaving it re-enter on the other side.\n"
          "Set z = 0 for a 2D (membrane) simulation. Keep it several focus sizes large.",
    "freq": "Sampling frequency of the random walk in kHz (time step = 1/frequency).\n"
            "The brightness of a molecule must stay well below this value.",
    "time": "Total simulated measurement time in seconds.",
    "frames": "Number of frames. Relevant for scanning; for point measurements 1 is fine.",
    "seed": "Random seed. Leave empty for a new random simulation each time;\n"
            "set a number to reproduce a simulation exactly.",
    "mirange": "Microtime (TCSPC) range in ns, i.e. the PIE period of all lasers together.",
    "scan": "Point measurement = FCS/FCCS/smFRET. Raster and line scans move the focus (RICS, pCF).",
    "px": "Number of pixels per line and lines per frame (scanning only).",
    "sz": "Pixel size and line distance in nm (scanning only).",
    "tpx": "Pixel dwell time in us and line time in ms (scanning only).",
    "noise": "Uncorrelated background count rate per detection channel in kHz.",
    "D": "Diffusion coefficient in um^2/s (e.g. ~400 for a free dye, ~30-100 for proteins).",
    "N": "Number of molecules of this species in the whole box. The concentration is shown next to it.",
    "colors": "Number of colours/dyes of the setup (lasers and detection channels in PIE).",
    "fret": "FRET between the dyes of this species. 'Dynamic' switches between species (states).",
    "map": "Barrier or quenching map (needs a map file on the Advanced tab).",
    "brightness": "Molecular brightness per colour in kHz = count rate of one molecule in the focus centre.\n"
                  "0 means the species carries no dye of this colour. Keep it < 10% of the sampling frequency.",
    "folder": "Folder where the .sim files are written.",
    "name": "File name; files are called <name>_1.sim, <name>_2.sim, ...",
    "nfiles": "Number of independent simulations with the same parameters (each saved as its own file).",
    "threads": "Number of CPU cores used.",
    "ownfolder": "Each simulation is written into a subfolder <output folder>/<file name>/,\n"
                 "created automatically - all its .sim, IRF and setup files stay together.",
    "ff": "Skips the random walk while a molecule is far from the focus (exact up to ~1e-12). Much faster.",
}

HELP_TEXT = """How to simulate data for PAM

1.  Start from a preset (top right) or load a setup.
2.  Measurement (left): box size, sampling frequency, time.
3.  Molecules (middle): one entry per species.  For each species set D, the
    number of molecules N and the brightness per colour (0 = dye not present).
    Several species = a mixture; for FCCS give a species brightness in two or
    three colours (a double/triple labelled complex).
4.  Check (right) warns about settings that would bias the result, for
    example a brightness close to the sampling frequency.
5.  Choose an output folder and press Start.
6.  In PAM: Load TCSPC data -> file type "Pam Simulation Files" -> select the
    .sim file(s).  Each colour is one detection channel (1, 2, 3, ...); with
    anisotropy, channels 5-8 are the perpendicular channels.

Very large simulations are split into <name>_part01.sim, _part02.sim, ...:
select all parts together when loading them in PAM.

Next to every file PAMsim writes <name>_1_info.txt, a text summary of the
parameters (duration, microtime range, background, FRET, crosstalk, direct
excitation, and D, concentration, brightness and lifetime of every species).

Units: nm (sizes), um^2/s (D), kHz (brightness, noise, frequency),
ns (lifetime, microtime range), ps (IRF width), 1/ms (dynamic rates)."""


def _f(text, name):
    try:
        return float(str(text).strip())
    except ValueError:
        raise ValueError(f"'{name}' must be a number (got '{text}')") from None


def _fmt(v):
    return f"{float(v):g}"


def config_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, "pamsim")
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------
# presets and checks (no Tk needed - also used by the tests)
# --------------------------------------------------------------------------
def _sp(name, brightness, D, N, color, **kw):
    b = list(brightness) + [0.0] * (4 - len(brightness))
    return Species(name=name, color=color, D=D, N=N, brightness=b, LT=[4, 3, 2, 2], **kw)


def presets():
    """Ready-made setups: name -> SimSettings."""
    out = {}
    out["1-colour FCS"] = SimSettings(name="fcs", sim_time=30, frames=1, species=[_sp("dye", [100], 100, 50, 1)])
    out["2-colour FCCS (PIE)"] = SimSettings(name="fccs_2c", sim_time=30, frames=1, mi_range=50, species=[
        _sp("green-red complex", [100, 70], 50, 300, 2),
        _sp("green only", [100, 0], 50, 200, 2),
        _sp("red only", [0, 70], 50, 200, 2)])
    out["3-colour FCCS (PIE)"] = SimSettings(name="fccs_3c", sim_time=30, frames=1, mi_range=60, species=[
        _sp("triple complex", [100, 70, 50], 35, 300, 3),
        _sp("blue-green", [100, 70, 0], 35, 200, 3),
        _sp("green-red", [0, 70, 50], 35, 200, 3),
        _sp("blue-red", [100, 0, 50], 35, 200, 3)])
    R = np.zeros((4, 4)); R[1, 0] = 50.0
    out["smFRET bursts (PIE, IRF)"] = SimSettings(
        name="smfret", sim_time=60, frames=1, mi_range=50, use_irf=True, irf_width=200,
        species=[_sp("FRET species", [200, 150], 100, 3, 2, fret=2, R=R)])
    return out


def _emission_volume(p_max, wr, wz, is3d):
    """Integral of min(1, p_max * exp(-u)) over the focus, u = 2r^2/wr^2 (+ 2z^2/wz^2).

    p_max = brightness / sampling frequency (excitation probability per tick in
    the focus centre).  Photons are only generated where p > 1e-4 (as in the
    C++ kernel).  Saturation (p_max > 1) is included, so this also predicts the
    count rate of over-bright molecules.
    """
    if p_max <= 1e-4:
        return 0.0
    u_max = np.log(p_max / 1e-4)
    u = np.linspace(0.0, u_max, 4000)
    p = np.minimum(1.0, p_max * np.exp(-u))
    dv = (2 * np.pi * wr * wr * wz / 2 ** 1.5 * np.sqrt(u)) if is3d else np.full_like(u, np.pi * wr * wr / 2)
    return float(np.trapezoid(p * dv, u)) if hasattr(np, "trapezoid") else float(np.trapz(p * dv, u))


def _add_expected_rates(rates, sp, freq, vol_nm3, is3d):
    """Add the expected count rate per channel [kHz] of one species, incl. saturation, crosstalk and
    direct excitation (FRET ignored): every laser excites every dye in its own focus (ExP[dye, laser]),
    and the photons of a dye are spread over the channels like in the kernel (Cross, DetP)."""
    exc = sp.excitation_matrix(freq)
    cross = _crosstalk(sp)
    for d in range(sp.color):
        with np.errstate(divide="ignore", invalid="ignore"):
            to_chan = np.nan_to_num(cross[:, d] / cross[:, d].sum() * sp.DetP[:, d], nan=0.0, posinf=0.0)
        for laser in range(sp.color):
            p = float(exc[d, laser])
            wr, wz = float(sp.wr[laser]), float(sp.wz[laser])
            if p > 0 and wr > 0 and wz > 0:
                rates += sp.N / vol_nm3 * freq * _emission_volume(p, wr, wz, is3d) * to_chan


def check_settings(s: SimSettings, folder=None):
    """Plausibility checks shown in the GUI: list of (level, message)."""
    msgs = []
    freq = float(s.freq)
    advanced = s.advanced
    if folder is not None and not os.path.isdir(folder):
        msgs.append(("error", "Output folder does not exist."))
    if freq <= 0 or s.sim_time <= 0:
        msgs.append(("error", "Sampling frequency and simulation time must be > 0."))
        return msgs
    box = np.asarray(s.box_size, float)
    is3d = box[2] > 0
    vol_nm3 = np.prod(box if is3d else box[:2])
    rates = np.zeros(4)
    for sp in s.species:
        bright = species_brightness(sp, freq)
        _add_expected_rates(rates, sp, freq, vol_nm3, is3d)
        for c in range(sp.color):
            b = float(bright[c])
            if b <= 0:
                continue
            ratio = b / freq
            if ratio >= 1:
                msgs.append(("error", f"{sp.name}: brightness {b:g} kHz (colour {c + 1}) >= sampling frequency "
                                      f"{freq:g} kHz. Excitation saturates completely: D and c will be wrong. "
                                      f"Lower the brightness or raise the frequency."))
            elif ratio > 0.1:
                msgs.append(("warn", f"{sp.name}: brightness {b:g} kHz (colour {c + 1}) is {100 * ratio:.0f}% of "
                                     f"the sampling frequency; the focus starts to saturate (keep < 10%)."))
        if sp.D > 0:
            step = np.sqrt(2 * sp.D * 1e6 / (freq * 1e3))
            wr_min = float(np.min(sp.wr[:sp.color]))
            if wr_min > 0 and step > 0.1 * wr_min:
                msgs.append(("warn", f"{sp.name}: one diffusion step is {step:.0f} nm (> 10% of wr = {wr_min:g} nm). "
                                     f"Raise the sampling frequency for accurate fast diffusion."))
        wr_max = float(np.max(sp.wr[:sp.color])); wz_max = float(np.max(sp.wz[:sp.color]))
        if min(box[:2]) < 8 * wr_max or (is3d and box[2] < 3 * wz_max):
            msgs.append(("warn", f"{sp.name}: the box is small compared with the focus "
                                 f"(use >= 8 wr laterally and >= 3 wz axially)."))
    if s.use_noise:
        rates += np.asarray(s.noise, float)
    n_ph = rates.sum() * 1e3 * s.sim_time
    mem_gb = n_ph * 12 / 1e9
    chans = ", ".join(f"{r:.3g}" for r in rates[:max(sp.color for sp in s.species)])
    msgs.append(("info", f"Expected count rates: {chans} kHz  ->  ~{n_ph / 1e6:.3g} M photons, "
                         f"~{max(mem_gb, 0.001):.2g} GB of memory per file."))
    if mem_gb > 8:
        msgs.append(("warn", "Very large result: shorten the time and use 'Number of files' instead "
                             "(each file is simulated and saved on its own)."))
    if n_ph * 10 > 3.5e9:
        msgs.append(("info", "The result will be saved in several parts (<name>_partNN.sim); "
                             "load all parts together in PAM."))
    if advanced:
        msgs.append(("info", "Advanced kernel (IRF / anisotropy / distance width / linker / dynamics): "
                             "species are states of one molecule; focus and map from species 1."))
    if any(sp.fret == 3 for sp in s.species) and (len(s.species) < 2 or s.dynamic_rates is None):
        msgs.append(("warn", "Dynamic FRET needs >= 2 species and non-zero rates (FRET / dynamics tab)."))
    if any(sp.barrier != 1 for sp in s.species) and s.maps is None:
        msgs.append(("warn", "A map type is selected but no map is loaded: free diffusion will be used."))
    if not any(m[0] in ("warn", "error") for m in msgs):
        msgs.insert(0, ("ok", "Settings look good."))
    return msgs


# --------------------------------------------------------------------------
# small widgets
# --------------------------------------------------------------------------
class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip, self.job = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self.job = self.widget.after(450, self._show)

    def _show(self):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", background="#fffbe6", foreground="#222",
                 relief="solid", borderwidth=1, padx=6, pady=4, wraplength=460).pack()

    def _hide(self, _e=None):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


def tip(widget, key):
    if key in TIPS:
        Tooltip(widget, TIPS[key])
    return widget


class SimGUI:
    def __init__(self, root, restore=True):
        self.root = root
        root.title(f"{APP} - photon simulation for PAM")
        self.settings = presets()["1-colour FCS"]
        self.settings.seed = None
        self.sel = 0
        self.matrix_key = list(MATRICES)[0]
        self.queue = queue.Queue()
        self.cancel = None
        self.worker = None
        self.last_result = None
        self.last_files = []
        self.v = {}
        self._check_job = None
        self._loading = False
        self._setup_style()
        self._set_icon()

        outer = self._scrollable(root)
        self._build_header(outer)
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True, pady=(8, 0))
        left = ttk.Frame(body); left.grid(row=0, column=0, sticky="nsew")
        right = ttk.Frame(body); right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._build_measurement(left)
        self._build_output(left)
        self._build_species(right)
        self._build_run(right)

        state = self._read_state() if restore else None
        if state:
            self._apply_state(state)
        else:
            self._load_all()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(100, self._poll)
        self._schedule_check()
        self._fit_to_screen()

    def _scrollable(self, root):
        """Content frame inside a canvas: scrollbars appear when the screen is too small."""
        self.canvas = tk.Canvas(root, highlightthickness=0, borderwidth=0, background=self._bg())
        vs = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        hs = ttk.Scrollbar(root, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        vs.grid_remove()
        hs.grid_remove()
        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        outer = ttk.Frame(self.canvas, padding=(10, 8, 10, 10))
        win = self.canvas.create_window(0, 0, window=outer, anchor="nw")

        def resize(_e=None):
            self.canvas.configure(scrollregion=(0, 0, outer.winfo_reqwidth(), outer.winfo_reqheight()))
            # stretch the content when the window is larger than needed
            self.canvas.itemconfigure(win, width=max(outer.winfo_reqwidth(), self.canvas.winfo_width()),
                                      height=max(outer.winfo_reqheight(), self.canvas.winfo_height()))
            need_v = outer.winfo_reqheight() > self.canvas.winfo_height() + 1
            need_h = outer.winfo_reqwidth() > self.canvas.winfo_width() + 1
            (vs.grid if need_v else vs.grid_remove)()
            (hs.grid if need_h else hs.grid_remove)()
        outer.bind("<Configure>", resize)
        self.canvas.bind("<Configure>", resize)

        def wheel(e):
            if outer.winfo_reqheight() > self.canvas.winfo_height():
                self.canvas.yview_scroll(int(-e.delta / 120) if e.delta else (1 if e.num == 5 else -1), "units")
        root.bind_all("<MouseWheel>", lambda e: None if isinstance(e.widget, tk.Text) else wheel(e), add="+")
        root.bind_all("<Button-4>", wheel, add="+")
        root.bind_all("<Button-5>", wheel, add="+")
        self._outer = outer
        return outer

    def _fit_to_screen(self):
        self.root.update_idletasks()
        w = self._outer.winfo_reqwidth() + 24
        h = self._outer.winfo_reqheight() + 24
        sw = self.root.winfo_screenwidth() - 40
        sh = self.root.winfo_screenheight() - 90  # task bar and title bar
        self.root.geometry(f"{min(w, sw)}x{min(h, sh)}+10+10")
        self.root.minsize(min(w, 900), min(h, 500))

    # ------------------------------------------------------------- look
    def _setup_style(self):
        style = ttk.Style(self.root)
        try:
            import sv_ttk
            sv_ttk.set_theme("light")
            self.themed = True
        except Exception:  # noqa: BLE001 - theme is optional
            self.themed = False
            if "vista" in style.theme_names():
                style.theme_use("vista")
            elif "clam" in style.theme_names():
                style.theme_use("clam")
            style.configure("Accent.TButton", font=("TkDefaultFont", 10, "bold"))
        base = "Segoe UI" if sys.platform == "win32" else "TkDefaultFont"
        style.configure("Title.TLabel", font=(base, 17, "bold"))
        style.configure("Sub.TLabel", foreground=INK2)
        style.configure("Head.TLabel", font=(base, 10, "bold"))
        style.configure("Hint.TLabel", foreground=INK2)
        style.configure("Big.Accent.TButton", font=(base, 11, "bold"), padding=(18, 8))

    def _set_icon(self):
        try:
            self._icon = tk.PhotoImage(file=os.path.join(ASSETS, "pamsim.png"))
            self.root.iconphoto(True, self._icon)
            if sys.platform == "win32":
                self.root.iconbitmap(default=os.path.join(ASSETS, "pamsim.ico"))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------- layout
    def _var(self, key, value=""):
        self.v[key] = tk.StringVar(value=value)
        self.v[key].trace_add("write", lambda *a: self._schedule_check())
        return self.v[key]

    def _row(self, parent, row, label, keys, unit="", width=7, tipkey=None):
        lab = ttk.Label(parent, text=label)
        lab.grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        tip(lab, tipkey)
        for i, k in enumerate(keys):
            e = ttk.Entry(parent, textvariable=self._var(k), width=width)
            e.grid(row=row, column=1 + i, padx=1, pady=2, sticky="w")
            tip(e, tipkey)
        ttk.Label(parent, text=unit, style="Hint.TLabel").grid(row=row, column=4, sticky="w", padx=(4, 0))

    def _build_header(self, parent):
        h = ttk.Frame(parent)
        h.pack(fill="x")
        try:
            self._logo = tk.PhotoImage(file=os.path.join(ASSETS, "pamsim.png")).subsample(5, 5)
            ttk.Label(h, image=self._logo).pack(side="left", padx=(0, 10))
        except Exception:  # noqa: BLE001
            pass
        t = ttk.Frame(h)
        t.pack(side="left")
        ttk.Label(t, text=APP, style="Title.TLabel").pack(anchor="w")
        ttk.Label(t, text="Fast photon simulation for PAM  -  writes .sim files for Load TCSPC data",
                  style="Sub.TLabel").pack(anchor="w")
        r = ttk.Frame(h)
        r.pack(side="right")
        ttk.Button(r, text="Help", command=self._help).pack(side="right", padx=(6, 0))
        ttk.Button(r, text="Save setup...", command=self._save_setup).pack(side="right", padx=(6, 0))
        ttk.Button(r, text="Open setup...", command=self._load_setup).pack(side="right", padx=(6, 0))
        ttk.Button(r, text="Load from planner...", command=self._open_planner).pack(side="right", padx=(6, 0))
        ttk.Separator(r, orient="vertical").pack(side="right", fill="y", padx=8)
        ttk.Button(r, text="Apply", command=self._apply_preset).pack(side="right", padx=(6, 0))
        self.preset_cb = ttk.Combobox(r, values=list(presets()), state="readonly", width=24)
        self.preset_cb.set("Start from a preset...")
        self.preset_cb.pack(side="right")

    def _build_measurement(self, parent):
        ttk.Label(parent, text="1  Measurement", style="Head.TLabel").pack(anchor="w", pady=(0, 4))
        g = ttk.LabelFrame(parent, text="General", padding=8)
        g.pack(fill="x")
        self._row(g, 0, "Box size x, y, z", ["bs0", "bs1", "bs2"], "nm", width=6, tipkey="bs")
        self._row(g, 1, "Sampling frequency", ["freq"], "kHz", tipkey="freq")
        self._row(g, 2, "Simulation time", ["time"], "s", tipkey="time")
        self._row(g, 3, "Frames", ["frames"], tipkey="frames")
        self._row(g, 4, "Microtime range", ["mirange"], "ns", tipkey="mirange")
        self._row(g, 5, "Seed", ["seed"], "empty = random", tipkey="seed")

        s = ttk.LabelFrame(parent, text="Scanning", padding=8)
        s.pack(fill="x", pady=(8, 0))
        lab = ttk.Label(s, text="Scan type"); lab.grid(row=0, column=0, sticky="w", padx=(0, 6)); tip(lab, "scan")
        self.scan_cb = ttk.Combobox(s, values=SCAN_TYPES, state="readonly", width=26)
        self.scan_cb.grid(row=0, column=1, columnspan=3, sticky="w", pady=2)
        self.scan_cb.bind("<<ComboboxSelected>>", lambda e: self._update_scan_state())
        self.scan_rows = ttk.Frame(s)
        self.scan_rows.grid(row=1, column=0, columnspan=5, sticky="w")
        self._row(self.scan_rows, 0, "Pixels / lines", ["px0", "px1"], width=7, tipkey="px")
        self._row(self.scan_rows, 1, "Pixel size x, y", ["sz0", "sz1"], "nm", width=7, tipkey="sz")
        self._row(self.scan_rows, 2, "Pixel / line time", ["t0", "t1"], "us, ms", width=7, tipkey="tpx")

        n = ttk.LabelFrame(parent, text="Background", padding=8)
        n.pack(fill="x", pady=(8, 0))
        self.use_noise = tk.BooleanVar()
        self.use_noise.trace_add("write", lambda *a: self._schedule_check())
        tip(ttk.Checkbutton(n, text="Add background per channel [kHz]", variable=self.use_noise), "noise").grid(
            row=0, column=0, columnspan=4, sticky="w")
        for i in range(4):
            tip(ttk.Entry(n, textvariable=self._var(f"noise{i}"), width=6), "noise").grid(row=1, column=i, padx=1, pady=(4, 0))

    def _build_species(self, parent):
        ttk.Label(parent, text="2  Molecules", style="Head.TLabel").pack(anchor="w", pady=(0, 4))
        top = ttk.Frame(parent)
        top.pack(fill="x")
        lf = ttk.LabelFrame(top, text="Species", padding=8)
        lf.pack(side="left", fill="y")
        self.sp_list = tk.Listbox(lf, height=6, width=20, exportselection=False, activestyle="none",
                                  borderwidth=1, relief="solid", highlightthickness=0,
                                  selectbackground="#2a78d6", selectforeground="white")
        self.sp_list.grid(row=0, column=0, columnspan=3)
        self.sp_list.bind("<<ListboxSelect>>", self._on_select_species)
        ttk.Button(lf, text="Add", width=6, command=self._add_species).grid(row=1, column=0, pady=(6, 0))
        ttk.Button(lf, text="Copy", width=6, command=self._copy_species).grid(row=1, column=1, pady=(6, 0), padx=2)
        ttk.Button(lf, text="Delete", width=6, command=self._delete_species).grid(row=1, column=2, pady=(6, 0))

        pf = ttk.LabelFrame(top, text="Selected species", padding=8)
        pf.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.sv = {k: tk.StringVar() for k in ("name", "D", "N")}
        for var in self.sv.values():
            var.trace_add("write", lambda *a: self._schedule_check())
        ttk.Label(pf, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(pf, textvariable=self.sv["name"], width=22).grid(row=0, column=1, columnspan=2, sticky="w", pady=2)
        tip(ttk.Label(pf, text="Colours"), "colors").grid(row=0, column=3, sticky="e", padx=(10, 4))
        self.color_cb = ttk.Combobox(pf, values=["1", "2", "3", "4"], state="readonly", width=4)
        self.color_cb.grid(row=0, column=4, sticky="w")
        self.color_cb.bind("<<ComboboxSelected>>", lambda e: (self._update_color_rows(), self._schedule_check()))
        tip(ttk.Label(pf, text="D"), "D").grid(row=1, column=0, sticky="w")
        tip(ttk.Entry(pf, textvariable=self.sv["D"], width=9), "D").grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(pf, text="um^2/s", style="Hint.TLabel").grid(row=1, column=2, sticky="w")
        tip(ttk.Label(pf, text="Molecules N"), "N").grid(row=1, column=3, sticky="e", padx=(10, 4))
        tip(ttk.Entry(pf, textvariable=self.sv["N"], width=9), "N").grid(row=1, column=4, sticky="w")
        self.conc = ttk.Label(pf, text="", style="Hint.TLabel")
        self.conc.grid(row=1, column=5, sticky="w", padx=6)
        self.sv["N"].trace_add("write", lambda *a: self._update_conc())
        tip(ttk.Label(pf, text="FRET"), "fret").grid(row=2, column=0, sticky="w")
        self.fret_cb = ttk.Combobox(pf, values=FRET_TYPES, state="readonly", width=14)
        self.fret_cb.grid(row=2, column=1, columnspan=2, sticky="w", pady=2)
        self.fret_cb.bind("<<ComboboxSelected>>", lambda e: (self._update_dyn_table(), self._schedule_check()))
        tip(ttk.Label(pf, text="Map type"), "map").grid(row=2, column=3, sticky="e", padx=(10, 4))
        self.barrier_cb = ttk.Combobox(pf, values=BARRIERS, state="readonly", width=30)
        self.barrier_cb.grid(row=2, column=4, columnspan=2, sticky="w")
        self.barrier_cb.bind("<<ComboboxSelected>>", lambda e: self._schedule_check())
        self.use_lt = tk.BooleanVar()
        ttk.Checkbutton(pf, text="Simulate fluorescence lifetime", variable=self.use_lt).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))

        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True, pady=(8, 0))
        self.notebook = nb

        cf = ttk.Frame(nb, padding=8)
        nb.add(cf, text="Colours & focus")
        for j, (name, unit) in enumerate(COLOR_COLUMNS):
            lab = ttk.Label(cf, text=f"{name}\n[{unit}]" if unit else f"{name}\n", justify="center")
            lab.grid(row=0, column=j + 1, padx=1)
            if j == 0:
                tip(lab, "brightness")
        self.cvars = [[tk.StringVar() for _ in COLOR_COLUMNS] for _ in range(4)]
        self.cent = []
        for i in range(4):
            dot = tk.Label(cf, text="●", foreground=PALETTE[i])
            dot.grid(row=i + 1, column=0, sticky="w")
            ttk.Label(cf, text=f" Colour {i + 1}").grid(row=i + 1, column=0, sticky="w", padx=(14, 4))
            row = []
            for j in range(len(COLOR_COLUMNS)):
                self.cvars[i][j].trace_add("write", lambda *a: self._schedule_check())
                e = ttk.Entry(cf, textvariable=self.cvars[i][j], width=6)
                e.grid(row=i + 1, column=j + 1, padx=1, pady=1)
                if j == 0:
                    tip(e, "brightness")
                row.append(e)
            self.cent.append(row)
        ttk.Label(cf, text="Brightness = count rate of one molecule in the focus centre (0 = no dye of this colour).\n"
                           "wr / wz = 1/e² radii of the focus.  r0, rho, r_inf are used only with anisotropy on.",
                  style="Hint.TLabel").grid(row=6, column=0, columnspan=11, sticky="w", pady=(8, 0))

        mf = ttk.Frame(nb, padding=8)
        nb.add(mf, text="Excitation / crosstalk / detection")
        self.mat_cb = ttk.Combobox(mf, values=list(MATRICES), state="readonly", width=44)
        self.mat_cb.current(0)
        self.mat_cb.grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 6))
        self.mat_cb.bind("<<ComboboxSelected>>", self._on_matrix_change)
        self.mvars = [[tk.StringVar() for _ in range(4)] for _ in range(4)]
        self.mrow_lbl = [ttk.Label(mf, text="") for _ in range(4)]
        self.mcol_lbl = [ttk.Label(mf, text="") for _ in range(4)]
        for j in range(4):
            self.mcol_lbl[j].grid(row=1, column=j + 1)
        for i in range(4):
            self.mrow_lbl[i].grid(row=i + 2, column=0, sticky="w", padx=(0, 6))
            for j in range(4):
                ttk.Entry(mf, textvariable=self.mvars[i][j], width=8).grid(row=i + 2, column=j + 1, padx=1, pady=1)
        self.mat_note = ttk.Label(mf, text="", style="Hint.TLabel", wraplength=560)
        self.mat_note.grid(row=6, column=0, columnspan=5, sticky="w", pady=(8, 0))

        ff = ttk.Frame(nb, padding=8)
        nb.add(ff, text="FRET & dynamics")
        self.fvars = {}
        pairs = [(1, 0), (2, 0), (3, 0), (2, 1), (3, 1), (3, 2)]
        for c, (title, key) in enumerate((("Foerster radius R0", "R0"), ("Distance R", "R"),
                                          ("Distance width sigma", "distance_width"))):
            pad = 0 if c == 0 else 14
            ttk.Label(ff, text=title, style="Head.TLabel").grid(row=0, column=2 * c, columnspan=2, sticky="w", padx=(pad, 0))
            for r, (a, d) in enumerate(pairs):
                ttk.Label(ff, text=f"{d + 1} → {a + 1}").grid(row=r + 1, column=2 * c, sticky="e", padx=(pad, 4))
                var = tk.StringVar()
                ttk.Entry(ff, textvariable=var, width=7).grid(row=r + 1, column=2 * c + 1, pady=1)
                self.fvars[(key, a, d)] = var
        ttk.Label(ff, text="donor → acceptor (colour numbers); R0, R, sigma and linker width share one unit (e.g. Å)",
                  style="Hint.TLabel").grid(row=8, column=0, columnspan=6, sticky="w", pady=(6, 0))
        self.dyn_frame = ttk.LabelFrame(ff, text="Dynamic interconversion rates [1/ms], from (row) → to (column)", padding=6)
        self.dyn_frame.grid(row=9, column=0, columnspan=6, sticky="we", pady=(8, 0))
        self.dyn_vars = []
        self.dyn_values = np.zeros((1, 1))

        af = ttk.Frame(nb, padding=8)
        nb.add(af, text="Advanced")
        self._build_advanced(af)

    def _build_advanced(self, parent):
        a = ttk.LabelFrame(parent, text="Lifetime & FRET extras (switch to the DifSim_ani kernel)", padding=8)
        a.pack(fill="x", anchor="w")
        self.use_irf = tk.BooleanVar(); self.use_aniso = tk.BooleanVar()
        self.use_fw = tk.BooleanVar(); self.use_lw = tk.BooleanVar()
        for var in (self.use_irf, self.use_aniso, self.use_fw, self.use_lw):
            var.trace_add("write", lambda *a: self._schedule_check())
        ttk.Checkbutton(a, text="IRF, width [ps]", variable=self.use_irf).grid(row=0, column=0, sticky="w")
        ttk.Entry(a, textvariable=self._var("irf"), width=8).grid(row=0, column=1, pady=2)
        ttk.Checkbutton(a, text="Anisotropy (channels 1-4 parallel, 5-8 perpendicular)", variable=self.use_aniso).grid(
            row=1, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(a, text="Distance width, redraw every [ms]", variable=self.use_fw).grid(row=2, column=0, sticky="w")
        ttk.Entry(a, textvariable=self._var("hetupd"), width=8).grid(row=2, column=1, pady=2)
        ttk.Checkbutton(a, text="Linker width", variable=self.use_lw).grid(row=3, column=0, sticky="w")
        ttk.Entry(a, textvariable=self._var("linker"), width=8).grid(row=3, column=1, pady=2)

        m = ttk.LabelFrame(parent, text="Barrier / quenching map (1 pixel = 1 nm, map[x, y])", padding=8)
        m.pack(fill="x", pady=(8, 0), anchor="w")
        self.map_label = ttk.Label(m, text="no map loaded", width=40)
        self.map_label.grid(row=0, column=0, sticky="w")
        ttk.Button(m, text="Load map...", command=self._load_map).grid(row=0, column=1, padx=4)
        ttk.Button(m, text="Clear", command=self._clear_map).grid(row=0, column=2)

        p = ttk.LabelFrame(parent, text="Performance", padding=8)
        p.pack(fill="x", pady=(8, 0), anchor="w")
        self.ff = tk.BooleanVar(value=True)
        tip(ttk.Checkbutton(p, text="Fast-forward far from the focus", variable=self.ff), "ff").grid(row=0, column=0, sticky="w")
        tip(ttk.Label(p, text="CPU cores"), "threads").grid(row=0, column=1, padx=(14, 4))
        tip(ttk.Entry(p, textvariable=self._var("threads", str(os.cpu_count() or 1)), width=5), "threads").grid(row=0, column=2)
        self.reset_bleach = tk.BooleanVar()
        ttk.Checkbutton(p, text="Unbleach dyes at every frame (exactly like Sim.m)", variable=self.reset_bleach).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

    def _build_output(self, parent):
        ttk.Label(parent, text="3  Output", style="Head.TLabel").pack(anchor="w", pady=(10, 4))
        o = ttk.LabelFrame(parent, text="Files", padding=8)
        o.pack(fill="x")
        tip(ttk.Label(o, text="Folder"), "folder").grid(row=0, column=0, sticky="w", padx=(0, 6))
        fe = ttk.Entry(o, textvariable=self._var("folder", os.path.expanduser("~")), width=30)
        fe.grid(row=0, column=1, columnspan=2, sticky="we", pady=2)
        tip(fe, "folder")
        ttk.Button(o, text="Browse...", command=self._choose_folder).grid(row=0, column=3, padx=(4, 0))
        tip(ttk.Label(o, text="File name"), "name").grid(row=1, column=0, sticky="w")
        ttk.Entry(o, textvariable=self._var("name"), width=18).grid(row=1, column=1, sticky="w", pady=2)
        tip(ttk.Label(o, text="Number of files"), "nfiles").grid(row=2, column=0, sticky="w")
        ttk.Entry(o, textvariable=self._var("nfiles", "1"), width=5).grid(row=2, column=1, sticky="w", pady=2)
        ttk.Label(o, text="Format").grid(row=3, column=0, sticky="w")
        self.fmt = ttk.Combobox(o, values=[".sim (PAM)", ".npz (numpy)", "both"], state="readonly", width=12)
        self.fmt.current(0)
        self.fmt.grid(row=3, column=1, sticky="w", pady=2)
        self.save_setup = tk.BooleanVar(value=True)
        ttk.Checkbutton(o, text="Save the setup next to the data", variable=self.save_setup).grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(2, 0))
        self.own_folder = tk.BooleanVar(value=True)
        tip(ttk.Checkbutton(o, text="Own folder per simulation (named after the file name)",
                            variable=self.own_folder), "ownfolder").grid(row=5, column=0, columnspan=4, sticky="w")
        o.columnconfigure(2, weight=1)

    def _build_run(self, parent):
        strip = ttk.Frame(parent)
        strip.pack(fill="both", expand=True, pady=(10, 0))
        nb = ttk.Notebook(strip)
        nb.pack(side="left", fill="both", expand=True)
        self.info_nb = nb
        cf = ttk.Frame(nb, padding=6)
        nb.add(cf, text="Check")
        lf = ttk.Frame(nb, padding=6)
        nb.add(lf, text="Log")
        font = ("Segoe UI", 9) if sys.platform == "win32" else ("TkDefaultFont", 9)
        self.check_text = tk.Text(cf, height=8, width=60, wrap="word", borderwidth=0, highlightthickness=0,
                                  font=font, background=self._bg(), cursor="arrow")
        self.check_text.pack(fill="both", expand=True)
        for lvl, col in LEVEL_COLORS.items():
            self.check_text.tag_configure(lvl, foreground=col)
        self.check_text.tag_configure("body", foreground="#222222", spacing3=4)
        self.check_text.configure(state="disabled")
        self.log = tk.Text(lf, height=8, width=60, wrap="word", state="disabled", borderwidth=0, highlightthickness=0,
                           font=("Consolas", 8) if sys.platform == "win32" else ("TkFixedFont", 8),
                           background=self._bg())
        self.log.pack(fill="both", expand=True)

        run = ttk.Frame(strip, padding=(12, 4, 0, 0))
        run.pack(side="left", fill="y")
        self.start_btn = ttk.Button(run, text="\u25b6  Start simulation", style="Big.Accent.TButton",
                                    command=self._start_stop, width=20)
        self.start_btn.pack(fill="x")
        self.progress = ttk.Progressbar(run, mode="determinate", maximum=1.0, length=230)
        self.progress.pack(fill="x", pady=(10, 2))
        self.status = ttk.Label(run, text="Ready.", style="Hint.TLabel", wraplength=240)
        self.status.pack(anchor="w")
        b2 = ttk.Frame(run)
        b2.pack(fill="x", side="bottom")
        self.plot_btn = ttk.Button(b2, text="Plot result", command=self._plot, state="disabled")
        self.plot_btn.pack(side="left", expand=True, fill="x")
        self.open_btn = ttk.Button(b2, text="Open folder", command=self._open_folder)
        self.open_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

    def _bg(self):
        try:
            return ttk.Style(self.root).lookup("TFrame", "background") or "#fafafa"
        except Exception:  # noqa: BLE001
            return "#fafafa"

    # ------------------------------------------------------------- model <-> widgets
    def _load_all(self):
        self._loading = True
        try:
            self._load_general()
            self.sel = min(self.sel, len(self.settings.species) - 1)
            self._refresh_species_list()
            self._load_species()
        finally:
            self._loading = False
        self._schedule_check()

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
        self.dyn_values = np.array(s.dynamic_rates, float) if s.dynamic_rates is not None else np.zeros((1, 1))
        self._show_map()
        self._update_scan_state()

    def _store_general(self):
        s = self.settings
        s.box_size = np.array([_f(self.v[f"bs{i}"].get(), "box size") for i in range(3)])
        s.freq = _f(self.v["freq"].get(), "sampling frequency")
        s.sim_time = _f(self.v["time"].get(), "simulation time")
        s.frames = max(1, int(_f(self.v["frames"].get(), "frames")))
        seed = self.v["seed"].get().strip()
        s.seed = int(_f(seed, "seed")) if seed else None
        s.mi_range = _f(self.v["mirange"].get(), "microtime range")
        s.scan_type = self.scan_cb.current() + 1
        s.pixels = np.array([_f(self.v[f"px{i}"].get(), "pixels") for i in range(2)])
        s.pixel_size = np.array([_f(self.v[f"sz{i}"].get(), "pixel size") for i in range(2)])
        s.times = np.array([_f(self.v["t0"].get(), "pixel time"), _f(self.v["t1"].get(), "line time"), s.times[2]])
        s.use_noise = self.use_noise.get()
        s.noise = np.array([_f(self.v[f"noise{i}"].get(), "background") for i in range(4)])
        s.use_irf = self.use_irf.get(); s.irf_width = _f(self.v["irf"].get(), "IRF width")
        s.use_aniso = self.use_aniso.get()
        s.use_fret_width = self.use_fw.get(); s.heterogeneity_update = _f(self.v["hetupd"].get(), "update time")
        s.use_linker_width = self.use_lw.get(); s.linker_width = _f(self.v["linker"].get(), "linker width")
        s.fast_forward = self.ff.get(); s.reset_bleaching_each_frame = self.reset_bleach.get()
        s.n_threads = max(1, int(_f(self.v["threads"].get(), "CPU cores")))
        s.name = self.v["name"].get().strip() or "simulation"
        self._store_dyn()
        n = len(s.species)
        dv = self.dyn_values[:n, :n]
        s.dynamic_rates = dv.copy() if dv.shape == (n, n) and np.any(dv) else None

    def _load_species(self):
        sp = self.settings.species[self.sel]
        self.sv["name"].set(sp.name); self.sv["D"].set(_fmt(sp.D)); self.sv["N"].set(str(int(sp.N)))
        self.color_cb.current(sp.color - 1)
        self.fret_cb.current(sp.fret - 1)
        self.barrier_cb.current(sp.barrier - 1)
        self.use_lt.set(bool(sp.use_lt))
        bright = species_brightness(sp, self.settings.freq)
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
        if self.sp_list.size() > self.sel and self.sp_list.get(self.sel) != sp.name:
            self.sp_list.delete(self.sel)
            self.sp_list.insert(self.sel, sp.name)
            self.sp_list.selection_set(self.sel)

    def _load_matrix(self):
        attr, rlab, clab = MATRICES[self.matrix_key]
        m = getattr(self.settings.species[self.sel], attr)
        for i in range(4):
            self.mrow_lbl[i].configure(text=f"{rlab} {i + 1}")
            self.mcol_lbl[i].configure(text=f"{clab} {i + 1}")
            for j in range(4):
                self.mvars[i][j].set(_fmt(m[i, j]))
        notes = {"ExP": "Excitation probability per time step in the focus centre. The diagonal is set by the Brightness "
                        "column; off-diagonal entries are direct excitation of a dye by another laser.",
                 "Cross": "Relative crosstalk of a dye's photons into other channels (the diagonal is always 1).",
                 "DetP": "Probability (0..1) that an emitted photon of a dye is detected in a channel.",
                 "BlP": "Probability per emitted photon that the dye bleaches (it recovers when leaving the box)."}
        self.mat_note.configure(text=notes[attr])

    def _store_matrix(self):
        attr, _, _ = MATRICES[self.matrix_key]
        sp = self.settings.species[self.sel]
        setattr(sp, attr, np.array([[_f(self.mvars[i][j].get(), attr) for j in range(4)] for i in range(4)]))

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

    def _update_scan_state(self):
        point = self.scan_cb.current() in (0, 3)
        if point:
            self.scan_rows.grid_remove()
        else:
            self.scan_rows.grid()

    def _update_conc(self):
        try:
            n = float(self.sv["N"].get())
            bs = [float(self.v[f"bs{i}"].get()) for i in range(3)]
            if bs[2] > 0:
                self.conc.configure(text=f"= {n / np.prod(bs) / 1e-24 / 6.022e23 / 1e-9:.3g} nM")
            else:
                self.conc.configure(text=f"= {n / (bs[0] * bs[1]) * 1e6:.3g} per um^2")
        except (ValueError, ZeroDivisionError, KeyError):
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
        dynamic = any(s.fret == 3 for s in self.settings.species) or self.fret_cb.current() == 2
        if not dynamic or n < 2:
            ttk.Label(self.dyn_frame, text="Set FRET to 'Dynamic FRET' and add >= 2 species (each species is one state).",
                      style="Hint.TLabel").grid(row=0, column=0)
            self.dyn_vars = []
            return
        names = [s.name for s in self.settings.species]
        self.dyn_vars = [[tk.StringVar(value=_fmt(self.dyn_values[i, j])) for j in range(n)] for i in range(n)]
        for j in range(n):
            ttk.Label(self.dyn_frame, text=names[j][:12]).grid(row=0, column=j + 1)
        for i in range(n):
            ttk.Label(self.dyn_frame, text=names[i][:12]).grid(row=i + 1, column=0, sticky="w")
            for j in range(n):
                e = ttk.Entry(self.dyn_frame, textvariable=self.dyn_vars[i][j], width=7)
                e.grid(row=i + 1, column=j + 1, padx=1, pady=1)
                if i == j:
                    e.configure(state="disabled")

    # ------------------------------------------------------------- checks
    def _schedule_check(self):
        if self._loading or not hasattr(self, "check_text"):
            return
        if self._check_job:
            self.root.after_cancel(self._check_job)
        self._check_job = self.root.after(350, self._run_check)

    def _run_check(self):
        self._check_job = None
        try:
            self._store_species()
            self._store_general()
            msgs = check_settings(self.settings, self.v["folder"].get().strip())
        except ValueError as err:
            msgs = [("error", str(err))]
        t = self.check_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for lvl, text in msgs:
            t.insert("end", LEVEL_ICONS[lvl] + "  ", lvl)
            t.insert("end", text + "\n", ("body",))
        t.configure(state="disabled")

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
        self._loading = True
        try:
            self._load_species()
        finally:
            self._loading = False

    def _add_species(self, copy_current=False):
        if not self._safe_store():
            return
        if copy_current:
            sp = copy.deepcopy(self.settings.species[self.sel])
        else:
            sp = Species(color=self.settings.species[self.sel].color, brightness=[100.0] * 4, D=50, N=100)
        sp.name = f"Species {len(self.settings.species) + 1}"
        self.settings.species.append(sp)
        self.sel = len(self.settings.species) - 1
        self._refresh_species_list()
        self._load_species()
        self._schedule_check()

    def _copy_species(self):
        self._add_species(copy_current=True)

    def _delete_species(self):
        if len(self.settings.species) <= 1:
            return
        del self.settings.species[self.sel]
        self.sel = max(0, self.sel - 1)
        self._refresh_species_list()
        self._load_species()
        self._schedule_check()

    # ------------------------------------------------------------- presets / files / state
    def _apply_preset(self):
        name = self.preset_cb.get()
        p = presets().get(name)
        if p is None:
            return
        if not messagebox.askyesno(APP, f"Replace the current setup with the preset '{name}'?"):
            return
        p.seed = None
        self.settings = p
        self.sel = 0
        self._load_all()
        self._log(f"preset '{name}' applied")

    def _choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.v["folder"].get() or os.path.expanduser("~"))
        if d:
            self.v["folder"].set(d)

    def _open_folder(self):
        folder = getattr(self, "_last_out_folder", None) or self.v["folder"].get().strip()
        if not os.path.isdir(folder):
            return
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as err:  # noqa: BLE001
            messagebox.showerror(APP, str(err))

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
        self._schedule_check()

    def _clear_map(self):
        self.settings.maps = None
        self._show_map()
        self._schedule_check()

    def _show_map(self, name=None):
        m = self.settings.maps
        if m is None:
            self.map_label.configure(text="no map loaded")
        else:
            self.map_label.configure(text=f"{name or 'map'}  ({' x '.join(str(x) for x in np.shape(m))})")

    def _load_setup(self):
        path = filedialog.askopenfilename(filetypes=[("Setup (PAMsim or Sim.m JSON)", "*.json"), ("All", "*.*")])
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
        self._load_all()
        self._log(f"loaded setup {path}")

    def _save_setup(self):
        try:
            self._store_species(); self._store_general()
        except ValueError as err:
            messagebox.showerror("Invalid value", str(err)); return
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile=self.settings.name + ".json",
                                            filetypes=[("Setup", "*.json")])
        if path:
            save_setup(self.settings, path)
            self._log(f"saved setup {path}")

    def _state_path(self):
        return os.path.join(config_dir(), "last_session.json")

    def _read_state(self):
        try:
            with open(self._state_path()) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return None

    def _apply_state(self, state):
        try:
            self.settings = SimSettings.from_dict(state["setup"])
        except Exception:  # noqa: BLE001 - fall back to the default setup
            pass
        self.sel = 0
        self._load_all()
        for key in ("folder", "nfiles", "threads"):
            if key in state:
                self.v[key].set(str(state[key]))
        if state.get("format") in (0, 1, 2):
            self.fmt.current(state["format"])
        self.save_setup.set(bool(state.get("save_json", True)))
        self.own_folder.set(bool(state.get("own_folder", True)))

    def _on_close(self):
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno(APP, "A simulation is running. Stop it and quit?"):
                return
            self.cancel.set()
        try:
            self._store_species(); self._store_general()
            s = copy.copy(self.settings); s.maps = None
            state = {"setup": s.to_dict(), "folder": self.v["folder"].get(), "nfiles": self.v["nfiles"].get(),
                     "threads": self.v["threads"].get(), "format": self.fmt.current(),
                     "save_json": self.save_setup.get(), "own_folder": self.own_folder.get()}
            with open(self._state_path(), "w") as f:
                json.dump(state, f)
        except Exception:  # noqa: BLE001 - never block closing
            pass
        self.root.destroy()

    def _help(self):
        win = tk.Toplevel(self.root)
        win.title(f"{APP} - help")
        txt = tk.Text(win, width=82, height=26, wrap="word", padx=12, pady=10, borderwidth=0)
        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=8)

    # ------------------------------------------------------------- run
    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start_stop(self):
        if self.worker is not None and self.worker.is_alive():
            self.cancel.set()
            self.status.configure(text="Stopping...")
            return
        try:
            self._store_species()
            self._store_general()
            nfiles = max(1, int(_f(self.v["nfiles"].get(), "number of files")))
        except ValueError as err:
            messagebox.showerror("Invalid value", str(err))
            return
        folder = self.v["folder"].get().strip() or os.path.expanduser("~")
        if not os.path.isdir(folder):
            messagebox.showerror("Output folder", f"The folder does not exist:\n{folder}")
            return
        errors = [m for lvl, m in check_settings(self.settings, folder) if lvl == "error"]
        if errors and not messagebox.askyesno(APP, "There are problems with the settings:\n\n- " +
                                              "\n- ".join(errors) + "\n\nSimulate anyway?"):
            return
        self._start_jobs([("", copy.deepcopy(self.settings), folder, nfiles, self.fmt.current(), self.save_setup.get())])

    def _start_jobs(self, jobs):
        """jobs: list of (label, settings, folder, number of files, format, save setup)."""
        self.cancel = threading.Event()
        self._own_folder_flag = self.own_folder.get()  # read here: Tk variables only in the main thread
        self._last_out_folder = None
        self.worker = threading.Thread(target=self._run, args=(jobs,), daemon=True)
        self.start_btn.configure(text="\u25a0  Stop")
        self.progress["value"] = 0
        self.last_files = []
        self.worker.start()

    def _run(self, jobs):
        q = self.queue
        n_total = sum(j[3] for j in jobs)
        n_done = 0
        try:
            for label, settings, folder, nfiles, fmt, save_json in jobs:
                if label:
                    q.put(("log", f"--- {label} ---"))
                for k in range(nfiles):
                    self._run_file(settings, folder, nfiles, fmt, save_json, k, label, n_done, n_total)
                    n_done += 1
            q.put(("done", "Finished."))
        except SimulationCancelled:
            q.put(("done", "Stopped."))
        except MemoryError:
            q.put(("error", "Out of memory: shorten the simulation time and use 'Number of files' instead."))
        except Exception:  # noqa: BLE001
            q.put(("error", traceback.format_exc()))

    def _run_file(self, settings, folder, nfiles, fmt, save_json, k, label, n_done, n_total):
        q = self.queue
        tag = (f"{label}: " if label else "") + f"file {k + 1}/{nfiles}"
        s = copy.deepcopy(settings)
        if settings.seed is not None:
            s.seed = settings.seed + k
        q.put(("status", f"{tag}: preparing (the very first run compiles for ~15 s)..."))

        def progress(done, total):
            q.put(("progress", (n_done + done / total) / n_total, f"{tag}: molecule {done}/{total}"))
        r = simulate(s, progress=progress, cancel=self.cancel)
        q.put(("status", f"{tag}: saving..."))
        name = safe_name(s.name)
        if self._own_folder_flag:
            folder = os.path.join(folder, name)
        os.makedirs(folder, exist_ok=True)
        self._last_out_folder = folder
        base = os.path.join(folder, f"{name}_{k + 1}")
        written = []
        if fmt in (0, 2):
            written += r.save_sim(base + ".sim")
        if fmt in (1, 2):
            written.append(r.save_npz(base + ".npz"))
        if save_json:
            save_setup(s, base + "_setup.json", seed=r.seed)
            written.append(base + "_setup.json")
        # plain-text summary of the parameters, always written next to the data
        written.append(r.save_info(base + "_info.txt", files=list(written), sim_id=label))
        rates = ", ".join(f"{x:.3g}" for x in r.count_rates_khz() if x > 0) or "0"
        q.put(("log", f"{os.path.basename(base)}: {r.elapsed:.1f} s, "
                      f"{sum(len(m) for m in r.macrotimes) / 1e6:.3g} M photons, rates [kHz] {rates}\n"
                      f"  \u2192 " + ", ".join(os.path.basename(w) for w in written)))
        q.put(("result", r, written))

    # ------------------------------------------------------------- Excel planner
    def _open_planner(self):
        path = filedialog.askopenfilename(title="Open the simulation planner",
                                          filetypes=[("Excel planner", "*.xlsx"), ("All", "*.*")])
        if not path:
            return
        if not ensure_package("openpyxl", "reading Excel planners", self.root):
            return
        try:
            from .planner import read_planner
            rows = read_planner(path)
        except Exception as err:  # noqa: BLE001
            messagebox.showerror(APP, f"Could not read the planner:\n{err}")
            return
        if not rows:
            messagebox.showinfo(APP, "No simulations found (fill in a Sim ID on the Simulations sheet).")
            return
        PlannerDialog(self, rows, os.path.basename(path))

    def _load_planner_row(self, row):
        self.settings = copy.deepcopy(row.settings)
        self.sel = 0
        self._load_all()
        self.v["name"].set(row.settings.name)
        self.v["nfiles"].set(str(row.nfiles))
        self.fmt.current(row.fmt)
        if row.folder and os.path.isdir(row.folder):
            self.v["folder"].set(row.folder)
        elif row.folder:
            self._log(f"planner folder not found on this computer, keeping {self.v['folder'].get()}:\n  {row.folder}")
        self._log(f"loaded {row.sim_id} ({row.settings.name}) from the planner"
                  + (f" with {row.extras}" if row.extras != "-" else ""))

    def _run_planner_rows(self, rows):
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo(APP, "A simulation is already running.")
            return
        fallback = self.v["folder"].get().strip()
        jobs, notes = [], []
        for row in rows:
            folder = row.folder if row.folder and os.path.isdir(row.folder) else fallback
            if folder != row.folder:
                notes.append(f"{row.sim_id}: folder not found, using {fallback}")
            jobs.append((row.sim_id, copy.deepcopy(row.settings), folder, row.nfiles, row.fmt, self.save_setup.get()))
        if not os.path.isdir(fallback) and any(j[2] == fallback for j in jobs):
            messagebox.showerror(APP, f"The output folder in PAMsim does not exist:\n{fallback}")
            return
        for n in notes:
            self._log(n)
        self._log(f"running {len(jobs)} simulation(s) from the planner: " + ", ".join(j[0] for j in jobs))
        self.info_nb.select(1)
        self._start_jobs(jobs)

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
                    self.last_files += msg[2]
                    self.plot_btn.configure(state="normal")
                elif kind == "done":
                    self.info_nb.select(1)
                    where = getattr(self, "_last_out_folder", None) or self.v["folder"].get()
                    self.status.configure(text=msg[1] + (f"  Files are in {where}" if msg[1] == "Finished." else ""))
                    if msg[1] == "Finished.":
                        self.progress["value"] = 1.0
                    self.start_btn.configure(text="▶  Start simulation")
                elif kind == "error":
                    self._log(msg[1])
                    self.info_nb.select(1)
                    self.status.configure(text="Error - see the log.")
                    self.start_btn.configure(text="▶  Start simulation")
                    messagebox.showerror(APP, msg[1].strip().splitlines()[-1])
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
        win.title(f"{APP} - last simulation")
        fig = Figure(figsize=(10, 3.8), dpi=100, facecolor="#fcfcfb")
        ax1 = fig.add_subplot(1, 2, 1); ax2 = fig.add_subplot(1, 2, 2)
        total = r.header["Frames"] * r.header["FrameTime"]
        chans = [c for c in range(min(r.n_channels, 4)) if r.macrotimes[c].size]
        binw = max(1, int(r.freq_hz * 1e-3))
        nb = int(total // binw) + 1
        for c in chans:
            tr = np.bincount((r.macrotimes[c] // binw).astype(np.int64), minlength=nb)[:nb]
            ax1.plot(np.arange(nb) * binw / r.freq_hz, tr / (binw / r.freq_hz) / 1e3, lw=0.7, alpha=0.85,
                     color=PALETTE[c], label=f"channel {c + 1}")
        ax1.set_xlabel("time [s]"); ax1.set_ylabel("count rate [kHz] (1 ms bins)")
        ax1.set_title("Intensity trace", fontsize=10)
        curves = [(c, c, f"auto {c + 1}", PALETTE[c]) for c in chans[:3]]
        extra = ["#e87ba4", "#6250d6", "#e34948"]
        pairs = [(a, b) for i, a in enumerate(chans[:3]) for b in chans[i + 1:3]]
        curves += [(a, b, f"cross {a + 1}×{b + 1}", extra[k]) for k, (a, b) in enumerate(pairs)]
        for a, b, lab, col in curves:
            try:
                lags, g, _, _ = correlate_blocks(r.macrotimes[a], r.macrotimes[b], total, n_blocks=10)
            except Exception:  # noqa: BLE001 - e.g. too few photons
                continue
            ok = lags > 0
            ax2.plot(lags[ok] / r.freq_hz, g[ok], lw=1.6, color=col, label=lab)
        ax2.set_xscale("log"); ax2.set_xlabel("lag time [s]"); ax2.set_ylabel("G(τ)")
        ax2.set_title("Correlation functions (10 sections)", fontsize=10)
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


class PlannerDialog:
    """Pick simulations from the Excel planner: load one into the editor or run several."""

    def __init__(self, gui, rows, filename):
        self.gui, self.rows = gui, rows
        w = self.win = tk.Toplevel(gui.root)
        w.title(f"{APP} - simulations in {filename}")
        w.transient(gui.root)
        ttk.Label(w, text="Select one simulation to load it into the editor, or several (Ctrl / Shift + click) "
                          "to run them one after another.", style="Hint.TLabel").pack(anchor="w", padx=10, pady=(10, 4))
        cols = ("id", "name", "species", "time", "extras", "status", "check", "purpose")
        heads = ("Sim ID", "File name", "Species", "Duration [s]", "Crosstalk / dir. exc.", "Status", "Check", "Purpose")
        widths = (60, 230, 60, 80, 150, 80, 300, 300)
        frame = ttk.Frame(w)
        frame.pack(fill="both", expand=True, padx=10)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended", height=14)
        for c, hd, wd in zip(cols, heads, widths):
            self.tree.heading(c, text=hd)
            self.tree.column(c, width=wd, anchor="w", stretch=c in ("check", "purpose"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.tag_configure("bad", foreground=LEVEL_COLORS["error"])
        self.tree.tag_configure("warn", foreground=LEVEL_COLORS["warn"])
        for i, r in enumerate(rows):
            tag = "bad" if r.check.startswith("\u2716") else "warn" if r.check.startswith("\u26a0") else ""
            self.tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                r.sim_id, r.settings.name, len(r.settings.species), f"{r.settings.sim_time:g}",
                r.extras, r.status, r.check, r.purpose))
        self.tree.bind("<Double-1>", lambda e: self._load())
        b = ttk.Frame(w)
        b.pack(fill="x", padx=10, pady=10)
        ttk.Button(b, text="Close", command=w.destroy).pack(side="right")
        ttk.Button(b, text="\u25b6  Run selected", style="Accent.TButton", command=self._run).pack(side="right", padx=6)
        ttk.Button(b, text="Load into editor", command=self._load).pack(side="right")
        ttk.Label(b, text="Files go to the planner's output folder, or to PAMsim's folder if it does not exist here.",
                  style="Hint.TLabel").pack(side="left")

    def _selected(self):
        return [self.rows[int(i)] for i in self.tree.selection()]

    def _load(self):
        sel = self._selected()
        if len(sel) != 1:
            messagebox.showinfo(APP, "Select exactly one simulation to load it into the editor.", parent=self.win)
            return
        self.gui._load_planner_row(sel[0])
        self.win.destroy()

    def _run(self):
        sel = self._selected()
        if not sel:
            messagebox.showinfo(APP, "Select the simulations to run.", parent=self.win)
            return
        bad = [r.sim_id for r in sel if r.check.startswith("\u2716")]
        if bad and not messagebox.askyesno(APP, "These simulations have red checks in the planner "
                                                "(e.g. saturated brightness):\n" + ", ".join(bad) +
                                           "\n\nRun them anyway?", parent=self.win):
            return
        self.win.destroy()
        self.gui._run_planner_rows(sel)


def safe_name(name):
    """File/folder name without characters Windows does not allow."""
    bad = '<>:"/\\|?*'
    out = "".join("_" if (ch in bad or ord(ch) < 32) else ch for ch in str(name)).strip().rstrip(".")
    return out or "simulation"


def _python_exe():
    """The console python.exe belonging to the running interpreter (also when started with pythonw)."""
    exe = sys.executable
    folder, name = os.path.split(exe)
    if name.lower() == "pythonw.exe" and os.path.exists(os.path.join(folder, "python.exe")):
        return os.path.join(folder, "python.exe")
    return exe


def ensure_package(module, purpose, parent=None):
    """Import ``module``; if it is missing, offer to pip-install it into this Python."""
    import importlib
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        pass
    exe = _python_exe()
    if not messagebox.askyesno(APP, f"The package '{module}' is needed for {purpose} but is not installed\n"
                                    f"for the Python that runs PAMsim:\n{exe}\n\nInstall it now (needs internet)?",
                               parent=parent):
        return False
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run([exe, "-m", "pip", "install", module], capture_output=True, text=True,
                             creationflags=flags, timeout=600)
    except Exception as err:  # noqa: BLE001
        messagebox.showerror(APP, f"Installation failed:\n{err}\n\nRun in a terminal:\n\"{exe}\" -m pip install {module}",
                             parent=parent)
        return False
    importlib.invalidate_caches()
    try:
        importlib.import_module(module)
        messagebox.showinfo(APP, f"'{module}' was installed.", parent=parent)
        return True
    except ImportError:
        tail = (out.stderr or out.stdout or "").strip().splitlines()[-5:]
        messagebox.showerror(APP, f"Installation of '{module}' failed:\n" + "\n".join(tail) +
                             f"\n\nRun in a terminal:\n\"{exe}\" -m pip install {module}", parent=parent)
        return False


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
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("pamsim.gui")  # own taskbar icon
        except Exception:  # noqa: BLE001
            pass
    root = tk.Tk()
    try:
        SimGUI(root)
    except Exception:  # noqa: BLE001 - started without console: show the error
        messagebox.showerror(APP, "PAMsim could not start:\n\n" + traceback.format_exc())
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
