#!/usr/bin/env python3
"""Update the retained programme DOCX, preserving every untouched package part."""
import argparse,copy,json,re,hashlib
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm,Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.text.paragraph import Paragraph

ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'assets/course-specifications/quranic-master-plo-update-20261015'

def put(cell,text,*,center=False,size=None):
    p=cell.paragraphs[0]
    ppr=copy.deepcopy(p._p.pPr) if p._p.pPr is not None else None
    rpr=copy.deepcopy(p.runs[0]._r.rPr) if p.runs and p.runs[0]._r.rPr is not None else None
    for child in list(cell._tc):
        if child.tag != qn('w:tcPr'):cell._tc.remove(child)
    p=cell.add_paragraph()
    if ppr is not None:p._p.insert(0,ppr)
    p.paragraph_format.space_before=Pt(0);p.paragraph_format.space_after=Pt(0)
    p.alignment=WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.RIGHT
    bidi=OxmlElement('w:bidi');p._p.get_or_add_pPr().append(bidi)
    run=p.add_run(str(text))
    if rpr is not None:run._r.insert(0,rpr)
    if size:run.font.size=Pt(size)

def repeat(row):
    pr=row._tr.get_or_add_trPr();e=OxmlElement('w:tblHeader');pr.append(e)

def no_split(row):
    e=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(e)

def small_table(doc,headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers));t.autofit=False
    pr=t._tbl.tblPr;rtl=OxmlElement('w:bidiVisual');pr.append(rtl)
    borders=OxmlElement('w:tblBorders')
    for edge in ['top','left','bottom','right','insideH','insideV']:
        e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
    pr.append(borders)
    for c,w,h in zip(t.rows[0].cells,widths,headers):c.width=Cm(w);put(c,h,center=True,size=10)
    repeat(t.rows[0])
    for cell in t.rows[0].cells:
        sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'E8E4F2');cell._tc.get_or_add_tcPr().append(sh)
    for values in rows:
        row=t.add_row();no_split(row)
        for cell,w,value in zip(row.cells,widths,values):cell.width=Cm(w);put(cell,value,center=True,size=9)
    return t

def main():
    a=argparse.ArgumentParser();a.add_argument('--source-docx',type=Path,required=True);args=a.parse_args()
    if hashlib.sha256(args.source_docx.read_bytes()).hexdigest() != 'a67a8970cd408dd32a5d7c271ceb0684f3d4517609b823d8e6fcae0090194975':
        raise ValueError('The retained 2023 template source has changed.')
    cfg=json.loads((BUNDLE/'alignment-decisions.json').read_text());doc=Document(args.source_docx)
    outcome={r['code']:r['text'] for r in cfg['outcomes']}
    # Explicit indexes avoid identity ambiguity after python-docx wraps tables.
    for row in doc.tables[3].rows:
        code=row.cells[0].text.strip()
        if code in outcome:put(row.cells[-1],outcome[code])
    for row in doc.tables[9].rows:
        code=row.cells[0].text.strip()
        if code in outcome:put(row.cells[1],outcome[code])
    put(doc.tables[0].rows[-1].cells[0],'تاريخ آخر مراجعة: 15 / 10 / 2026م')
    for row,course in zip(doc.tables[5].rows[1:],cfg['courses']):put(row.cells[1],course['code'],center=True)
    matrix=[]
    for course in cfg['courses']:
        codes={p for clo in course['clos'] for p in clo['new_plo_codes']}
        levels={p:3 if course['code'] in cfg['mastery'][p] else 1 if course['level']==1 else 2 for p in outcome if p in codes}
        matrix.append({'course_code':course['code'],'course_name':course['name'],'levels':levels})
    for row,course in zip(doc.tables[7].rows[3:],matrix):
        put(row.cells[0],course['course_name'])
        for index,code in enumerate(outcome,1):put(row.cells[index],course['levels'].get(code,''),center=True)
        no_split(row)
    for row in doc.tables[7].rows[:3]:repeat(row)
    # A past council session does not certify this newly authored revision.
    put(doc.tables[27].rows[1].cells[1],'');put(doc.tables[27].rows[2].cells[1],'')
    while doc.paragraphs and not doc.paragraphs[-1].text.strip():
        p=doc.paragraphs[-1]._p;p.getparent().remove(p)
    # The retained template keeps its TOC inside an SDT (not doc.paragraphs).
    # Replace stale cached fields with a verified page index for this edition.
    for content in doc._element.iter(qn('w:sdtContent')):
        if not any('جدول المحتويات' in (t.text or '') for t in content.iter(qn('w:t'))):continue
        for child in list(content):content.remove(child)
        node=OxmlElement('w:p');content.append(node);p=Paragraph(node,doc._body)
        p.paragraph_format.page_break_before=True;p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
        p.add_run('جدول المحتويات').bold=True
        toc=[('أ. التعريف بالبرنامج ومعلومات عامة عنه',3),('ب. رسالة البرنامج وأهدافه ونواتج التعلم',4),
             ('ج. المنهج الدراسي',5),('د. الرسالة العلمية ومتطلباتها',9),('هـ. القبول والدعم الطلابي',9),
             ('و. هيئة التدريس والموظفون',10),('ز. مصادر التعلم والمرافق والتجهيزات',11),
             ('ح. ضمان جودة البرنامج',11),('ط. اعتماد التوصيف',14),
             ('ملحق (1): ربط نواتج المقررات بنواتج البرنامج',15),('ملحق (2): أدلة التمكين ومؤشرات التقويم',18)]
        for label,page in toc:
            node=OxmlElement('w:p');content.append(node);p=Paragraph(node,doc._body)
            p.alignment=WD_ALIGN_PARAGRAPH.RIGHT;p.paragraph_format.space_after=Pt(9)
            p._p.get_or_add_pPr().append(OxmlElement('w:bidi'))
            p.add_run(f'{label}  ................................  {page}')
        break
    doc.add_page_break();doc.add_heading('ملحق (1): ربط نواتج المقررات بنواتج البرنامج',level=1)
    doc.add_paragraph('يحدد هذا الملحق الربط المحدث في سياق ماجستير الدراسات القرآنية المعاصرة، ويحل محل رموز ربط البرنامج السابقة في توصيفات مقرراته لهذا السياق. تبقى نصوص نواتج المقررات وخطط تقويمها كما وردت في مصادرها. الرمز 1 تأسيس، و2 ممارسة، و3 تمكين؛ ولا يعني الربط وحده توافر نتيجة قياس.')
    records=[]
    for c in cfg['courses']:
        first=True
        for i,clo in enumerate(c['clos']):
            if not clo['text']:continue
            records.append([c['code'] if first else '',c['name'] if first else '',clo['code'] or 'غير مرمز', '، '.join(clo['new_plo_codes']) or 'دون ربط مباشر'])
            first=False
    small_table(doc,['رمز المقرر','المقرر','بند المقرر CLO','نواتج البرنامج PLO'],records,[3.1,5.1,2.8,4.6])
    doc.add_paragraph('البنود غير المرمزة والخلايا الفارغة في المصدر لا تُستكمل بنصوص أو رموز مستنتجة، ولا تدخل القياس المباشر قبل حسم هويتها. تتبع روابط المستوى 3 المصفوفة، وتستخدم نواتج المقرر المرتبطة بالناتج نفسه فقط في حسابه.')
    doc.add_page_break();doc.add_heading('ملحق (2): أدلة التمكين ومؤشرات التقويم',level=1)
    indicators={
      'ع1':'تحليل الأصول والمناهج والاتجاهات التفسيرية والموازنة بينها بأدلة علمية.',
      'ع2':'تفسير قضايا علوم القرآن وتقويم التكامل مع المعارف الشرعية واللغوية في دراسة تطبيقية.',
      'ع3':'تقويم مناهج المصادر وموثوقيتها وتوثيق اختيارها وتوظيفها في البحث.',
      'م1':'تطبيق خطوات التفسير والتحليل والنقد على نصوص قرآنية مختارة.',
      'م2':'إعداد خطة بحث وتنفيذ دراسة أو تحقيق نص مع جمع المادة وتحليلها وتوثيقها والإفادة من الأدوات الرقمية.',
      'ق1':'سلامة التوثيق ونسبة الأقوال والاقتباس والنزاهة واحترام النص القرآني وإنتاج الآخرين.',
      'ق2':'مسؤولية الإنجاز واستقلاليته، والاستجابة للنقد، والمبادرة والتعاون وقيادة المناقشة البحثية.'}
    rows=[]
    for code in outcome:
        courses=[c['name'] for c in cfg['courses'] if c['code'] in cfg['mastery'][code]]
        rows.append([code,'؛ '.join(courses),indicators[code]])
    small_table(doc,['الناتج','مقررات التمكين','مؤشرات الأداء في أدوات التقويم'],rows,[1.4,5.0,9.2])
    doc.add_paragraph('المستهدف المباشر 80%، وغير المباشر 4 من 5، والمركب 80% بأوزان 80% للمباشر و20% لغير المباشر. لا يغير ذلك حد إتقان الطالب في أدوات القياس. تجمع الاستطلاعات للمقررات نفسها، وتؤجل أحكام التحقق عند نقص التغطية.')
    doc.add_paragraph('يقاس ق2 في منهج البحث والتحقيق من تقويم عمل الزملاء ضمن فريق منتج والمناقشات الجماعية؛ وفي المشروع البحثي من مسؤولية إنجاز البحث وعرضه والمشاركة في الحلقات البحثية. تستخدم مؤشرات مستقلة لهذا الناتج؛ لا تُنقل إليه درجة جودة التحرير أو النزاهة وحدها. هذا التحديث لا يعيد تصنيف نتائج سابقة بوصفها قياسًا لهذا الناتج دون مراجعة أدواتها.')
    settings=doc.settings.element
    node=OxmlElement('w:updateFields');node.set(qn('w:val'),'true');settings.append(node)
    output=BUNDLE/'program-specification.docx'
    replacements={'word/document.xml':etree.tostring(doc._element,xml_declaration=True,encoding='UTF-8',standalone=True),'word/settings.xml':etree.tostring(settings,xml_declaration=True,encoding='UTF-8',standalone=True)}
    with ZipFile(args.source_docx) as original,ZipFile(output,'w') as final:
        for info in original.infolist():final.writestr(info,replacements.get(info.filename,original.read(info.filename)))
    with ZipFile(args.source_docx) as original,ZipFile(output) as final:
        changed=[name for name in original.namelist() if original.read(name)!=final.read(name)]
        assert set(changed)<=set(replacements),changed
    (BUNDLE/'authored-matrix.json').write_text(json.dumps(matrix,ensure_ascii=False,indent=2)+'\n')
    print(output);print('Changed package parts',changed,'matrix links',sum(len(r['levels']) for r in matrix))

if __name__=='__main__':main()
