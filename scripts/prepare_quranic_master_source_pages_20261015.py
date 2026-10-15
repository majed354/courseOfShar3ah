"""Reproduce the authorized Master CLO revision from preserved source PDFs and decisions.

Run prepare_quranic_master_source_pages_20261015.py first; then build documents
with the bundled document Python. PDF export uses the bundled renderer.
"""
import json,re,hashlib
from pathlib import Path
import fitz
R=Path(__file__).resolve().parents[1];B=R/'assets/course-specifications/quranic-master-single-domain-20261015';Q=R/'.netlify/qa/master_single_domain_20261015';Q.mkdir(parents=True,exist_ok=True);cfg=json.loads((B/'revision-decisions.json').read_text());result={}
def norm(t):return re.sub(r'[\s:：.،؛()\u0640]+','',t).replace('امل','الم')
for c in cfg['courses']:
 d=fitz.open(R/c['pdf']);starts=[];ends=[];approvals=[];toc=[];covers=[]
 for i,p in enumerate(d):
  t=p.get_text();nt=norm(t)
  if 'جدولالمحتويات' in nt:toc.append(i)
  if i<3 and ('اسمالمقرر' in nt or 'اسماملقرر' in nt):covers.append(i)
  for block in p.get_text('blocks'):
   text=' '.join(block[4].split());n=norm(text)
   if 'نواتجالتعلم' in n and 'استراتيجيات' in n and '...' not in text and 'جدولالمحتويات' not in nt:starts.append((i,block[1]-4))
   if 'موضوعاتالمقرر' in n and '...' not in text and 'جدولالمحتويات' not in nt:ends.append((i,block[1]-4))
   if 'اعتمادالتوصيف' in n and '...' not in text and 'جدولالمحتويات' not in nt:approvals.append((i,block[1]-4))
 # Some headings are stored as individually positioned glyphs; header table is a safe fallback.
 if not starts:
  for i,p in enumerate(d):
   if i<2:continue
   for b in p.get_text('blocks'):
    n=norm(b[4])
    if 'نواتجالتعلم' in n and 'الرمز' in n:starts.append((i,b[1]-35));break
   if starts:break
 assert starts and ends,(c['code'],starts,ends)
 start=min(starts);end=min(x for x in ends if x>start);before=[];after=[];records=[]
 for i,p in enumerate(d):
  if i in toc or i in covers or (i==0):continue
  if start[0]<i<end[0]:continue
  if i==start[0]:p.add_redact_annot(fitz.Rect(30,start[1],p.rect.width-25,p.rect.height-40),fill=(1,1,1))
  if i==end[0]:p.add_redact_annot(fitz.Rect(30,65,p.rect.width-25,end[1]-1),fill=(1,1,1))
  for ai,ay in approvals:
   if ai==i:p.add_redact_annot(fitz.Rect(30,ay,p.rect.width-25,p.rect.height-40),fill=(1,1,1))
  p.add_redact_annot(fitz.Rect(p.rect.width*.40,p.rect.height-40,p.rect.width*.60,p.rect.height),fill=(1,1,1))
  p.apply_redactions(images=2,graphics=2)
  # A source page consisting only of a former approval table is not retained.
  body=p.get_text(clip=fitz.Rect(30,65,p.rect.width-25,p.rect.height-40)).strip()
  if not body:continue
  f=Q/f'{c["code"]}-body-{i+1}.jpg';pix=p.get_pixmap(matrix=fitz.Matrix(1.8,1.8));pix.pil_save(f,format='JPEG',quality=94)
  (before if i<=start[0] else after).append(str(f));records.append({'original_page':i+1,'side':'before' if i<=start[0] else 'after','image':f.name})
 original=fitz.open(R/c['pdf']);h=Q/(c['code']+'-header.png');original[0].get_pixmap(matrix=fitz.Matrix(2,2),clip=fitz.Rect(25,18,original[0].rect.width-20,105)).save(h)
 result[c['code']]={'before':before,'after':after,'header':str(h),'removed_clo_region':{'start_page':start[0]+1,'start_y':round(start[1],2),'end_page':end[0]+1,'end_y':round(end[1],2)},'source_pages':len(original),'retained_pages':records,'original_docx':None}
 print(c['code'],'CLO',start,end,'body',len(before),len(after))
(Q/'course-image-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
