import { createHash, createHmac, timingSafeEqual, randomUUID } from 'node:crypto';
import { PDFDocument } from 'pdf-lib';
import siteEdits from '../assets/js/site-edits.js';

export const MAX_PDF_BYTES = 4 * 1024 * 1024;
const COOKIE = '__Host-course_editor';
const REPO = 'majed354/courseOfShar3ah';
const ORIGIN = 'https://courseofshar3ah.netlify.app';
const json = (body, status = 200, headers = {}) => Response.json(body, {
    status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...headers }
});
const fail = (status, message) => Object.assign(new Error(message), { status });
const hash = value => createHash('sha256').update(value).digest('hex');
const safeEqual = (a, b) => timingSafeEqual(Buffer.from(hash(a)), Buffer.from(hash(b)));
export const normalizePassword = value => String(value ?? '').trim().replace(/[٠-٩۰-۹]/g, digit =>
    String((digit.charCodeAt(0) >= 0x6f0 ? digit.charCodeAt(0) - 0x6f0 : digit.charCodeAt(0) - 0x660)))
    .replace(/\s+/g, '');

export function issueSession(secret, now = Date.now()) {
    const payload = Buffer.from(JSON.stringify({ expires: now + 2 * 60 * 60 * 1000, nonce: randomUUID() })).toString('base64url');
    return `${payload}.${createHmac('sha256', secret).update(payload).digest('base64url')}`;
}
export function validSession(token, secret, now = Date.now()) {
    try {
        const [payload, signature, extra] = String(token || '').split('.');
        if (!payload || !signature || extra) return false;
        const expected = createHmac('sha256', secret).update(payload).digest('base64url');
        return safeEqual(signature, expected) && JSON.parse(Buffer.from(payload, 'base64url')).expires > now;
    } catch { return false; }
}

export function validateFields(fields) {
    if (fields === undefined) return undefined;
    if (!fields || typeof fields !== 'object' || Array.isArray(fields)) throw fail(400, 'بيانات المقرر غير صالحة.');
    const result = {};
    for (const [key, max] of Object.entries({ code: 64, name: 250, name_en: 250, type: 80, category: 120 })) {
        if (typeof fields[key] !== 'string') throw fail(400, 'أكمل حقول بيانات المقرر.');
        result[key] = fields[key].normalize('NFC').trim().replace(/\s+/g, ' ');
        if (result[key].length > max || /[\u0000-\u001f\u007f]/.test(result[key])) throw fail(400, 'أحد الحقول طويل أو غير صالح.');
    }
    if (!/^[A-Za-z0-9-]+$/.test(result.code) || !result.name) throw fail(400, 'أدخل رمزًا واسمًا صحيحين للمقرر.');
    if (!Number.isInteger(fields.hours) || fields.hours < 0 || fields.hours > 30
        || !Number.isInteger(fields.level) || fields.level < 1 || fields.level > 12) throw fail(400, 'تحقق من الساعات والمستوى.');
    result.hours = fields.hours;
    result.level = fields.level;
    result.optional_pool = Boolean(fields.optional_pool);
    return result;
}

export async function validatePdf(file) {
    if (!file || typeof file.arrayBuffer !== 'function' || !/\.pdf$/i.test(file.name)) throw fail(400, 'اختر ملف PDF.');
    if (!file.size || file.size > MAX_PDF_BYTES) throw fail(413, 'الحد الأقصى لحجم PDF هو 4 ميجابايت.');
    const bytes = Buffer.from(await file.arrayBuffer());
    if (bytes.subarray(0, 5).toString() !== '%PDF-') throw fail(400, 'الملف ليس PDF صالحًا.');
    let document;
    try { document = await PDFDocument.load(bytes, { updateMetadata: false }); }
    catch { throw fail(400, 'تعذر قراءة PDF. تأكد أنه سليم وغير محمي بكلمة مرور.'); }
    if (!document.getPageCount()) throw fail(400, 'ملف PDF لا يحتوي صفحات.');
    return { bytes, sha256: hash(bytes), pages: document.getPageCount() };
}

export function githubClient(token, fetcher = fetch) {
    return async (path, { method = 'GET', body, raw = false } = {}) => {
        const response = await fetcher(`https://api.github.com/repos/${REPO}/${path}`, {
            method, signal: AbortSignal.timeout(12000),
            headers: { Authorization: `Bearer ${token}`, Accept: raw ? 'application/vnd.github.raw+json' : 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body)
        });
        if (!response.ok) {
            // Never return provider responses or credentials to a browser.
            console.error('Course editor GitHub operation failed', method, path.split('?')[0], response.status);
            throw fail([409, 422].includes(response.status) ? 409 : 502,
                [409, 422].includes(response.status) ? 'وصل تعديل آخر. أعد فتح المقرر ثم حاول مجددًا.' : 'تعذر حفظ التعديل في المستودع. حاول مجددًا.');
        }
        return raw ? response.text() : response.json();
    };
}

export async function publishEdit(api, payload, pdf, now = new Date().toISOString()) {
    const fields = validateFields(payload.fields);
    if (!fields && !pdf) throw fail(400, 'عدّل البيانات أو اختر ملف PDF أولًا.');
    if (!Number.isInteger(payload.course_index) || payload.course_index < 0) throw fail(400, 'المقرر غير محدد.');
    if (pdf && !['add', 'replace'].includes(payload.pdf_mode)) throw fail(400, 'اختر إضافة الملف أو استبداله.');
    const head = (await api('git/ref/heads/main')).object.sha;
    const [commit, dataText, registryText, auditText, workText] = await Promise.all([
        api(`git/commits/${head}`),
        api(`contents/data.json?ref=${head}`, { raw: true }),
        api(`contents/site-edits.json?ref=${head}`, { raw: true }),
        api(`contents/COURSE_SITE_EDITS_AUDIT.md?ref=${head}`, { raw: true }),
        api(`contents/WORK_STATUS.md?ref=${head}`, { raw: true })
    ]);
    if (/## حالة الكتابة\s+`IN_PROGRESS`/.test(workText)) throw fail(423, 'يجري تحديث المشروع حاليًا. حاول بعد اكتمال التحديث.');
    const data = JSON.parse(dataText);
    const registry = JSON.parse(registryText);
    const program = data.programs.find(program => String(program.id) === String(payload.program_id));
    const source = program?.courses[payload.course_index];
    if (!source || !siteEdits.identityMatches(source, payload.source || {})) throw fail(409, 'تغيرت هوية المقرر الأصلية. حدّث الصفحة قبل الحفظ.');
    const id = `${program.id}:${payload.course_index}`;
    const previous = registry.entries.find(entry => entry.id === id);
    if (previous && !siteEdits.identityMatches(source, previous.source)) throw fail(409, 'تغير المصدر الأساسي لهذا المقرر؛ يلزم مراجعة تعديلاته السابقة قبل نشر تعديل جديد.');
    if ((previous?.revision || null) !== (payload.expected_revision || null)) throw fail(409, 'حُفظ تعديل أحدث لهذا المقرر. حدّث الصفحة قبل الحفظ.');
    const entry = previous ? structuredClone(previous) : {
        id, program_id: program.id, course_index: payload.course_index,
        source: { code: source.code, name: source.name, hours: source.hours }, files: []
    };
    // Preserve PDF selection when only metadata changes, and metadata when only PDF changes.
    if (fields) entry.fields = fields;
    entry.fields ||= Object.fromEntries(['code', 'name', 'name_en', 'hours', 'level', 'type', 'category', 'optional_pool']
        .map(key => [key, source[key] ?? (key === 'optional_pool' ? false : '')]));
    const effective = siteEdits.apply(structuredClone(data), registry);
    const currentCourse = effective.programs.find(p => p.id === program.id).courses[payload.course_index];
    if (!pdf && fields && Object.keys(fields).every(key => String(fields[key] ?? '') === String(currentCourse[key] ?? (key === 'optional_pool' ? false : '')))) {
        return { unchanged: true };
    }
    if (effective.programs.find(p => p.id === program.id).courses.some((course, index) => index !== payload.course_index
        && course.code === entry.fields.code && course.name === entry.fields.name)) throw fail(409, 'يوجد مقرر بالرمز والاسم نفسيهما في هذه الخطة.');
    const changes = [];
    if (pdf) {
        const path = `assets/course-uploads/${pdf.sha256}.pdf`;
        if (!entry.files.some(file => file.path === path)) {
            entry.files.push({ path, sha256: pdf.sha256, source_sha256: pdf.sha256, publication_sha256: pdf.sha256,
                file_name: payload.file_name.replace(/[\u0000-\u001f\u007f]/g, '').slice(0, 180),
                size: pdf.bytes.length, pages: pdf.pages, uploaded_at: now, review_status: 'user_uploaded' });
        }
        if (payload.pdf_mode === 'replace') entry.active_pdf_path = path;
        const blob = await api('git/blobs', { method: 'POST', body: { content: pdf.bytes.toString('base64'), encoding: 'base64' } });
        changes.push({ path, mode: '100644', type: 'blob', sha: blob.sha });
    }
    entry.revision = randomUUID();
    entry.updated_at = now;
    registry.entries = [...registry.entries.filter(item => item.id !== id), entry];
    const log = { timestamp: now, program: siteEdits.scopeOf(program), source: entry.source,
        previous: previous || null, current: entry, operation: pdf ? payload.pdf_mode : 'metadata_only' };
    changes.push({ path: 'site-edits.json', mode: '100644', type: 'blob', content: JSON.stringify(registry, null, 2) + '\n' });
    changes.push({ path: 'COURSE_SITE_EDITS_AUDIT.md', mode: '100644', type: 'blob',
        content: auditText + `\n## ${now}\n\n\`\`\`json\n${JSON.stringify(log, null, 2)}\n\`\`\`\n` });
    changes.push({ path: 'WORK_STATUS.md', mode: '100644', type: 'blob', content: workText.replace('## حالة الكتابة',
        `## حالة الكتابة\n\n\`IDLE\` — حُفظ تعديل صاحب الصلاحية في ${now} للمقرر ${entry.fields.code} ضمن البرنامج ${program.id}، وظهوره ${payload.course_index}. المراجعة \`${entry.revision}\`؛ التفاصيل والبصمات والنسخ السابقة في \`site-edits.json\` و\`COURSE_SITE_EDITS_AUDIT.md\`. جارٍ النشر الآلي؛ لا يغير الحفظ سجل CLO/PLO أو أرقام التغطية المدققة.`) });
    const tree = await api('git/trees', { method: 'POST', body: { base_tree: commit.tree.sha, tree: changes } });
    const created = await api('git/commits', { method: 'POST', body: {
        message: `Publish course edit ${entry.fields.code} (program ${program.id})`, tree: tree.sha, parents: [head]
    } });
    // A concurrent writer causes a conflict; force updates are never allowed.
    await api('git/refs/heads/main', { method: 'PATCH', body: { sha: created.sha, force: false } });
    return { entry, commit: created.sha };
}

export function createHandler({ env = key => globalThis.Netlify?.env.get(key), apiFactory = githubClient } = {}) {
    return async (request, context = {}) => {
        try {
            if (request.method !== 'POST') return json({ error: 'الطريقة غير مدعومة.' }, 405, { Allow: 'POST' });
            if (context.deploy?.context !== 'production') return json({ error: 'التعديل متاح على الموقع المنشور فقط.' }, 403);
            if (request.headers.get('origin') !== ORIGIN) return json({ error: 'مصدر الطلب غير مسموح.' }, 403);
            const password = env('EDIT_ACCESS_PASSWORD');
            const secret = env('COURSE_EDITOR_SESSION_SECRET');
            const token = env('COURSE_EDITOR_GITHUB_TOKEN');
            if (!password || !secret || !token) return json({ error: 'خدمة النشر غير مهيأة بعد.' }, 503);
            if (Number(request.headers.get('content-length')) > MAX_PDF_BYTES + 40000) return json({ error: 'الحد الأقصى لحجم PDF هو 4 ميجابايت.' }, 413);
            if (request.headers.get('content-type')?.startsWith('application/json')) {
                const body = await request.text();
                if (body.length > 1000) throw fail(400, 'طلب غير صالح.');
                const input = JSON.parse(body);
                if (!safeEqual(normalizePassword(input.password), normalizePassword(password))) return json({ error: 'كلمة المرور غير صحيحة.' }, 401);
                return json({ authenticated: true }, 200, {
                    'Set-Cookie': `${COOKIE}=${issueSession(secret)}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=7200`
                });
            }
            const cookie = request.headers.get('cookie')?.split(';').map(value => value.trim()).find(value => value.startsWith(`${COOKIE}=`))?.slice(COOKIE.length + 1);
            if (!validSession(cookie, secret)) return json({ error: 'انتهت الصلاحية. فعّل وضع التعديل بكلمة المرور مجددًا.' }, 401);
            const form = await request.formData();
            const payloadText = form.get('payload');
            if (typeof payloadText !== 'string' || payloadText.length > 20000) throw fail(400, 'بيانات الطلب غير صالحة.');
            const payload = JSON.parse(payloadText);
            const file = form.get('pdf');
            const pdf = file && typeof file !== 'string' && file.name ? await validatePdf(file) : null;
            if (pdf) payload.file_name = file.name;
            const saved = await publishEdit(apiFactory(token), payload, pdf);
            return json({ ...saved, message: saved.unchanged ? 'لا توجد تغييرات جديدة للنشر.' : 'حُفظ التعديل، وجارٍ نشره للجميع.' }, saved.unchanged ? 200 : 202);
        } catch (error) {
            if (error instanceof SyntaxError || error instanceof TypeError) return json({ error: 'بيانات الطلب غير صالحة.' }, 400);
            if (!error.status) console.error('Course editor failed', error.name);
            return json({ error: error.status ? error.message : 'تعذر حفظ التعديل. حاول مجددًا.' }, error.status || 500);
        }
    };
}
