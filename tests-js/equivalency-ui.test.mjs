import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

// Exercise the actual selection functions without controlling a user's browser.
function ui() {
  const nodes = new Map();
  const element = id => {
    if (!nodes.has(id)) nodes.set(id, {
      value: '', options: [], hidden: false, textContent: '',
      scrollIntoView() {},
      set innerHTML(html) {
        this.html = html;
        this.options = [...html.matchAll(/<option value="([^"]*)">([^<]*)<\/option>/g)]
          .map(m => ({value:m[1], text:m[2]}));
        if (this.options.length) this.value = this.options[0].value;
      },
      get innerHTML() { return this.html || ''; }
    });
    return nodes.get(id);
  };
  const context = vm.createContext({document:{getElementById:element, querySelectorAll:()=>[]}, console});
  const source = fs.readFileSync(new URL('../equivalency-pilot/app.js', import.meta.url), 'utf8');
  vm.runInContext(source.slice(0,source.indexOf("document.querySelectorAll('[data-tab]')")),context);
  const catalog = JSON.parse(fs.readFileSync(new URL('../equivalency-pilot/catalog.json', import.meta.url)));
  context.inputCatalog = catalog;
  vm.runInContext('catalog = inputCatalog; initContexts();',context);
  return {context, element, catalog};
}

test('college selectors cover every context and retain Quran default', () => {
  const {context,element,catalog} = ui();
  assert.equal(element('program').value,'القرآن وعلومه | بكالوريوس');
  for(const scope of catalog.contexts) {
    element('program').value=scope.program+' | '+scope.degree;
    vm.runInContext('planOptions()',context);
    assert.ok(element('version').options.some(o=>o.value===scope.id));
    element('version').value=scope.id;
    vm.runInContext('targetOptions()',context);
    const expected=catalog.courses.filter(c=>c.context_id===scope.id).map(c=>c.id);
    assert.deepEqual(element('targetCourse').options.map(o=>o.value).filter(Boolean),expected);
  }
});

test('source filter distinguishes master and doctorate with the same program name', () => {
  const {context,element,catalog} = ui();
  element('sourceProgram').value='القراءات | دكتوراه';
  vm.runInContext('sourceOptions()',context);
  const expected=catalog.courses.filter(c=>c.context.program==='القراءات'&&c.context.degree==='دكتوراه'&&c.topics.length).map(c=>c.id);
  assert.deepEqual(element('sourceCourse').options.map(o=>o.value).filter(Boolean),expected);
});

test('changing a target program clears the prior candidate and report state', () => {
  const {context,element} = ui();
  element('candidatePanel').hidden=false;element('reportPanel').hidden=false;element('reviewed').checked=true;
  vm.runInContext('clearTarget()',context);
  assert.equal(element('candidatePanel').hidden,true);
  assert.equal(element('reportPanel').hidden,true);
  assert.equal(element('reviewed').checked,false);
});

test('unscoped library documents are source choices and never plan targets', () => {
  const {context,element,catalog} = ui();
  element('sourceProgram').value='__library__';
  vm.runInContext('sourceOptions()',context);
  assert.deepEqual(element('sourceCourse').options.map(o=>o.value).filter(Boolean),(catalog.library_sources||[]).map(c=>c.id));
  const libraryIds=new Set((catalog.library_sources||[]).map(c=>c.id));
  assert.ok(element('targetCourse').options.every(o=>!libraryIds.has(o.value)));
});

test('printed report identifies the target program and discloses normalized readings', () => {
  const {context,element} = ui();
  context.reportInput={id:'test',source:{id:'s',name:'مصدر',topics:[]},target:{id:'t',name:'هدف',topics:[],context:{program:'الأنظمة',degree:'بكالوريوس',version:'47'},extraction_method:'reviewed_visual_normalization'},
    calculation:{decision:'insufficient',label:'المعلومات لا تكفي',total_topics:0,strict_matches:{},lenient_matches:{},strict_count:0,lenient_count:0},evidence:{pairs:[]},notice:'اختبار فقط'};
  vm.runInContext('showReport(reportInput)',context);
  assert.ok(element('report').innerHTML.includes('الأنظمة'));
  assert.ok(element('report').innerHTML.includes('بكالوريوس'));
  assert.ok(element('report').innerHTML.includes('ليست نقلًا حرفيًا'));
});
