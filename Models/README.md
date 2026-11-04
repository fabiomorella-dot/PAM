# Custom FCSFit models

FCSFit (PAM v1.7+) loads every `*.m` model function in `<PAM root>/Models/fcs/`.

| file | what it is |
|---|---|
| `fcs/FCS_D_2Component_noBG.m` | 2-component 3D diffusion + triplet + offset, **no background correction**. Replaces the earlier custom model that had `Counts_a`, `BG_a`, `Counts_b`, `BG_b`. |

## Install / update

1. Close FCSFit.
2. Copy `Models/fcs/FCS_D_2Component_noBG.m` into the `Models/fcs/` folder of
   the PAM installation you run.
3. Delete (or move out of `Models/fcs/`) the old model file that has the
   `Counts_a / BG_a / Counts_b / BG_b` parameters, so it can no longer be
   selected.
4. Restart FCSFit and pick `FCS_D_2Component_noBG` from the model list.
   Re-load or re-fit your `.mcor`/`.cor` files. Old saved sessions still
   reference the old model, so fit them again with the new one.

## Upstream PAM models with background correction

Upstream PAM ships two models that contain a `(1-BG/Counts)^2` factor:
`FCS_D_Background.m` and `FCS_TauD_Background.m`. Their background-free
equivalents already exist upstream: `FCS_D.m` and `FCS_TauD.m`. Use those
instead, or delete the two `*_Background.m` files from `Models/fcs/` so they
no longer show up in FCSFit.
