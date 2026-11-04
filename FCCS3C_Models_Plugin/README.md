# 3C-FCCS fit models plugin for PAM / FCSFit

## Install (once)

1. Unzip this folder anywhere (it does not have to be inside PAM).
2. In MATLAB, go to this folder and run:

   ```matlab
   install_fccs3c_models
   ```

   It finds PAM on your MATLAB path (or asks for the PAM folder). You can also
   give it directly: `install_fccs3c_models('C:\path\to\PAM')`.
3. Close all FCSFit windows and open FCSFit again. The models are in
   **3C-FCCS > Fit models > 1 component / 2 components**.

The installer:

* copies the 8 `models/FCCS3C_*.m` files to `<PAM>/Models/fcs/`,
* copies `FCCS3C_Menu.m` to `<PAM>/`,
* adds 6 lines (between `>>> 3C-FCCS fit models` markers) at the end of the
  main function in `<PAM>/FCSFit.m`, and keeps a backup
  `FCSFit.m.bak_fccs3c`.

Running it again updates the models and the menu; `FCSFit.m` is only changed
once. `uninstall_fccs3c_models` removes everything again and restores
`FCSFit.m` to exactly what it was.

## The models

One family of models for a 3C-FCCS measurement. Every model
fits **autocorrelations (GG, RR, BB), 2-colour cross-correlations (GR, GB, RB)
and the 3-colour triple correlation**, selected with the `3C (0/1)` column.

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

All models also have a triplet term (`tauT`, `Trip`; fixed, Trip = 0 by
default) and an offset `y0`.

## The 3C (0/1) column

* `0`: autocorrelation or 2-colour cross-correlation (standard FCS model).
* `1`: 3-colour triple correlation, on the equal-interval diagonal
  tau1 = tau, tau2 = 2*tau (the curve the `fcs3c` Python code computes).

It is fixed by default; keep it fixed. Any value is rounded to 0 or 1. It can
be set per file, so ACFs, CCFs and the triple correlation can be fitted in the
same FCSFit session, e.g. with D global. Do not make N global across them:
the ACF, CCF and triple correlation each have their own (apparent) N.

## Equations

```
3C = 0:
G(tau) = BGab * (1/sqrt(8)) * [1 + Trip/(1-Trip) exp(-tau/tauT)] * sum_i N_i g2_i(tau) / (sum_i N_i)^2 + y0
g2(tau) = 1/(1 + u) * 1/sqrt(1 + v)

3C = 1:
G(tau) = BGab * BGc * (1/sqrt(27)) * sum_i N_i g3_i(tau) / (sum_i N_i)^3 + y0
g3(tau) = 1/(1 + 8/3 u + 4/3 u^2) * 1/sqrt(1 + 8/3 v + 4/3 v^2)

u = 4 D tau / w_r^2  (= tau/tauD),   v = 4 D tau / w_z^2  (= tau/(p^2 tauD))
1 component: sum_i N_i g_i / (sum_i N_i)^2 = g/N  and  sum_i N_i g_i / (sum_i N_i)^3 = g/N^2
BGab = (1 - BG_a/Counts_a)(1 - BG_b/Counts_b),  BGc = (1 - BG_c/Counts_c)   (_BG models; 1 otherwise)
```

The 3C = 0 part is identical to PAM's own `FCS_D`, `FCS_TauD`,
`FCS_D_2Component` and `FCS_D_Background`. The 3C = 1 part is identical to
`triple_correlation_diagonal` in `fcs3c/models.py` (gamma_3 = 3^(-3/2)).
The triplet term is not used for 3C = 1: triplet blinking is uncorrelated
between three different dyes.

With background correction the fitted N is the background-corrected number.
Without it, N is the apparent number (larger when the background is high).

## How to use the _BG models

`Counts_a`, `BG_a`, `Counts_b`, `BG_b`, `Counts_c`, `BG_c` are **inputs, not
fit parameters**: they are fixed by default. Type in, in kHz, the mean count
rate and the background (from a buffer measurement) of:

* autocorrelation (e.g. GG): the same channel in a and b;
* 2-colour cross-correlation (e.g. GR): green in a, red in b;
* triple correlation (3C = 1): the three channels in a, b and c.

Channel c is ignored when 3C = 0.

## The 3C-FCCS menu

`FCCS3C_Menu.m` adds **Fit models** to the existing **3C-FCCS** menu of
FCSFit (the one from the `+fcs3c` extension), with all 8 models, a check mark
on the loaded one, and a short help. If there is no 3C-FCCS menu, it creates
one. Clicking a model loads it exactly like File > Load Fit Function.
