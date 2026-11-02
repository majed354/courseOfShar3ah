'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const textOf = t => t.corrected_text || t.text;
const pageOf = t => t.page ? String(t.page)+(t.end_page&&t.end_page!==t.page?'–'+t.end_page:'') : '—';
let catalog, token, source, target, currentReport;
const groupKey = c => c.program+' | '+c.degree;
const selectedContext = () => catalog.contexts.find(c=>c.id===$('version').value);
function notice(message, error=false, busy=false) { $('notice').className='status'+(error?' error':'')+(busy?' busy':''); $('notice').textContent=message; }
async function api(route, body) {
  const r=await fetch(route, body ? {method:'POST',headers:{'Content-Type':'application/json','X-Equivalency-Token':token},body:JSON.stringify(body)} : {});
  const data=await r.json(); if(!r.ok) throw new Error(data.error || 'تعذر تنفيذ الطلب'); return data;
}
async function action(button, task) { button.disabled=true; try { await task(); } catch(e) { notice(e.message,true); } finally { button.disabled=false; } }
function courseLabel(c) { return `${c.code} · ${c.name} · ${c.context?c.context.program+' · '+c.context.degree+' · '+c.context.version:'مصدر إضافي بلا خطة محددة'}${c.topics.length?'':c.status==='no_fixed_topics'?' · بلا مفردات ثابتة':c.source_pdf?' · المفردات تحتاج استكمالًا':' · توصيف غير متاح'}`; }
function options(courses) { return '<option value="">اختر المقرر</option>'+courses.map(c=>`<option value="${esc(c.id)}">${esc(courseLabel(c))}</option>`).join(''); }
function sourceLink(c) { const key=c.catalog_course_id || c.id; return c.source_pdf || c.upload_pdf ? `<a href="/pdf/${esc(key)}" target="_blank" rel="noopener">فتح التوصيف</a>` : ''; }
function readingLabel(c) {
  if(c.extraction_method==='local_vision_transcription') return 'قراءة المفردات: نقل بصري آلي بالنموذج '+(c.transcription_model||'المحلي')+'؛ تحتاج مراجعة صورة المصدر.';
  if(c.extraction_method==='reviewed_visual_normalization') return 'قراءة المفردات: تمثيل معياري للمحتوى من قراءة بصرية؛ راجع النص الأصلي، فالصياغة ليست نقلًا حرفيًا.';
  if(c.extraction_method==='reviewed_visual_transcription') return 'قراءة المفردات: نقل بصري موثق بالصفحة وبصمة المصدر؛ لا يمثل اعتمادًا أكاديميًا.';
  return '';
}
function metadata(c) { return `<p class="muted">${esc(c.topics.length)} مفردة مستخرجة · ${sourceLink(c)} ${c.context ? '· الخطة '+esc(c.context.version):''}</p>`+(c.warnings||[]).map(w=>`<div class="warn">${esc(w)}</div>`).join('')+(c.excluded_rows?.length?`<p class="muted">استُبعد ${c.excluded_rows.length} صف للمراجعة أو الاختبار من مقام التغطية.</p>`:''); }
function editor(container, course) {
  $(container).innerHTML=course.topics.map((t,i)=>`<div class="topic-row" data-id="${esc(t.id)}"><span class="topic-index">${i+1}</span><div><textarea rows="2" aria-label="المفردة ${i+1}">${esc(textOf(t))}</textarea><div class="topic-foot"><span>${t.page?'صفحة '+t.page:'إدخال يدوي'}</span>${t.corrected_text?'<span class="tag">قراءة مستكملة من السياق</span>':''}${t.origin==='local_vision_transcription'?'<span class="tag">نقل بصري آلي؛ راجع الصورة</span>':''}<button type="button" class="remove-topic">حذف الصف</button><details><summary>النص المستخرج الأصلي</summary>${esc(t.text)}</details></div></div></div>`).join('')+'<div class="topic-tools"><button type="button" class="add-topic">إضافة مفردة</button></div>';
  $(container).querySelectorAll('.remove-topic').forEach(b=>b.onclick=()=>b.closest('.topic-row').remove());
  $(container).querySelector('.add-topic').onclick=()=>{
    const div=document.createElement('div');div.className='topic-row';div.dataset.id='manual'+crypto.randomUUID().replaceAll('-','');div.innerHTML='<span class="topic-index">+</span><div><textarea rows="2" aria-label="مفردة إضافية"></textarea><button class="remove-topic" type="button">حذف الصف</button></div>';div.querySelector('button').onclick=()=>div.remove();$(container).insertBefore(div,$(container).lastElementChild);div.querySelector('textarea').focus();
  };
  $(container).oninput=()=>{$('reviewed').checked=false;};
}
function readEditor(container) { return [...$(container).querySelectorAll('.topic-row')].map(row=>({id:row.dataset.id,text:row.querySelector('textarea').value.trim()})); }
function setSource(data) {
  source=data;target=null;currentReport=null;beneficiaryStatus();$('sourcePanel').hidden=false;$('sourceTitle').textContent='مفردات '+source.name;$('sourceMeta').innerHTML=metadata(source);editor('sourceTopics',source);
  $('candidatePanel').hidden=true;$('reportPanel').hidden=true;$('reviewed').checked=false;notice(`استُخرجت ${source.topics.length} مفردة. راجع النصوص وأكمل الكلمات الناقصة قبل البحث.`);$('sourcePanel').scrollIntoView({behavior:'smooth'});
}
function sourceOptions() {
  const group=$('sourceProgram').value;
  const all=[...catalog.courses.filter(c=>c.topics.length),...(catalog.library_sources||[])];
  $('sourceCourse').innerHTML=options(all.filter(c=>!group||(group==='__library__'?c.library_only:c.context&&groupKey(c.context)===group)));
}
function targetOptions() {
  const context=selectedContext();
  const courses=context?catalog.courses.filter(c=>c.context_id===context.id):[];
  $('targetCourse').innerHTML=options(courses);
  $('scopeInventory').textContent=context?`${context.program} · ${context.degree} · الخطة ${context.plan_type} ${context.version}: ${courses.filter(c=>c.topics.length).length} توصيفًا بمفردات مستخرجة من ${courses.length} مقررًا.`:'';
}
function clearTarget() {
  target=null;currentReport=null;beneficiaryStatus();$('targetReview').hidden=true;$('candidatePanel').hidden=true;$('reportPanel').hidden=true;$('candidates').innerHTML='';$('reviewed').checked=false;
}
function planOptions() {
  const plans=catalog.contexts.filter(c=>groupKey(c)===$('program').value).sort((a,b)=>Number(b.version)-Number(a.version));
  $('version').innerHTML=plans.map(c=>`<option value="${esc(c.id)}">${esc(c.plan_type)} · ${esc(c.version)}</option>`).join('');
  targetOptions();clearTarget();
}
function initContexts() {
  if(!catalog.contexts) {
    catalog.contexts=[];
    for(const course of catalog.courses) {
      const context={...course.context,id:'legacy'+course.context.version};course.context_id=context.id;
      if(!catalog.contexts.some(c=>c.id===context.id))catalog.contexts.push(context);
    }
  }
  const groups=[...new Set(catalog.contexts.map(groupKey))].sort((a,b)=>a.localeCompare(b,'ar'));
  const groupOptions=groups.map(g=>`<option value="${esc(g)}">${esc(g.replace(' | ',' · '))}</option>`).join('');
  $('program').innerHTML=groupOptions;$('program').value=groups.find(g=>g==='القرآن وعلومه | بكالوريوس')||groups[0];
  $('sourceProgram').innerHTML='<option value="">كل البرامج والدرجات</option>'+groupOptions+((catalog.library_sources||[]).length?'<option value="__library__">مصادر إضافية غير مرتبطة بخطة</option>':'');sourceOptions();planOptions();
}
function setTarget(id) {
  target=catalog.courses.find(c=>c.id===id);if(!target) return;currentReport=null;beneficiaryStatus();$('reportPanel').hidden=true;
  $('targetCourse').value=id;$('targetReview').hidden=false;$('targetTitle').textContent=target.name+' · '+target.code;$('targetMeta').innerHTML=metadata(target);editor('targetTopics',target);$('reviewed').checked=false;
  document.querySelectorAll('.candidate').forEach(b=>b.classList.toggle('selected',b.dataset.id===id));
}
function download(name, content, mime) { const url=URL.createObjectURL(new Blob([content],{type:mime}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
function beneficiaryValues() {
  return {name:($('beneficiaryName')?.value||'').trim(),number:($('beneficiaryNumber')?.value||'').trim()};
}
function beneficiaryIsDirty() {
  const entered=beneficiaryValues(),saved=currentReport?.beneficiary||{};
  return !!currentReport&&(entered.name!==(saved.name||'')||entered.number!==(saved.number||''));
}
function beneficiaryStatus() {
  const dirty=beneficiaryIsDirty(),state=$('beneficiarySaveState');
  if(state) state.className='muted'+(dirty?' beneficiary-dirty':'');
  if(state) state.textContent=dirty?'تغييرات غير محفوظة؛ احفظها لتحديث التقرير.':currentReport?'بيانات المستفيد محفوظة في هذا التقرير.':'تُضاف البيانات إلى التقرير عند إصداره.';
}
function showReportPreservingEdits(report,submitted) {
  const latest=beneficiaryValues();
  showReport(report);
  if(latest.name!==submitted.name||latest.number!==submitted.number) {
    if($('beneficiaryName')) $('beneficiaryName').value=latest.name;
    if($('beneficiaryNumber')) $('beneficiaryNumber').value=latest.number;
    beneficiaryStatus();
  }
}
async function saveBeneficiary() {
  if(!currentReport){beneficiaryStatus();notice('ستظهر بيانات المستفيد في التقرير بعد إصدار المقارنة.');return;}
  if(beneficiaryIsDirty()) {
    const submitted=beneficiaryValues(),reportId=currentReport.id;
    const report=await api('/api/reports/'+reportId+'/beneficiary',{beneficiary:submitted});
    if(currentReport?.id!==reportId) throw new Error('تغير التقرير أثناء الحفظ؛ افتح التقرير المطلوب قبل التصدير.');
    showReportPreservingEdits(report,submitted);
    if(beneficiaryIsDirty()) throw new Error('تغيرت بيانات المستفيد أثناء الحفظ؛ احفظ التعديل الجديد قبل تصدير التقرير.');
  }
  beneficiaryStatus();
}
function showReport(r) {
  currentReport=r;
  if($('beneficiaryName')) $('beneficiaryName').value=r.beneficiary?.name||'';
  if($('beneficiaryNumber')) $('beneficiaryNumber').value=r.beneficiary?.number||'';
  beneficiaryStatus();
  const calc=r.calculation,evidence=r.evidence||{},pairs=evidence.pairs||[],insufficient=calc.decision==='insufficient';
  const decisions={equivalent:'يمكن معادلته',lenient:'يمكن مع التسامح',not_equivalent:'لا يمكن معادلته',insufficient:'المعلومات لا تكفي'};
  const decision=Object.hasOwn(decisions,calc.decision)?calc.decision:'insufficient';
  const total=calc.total_topics,required=Math.ceil(total*.8);
  const percent=value=>Number.isFinite(value)?(Math.floor(value*100)/100).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:2})+'%':'—';
  const sources=new Map(r.source.topics.map(t=>[t.id,t]));
  const count=mode=>calc[mode+'_count']||0;
  const coverage=mode=>Number.isFinite(calc[mode+'_coverage'])?Math.max(0,Math.min(100,calc[mode+'_coverage'])):null;
  const names={strict:'الحساب الدقيق',lenient:'الحساب المتسامح'},threshold={strict:80,lenient:60};
  const coverageCard=mode=>{
    const value=coverage(mode),pending=insufficient||value===null;
    const label=pending?names[mode]+': التغطية لم تحسب':`${names[mode]}: تغطية ${percent(value)}، ${count(mode)} من ${total} مفردة`;
    return `<section class="coverage-card ${mode}" data-mode="${mode}" data-count="${pending?'':count(mode)}" data-total="${total}" data-coverage="${pending?'':value}"><div class="coverage-caption"><span class="report-kicker">توافق المفردة ≥${threshold[mode]}%</span><h3>${names[mode]}</h3></div>${pending?'<div class="coverage-pending"><b>—</b><span>لم تُحسب التغطية</span></div>':`<div class="coverage-visual"><svg class="coverage-gauge" viewBox="0 0 104 104" role="img" aria-label="${esc(label)}"><circle class="gauge-track" cx="52" cy="52" r="43" pathLength="100"/><circle class="gauge-value" cx="52" cy="52" r="43" pathLength="100" stroke-dasharray="${value} ${100-value}" transform="rotate(-90 52 52)"/></svg><div class="coverage-value"><b dir="ltr">${percent(value)}</b><span>من مفردات الهدف</span></div></div>`}<p class="coverage-count">${pending?'بانتظار اكتمال المصدر والمقارنة':`<strong>${count(mode)}</strong> من <strong>${total}</strong> مفردة محتسبة`}</p><span class="coverage-threshold">حد تغطية المقرر: 80%</span></section>`;
  };
  const bar=mode=>{const value=coverage(mode);return `<div class="coverage-bar-row" data-mode="${mode}"><div class="coverage-bar-label"><b>${names[mode]}</b><span>${count(mode)} محتسبة · ${Math.max(0,total-count(mode))} غير محتسبة</span></div><div class="coverage-track" role="img" aria-label="${esc(names[mode]+': '+percent(value)+'، حد القبول 80%')}"><span class="coverage-bar-fill ${mode}" style="width:${value}%"></span><span class="threshold-marker" style="left:80%"></span></div><div class="coverage-scale"><span>0%</span><span>حد القبول 80%</span><span>100%</span></div></div>`;};
  const sourceCard=(c,label,n)=>`<section class="course-card"><div class="course-card-top"><span class="report-section-number">${n}</span><span class="report-kicker">${label}</span>${c.code?'<bdi class="course-code" dir="ltr">'+esc(c.code)+'</bdi>':''}</div><h3>${esc(c.name)}</h3><p class="course-scope">${c.context?esc(c.context.program)+' · '+esc(c.context.degree)+'<br>الخطة '+esc(c.context.plan_type||'')+' '+esc(c.context.version):'توصيف مصدر المقارنة'}</p><dl class="course-facts"><div><dt>الساعات المعتمدة</dt><dd>${esc(c.hours??'غير محددة')}</dd></div><div><dt>المفردات</dt><dd>${c.topics.length}</dd></div></dl>${sourceLink(c)?'<div class="course-source-link">'+sourceLink(c)+'</div>':''}${readingLabel(c)?'<p class="report-note reading-disclosure">'+esc(readingLabel(c))+'</p>':''}${c.source_sha256?'<details class="source-fingerprint"><summary>بصمة ملف التوصيف</summary><span class="hash">SHA-256 '+esc(c.source_sha256)+'</span></details>':''}</section>`;
  const matchedCell=(t,mode)=>{
    const sid=calc[mode+'_matches']?.[t.id],pair=sid?pairs.find(p=>p.target_id===t.id&&p.source_id===sid):null,s=pair?sources.get(pair.source_id):null;
    if(!pair||!s) return '<td class="matching-cell"><span class="match-state uncounted">غير محتسبة</span><span class="match-empty">لا مقابلة محتسبة في هذا الحساب</span></td>';
    return `<td class="matching-cell"><span class="match-state ${mode}">محتسبة · <bdi dir="ltr">${esc(pair.score)}%</bdi></span><p>${esc(textOf(s))}</p><small>المصدر · ص ${esc(pageOf(s))} · ${esc(s.id)}</small>${s.corrected_text?'<span class="tag">قراءة مستكملة</span>':''}<p class="match-reason">${esc(pair.reason)}</p></td>`;
  };
  const rows=r.target.topics.map((t,i)=>{
    const topic=`<td class="target-topic"><span class="topic-order">${i+1}</span><p>${esc(textOf(t))}</p><small>الهدف · ص ${esc(pageOf(t))} · ${esc(t.id)}</small>${t.corrected_text?'<span class="tag">قراءة مستكملة</span>':''}${textOf(t)==='أخرى'?'<span class="tag">موضوع غير محدد في المصدر</span>':''}</td>`;
    if(insufficient) return `<tr>${topic}<td>الحساب معلق إلى استكمال المصدر والمقارنة؛ لا تُفسر هذه الحالة كعدم توافق.</td></tr>`;
    const best=pairs.filter(p=>p.target_id===t.id).sort((a,b)=>b.score-a.score)[0];
    const strict=!!calc.strict_matches?.[t.id],lenient=!!calc.lenient_matches?.[t.id];
    let note=strict&&lenient?'احتُسبت في الحسابين؛ قد تختلف المفردة المقابلة لأن كل حساب يبني مطابقة مستقلة.':strict?'احتُسبت في المطابقة الدقيقة. اختلف توزيع المقابلات في الحساب المتسامح.':lenient?'احتُسبت في المطابقة المتسامحة فقط.':'لم تُحتسب في أي من الحسابين.';
    if((!strict||!lenient)&&best) note+=` أعلى توافق مرصود لهذه المفردة ${percent(best.score)}؛ لا يكفي وحده للاحتساب إذا تكرر استعمال مفردة المصدر.`;
    return `<tr>${topic}${matchedCell(t,'strict')}${matchedCell(t,'lenient')}<td class="matching-note">${esc(note)}</td></tr>`;
  }).join('');
  const corrections=[['المصدر',r.source],['الهدف',r.target]].flatMap(([label,c])=>c.topics.filter(t=>t.corrected_text).map(t=>`<tr><td>${label} · ${esc(t.id)} · ص ${esc(pageOf(t))}</td><td>${esc(t.text)}</td><td>${esc(t.corrected_text)}</td><td>${esc(t.correction_method||'contextual_inference')}</td></tr>`));
  const date=r.created_at?new Date(r.created_at):null;
  const dated=date&&!Number.isNaN(date.getTime())?date.toLocaleDateString('ar-SA-u-ca-gregory-nu-latn',{year:'numeric',month:'long',day:'numeric'}):'غير مسجل في النسخة السابقة';
  const summary=insufficient?(calc.reason||'المصدر أو المقارنة غير مكتمل؛ لم تحسب نسبة المعادلة.'):`تتطلب المعادلة تغطية ${required} من ${total} مفردة على الأقل. بلغ الاحتساب الدقيق ${count('strict')}، والمتسامح ${count('lenient')} مفردة.`;
  $('report').innerHTML=`<div class="equivalency-report" data-decision="${decision}"><header class="report-head"><div class="report-brand"><span class="report-mark" aria-hidden="true">م</span><div><span class="report-kicker">كلية الشريعة والأنظمة</span><p>${esc(r.target.context?.program||'دراسة توافق المقررات')} · ${esc(r.target.context?.degree||'')}</p></div><span class="report-edition">دراسة معادلة<br>نسخة تجريبية</span></div><h1>تقرير توافق مفردات المقررات</h1><div class="report-reference"><span>تاريخ التقرير: ${esc(dated)}</span><span>رقم التقرير <bdi dir="ltr">${esc(r.id)}</bdi></span></div></header><section class="beneficiary-card" aria-label="بيانات المستفيد"><span class="report-section-number" aria-hidden="true">01</span><div><span class="report-kicker">اسم المستفيد</span><strong>${esc(r.beneficiary?.name||'غير مسجل')}</strong></div><div><span class="report-kicker">رقم المستفيد</span><strong><bdi dir="auto">${esc(r.beneficiary?.number||'غير مسجل')}</bdi></strong></div></section><section class="report-hero ${decision}"><div class="verdict-symbol" aria-hidden="true">${decision==='equivalent'?'✓':decision==='lenient'?'≈':decision==='not_equivalent'?'×':'…'}</div><div><span class="report-kicker">نتيجة دراسة المفردات</span><h2>${esc(decisions[decision])}</h2><p>${esc(summary)}</p><span class="verdict-scope">حكم تجريبي للمحتوى · يعتمد أكاديميًا من المختص</span></div></section><section class="report-block"><div class="report-section-heading"><span class="report-section-number">02</span><div><h2>المقرران محل الدراسة</h2><p>المقارنة من محتوى المصدر إلى المقرر الهدف المحدد</p></div></div><div class="source-grid">${sourceCard(r.source,'المقرر المصدر','أ')}${sourceCard(r.target,'المقرر الهدف','ب')}</div></section><section class="report-block"><div class="report-section-heading"><span class="report-section-number">03</span><div><h2>ملخص تغطية المفردات</h2><p>عدد مفردات الهدف المحتسبة ÷ جميع مفردات الهدف × 100</p></div></div><div class="report-summary">${coverageCard('strict')}${coverageCard('lenient')}</div>${insufficient?'<div class="pending-explanation">لا تظهر نسب أو أعمدة تغطية قبل اكتمال المعلومات؛ غياب النسبة لا يعني انعدام التوافق.</div>':`<div class="distribution-chart"><div class="distribution-heading"><h3>المحتسب والمتبقي من مفردات الهدف</h3><span>الخط المنقّط: حد القبول</span></div>${bar('strict')}${bar('lenient')}</div>`}<p class="report-note calculation-note">حد تغطية المقرر 80% في الحسابين. الحسابان مستقلان؛ يُحتسب كل صف هدف وكل صف مصدر مرة واحدة داخل كل حساب. قد تختلف المقابلات المختارة بينهما. يصدر الحكم من الأعداد قبل تقريب النسبة؛ درجة المفردة تقدير للمحتوى، وليست درجة ثقة النموذج أو نتيجة البحث الدلالي.</p></section><section class="report-block evidence-block"><div class="report-section-heading"><span class="report-section-number">04</span><div><h2>${insufficient?'مفردات الهدف قبل المقارنة':'تفصيل التوافق وأسباب الاحتساب'}</h2><p>${insufficient?'استكمل المفردات غير المحددة ثم أعد المقارنة':'تظهر مقابلة كل مفردة وسببها في كل حساب على حدة'}</p></div></div><div class="report-table-wrap"><table class="details-table"><thead><tr><th scope="col">مفردة المقرر الهدف</th>${insufficient?'<th scope="col">حالة المقارنة</th>':'<th scope="col">الحساب الدقيق · ≥80%</th><th scope="col">الحساب المتسامح · ≥60%</th><th scope="col">تفسير الاحتساب</th>'}</tr></thead><tbody>${rows||`<tr><td colspan="${insufficient?2:4}">لا تتوفر مفردات هدف ثابتة؛ يلزم استكمال المصدر قبل الحساب.</td></tr>`}</tbody></table></div></section>${corrections.length?'<section class="report-block corrections-block"><div class="report-section-heading"><span class="report-section-number">05</span><div><h2>القراءات المصححة والاستكمالات</h2><p>النص الأصلي محفوظ بجوار القراءة المستخدمة في هذه المقارنة</p></div></div><div class="report-table-wrap"><table class="corrections-table"><thead><tr><th>الموضع</th><th>المستخرج الأصلي</th><th>القراءة المستخدمة</th><th>الطريقة</th></tr></thead><tbody>'+corrections.join('')+'</tbody></table></div></section>':''}<section class="report-method"><h2>منهج الدراسة وحدود النتيجة</h2><p>${esc(r.notice||'نتيجة تجريبية للمفردات وفق سياسة 80/80/60؛ اعتماد المختص مستقل.')}</p><p>هذه مقارنة اتجاهية من المصدر إلى الهدف المحدد، ولا تثبت المعادلة العكسية. راجع اختلاف تجميع المفردات؛ لا يجزئ المحرك صفًا مركبًا أو يعيد استعماله آليًا. الساعات المعتمدة معروضة للمراجعة، ولا تغير حكم المفردات.</p><div class="method-facts"><div><span>محرك المقارنة</span><b>${esc(evidence.model||(evidence.provider==='exact_text'?'تطابق نصي حتمي':'المقارنة معلقة'))}</b></div><div><span>منهج التقدير</span><b>${esc(evidence.rubric||'80/80/60')}</b></div></div><p>${r.reviewed_by==='Codex_visual_and_context_pilot_test'?'مثال اختبار أعده Codex بمراجعة صفحات المصدر؛ ليس اعتمادًا من مختص.':'أُكدت مراجعة النصوص في واجهة التجربة؛ اعتماد المعادلة الأكاديمي مستقل.'}</p><details class="technical-evidence" open><summary>بصمات التحقق والمصدر</summary><span class="hash">Catalog: ${esc(r.catalog_id||'غير متاح')}<br>Model: ${esc(evidence.model_digest||'not used')}</span>${[r.source,r.target].filter(c=>c.source_sha256).map(c=>'<span class="hash">PDF '+esc(c.code||c.name)+': '+esc(c.source_sha256)+'</span>').join('')}</details></section><div class="signature"><div><span>اسم المختص</span><i></i></div><div><span>القرار والتوقيع</span><i></i></div><div><span>التاريخ</span><i></i></div></div><div class="report-end"><span>تقرير توافق مفردات المقررات · نسخة تجريبية للمراجعة الأكاديمية</span><bdi dir="ltr">${esc(r.id)}</bdi></div></div>`;
  $('reportPanel').hidden=false;$('reportPanel').scrollIntoView({behavior:'smooth'});notice('اكتمل التقرير. يمكنك مراجعة الأدلة وطباعته.');
}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(t=>t.classList.toggle('active',t===b));for(const name of ['upload','catalog','manual']) $(name+'Tab').hidden=name!==b.dataset.tab;});
$('extractButton').onclick=e=>action(e.target,async()=>{const file=$('pdfFile').files[0];if(!file) throw new Error('اختر توصيف PDF أولًا');if(file.size>12*1024*1024) throw new Error('الحد الأقصى 12 ميغابايت');notice('استخراج جدول الموضوعات مع حفظ صفحات المصدر…',false,true);const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192) binary+=String.fromCharCode(...bytes.subarray(i,i+8192));setSource(await api('/api/sources',{pdf_base64:btoa(binary),name:$('uploadName').value||file.name}));});
$('loadCourse').onclick=e=>action(e.target,async()=>{if(!$('sourceCourse').value) throw new Error('اختر المقرر المصدر');setSource(await api('/api/sources',{catalog_id:$('sourceCourse').value}));});
$('loadManual').onclick=e=>action(e.target,async()=>{const topics=$('manualTopics').value.split('\n').map(s=>s.trim()).filter(Boolean).map((text,i)=>({id:'t'+(i+1),text}));if(!topics.length) throw new Error('أدخل المفردات أولًا');setSource(await api('/api/sources',{name:$('manualName').value,topics}));});
$('sourceProgram').onchange=sourceOptions;
$('program').onchange=planOptions;
$('version').onchange=()=>{targetOptions();clearTarget();};
$('directTargetButton').onclick=()=>{targetOptions();$('candidatePanel').hidden=false;$('searchNote').textContent='اختر مقررًا من البرنامج والخطة المحددين، ثم راجع مفرداته.';$('candidatePanel').scrollIntoView({behavior:'smooth'});};
$('searchButton').onclick=e=>action(e.target,async()=>{notice('البحث في مفردات الخطة المختارة…',false,true);targetOptions();const context=selectedContext();if(!context)throw new Error('اختر البرنامج والخطة أولًا');const r=await api('/api/search',{source_id:source.id,topics:readEditor('sourceTopics'),version:context.version,context_id:context.id});if(selectedContext()?.id!==context.id){notice('تغيرت الخطة أثناء البحث؛ أعد البحث في الخطة الجديدة.');return;}$('candidates').innerHTML=r.candidates.map(c=>`<button class="candidate" data-id="${esc(c.id)}"><strong>${esc(c.name)}</strong><span>${esc(c.code)} · ${c.topics.length} مفردة · الخطة ${esc(c.context.version)}</span></button>`).join('');$('candidates').querySelectorAll('button').forEach(b=>b.onclick=()=>setTarget(b.dataset.id));$('candidatePanel').hidden=false;$('searchNote').textContent=`البحث ${r.method.startsWith('hybrid')?'النصي والدلالي':'النصي'} بين ${r.scope_count} توصيفًا له مفردات مستخرجة. ترتيب المرشحين لا يمثل نسبة المعادلة.`;notice(r.warning||'اختر المرشح وراجع مفرداته قبل تدقيق التوافق.',!!r.warning);$('candidatePanel').scrollIntoView({behavior:'smooth'});});
$('targetCourse').onchange=()=>setTarget($('targetCourse').value);
$('compareButton').onclick=e=>action(e.target,async()=>{if(!target) throw new Error('اختر المقرر الهدف');if(!$('reviewed').checked) throw new Error('أكد مراجعة مفردات المقررين أولًا');const beneficiarySnapshot=beneficiaryValues(),sourceSnapshot=source.id,targetSnapshot=target.id;const job=await api('/api/jobs',{source_id:sourceSnapshot,target_id:targetSnapshot,source_topics:readEditor('sourceTopics'),target_topics:readEditor('targetTopics'),reviewed:true,beneficiary:beneficiarySnapshot});notice('المهمة في المحرك المحلي. قد تستغرق المقارنة عدة دقائق…',false,true);while(true){await new Promise(resolve=>setTimeout(resolve,1500));const j=await api('/api/jobs/'+job.id);if(j.status==='error') throw new Error(j.message);if(j.status==='done'){if(source?.id!==sourceSnapshot||target?.id!==targetSnapshot){notice('اكتملت المقارنة السابقة، لكن المقرر المحدد تغير؛ أعد المقارنة للمقرر الحالي.');return;}history.replaceState(null,'','?report='+job.id);showReportPreservingEdits(j.result,beneficiarySnapshot);break;}notice(j.message+'…',false,true);}});
for(const id of ['beneficiaryName','beneficiaryNumber']) if($(id)) $(id).oninput=beneficiaryStatus;
if($('saveBeneficiary')) $('saveBeneficiary').onclick=e=>action(e.target,saveBeneficiary);
if($('editBeneficiary')) $('editBeneficiary').onclick=()=>{$('beneficiaryName')?.closest('.beneficiary-panel')?.scrollIntoView({behavior:'smooth',block:'center'});$('beneficiaryName')?.focus({preventScroll:true});};
$('printButton').onclick=e=>action(e.target,async()=>{await saveBeneficiary();window.print();});
$('jsonButton').onclick=e=>action(e.target,async()=>{await saveBeneficiary();download('equivalency-'+currentReport.id+'.json',JSON.stringify(currentReport,null,2),'application/json');});
$('htmlButton').onclick=e=>action(e.target,async()=>{await saveBeneficiary();const css=await(await fetch('/style.css')).text();const reportHTML=$('report').innerHTML.replace(/href="(\/pdf\/[^" ]+)"/g,(_,path)=>'href="'+esc(location.origin+path)+'"');const html='<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>تقرير معادلة المقررات</title><style>'+css+'</style><main><section class="panel" id="reportPanel"><article id="report">'+reportHTML+'<p class="report-note export-source-note">روابط التوصيفات تتطلب تشغيل خدمة المعادلة المحلية على الجهاز الذي صدر منه التقرير.</p></article></section></main></html>';download('equivalency-'+currentReport.id+'.html',html,'text/html');});
(async()=>{try{const r=await api('/api/catalog');catalog=r.catalog;token=r.token;initContexts();const available=catalog.courses.filter(c=>c.topics.length).length;$('inventory').textContent=`الفهرس: ${catalog.courses.length} ظهورًا في ${catalog.contexts.length} سياقًا دراسيًا، ${available} بمفردات مستخرجة؛ الاستخراج يحتاج مراجعة قبل الحكم.`;targetOptions();const id=new URLSearchParams(location.search).get('report');if(id){const j=await api('/api/jobs/'+id);if(j.result)showReport(j.result);}}catch(e){notice(e.message,true);}})();
