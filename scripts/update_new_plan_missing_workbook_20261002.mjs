import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root = '/Users/majd/Desktop/codex/courseOfShar3ah-main';
const path = `${root}/قائمة_المقررات_التخصصية_المفقودة_2026-09-10.xlsx`;
const tmp = `${root}/tmp/new-plan-20261002`;
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
const coverage = JSON.parse(await fs.readFile(`${root}/assets/course-specifications/new-plan-updates-20261002/coverage.json`, 'utf8'));
const recovered = new Set(coverage.recovered_codes);
const summary = workbook.worksheets.getItem('الملخص');
const identities = workbook.worksheets.getItem('المقررات المفقودة');
const occurrences = workbook.worksheets.getItem('مواضع الخطط');

if (process.argv.includes('--inspect')) {
  console.log((await workbook.inspect({kind:'workbook,sheet,table',maxChars:2500,tableMaxRows:3,tableMaxCols:5})).ndjson);
  for (const sheet of [summary, identities, occurrences]) {
    const preview = await workbook.render({sheetName:sheet.name,range:sheet === summary ? 'A1:I21' : (sheet === identities ? 'A1:L9' : 'A1:O9'),scale:1,format:'png'});
    await fs.writeFile(`${tmp}/before-${sheet.name}.png`,new Uint8Array(await preview.arrayBuffer()));
  }
  process.exit(0);
}

// Update only the affected summary cells; keep all unrelated values/styles.
const values = summary.getRange('A1:I21').values;
summary.getRange('A3').values = [['المصدر: data.json في مستودع التوصيفات، بتاريخ 2026-10-02. النطاق: رموز 200* والاستثناء القديم 101221-2، دون الرسالة والاختبار الشامل أو مقررات الأقسام الخارجية.']];
for (const stats of coverage.programs) {
  const index = values.findIndex(row => row[0]===stats.program && row[1]===stats.degree);
  if (index < 0) throw new Error(`Missing summary program ${stats.program}`);
  summary.getRange(`E${index+1}:H${index+1}`).values = [[stats.available,stats.missing,stats.available/stats.required,stats.missing_identities]];
}
const total = values.findIndex(row => row[0]==='الإجمالي');
if (total < 0) throw new Error('Missing total row');
summary.getRange(`E${total+1}:H${total+1}`).values = [[coverage.available,coverage.missing,coverage.coverage,coverage.missing_identities]];

for (const [sheet, columns, codeColumn, tableName, expected, label] of [
  [identities,'L',1,'MissingCourseIdentities',coverage.missing_identities,'عدد الهويات الفريدة'],
  [occurrences,'O',6,'MissingCourseOccurrences',coverage.missing,'عدد المواضع'],
]) {
  const original = sheet.getRange(`A1:${columns}120`).values;
  const prefix = original.slice(0,5);
  prefix[2][0] = sheet === identities ? `${label}: ${expected}. قد يظهر المقرر نفسه في أكثر من برنامج أو خطة، وتوضح الأعمدة جميع المواضع المتأثرة.` : `${label}: ${expected}. كل صف يمثل ظهور مقرر في برنامج وخطة وإصدار محدد.`;
  const rows = original.slice(5).filter(row => row[codeColumn] && !recovered.has(String(row[codeColumn])));
  if (rows.length !== expected) throw new Error(`Unexpected ${sheet.name} count ${rows.length}`);
  rows.forEach((row,index) => {row[0]=index+1;});
  const table = sheet.tables.getItem(tableName);
  const style = table.style;
  const bandedColumns = table.showBandedColumns;
  const filterButton = table.showFilterButton;
  table.delete();
  sheet.getRange(`A1:${columns}120`).clear({applyTo:'contents'});
  sheet.getRange('A1').writeValues([...prefix,...rows]);
  const replacement = sheet.tables.add(`A5:${columns}${rows.length+5}`,true,tableName);
  replacement.style=style;
  replacement.showBandedColumns=bandedColumns;
  replacement.showFilterButton=filterButton;
}
workbook.recalculate();
console.log((await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:50},summary:'final error scan'})).ndjson);
for (const sheet of [summary,identities,occurrences]) {
  const preview=await workbook.render({sheetName:sheet.name,range:sheet===summary?'A1:I21':(sheet===identities?'A1:L9':'A1:O9'),scale:1,format:'png'});
  await fs.writeFile(`${tmp}/after-${sheet.name}.png`,new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path);
console.log(JSON.stringify({available:coverage.available,missing:coverage.missing,identities:coverage.missing_identities}));
