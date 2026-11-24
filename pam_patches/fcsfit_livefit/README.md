# FCSFit: Fit button and live fitting

Adds three controls to the right of the fit table in FCSFit (the **Fit** tab at the bottom):

| Control      | What it does |
|--------------|--------------|
| **Fit**      | Fits now. It is FCSFit's normal fit, exactly like *Start... > ...Fit*. |
| **Live fit** | When ticked, FCSFit refits by itself whenever something changes (see below). Ticking it also starts a fit straight away. |
| **Stop**     | Stops a running fit, like *Stop.... > ...Fit*. |

With **Live fit** on, a new fit starts as soon as you:

- change a start value, tick or untick *Fixed* / *Global*, or switch a file on or off in the fit table;
- change the fit borders [s] (Settings tab);
- tick or untick *Use weights* (Settings tab);
- load or add correlation files (*File > Load New Files* / *Add Files*);
- load another fit model (*File > Load Fit Function*).

If you make another change while a fit is running, FCSFit finishes that fit and then fits once more with the newest settings. Changes are never lost and fits don't pile up.

Fitting itself, the fit models and the results table are FCSFit's own and are not changed.

## Install (once)

1. Close FCSFit.
2. Save `FCSFit_LiveFit.m` and `apply_fcsfit_livefit.m` together in one folder. Your PAM program folder (the one with `PAM.m` and `FCSFit.m`) is fine.
3. In MATLAB, go to that folder and run the installer with your PAM program folder, for example:

   ```matlab
   cd C:\Users\Rosario\Documents\MATLAB\PAM_current_with_3FCCS
   apply_fcsfit_livefit(pwd)
   ```

   Without an argument, `apply_fcsfit_livefit` asks for the PAM folder in a window.
4. Open FCSFit (from PAM or by typing `FCSFit`).

The script:

- copies `FCSFit_LiveFit.m` next to `FCSFit.m`;
- adds 2 lines to `FCSFit.m`, right after `guidata(fig, h);` near the top (in older single-file versions: after the first `guidata(h.FCSFit,h);`);
- keeps a backup as `FCSFit.m.bak`.

Running it again does nothing. After you update PAM itself, run it again if the buttons are gone.

**Without installing:** with `FCSFit_LiveFit.m` on the MATLAB path, open FCSFit and type `FCSFit_LiveFit`. The controls are added to every open FCSFit window until you close it.

## Undo

Rename `FCSFit.m.bak` back to `FCSFit.m` (replacing the patched file) and delete `FCSFit_LiveFit.m` from the same folder.

## Manual change (if the script reports "not supported")

Add this line to `FCSFit.m` right after the GUI handles are stored with `guidata`, where `fig` is the FCSFit figure:

```matlab
if exist('FCSFit_LiveFit', 'file'), FCSFit_LiveFit(fig); end
```
