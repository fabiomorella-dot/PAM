# 3C-FCCS models for FCSFit

FCSFit (PAM v1.7+) loads every `*.m` model function in `<PAM root>/Models/fcs/`.
This folder holds one family of models for fitting the auto- and
cross-correlations of a 3C-FCCS measurement (GG, RR, BB, GR, GB, RB):

| model | components | fits | background correction |
|---|---|---|---|
| `FCCS3C_1Comp_D`       | 1 | D (w_r, w_z fixed)        | no  |
| `FCCS3C_1Comp_D_BG`    | 1 | D (w_r, w_z fixed)        | yes |
| `FCCS3C_1Comp_TauD`    | 1 | tauD and p (= w_z/w_r)    | no  |
| `FCCS3C_1Comp_TauD_BG` | 1 | tauD and p                | yes |
| `FCCS3C_2Comp_D`       | 2 | D1, D2 (w_r, w_z fixed)   | no  |
| `FCCS3C_2Comp_D_BG`    | 2 | D1, D2 (w_r, w_z fixed)   | yes |
| `FCCS3C_2Comp_TauD`    | 2 | tauD1, tauD2 (p fixed)    | no  |
| `FCCS3C_2Comp_TauD_BG` | 2 | tauD1, tauD2 (p fixed)    | yes |

All models have one triplet term (`tauT`, `Trip`; fixed, Trip = 0 by default)
and an offset `y0`.

## Equations

```
G(tau) = gamma * A * BGcorr * [1 + Trip/(1-Trip) * exp(-tau/tauT)] * Diff(tau) + y0

gamma   = 1/sqrt(8)                              (3D Gaussian focus)
1 comp:  A*Diff = (1/N) * g(tau; D)
2 comp:  A*Diff = (N1*g(tau; D1) + N2*g(tau; D2)) / (N1+N2)^2   (equal brightness)
g(tau; D) = 1/(1 + 4 D tau / w_r^2) * 1/sqrt(1 + 4 D tau / w_z^2)
TauD models: 4 D / w_r^2 -> 1/tauD,  4 D / w_z^2 -> 1/(p^2 tauD)

BGcorr = (1 - BG_a/Counts_a) * (1 - BG_b/Counts_b)    (_BG models only, 1 otherwise)
```

With background correction the fitted N is the background-corrected particle
number. Without it, N is the apparent number (larger when background is high).

## How to use the _BG models

`Counts_a`, `BG_a`, `Counts_b`, `BG_b` are **inputs, not fit parameters**: they
are fixed by default. Type in, in kHz:

* `Counts_a`, `Counts_b`: mean count rate of the two channels that were
  correlated (PAM shows them in FCSFit's Counts column / the .mcor file).
* `BG_a`, `BG_b`: background count rate of the same channels, from a buffer
  measurement.

For an **auto**correlation (e.g. GG) put the same channel in a and b
(`Counts_a = Counts_b`, `BG_a = BG_b`). This gives the usual (1 - BG/Counts)^2
correction. For a **cross**correlation (e.g. GR) put green in a and red in b.

## Install / update

1. Close FCSFit.
2. Copy all `Models/fcs/FCCS3C_*.m` files into the `Models/fcs/` folder of the
   PAM installation you run (next to `FCS_D.m`, `FCS_TauD.m`, ...).
   Keep the file names unchanged: MATLAB needs the file name to match the
   function name inside.
3. If you copied `FCS_D_2Component_noBG.m` earlier, delete it: it is now
   `FCCS3C_2Comp_D.m`.
4. Restart PAM / FCSFit and pick the model from the list.
