#!/usr/bin/env node

import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "/Users/majd/Desktop/codex/courseOfShar3ah-main";
const workbookPath = `${root}/قائمة_المقررات_التخصصية_المفقودة_2026-09-10.xlsx`;
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = workbook.worksheets.getItem("الملخص");
const identities = workbook.worksheets.getItem("المقررات المفقودة");
const occurrences = workbook.worksheets.getItem("مواضع الخطط");

const summaryValues = summary.getRange("A1:I21").values;
summaryValues[2][0] =
  "المصدر: data.json في مستودع التوصيفات، بتاريخ 2026-09-11. النطاق: رموز 200* والاستثناء القديم 101221-2، دون الرسالة والاختبار الشامل أو مقررات الأقسام الخارجية.";
const quranRow = summaryValues.find(
  (row) => row[0] === "القرآن وعلومه" && row[1] === "بكالوريوس",
);
if (!quranRow) throw new Error("Quran bachelor summary row was not found");
quranRow[4] = 106;
quranRow[5] = 14;
quranRow[6] = 106 / 120;
quranRow[7] = 12;
const totalRow = summaryValues.find((row) => row[0] === "الإجمالي");
if (!totalRow) throw new Error("Total summary row was not found");
totalRow[4] = 635;
totalRow[5] = 121;
totalRow[6] = 635 / 756;
totalRow[7] = 100;
summary.getRange("A1:I21").values = summaryValues;

const identityValues = identities.getRange("A1:L106").values;
const identityPrefix = identityValues.slice(0, 5);
identityPrefix[2][0] =
  "عدد الهويات الفريدة: 100. قد يظهر المقرر نفسه في أكثر من برنامج أو خطة، وتوضح الأعمدة جميع المواضع المتأثرة.";
const partial = {
  "2001205-2": {
    programs: "القراءات",
    degree: "بكالوريوس",
    plans: "القراءات: قديمة 38",
    levels: "3",
    count: 1,
  },
  "2001209-2": {
    programs: "القراءات",
    degree: "بكالوريوس",
    plans: "القراءات: قديمة 38",
    levels: "4",
    count: 1,
  },
  "2001221-2": {
    programs: "القراءات",
    degree: "بكالوريوس",
    plans: "القراءات: جديدة 47؛ القراءات: قديمة 38",
    levels: "3",
    count: 2,
  },
  "2001320-2": {
    programs: "القراءات",
    degree: "بكالوريوس",
    plans: "القراءات: قديمة 38",
    levels: "6",
    count: 1,
  },
  "2001322-2": {
    programs: "القراءات",
    degree: "بكالوريوس",
    plans: "القراءات: قديمة 38",
    levels: "4",
    count: 1,
  },
  "2001330-2": {
    programs: "الأنظمة",
    degree: "بكالوريوس",
    plans: "الأنظمة: قديمة 38",
    levels: "3",
    count: 1,
  },
};
const identityRows = [];
for (const sourceRow of identityValues.slice(5)) {
  if (!sourceRow[1]) continue;
  const code = String(sourceRow[1]);
  if (code === "2001317-2") continue;
  const row = [...sourceRow];
  if (partial[code]) {
    const item = partial[code];
    row[3] = item.programs;
    row[4] = item.degree;
    row[5] = item.plans;
    row[6] = item.levels;
    row[7] = item.count;
    row[8] = "يوجد توصيف مؤسسي لبرنامج القرآن وعلومه فقط";
    row[9] = `institutional-recovery-20260911/${code}.pdf`;
    row[10] = `الحصول على دليل خاص ببرنامج ${item.programs}، ثم ربط مخرجاته في نطاقه فقط`;
  }
  identityRows.push(row);
}
if (identityRows.length !== 100) {
  throw new Error(`Expected 100 missing identities, found ${identityRows.length}`);
}
identityRows.forEach((row, index) => {
  row[0] = index + 1;
});

const coveredScopes = new Set([
  "2001205-2|القرآن وعلومه|قديمة|39",
  "2001209-2|القرآن وعلومه|قديمة|39",
  "2001221-2|القرآن وعلومه|جديدة|47",
  "2001320-2|القرآن وعلومه|قديمة|39",
  "2001322-2|القرآن وعلومه|قديمة|39",
  "2001322-2|القرآن وعلومه|جديدة|47",
  "2001317-2|القرآن وعلومه|قديمة|39",
  "2001317-2|القرآن وعلومه|جديدة|47",
  "2001330-2|القرآن وعلومه|قديمة|39",
  "2001330-2|القرآن وعلومه|جديدة|47",
]);
const occurrenceValues = occurrences.getRange("A1:O136").values;
const occurrencePrefix = occurrenceValues.slice(0, 5);
occurrencePrefix[2][0] =
  "عدد المواضع: 121. كل صف يمثل ظهور مقرر في برنامج وخطة وإصدار محدد.";
const occurrenceRows = occurrenceValues
  .slice(5)
  .filter((row) => row[6])
  .filter((row) => {
    const key = `${row[6]}|${row[1]}|${row[3]}|${row[4]}`;
    return !coveredScopes.has(key);
  });
if (occurrenceRows.length !== 121) {
  throw new Error(`Expected 121 missing occurrences, found ${occurrenceRows.length}`);
}
occurrenceRows.forEach((row, index) => {
  row[0] = index + 1;
});

identities.tables.getItem("MissingCourseIdentities").delete();
identities.getRange("A1:L106").clear({ applyTo: "contents" });
identities.getRange("A1").writeValues([...identityPrefix, ...identityRows]);
const identitiesTable = identities.tables.add(
  "A5:L105",
  true,
  "MissingCourseIdentities",
);
identitiesTable.style = "TableStyleMedium2";

occurrences.tables.getItem("MissingCourseOccurrences").delete();
occurrences.getRange("A1:O136").clear({ applyTo: "contents" });
occurrences.getRange("A1").writeValues([...occurrencePrefix, ...occurrenceRows]);
const occurrencesTable = occurrences.tables.add(
  "A5:O126",
  true,
  "MissingCourseOccurrences",
);
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
for (const sheetName of ["الملخص", "المقررات المفقودة", "مواضع الخطط"]) {
  const preview = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    `${root}/tmp/artifact-inventory/${sheetName}-20260911.png`,
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
