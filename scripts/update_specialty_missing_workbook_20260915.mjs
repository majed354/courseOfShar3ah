#!/usr/bin/env node

import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "/Users/majd/Desktop/codex/courseOfShar3ah-main";
const workbookPath = `${root}/قائمة_المقررات_التخصصية_المفقودة_2026-09-10.xlsx`;
const coveragePath = `${root}/tmp/eight-course-completion-20260915/specialty-coverage.json`;
const coverage = JSON.parse(await fs.readFile(coveragePath, "utf8"));
const recoveredCodes = new Set(coverage.recovered_codes);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));

const summary = workbook.worksheets.getItem("الملخص");
const identities = workbook.worksheets.getItem("المقررات المفقودة");
const occurrences = workbook.worksheets.getItem("مواضع الخطط");

const summaryValues = summary.getRange("A1:I21").values;
summaryValues[2][0] =
  "المصدر: data.json في مستودع التوصيفات، بتاريخ 2026-09-15. النطاق: رموز 200* والاستثناء القديم 101221-2، دون الرسالة والاختبار الشامل أو مقررات الأقسام الخارجية.";
for (const stats of coverage.programs) {
  const row = summaryValues.find(
    (item) => item[0] === stats.program && item[1] === stats.degree,
  );
  if (!row) throw new Error(`Summary row was not found: ${stats.program} / ${stats.degree}`);
  row[4] = stats.available;
  row[5] = stats.missing;
  row[6] = stats.available / stats.required;
  row[7] = stats.missing_identities;
}
const totalRow = summaryValues.find((row) => row[0] === "الإجمالي");
if (!totalRow) throw new Error("Total summary row was not found");
totalRow[4] = coverage.available;
totalRow[5] = coverage.missing;
totalRow[6] = coverage.coverage;
totalRow[7] = coverage.missing_identities;
summary.getRange("A1:I21").values = summaryValues;

const identityValues = identities.getRange("A1:L101").values;
const identityPrefix = identityValues.slice(0, 5);
identityPrefix[2][0] =
  `عدد الهويات الفريدة: ${coverage.missing_identities}. قد يظهر المقرر نفسه في أكثر من برنامج أو خطة، وتوضح الأعمدة جميع المواضع المتأثرة.`;
const identityRows = identityValues
  .slice(5)
  .filter((row) => row[1])
  .filter((row) => !recoveredCodes.has(String(row[1])));
if (identityRows.length !== coverage.missing_identities) {
  throw new Error(`Expected ${coverage.missing_identities} missing identities, found ${identityRows.length}`);
}
identityRows.forEach((row, index) => { row[0] = index + 1; });

const occurrenceValues = occurrences.getRange("A1:O122").values;
const occurrencePrefix = occurrenceValues.slice(0, 5);
occurrencePrefix[2][0] =
  `عدد المواضع: ${coverage.missing}. كل صف يمثل ظهور مقرر في برنامج وخطة وإصدار محدد.`;
const occurrenceRows = occurrenceValues
  .slice(5)
  .filter((row) => row[6])
  .filter((row) => !recoveredCodes.has(String(row[6])));
if (occurrenceRows.length !== coverage.missing) {
  throw new Error(`Expected ${coverage.missing} missing occurrences, found ${occurrenceRows.length}`);
}
occurrenceRows.forEach((row, index) => { row[0] = index + 1; });

identities.tables.getItem("MissingCourseIdentities").delete();
identities.getRange("A1:L101").clear({ applyTo: "contents" });
identities.getRange("A1").writeValues([...identityPrefix, ...identityRows]);
const identitiesEnd = identityRows.length + 5;
const identitiesTable = identities.tables.add(`A5:L${identitiesEnd}`, true, "MissingCourseIdentities");
identitiesTable.style = "TableStyleMedium2";

occurrences.tables.getItem("MissingCourseOccurrences").delete();
occurrences.getRange("A1:O122").clear({ applyTo: "contents" });
occurrences.getRange("A1").writeValues([...occurrencePrefix, ...occurrenceRows]);
const occurrencesEnd = occurrenceRows.length + 5;
const occurrencesTable = occurrences.tables.add(`A5:O${occurrencesEnd}`, true, "MissingCourseOccurrences");
occurrencesTable.style = "TableStyleMedium2";

workbook.recalculate();
const errorScan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
if (!errorScan.ndjson.includes('"count":0') && errorScan.ndjson.trim()) {
  process.stdout.write(`${errorScan.ndjson}\n`);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(workbookPath);
await fs.mkdir(`${root}/tmp/spreadsheet-update-20260915`, { recursive: true });
for (const sheetName of ["الملخص", "المقررات المفقودة", "مواضع الخطط"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(
    `${root}/tmp/spreadsheet-update-20260915/${sheetName}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const keyCheck = await workbook.inspect({
  kind: "table",
  range: "الملخص!A1:I21",
  include: "values,formulas",
  tableMaxRows: 25,
  tableMaxCols: 10,
  maxChars: 12000,
});
process.stdout.write(`${keyCheck.ndjson}\n`);
