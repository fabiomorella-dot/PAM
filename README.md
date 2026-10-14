# PAM + PAMsim

This repository holds PAM (PIE Analysis with MATLAB) files and **PAMsim**, a
fast Python version of PAM's photon simulation (`Sim.m`) with its own window.
PAMsim writes `.sim` files that open in PAM via *Load TCSPC data → "Pam
Simulation Files"*.

## Install PAMsim on Windows (once)

1. Install Python 3.9 or newer from <https://www.python.org/downloads/> if it
   is not installed yet (tick *"Add python.exe to PATH"*).
2. Double-click **`Install_PAMsim.bat`** in this folder.
   It installs the required libraries and puts a **PAMsim** icon on your
   Desktop and in the Start menu.
3. Start PAMsim with the icon.  (The very first simulation takes ~15 s
   longer because the code is compiled once.)

Without installing anything you can also double-click `python/PAMsim.pyw`.
On macOS / Linux run `python/install_pamsim.sh`.

## Update

Double-click **`Update_PAMsim.bat`** (or run `git pull` in this folder).

## Planning simulations

`planning/PAMsim_simulation_planner.xlsx` – one row per simulation with up to six
species side by side (D, molecules, brightness and lifetime per colour, FRET);
it calculates FRET efficiencies, concentrations, expected count rates, photons and memory
and flags saturating brightness or too coarse time steps before you run anything.

## More

* `python/README.md` – how the simulation works, all parameters, validation
  against PAM's original code, speed comparison, scripting from Python
* `Sim.m`, `DifSim*.cpp` – PAM's original simulation code (unmodified)
