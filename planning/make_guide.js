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
const step = (runs) => new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { after: 60 },
  children: typeof runs === "string" ? [t(runs)] : runs });
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
  p("Everything else is optional (defaults in chapter 4). Purpose, Status, Priority and all Results columns are only for your own bookkeeping - PAMsim does not use them."),

  h1("4  Column reference"),
  h2("4.1  Identification"),
  colTable([
    ["Sim ID", "Unique short name of the simulation (e.g. S12)", "-", "Required", "row is skipped"],
    ["File name", "Files are written as <name>_1.sim, <name>_2.sim, ...", "-", "Optional", "the Sim ID"],
    ["Purpose / question", "What you want to learn from this simulation", "-", "Not used", "-"],
    ["Output folder", "Folder for the files; must exist on the PC that runs PAMsim", "-", "Optional", "PAMsim's output folder"],
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
  h2("4.3  Focus and Förster radii"),
  colTable([
    ["wr", "Lateral 1/e² radius of the focus (all colours)", "nm", "Optional", "200"],
    ["wz", "Axial 1/e² radius of the focus (all colours)", "nm", "Optional", "1000"],
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
    ["R 1→2, 1→3, 2→3", "Dye distances for FRET (same unit as R0)", "Å or nm", "Optional", "50"],
    ["E 1→2, ... (grey)", "FRET efficiency E = 1/(1 + (R/R0)^6), calculated", "-", "Calculated", "-"],
    ["Conc. (grey)", "Concentration of the species, calculated", "nM", "Calculated", "-"],
    ["Check (grey)", "Check of this species (see chapter 6)", "-", "Calculated", "-"],
  ]),
  p([t("Example - a green-red complex in a 3-colour experiment: "), t("Brightness 1 = 0, Brightness 2 = 70, Brightness 3 = 50", { bold: true }), t(".")]),
  h2("4.5  Totals, output and results"),
  colTable([
    ["Species used (grey)", "Number of filled species blocks", "-", "Calculated", "-"],
    ["Exp. rate ch1-3 (grey)", "Expected count rate per channel, incl. saturation (FRET and crosstalk ignored)", "kHz", "Calculated", "-"],
    ["Photons / Memory (grey)", "Expected photons and memory per file (~12 bytes per photon)", "M / GB", "Calculated", "-"],
    ["Check (grey)", "Overall check of the simulation", "-", "Calculated", "-"],
    ["Number of files", "Independent repeats with the same parameters", "-", "Optional", "1"],
    ["Seed", "Random seed; file k uses seed + k - 1", "-", "Optional", "random"],
    ["Format", ".sim (PAM) / .npz (numpy) / both", "-", "Optional", ".sim"],
    ["Date run ... Result notes", "Your notes after running and analysing", "-", "Not used", "-"],
  ]),

  h1("5  Running the simulations in PAMsim"),
  step([t("Click "), t("Load from planner...", { bold: true }), t(" (top of the window) and choose the planner file.")]),
  step("A list shows all simulations with their check; red rows have a red check."),
  step([t("To check or change one simulation first: double-click it (or "), t("Load into editor", { bold: true }), t("). All values appear in the PAMsim window; press Start.")]),
  step([t("To run several: select them with Ctrl + click (single rows) or Shift + click (a range) and click "), t("Run selected", { bold: true }), t(".")]),
  p("PAMsim runs the selected simulations one after another, each with exactly the parameters of its own row - different boxes, durations, species, brightness and FRET are no problem. The Log tab shows --- S01 ---, --- S02 ---, ... with the count rates and the written files. Stop ends the whole sequence."),
  bullet("Every simulation needs its own file name (or its own folder) - two rows with the same name and folder overwrite each other's files."),
  bullet("If the output folder of a row does not exist on this PC, the files are written to the folder set in PAMsim; the Log says so."),
  bullet("PAMsim asks before running simulations that have a red check."),

  h1("6  What the checks mean"),
  table(["Check", "Meaning and what to do"], [
    ["✔ OK", "Nothing to fix."],
    ["✖ saturated (B ≥ freq.)", "Brightness is at least the sampling frequency: the excitation saturates completely, D comes out too small and the concentration too large. Lower the brightness or raise the sampling frequency."],
    ["⚠ B > 10% of freq.", "The focus starts to saturate. Keep the brightness below 10% of the sampling frequency (< 100 kHz at 1000 kHz)."],
    ["⚠ step > 10% of wr", "One diffusion step sqrt(2·D/frequency) is large compared with the focus. Raise the sampling frequency."],
    ["⚠ no brightness", "All brightness values of the species are 0 - it would be invisible."],
    ["⚠ FRET needs ≥ 2 colours / set R", "FRET is selected but Colours < 2 or no distance R is given."],
    ["⚠ box too small", "Use at least 8·wr laterally and 3·wz axially."],
    ["⚠ > 8 GB per file", "Too many photons for one file: shorten the duration and use several files instead."],
  ], [3000, 6638]),

  h1("7  Settings that are not in the planner"),
  p("Crosstalk, detection efficiencies, bleaching, anisotropy, dynamic FRET rates and barrier/quenching maps are not columns of the planner (PAMsim uses its defaults: no crosstalk, detection efficiency 1, no bleaching, no anisotropy). For such simulations load the row into the editor, set these values in the tabs of PAMsim and press Start; Save setup... stores the complete setup as a JSON file."),

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
  ], [5400, 4238], { codeCol: 0 }),
  gap(),
  table(["Option", "What it does"], [
    ["-o name.xlsx", "Name of the new file (created in the current folder). Without -o the default name PAMsim_simulation_planner.xlsx is used."],
    ["--empty", "Leave out the example rows - all input cells start empty; formulas and checks are in place."],
    ["--species N", "Number of species blocks per simulation row (default 6). The totals add up all N species."],
    ["--rows N", "Number of prepared simulation rows with formulas and formatting (default 60)."],
    ["--force", "Overwrite an existing file. Without it the program stops if the file exists - so a filled-in planner cannot be lost by accident."],
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
