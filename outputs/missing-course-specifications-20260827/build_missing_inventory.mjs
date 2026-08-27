import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const sourcePath = "/tmp/missing-specialty-inventory-20260826.json";
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..");
const recoveryEntriesPath = path.join(repoRoot, "assets", "course-specifications", "raw-recovery-20260827", "data-entries.json");
const outputDir = path.join(repoRoot, "outputs", "missing-course-specifications-20260827");
const outputPath = path.join(outputDir, "تفاصيل-التوصيفات-المطلوبة-2026-08-27.xlsx");

const raw = JSON.parse(await fs.readFile(sourcePath, "utf8"));
const recovered = JSON.parse(await fs.readFile(recoveryEntriesPath, "utf8"));
const recoveredCodes = new Set(Object.keys(recovered.course_details));

const foldArabic = value => String(value ?? "")
  .normalize("NFKD")
  .replace(/\p{M}+/gu, "")
  .replace(/ـ/g, "")
  .replace(/[أإآٱٲٳ]/g, "ا")
  .replace(/[ةۀہ]/g, "ه")
  .replace(/\s+/g, " ")
  .trim();
const thesisTitles = new Set([
  "الرساله",
  "رساله",
  "الرساله العلميه",
  "رساله الماجستير",
  "الاطروحه",
  "اطروحه الدكتوراه",
]);
const comprehensiveExamTitles = new Set(["الاختبار الشامل", "اختبار شامل"]);
const isGraduateRequirementWithoutCourseSpecification = item => {
  const occurrences = item.occurrences || [];
  if (!occurrences.length || occurrences.some(occurrence => occurrence.degree === "بكالوريوس")) return false;
  const title = foldArabic(item.title);
  if (thesisTitles.has(title)) {
    return occurrences.every(occurrence => occurrence.course_type === "بحث" && Number(occurrence.hours) >= 6);
  }
  if (comprehensiveExamTitles.has(title)) {
    return occurrences.every(occurrence =>
      Number(occurrence.hours) === 0 && foldArabic(occurrence.course_type) === "الاختبار الشامل"
    );
  }
  return false;
};

const unresolvedCandidates = raw.missing_no_source_or_candidate.filter(item => !recoveredCodes.has(item.code));
const ambiguousCandidates = raw.ambiguous_excluded.filter(item => !recoveredCodes.has(item.code));
const excludedNonCourseRequirements = [...unresolvedCandidates, ...ambiguousCandidates]
  .filter(isGraduateRequirementWithoutCourseSpecification);
const missing = unresolvedCandidates.filter(item => !isGraduateRequirementWithoutCourseSpecification(item));
const ambiguous = ambiguousCandidates.filter(item => !isGraduateRequirementWithoutCourseSpecification(item));

const planLabel = value => value === "جديدة" ? "حديثة" : value;
const unique = values => [...new Set(values.filter(value => value !== null && value !== undefined && value !== ""))];
const join = values => unique(values).join("؛ ");
const display = value => value === null || value === undefined ? "" : value;
const classify = occurrences => {
  const types = new Set(occurrences.map(item => item.plan_type));
  if (types.has("قديمة") && types.has("جديدة")) return "مشتركة بين القديمة والحديثة";
  return types.has("قديمة") ? "قديمة فقط" : "حديثة فقط";
};
const programsText = occurrences => join(occurrences.map(item => item.program));
const degreesText = occurrences => join(occurrences.map(item => item.degree));
const versionsText = occurrences => join(occurrences.map(item => `${planLabel(item.plan_type)} ${item.version}`));
const scopesText = occurrences => join(occurrences.map(item => `${item.program} | ${item.degree} | ${planLabel(item.plan_type)} | إصدار ${item.version}`));

const missingOccurrences = missing.flatMap(item => item.occurrences.map(occurrence => ({
  ...occurrence,
  inventory_group: "مفقود بلا مصدر"
})));
const ambiguousOccurrences = ambiguous.flatMap(item => item.occurrences.map(occurrence => ({
  ...occurrence,
  inventory_group: "مرشح يحتاج حسم"
})));
const allOccurrences = [...missingOccurrences, ...ambiguousOccurrences].sort((a, b) =>
  a.inventory_group.localeCompare(b.inventory_group, "ar") ||
  a.program.localeCompare(b.program, "ar") ||
  a.degree.localeCompare(b.degree, "ar") ||
  a.plan_type.localeCompare(b.plan_type, "ar") ||
  Number(a.version) - Number(b.version) ||
  Number(a.level ?? 999) - Number(b.level ?? 999) ||
  a.code.localeCompare(b.code, "en", { numeric: true })
);

const identityClassCounts = missing.reduce((acc, item) => {
  const key = classify(item.occurrences);
  acc[key] = (acc[key] || 0) + 1;
  return acc;
}, {});
const identityClassOccurrenceCounts = missing.reduce((acc, item) => {
  const key = classify(item.occurrences);
  acc[key] = (acc[key] || 0) + item.occurrence_count;
  return acc;
}, {});

const checks = {
  excludedNonCourseIdentities: excludedNonCourseRequirements.length,
  excludedNonCourseOccurrences: excludedNonCourseRequirements.reduce((sum, item) => sum + item.occurrence_count, 0),
  missingIdentities: missing.length,
  missingOccurrences: missingOccurrences.length,
  ambiguousIdentities: ambiguous.length,
  ambiguousOccurrences: ambiguousOccurrences.length,
  allUncoveredIdentities: missing.length + ambiguous.length,
  allUncoveredOccurrences: allOccurrences.length,
  oldOnly: identityClassCounts["قديمة فقط"] || 0,
  newOnly: identityClassCounts["حديثة فقط"] || 0,
  shared: identityClassCounts["مشتركة بين القديمة والحديثة"] || 0,
  oldOnlyOccurrences: identityClassOccurrenceCounts["قديمة فقط"] || 0,
  newOnlyOccurrences: identityClassOccurrenceCounts["حديثة فقط"] || 0,
  sharedOccurrences: identityClassOccurrenceCounts["مشتركة بين القديمة والحديثة"] || 0,
  oldOccurrences: missingOccurrences.filter(item => item.plan_type === "قديمة").length,
  newOccurrences: missingOccurrences.filter(item => item.plan_type === "جديدة").length,
};

const expected = {
  excludedNonCourseIdentities: 6,
  excludedNonCourseOccurrences: 8,
  missingIdentities: 116,
  missingOccurrences: 158,
  ambiguousIdentities: 5,
  ambiguousOccurrences: 6,
  allUncoveredIdentities: 121,
  allUncoveredOccurrences: 164,
  oldOnly: 49,
  newOnly: 61,
  shared: 6,
  oldOnlyOccurrences: 75,
  newOnlyOccurrences: 66,
  sharedOccurrences: 17,
  oldOccurrences: 85,
  newOccurrences: 73,
};
for (const [name, expectedValue] of Object.entries(expected)) {
  if (checks[name] !== expectedValue) {
    throw new Error(`Reconciliation failed for ${name}: got ${checks[name]}, expected ${expectedValue}`);
  }
}

const identityKeys = missing.map(item => item.identity_key);
if (new Set(identityKeys).size !== identityKeys.length) throw new Error(`Duplicate identity keys in the ${missing.length} list`);
const allUncoveredCodes = [...missing, ...ambiguous].map(item => item.code);
if (new Set(allUncoveredCodes).size !== allUncoveredCodes.length) throw new Error(`Duplicate codes across the ${allUncoveredCodes.length} unresolved identities`);
const occurrenceKeys = allOccurrences.map(item => `${item.identity_key}||${item.program}||${item.degree}||${item.plan_type}||${item.version}`);
if (new Set(occurrenceKeys).size !== occurrenceKeys.length) throw new Error("Duplicate occurrence keys");

const programDegreeGroups = new Map();
for (const occurrence of missingOccurrences) {
  const groupKey = `${occurrence.program}||${occurrence.degree}`;
  if (!programDegreeGroups.has(groupKey)) {
    programDegreeGroups.set(groupKey, {
      program: occurrence.program,
      degree: occurrence.degree,
      identities: new Set(),
      occurrenceCount: 0,
    });
  }
  const group = programDegreeGroups.get(groupKey);
  group.identities.add(occurrence.identity_key);
  group.occurrenceCount += 1;
}
const programDegreeRows = [...programDegreeGroups.values()].map(group => ({
  program: group.program,
  degree: group.degree,
  identityCount: group.identities.size,
  occurrenceCount: group.occurrenceCount,
})).sort((a, b) => a.degree.localeCompare(b.degree, "ar") || a.program.localeCompare(b.program, "ar"));

const planGroups = new Map();
for (const occurrence of missingOccurrences) {
  const groupKey = `${occurrence.program}||${occurrence.degree}||${occurrence.plan_type}||${occurrence.version}`;
  if (!planGroups.has(groupKey)) {
    planGroups.set(groupKey, {
      program: occurrence.program,
      degree: occurrence.degree,
      planType: occurrence.plan_type,
      version: occurrence.version,
      identities: new Set(),
      occurrenceCount: 0,
    });
  }
  const group = planGroups.get(groupKey);
  group.identities.add(occurrence.identity_key);
  group.occurrenceCount += 1;
}
const planRows = [...planGroups.values()].map(group => ({
  program: group.program,
  degree: group.degree,
  planType: planLabel(group.planType),
  version: group.version,
  identityCount: group.identities.size,
  occurrenceCount: group.occurrenceCount,
})).sort((a, b) => a.planType.localeCompare(b.planType, "ar") || a.degree.localeCompare(b.degree, "ar") || a.program.localeCompare(b.program, "ar") || Number(a.version) - Number(b.version));

const missingSheetName = `المفقودات ${missing.length}`;
const missingLastRow = 4 + missing.length;
const occurrencesLastRow = 4 + allOccurrences.length;
const ambiguousLastRow = 4 + ambiguous.length;
const missingDataRange = `A5:S${missingLastRow}`;
const occurrenceDataRange = `A5:P${occurrencesLastRow}`;
const ambiguousDataRange = `A5:N${ambiguousLastRow}`;

const workbook = Workbook.create();
const summary = workbook.worksheets.add("ملخص");
const missingSheet = workbook.worksheets.add(missingSheetName);
const occurrencesSheet = workbook.worksheets.add("مواضع الظهور");
const ambiguousSheet = workbook.worksheets.add("حالات تحتاج حسم");

const colors = {
  navy: "#173B57",
  teal: "#0F6B78",
  tealLight: "#DDF2F2",
  sky: "#E8F3F8",
  gold: "#B88922",
  goldLight: "#FFF4D6",
  green: "#26734D",
  greenLight: "#E2F3E9",
  blue: "#24628A",
  blueLight: "#E4F0F8",
  gray: "#5F6B76",
  grayLight: "#F2F5F7",
  border: "#CCD6DD",
  white: "#FFFFFF",
  text: "#17212B",
};

function styleTitle(sheet, rangeAddress, title) {
  const range = sheet.getRange(rangeAddress);
  range.merge();
  range.values = [[title]];
  range.format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
  range.format.rowHeight = 34;
}

function styleNote(sheet, rangeAddress, text) {
  const range = sheet.getRange(rangeAddress);
  range.merge();
  range.values = [[text]];
  range.format = {
    fill: colors.sky,
    font: { color: colors.text },
    horizontalAlignment: "right",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: colors.border },
  };
  range.format.rowHeight = 42;
}

function styleHeader(range) {
  range.format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "inside", style: "thin", color: "#FFFFFF" },
  };
  range.format.rowHeight = 32;
}

function styleBody(range) {
  range.format = {
    font: { color: colors.text },
    verticalAlignment: "center",
    wrapText: true,
    borders: {
      insideHorizontal: { style: "thin", color: colors.border },
      bottom: { style: "thin", color: colors.border },
    },
  };
}

function addStatusFormatting(range) {
  range.conditionalFormats.add("containsText", {
    text: "تم التزويد",
    format: { fill: colors.greenLight, font: { color: colors.green, bold: true } },
  });
  range.conditionalFormats.add("containsText", {
    text: "قيد البحث",
    format: { fill: colors.blueLight, font: { color: colors.blue, bold: true } },
  });
  range.conditionalFormats.add("containsText", {
    text: "يحتاج مراجعة",
    format: { fill: colors.goldLight, font: { color: colors.gold, bold: true } },
  });
}

// Summary sheet.
summary.showGridLines = false;
styleTitle(summary, "A1:L1", "حصر توصيفات المقررات التخصصية المفقودة");
styleNote(summary, "A2:L2", "الحصر مبني على تطابق رمز المقرر واسمه ونطاق الخطة. «حديثة» هنا تعني القيمة «جديدة» في بيانات الموقع، وتشمل إصدار 47 للبكالوريوس وإصدار 1 للدراسات العليا.");

const cardRanges = ["A4:B4", "C4:D4", "E4:F4", "G4:H4", "I4:J4", "K4:L4"];
const cardValueRanges = ["A5:B6", "C5:D6", "E5:F6", "G5:H6", "I5:J6", "K5:L6"];
const cardLabels = ["مفقود بلا مصدر", "ظهورات المفقود", "حالات تحتاج حسم", "إجمالي غير مكتمل", "تم التزويد", "نسبة الإنجاز"];
for (let i = 0; i < cardRanges.length; i += 1) {
  const labelRange = summary.getRange(cardRanges[i]);
  labelRange.merge();
  labelRange.values = [[cardLabels[i]]];
  labelRange.format = {
    fill: colors.tealLight,
    font: { bold: true, color: colors.teal },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: colors.border },
  };
  const valueRange = summary.getRange(cardValueRanges[i]);
  valueRange.merge();
  valueRange.format = {
    fill: colors.white,
    font: { bold: true, color: colors.navy },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: colors.border },
  };
}
summary.getRange("A5").formulas = [[`=COUNTA('${missingSheetName}'!$B$5:$B$${missingLastRow})`]];
summary.getRange("C5").formulas = [[`=SUM('${missingSheetName}'!$G$5:$G$${missingLastRow})`]];
summary.getRange("E5").formulas = [[`=COUNTA('حالات تحتاج حسم'!$B$5:$B$${ambiguousLastRow})`]];
summary.getRange("G5").formulas = [["=A5+E5"]];
summary.getRange("I5").formulas = [[`=COUNTIF('${missingSheetName}'!$P$5:$P$${missingLastRow},\"تم التزويد\")`]];
summary.getRange("K5").formulas = [["=IF(A5=0,0,I5/A5)"]];
summary.getRange("K5").format.numberFormat = "0.0%";

summary.getRange("A9:C9").values = [["النطاق الحصري", "الهويات", "الظهورات"]];
styleHeader(summary.getRange("A9:C9"));
summary.getRange("A10:A13").values = [["قديمة فقط"], ["حديثة فقط"], ["مشتركة بين القديمة والحديثة"], ["الإجمالي"]];
summary.getRange("B10").formulas = [[`=COUNTIF('${missingSheetName}'!$D$5:$D$${missingLastRow},A10)`]];
summary.getRange("B10:B12").fillDown();
summary.getRange("C10").formulas = [[`=SUMIF('${missingSheetName}'!$D$5:$D$${missingLastRow},A10,'${missingSheetName}'!$G$5:$G$${missingLastRow})`]];
summary.getRange("C10:C12").fillDown();
summary.getRange("B13").formulas = [["=SUM(B10:B12)"]];
summary.getRange("C13").formulas = [["=SUM(C10:C12)"]];
styleBody(summary.getRange("A10:C13"));
summary.getRange("A13:C13").format = {
  fill: colors.tealLight,
  font: { bold: true, color: colors.teal },
  borders: { preset: "doubleBottom", style: "thin", color: colors.teal },
};

summary.getRange("E9:G9").values = [["عضوية نوع الخطة", "الهويات", "الظهورات"]];
styleHeader(summary.getRange("E9:G9"));
summary.getRange("E10:E11").values = [["الخطط القديمة"], ["الخطط الحديثة"]];
summary.getRange("F10").formulas = [[`=COUNTIF('${missingSheetName}'!$E$5:$E$${missingLastRow},\">0\")`]];
summary.getRange("F11").formulas = [[`=COUNTIF('${missingSheetName}'!$F$5:$F$${missingLastRow},\">0\")`]];
summary.getRange("G10").formulas = [[`=SUM('${missingSheetName}'!$E$5:$E$${missingLastRow})`]];
summary.getRange("G11").formulas = [[`=SUM('${missingSheetName}'!$F$5:$F$${missingLastRow})`]];
styleBody(summary.getRange("E10:G11"));
styleNote(summary, "E13:G14", `تتداخل ${checks.shared} هويات بين القديمة والحديثة؛ لذلك لا يُجمع عمود الهويات هنا للوصول إلى ${missing.length}.`);

summary.getRange("I9:L9").values = [["حالة المتابعة", "العدد", "النسبة", "الغرض"]];
styleHeader(summary.getRange("I9:L9"));
summary.getRange("I10:I14").values = [["غير متوفر"], ["قيد البحث"], ["تم التزويد"], ["يحتاج مراجعة"], ["غير مطلوب"]];
summary.getRange("J10").formulas = [[`=COUNTIF('${missingSheetName}'!$P$5:$P$${missingLastRow},I10)`]];
summary.getRange("J10:J14").fillDown();
summary.getRange("K10").formulas = [["=IF($A$5=0,0,J10/$A$5)"]];
summary.getRange("K10:K14").fillDown();
summary.getRange("K10:K14").format.numberFormat = "0.0%";
summary.getRange("L10:L14").values = [["يلزم توفير PDF معتمد"], ["يجري البحث عنه"], ["أضيف رابط أو مسار"], ["وصل ويحتاج فحص"], ["حُسم أنه غير مطلوب"]];
styleBody(summary.getRange("I10:L14"));

summary.getRange("A17:F17").values = [["البرنامج", "الدرجة", "نوع الخطة", "الإصدار", "الهويات", "الظهورات"]];
styleHeader(summary.getRange("A17:F17"));
const planSummaryValues = planRows.map(row => [row.program, row.degree, row.planType, row.version, row.identityCount, row.occurrenceCount]);
summary.getRangeByIndexes(17, 0, planSummaryValues.length, 6).values = planSummaryValues;
styleBody(summary.getRangeByIndexes(17, 0, planSummaryValues.length, 6));
summary.getRangeByIndexes(17, 3, planSummaryValues.length, 3).format.horizontalAlignment = "center";

summary.getRange("H17:K17").values = [["البرنامج", "الدرجة", "هويات داخل البرنامج", "الظهورات"]];
styleHeader(summary.getRange("H17:K17"));
const programSummaryValues = programDegreeRows.map(row => [row.program, row.degree, row.identityCount, row.occurrenceCount]);
summary.getRangeByIndexes(17, 7, programSummaryValues.length, 4).values = programSummaryValues;
styleBody(summary.getRangeByIndexes(17, 7, programSummaryValues.length, 4));
summary.getRangeByIndexes(17, 9, programSummaryValues.length, 2).format.horizontalAlignment = "center";
const programIdentityMemberships = programDegreeRows.reduce((sum, row) => sum + row.identityCount, 0);
const sharedProgramMemberships = programIdentityMemberships - missing.length;
styleNote(summary, "H31:L33", `مجموع هويات البرامج = ${programIdentityMemberships} لا ${missing.length} لأن ${sharedProgramMemberships} هوية مشتركة بين برنامجين. المرجع الإجمالي الصحيح هو ${missing.length} هوية و${missingOccurrences.length} ظهورًا.`);

styleNote(summary, "A37:L39", `المصدر: data.json وCOURSE_SPECIFICATIONS_AUDIT.md — تاريخ الحصر: 27 أغسطس 2026م. المطلوب لكل صف في ورقة «${missingSheetName}»: ملف PDF معتمد يحمل رمز المقرر واسمه. استُبعدت ${checks.excludedNonCourseIdentities} هويات تمثل ${checks.excludedNonCourseOccurrences} ظهورات للرسالة والاختبار الشامل لأنها متطلبات دراسات عليا غير تدريسية لا تحتاج توصيف مقرر.`);
summary.getRange("A1:L39").format.verticalAlignment = "center";
summary.getRange("A1:L39").format.wrapText = true;
summary.getRange("A1:L1").format.font.color = colors.white;
summary.getRange("A:A").format.columnWidth = 19;
summary.getRange("B:B").format.columnWidth = 12;
summary.getRange("C:C").format.columnWidth = 17;
summary.getRange("D:D").format.columnWidth = 11;
summary.getRange("E:E").format.columnWidth = 18;
summary.getRange("F:F").format.columnWidth = 12;
summary.getRange("G:G").format.columnWidth = 14;
summary.getRange("H:H").format.columnWidth = 18;
summary.getRange("I:I").format.columnWidth = 18;
summary.getRange("J:J").format.columnWidth = 12;
summary.getRange("K:K").format.columnWidth = 12;
summary.getRange("L:L").format.columnWidth = 24;
summary.freezePanes.freezeRows(2);

// Missing identities sheet.
missingSheet.showGridLines = false;
styleTitle(missingSheet, "A1:S1", `المفقودات التي يلزم توفير توصيف PDF لها — ${missing.length} هوية`);
styleNote(missingSheet, "A2:S2", "صف واحد لكل هوية (الرمز + الاسم). استخدم حالة التوفير والرابط/المسار وملاحظات التزويد للمتابعة. لا تشمل القائمة الرسالة والاختبار الشامل؛ وتفاصيل كل موضع في الخطة موجودة في ورقة «مواضع الظهور».");
const missingHeaders = [
  "م", "رمز المقرر", "اسم المقرر", "نطاق الخطة", "ظهورات قديمة", "ظهورات حديثة", "إجمالي الظهورات",
  "البرامج", "الدرجات", "الإصدارات", "الساعات", "المستويات", "الفئات", "تنبيه الساعات",
  "اسم الملف المقترح", "حالة التوفير", "رابط أو مسار الملف", "ملاحظات التزويد", "مفتاح الهوية"
];
missingSheet.getRange("A4:S4").values = [missingHeaders];
styleHeader(missingSheet.getRange("A4:S4"));
const missingBaseRows = missing.map((item, index) => {
  const hourValues = unique(item.occurrences.map(occurrence => occurrence.hours));
  const codeSuffix = Number((item.code.match(/-(\d+)$/) || [])[1]);
  const hourWarning = hourValues.length === 1 && Number.isFinite(codeSuffix) && Number(hourValues[0]) !== codeSuffix
    ? `ساعات الخطة ${hourValues[0]} ولا تؤخذ من لاحقة الرمز -${codeSuffix}`
    : "";
  return [
    index + 1,
    item.code,
    item.title,
    "",
    "",
    "",
    "",
    programsText(item.occurrences),
    degreesText(item.occurrences),
    versionsText(item.occurrences),
    join(item.occurrences.map(occurrence => occurrence.hours)),
    join(item.occurrences.map(occurrence => occurrence.level)),
    join(item.occurrences.map(occurrence => occurrence.category)),
    hourWarning,
    `${item.code}.pdf`,
    "غير متوفر",
    "",
    "",
    item.identity_key,
  ];
});
const hourWarningRows = missingBaseRows.filter(row => row[13]);
if (hourWarningRows.length !== 1 || hourWarningRows[0][1] !== "2003255-3") {
  throw new Error(`Unexpected hours warnings: ${JSON.stringify(hourWarningRows.map(row => [row[1], row[13]]))}`);
}
missingSheet.getRangeByIndexes(4, 0, missingBaseRows.length, missingHeaders.length).values = missingBaseRows;
for (let rowIndex = 5; rowIndex <= missingLastRow; rowIndex += 1) {
  missingSheet.getRange(`D${rowIndex}`).formulas = [[`=IF(AND(E${rowIndex}>0,F${rowIndex}>0),\"مشتركة بين القديمة والحديثة\",IF(E${rowIndex}>0,\"قديمة فقط\",\"حديثة فقط\"))`]];
  missingSheet.getRange(`E${rowIndex}`).formulas = [[`=COUNTIFS('مواضع الظهور'!$P$5:$P$${occurrencesLastRow},$S${rowIndex},'مواضع الظهور'!$G$5:$G$${occurrencesLastRow},\"قديمة\",'مواضع الظهور'!$B$5:$B$${occurrencesLastRow},\"مفقود بلا مصدر\")`]];
  missingSheet.getRange(`F${rowIndex}`).formulas = [[`=COUNTIFS('مواضع الظهور'!$P$5:$P$${occurrencesLastRow},$S${rowIndex},'مواضع الظهور'!$G$5:$G$${occurrencesLastRow},\"حديثة\",'مواضع الظهور'!$B$5:$B$${occurrencesLastRow},\"مفقود بلا مصدر\")`]];
  missingSheet.getRange(`G${rowIndex}`).formulas = [[`=SUM(E${rowIndex}:F${rowIndex})`]];
}
styleBody(missingSheet.getRange(missingDataRange));
missingSheet.getRange(`A5:A${missingLastRow}`).format.horizontalAlignment = "center";
missingSheet.getRange(`B5:B${missingLastRow}`).format.horizontalAlignment = "center";
missingSheet.getRange(`D5:G${missingLastRow}`).format.horizontalAlignment = "center";
missingSheet.getRange(`J5:Q${missingLastRow}`).format.horizontalAlignment = "center";
missingSheet.getRange(`S5:S${missingLastRow}`).format.font.color = colors.gray;
missingSheet.getRange(`P5:P${missingLastRow}`).dataValidation = {
  rule: { type: "list", values: ["غير متوفر", "قيد البحث", "تم التزويد", "يحتاج مراجعة", "غير مطلوب"] },
};
addStatusFormatting(missingSheet.getRange(`P5:P${missingLastRow}`));
missingSheet.getRange(`N5:N${missingLastRow}`).conditionalFormats.add("notContainsBlanks", {
  format: { fill: colors.goldLight, font: { color: colors.gold, bold: true } },
});
const missingTable = missingSheet.tables.add(`A4:S${missingLastRow}`, true, "MissingSpecsTable");
missingTable.style = "TableStyleMedium2";
missingTable.showFilterButton = true;
missingSheet.freezePanes.freezeRows(4);
missingSheet.freezePanes.freezeColumns(3);
const missingWidths = [7, 16, 29, 27, 12, 13, 12, 34, 16, 22, 11, 13, 25, 28, 21, 17, 32, 34, 36];
missingWidths.forEach((width, index) => missingSheet.getRangeByIndexes(0, index, missingLastRow, 1).format.columnWidth = width);
missingSheet.getRange(missingDataRange).format.rowHeight = 38;

// All unresolved occurrences sheet.
occurrencesSheet.showGridLines = false;
styleTitle(occurrencesSheet, "A1:P1", `مواضع ظهور المقررات غير المكتملة في الخطط — ${allOccurrences.length} ظهورًا`);
styleNote(occurrencesSheet, "A2:P2", `تشمل ${missingOccurrences.length} ظهورًا للـ${missing.length} التي يلزم توفيرها، و${ambiguousOccurrences.length} ظهورات للحالات ${ambiguous.length} التي لها مرشح يحتاج حسمًا. لا تشمل الرسالة والاختبار الشامل؛ والساعات مأخوذة من صفوف الخطط، لا من لاحقة الرمز.`);
const occurrenceHeaders = [
  "م", "المجموعة", "رمز المقرر", "اسم المقرر", "البرنامج", "الدرجة", "نوع الخطة", "الإصدار",
  "المستوى", "الفصل", "الساعات", "نوع المقرر", "الفئة", "القسم", "ملف مصدر الخطة", "مفتاح الهوية"
];
occurrencesSheet.getRange("A4:P4").values = [occurrenceHeaders];
styleHeader(occurrencesSheet.getRange("A4:P4"));
const occurrenceValues = allOccurrences.map((item, index) => [
  index + 1,
  item.inventory_group,
  item.code,
  item.title,
  item.program,
  item.degree,
  planLabel(item.plan_type),
  item.version,
  display(item.level),
  display(item.semester),
  item.hours,
  item.course_type,
  item.category,
  item.department,
  item.plan_source_file,
  item.identity_key,
]);
occurrencesSheet.getRangeByIndexes(4, 0, occurrenceValues.length, occurrenceHeaders.length).values = occurrenceValues;
styleBody(occurrencesSheet.getRange(occurrenceDataRange));
occurrencesSheet.getRange(`A5:A${occurrencesLastRow}`).format.horizontalAlignment = "center";
occurrencesSheet.getRange(`C5:C${occurrencesLastRow}`).format.horizontalAlignment = "center";
occurrencesSheet.getRange(`F5:K${occurrencesLastRow}`).format.horizontalAlignment = "center";
occurrencesSheet.getRange(`P5:P${occurrencesLastRow}`).format.font.color = colors.gray;
occurrencesSheet.getRange(`B5:B${occurrencesLastRow}`).conditionalFormats.add("containsText", {
  text: "مرشح يحتاج حسم",
  format: { fill: colors.goldLight, font: { color: colors.gold, bold: true } },
});
const occurrenceTable = occurrencesSheet.tables.add(`A4:P${occurrencesLastRow}`, true, "UnresolvedOccurrencesTable");
occurrenceTable.style = "TableStyleMedium2";
occurrenceTable.showFilterButton = true;
occurrencesSheet.freezePanes.freezeRows(4);
occurrencesSheet.freezePanes.freezeColumns(4);
const occurrenceWidths = [7, 22, 16, 30, 22, 14, 14, 10, 10, 10, 10, 15, 22, 21, 29, 36];
occurrenceWidths.forEach((width, index) => occurrencesSheet.getRangeByIndexes(0, index, occurrencesLastRow, 1).format.columnWidth = width);
occurrencesSheet.getRange(occurrenceDataRange).format.rowHeight = 34;

// Ambiguous candidates sheet.
ambiguousSheet.showGridLines = false;
styleTitle(ambiguousSheet, "A1:N1", `حالات لها ملفات مرشحة وتحتاج قرارًا — ${ambiguous.length} هويات`);
styleNote(ambiguousSheet, "A2:N2", `هذه الحالات ليست ضمن الـ${missing.length} المطلوب توفيرها مباشرة؛ راجع المرشح أولًا. لا يُربط الملف إلا بعد اعتماد أنه تحديث للهوية أو بعد توفير توصيف مستقل مطابق.`);
const ambiguousHeaders = [
  "م", "رمز المقرر", "اسم المقرر", "نطاق الخطة", "عدد الظهورات", "البرامج والدرجات",
  "رمز المرشح", "اسم المرشح", "ساعات المرشح", "ملفات المرشح", "سبب عدم الربط", "ملفات الدليل", "القرار", "ملاحظات"
];
ambiguousSheet.getRange("A4:N4").values = [ambiguousHeaders];
styleHeader(ambiguousSheet.getRange("A4:N4"));
const ambiguousValues = ambiguous.map((item, index) => [
  index + 1,
  item.code,
  item.title,
  classify(item.occurrences),
  item.occurrence_count,
  scopesText(item.occurrences),
  item.candidate_identity?.code || "",
  item.candidate_identity?.title || "",
  item.candidate_identity?.hours ?? "",
  (item.candidate_files || []).join("؛ "),
  item.reason,
  (item.evidence_files || []).join("؛ "),
  "يحتاج حسم",
  "",
]);
ambiguousSheet.getRange(ambiguousDataRange).values = ambiguousValues;
styleBody(ambiguousSheet.getRange(ambiguousDataRange));
ambiguousSheet.getRange(`A5:A${ambiguousLastRow}`).format.horizontalAlignment = "center";
ambiguousSheet.getRange(`B5:B${ambiguousLastRow}`).format.horizontalAlignment = "center";
ambiguousSheet.getRange(`D5:E${ambiguousLastRow}`).format.horizontalAlignment = "center";
ambiguousSheet.getRange(`G5:I${ambiguousLastRow}`).format.horizontalAlignment = "center";
ambiguousSheet.getRange(`M5:M${ambiguousLastRow}`).dataValidation = {
  rule: { type: "list", values: ["يحتاج حسم", "اعتماد المرشح بعد المراجعة", "طلب توصيف جديد", "استبعاد المرشح"] },
};
ambiguousSheet.getRange(`M5:M${ambiguousLastRow}`).conditionalFormats.add("containsText", {
  text: "يحتاج حسم",
  format: { fill: colors.goldLight, font: { color: colors.gold, bold: true } },
});
ambiguousSheet.getRange(`M5:M${ambiguousLastRow}`).conditionalFormats.add("containsText", {
  text: "اعتماد المرشح",
  format: { fill: colors.greenLight, font: { color: colors.green, bold: true } },
});
ambiguousSheet.getRange(`M5:M${ambiguousLastRow}`).conditionalFormats.add("containsText", {
  text: "طلب توصيف جديد",
  format: { fill: colors.blueLight, font: { color: colors.blue, bold: true } },
});
const ambiguousTable = ambiguousSheet.tables.add(`A4:N${ambiguousLastRow}`, true, "AmbiguousCandidatesTable");
ambiguousTable.style = "TableStyleMedium2";
ambiguousTable.showFilterButton = true;
ambiguousSheet.freezePanes.freezeRows(4);
ambiguousSheet.freezePanes.freezeColumns(3);
const ambiguousWidths = [7, 16, 27, 25, 12, 46, 16, 28, 12, 46, 58, 44, 25, 34];
ambiguousWidths.forEach((width, index) => ambiguousSheet.getRangeByIndexes(0, index, ambiguousLastRow, 1).format.columnWidth = width);
ambiguousSheet.getRange(ambiguousDataRange).format.rowHeight = 76;

// Number formats.
missingSheet.getRange(`A5:A${missingLastRow}`).format.numberFormat = "#,##0";
missingSheet.getRange(`E5:G${missingLastRow}`).format.numberFormat = "#,##0";
occurrencesSheet.getRange(`A5:A${occurrencesLastRow}`).format.numberFormat = "#,##0";
occurrencesSheet.getRange(`H5:K${occurrencesLastRow}`).format.numberFormat = "#,##0";
ambiguousSheet.getRange(`A5:A${ambiguousLastRow}`).format.numberFormat = "#,##0";
ambiguousSheet.getRange(`E5:E${ambiguousLastRow}`).format.numberFormat = "#,##0";
summary.getRange("B10:C13").format.numberFormat = "#,##0";
summary.getRange("F10:G11").format.numberFormat = "#,##0";
summary.getRange("J10:J14").format.numberFormat = "#,##0";

// Compact workbook verification before export.
const summaryCheck = await workbook.inspect({
  kind: "table",
  range: "ملخص!A1:L39",
  include: "values,formulas",
  tableMaxRows: 39,
  tableMaxCols: 12,
  maxChars: 12000,
});
console.log("SUMMARY_CHECK");
console.log(summaryCheck.ndjson);

const missingCheck = await workbook.inspect({
  kind: "table",
  range: `${missingSheetName}!A4:S12`,
  include: "values,formulas",
  tableMaxRows: 9,
  tableMaxCols: 19,
  maxChars: 8000,
});
console.log("MISSING_SAMPLE_CHECK");
console.log(missingCheck.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("FORMULA_ERROR_SCAN");
console.log(errors.ndjson);

await fs.mkdir(outputDir, { recursive: true });
for (const [sheetName, fileName, range] of [
  ["ملخص", "preview-summary.png", "A1:L39"],
  [missingSheetName, "preview-missing.png", "A1:S18"],
  ["مواضع الظهور", "preview-occurrences.png", "A1:P18"],
  ["حالات تحتاج حسم", "preview-ambiguous.png", `A1:N${ambiguousLastRow}`],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1.2, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
const roundTrip = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const roundTripSummary = roundTrip.worksheets.getItem("ملخص");
const headlineValues = roundTripSummary.getRange("A5:G5").values[0];
const expectedHeadlineValues = [
  [0, checks.missingIdentities],
  [2, checks.missingOccurrences],
  [4, checks.ambiguousIdentities],
  [6, checks.allUncoveredIdentities],
];
for (const [columnIndex, expectedValue] of expectedHeadlineValues) {
  if (Number(headlineValues[columnIndex]) !== expectedValue) {
    throw new Error(`Round-trip summary mismatch at column ${columnIndex}: got ${headlineValues[columnIndex]}, expected ${expectedValue}`);
  }
}
const classValues = roundTripSummary.getRange("B10:C13").values;
const expectedClassValues = [
  [checks.oldOnly, checks.oldOnlyOccurrences],
  [checks.newOnly, checks.newOnlyOccurrences],
  [checks.shared, checks.sharedOccurrences],
  [checks.missingIdentities, checks.missingOccurrences],
];
if (JSON.stringify(classValues.map(row => row.map(Number))) !== JSON.stringify(expectedClassValues)) {
  throw new Error(`Round-trip plan classification mismatch: ${JSON.stringify(classValues)}`);
}
const roundTripCheck = await roundTrip.inspect({
  kind: "table",
  range: "ملخص!A4:L14",
  include: "values,formulas",
  tableMaxRows: 11,
  tableMaxCols: 12,
  maxChars: 6000,
});
console.log("ROUND_TRIP_CHECK");
console.log(roundTripCheck.ndjson);
const roundTripErrors = await roundTrip.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "round-trip formula error scan",
});
console.log("ROUND_TRIP_ERROR_SCAN");
console.log(roundTripErrors.ndjson);
console.log(JSON.stringify({ outputPath, checks, planRows: planRows.length, programDegreeRows: programDegreeRows.length }));
