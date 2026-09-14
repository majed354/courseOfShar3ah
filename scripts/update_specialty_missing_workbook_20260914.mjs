#!/usr/bin/env node

import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "/Users/majd/Desktop/codex/courseOfShar3ah-main";
const workbookPath = `${root}/قائمة_المقررات_التخصصية_المفقودة_2026-09-10.xlsx`;
const recoveredCodes = new Set(["2002228-2", "2002229-2", "2002236-2", "20041201-2"]);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));

const summary = workbook.worksheets.getItem("الملخص");
const identities = workbook.worksheets.getItem("المقررات المفقودة");
const occurrences = workbook.worksheets.getItem("مواضع الخطط");

const summaryValues = summary.getRange("A1:I21").values;
summaryValues[2][0] =
  "المصدر: data.json في مستودع التوصيفات، بتاريخ 2026-09-14. النطاق: رموز 200* والاستثناء القديم 101221-2، دون الرسالة والاختبار الشامل أو مقررات الأقسام الخارجية.";
const islamicStudiesRow = summaryValues.find(
  (row) => row[0] === "الدراسات الإسلامية" && row[1] === "بكالوريوس",
);
if (!islamicStudiesRow) throw new Error("Islamic Studies bachelor summary row was not found");
islamicStudiesRow[4] = 102;
islamicStudiesRow[5] = 25;
islamicStudiesRow[6] = 102 / 127;
islamicStudiesRow[7] = 25;
const totalRow = summaryValues.find((row) => row[0] === "الإجمالي");
if (!totalRow) throw new Error("Total summary row was not found");
totalRow[4] = 639;
totalRow[5] = 117;
totalRow[6] = 639 / 756;
totalRow[7] = 96;
summary.getRange("A1:I21").values = summaryValues;

const identityValues = identities.getRange("A1:L105").values;
const identityPrefix = identityValues.slice(0, 5);
identityPrefix[2][0] =
  "عدد الهويات الفريدة: 96. قد يظهر المقرر نفسه في أكثر من برنامج أو خطة، وتوضح الأعمدة جميع المواضع المتأثرة.";
const identityRows = identityValues
  .slice(5)
  .filter((row) => row[1])
  .filter((row) => !recoveredCodes.has(String(row[1])));
if (identityRows.length !== 96) {
  throw new Error(`Expected 96 missing identities, found ${identityRows.length}`);
}
identityRows.forEach((row, index) => { row[0] = index + 1; });

const occurrenceValues = occurrences.getRange("A1:O126").values;
const occurrencePrefix = occurrenceValues.slice(0, 5);
occurrencePrefix[2][0] =
  "عدد المواضع: 117. كل صف يمثل ظهور مقرر في برنامج وخطة وإصدار محدد.";
const occurrenceRows = occurrenceValues
  .slice(5)
  .filter((row) => row[6])
  .filter((row) => !recoveredCodes.has(String(row[6])));
if (occurrenceRows.length !== 117) {
  throw new Error(`Expected 117 missing occurrences, found ${occurrenceRows.length}`);
}
occurrenceRows.forEach((row, index) => { row[0] = index + 1; });

identities.tables.getItem("MissingCourseIdentities").delete();
identities.getRange("A1:L105").clear({ applyTo: "contents" });
identities.getRange("A1").writeValues([...identityPrefix, ...identityRows]);
const identitiesTable = identities.tables.add("A5:L101", true, "MissingCourseIdentities");
identitiesTable.style = "TableStyleMedium2";

occurrences.tables.getItem("MissingCourseOccurrences").delete();
occurrences.getRange("A1:O126").clear({ applyTo: "contents" });
occurrences.getRange("A1").writeValues([...occurrencePrefix, ...occurrenceRows]);
const occurrencesTable = occurrences.tables.add("A5:O122", true, "MissingCourseOccurrences");
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
await fs.mkdir(`${root}/tmp/spreadsheet-update`, { recursive: true });
for (const sheetName of ["الملخص", "المقررات المفقودة", "مواضع الخطط"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(
    `${root}/tmp/spreadsheet-update/${sheetName}-after.png`,
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
