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
  source=data;$('sourcePanel').hidden=false;$('sourceTitle').textContent='مفردات '+source.name;$('sourceMeta').innerHTML=metadata(source);editor('sourceTopics',source);
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
  target=null;$('targetReview').hidden=true;$('candidatePanel').hidden=true;$('reportPanel').hidden=true;$('candidates').innerHTML='';$('reviewed').checked=false;
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
  target=catalog.courses.find(c=>c.id===id);if(!target) return;
  $('targetCourse').value=id;$('targetReview').hidden=false;$('targetTitle').textContent=target.name+' · '+target.code;$('targetMeta').innerHTML=metadata(target);editor('targetTopics',target);$('reviewed').checked=false;
  document.querySelectorAll('.candidate').forEach(b=>b.classList.toggle('selected',b.dataset.id===id));
}
function download(name, content, mime) { const url=URL.createObjectURL(new Blob([content],{type:mime}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
function showReport(r) {
  currentReport=r;const calc=r.calculation, pairs=r.evidence.pairs;const sources=new Map(r.source.topics.map(t=>[t.id,t]));
  const percent=x=>x==null?'—':x.toFixed(1)+'%';
  const detail=r.target.topics.map((t,i)=>{
    const sid=calc.strict_matches[t.id] || calc.lenient_matches[t.id];
    const best=sid ? pairs.find(p=>p.target_id===t.id&&p.source_id===sid) : pairs.filter(p=>p.target_id===t.id).sort((a,b)=>b.score-a.score)[0];
    const s=best?sources.get(best.source_id):null;
    const counted=calc.decision==='insufficient'?'الحساب معلق':calc.strict_matches[t.id]?'دقيق ومتسامح':calc.lenient_matches[t.id]?'بالتسامح فقط':'لم تُحتسب';
    let why=best?.reason || 'لم تتوفر مقارنة مكتملة';
    if(calc.decision==='insufficient') why+=' · لم يحتسب التوافق لأن الحساب معلق إلى استكمال المصدر.';
    else if(!sid && best?.score>=60) why+=' · لم تُحتسب لتجنب احتساب مفردة المصدر نفسها أكثر من مرة.';
    if(calc.decision==='insufficient') return `<tr><td class="number">${i+1}</td><td>${esc(textOf(t))}<br><small>ص ${esc(pageOf(t))} · ${esc(t.id)}</small>${textOf(t)==='أخرى'?'<br><span class="tag">موضوع غير محدد في المصدر</span>':''}</td></tr>`;
    return `<tr><td class="number">${i+1}</td><td>${esc(textOf(t))}<br><small>ص ${esc(pageOf(t))} · ${esc(t.id)}</small>${t.corrected_text?'<br><span class="tag">نص مستكمل</span>':''}</td><td>${s?esc(textOf(s)):'—'}<br><small>${s?'ص '+esc(pageOf(s))+' · '+esc(s.id):''}</small>${s?.corrected_text?'<br><span class="tag">نص مستكمل</span>':''}</td><td class="number">${best?best.score+'%':'—'}</td><td>${esc(counted)}<br>${esc(why)}</td></tr>`;
  }).join('');
  const sourceCard=(c,label)=>`<div><b>${label}</b><p>${esc(c.name)}${c.code?' · <bdi dir="ltr">'+esc(c.code)+'</bdi>':''}<br>${c.context?esc(c.context.program)+' · '+esc(c.context.degree)+' · '+esc(c.context.plan_type)+' '+esc(c.context.version):'توصيف مصدر المقارنة'}</p><p class="muted">الساعات المعتمدة: ${esc(c.hours??'غير محددة')} · ${c.topics.length} مفردة · ${sourceLink(c)}</p>${readingLabel(c)?'<p class="report-note">'+esc(readingLabel(c))+'</p>':''}${c.source_sha256?'<span class="hash">SHA-256 '+esc(c.source_sha256)+'</span>':''}</div>`;
  const corrections=[['المصدر',r.source],['الهدف',r.target]].flatMap(([label,c])=>c.topics.filter(t=>t.corrected_text).map(t=>`<tr><td>${label} · ${esc(t.id)} · ص ${esc(t.page??'—')}</td><td>${esc(t.text)}</td><td>${esc(t.corrected_text)}</td><td>${esc(t.correction_method||'contextual_inference')}</td></tr>`));
  const required=Math.ceil(calc.total_topics*.8);
  $('report').innerHTML=`<div class="report-head"><div class="eyebrow">${esc(r.target.context?.program||'كلية الشريعة والأنظمة')} · ${esc(r.target.context?.degree||'')} · دراسة معادلة تجريبية</div><h1>تقرير توافق مفردات المقررات</h1><p class="muted">${esc(new Date().toLocaleDateString('ar-SA-u-ca-gregory-nu-latn'))} · رقم التقرير <span dir="ltr">${esc(r.id)}</span></p></div><div class="source-grid">${sourceCard(r.source,'المقرر المصدر')}${sourceCard(r.target,'المقرر الهدف')}</div><div class="verdict ${calc.decision==='not_equivalent'?'negative':calc.decision==='lenient'?'lenient':''}"><h2>${esc(calc.label)}</h2><p>${calc.decision==='insufficient'?esc(calc.reason||'المصدر أو المقارنة غير مكتمل؛ لم تحسب نسبة المعادلة.'):`المطلوب تغطية ${required} من ${calc.total_topics} مفردة على الأقل. ${calc.strict_count} مفردة في الحساب الدقيق، و${calc.lenient_count} في الحساب المتسامح.`}</p></div><div class="metrics"><div class="metric"><b>${percent(calc.strict_coverage)}</b><span>التغطية الدقيقة · توافق المفردة ≥80%</span></div><div class="metric"><b>${percent(calc.lenient_coverage)}</b><span>التغطية المتسامحة · توافق المفردة ≥60%</span></div></div><p class="report-note">نسبة التغطية = عدد مفردات الهدف المحتسبة ÷ جميع مفردات الهدف × 100. حد تغطية المقرر 80% في الحسابين. يُحتسب كل صف هدف مرة واحدة، وكل صف مصدر مرة واحدة في كل حساب، ولا تُقرّب النسب قبل اتخاذ الحكم. درجة المفردة تقدير للمحتوى وليست درجة ثقة النموذج أو درجة البحث الدلالي.</p><h3>${calc.decision==='insufficient'?'مفردات الهدف قبل المقارنة':'المقارنة التفصيلية'}</h3><table><thead><tr><th>#</th><th>مفردة المقرر الهدف</th>${calc.decision==='insufficient'?'':'<th>مقابلتها في المصدر</th><th>التوافق</th><th>الاحتساب والتعليل</th>'}</tr></thead><tbody>${detail}</tbody></table>${corrections.length?'<h3>القراءات المصححة والاستكمالات</h3><table><thead><tr><th>الموضع</th><th>المستخرج الأصلي</th><th>القراءة المستخدمة</th><th>الطريقة</th></tr></thead><tbody>'+corrections.join('')+'</tbody></table>':''}<h3>نطاق النتيجة وأثر المصدر</h3><p class="report-note">${esc(r.notice)}<br>هذه مقارنة اتجاهية من المصدر إلى الهدف المحدد، ولا تثبت المعادلة العكسية. راجع اختلاف تجميع المفردات قبل الاعتماد، إذ لا يجزئ المحرك صفًا مركبًا أو يعيد استعماله آليًا.</p><p class="report-note">محرك المقارنة: ${esc(r.evidence.model||(r.evidence.provider==='exact_text'?'تطابق نصي حتمي':'المقارنة معلقة إلى استكمال المصدر'))} · ${esc(r.evidence.rubric)}${r.evidence.seconds?' · '+r.evidence.seconds+' ثانية':''}<br>${r.reviewed_by==='Codex_visual_and_context_pilot_test'?'مثال اختبار أعده Codex بمراجعة صفحات المصدر؛ ليس اعتمادًا من مختص.':'أُكدت مراجعة النصوص في واجهة التجربة؛ اعتماد المعادلة الأكاديمي مستقل.'}</p><span class="hash">Catalog: ${esc(r.catalog_id)}<br>Model: ${esc(r.evidence.model_digest||'not used')}</span><div class="signature"><span>اسم المختص: ................................</span><span>القرار والتوقيع: ................................</span><span>التاريخ: ................</span></div>`;
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
$('compareButton').onclick=e=>action(e.target,async()=>{if(!target) throw new Error('اختر المقرر الهدف');if(!$('reviewed').checked) throw new Error('أكد مراجعة مفردات المقررين أولًا');const job=await api('/api/jobs',{source_id:source.id,target_id:target.id,source_topics:readEditor('sourceTopics'),target_topics:readEditor('targetTopics'),reviewed:true});notice('المهمة في المحرك المحلي. قد تستغرق المقارنة عدة دقائق…',false,true);while(true){await new Promise(resolve=>setTimeout(resolve,1500));const j=await api('/api/jobs/'+job.id);if(j.status==='error') throw new Error(j.message);if(j.status==='done'){history.replaceState(null,'','?report='+job.id);showReport(j.result);break;}notice(j.message+'…',false,true);}});
$('printButton').onclick=()=>window.print();
$('jsonButton').onclick=()=>download('equivalency-'+currentReport.id+'.json',JSON.stringify(currentReport,null,2),'application/json');
$('htmlButton').onclick=async()=>{const css=await(await fetch('/style.css')).text();const html='<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>تقرير معادلة المقررات</title><style>'+css+'</style><main><section class="panel" id="reportPanel"><article id="report">'+$('report').innerHTML+'</article></section></main></html>';download('equivalency-'+currentReport.id+'.html',html,'text/html');};
(async()=>{try{const r=await api('/api/catalog');catalog=r.catalog;token=r.token;initContexts();const available=catalog.courses.filter(c=>c.topics.length).length;$('inventory').textContent=`الفهرس: ${catalog.courses.length} ظهورًا في ${catalog.contexts.length} سياقًا دراسيًا، ${available} بمفردات مستخرجة؛ الاستخراج يحتاج مراجعة قبل الحكم.`;targetOptions();const id=new URLSearchParams(location.search).get('report');if(id){const j=await api('/api/jobs/'+id);if(j.result)showReport(j.result);}}catch(e){notice(e.message,true);}})();
