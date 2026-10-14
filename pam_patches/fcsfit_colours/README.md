# FCSFit: colour curves by channel

Every time you load correlation files in FCSFit, each curve gets its colour from the channels in its file name:

| Curve | Colour      | RGB              |
|-------|-------------|------------------|
| BB    | blue        | 0 0 1            |
| GG    | green       | 0 0.6 0          |
| RR    | red         | 1 0 0            |
| BG    | violet      | 0.55 0.35 0.95   |
| BR    | purple      | 0.5 0 0.5        |
| GR    | dark yellow | 0.8 0.65 0       |
| BGR   | dark        | 0.2 0.2 0.2      |

Other files keep FCSFit's normal colours. The patch only changes colours. Line styles, markers and the Style table work as before, and you can still change any colour there by hand.

## How the channels are recognised

PAM saves correlations as `<file>_<PIE channel 1>_x_<PIE channel 2>.mcor`. The letters B, G and R in the two PIE channel names give the colour, and their order does not matter:

- `dsDNA_BB_x_BB`, `dsDNA_B_x_B`, `dsDNA_B1_x_B2` → BB (blue)
- `dsDNA_BB_x_GG`, `dsDNA_GG_x_BB`, `dsDNA_B_x_G` → BG (violet)
- `dsDNA_GG_x_RR` → GR (dark yellow)
- `dsDNA_BGR_x_BGR` → BGR (dark)

If the name has no `_x_` part, a stand-alone `BB`, `GG`, `RR`, `BG`, `BR`, `GR` or `BGR` anywhere in the name is used instead, for example `dsDNA_GR_run2`.

PIE channel names that are not made of B, G and R (for example `Blue` or `Donor`) are not recognised. Either rename the PIE channels in PAM, or add your names to `channelLetters` in `FCSFit_ChannelColor.m`.

## Install (once)

1. Update this repository: run `Update_PAMsim.bat`, or `git pull`.
2. Close PAM and FCSFit.
3. In MATLAB, run:

   ```matlab
   cd C:\Users\Rosario\PAM\pam_patches\fcsfit_colours
   apply_fcsfit_colours
   ```

   A window asks for your **PAM program folder**, the one that contains `PAM.m` and `FCSFit.m` (your MATLAB PAM installation, not this repository). You can also give it directly: `apply_fcsfit_colours('C:\path\to\PAM')`.
4. Start PAM, open FCSFit and load your files.

The script:

- copies `FCSFit_ChannelColor.m` into the PAM folder;
- adds 7 lines where FCSFit styles newly loaded files. In the new FCSFit (2026) that is `functions/FCSFit/+fcs/+gui/+cb/styleLoadNewFileCallback.m`; in older versions it is `FCSFit.m`, in `Update_Style`, case 1;
- keeps a backup of the changed file as `*.bak`.

Running it again does nothing. After you update PAM itself (for example with `git pull` in the PAM program folder), run it again if the colours are gone.

## Change a colour

Edit the RGB values (0 to 1) at the top of `FCSFit_ChannelColor.m` in your PAM folder and reopen FCSFit.

## Undo

Rename `styleLoadNewFileCallback.m.bak` (or `FCSFit.m.bak`) back to its original name, replacing the patched file. Then delete `FCSFit_ChannelColor.m` from the PAM folder.

## Manual change (if the script reports "not supported")

Put this right after the loop that fills `Data(i, 1:8)` from `userValues.FCSFit.PlotStyles`, before the plots are styled:

```matlab
% new FCSFit (styleLoadNewFileCallback.m)
for i = 1:numel(fcsData.fileName)
    color = FCSFit_ChannelColor(fcsData.fileName{i});
    if ~isempty(color)
        Data{i, layout.COL_COLOR} = sprintf('%g %g %g', color);
    end
end

% older FCSFit (FCSFit.m, Update_Style, case 1)
for i=1:numel(FCSData.FileName)
    color = FCSFit_ChannelColor(FCSData.FileName{i});
    if ~isempty(color)
        Data{i,1} = sprintf('%g %g %g', color);
    end
end
```
