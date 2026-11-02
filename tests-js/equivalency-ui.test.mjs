import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

// Exercise the actual selection/report functions without controlling a user's browser.
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

function reportFixture({decision='equivalent', strict=4, lenient=5, total=5, beneficiary}={}) {
  const labels={equivalent:'يمكن معادلته',lenient:'يمكن مع التسامح',not_equivalent:'لا يمكن معادلته',insufficient:'المعلومات لا تكفي'};
  const targetTopics=Array.from({length:total},(_,i)=>({id:'t'+i,text:'مفردة الهدف '+i,page:5}));
  const sourceTopics=targetTopics.map((_,i)=>({id:'s'+i,text:'مفردة المصدر '+i,page:6}));
  const insufficient=decision==='insufficient';
  const pairs=insufficient?[]:targetTopics.map((t,i)=>({target_id:t.id,source_id:sourceTopics[i].id,score:i<strict?85:i<lenient?65:40,reason:'تعليل الدليل '+i}));
  return {
    id:'test-report',beneficiary,source:{id:'source',name:'المقرر المصدر',topics:sourceTopics,hours:2},
    target:{id:'target',name:'المقرر الهدف',topics:targetTopics,hours:2,context:{program:'الأنظمة',degree:'بكالوريوس',version:'47',plan_type:'جديدة'}},
    calculation:{decision,label:labels[decision],total_topics:total,coverage_threshold:80,strict_topic_threshold:80,lenient_topic_threshold:60,
      strict_count:insufficient?0:strict,lenient_count:insufficient?0:lenient,
      strict_coverage:insufficient?null:100*strict/total,lenient_coverage:insufficient?null:100*lenient/total,
      strict_matches:insufficient?{}:Object.fromEntries(targetTopics.slice(0,strict).map((t,i)=>[t.id,'s'+i])),
      lenient_matches:insufficient?{}:Object.fromEntries(targetTopics.slice(0,lenient).map((t,i)=>[t.id,'s'+i])),
      ...(insufficient?{reason:'موضوع غير محدد؛ يلزم استكمال المصدر'}:{})},
    evidence:{pairs,provider:'test_fixture',rubric:'test'},notice:'بيانات اختبار فقط',catalog_id:'test-catalog',reviewed_by:'user_confirmed_extraction'
  };
}

function renderedReport(input) {
  const state=ui();
  state.context.reportInput=input;
  vm.runInContext('showReport(reportInput)',state.context);
  return {...state,html:state.element('report').innerHTML};
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

test('report displays all decision outcomes with independent strict and lenient graphics', () => {
  for (const [decision,strict,lenient] of [['equivalent',4,5],['lenient',3,4],['not_equivalent',2,3]]) {
    const {html}=renderedReport(reportFixture({decision,strict,lenient}));
    assert.ok(html.includes(`data-decision="${decision}"`));
    assert.ok(html.includes('coverage-card'));
    assert.equal((html.match(/class="coverage-gauge"/g)||[]).length,2);
    assert.equal((html.match(/class="coverage-bar-row"/g)||[]).length,2);
    for (const [mode,count] of [['strict',strict],['lenient',lenient]]) {
      assert.ok(html.includes(`data-mode="${mode}" data-count="${count}" data-total="5" data-coverage="${count*20}"`));
      assert.ok(html.includes(`stroke-dasharray="${count*20} ${100-count*20}"`));
      assert.ok(html.includes(`class="coverage-bar-fill ${mode}" style="width:${count*20}%"`));
    }
    assert.ok(html.includes('80%'));
  }
});

test('insufficient evidence is shown as pending rather than zero percent or rejection', () => {
  const {html}=renderedReport(reportFixture({decision:'insufficient'}));
  assert.ok(html.includes('data-decision="insufficient"'));
  assert.ok(html.includes('coverage-pending'));
  assert.ok(html.includes('موضوع غير محدد'));
  assert.ok(!html.includes('class="coverage-gauge"'));
  assert.ok(!html.includes('class="coverage-bar-fill"'));
  assert.ok(html.includes('data-mode="strict" data-count="" data-total="5" data-coverage=""'));
  assert.ok(!html.includes('0.0%'));
  assert.ok(!html.includes('لا يمكن معادلته'));
});

test('beneficiary and evidence are escaped while textual beneficiary numbers retain zeroes and Arabic digits', () => {
  const input=reportFixture({beneficiary:{name:'<img src=x onerror=alert(1)>',number:'٠٠١23&"'}});
  input.source.name='<script>source</script>';
  input.target.topics[0].text='<svg onload=alert(2)>';
  input.evidence.pairs[0].reason='<iframe src=evil>';
  const {html}=renderedReport(input);
  assert.ok(html.includes('beneficiary-card'));
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(html.includes('٠٠١23&amp;&quot;'));
  assert.ok(html.includes('&lt;script&gt;source&lt;/script&gt;'));
  assert.ok(html.includes('&lt;svg onload=alert(2)&gt;'));
  assert.ok(html.includes('&lt;iframe src=evil&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('<img src=x'));
  assert.ok(!html.includes('<svg onload'));
  assert.ok(!html.includes('<iframe'));
});

test('legacy report without beneficiary still renders its decision and source evidence', () => {
  const input=reportFixture();delete input.beneficiary;
  const {html}=renderedReport(input);
  assert.ok(html.includes(input.calculation.label));
  assert.ok(html.includes('تعليل الدليل 0'));
  assert.ok(!html.includes('undefined'));
  assert.ok(!html.includes('NaN'));
});

test('different maximum matchings preserve both source assignments and explanations', () => {
  const input=reportFixture({decision:'lenient',strict:1,lenient:2,total:2});
  input.calculation.strict_matches={t0:'s0'};
  input.calculation.lenient_matches={t0:'s1',t1:'s0'};
  input.evidence.pairs=[
    {target_id:'t0',source_id:'s0',score:85,reason:'المقابلة الدقيقة المستقلة'},
    {target_id:'t0',source_id:'s1',score:65,reason:'المقابلة المتسامحة البديلة'},
    {target_id:'t1',source_id:'s0',score:65,reason:'الهدف الثاني في الحساب المتسامح'}
  ];
  const {html}=renderedReport(input);
  assert.ok(html.includes('المقابلة الدقيقة المستقلة'));
  assert.ok(html.includes('المقابلة المتسامحة البديلة'));
  assert.ok(html.includes('الهدف الثاني في الحساب المتسامح'));
  assert.ok(html.includes('50.0%'));
  assert.ok(html.includes('100.0%'));
});

test('report keeps a 79.5 percent boundary result below the acceptance threshold', () => {
  const {html}=renderedReport(reportFixture({decision:'not_equivalent',strict:159,lenient:159,total:200}));
  assert.ok(html.includes('data-decision="not_equivalent"'));
  assert.ok(html.includes('79.5%'));
  assert.ok(html.includes('لا يمكن معادلته'));
  assert.ok(!html.includes('80.0%'));
});

test('beneficiary can be saved into an existing report without starting a comparison', async () => {
  const input=reportFixture();
  const {context,element}=renderedReport(input);
  element('beneficiaryName').value='مستفيد تجريبي';
  element('beneficiaryNumber').value='٠٠١234';
  context.updatedReport={...input,beneficiary:{name:'مستفيد تجريبي',number:'٠٠١234'}};
  context.calls=[];
  await vm.runInContext('api=async(route,body)=>{calls.push({route,body});return updatedReport;}; saveBeneficiary()',context);
  assert.deepEqual(JSON.parse(JSON.stringify(context.calls)),[{
    route:'/api/reports/test-report/beneficiary',body:{beneficiary:{name:'مستفيد تجريبي',number:'٠٠١234'}}
  }]);
  assert.ok(element('report').innerHTML.includes('مستفيد تجريبي'));
  assert.ok(element('report').innerHTML.includes('٠٠١234'));
  assert.equal(vm.runInContext('beneficiaryIsDirty()',context),false);
  await vm.runInContext('saveBeneficiary()',context);
  assert.equal(context.calls.length,1,'an unchanged beneficiary should not trigger another request');
});

test('starting a new target context keeps beneficiary draft without updating a hidden earlier report', async () => {
  const input=reportFixture({beneficiary:{name:'اسم التقرير السابق',number:'001'}});
  const {context,element}=renderedReport(input);
  vm.runInContext('clearTarget()',context);
  element('beneficiaryName').value='مسودة المستفيد الجديد';
  context.calls=[];
  await vm.runInContext('api=async(route,body)=>{calls.push({route,body});throw Error("must not edit hidden report");}; saveBeneficiary()',context);
  assert.equal(context.calls.length,0);
  assert.equal(element('beneficiaryName').value,'مسودة المستفيد الجديد');
  assert.equal(element('beneficiaryNumber').value,'001');
  assert.equal(element('reportPanel').hidden,true);
});

test('typing while beneficiary save is pending preserves the latest draft and prevents exporting stale details', async () => {
  const input=reportFixture();
  const {context,element}=renderedReport(input);
  element('beneficiaryName').value='الاسم المرسل';
  element('beneficiaryNumber').value='001';
  const pending=vm.runInContext('api=()=>new Promise(resolve=>{globalThis.finishRequest=resolve;}); saveBeneficiary()',context);
  element('beneficiaryName').value='الاسم الأحدث أثناء الحفظ';
  element('beneficiaryNumber').value='٠٠٢';
  context.finishRequest({...input,beneficiary:{name:'الاسم المرسل',number:'001'}});
  await assert.rejects(pending,/تغيرت بيانات المستفيد أثناء الحفظ/);
  assert.equal(element('beneficiaryName').value,'الاسم الأحدث أثناء الحفظ');
  assert.equal(element('beneficiaryNumber').value,'٠٠٢');
  assert.equal(vm.runInContext('beneficiaryIsDirty()',context),true);
  assert.ok(element('beneficiarySaveState').textContent.includes('غير محفوظة'));
});

test('a late beneficiary save cannot reopen an earlier report after the target context changes', async () => {
  const input=reportFixture();
  const {context,element}=renderedReport(input);
  element('beneficiaryName').value='بيانات التقرير السابق';
  const pending=vm.runInContext('api=()=>new Promise(resolve=>{globalThis.finishRequest=resolve;}); saveBeneficiary()',context);
  vm.runInContext('clearTarget()',context);
  element('beneficiaryName').value='مسودة السياق الجديد';
  context.finishRequest({...input,beneficiary:{name:'بيانات التقرير السابق',number:''}});
  await assert.rejects(pending,/تغير التقرير أثناء الحفظ/);
  assert.equal(element('reportPanel').hidden,true);
  assert.equal(element('beneficiaryName').value,'مسودة السياق الجديد');
});
