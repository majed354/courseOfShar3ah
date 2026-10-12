let publishedEditorTarget = null;
let publishedEditorBusy = false;
let publishedEditorPreview = null;
let publishedEditorAuthPromise = null;

function requestPublishedEditorAccess() {
    if (publishedEditorAuthPromise) return publishedEditorAuthPromise;
    publishedEditorAuthPromise = new Promise(resolve => {
        const dialog = document.createElement('dialog');
        dialog.className = 'published-course-editor published-editor-login';
        dialog.setAttribute('aria-labelledby', 'editorLoginTitle');
        dialog.innerHTML = `<form>
            <h3 id="editorLoginTitle">تفعيل صلاحيات التعديل</h3>
            <label>كلمة المرور<input name="password" type="password" inputmode="numeric" autocomplete="current-password" required class="edit-input" dir="ltr"></label>
            <p class="published-editor-note">تُقبل الأرقام العربية والإنجليزية.</p>
            <p role="status" aria-live="polite"></p>
            <button type="submit" class="download-btn save-edit">تفعيل الصلاحيات</button>
            <button type="button" class="mini-btn">إلغاء</button>
        </form>`;
        document.body.appendChild(dialog);
        dialog.querySelector('[type=button]').onclick = () => dialog.close();
        dialog.onclose = () => { dialog.remove(); resolve(editAccessGranted); };
        dialog.querySelector('form').onsubmit = async event => {
            event.preventDefault();
            const submit = dialog.querySelector('[type=submit]');
            const status = dialog.querySelector('[role=status]');
            submit.disabled = true;
            status.textContent = 'جارٍ التحقق…';
            try {
                const response = await fetch('/.netlify/functions/course-editor', {
                    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: normalizePasswordInput(dialog.querySelector('input').value) })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || 'تعذر تفعيل الصلاحيات.');
                editAccessGranted = true;
                dialog.close();
            } catch (error) {
                status.textContent = error.message || 'تعذر الاتصال بخدمة الصلاحيات.';
                submit.disabled = false;
            }
        };
        dialog.showModal();
    }).finally(() => { publishedEditorAuthPromise = null; });
    return publishedEditorAuthPromise;
}

function getPublishedEditorDialog() {
    let dialog = document.getElementById('publishedCourseEditor');
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'publishedCourseEditor';
    dialog.className = 'published-course-editor';
    dialog.setAttribute('aria-labelledby', 'publishedEditorTitle');
    dialog.addEventListener('cancel', event => { if (publishedEditorBusy) event.preventDefault(); });
    document.body.appendChild(dialog);
    return dialog;
}

async function openPublishedCourseEditor(courseIndex) {
    if (!await requestEditAccess()) return;
    const program = getCurrentProgram();
    const course = program?.courses[courseIndex];
    const sourceIndex = course?._sourceCourseIndex;
    const base = baseProgramsData?.programs.find(item => item.id === program?.id)?.courses[sourceIndex];
    if (!course || !base) {
        alert('النشر متاح للمقررات الموجودة في الخطة المنشورة. هذا المقرر محلي أو تغير موضعه؛ حدّث الصفحة أولًا.');
        return;
    }
    const entry = siteEditsRegistry.entries.find(item => item.id === `${program.id}:${sourceIndex}`);
    publishedEditorTarget = {
        program_id: program.id, course_index: sourceIndex, expected_revision: entry?.revision || null,
        source: { code: base.code, name: base.name, hours: base.hours },
        local_course_index: courseIndex
    };
    const details = getCourseDetails(course.code, buildProgramContext(program), course.name);
    const dialog = getPublishedEditorDialog();
    if (publishedEditorPreview) URL.revokeObjectURL(publishedEditorPreview);
    publishedEditorPreview = null;
    dialog.innerHTML = `
        <form id="publishedEditorForm" onsubmit="publishCourseEditor(event)">
            <div class="published-editor-header">
                <h3 id="publishedEditorTitle">تعديل المقرر ونشره</h3>
                <button type="button" class="mini-btn" onclick="closePublishedCourseEditor()" aria-label="إغلاق نافذة التعديل">إغلاق</button>
            </div>
            <p class="published-editor-scope">${escapeHtml(program.name)} · ${escapeHtml(program.degree)} · الخطة ${escapeHtml(program.plan_type)} (${escapeHtml(program.version)})</p>
            <label class="published-editor-check"><input type="checkbox" name="save_fields" checked onchange="document.getElementById('publishedEditorFields').disabled = !this.checked"> حفظ بيانات المقرر</label>
            <fieldset id="publishedEditorFields" class="published-editor-grid">
                <legend class="sr-only">بيانات المقرر</legend>
                <label>رمز المقرر<input name="code" required maxlength="64" class="edit-input" dir="ltr" value="${escapeHtml(course.code)}"></label>
                <label>اسم المقرر<input name="name" required maxlength="250" class="edit-input" value="${escapeHtml(course.name)}"></label>
                <label>الاسم بالإنجليزية<input name="name_en" maxlength="250" class="edit-input" dir="ltr" value="${escapeHtml(course.name_en || '')}"></label>
                <label>الساعات<input name="hours" required type="number" min="0" max="30" step="1" class="edit-input" value="${toNumber(course.hours, 0)}"></label>
                <label>المستوى<select name="level" class="edit-select">${levelOptionsHtml(course.level)}</select></label>
                <label>نوع المقرر<input name="type" maxlength="80" class="edit-input" value="${escapeHtml(course.type || 'نظري')}"></label>
                <label>التصنيف<input name="category" maxlength="120" class="edit-input" value="${escapeHtml(course.category || '')}"></label>
                <label class="published-editor-check"><input type="checkbox" name="optional_pool" ${course.optional_pool ? 'checked' : ''}> اختياري خارج المستويات</label>
            </fieldset>
            <section class="published-editor-pdf">
                <h4>ملف PDF <small>(اختياري)</small></h4>
                ${details?.pdf_url ? `<a href="${escapeHtml(sanitizeResourceUrl(details.pdf_url))}" target="_blank" rel="noopener">عرض PDF الحالي</a>` : '<p>لا يوجد PDF معروض لهذا المقرر.</p>'}
                <label>اختيار PDF — حتى 4 ميجابايت<input type="file" name="pdf" accept="application/pdf,.pdf" onchange="previewPublishedEditorPdf(this)"></label>
                <a id="publishedEditorPreview" hidden target="_blank" rel="noopener">معاينة الملف المختار</a>
                <label>عند رفع ملف جديد<select name="pdf_mode" class="edit-select">
                    <option value="replace">استبدال PDF المعروض، مع حفظ السابق</option>
                    <option value="add">إضافة PDF آخر مع إبقاء الحالي</option>
                </select></label>
                <p class="published-editor-note">يمكنك حفظ البيانات وحدها، أو إلغاء «حفظ بيانات المقرر» لتعديل PDF وحده. يستمر الملف الحالي إذا لم تختر ملفًا جديدًا.</p>
            </section>
            <label class="published-editor-check"><input name="confirmed" type="checkbox" required> تحققت من صحة البيانات ومطابقة الملف لهذا المقرر والخطة.</label>
            <p id="publishedEditorStatus" role="status" aria-live="polite"></p>
            <button id="publishedEditorSubmit" class="download-btn save-edit" type="submit">حفظ ونشر للجميع</button>
        </form>`;
    dialog.showModal();
}

function closePublishedCourseEditor() {
    if (!publishedEditorBusy) getPublishedEditorDialog().close();
}

function previewPublishedEditorPdf(input) {
    if (publishedEditorPreview) URL.revokeObjectURL(publishedEditorPreview);
    const link = document.getElementById('publishedEditorPreview');
    const file = input.files[0];
    link.hidden = true;
    if (!file) return;
    if (!/\.pdf$/i.test(file.name) || !file.size || file.size > 4 * 1024 * 1024) {
        input.value = '';
        document.getElementById('publishedEditorStatus').textContent = 'اختر PDF صالحًا بحجم لا يتجاوز 4 ميجابايت.';
        return;
    }
    publishedEditorPreview = URL.createObjectURL(file);
    link.href = publishedEditorPreview;
    link.hidden = false;
    document.getElementById('publishedEditorStatus').textContent = '';
}

async function publishCourseEditor(event) {
    event.preventDefault();
    if (publishedEditorBusy || !publishedEditorTarget) return;
    if (!await requestEditAccess()) return;
    if (publishedEditorBusy) return;
    const form = event.target;
    const values = new FormData(form);
    const status = document.getElementById('publishedEditorStatus');
    const file = values.get('pdf');
    const saveFields = values.get('save_fields') === 'on';
    if (!saveFields && !file?.size) {
        status.textContent = 'اختر تعديل البيانات أو ملف PDF قبل الحفظ.';
        return;
    }
    const payload = { ...publishedEditorTarget, pdf_mode: values.get('pdf_mode') };
    delete payload.local_course_index;
    if (saveFields) {
        payload.fields = Object.fromEntries(['code', 'name', 'name_en', 'type', 'category'].map(key => [key, values.get(key)]));
        Object.assign(payload.fields, { hours: Number(values.get('hours')), level: Number(values.get('level')), optional_pool: values.get('optional_pool') === 'on' });
    }
    const body = new FormData();
    body.set('payload', JSON.stringify(payload));
    if (file?.size) body.set('pdf', file);
    publishedEditorBusy = true;
    const submit = document.getElementById('publishedEditorSubmit');
    submit.disabled = true;
    status.textContent = 'جارٍ التحقق والحفظ…';
    try {
        const response = await fetch('/.netlify/functions/course-editor', { method: 'POST', credentials: 'same-origin', body });
        const result = await response.json();
        if (response.status === 401) editAccessGranted = false;
        if (!response.ok) throw new Error(result.error || 'تعذر الحفظ.');
        if (result.unchanged) {
            status.textContent = 'البيانات مطابقة للنسخة المنشورة؛ لا توجد تغييرات جديدة.';
            submit.disabled = false;
            return;
        }
        siteEditsRegistry.entries = [...siteEditsRegistry.entries.filter(item => item.id !== result.entry.id), result.entry];
        const effective = CourseSiteEdits.apply(deepClone(baseProgramsData), siteEditsRegistry);
        originalProgramsData = deepClone(effective);
        const targetProgram = programsData.programs.find(item => item.id === result.entry.program_id);
        const publishedCourse = effective.programs.find(item => item.id === result.entry.program_id).courses[result.entry.course_index];
        Object.assign(targetProgram.courses[publishedEditorTarget.local_course_index], deepClone(publishedCourse));
        programsData.course_details = effective.course_details;
        applyProgramMutation();
        publishedEditorTarget.expected_revision = result.entry.revision;
        status.textContent = 'حُفظ التعديل. جارٍ نشره للجميع…';
        // Preserve the receipt until publication is confirmed; do not submit it twice.
        submit.textContent = 'تم الحفظ';
        void waitForCoursePublication(result.entry.revision, status);
    } catch (error) {
        status.textContent = error.message || 'تعذر الاتصال. تحقق من الشبكة ثم حاول مجددًا.';
        submit.disabled = false;
    } finally {
        publishedEditorBusy = false;
    }
}

async function waitForCoursePublication(revision, status) {
    for (let attempt = 0; attempt < 18; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 5000));
        try {
            const response = await fetch(`site-edits.json?publication=${encodeURIComponent(revision)}`, { cache: 'no-store' });
            const registry = await response.json();
            if (registry.entries.some(entry => entry.revision === revision)) {
                status.textContent = 'تم النشر بنجاح. التعديل متاح الآن لجميع الزوار.';
                return;
            }
        } catch { /* A transient request failure does not undo a saved commit. */ }
    }
    status.textContent = 'حُفظ التعديل في المستودع، ولم يتأكد النشر بعد. يمكنك إغلاق النافذة وتحديث الصفحة لاحقًا.';
}
