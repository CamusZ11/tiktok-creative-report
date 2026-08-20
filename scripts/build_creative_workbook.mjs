import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const args = process.argv.slice(2);
const inputPath = args[0];
const existingWorkbookPath = args.length >= 4 ? args[1] : "";
const metadataSourcePath = args.length >= 4 ? args[2] : "";
const outputPath = args.length >= 4 ? args[3] : args[1];
if (!inputPath || !outputPath) {
  throw new Error(
    "Usage: build_creative_workbook.mjs <payload.json> [existing.xlsx] [metadata-source.xlsx] <output.xlsx>",
  );
}

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
if (!Array.isArray(payload.headers) || payload.headers.length !== 24 || !Array.isArray(payload.rows)) {
  throw new Error("Invalid creative report payload");
}

const metadataHeaders = [
  "创意素材",
  "商品名称",
  "商品 ID",
  "TikTok 账号",
  "授权类型",
  "发布时间",
  "广告计划名称",
];
const metadataByPostId = new Map();

async function workbookRows(workbookPath, preferredSheetNames) {
  if (!workbookPath) return [];
  try {
    await fs.access(workbookPath);
  } catch {
    return [];
  }
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
  const sheet = preferredSheetNames
    .map((name) => workbook.worksheets.items.find((candidate) => candidate.name === name))
    .find(Boolean) ?? workbook.worksheets.getItemAt(0);
  return sheet.getUsedRange(true).values;
}

function overlayMetadata(postId, values) {
  const key = String(postId ?? "").trim();
  if (!key) return;
  const current = metadataByPostId.get(key) ?? {};
  for (const [header, value] of Object.entries(values)) {
    if (value === null || value === "" || value === undefined) continue;
    if (["商品名称", "商品 ID", "广告计划名称"].includes(header) && current[header] && current[header] !== value) {
      current[header] = [...new Set(
        [current[header], value]
          .flatMap((item) => String(item).split(" | "))
          .map((item) => item.trim())
          .filter(Boolean),
      )].join(" | ");
    } else {
      current[header] = value;
    }
  }
  metadataByPostId.set(key, current);
}

const sourceValues = await workbookRows(metadataSourcePath, ["11_creative_daily_report", "创意明细", "Sheet1"]);
if (sourceValues.length > 1) {
  const sourceHeaders = sourceValues[0].map((value) => String(value ?? "").trim());
  const sourceIndex = Object.fromEntries(sourceHeaders.map((header, index) => [header, index]));
  if (sourceIndex["作品 ID"] !== undefined) {
    for (const row of sourceValues.slice(1)) {
      overlayMetadata(
        row[sourceIndex["作品 ID"]],
        Object.fromEntries(metadataHeaders.map((header) => [header, row[sourceIndex[header]]])),
      );
    }
  } else {
    for (const row of sourceValues.slice(1)) {
      overlayMetadata(row[sourceIndex["Post ID"]], {
        "创意素材": row[sourceIndex.Creative],
        "TikTok 账号": row[sourceIndex["TikTok account"]],
        "探索状态": row[sourceIndex.Status],
        "发布时间": row[sourceIndex["Time posted"]],
      });
    }
  }
}

const existingValues = await workbookRows(existingWorkbookPath, ["创意明细", "11_creative_daily_report"]);
if (existingValues.length > 1) {
  const existingHeaders = existingValues[0].map((value) => String(value ?? "").trim());
  const existingIndex = Object.fromEntries(existingHeaders.map((header, index) => [header, index]));
  for (const row of existingValues.slice(1)) {
    overlayMetadata(
      row[existingIndex["作品 ID"]],
      Object.fromEntries(metadataHeaders.map((header) => [header, row[existingIndex[header]]])),
    );
  }
}

const enrichedRows = payload.rows.map((row) => {
  const enriched = { ...row };
  const cached = metadataByPostId.get(String(row?.["作品 ID"] ?? "").trim()) ?? {};
  for (const header of metadataHeaders) {
    if ((enriched[header] === null || enriched[header] === "" || enriched[header] === undefined) && cached[header] !== undefined) {
      enriched[header] = cached[header];
    }
  }
  return enriched;
});

const textIdentifierHeaders = new Set(["作品 ID", "商品 ID"]);
const outputValue = (header, value) => {
  if (header === "日期" && value) return new Date(`${String(value)}T12:00:00Z`);
  if (textIdentifierHeaders.has(header)) return "";
  return value ?? "";
};
const identifierFormula = (value) => {
  if (value === null || value === "" || value === undefined) return "";
  return `="${String(value).replaceAll('"', '""')}"`;
};

const matrix = [
  payload.headers,
  ...enrichedRows.map((row) => payload.headers.map((header) => outputValue(header, row?.[header]))),
];
let workbook = Workbook.create();
if (existingWorkbookPath) {
  try {
    await fs.access(existingWorkbookPath);
    workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(existingWorkbookPath));
  } catch {
    // A missing existing workbook is the normal first-run case.
  }
}
const existingSheet = ["11_creative_daily_report", "创意明细"]
  .map((name) => workbook.worksheets.items.find((candidate) => candidate.name === name))
  .find(Boolean);
const canReuseTargetSheet = existingSheet && workbook.worksheets.items.length > 1;
if (existingSheet && !canReuseTargetSheet) {
  workbook = Workbook.create();
}
const sheet = canReuseTargetSheet
  ? existingSheet
  : workbook.worksheets.add(existingSheet?.name ?? "11_creative_daily_report");
if (canReuseTargetSheet) sheet.reset();
sheet.showGridLines = false;
sheet.getRange("B:J").format.numberFormat = "@";
sheet.getRangeByIndexes(0, 0, matrix.length, payload.headers.length).values = matrix;
if (enrichedRows.length) {
  sheet.getRangeByIndexes(1, 2, enrichedRows.length, 1).formulas = enrichedRows.map((row) => [
    identifierFormula(row?.["作品 ID"]),
  ]);
  sheet.getRangeByIndexes(1, 4, enrichedRows.length, 1).formulas = enrichedRows.map((row) => [
    identifierFormula(row?.["商品 ID"]),
  ]);
}
sheet.getRange("A1:X1").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange("A:X").format.verticalAlignment = "center";
sheet.getRange("A:A").format.numberFormat = "yyyy-mm-dd";
sheet.getRange("K:K").format.numberFormat = "#,##0.00";
sheet.getRange("L:L").format.numberFormat = "#,##0";
sheet.getRange("M:N").format.numberFormat = "#,##0.00";
sheet.getRange("O:P").format.numberFormat = "#,##0";
sheet.getRange("Q:X").format.numberFormat = "0.00%";
sheet.getRange(`A1:X${matrix.length}`).format.borders = {
  preset: "insideHorizontal",
  style: "thin",
  color: "#E5E7EB",
};
sheet.getRange("A:A").format.columnWidth = 13;
sheet.getRange("B:B").format.columnWidth = 30;
sheet.getRange("C:C").format.columnWidth = 20;
sheet.getRange("D:D").format.columnWidth = 28;
sheet.getRange("E:E").format.columnWidth = 20;
sheet.getRange("F:J").format.columnWidth = 18;
sheet.getRange("K:X").format.columnWidth = 15;
sheet.getRange("A1:X1").format.rowHeight = 34;
sheet.freezePanes.freezeRows(1);
sheet.tables.add(`A1:X${matrix.length}`, true, "CreativeDetails");
if (enrichedRows.length) {
  sheet.getRange(`A2:A${matrix.length}`).format.numberFormat = "yyyy-mm-dd";
  sheet.getRange(`C2:C${matrix.length}`).format.numberFormat = "@";
  sheet.getRange(`E2:E${matrix.length}`).format.numberFormat = "@";
}

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
