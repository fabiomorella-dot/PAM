const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
        HeadingLevel, AlignmentType, LevelFormat, BorderStyle, Footer, PageNumber } = require("docx");

const FONT = "Arial";
const W = 9638; // A4 text width (11906 - 2*1134)
const border = { style: BorderStyle.SINGLE, size: 4, color: "C9CED6" };
const borders = { top: border, bottom: border, left: border, right: border };

const p = (text, opts = {}) => new Paragraph({ spacing: { after: 120 }, ...opts,
  children: Array.isArray(text) ? text : [new TextRun({ text, font: FONT, size: 21 })] });
const t = (text, o = {}) => new TextRun({ text, font: FONT, size: 21, ...o });
const code = (text) => new TextRun({ text, font: "Consolas", size: 19 });
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text })] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text })] });
const bullet = (runs) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 },
  children: typeof runs === "string" ? [t(runs)] : runs });
const step = (runs, ref = "steps") => new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60 },
  children: typeof runs === "string" ? [t(runs)] : runs });
const step5 = (runs) => step(runs, "steps5");
const codeBlock = (lines) => lines.map((l, i) => new Paragraph({
  shading: { type: ShadingType.CLEAR, fill: "F2F4F7", color: "auto" },
  spacing: { after: i === lines.length - 1 ? 160 : 0 }, indent: { left: 200 },
  children: [code(l)] }));

function table(headers, rows, widths, opts = {}) {
  const head = new TableRow({ tableHeader: true, children: headers.map((h, i) => new TableCell({
    borders, width: { size: widths[i], type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: "1F3A5F", color: "auto" },
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ children: [new TextRun({ text: h, bold: true, color: "FFFFFF", font: FONT, size: 19 })] })] })) });
  const body = rows.map((r, ri) => new TableRow({ children: r.map((c, i) => {
    const req = opts.reqCol === i && c.startsWith("Required");
    return new TableCell({ borders, width: { size: widths[i], type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: req ? "FDE2E2" : (ri % 2 ? "F7F9FB" : "FFFFFF"), color: "auto" },
      margins: { top: 50, bottom: 50, left: 100, right: 100 },
      children: [new Paragraph({ children: [new TextRun({ text: c, font: i === (opts.codeCol ?? -1) ? "Consolas" : FONT,
        size: 19, bold: req })] })] });
  }) }));
  return new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: widths, rows: [head, ...body] });
}
const COLW = [2300, 3300, 1100, 1300, 1638];
const COLH = ["Column", "Meaning", "Unit", "Required?", "If left blank"];
const colTable = (rows) => table(COLH, rows, COLW, { reqCol: 3 });
const gap = () => new Paragraph({ spacing: { after: 120 }, children: [] });

const children = [
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "PAMsim simulation planner", font: FONT, size: 44, bold: true, color: "1F3A5F" })] }),
  new Paragraph({ spacing: { after: 240 }, children: [new TextRun({ text: "How to fill in the Excel planner, run the simulations in PAMsim and create new planner files", font: FONT, size: 24, color: "5D5C58" })] }),

  h1("1  What the planner is"),
  p("The planner (planning/PAMsim_simulation_planner.xlsx) is an Excel workbook in which every row is one simulation. You write the parameters into it, Excel checks them and estimates the count rates, photons and memory, and PAMsim reads the file and runs the simulations - one at a time or several in a row."),
  bullet([t("Sheet "), t("How to use", { bold: true }), t(": short summary and rules of thumb.")]),
  bullet([t("Sheet "), t("Column guide", { bold: true }), t(": the column reference of chapter 4, inside the workbook.")]),
  bullet([t("Sheet "), t("Simulations", { bold: true }), t(": the planner itself - one row per simulation.")]),
  bullet([t("Sheet "), t("Crosstalk & direct exc", { bold: true }), t(": optional crosstalk and direct excitation per simulation (chapter 4.6). Off unless you switch it on.")]),
  p([t("Colour code: "), t("yellow cells with blue text", { bold: true }), t(" are your input; "), t("grey cells with black text", { bold: true }), t(" are calculated by Excel - do not type into them.")]),

  h1("2  Quick start"),
  step([t("Open the planner in Excel and write one simulation per row, starting with a "), t("Sim ID", { bold: true }), t(" (e.g. S12).")]),
  step("Fill in at least the required columns (chapter 3) and the species you need (Species 1, Species 2, ...)."),
  step("Look at the Check columns: fix every red check; orange checks bias the results slightly."),
  step([t("Save the file in Excel ("), t("Ctrl + S", { bold: true }), t(") - only then are the checks stored in the file.")]),
  step([t("In PAMsim click "), t("Load from planner...", { bold: true }), t(", choose the file, select the simulations and click "), t("Run selected", { bold: true }), t(" (or double-click one to load it into the editor).")]),
  step([t("Open the .sim files in PAM: "), t("Load TCSPC data -> Pam Simulation Files", { bold: true }), t(".")]),

  h1("3  Do I have to fill in every column?"),
  p("No. PAMsim uses a default value for every empty cell. A few columns must be filled in, because their defaults would silently give a different simulation than you intend:"),
  table(["Must be filled in", "Why"], [
    ["Sim ID", "Rows without a Sim ID are skipped."],
    ["Colours", "The default is 1. With 1 colour, brightness 2 and 3 are ignored - write 3 for 3-colour FCCS."],
    ["Duration [s]", "The default is 10 s."],
    ["Species: D [µm²/s]", "The default is 1 µm²/s."],
    ["Species: Molecules N", "Empty means 0 molecules - the species is not simulated."],
    ["Species: Brightness 1/2/3", "Empty means 0 = the species carries no dye of this colour."],
  ], [3000, 6638]),
  gap(),
  p("Everything else is optional (defaults in chapter 4). The formulas of the planner use the same defaults for empty cells as PAMsim, so the estimates are right even with empty cells. Purpose, Status, Priority and all Results columns are only for your own bookkeeping - PAMsim does not use them."),

  h1("4  Column reference"),
  h2("4.1  Identification"),
  colTable([
    ["Sim ID", "Unique short name of the simulation (e.g. S12)", "-", "Required", "row is skipped"],
    ["File name", "Name of the simulation: its folder <Output folder>/<name>/ and its files <name>_1.sim, <name>_2.sim, ...", "-", "Optional", "the Sim ID"],
    ["Purpose / question", "What you want to learn from this simulation", "-", "Not used", "-"],
    ["Output folder", "Main folder; each simulation gets its own subfolder in it (created automatically). Must exist on the PC that runs PAMsim", "-", "Optional", "PAMsim's output folder"],
    ["Status", "Idea / Planned / Running / Done / Analysed / Discarded", "-", "Not used", "-"],
    ["Priority", "Your ranking (1 = highest)", "-", "Not used", "-"],
  ]),
  h2("4.2  Measurement"),
  colTable([
    ["Box x, y, z", "Size of the simulation box; z = 0 gives a 2D (membrane) simulation", "nm", "Optional", "5000 each"],
    ["Sampling freq.", "Time resolution of the random walk (time step = 1/frequency)", "kHz", "Optional", "1000"],
    ["Duration", "Simulated measurement time per file", "s", "Required", "10"],
    ["Frames", "Number of frames (relevant for scanning)", "-", "Optional", "1"],
    ["Microtime range", "TCSPC range (PIE period)", "ns", "Optional", "80"],
    ["Scan type", "Point / Raster scan / Line scan / Circle scan", "-", "Optional", "Point"],
    ["Colours", "Number of colours = PIE lasers = detection channels (1-3)", "-", "Required", "1"],
    ["Background?", "Yes / No: add uncorrelated background", "-", "Optional", "No"],
    ["Background", "Background count rate per channel", "kHz", "Optional", "0"],
    ["IRF? / IRF width", "Simulate an instrument response function", "ps", "Optional", "No / 250"],
  ]),
  h2("4.3  Focus per colour and Förster radii"),
  p("Every colour (laser) has its own focus: its size wr / wz and its position dX / dY / dZ. The expected count rate of each channel is calculated with the focus of that colour, and PAMsim simulates each laser with its own focus. Shifted foci (dX/dY/dZ not 0) reduce the overlap and therefore the cross-correlation amplitude - useful to simulate an imperfectly aligned setup."),
  colTable([
    ["wr 1, wr 2, wr 3", "Lateral 1/e² radius of the focus of colour 1, 2, 3", "nm", "Optional", "200"],
    ["wz 1, wz 2, wz 3", "Axial 1/e² radius of the focus of colour 1, 2, 3", "nm", "Optional", "1000"],
    ["dX, dY, dZ 1/2/3", "Shift of the focus of each colour from the box centre", "nm", "Optional", "0 (foci overlap)"],
    ["R0 1→2, 1→3, 2→3", "Förster radius of each dye pair (donor colour → acceptor colour)", "Å or nm", "Optional", "63, 51, 68"],
  ]),
  h2("4.4  Species blocks (Species 1, Species 2, ...)"),
  p("Each simulation row has several species blocks side by side. Fill in one block per species and leave unused blocks empty. A block counts as used as soon as it has a name or a number of molecules."),
  colTable([
    ["Name", "Name of the species (e.g. triple complex)", "-", "Optional", "Species 1, 2, ..."],
    ["D", "Diffusion coefficient", "µm²/s", "Required", "1"],
    ["Molecules N", "Number of molecules in the box (the concentration is shown)", "-", "Required", "0 = absent"],
    ["Brightness 1/2/3", "Count rate of one molecule in the focus centre for each colour; 0 = no dye of this colour", "kHz", "Required", "0"],
    ["Lifetime 1/2/3", "Fluorescence lifetime of the dye of each colour", "ns", "Optional", "4"],
    ["FRET", "No FRET / Static FRET / Dynamic FRET", "-", "Optional", "No FRET"],
    ["R 1→2, 1→3, 2→3", "Dye distance for FRET between these two colours (same unit as R0)", "Å or nm", "Optional", "no FRET for this pair"],
    ["E 1→2, ... (grey)", "FRET efficiency E = 1/(1 + (R/R0)^6), calculated", "-", "Calculated", "-"],
    ["Conc. (grey)", "Concentration of the species, calculated", "nM", "Calculated", "-"],
    ["Check (grey)", "Check of this species (see chapter 6)", "-", "Calculated", "-"],
  ]),
  p([t("Example - a green-red complex in a 3-colour experiment: "), t("Brightness 1 = 0, Brightness 2 = 70, Brightness 3 = 50", { bold: true }), t(".")]),
  p([t("FRET happens only between dyes that are present (brightness > 0) and only for the pairs with a distance R. Example: a species with dyes 1 and 2 and FRET between them gets "), t("FRET = Static FRET, R 1→2 = 50", { bold: true }), t(", and R 1→3 / R 2→3 stay empty.")]),
  h2("4.5  Totals, output and results"),
  colTable([
    ["Species used (grey)", "Number of filled species blocks", "-", "Calculated", "-"],
    ["Exp. rate ch1-3 (grey)", "Expected count rate per channel, incl. saturation, crosstalk and direct excitation (FRET ignored)", "kHz", "Calculated", "-"],
    ["Photons / Memory (grey)", "Expected photons and memory per file (~12 bytes per photon)", "M / GB", "Calculated", "-"],
    ["Crosstalk / dir. exc. (grey)", "Whether crosstalk and/or direct excitation are switched on for this simulation (chapter 4.6)", "-", "Calculated", "-"],
    ["Check (grey)", "Overall check of the simulation", "-", "Calculated", "-"],
    ["Number of files", "Independent repeats with the same parameters", "-", "Optional", "1"],
    ["Seed", "Random seed; file k uses seed + k - 1", "-", "Optional", "random"],
    ["Format", ".sim (PAM) / .npz (numpy) / both", "-", "Optional", ".sim"],
    ["Date run ... Result notes", "Your notes after running and analysing", "-", "Not used", "-"],
  ]),

  h2("4.6  Crosstalk and direct excitation (sheet Crosstalk & direct exc)"),
  p("Crosstalk and direct excitation are an extra option on their own sheet, so the Simulations sheet stays as it is. They are off for every simulation until you switch them on:"),
  step([t("Go to the sheet "), t("Crosstalk & direct exc", { bold: true }), t(" and pick the "), t("Sim ID", { bold: true }), t(" of the simulation in column A (drop-down). File name and Colours are looked up for you.")], "steps46"),
  step([t("Set "), t("Crosstalk?", { bold: true }), t(" and/or "), t("Direct exc.?", { bold: true }), t(" to "), t("Yes", { bold: true }), t(" and type the values as fractions (0.05 = 5 %).")], "steps46"),
  step("Save the file. The column Crosstalk / dir. exc. on the Simulations sheet now shows what is switched on, and the expected count rates include it.", "steps46"),
  p("A simulation that is not listed on this sheet, or whose switches are No or empty, is simulated without crosstalk and direct excitation - the values of that row are kept but ignored, so you can switch them on and off without retyping them. One row per simulation; the values apply to all species of that simulation."),
  colTable([
    ["Sim ID", "Sim ID of a simulation on the Simulations sheet (drop-down)", "-", "Required", "row is ignored"],
    ["Crosstalk?", "Yes = simulate the crosstalk values of this row", "-", "Optional", "No"],
    ["Crosstalk 1→2, 1→3, 2→3", "Photons of dye 1 (2) detected in channel 2 (3), as a fraction of that dye's photons in its own channel", "fraction", "Optional", "0"],
    ["Direct exc.?", "Yes = simulate the direct excitation values of this row", "-", "Optional", "No"],
    ["Direct exc. 1→2, 1→3, 2→3", "Excitation of dye 2 (3) by laser 1 (2), as a fraction of its excitation by its own laser", "fraction", "Optional", "0"],
    ["Check (grey)", "on / off and warnings (chapter 6)", "-", "Calculated", "-"],
  ]),
  gap(),
  p([t("Example: "), t("Crosstalk 1→2 = 0.08", { bold: true }), t(" - for every 100 photons of dye 1 in channel 1, 8 more photons of dye 1 appear in channel 2. "),
     t("Direct exc. 2→3 = 0.06", { bold: true }), t(" - laser 2 excites dye 3 with 6 % of the excitation of laser 3, so a dye-3 molecule gives 6 % of its brightness in the laser-2 window (in the focus of laser 2).")]),
  bullet("The brightness on the Simulations sheet keeps its meaning: the count rate of a dye in its own channel with its own laser. Crosstalk and direct excitation add photons on top of it."),
  bullet("Direct excitation only affects species that carry the excited dye (brightness > 0), e.g. an acceptor-only species is also directly excited."),
  bullet("Pairs with a colour above Colours are ignored (with 2 colours only 1→2 is used)."),
  bullet("Example row: S00 is listed with realistic values but switched off - set its switches to Yes to try it."),

  h1("5  Running the simulations in PAMsim"),
  step5([t("Click "), t("Load from planner...", { bold: true }), t(" (top of the window) and choose the planner file.")]),
  step5("A list shows all simulations with their check; red rows have a red check."),
  step5([t("To check or change one simulation first: double-click it (or "), t("Load into editor", { bold: true }), t("). All values appear in the PAMsim window; press Start.")]),
  step5([t("To run several: select them with Ctrl + click (single rows) or Shift + click (a range) and click "), t("Run selected", { bold: true }), t(".")]),
  p("PAMsim runs the selected simulations one after another, each with exactly the parameters of its own row - different boxes, durations, species, brightness and FRET are no problem. The Log tab shows --- S01 ---, --- S02 ---, ... with the count rates and the written files. Stop ends the whole sequence."),
  bullet([t("Each simulation is written into its own folder named after its file name, e.g. "), t("C:\\Sims\\Crazy_2\\Crazy_2_1.sim", { font: "Consolas", size: 19 }), t(" - the folder is created automatically. Switch this off in PAMsim's Output box (Own folder per simulation) to write all files into the output folder directly.")]),
  bullet("Every simulation needs its own file name - two rows with the same name and output folder write into the same folder and overwrite each other's files."),
  bullet("Characters that Windows does not allow in names (< > : \" / \\ | ? *) are replaced by _."),
  bullet("If the output folder of a row does not exist on this PC, the files are written to the folder set in PAMsim; the Log says so."),
  bullet("PAMsim asks before running simulations that have a red check."),
  bullet("The list in PAMsim has a column Crosstalk / dir. exc. that shows what is switched on for each simulation."),
  h2("5.1  The info file written after every simulation"),
  p([t("When a file is finished, PAMsim writes a text file next to it: "), t("<name>_1_info.txt", { font: "Consolas", size: 19 }), t(" next to "), t("<name>_1.sim", { font: "Consolas", size: 19 }), t(" (also when you start a simulation from the editor). It lists:")]),
  bullet("File name, Duration, Microtime range, Background (yes / no), Number of species"),
  bullet("FRET (no / static / dynamic) and, with FRET, the Förster radii R0 and the distances R (with the FRET efficiency E)"),
  bullet("Crosstalk (yes / no) and Direct excitation (yes / no), with the values when yes"),
  bullet("For every species: name, number of colours (the dyes it carries), diffusion coefficient, concentration, brightness and lifetime. With one colour the values are written without a number; with several colours they are numbered by colour: Diffusion coefficient 1, Concentration 1, Brightness 1, Lifetime 1, Diffusion coefficient 2, ..."),
  bullet("At the end: date, planner Sim ID, seed, run time, measured count rates and the files written."),
  ...codeBlock(["Species 3", "  Name:                      green-red", "  Number of colours:         2 (colours 2, 3)",
    "  Diffusion coefficient 2:   35 um^2/s", "  Concentration 2:           2.657 nM", "  Brightness 2:              70 kHz",
    "  Lifetime 2:                3 ns", "  Diffusion coefficient 3:   35 um^2/s", "  ..."]),

  h1("6  What the checks mean"),
  table(["Check", "Meaning and what to do"], [
    ["✔ OK", "Nothing to fix."],
    ["✖ saturated (B ≥ freq.)", "Brightness is at least the sampling frequency: the excitation saturates completely, D comes out too small and the concentration too large. Lower the brightness or raise the sampling frequency."],
    ["⚠ B > 10% of freq.", "The focus starts to saturate. Keep the brightness below 10% of the sampling frequency (< 100 kHz at 1000 kHz)."],
    ["⚠ step > 10% of wr", "One diffusion step sqrt(2·D/frequency) is large compared with the focus. Raise the sampling frequency."],
    ["⚠ no brightness", "All brightness values of the species are 0 - it would be invisible."],
    ["⚠ uses a colour above Colours", "The species has a brightness in colour 3 (or 2) but Colours is smaller - that colour is ignored. Increase Colours."],
    ["⚠ FRET needs ≥ 2 colours / set R", "FRET is selected but Colours < 2 or no distance R is given."],
    ["⚠ box too small", "Use at least 8·wr laterally and 3·wz axially."],
    ["⚠ > 8 GB per file", "Too many photons for one file: shorten the duration and use several files instead."],
    ["⚠ crosstalk sheet: ...", "The row of this simulation on the sheet Crosstalk & direct exc has a warning - see its Check column."],
  ], [3000, 6638]),
  p([t("Checks on the sheet "), t("Crosstalk & direct exc", { bold: true }), t(":")]),
  table(["Check", "Meaning and what to do"], [
    ["✔ on: crosstalk + direct excitation", "Switched on; the values are used."],
    ["– off", "Both switches are No or empty: this simulation has no crosstalk and no direct excitation."],
    ["✖ Sim ID not found", "The Sim ID does not exist on the Simulations sheet (typo, or the simulation was renamed)."],
    ["✖ Sim ID entered twice", "Only the first row of a Sim ID is used - delete the other one."],
    ["⚠ needs ≥ 2 colours", "With 1 colour there is no other channel or laser: the row is ignored."],
    ["⚠ value > 1", "Write fractions: 0.05 for 5 %."],
    ["⚠ switched on but all values are 0", "Fill in the values or set the switch to No."],
    ["⚠ 1→3 and 2→3 ignored", "Colours is 2, so only 1→2 is used."],
  ], [3000, 6638]),

  h1("7  Settings that are not in the planner"),
  p("Detection efficiencies, bleaching, anisotropy, dynamic FRET rates and barrier/quenching maps are not columns of the planner (PAMsim uses its defaults: detection efficiency 1, no bleaching, no anisotropy). The same holds for crosstalk or direct excitation that differ between species of one simulation, and for the reverse directions (e.g. dye 2 into channel 1). For such simulations load the row into the editor, set these values in the tabs of PAMsim and press Start; Save setup... stores the complete setup as a JSON file."),

  h1("8  Creating new planner files (make_planner.py)"),
  p("You only need make_planner.py to create a new, differently sized planner - for normal planning just edit the existing Excel file. Open a terminal (PowerShell) in the planning folder:"),
  ...codeBlock(["cd C:\\Users\\Rosario\\PAM\\planning"]),
  p("and run one of the following commands (they need openpyxl: py -3 -m pip install openpyxl):"),
  table(["Command", "Creates"], [
    ["python make_planner.py -o my_planner.xlsx", "a new planner with the example rows S00-S11"],
    ["python make_planner.py --empty -o my_planner.xlsx", "an empty planner (no example rows)"],
    ["python make_planner.py --species 10 -o my_planner.xlsx", "10 species blocks per simulation instead of 6"],
    ["python make_planner.py --rows 200 -o my_planner.xlsx", "200 prepared simulation rows instead of 60"],
    ["python make_planner.py --empty --species 8 --rows 150 -o big.xlsx", "options combined: empty, 8 species, 150 rows"],
    ["python make_planner.py --from old.xlsx -o new.xlsx", "the newest layout with all your simulations copied from old.xlsx"],
  ], [5400, 4238], { codeCol: 0 }),
  gap(),
  table(["Option", "What it does"], [
    ["-o name.xlsx", "Name of the new file (created in the current folder). Without -o the default name PAMsim_simulation_planner.xlsx is used."],
    ["--empty", "Leave out the example rows - all input cells start empty; formulas and checks are in place."],
    ["--species N", "Number of species blocks per simulation row (default 6). The totals add up all N species."],
    ["--rows N", "Number of prepared simulation rows with formulas and formatting (default 60)."],
    ["--force", "Overwrite an existing file. Without it the program stops if the file exists - so a filled-in planner cannot be lost by accident."],
    ["--from old.xlsx", "Copy every input cell of an existing planner (simulations, species, crosstalk sheet) into the new file, matched by column name, instead of the example rows. Use it to bring a filled-in planner to the newest layout, e.g. to get the crosstalk sheet. The old file is not changed."],
  ], [2400, 7238], { codeCol: 0 }),
  gap(),
  p("The calculated (grey) cells fill in when the new file is opened in Excel; save it once in Excel before loading it into PAMsim. PAMsim reads planners with any number of species blocks."),

  h1("9  Troubleshooting"),
  table(["Problem", "Solution"], [
    ["'Reading Excel files needs openpyxl'", "Close PAMsim and run  py -3 -m pip install openpyxl  (or Update_PAMsim.bat). Newer PAMsim versions offer to install it themselves."],
    ["Check column empty in PAMsim's list", "The file was not saved in Excel after the last change (or was created by make_planner.py and never opened). Open it in Excel, press Ctrl + S."],
    ["'folder not found' in the Log", "The output folder of the row does not exist on this PC (e.g. a Mac path). Correct it in the planner, or the files go to PAMsim's folder."],
    ["Fitted D too small, concentration too large", "The brightness was too close to the sampling frequency (saturated focus) - see chapter 6."],
    ["A species seems missing", "Its Molecules N is empty or 0, or Colours is too small for its brightness columns."],
    ["Crosstalk / direct excitation not simulated", "On the sheet Crosstalk & direct exc the switch must be Yes, the Sim ID must match the Simulations sheet, and Colours must be at least 2. The info file (<name>_1_info.txt) says what was simulated."],
    ["#DIV/0! in the planner", "Only in planners made before this version, when Box, Sampling frequency or wr/wz are empty. Fill them in, or copy your rows into a new planner (python make_planner.py --empty -o new.xlsx)."],
  ], [3600, 6038]),
];

const doc = new Document({
  creator: "PAMsim", title: "PAMsim simulation planner - guide",
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: FONT, color: "1F3A5F" }, paragraph: { spacing: { before: 320, after: 140 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: FONT, color: "2A62A8" }, paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
    { reference: "steps5", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
    { reference: "steps46", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { page: { margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "PAMsim planner guide  -  page ", font: FONT, size: 16, color: "777777" }),
                 new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: "777777" })] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(process.argv[2], b); console.log("written", process.argv[2]); });
