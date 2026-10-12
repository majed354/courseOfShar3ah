import test from 'node:test';
import assert from 'node:assert/strict';
import { PDFDocument } from 'pdf-lib';
import { createHandler, issueSession, validSession, validatePdf, validateFields, publishEdit, MAX_PDF_BYTES } from '../lib/course-editor.mjs';
import siteEdits from '../assets/js/site-edits.js';

const origin = 'https://courseofshar3ah.netlify.app';
const course = { code: '2001111-2', name: 'مقرر تجريبي', hours: 2, level: 1, type: 'نظري', category: 'إجبارية القسم', name_en: '' };
const program = { id: 1, name: 'الشريعة', degree: 'بكالوريوس', plan_type: 'جديدة', version: 47, courses: [course] };
const secondProgram = { ...program, id: 2, name: 'القراءات', courses: [structuredClone(course)] };
const originalPdf = 'assets/course-specifications/original.pdf';
const data = { programs: [program, secondProgram], course_details: { [course.code]: { variants: [{ title: course.name, pdf_url: originalPdf, scopes: [siteEdits.scopeOf(program), siteEdits.scopeOf(secondProgram)] }] } } };
const fields = { ...course, optional_pool: false };
const payload = () => ({ program_id: 1, course_index: 0, source: course, expected_revision: null, fields: { ...fields, name: 'اسم معدل' } });
function mockApi(registry = { schema_version: 1, entries: [] }, options = {}) {
    const calls = [];
    const api = async (path, request = {}) => {
        calls.push({ path, ...request });
        if (path === 'git/ref/heads/main') return { object: { sha: 'head' } };
        if (path === 'git/commits/head') return { tree: { sha: 'base-tree' } };
        if (path.startsWith('contents/data.json')) return JSON.stringify(data);
        if (path.startsWith('contents/site-edits.json')) return JSON.stringify(registry);
        if (path.startsWith('contents/COURSE_SITE_EDITS_AUDIT.md')) return '# Audit\n';
        if (path.startsWith('contents/WORK_STATUS.md')) return `## حالة الكتابة\n\n\`${options.lock ? 'IN_PROGRESS' : 'IDLE'}\`\n`;
        if (path === 'git/blobs') return { sha: 'blob' };
        if (path === 'git/trees') return { sha: 'new-tree' };
        if (path === 'git/commits') return { sha: 'new-commit' };
        if (path === 'git/refs/heads/main') {
            if (options.conflict) throw Object.assign(new Error('conflict'), { status: 409 });
            return {};
        }
        throw new Error(`Unexpected API operation ${path}`);
    };
    return { api, calls };
}
const pdf = { bytes: Buffer.from('%PDF-verified-test'), sha256: 'a'.repeat(64), pages: 1 };

test('session authenticates either digit form, hides password, and sets secure cookie', async () => {
    const handler = createHandler({ env: key => ({ EDIT_ACCESS_PASSWORD: '142906', COURSE_EDITOR_SESSION_SECRET: 'session-secret', COURSE_EDITOR_GITHUB_TOKEN: 'private-token' })[key] });
    for (const password of ['142906', '١٤٢٩٠٦']) {
        const response = await handler(new Request(`${origin}/.netlify/functions/course-editor`, { method: 'POST', headers: { origin, 'content-type': 'application/json' }, body: JSON.stringify({ password }) }), { deploy: { context: 'production' } });
        assert.equal(response.status, 200);
        assert.match(response.headers.get('set-cookie'), /HttpOnly; Secure; SameSite=Strict/);
        assert.doesNotMatch(await response.text(), /142906|private-token|session-secret/);
    }
    const denied = await handler(new Request(`${origin}/.netlify/functions/course-editor`, { method: 'POST', headers: { origin, 'content-type': 'application/json' }, body: '{"password":"140505"}' }), { deploy: { context: 'production' } });
    assert.equal(denied.status, 401);
});

test('session rejects tampering, expiry, and a different secret', () => {
    const token = issueSession('secret', 1000);
    assert.equal(validSession(token, 'secret', 2000), true);
    assert.equal(validSession(`${token}x`, 'secret', 2000), false);
    assert.equal(validSession(token, 'other', 2000), false);
    assert.equal(validSession(token, 'secret', 1000 + 7200001), false);
});

test('endpoint refuses foreign origin, previews, unauthenticated writes, and wrong method', async () => {
    const handler = createHandler({ env: () => 'configured' });
    const post = headers => new Request(origin, { method: 'POST', headers, body: new FormData() });
    assert.equal((await handler(post({ origin: 'https://example.com' }), { deploy: { context: 'production' } })).status, 403);
    assert.equal((await handler(post({ origin }), { deploy: { context: 'deploy-preview' } })).status, 403);
    assert.equal((await handler(post({ origin }), { deploy: { context: 'production' } })).status, 401);
    assert.equal((await handler(new Request(origin))).status, 405);
});

test('PDF validation parses pages and preserves exact uploaded bytes', async () => {
    const document = await PDFDocument.create();
    document.addPage();
    const bytes = await document.save();
    const valid = await validatePdf(new File([bytes], 'اختبار.pdf', { type: 'application/pdf' }));
    assert.equal(valid.pages, 1);
    assert.deepEqual(valid.bytes, Buffer.from(bytes));
    await assert.rejects(validatePdf(new File(['hello'], 'fake.pdf')), /ليس PDF/);
    await assert.rejects(validatePdf(new File(['%PDF-broken'], 'broken.pdf')), /تعذر قراءة/);
    await assert.rejects(validatePdf(new File([], 'empty.pdf')), /حجم PDF/);
    await assert.rejects(validatePdf({ name: 'large.pdf', size: MAX_PDF_BYTES + 1, arrayBuffer() {} }), /4 ميجابايت/);
});

test('fields reject malformed identity, hours, and levels', () => {
    assert.equal(validateFields(fields).code, course.code);
    assert.throws(() => validateFields({ ...fields, code: '../index.html' }));
    assert.throws(() => validateFields({ ...fields, hours: -1 }));
    assert.throws(() => validateFields({ ...fields, level: 13 }));
});

test('metadata-only publication preserves PDF and atomically commits audit and registry', async () => {
    const { api, calls } = mockApi();
    const result = await publishEdit(api, payload(), null);
    assert.equal(result.entry.fields.name, 'اسم معدل');
    assert.equal(result.entry.active_pdf_path, undefined);
    assert.equal(calls.some(call => call.path === 'git/blobs'), false);
    const tree = calls.find(call => call.path === 'git/trees').body;
    assert.deepEqual(tree.tree.map(file => file.path).sort(), ['COURSE_SITE_EDITS_AUDIT.md', 'WORK_STATUS.md', 'site-edits.json']);
    assert.equal(calls.at(-1).body.force, false);
    const effective = siteEdits.apply(structuredClone(data), { entries: [result.entry] });
    assert.equal(effective.programs[0].courses[0].name, 'اسم معدل');
    const variant = effective.course_details[course.code].variants[0];
    assert.equal(variant.pdf_url, originalPdf);
    assert.equal(effective.programs[1].courses[0].name, course.name);
});

test('PDF-only replacement preserves metadata, previous PDF, and program scope', async () => {
    const { api } = mockApi();
    const input = payload(); delete input.fields;
    Object.assign(input, { pdf_mode: 'replace', file_name: 'توصيف.pdf' });
    const { entry } = await publishEdit(api, input, pdf);
    assert.equal(entry.fields.name, course.name);
    assert.equal(entry.files[0].sha256, pdf.sha256);
    const effective = siteEdits.apply(structuredClone(data), { entries: [entry] });
    const details = effective.course_details[course.code].variants[0];
    assert.equal(details.pdf_url, entry.active_pdf_path);
    assert.equal(details.attachments[0].pdf_url, originalPdf);
    assert.deepEqual(details.scopes, [siteEdits.scopeOf(program)]);
    assert.equal(effective.programs[1].courses[0].name, course.name);
});

test('adding a PDF keeps current PDF; a later metadata edit preserves both', async () => {
    const first = mockApi();
    const input = { ...payload(), pdf_mode: 'add', file_name: 'extra.pdf' };
    const { entry } = await publishEdit(first.api, input, pdf);
    assert.equal(entry.active_pdf_path, undefined);
    const second = mockApi({ entries: [entry] });
    const next = await publishEdit(second.api, { ...payload(), fields: { ...payload().fields, hours: 3 }, expected_revision: entry.revision }, null);
    assert.deepEqual(next.entry.files, entry.files);
    const details = siteEdits.apply(structuredClone(data), { entries: [next.entry] }).course_details[course.code].variants[0];
    assert.equal(details.pdf_url, originalPdf);
    assert.equal(details.attachments[0].pdf_url, entry.files[0].path);
});

test('combined edit can change identity and PDF without touching another program', async () => {
    const { api } = mockApi();
    const input = { ...payload(), pdf_mode: 'replace', file_name: 'new.pdf' };
    input.fields.code = '2002222-2';
    const { entry } = await publishEdit(api, input, pdf);
    const effective = siteEdits.apply(structuredClone(data), { entries: [entry] });
    assert.equal(effective.programs[0].courses[0].code, '2002222-2');
    assert.equal(effective.programs[1].courses[0].code, course.code);
    assert.equal(effective.course_details['2002222-2'].variants[0].pdf_url, entry.active_pdf_path);
});

test('stale identity and revision, writer lock, and concurrent commit are rejected', async () => {
    await assert.rejects(publishEdit(mockApi().api, { ...payload(), source: { ...course, name: 'wrong' } }, null), /هوية/);
    await assert.rejects(publishEdit(mockApi({ entries: [{ id: '1:0', revision: 'new', source: course }] }).api, payload(), null), /أحدث/);
    await assert.rejects(publishEdit(mockApi(undefined, { lock: true }).api, payload(), null), /تحديث المشروع/);
    await assert.rejects(publishEdit(mockApi(undefined, { conflict: true }).api, payload(), null), /conflict/);
});

test('overrides stop applying if the original source identity changes', () => {
    const copy = structuredClone(data);
    copy.programs[0].courses[0].hours = 3;
    siteEdits.apply(copy, { entries: [{ program_id: 1, course_index: 0, source: course, fields: { name: 'must not apply' } }] });
    assert.equal(copy.programs[0].courses[0].name, course.name);
});

test('saving unchanged data performs no repository write', async () => {
    const { api, calls } = mockApi();
    const result = await publishEdit(api, { ...payload(), fields }, null);
    assert.equal(result.unchanged, true);
    assert.equal(calls.some(call => call.method === 'POST' || call.method === 'PATCH'), false);
});

test('authenticated multipart request publishes through the complete handler', async () => {
    const { api, calls } = mockApi();
    const handler = createHandler({ env: key => ({ EDIT_ACCESS_PASSWORD: '142906', COURSE_EDITOR_SESSION_SECRET: 'secret', COURSE_EDITOR_GITHUB_TOKEN: 'token' })[key], apiFactory: () => api });
    const document = await PDFDocument.create(); document.addPage();
    const body = new FormData();
    body.set('payload', JSON.stringify({ ...payload(), pdf_mode: 'replace' }));
    body.set('pdf', new File([await document.save()], 'new.pdf', { type: 'application/pdf' }));
    const response = await handler(new Request(origin, { method: 'POST', headers: { origin, cookie: `__Host-course_editor=${issueSession('secret')}` }, body }), { deploy: { context: 'production' } });
    assert.equal(response.status, 202);
    const saved = await response.json();
    assert.equal(saved.entry.files[0].pages, 1);
    assert.equal(calls.at(-1).path, 'git/refs/heads/main');
});
