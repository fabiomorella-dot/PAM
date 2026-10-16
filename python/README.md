# pamsim – fast Python port of PAM's photon simulation

`pamsim` is a Python/[numba](https://numba.pydata.org) port of the photon
simulation in **PAM – PIE Analysis with MATLAB** (FAB Lab Munich, Don C. Lamb):
the *Extras → Simulate photon data* window (`Sim.m`) and its two C++ MEX
kernels `DifSim.cpp` and `DifSim_ani.cpp`.  It also contains a bit-exact port of
PAM's correlator (`CrossCorrelation.m` + `Do_CCF.c`) for analysing the result.

The original sources were pulled from the official repository
(<https://gitlab.com/PAM-PIE/PAM>, `master` at commit `7319d15d`) and are
stored unmodified in the repository root: `Sim.m`, `DifSim.cpp`,
`DifSim_ani.cpp` and their Linux/macOS variants `DifSim_mac.cpp`,
`DifSim_ani_mac.cpp`.

## Why it is faster

The heavy lifting in Sim.m is already compiled C++, so speed does not come from
"Python vs. MATLAB".  It comes from what the code does:

1. **Dark periods are skipped.**  The kernels take every 1/f diffusion step of
   every particle (10⁷ steps per particle for 10 s at 1 MHz), although with
   the default settings a particle spends ~98 % of the time outside the small
   region around the focus where the C++ code can produce a photon at all (it
   only rolls for photons when the excitation probability is > 10⁻⁴).  pamsim combines such steps into one
   Gaussian jump.  A sum of *n* Gaussian steps is exactly Gaussian with
   variance *nσ²*.  *n* is chosen with the reflection principle so that the
   particle enters the region where photons are possible during the jump with
   probability < 4·Q(7) ≈ 5·10⁻¹²
   (`SimSettings.fast_forward`, `ff_z`).  Near the focus, every step is
   simulated as before.
2. **Faster per-step kernel**: about 2× faster per step than the C++ code,
   because it uses a cheaper random number generator and skips `exp()` outside
   the focus.
3. **All cores without the Parallel Computing Toolbox**: particles run in
   parallel threads.
4. **Memory**: each MEX call preallocates room for 4 photons per tick
   (44–48 bytes/tick).  For example, a single 100 s frame at 1 MHz needs
   4.4 GB per call and per parallel worker.  pamsim stores only the photons
   that are actually detected.

Timings on a 4-core Xeon VM (2.1 GHz), 10 s of simulated data each
(`python benchmarks/benchmark.py`).  "Original" is the unmodified C++
kernel driven exactly as Sim.m drives it (one call per particle and frame,
one core), without MATLAB's own overhead:

| scenario | original C++, 1 core | pamsim, 1 core | pamsim, 4 cores |
|---|---:|---:|---:|
| Sim.m defaults (D = 1 µm²/s, N = 10, 5 µm box) | 14.4 s | 0.38 s (38×) | 0.15 s (97×) |
| solution FCS (D = 100 µm²/s, N = 50) | 70.6 s | 4.5 s (16×) | 1.0 s (68×) |
| smFRET, 2-colour PIE, IRF + anisotropy (advanced kernel) | 34.0 s | 1.9 s (18×) | 0.58 s (58×) |
| *pamsim without fast-forward, 1 core* | | 7.8 / 38 / 16 s (≈2×) | |

The gain is largest when the focus is small compared with the box (low
concentrations, slow diffusion, i.e. the long simulations that hurt most in
MATLAB).

## Installation

```bash
cd python
pip install -e .            # numpy, numba, scipy;  add ".[plot,test]" for matplotlib/pytest
```

The first simulation compiles the kernel (about 15 s); the compiled code is
cached on disk afterwards.

## Graphical interface (PAMsim app)

**Windows:** double-click `Install_PAMsim.bat` (repository root) once.  It
installs the libraries and creates a **PAMsim** icon on the Desktop and in the
Start menu.  Without installing you can double-click `PAMsim.pyw`; from a
terminal: `python run_gui.py` (or `pamsim-gui` after `pip install -e .[gui]`).

The window is organised in three steps:

1. **Measurement** – box, sampling frequency, time, scanning, background.
2. **Molecules** – the species list (Add / Copy / Delete) and, per species, D,
   number of molecules (the concentration is shown) and brightness per colour
   (0 = dye not present).  The tabs hold focus/lifetime/anisotropy per colour,
   the excitation / crosstalk / detection / bleaching matrices, FRET distances
   and dynamic rates, and advanced options (IRF, distance width, linker, maps,
   CPU cores).
3. **Output** – folder, file name, number of files, format.

* **Presets** (top right): 1-colour FCS, 2- and 3-colour FCCS with PIE,
  smFRET bursts.
* **Load from planner...**: reads `planning/PAMsim_simulation_planner.xlsx`;
  load one simulation into the editor or run several selected ones in a row.
* **Check** tab: updates live and warns about settings that bias the result.
  Examples are a brightness close to the sampling frequency (saturated
  focus), diffusion steps that are too coarse, or a box that is too small.
  It also predicts the count rate per channel and the memory needed,
  including for saturated foci.
* Every field has a tooltip.  **Help** gives a short guide.
* **Start / Stop**, progress bar, **Plot result** (trace plus all auto- and
  cross-correlations), **Open folder**.
* The last setup and output folder are restored at the next start.  *Save /
  Open setup* store setups as JSON, and setups saved by Sim.m open too.

Next to every file PAMsim writes `<name>_<k>_info.txt`, a plain-text summary of
the parameters (duration, microtime range, background, FRET with R0 / R,
crosstalk, direct excitation, and D, concentration, brightness and lifetime of
every species), plus seed, run time and measured count rates.  From a script:
`r.save_info("my_simulation_1_info.txt", files=r.save_sim("my_simulation_1.sim"))`.

Each simulation is written into its own folder `<output folder>/<name>/`
(option *Own folder per simulation*, on by default). Files are named like in
Sim.m (`<name>_1.sim`, `<name>_2.sim`, ...; with a seed, file *k* uses seed + k − 1) and open in PAM via *Load TCSPC data → Pam
Simulation Files*.  Very large results are split into `<name>_1_part01.sim`,
`_part02.sim`, ...: select all parts together in PAM.

## Quick start (scripting)

```python
import numpy as np
from pamsim import SimSettings, Species, simulate, correlate_blocks

s = SimSettings(box_size=[5000, 5000, 5000],   # nm      (Sim.m: Box size)
                freq=1000,                     # kHz     (Frequency)
                sim_time=30, frames=10,        # s       (Time, Frames)
                species=[Species(D=50, N=20,   # um^2/s, particles
                                 wr=[200]*4, wz=[1000]*4,
                                 brightness=[100]*4)])   # kHz
r = simulate(s, progress=True)

r.macrotimes[0]      # photon arrival times of channel 1 in sampling ticks
r.microtimes[0]      # TCSPC microtimes (uint16)
r.labels[0]          # laser<<6 | excited dye<<4 | emitting dye<<2 | channel (255 = background)
r.save_sim("my_simulation_1.sim")   # open in PAM: Load TCSPC data -> "Pam Simulation Files"

lags, g, sem, _ = correlate_blocks(r.macrotimes[0], r.macrotimes[0],
                                   r.header["Frames"] * r.header["FrameTime"], n_blocks=10)
```

See `examples/fcs_quickstart.py` for a full simulate → save → correlate → fit
example.  A setup saved with the *save* button of Sim.m (JSON) can be
loaded with `SimSettings.load_json("setup.json")`.

## Parameters

`SimSettings` mirrors `SimData.General`, `Species` mirrors `SimData.Species`.
Units and matrix orientation are the same as in the GUI, so values can be
copied one to one (full list in `pamsim/params.py`):

| Sim.m | pamsim | unit |
|---|---|---|
| Box size | `box_size` | nm |
| Frequency | `freq` | kHz |
| Time, Frames | `sim_time`, `frames` | s |
| Scan type (point/raster/line/circle) | `scan_type` 1/2/3/4 | |
| Pixels/Lines, Pixel size, Pixel/Line/Frame time | `pixels`, `pixel_size`, `times` | –, nm, µs/ms/s |
| Apply noise | `use_noise`, `noise` | kHz per channel |
| Microtime range, IRF width | `mi_range`, `irf_width` (+ `use_irf`) | ns, ps |
| Anisotropy | `use_aniso`, `Species.aniso` (r0, ρ [ns], r∞, G) | |
| FRET distance width, update time | `use_fret_width`, `Species.distance_width`, `heterogeneity_update` | –, ms |
| Linker width | `use_linker_width`, `linker_width` | |
| Dynamic rates table (from → to) | `dynamic_rates` | 1/ms |
| barrier / quenching maps | `maps` (`map[x, y]`, 1 px = 1 nm; 3D array for moving maps) | |
| Species: colours, FRET type, barrier type | `color`, `fret`, `barrier` | |
| D, N, ω_r, ω_z, focus shifts | `D`, `N`, `wr`, `wz`, `dX/dY/dZ` | µm²/s, –, nm |
| Brightness | `brightness` (or set `ExP` directly) | kHz |
| ExP, Cross, DetP, BlP matrices | `ExP`, `Cross`, `DetP`, `BlP` | |
| Lifetime | `use_lt`, `LT` | ns |
| R0, R | `R0`, `R` (lower triangle: [acceptor, donor]) | |

As in Sim.m, the *advanced* kernel (`DifSim_ani`) is used as soon as IRF,
anisotropy, distance width, linker width or dynamic FRET is switched on
(`SimSettings.advanced`).  In that mode the species are states of one
molecule, and the focus and map type are taken from the first species.

## Validation

`validation/` builds PAM's **original, unmodified** `DifSim*_mac.cpp` and
`Do_CCF.c` natively (a small stand-in for the MEX API is in
`validation/mex_shim`).  It drives them exactly like Sim.m does, with all
inputs built directly from the Sim.m source, and compares them with pamsim:

```bash
python validation/compare_kernels.py     # 9 scenarios, original vs pamsim
python validation/check_fcs.py           # FCS fit vs theory, pamsim and original
python -m pytest                         # 29 tests (~1 min)
```

* **Simulation**: the comparison covers 1 colour; 2-colour PIE with static
  FRET, crosstalk, direct excitation and detection efficiencies;
  photobleaching; raster scan; the advanced kernel with IRF + anisotropy +
  distance heterogeneity + linker fluctuations; dynamic two-state FRET; and
  quenching, restricted-zone and barrier maps.  In every scenario, count
  rates and mean microtimes per photon type (laser / excited dye / emitting
  dye / channel) agree within statistical error (max |z| = 2.2 over 12
  seeds each), and full microtime histograms pass a χ² test.
* **Physics**: count rates agree with the analytic value for a Gaussian focus
  (fast-forward on: −0.2σ, off: +1.1σ, 48 runs).  FCS fits give the
  theoretical N and τ_D = ω_r²/4D for pamsim with and without fast-forward
  and for the original kernel alike (N = 0.090/0.092/0.092, τ_D = 202/198/201 µs
  vs. 0.093 and 200 µs).
* **Correlator**: `do_ccf` and `cross_correlation` give results *identical*
  (difference exactly 0) to `Do_CCF.c` and to a literal transcription of
  `CrossCorrelation.m`.  For 2·10⁶ × 2·10⁶ photons it takes 0.84 s vs. 1.07 s
  for the C code.

Results are statistically equivalent to Sim.m, not bit-identical: MATLAB's
MT19937 streams are not reproduced (see below).

## Deliberate differences from Sim.m

| | Sim.m / C++ | pamsim | why |
|---|---|---|---|
| random numbers | MT19937 seeded with `seed + frame + particle` | xoshiro256** per particle from `SeedSequence(seed, (species, particle))` | in Sim.m, particle *j* in frame *k* and particle *j+1* in frame *k−1* get **the same random stream**, so their random walks are identical copies |
| default seed | clock (`now`) | fresh random seed; the seed used is stored in `result.seed` and in the `.sim` header | reproducible runs |
| frames | one MEX call per frame; every call starts with all dyes **unbleached** | all frames in one call, bleaching persists | physically correct; `reset_bleaching_each_frame=True` reproduces Sim.m |
| bleaching switch (basic kernel) | bleaching is only evaluated if `BlP(m,1) > 0`, but `BlP(m,k)` is used as the probability | `BlP(m,k)` for both (as in `DifSim_ani.cpp`) | otherwise `BlP` entries for excitation of dyes 2–4 are silently ignored |
| raster scan y origin | uses `x0 = −Px(1)·Size(1)/2` for y as well | `−Px(2)·Size(2)/2` | identical for square images |
| start positions | uniform in `[0, BS−1]` | uniform in `[0, BS)` | |
| background (basic mode) | stops after 10⁶ noise photons | Poisson process over the whole measurement | long/bright-noise simulations lost background |
| moving maps (types 6/7) | particle moved to the 1-based pixel index of the nearest matching pixel (1 px off; error if none exists) | pixel centre of the nearest matching pixel; unchanged if none exists | |
| map cropping | 2nd dimension cropped to `BS(1)` | cropped to `BS(2)` | typo in Sim.m |
| output | unsorted per particle in the workspace, sorted in `.sim` | always sorted, plus `labels` per photon | |
| `.sim` file | MAT `-v7.3` (HDF5) | MAT v5 (read by PAM's `LoadTcspc` the same way). A v5 variable must stay below 4 GB, so results above ~350 million photons are split in time into `<name>_part01.sim`, `_part02.sim`, … – select all parts together in PAM | |

Reproduced as in Sim.m (properties of the original, not bugs of the port):
basic-mode microtimes are `laser·16384 + 1 + Σ lifetimes` while the header says
`MI_Bins = 8192` (65537 with noise); circle scans (type 4) are simulated as
point measurements by the kernels; photons are only generated where the
excitation probability exceeds 10⁻⁴; the advanced mode writes `*_irf.sim` /
`*_scat.sim` files alongside the data.

## Not ported

* the camera simulation (scan type 5, pure MATLAB in Sim.m)
* reading Sim.m's own `-v7.3` `.sim` files (re-save them with `-v7` in MATLAB)

## Layout

```
pamsim/_kernel.py      numba port of DifSim.cpp + DifSim_ani.cpp (+ fast-forward)
pamsim/_rng.py         xoshiro256** / normal / geometric deviates
pamsim/simulate.py     Do_PointSim: input preparation, threads, noise, channels
pamsim/params.py       SimSettings / Species (Sim.m parameters)
pamsim/correlation.py  CrossCorrelation.m + Do_CCF.c
pamsim/io.py           .sim / .npz output, IRF and scatter files
pamsim/report.py       <name>_<k>_info.txt summary written after every simulation
pamsim/planner.py      reads the Excel planner (incl. the crosstalk / direct excitation sheet)
pamsim/gui.py          PAMsim window (tkinter + sv-ttk theme): presets, live checks
pamsim/shortcut.py     creates the Desktop / Start menu shortcuts
PAMsim.pyw             double-click launcher (no console window)
validation/            builds and runs PAM's original kernels for comparison
benchmarks/, examples/, tests/
```

## License

PAM is licensed under the GNU GPL v3, and so is this port (see `LICENSE.md`).
