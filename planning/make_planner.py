import os
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.comments import Comment

F = "Arial"
HDR = PatternFill("solid", fgColor="1F3A5F")
BAND = {"id": "2A78D6", "gen": "3D6B9E", "foc": "5A7FA8", "out": "6C8EAF", "chk": "7A7A7A", "res": "4E8A5B"}
INPUT = PatternFill("solid", fgColor="FFF6C7")
CALC = PatternFill("solid", fgColor="EEF2F6")
thin = Side(style="thin", color="C9CED6")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
BLUE = Font(name=F, size=10, color="0000FF")
BLACK = Font(name=F, size=10, color="000000")
WHITE_B = Font(name=F, size=10, bold=True, color="FFFFFF")
N_ROWS_SIM, N_ROWS_SP = 60, 300

wb = Workbook()

# ------------------------------------------------------------------ How to use
h = wb.active
h.title = "How to use"
lines = [
    ("PAMsim simulation planner", Font(name=F, size=16, bold=True, color="1F3A5F")),
    ("Plan your simulations here, then type the values into PAMsim (or Sim.m).", Font(name=F, size=10, italic=True, color="555555")),
    ("", None),
    ("How it works", Font(name=F, size=12, bold=True)),
    ("1.  Sheet 'Simulations': one row per simulation (measurement settings, output, status, results).", None),
    ("2.  Sheet 'Species': one row per molecule species. Link it to its simulation with the Sim ID (dropdown).", None),
    ("3.  Grey columns are calculated automatically: concentration, expected count rates, photons, memory and checks.", None),
    ("4.  Fix every red check before running a simulation; orange checks bias the results slightly.", None),
    ("", None),
    ("Colour code", Font(name=F, size=12, bold=True)),
    ("Yellow cells with blue text = your input.   Grey cells with black text = formulas (do not overwrite).", None),
    ("", None),
    ("Rules of thumb (from the PAMsim checks)", Font(name=F, size=12, bold=True)),
    ("•  Brightness < 10% of the sampling frequency (e.g. < 100 kHz at 1000 kHz). Above it the focus saturates:", None),
    ("    the fitted D comes out too small and the concentration too large. At >= 100% the excitation is fully saturated.", None),
    ("•  One diffusion step sqrt(2·D·dt) should be < 10% of wr; otherwise raise the sampling frequency.", None),
    ("•  Box >= 8·wr laterally and >= 3·wz axially.", None),
    ("•  Memory ≈ 12 bytes per photon and file. For very long runs use several files (Number of files) instead.", None),
    ("•  Expected count rates: Gaussian focus incl. saturation (as in PAMsim's Check panel); FRET and crosstalk are ignored.", None),
    ("", None),
    ("Units", Font(name=F, size=12, bold=True)),
    ("nm (box, wr, wz) · kHz (sampling frequency, brightness, background) · s (duration) · ns (lifetime, microtime range)", None),
    ("µm²/s (D) · nM (concentration) · kHz (count rates) · million photons · GB", None),
    ("", None),
    ("Example rows", Font(name=F, size=12, bold=True)),
    ("S00 is a worked example with realistic values. S01-S11 are the simulations from your earlier spreadsheet", None),
    ("(box 5000 nm assumed, wr 200 nm, wz 1000 nm) - the checks show which of them saturate. Delete or overwrite rows freely.", None),
]
for i, (t, f) in enumerate(lines, start=1):
    c = h.cell(row=i, column=2, value=t)
    c.font = f or Font(name=F, size=10)
h.column_dimensions["A"].width = 3
h.column_dimensions["B"].width = 120
h["B11"].fill = INPUT
h.sheet_view.showGridLines = False

# ------------------------------------------------------------------ Lists
ls = wb.create_sheet("Lists")
lists = {
    "A": ("Status", ["Idea", "Planned", "Running", "Done", "Analysed", "Discarded"]),
    "B": ("Scan type", ["Point", "Raster scan", "Line scan", "Circle scan"]),
    "C": ("Yes/No", ["Yes", "No"]),
    "D": ("FRET", ["No FRET", "Static FRET", "Dynamic FRET"]),
    "E": ("Format", [".sim", ".npz", "both"]),
}
for col, (title, vals) in lists.items():
    ls[f"{col}1"] = title
    ls[f"{col}1"].font = Font(name=F, bold=True)
    for i, v in enumerate(vals, start=2):
        ls[f"{col}{i}"] = v
        ls[f"{col}{i}"].font = Font(name=F)
ls.sheet_state = "hidden"

# ------------------------------------------------------------------ Simulations
s = wb.create_sheet("Simulations")
sim_cols = [  # key, header, width, band, kind(input/calc), comment
    ("id", "Sim ID", 8, "id", "in", "Unique short ID, e.g. S12. Used to link species."),
    ("name", "File name", 26, "id", "in", "PAMsim 'File name': files become <name>_1.sim, ..."),
    ("purpose", "Purpose / question", 40, "id", "in", None),
    ("folder", "Output folder", 34, "id", "in", None),
    ("status", "Status", 11, "id", "in", None),
    ("prio", "Priority", 8, "id", "in", "1 = highest"),
    ("bx", "Box x [nm]", 9, "gen", "in", None),
    ("by", "Box y [nm]", 9, "gen", "in", None),
    ("bz", "Box z [nm]", 9, "gen", "in", "0 = 2D (membrane)"),
    ("freq", "Sampling freq. [kHz]", 10, "gen", "in", None),
    ("dur", "Duration [s]", 9, "gen", "in", None),
    ("frames", "Frames", 7, "gen", "in", None),
    ("mir", "Microtime range [ns]", 10, "gen", "in", None),
    ("scan", "Scan type", 11, "gen", "in", None),
    ("ncol", "Colours", 7, "gen", "in", "Number of colours / PIE lasers (1-4)"),
    ("bg", "Background?", 9, "gen", "in", None),
    ("bgk", "Background [kHz/ch]", 10, "gen", "in", None),
    ("irf", "IRF?", 6, "gen", "in", None),
    ("irfw", "IRF width [ps]", 8, "gen", "in", None),
    ("wr", "wr [nm]", 7, "foc", "in", "1/e² radius, same for all colours here"),
    ("wz", "wz [nm]", 7, "foc", "in", None),
    ("nfiles", "Number of files", 8, "out", "in", None),
    ("seed", "Seed", 8, "out", "in", "Empty = random"),
    ("fmt", "Format", 7, "out", "in", None),
    ("nsp", "Species", 8, "chk", "calc", None),
    ("ntot", "Total molecules", 9, "chk", "calc", None),
    ("r1", "Exp. rate ch1 [kHz]", 10, "chk", "calc", None),
    ("r2", "Exp. rate ch2 [kHz]", 10, "chk", "calc", None),
    ("r3", "Exp. rate ch3 [kHz]", 10, "chk", "calc", None),
    ("r4", "Exp. rate ch4 [kHz]", 10, "chk", "calc", None),
    ("ph", "Photons per file [M]", 10, "chk", "calc", None),
    ("mem", "Memory per file [GB]", 10, "chk", "calc", None),
    ("step", "Diff. step / wr (max)", 10, "chk", "calc", "Largest diffusion step of all species divided by wr; keep < 0.1"),
    ("check", "Check", 44, "chk", "calc", None),
    ("date", "Date run", 11, "res", "in", None),
    ("runtime", "Run time [min]", 9, "res", "in", None),
    ("fitD", "Fitted D [µm²/s]", 10, "res", "in", None),
    ("fitc", "Fitted c [nM]", 9, "res", "in", None),
    ("notes", "Result notes", 40, "res", "in", None),
]
SC = {k: L(i + 1) for i, (k, *_r) in enumerate(sim_cols)}
band_names = {"id": "Identification", "gen": "Measurement", "foc": "Focus", "out": "Output",
              "chk": "Automatic estimates and checks", "res": "Results"}
# band row 1, header row 2
col = 1
while col <= len(sim_cols):
    band = sim_cols[col - 1][3]
    end = col
    while end + 1 <= len(sim_cols) and sim_cols[end][3] == band:
        end += 1
    s.merge_cells(start_row=1, start_column=col, end_row=1, end_column=end)
    c = s.cell(row=1, column=col, value=band_names[band])
    c.fill = PatternFill("solid", fgColor=BAND[band]); c.font = WHITE_B
    c.alignment = Alignment(horizontal="center")
    for k in range(col, end + 1):
        s.cell(row=1, column=k).fill = PatternFill("solid", fgColor=BAND[band])
    col = end + 1
for i, (k, head, w, band, kind, com) in enumerate(sim_cols, start=1):
    c = s.cell(row=2, column=i, value=head)
    c.fill = HDR; c.font = WHITE_B; c.border = BOX
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if com:
        c.comment = Comment(com, "PAMsim planner")
    s.column_dimensions[L(i)].width = w
s.row_dimensions[2].height = 42
s.freeze_panes = "C3"

SP_FIRST, SP_LAST = 3, 3 + N_ROWS_SP - 1
def sp(col):  # absolute species range
    return f"Species!${col}${SP_FIRST}:${col}${SP_LAST}"

FIRST, LAST = 3, 3 + N_ROWS_SIM - 1
for r in range(FIRST, LAST + 1):
    for i, (k, head, w, band, kind, com) in enumerate(sim_cols, start=1):
        c = s.cell(row=r, column=i)
        c.border = BOX
        if kind == "in":
            c.fill = INPUT; c.font = BLUE
        else:
            c.fill = CALC; c.font = BLACK
        c.alignment = Alignment(vertical="top", wrap_text=(k in ("purpose", "check", "notes", "folder")))
    idc = f"$A{r}"
    g = lambda k: f"${SC[k]}{r}"
    s[f"{SC['nsp']}{r}"] = f'=IF({idc}="","",COUNTIF({sp("A")},{idc}))'
    s[f"{SC['ntot']}{r}"] = f'=IF({idc}="","",SUMIF({sp("A")},{idc},{sp("D")}))'
    for ch, spcol in zip(("r1", "r2", "r3", "r4"), ("Q", "R", "S", "T")):
        s[f"{SC[ch]}{r}"] = f'=IF({idc}="","",SUMIF({sp("A")},{idc},{sp(spcol)}))'
        s[f"{SC[ch]}{r}"].number_format = '0.0;-0.0;"-"'
    s[f"{SC['ph']}{r}"] = (f'=IF({idc}="","",(SUM({g("r1")}:{g("r4")})+IF({g("bg")}="Yes",{g("bgk")}*{g("ncol")},0))'
                          f'*1000*{g("dur")}/1000000)')
    s[f"{SC['ph']}{r}"].number_format = "0.00"
    s[f"{SC['mem']}{r}"] = f'=IF({idc}="","",{g("ph")}*1000000*12/1000000000)'
    s[f"{SC['mem']}{r}"].number_format = "0.000"
    s[f"{SC['step']}{r}"] = f'=IF(OR({idc}="",{g("nsp")}=0),"",_xlfn.MAXIFS({sp("U")},{sp("A")},{idc}))'
    s[f"{SC['step']}{r}"].number_format = "0.000"
    nsat = f'COUNTIFS({sp("A")},{idc},{sp("V")},"✖*")'
    nwarn = f'COUNTIFS({sp("A")},{idc},{sp("V")},"⚠*")'
    s[f"{SC['check']}{r}"] = (
        f'=IF({idc}="","",IF({g("nsp")}=0,"⚠ no species on the Species sheet",'
        f'IF({nsat}>0,"✖ "&{nsat}&" species saturated (brightness >= frequency) - see Species sheet",'
        f'IF(MIN({g("bx")},{g("by")})<8*{g("wr")},"⚠ box too small laterally (< 8·wr)",'
        f'IF(AND({g("bz")}>0,{g("bz")}<3*{g("wz")}),"⚠ box too small axially (< 3·wz)",'
        f'IF({g("mem")}>8,"⚠ more than 8 GB per file: shorten the duration and use several files",'
        f'IF({nwarn}>0,"⚠ "&{nwarn}&" species with a warning - see Species sheet","✔ OK")))))))')

# validations
dv = lambda f: DataValidation(type="list", formula1=f, allow_blank=True)
for key, ref in (("status", "Lists!$A$2:$A$7"), ("scan", "Lists!$B$2:$B$5"), ("bg", "Lists!$C$2:$C$3"),
                 ("irf", "Lists!$C$2:$C$3"), ("fmt", "Lists!$E$2:$E$4")):
    v = dv(ref); s.add_data_validation(v); v.add(f"{SC[key]}{FIRST}:{SC[key]}{LAST}")
vn = DataValidation(type="whole", operator="between", formula1="1", formula2="4", allow_blank=True)
vn.error = "Colours must be 1-4"; s.add_data_validation(vn); vn.add(f"{SC['ncol']}{FIRST}:{SC['ncol']}{LAST}")
vp = DataValidation(type="decimal", operator="greaterThan", formula1="0", allow_blank=True)
vp.error = "Must be > 0"; s.add_data_validation(vp)
for key in ("freq", "dur", "wr", "wz", "bx", "by"):
    vp.add(f"{SC[key]}{FIRST}:{SC[key]}{LAST}")
# conditional colours of the check column
rng = f"{SC['check']}{FIRST}:{SC['check']}{LAST}"
cc = SC["check"]
s.conditional_formatting.add(rng, FormulaRule(formula=[f'LEFT(${cc}{FIRST},1)="✖"'], fill=PatternFill("solid", fgColor="F8D3D3"), font=Font(name=F, color="9C1C1C", bold=True)))
s.conditional_formatting.add(rng, FormulaRule(formula=[f'LEFT(${cc}{FIRST},1)="⚠"'], fill=PatternFill("solid", fgColor="FCE6C4"), font=Font(name=F, color="8A4B00")))
s.conditional_formatting.add(rng, FormulaRule(formula=[f'LEFT(${cc}{FIRST},1)="✔"'], fill=PatternFill("solid", fgColor="D5EFD5"), font=Font(name=F, color="1E6B1E")))
st = SC["status"]
for val, colr in (("Done", "D5EFD5"), ("Analysed", "BFE3C6"), ("Running", "D6E6FA"), ("Discarded", "E3E3E3")):
    s.conditional_formatting.add(f"{st}{FIRST}:{st}{LAST}", FormulaRule(formula=[f'${st}{FIRST}="{val}"'], fill=PatternFill("solid", fgColor=colr)))
s.auto_filter.ref = f"A2:{L(len(sim_cols))}{LAST}"

# ------------------------------------------------------------------ Species
p = wb.create_sheet("Species")
sp_cols = [
    ("A", "Sim ID", 8, "in"), ("B", "Species name", 20, "in"), ("C", "D [µm²/s]", 9, "in"),
    ("D", "Molecules N", 10, "in"), ("E", "Brightness 1 [kHz]", 10, "in"), ("F", "Brightness 2 [kHz]", 10, "in"),
    ("G", "Brightness 3 [kHz]", 10, "in"), ("H", "Brightness 4 [kHz]", 10, "in"),
    ("I", "Lifetime 1 [ns]", 8, "in"), ("J", "Lifetime 2 [ns]", 8, "in"), ("K", "Lifetime 3 [ns]", 8, "in"),
    ("L", "Lifetime 4 [ns]", 8, "in"), ("M", "FRET", 11, "in"), ("N", "Notes", 30, "in"),
    ("O", "Conc. [nM]", 9, "calc"), ("P", "Max brightness / freq.", 10, "calc"),
    ("Q", "Exp. rate ch1 [kHz]", 10, "calc"), ("R", "Exp. rate ch2 [kHz]", 10, "calc"),
    ("S", "Exp. rate ch3 [kHz]", 10, "calc"), ("T", "Exp. rate ch4 [kHz]", 10, "calc"),
    ("U", "Diff. step / wr", 9, "calc"), ("V", "Check", 46, "calc"),
]
bands = [(1, 2, "Link", "id"), (3, 4, "Molecule", "gen"), (5, 8, "Brightness per colour (0 = no dye)", "foc"),
         (9, 12, "Lifetime per colour", "out"), (13, 14, "Other", "gen"), (15, 22, "Automatic estimates and checks", "chk")]
for a, b, name, band in bands:
    p.merge_cells(start_row=1, start_column=a, end_row=1, end_column=b)
    c = p.cell(row=1, column=a, value=name); c.font = WHITE_B; c.alignment = Alignment(horizontal="center")
    for k in range(a, b + 1):
        p.cell(row=1, column=k).fill = PatternFill("solid", fgColor=BAND[band])
for i, (cl, head, w, kind) in enumerate(sp_cols, start=1):
    c = p.cell(row=2, column=i, value=head)
    c.fill = HDR; c.font = WHITE_B; c.border = BOX
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    p.column_dimensions[cl].width = w
p.row_dimensions[2].height = 42
p.freeze_panes = "C3"
p["P2"].comment = Comment("Largest brightness of this species divided by the sampling frequency. Keep < 10 %.", "PAMsim planner")
p["Q2"].comment = Comment("Gaussian focus: c · brightness · (π/2)^1.5 · wr² · wz. If brightness >= frequency the saturated focus is integrated exactly (same model as the PAMsim Check panel). FRET and crosstalk are ignored.", "PAMsim planner")
p["U2"].comment = Comment("sqrt(2·D·dt) / wr with dt = 1/sampling frequency. Keep < 0.1.", "PAMsim planner")

simrng = lambda key: f"Simulations!${SC[key]}${FIRST}:${SC[key]}${LAST}"
look = lambda key, r: f"INDEX({simrng(key)},MATCH($A{r},Simulations!$A${FIRST}:$A${LAST},0))"
for r in range(SP_FIRST, SP_LAST + 1):
    for i, (cl, head, w, kind) in enumerate(sp_cols, start=1):
        c = p.cell(row=r, column=i); c.border = BOX
        c.fill = INPUT if kind == "in" else CALC
        c.font = BLUE if kind == "in" else BLACK
        c.alignment = Alignment(vertical="top", wrap_text=(cl in ("N", "V")))
    ok = f'OR($A{r}="",ISNA(MATCH($A{r},Simulations!$A${FIRST}:$A${LAST},0)))'
    vol = f'({look("bx", r)}*{look("by", r)}*IF({look("bz", r)}>0,{look("bz", r)},1))'
    freq = look("freq", r); wr = look("wr", r); wz = look("wz", r); bz = look("bz", r)
    p[f"O{r}"] = f'=IF({ok},"",IF({bz}>0,$D{r}/{vol}/1E-24/6.022E+23/1E-9,""))'
    p[f"O{r}"].number_format = "0.000"
    p[f"P{r}"] = f'=IF({ok},"",MAX($E{r}:$H{r})/{freq})'
    p[f"P{r}"].number_format = "0.0%"
    prof = f'(PI()/2*{wr}^2*IF({bz}>0,SQRT(PI()/2)*{wz},1))'
    for out, bcol in zip("QRST", "EFGH"):
        # saturated focus: integral of min(1, p*exp(-u)) over the focus, u0 = ln(p), p = brightness/frequency
        u0 = f"LN(${bcol}{r}/{freq})"
        sat3 = (f"2*PI()*{wr}^2*{wz}/2^1.5*(2/3*{u0}^1.5+SQRT({u0})"
                f"+${bcol}{r}/{freq}*SQRT(PI())/2*ERFC(SQRT({u0})))")
        sat2 = f"PI()*{wr}^2/2*({u0}+1)"
        p[f"{out}{r}"] = (f'=IF({ok},"",IF(N(${bcol}{r})<=0,0,IF(${bcol}{r}<{freq},'
                          f'$D{r}/{vol}*${bcol}{r}*{prof},'
                          f'$D{r}/{vol}*{freq}*IF({bz}>0,{sat3},{sat2}))))')
        p[f"{out}{r}"].number_format = '0.0;-0.0;"-"'
    p[f"U{r}"] = f'=IF(OR({ok},N($C{r})<=0),"",SQRT(2*$C{r}*1000000/({freq}*1000))/{wr})'
    p[f"U{r}"].number_format = "0.000"
    p[f"V{r}"] = (f'=IF($A{r}="","",IF(ISNA(MATCH($A{r},Simulations!$A${FIRST}:$A${LAST},0)),"✖ Sim ID not found on the Simulations sheet",'
                  f'IF($P{r}>=1,"✖ brightness >= sampling frequency: completely saturated (D too small, c too large)",'
                  f'IF($P{r}>0.1,"⚠ brightness > 10% of the sampling frequency: focus starts to saturate",'
                  f'IF(N($U{r})>0.1,"⚠ diffusion step > 10% of wr: raise the sampling frequency",'
                  f'IF(MAX($E{r}:$H{r})=0,"⚠ no brightness set","✔ OK"))))))')
vid = DataValidation(type="list", formula1=f"=Simulations!$A${FIRST}:$A${LAST}", allow_blank=True)
p.add_data_validation(vid); vid.add(f"A{SP_FIRST}:A{SP_LAST}")
vf = DataValidation(type="list", formula1="Lists!$D$2:$D$4", allow_blank=True)
p.add_data_validation(vf); vf.add(f"M{SP_FIRST}:M{SP_LAST}")
vpos = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
vpos.error = "Must be >= 0"; p.add_data_validation(vpos); vpos.add(f"C{SP_FIRST}:L{SP_LAST}")
rngv = f"V{SP_FIRST}:V{SP_LAST}"
p.conditional_formatting.add(rngv, FormulaRule(formula=[f'LEFT($V{SP_FIRST},1)="✖"'], fill=PatternFill("solid", fgColor="F8D3D3"), font=Font(name=F, color="9C1C1C", bold=True)))
p.conditional_formatting.add(rngv, FormulaRule(formula=[f'LEFT($V{SP_FIRST},1)="⚠"'], fill=PatternFill("solid", fgColor="FCE6C4"), font=Font(name=F, color="8A4B00")))
p.conditional_formatting.add(rngv, FormulaRule(formula=[f'LEFT($V{SP_FIRST},1)="✔"'], fill=PatternFill("solid", fgColor="D5EFD5"), font=Font(name=F, color="1E6B1E")))
p.conditional_formatting.add(f"P{SP_FIRST}:P{SP_LAST}", FormulaRule(formula=[f'AND(ISNUMBER($P{SP_FIRST}),$P{SP_FIRST}>=1)'], fill=PatternFill("solid", fgColor="F8D3D3")))
p.conditional_formatting.add(f"P{SP_FIRST}:P{SP_LAST}", FormulaRule(formula=[f'AND(ISNUMBER($P{SP_FIRST}),$P{SP_FIRST}>0.1,$P{SP_FIRST}<1)'], fill=PatternFill("solid", fgColor="FCE6C4")))
p.auto_filter.ref = f"A2:V{SP_LAST}"

# ------------------------------------------------------------------ data
base = "/Fablab 4/Users/Fabio/PhD/Projects/3C_FCCS/Simulation"
sims = [
    ("S00", "example_3C_realistic", "EXAMPLE: realistic 3-colour FCCS (brightness < 10% of the frequency)", base, "Idea", 1, 60, [("triple complex", 35, 1000, [100, 70, 50], [4, 3, 2])], 60),
    ("S01", "Simulation_800N_15D_200wr_1000wz_60s_60ns", "Just to see if the code works", base, "Planned", 2, 60, [("Species 1", 15, 800, [50, 50, 50], [4, 3, 2])], 60),
    ("S02", "Simulation_100Nx3_200wr_1000wz_60s_60ns_3colorXspecies", "To verify that no 3C cross-correlation would arise", base, "Planned", 2, 60,
     [("Species 1", 50, 800, [50, 50, 0], [4, 3, 2]), ("Species 2", 50, 100, [50, 0, 50], [4, 3, 2]), ("Species 3", 50, 100, [0, 50, 50], [4, 3, 2])], 60),
]
C = base + "/Complex"
cx = [4, 3, 2.5]
sims += [
    ("S03", "Simulation_complexes_1st_10N_200wr_1000wz_10s_60ns_1000kHz", "To test the code in a crowded environment", C, "Planned", 3, 10,
     [("Species 1", 400, 10, [1e4, 0, 0], cx), ("Species 2", 400, 10, [0, 1e4, 0], cx), ("Species 3", 400, 10, [0, 0, 1e4], cx),
      ("Species 4", 33, 10, [1e4, 1e4, 1e4], cx), ("Species 5", 35, 10, [1e4, 1e4, 0], cx), ("Species 6", 33, 10, [2e4, 1e4, 0], cx)], 60),
    ("S04", "Simulation_complexes_2nd_10N_200wr_1000wz_10s_60ns_1000kHz", "To test the code in a crowded environment", C, "Planned", 3, 10,
     [("Species 1", 400, 10, [1e4, 0, 0], cx), ("Species 2", 400, 10, [0, 7e3, 0], cx), ("Species 3", 400, 10, [0, 0, 5e3], cx),
      ("Species 4", 33, 10, [1e4, 7e3, 5e3], cx), ("Species 5", 33, 10, [2e4, 7e3, 0], cx)], 60),
    ("S05", "Simulation_complexes_3rd_10N_200wr_1000wz_10s_60ns_1000kHz", "To test whether the code would give rise to a 3C cross-correlation when wrong", C, "Planned", 3, 10,
     [("Species 1", 400, 10, [1e4, 0, 0], cx), ("Species 2", 400, 10, [0, 7e3, 0], cx), ("Species 3", 400, 10, [0, 0, 5e3], cx),
      ("Species 4", 33, 10, [2e4, 7e3, 0], cx), ("Species 5", 33, 10, [1e4, 7e3, 5e3], cx)], 60),
    ("S06", "Simulation_complexes_4th_10N_200wr_1000wz_10s_60ns_1000kHz", "To test whether the code would give rise to a 3C cross-correlation when wrong", C, "Planned", 3, 10,
     [("Species 1", 400, 10, [1e4, 0, 0], cx), ("Species 2", 400, 10, [0, 7e3, 0], cx), ("Species 3", 400, 10, [0, 0, 5e3], cx),
      ("Species 4", 33, 10, [2e4, 7e3, 0], cx), ("Species 5", 33, 10, [1e4, 0, 5e3], cx), ("Species 6", 33, 10, [0, 7e3, 1e4], cx)], 60),
    ("S07", "Crazy", "What happens to 3C if the environment is very crowded", C, "Planned", 3, 30,
     [("Species 1", 35, 100, [1e3, 700, 500], [4, 3, 2]), ("Species 2", 35, 1000, [1e3, 0, 500], [4, 3, 2]), ("Species 3", 35, 500, [1e3, 700, 0], [4, 3, 2])], 60),
    ("S08", "Crazy_2", "you need to shorten the lag time", C, "Planned", 3, 30,
     [("Species 1", 35, 100, [1e3, 700, 500], [4, 3, 2]), ("Species 2", 35, 1000, [1e3, 0, 500], [4, 3, 2]), ("Species 3", 35, 2000, [2e3, 700, 0], [4, 3, 2])], 60),
    ("S09", "Crazy_3", "", C, "Planned", 3, 30,
     [("Species 1", 35, 10, [1e3, 700, 500], [4, 3, 2]), ("Species 2", 35, 10, [1e3, 0, 500], [4, 3, 2]), ("Species 3", 35, 10, [2e3, 700, 0], [4, 3, 2])], 60),
    ("S10", "Crazy_4", "", C, "Planned", 3, 5,
     [("Species 1", 35, 1000, [1e3, 700, 500], [4, 3, 2]), ("Species 2", 35, 1000, [1e3, 0, 500], [4, 3, 2]), ("Species 3", 35, 1000, [2e3, 700, 0], [4, 3, 2])], 60),
    ("S11", "Crazy_2_checkup_final", "longer simulation with same concept as crazy_2 but better statistics", C + "/Crazy_2", "Planned", 3, 150,
     [("Species 1", 35, 200, [1e4, 7e3, 5e3], [4, 3, 2]), ("Species 2", 35, 2000, [1e4, 0, 5e3], [4, 3, 2]), ("Species 3", 35, 4000, [2e4, 7e3, 0], [4, 3, 2])], 60),
]
row_sp = SP_FIRST
for k, (sid, name, purpose, folder, status, prio, dur, species, mir) in enumerate(sims):
    r = FIRST + k
    vals = {"id": sid, "name": name, "purpose": purpose, "folder": folder, "status": status, "prio": prio,
            "bx": 5000, "by": 5000, "bz": 5000, "freq": 1000, "dur": dur, "frames": 1, "mir": mir, "scan": "Point",
            "ncol": 3, "bg": "No", "bgk": 0.2, "irf": "No", "irfw": 250, "wr": 200, "wz": 1000, "nfiles": 1, "fmt": ".sim"}
    for key, v in vals.items():
        s[f"{SC[key]}{r}"] = v
    if sid != "S00":
        s[f"{SC['notes']}{r}"] = "from Simulation_parameters.xlsx (box size assumed)"
    else:
        s[f"{SC['notes']}{r}"] = "Example row - shows the expected format"
    for (nm, D, N, b, lt) in species:
        p[f"A{row_sp}"] = sid; p[f"B{row_sp}"] = nm; p[f"C{row_sp}"] = D; p[f"D{row_sp}"] = N
        for c_, v in zip("EFGH", list(b) + [0]):
            p[f"{c_}{row_sp}"] = v
        for c_, v in zip("IJKL", list(lt) + [lt[-1]]):
            p[f"{c_}{row_sp}"] = v
        p[f"M{row_sp}"] = "No FRET"
        row_sp += 1

wb.move_sheet("Lists", offset=10)
wb.active = 1
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PAMsim_simulation_planner.xlsx")
wb.save(out)
print("saved", out, "species rows used", row_sp - SP_FIRST)
