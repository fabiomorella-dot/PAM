"""Simulation parameters.

The two dataclasses mirror ``SimData.General`` and ``SimData.Species`` from
PAM's ``Sim.m`` and use the same units and the same matrix orientation, so
values can be copied over from the MATLAB GUI one to one:

=====================  =========================================  ==========
field                  meaning                                    unit
=====================  =========================================  ==========
box_size               simulation box (BS)                        nm
freq                   sampling frequency of the random walk      kHz
sim_time               total simulated time                       s
D                      diffusion coefficient                      um^2/s
wr, wz                 1/e^2 radii of the Gaussian focus          nm
dX, dY, dZ             focus shift per laser                      nm
LT                     fluorescence lifetime per dye              ns
mi_range               microtime (TAC) range                      ns
irf_width              IRF width                                  ps
R0, R                  Foerster radius / dye distance             same unit
distance_width         width of the distance distribution         same unit
linker_width           linker fluctuation width                   same unit
noise                  background count rate per channel          kHz
dynamic_rates          interconversion rates, from (row) -> to    1/ms
heterogeneity_update   time between distance redraws              ms
=====================  =========================================  ==========

4x4 matrices (row/column meaning as in Sim.m):

* ``ExP[dye, laser]``      excitation probability per tick in the focus centre
* ``Cross[channel, dye]``  relative crosstalk (diagonal is forced to 1)
* ``DetP[channel, dye]``   detection probability
* ``BlP[em. dye, ex. dye]`` bleaching probability per emitted photon
* ``R0/R/distance_width[acceptor, donor]`` (lower triangle is used)
* ``aniso[dye, :] = (r0, rho [ns], r_inf, G)``
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, asdict
from typing import List, Optional

import numpy as np


def _arr(values, shape=None):
    a = np.array(values, dtype=float)
    if shape is not None:
        a = a.reshape(shape)
    return a


def _default_R0():
    r0 = np.zeros((4, 4))
    r0[1, 0], r0[2, 0], r0[3, 0] = 63, 51, 65
    r0[2, 1], r0[3, 1], r0[3, 2] = 68, 50, 60
    return r0


def _lower(value):
    a = np.zeros((4, 4))
    a[np.tril_indices(4, -1)] = value
    return a


@dataclass
class Species:
    name: str = "Species 1"
    color: int = 1           # number of colours / dyes used (1..4)
    fret: int = 1            # 1: no FRET, 2: static FRET, 3: dynamic FRET
    barrier: int = 1         # map type, see README (1 = free diffusion)
    D: float = 1.0           # um^2/s
    N: int = 10              # number of particles in the box
    wr: np.ndarray = field(default_factory=lambda: _arr([200] * 4))
    wz: np.ndarray = field(default_factory=lambda: _arr([1000] * 4))
    dX: np.ndarray = field(default_factory=lambda: np.zeros(4))
    dY: np.ndarray = field(default_factory=lambda: np.zeros(4))
    dZ: np.ndarray = field(default_factory=lambda: np.zeros(4))
    ExP: np.ndarray = field(default_factory=lambda: np.eye(4))
    Cross: np.ndarray = field(default_factory=lambda: np.eye(4))
    DetP: np.ndarray = field(default_factory=lambda: np.ones((4, 4)))
    BlP: np.ndarray = field(default_factory=lambda: np.zeros((4, 4)))
    use_lt: bool = True
    LT: np.ndarray = field(default_factory=lambda: _arr([4] * 4))
    R0: np.ndarray = field(default_factory=_default_R0)
    R: np.ndarray = field(default_factory=lambda: _lower(50.0))
    distance_width: np.ndarray = field(default_factory=lambda: _lower(5.0))
    aniso: np.ndarray = field(default_factory=lambda: np.tile([0.4, 1.0, 0.0, 1.0], (4, 1)))
    #: Optional molecular brightness per colour in kHz.  When given, it sets
    #: the diagonal of ExP the same way the Brightness boxes of Sim.m do.
    brightness: Optional[np.ndarray] = None

    def __post_init__(self):
        for name, shape in (("wr", (4,)), ("wz", (4,)), ("dX", (4,)), ("dY", (4,)),
                            ("dZ", (4,)), ("LT", (4,)), ("ExP", (4, 4)), ("Cross", (4, 4)),
                            ("DetP", (4, 4)), ("BlP", (4, 4)), ("R0", (4, 4)), ("R", (4, 4)),
                            ("distance_width", (4, 4)), ("aniso", (4, 4))):
            setattr(self, name, _arr(getattr(self, name), shape))
        if self.brightness is not None:
            self.brightness = _arr(np.broadcast_to(self.brightness, (4,)))
        if not 1 <= self.color <= 4:
            raise ValueError("color must be between 1 and 4")

    def excitation_matrix(self, freq_khz: float) -> np.ndarray:
        """ExP after applying ``brightness`` (Sim.m, Sim_Brightness callback)."""
        exp_ = self.ExP.copy()
        if self.brightness is None:
            return exp_
        cross = self.Cross.copy()
        np.fill_diagonal(cross, 1.0)
        for i in range(4):
            old = exp_[i, i]
            new = self.brightness[i] / freq_khz / self.DetP[i, i] * cross[:, i].sum()
            exp_[i, i] = new
            for j in range(4):
                if j != i:
                    exp_[j, i] = exp_[j, i] * new / old if old != 0 else exp_[j, i]
        return exp_


@dataclass
class SimSettings:
    name: str = "Simulation1"
    box_size: np.ndarray = field(default_factory=lambda: _arr([5000, 5000, 5000]))
    #: random seed; None draws a fresh one each run (Sim.m seeds with the clock)
    seed: Optional[int] = None
    freq: float = 1000.0     # kHz
    sim_time: float = 10.0   # s
    frames: int = 10
    scan_type: int = 1       # 1 point, 2 raster, 3 line, 4 circle (kernel treats as point)
    pixels: np.ndarray = field(default_factory=lambda: _arr([100, 100]))      # Px
    pixel_size: np.ndarray = field(default_factory=lambda: _arr([50, 50]))    # Size [nm]
    #: pixel time [us], line time [ms], frame time [s]  (Time)
    times: np.ndarray = field(default_factory=lambda: _arr([100, 10, 1]))
    use_noise: bool = False
    noise: np.ndarray = field(default_factory=lambda: _arr([0.2] * 4))        # kHz
    mi_range: float = 80.0   # ns
    use_irf: bool = False
    irf_width: float = 250.0  # ps
    use_aniso: bool = False
    use_fret_width: bool = False
    heterogeneity_update: float = 10.0  # ms
    use_linker_width: bool = False
    linker_width: float = 5.0
    dynamic_rates: Optional[np.ndarray] = None  # n_species x n_species, 1/ms
    #: Barrier / quenching map(s), indexed map[x_pixel, y_pixel] like Map(x,y)
    #: in MATLAB.  2D array, or 3D array (frames, x, y) for map types 6 and 7.
    maps: Optional[np.ndarray] = None
    species: List[Species] = field(default_factory=lambda: [Species()])

    # ---- options that do not exist in Sim.m -------------------------------
    #: combine diffusion steps while a particle is far away from the focus
    fast_forward: bool = True
    #: safety margin of the fast-forward jumps in standard deviations
    ff_z: float = 7.0
    #: reproduce Sim.m, where every frame starts with unbleached dyes
    reset_bleaching_each_frame: bool = False
    #: worker threads (None = all cores)
    n_threads: Optional[int] = None

    def __post_init__(self):
        self.box_size = _arr(self.box_size, (3,))
        self.pixels = _arr(self.pixels, (2,))
        self.pixel_size = _arr(self.pixel_size, (2,))
        self.times = _arr(self.times, (3,))
        self.noise = _arr(np.broadcast_to(self.noise, (4,)))
        if isinstance(self.species, Species):
            self.species = [self.species]

    @property
    def advanced(self) -> bool:
        """Sim.m switches to DifSim_ani when any of these features is used."""
        return bool(self.use_irf or self.use_aniso or self.use_fret_width
                    or self.use_linker_width or any(s.fret == 3 for s in self.species))

    def concentration_nM(self, species_index: int = 0) -> float:
        """Same formula as Sim.m's Update_Concentration."""
        n = self.species[species_index].N
        return n / np.prod(np.floor(self.box_size)) / 1e-24 / 6.022e23 / 1e-9

    def to_dict(self):
        d = asdict(self)
        return _to_jsonable(d)

    def save_json(self, path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, path):
        """Load either a file written by :meth:`save_json` or the JSON that
        Sim.m writes with its "save" button (``save_json`` in Sim.m)."""
        with open(path) as f:
            data = json.load(f)
        if "BS" in data or "Freq" in data:
            return cls.from_pam_dict(data)
        species = [Species(**{k: v for k, v in s.items() if k in _field_names(Species)})
                   for s in data.pop("species", [])]
        data = {k: v for k, v in data.items() if k in _field_names(cls)}
        return cls(species=species or [Species()], **data)

    @classmethod
    def from_pam_dict(cls, g):
        """Build settings from a ``SimData.General`` struct (as dict)."""
        sp = g.get("Species", [])
        if isinstance(sp, dict):
            sp = [sp]
        species = [_species_from_pam(s) for s in sp] or [Species()]
        kw = dict(
            name=g.get("Name", "Simulation1"),
            box_size=g.get("BS", [5000, 5000, 5000]),
            seed=int(g.get("Seed", 0)) if g.get("Seed") is not None else None,
            freq=g.get("Freq", 1000.0),
            sim_time=g.get("SimTime", 10.0),
            frames=int(g.get("Frames", 10)),
            scan_type=int(g.get("ScanType", 1)),
            pixels=g.get("Px", [100, 100]),
            pixel_size=g.get("Size", [50, 50]),
            times=g.get("Time", [100, 10, 1]),
            use_noise=bool(g.get("UseNoise", 0)),
            noise=g.get("Noise", [0.2] * 4),
            mi_range=g.get("MIRange", 80.0),
            irf_width=g.get("IRFwidth", g.get("IRFWidth", 250.0)),
            use_irf=bool(sp[0].get("UseIRF", 0)) if sp else False,
            heterogeneity_update=g.get("HeterogeneityUpdate", 10.0),
            linker_width=g.get("LinkerWidth", 5.0),
            species=species,
        )
        dyn = np.atleast_2d(np.array(g.get("DynamicRate", 0), dtype=float))
        if dyn.shape == (len(species), len(species)) and np.any(dyn):
            kw["dynamic_rates"] = dyn
        return cls(**kw)


def _species_from_pam(s):
    kw = dict(
        name=s.get("Name", "Species"), color=int(s.get("Color", 1)), fret=int(s.get("FRET", 1)),
        barrier=int(s.get("Barrier", 1)), D=float(s.get("D", 1.0)), N=int(s.get("N", 10)),
    )
    mapping = {"wr": "wr", "wz": "wz", "dX": "dX", "dY": "dY", "dZ": "dZ", "ExP": "ExP",
               "Cross": "Cross", "DetP": "DetP", "BlP": "BlP", "LT": "LT", "R0": "R0",
               "R": "R", "DistanceWidth": "distance_width", "Aniso": "aniso"}
    for k_pam, k_py in mapping.items():
        if k_pam in s:
            kw[k_py] = s[k_pam]
    if "UseLT" in s:
        kw["use_lt"] = bool(s["UseLT"])
    return Species(**kw)


def _field_names(cls):
    return {f.name for f in fields(cls)}


def _to_jsonable(obj):
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    return obj
