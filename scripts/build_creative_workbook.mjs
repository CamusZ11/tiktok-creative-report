import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("Usage: build_creative_workbook.mjs <payload.json> <output.xlsx>");
}

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
if (!Array.isArray(payload.headers) || payload.headers.length !== 23 || !Array.isArray(payload.rows)) {
  throw new Error("Invalid creative report payload");
}

const matrix = [
  payload.headers,
  ...payload.rows.map((row) => payload.headers.map((header) => row?.[header] ?? "")),
];
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("创意明细");
sheet.showGridLines = false;
sheet.getRangeByIndexes(0, 0, matrix.length, payload.headers.length).values = matrix;
sheet.getRange("A1:W1").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange("A:W").format.verticalAlignment = "center";
sheet.getRange("A:I").format.numberFormat = "@";
sheet.getRange("J:J").format.numberFormat = "#,##0.00";
sheet.getRange("K:K").format.numberFormat = "#,##0";
sheet.getRange("L:M").format.numberFormat = "#,##0.00";
sheet.getRange("N:O").format.numberFormat = "#,##0";
sheet.getRange("P:W").format.numberFormat = "0.00%";
sheet.getRange(`A1:W${matrix.length}`).format.borders = {
  preset: "insideHorizontal",
  style: "thin",
  color: "#E5E7EB",
};
sheet.getRange("A:A").format.columnWidth = 30;
sheet.getRange("B:B").format.columnWidth = 20;
sheet.getRange("C:C").format.columnWidth = 28;
sheet.getRange("D:D").format.columnWidth = 20;
sheet.getRange("E:I").format.columnWidth = 18;
sheet.getRange("J:W").format.columnWidth = 15;
sheet.getRange("A1:W1").format.rowHeight = 34;
sheet.freezePanes.freezeRows(1);
sheet.tables.add(`A1:W${matrix.length}`, true, "CreativeDetails");

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 20 },
});
if (errors.ndjson?.includes('"kind":"match"')) {
  throw new Error("Workbook formula error detected");
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
