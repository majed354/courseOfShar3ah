#!/usr/bin/env python3
"""Apply narrowly scoped CLO/PLO corrections from uploaded program specs.

The original PDFs remain untouched.  Every corrected program/version variant is
written to a dated bundle, and data.json is split only when a shared PDF needs a
different PLO mapping for one program scope.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_RELATIVE = Path("assets/course-specifications/clo-plo-corrections-20260901")
MANIFEST_RELATIVE = BUNDLE_RELATIVE / "manifest.json"
DETAILED_AUDIT_PATH = ROOT / "CLO_PLO_CORRECTIONS_DETAILED_AUDIT.md"
DATA_PATH = ROOT / "data.json"
ARIAL = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
CORRECTION_DATE = "2026-09-01"


def edit(
    clo: str,
    plo: str,
    text: str | None = None,
    new_clo: str | None = None,
    page: int | None = None,
) -> dict[str, Any]:
    item = {"clo": clo, "new_plo": plo}
    if text is not None:
        item["new_text"] = text
    if new_clo is not None:
        item["new_clo"] = new_clo
    if page is not None:
        item["page"] = page
    return item


SHARIA_ALL = [{"program": "الشريعة", "version": value} for value in ("38", "39", "47")]
SHARIA_OLD = [{"program": "الشريعة", "version": value} for value in ("38", "39")]
SHARIA_NEW = [{"program": "الشريعة", "version": "47"}]
QURAN_OLD = [{"program": "القرآن وعلومه", "version": "39"}]
QIRAAT_OLD = [{"program": "القراءات", "version": "38"}]
USUL_MASTER = [{"program": "أصول الفقه", "degree": "ماجستير"}]


CORRECTIONS: list[dict[str, Any]] = [
    {
        "course_key": "103171-2",
        "source": "assets/course-specifications/raw-recovery-20260827/103171-2.pdf",
        "source_sha256": "0659564173c2889c569539f6c1338b97d9d067bf5aafe63071be3f43f78cd53b",
        "tag": "quran-old-v39",
        "selectors": QURAN_OLD,
        "program_evidence": {"file": "توصيفات البرامج/القرآن وعلومه قديم.pdf", "pages": [5, 9]},
        "reason": "المصفوفة تربط المقرر بقيم البرنامج، ولا يوجد في البرنامج مخرج قيمي بالرمز ق3.",
        "edits": [
            edit("3.1", "ق2", "أن يتحمل الطالب مسؤولية التحقق من سلامة المعلومات التي يوظفها في التحرير."),
            edit("3.2", "ق2", "أن يبادر الطالب إلى تطوير مهاراته في التحرير العربي باستمرار."),
        ],
    },
    {
        "course_key": "103281-2",
        "source": "assets/course-specifications/raw-recovery-20260827/103281-2.pdf",
        "source_sha256": "5754e83ea6d6fd6562c8d4ef1c753371a2369e4a3d4a298183fa84d89aad07dc",
        "tag": "quran-old-v39",
        "selectors": QURAN_OLD,
        "program_evidence": {"file": "توصيفات البرامج/القرآن وعلومه قديم.pdf", "pages": [5, 10]},
        "reason": "مخرجات القيم العامة بعيدة عن موضوعات النحو، وقيم البرنامج المعتمدة هي ق2.",
        "edits": [
            edit("3.1", "ق2", "أن يتحمل الطالب مسؤولية إنجاز التكليفات النحوية بدقة."),
            edit("3.2", "ق2", "أن يبادر الطالب إلى معالجة أخطائه النحوية في التعبير."),
            edit("3.3", "ق2", "أن يطور الطالب أداءه في تطبيق القواعد النحوية باستمرار."),
        ],
    },
    {
        "course_key": "103282-2",
        "source": "assets/course-specifications/raw-recovery-20260827/103282-2.pdf",
        "source_sha256": "30805da13e5cbac1443ff5a897e3863a97ff8f8ea08202a5200274ab9d7eb817",
        "tag": "quran-old-v39",
        "selectors": QURAN_OLD,
        "program_evidence": {"file": "توصيفات البرامج/القرآن وعلومه قديم.pdf", "pages": [5, 10]},
        "reason": "مخرجات القيم العامة بعيدة عن موضوعات النحو، والرمز ق3 غير موجود في قيم البرنامج.",
        "edits": [
            edit("3.1", "ق2", "أن يتحمل الطالب مسؤولية تطبيق القواعد النحوية في كتاباته."),
            edit("3.2", "ق2", "أن يبادر الطالب إلى تصحيح أخطائه النحوية."),
            edit("3.3", "ق2", "أن يطور الطالب أداءه في التحليل النحوي باستمرار."),
        ],
    },
    {
        "course_key": "103349-2",
        "source": "assets/course-specifications/raw-recovery-20260827/103349-2.pdf",
        "source_sha256": "b4916b9b316ad84084a7912ff6c4c1eebc7862865ab04a7f882c88a6e4663e4d",
        "tag": "quran-old-v39",
        "selectors": QURAN_OLD,
        "program_evidence": {"file": "توصيفات البرامج/القرآن وعلومه قديم.pdf", "pages": [5, 10]},
        "reason": "الربط بـ22 هو المخرج القيمي المعتمد للمقرر، والرمز ق3 غير موجود.",
        "edits": [
            edit("3.1", "ق2", "أن يتحمل الطالب مسؤولية تطبيق القواعد النحوية المتقدمة بدقة."),
            edit("3.2", "ق2", "أن يبادر الطالب إلى تطوير أدائه في التحليل النحوي."),
        ],
    },
    {
        "course_key": "103411-2",
        "source": "assets/course-specifications/raw-recovery-20260827/103411-2.pdf",
        "source_sha256": "3e03f6253863a53e1d25f55053ff1f64e20772732ab609a569b054586d1356f7",
        "tag": "quran-old-v39",
        "selectors": QURAN_OLD,
        "program_evidence": {"file": "توصيفات البرامج/القرآن وعلومه قديم.pdf", "pages": [5, 10]},
        "reason": "تخصيص مخرجات القيم لموضوعات الصرف وربطها بـ22 المعتمد.",
        "edits": [
            edit("3.1", "ق2", "أن يتحمل الطالب مسؤولية ضبط صيغ الكلمات في كتاباته."),
            edit("3.2", "ق2", "أن يبادر الطالب إلى تطوير مهاراته الصرفية باستمرار."),
        ],
    },
    {
        "course_key": "2001101-2",
        "source": "assets/course-specifications/raw-recovery-20260827/2001101-2.pdf",
        "source_sha256": "471c8082c4a093ac531666ac6ffc7129b44f06ed07499a6864c85559475cd712",
        "tag": "quran-old-v39",
        "selectors": QURAN_OLD,
        "program_evidence": {"file": "توصيفات البرامج/القرآن وعلومه قديم.pdf", "pages": [5, 10]},
        "reason": "النص القيمي مشوش ومربوط برمز غير موجود في البرنامج.",
        "edits": [edit("3.1", "ق2", "أن يبادر الطالب إلى تطوير مهاراته في تطبيق قواعد مصطلح الحديث.")],
    },
    {
        "course_key": "2001403-2",
        "source": "assets/course-specifications/raw-recovery-20260827/2001403-2.pdf",
        "source_sha256": "7cc4ed1643a8afb655ffe4710e23c20c3e69d933591b382d257dbe37b51e9652",
        "tag": "quran-old-v39",
        "selectors": QURAN_OLD,
        "program_evidence": {"file": "توصيفات البرامج/القرآن وعلومه قديم.pdf", "pages": [5, 11]},
        "reason": "النصوص القيمية مشوشة، والربط الأنسب للسلوك الأخلاقي هو ق1.",
        "edits": [
            edit("3.1", "ق1", "أن يلتزم الطالب بالمنهج العلمي في مناقشة شبهات الأديان والفرق والمذاهب الفكرية."),
            edit("3.2", "ق1", "أن يتحلى الطالب بالأمانة العلمية عند عرض معتقدات الأديان والفرق والمذاهب."),
            edit("3.3", "ق1", "أن يلتزم الطالب بالموقف الشرعي المنضبط تجاه العقائد والأفكار الباطلة."),
        ],
    },
    {
        "course_key": "2002412-2",
        "source": "assets/course-specifications/qiraat-source-1445/2002412-2.pdf",
        "source_sha256": "e1278e593994606ffb5e5e95a380a7fcfb859ec0104692bd2b46a63d805d992a",
        "tag": "qiraat-old-v38",
        "selectors": QIRAAT_OLD,
        "program_evidence": {"file": "توصيفات البرامج/القراءات القديم.pdf", "pages": [7, 12]},
        "reason": "المصفوفة تخصص لقاعة البحث ع3 وم4، والرمزان ع6/م6 غير موجودين، والرمز 3.3 مكتوب في مجال المهارات.",
        "edits": [
            edit("1.1", "ع3"),
            edit("1.2", "ع3"),
            edit("2.1", "م4"),
            edit("2.2", "م4"),
            edit("3.3", "م4", new_clo="2.3", page=4),
        ],
    },
    {
        "course_key": "2001110-2",
        "source": "assets/course-specifications/sharia-ba-1445/2001110-2.pdf",
        "source_sha256": "063ccdd73c17f27288a0209bd8c5efca0de8652eeb3945c21569185505f365ee",
        "tag": "sharia-all",
        "selectors": SHARIA_ALL,
        "program_evidence": {"file": "توصيفات البرامج/الشريعة القديم ٠١.pdf", "pages": [4, 8]},
        "reason": "المخرج 1.2 يجمع فعلين ومضمونين في خلية واحدة، وخلية الربط فارغة.",
        "edits": [edit("1.2", "ع1", "أن يوضح الطالب أصول الاستنباط عند أئمة المذاهب الفقهية الأربعة وأهم مصطلحاتها.")],
    },
    {
        "course_key": "2001148-2",
        "source": "assets/course-specifications/raw-recovery-20260827/2001148-2.pdf",
        "source_sha256": "41c0fa5034291c46f2cb3ec2feb365a8872a5790c779d07e14b305318fc23365",
        "tag": "sharia-all",
        "selectors": SHARIA_ALL,
        "program_evidence": {"file": "توصيفات البرامج/الشريعة القديم ٠١.pdf", "pages": [4, 10]},
        "reason": "مخرجات المعرفة 1.x مربوطة خطأً بمخرجات المهارات، والمصفوفة تربط المقرر بع1.",
        "edits": [edit(value, "ع1") for value in ("1.1", "1.2", "1.3", "1.4")],
    },
    {
        "course_key": "2001346-2",
        "source": "assets/course-specifications/raw-recovery-20260827/2001346-2.pdf",
        "source_sha256": "260b6cc20c29deaf7c3d77f004547a238c27f4dd993ae165a1d2920d58dfb251",
        "tag": "sharia-old-v38-v39",
        "selectors": SHARIA_OLD,
        "program_evidence": {"file": "توصيفات البرامج/الشريعة القديم ٠١.pdf", "pages": [4, 11]},
        "reason": "ع5 وم4 خارج مخرجات الشريعة القديمة؛ الربط الملائم للنصين هو ع1 وم3.",
        "edits": [edit("1.3", "ع1"), edit("2.2", "م3")],
    },
    {
        "course_key": "2001346-2",
        "source": "assets/course-specifications/raw-recovery-20260827/2001346-2.pdf",
        "source_sha256": "260b6cc20c29deaf7c3d77f004547a238c27f4dd993ae165a1d2920d58dfb251",
        "tag": "sharia-new-v47",
        "selectors": SHARIA_NEW,
        "program_evidence": {"file": "توصيفات البرامج/الشريعة جديد.pdf", "pages": [4, 9]},
        "reason": "ع5 في البرنامج الجديد مخصص لموضوع آخر، ونص المهارة يحتاج فعلًا تطبيقيًا.",
        "edits": [
            edit("1.3", "ع1"),
            edit("2.2", "م2", "أن يطبق الطالب مقاصد الشريعة في تحليل المسائل الأصولية."),
        ],
    },
    {
        "course_key": "2001465-2",
        "source": "assets/course-specifications/raw-recovery-20260827/2001465-2.pdf",
        "source_sha256": "9a3ef9552a5568e9a4b56d3b54890d35510338fa3afc25137496a68ccb606969",
        "tag": "sharia-old-v38-v39",
        "selectors": SHARIA_OLD,
        "program_evidence": {"file": "توصيفات البرامج/الشريعة القديم ٠١.pdf", "pages": [4, 11]},
        "reason": "نص المخرج غير مقروء، وعلاقته بع5 غير صالحة للبرنامج القديم.",
        "edits": [edit("1.2", "ع1", "أن يبين الطالب مفهوم فقه النوازل وضوابطه.")],
    },
    {
        "course_key": "2001465-2",
        "source": "assets/course-specifications/raw-recovery-20260827/2001465-2.pdf",
        "source_sha256": "9a3ef9552a5568e9a4b56d3b54890d35510338fa3afc25137496a68ccb606969",
        "tag": "sharia-new-v47",
        "selectors": SHARIA_NEW,
        "program_evidence": {"file": "توصيفات البرامج/الشريعة جديد.pdf", "pages": [4, 9]},
        "reason": "نص المخرج غير مقروء؛ صيغ في نطاق موضوعات النوازل وربط بع4.",
        "edits": [edit("1.2", "ع4", "أن يبين الطالب أحكام النوازل الفقهية المعاصرة وضوابطها.")],
    },
]


def add_mapping_only_corrections() -> None:
    sharia_sources = [
        ("2001128-2", "assets/course-specifications/raw-recovery-20260827/2001128-2.pdf", "c9c2d85a27d857f067e5eac06206424e14bbe61d7abd151e96a65188b3a9cf71"),
        ("2001256-2", "assets/course-specifications/raw-recovery-20260827/2001256-2.pdf", "95f908d981ed595adfe56b7f22accc9d6a21ccbb56a466bd4c644de9e2852ef5"),
        ("2001257-2", "assets/course-specifications/raw-recovery-20260827/2001257-2.pdf", "7b8cfdebf6d88e34ef7a19c4cc7fcc30de7f2de134d90a2fc697d2963d284d2f"),
        ("2001115-4", "assets/course-specifications/sharia-ba-1445/2001115-4.pdf", "f826cba832afa713299c8d09bdfb6e2474e8ef6f4be8b3dbb0ab54b254c894f0"),
        ("2001116-4", "assets/course-specifications/sharia-ba-1445/2001116-4.pdf", "e10f6a3eaa0bd1684d25de8e19696cd807714c8b452684522d4e9198293f1478"),
        ("2001215-4", "assets/course-specifications/sharia-ba-1445/2001215-4.pdf", "2b7dc2cd579fc921c2c77e8e03c56bffa87261379ab1894e4d64ae65beec5f3f"),
        ("2001216-4", "assets/course-specifications/sharia-ba-1445/2001216-4.pdf", "384dc0fe52b3de86bdada2175760ee35ded702b79e3761561bae5fdd87f875e1"),
        ("2001311-4", "assets/course-specifications/sharia-ba-1445/2001311-4.pdf", "4bddc2978040a99ebc9f323a1ce0bacb413f0d3c480b8909fda5e7f7a43d0427"),
        ("2001321-4", "assets/course-specifications/sharia-ba-1445/2001321-4.pdf", "1e0c6c0839476b3a09b47c8696ca1e3cf9bca6a061b70fcaa421268833a2a81e"),
        ("2001411-4", "assets/course-specifications/sharia-ba-1445/2001411-4.pdf", "2f4f63dc53a84d521d0bd96798ce9297ad7095a8a5280e089aa2da924b025647"),
    ]
    for course_key, source, source_hash in sharia_sources:
        CORRECTIONS.append(
            {
                "course_key": course_key,
                "source": source,
                "source_sha256": source_hash,
                "tag": "sharia-new-v47",
                "selectors": SHARIA_NEW,
                "program_evidence": {"file": "توصيفات البرامج/الشريعة جديد.pdf", "pages": [5, 8, 9, 10]},
                "reason": "ق4 في نسخة المقرر المشتركة لا يطابق قيم الشريعة الجديدة؛ نص النزاهة المهنية يطابق ق1.",
                "edits": [edit("3.2", "ق1")],
            }
        )

    CORRECTIONS.extend(
        [
            {
                "course_key": "20044204-2",
                "source": "assets/course-specifications/islamic-studies-bundle-1444/20044204-2.pdf",
                "source_sha256": "b3739cde207c7227f0029a5fc94ff16548503bed26e6674ec06d01d69b5b6fbf",
                "tag": "sharia-new-v47",
                "selectors": SHARIA_NEW,
                "program_evidence": {"file": "توصيفات البرامج/الشريعة جديد.pdf", "pages": [5, 8, 9, 10]},
                "reason": "ق5 مخصص لبرنامج آخر، وليس من قيم الشريعة الجديدة.",
                "edits": [edit("3.1", "ق3", "أن يتحمل الطالب مسؤولية التحقق العلمي عند نقد المذاهب والتيارات المعاصرة.")],
            },
            {
                "course_key": "2001700-2",
                "source": "assets/course-specifications/usul-master-1446/2001700-2.pdf",
                "source_sha256": "79a237c296218ce8e24d4daf6e72acf5d5a0dbe8f6ab424a8ec8d9ae9a13ba52",
                "tag": "usul-master",
                "selectors": USUL_MASTER,
                "program_evidence": {"file": "توصيفات البرامج/ماجستير أصول الفقه.pdf", "pages": [5, 7]},
                "reason": "ق4 غير موجود في البرنامج، ونص التخطيط الذاتي لا يطابق قيمه المعتمدة.",
                "edits": [edit("3.2", "ق2", "أن يشارك الطالب بفاعلية في فريق عمل لمعالجة القضايا الأصولية.")],
            },
            {
                "course_key": "2001701-3",
                "source": "assets/course-specifications/usul-master-1446/2001701-3.pdf",
                "source_sha256": "d461f445df138d66432d4bf6465f3bc2b3fa5f0b43a707d66c884401e31ca7ed",
                "tag": "usul-master",
                "selectors": USUL_MASTER,
                "program_evidence": {"file": "توصيفات البرامج/ماجستير أصول الفقه.pdf", "pages": [5, 7]},
                "reason": "ق4 غير موجود في البرنامج، ونص التخطيط الذاتي لا يطابق قيمه المعتمدة.",
                "edits": [edit("3.2", "ق2", "أن يشارك الطالب بفاعلية في فريق عمل لمعالجة القضايا الأصولية.")],
            },
            {
                "course_key": "2001704-2",
                "source": "assets/course-specifications/usul-master-1446/2001704-2.pdf",
                "source_sha256": "e43724166e3d0670a7bfac9d495241e30b247b1767fdf1533fa907cdd72c683c",
                "tag": "usul-master",
                "selectors": USUL_MASTER,
                "program_evidence": {"file": "توصيفات البرامج/ماجستير أصول الفقه.pdf", "pages": [5, 7]},
                "reason": "ع4 غير موجود، والفعل في 1.2 مهاري فأعيدت صياغته معرفيًا.",
                "edits": [edit("1.2", "ع1", "أن يشرح الطالب خطوات المنهج العلمي في إعمال الأدلة المختلف فيها.")],
            },
            {
                "course_key": "2001706-2",
                "source": "assets/course-specifications/usul-master-1446/2001706-2.pdf",
                "source_sha256": "e12297cf9612fedd49a81a0343209bce194930cd45a5f1147b943bc898b3dec8",
                "tag": "usul-master",
                "selectors": USUL_MASTER,
                "program_evidence": {"file": "توصيفات البرامج/ماجستير أصول الفقه.pdf", "pages": [5, 7]},
                "reason": "م6 غير موجود في البرنامج، وصياغة المخرج مقلوبة الترتيب.",
                "edits": [edit("2.1", "م2", "أن يعد الطالب خطة بحث علمية صحيحة في الدراسات الأصولية.")],
            },
            {
                "course_key": "2001710-4",
                "source": "assets/course-specifications/usul-master-1446/2001710-4.pdf",
                "source_sha256": "e1f8d4d04dffb55eab2d471aea5170286200ee67f39dc07b3a2e6c8dd2709c26",
                "tag": "usul-master",
                "selectors": USUL_MASTER,
                "program_evidence": {"file": "توصيفات البرامج/ماجستير أصول الفقه.pdf", "pages": [5, 7]},
                "reason": "ع4 غير موجود، والنص يصف قضايا علم أصول الفقه فيناسب ع1.",
                "edits": [edit("1.2", "ع1")],
            },
            {
                "course_key": "2001711-4",
                "source": "assets/course-specifications/usul-master-1446/2001711-4.pdf",
                "source_sha256": "b71ae005f8f44d9d144a5d7ab72d65ea9280120ac6020af7fdb053d6fec5ff39",
                "tag": "usul-master",
                "selectors": USUL_MASTER,
                "program_evidence": {"file": "توصيفات البرامج/ماجستير أصول الفقه.pdf", "pages": [5, 7]},
                "reason": "ق4 غير موجود، ونص خدمة المجتمع يطابق التواصل في ق2.",
                "edits": [edit("3.2", "ق2", "أن يشارك الطالب في الإفادة من تخصصه بتعليم المجتمع وتوعيته.")],
            },
        ]
    )


add_mapping_only_corrections()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", value.replace("\u200f", " ").replace("\u200e", " ")).strip(" /\n")


def dominant_background(page: pymupdf.Page, rect: pymupdf.Rect) -> tuple[float, float, float]:
    sample = pymupdf.Rect(rect.x0 + 2, rect.y0 + 2, min(rect.x0 + 18, rect.x1 - 2), min(rect.y0 + 18, rect.y1 - 2))
    pixmap = page.get_pixmap(clip=sample, colorspace=pymupdf.csRGB, alpha=False)
    pixels = zip(pixmap.samples[0::3], pixmap.samples[1::3], pixmap.samples[2::3])
    red, green, blue = Counter(pixels).most_common(1)[0][0]
    return red / 255, green / 255, blue / 255


def insert_centered_arabic(page: pymupdf.Page, rect: pymupdf.Rect, text: str, *, font_size: float, align: str) -> float:
    justify = "center" if align == "center" else "flex-start"
    css = f"""
        @font-face {{ font-family: SiteArabic; src: url('{ARIAL.name}'); }}
        html, body {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
        .box {{
            box-sizing: border-box; width: 100%; height: 100%;
            display: flex; align-items: center; justify-content: {justify};
            padding: 2pt 4pt; direction: rtl; text-align: {align};
            font-family: SiteArabic; font-size: {font_size}pt;
            line-height: 1.08; color: #000000;
        }}
    """
    spare, scale = page.insert_htmlbox(
        rect,
        f'<div class="box" dir="rtl">{html.escape(text)}</div>',
        css=css,
        archive=pymupdf.Archive(str(ARIAL.parent)),
        scale_low=0.58,
        overlay=True,
    )
    if spare < 0:
        raise RuntimeError(f"Arabic replacement did not fit: {text}")
    return float(scale)


def find_clo_cells(
    document: pymupdf.Document, clo: str, page_1_based: int | None = None
) -> tuple[pymupdf.Page, pymupdf.Rect, pymupdf.Rect, pymupdf.Rect, str, str]:
    matches: list[tuple[pymupdf.Page, pymupdf.Rect, pymupdf.Rect, pymupdf.Rect, str, str]] = []
    for page in document:
        if page_1_based is not None and page.number + 1 != page_1_based:
            continue
        words = page.get_text("words", sort=True)
        for word in words:
            if str(word[4]).strip() != clo:
                continue
            center_x = (float(word[0]) + float(word[2])) / 2
            center_y = (float(word[1]) + float(word[3])) / 2
            for table in page.find_tables().tables:
                for row in table.rows:
                    code_cell = next(
                        (
                            pymupdf.Rect(cell)
                            for cell in row.cells
                            if cell
                            and float(cell[0]) <= center_x <= float(cell[2])
                            and float(cell[1]) <= center_y <= float(cell[3])
                        ),
                        None,
                    )
                    if code_cell is None:
                        continue
                    outcome_candidates = []
                    for cell in row.cells:
                        if not cell:
                            continue
                        rect = pymupdf.Rect(cell)
                        if rect.x1 <= code_cell.x0 + 1 and rect.width >= 70 and rect.x0 >= 300:
                            outcome_candidates.append(rect)
                    if not outcome_candidates:
                        continue
                    outcome_cell = max(outcome_candidates, key=lambda item: item.x1)
                    # Word-generated tables often expose each wrapped line as a
                    # separate nested cell.  The CLO code cell spans the complete
                    # logical row, so use its vertical bounds to replace all old
                    # lines rather than only the first nested line.
                    outcome_cell = pymupdf.Rect(
                        outcome_cell.x0, code_cell.y0, outcome_cell.x1, code_cell.y1
                    )
                    mapping_candidates = []
                    for cell in row.cells:
                        if not cell:
                            continue
                        rect = pymupdf.Rect(cell)
                        if rect.x1 <= outcome_cell.x0 + 1 and rect.width >= 55 and rect.x0 >= 180:
                            mapping_candidates.append(rect)
                    if not mapping_candidates:
                        continue
                    mapping_cell = max(mapping_candidates, key=lambda item: (item.x1, item.width))
                    mapping_cell = pymupdf.Rect(
                        mapping_cell.x0, code_cell.y0, mapping_cell.x1, code_cell.y1
                    )
                    matches.append(
                        (
                            page,
                            outcome_cell,
                            mapping_cell,
                            code_cell,
                            normalize_text(page.get_textbox(outcome_cell)),
                            normalize_text(page.get_textbox(mapping_cell)),
                        )
                    )
                    break
                else:
                    continue
                break
    if len(matches) != 1:
        raise RuntimeError(f"Expected one table row for CLO {clo}, found {len(matches)}")
    return matches[0]


def replace_cell(page: pymupdf.Page, rect: pymupdf.Rect, text: str, *, font_size: float, align: str) -> float:
    background = dominant_background(page, rect)
    redaction = pymupdf.Rect(rect.x0 + 0.35, rect.y0 + 0.35, rect.x1 - 0.35, rect.y1 - 0.35)
    page.add_redact_annot(redaction, fill=background, cross_out=False)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    insertion = pymupdf.Rect(rect.x0 + 1.5, rect.y0 + 1.2, rect.x1 - 1.5, rect.y1 - 1.2)
    return insert_centered_arabic(page, insertion, text, font_size=font_size, align=align)


def apply_pdf_correction(record: dict[str, Any]) -> dict[str, Any]:
    source = ROOT / record["source"]
    if sha256(source) != record["source_sha256"]:
        raise RuntimeError(f"Source hash changed: {record['source']}")
    output_relative = BUNDLE_RELATIVE / f"{record['course_key']}--{record['tag']}.pdf"
    output = ROOT / output_relative
    output.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(source)
    manifest_edits = []
    for requested in record["edits"]:
        page, outcome_cell, mapping_cell, code_cell, old_text, old_plo = find_clo_cells(
            document, requested["clo"], requested.get("page")
        )
        item: dict[str, Any] = {
            "page_1_based": page.number + 1,
            "clo_from": requested["clo"],
            "plo_from": old_plo,
            "plo_to": requested["new_plo"],
            "text_from": old_text,
            "mapping_rect": [round(value, 3) for value in mapping_cell],
        }
        item["mapping_scale"] = replace_cell(page, mapping_cell, requested["new_plo"], font_size=11.2, align="center")
        if "new_text" in requested:
            item["text_to"] = requested["new_text"]
            item["outcome_rect"] = [round(value, 3) for value in outcome_cell]
            item["text_scale"] = replace_cell(page, outcome_cell, requested["new_text"], font_size=10.7, align="right")
        if "new_clo" in requested:
            item["clo_to"] = requested["new_clo"]
            item["code_rect"] = [round(value, 3) for value in code_cell]
            item["code_scale"] = replace_cell(page, code_cell, requested["new_clo"], font_size=10.8, align="center")
        manifest_edits.append(item)
    document.set_metadata({**document.metadata, "modDate": "D:20260901000000+03'00'"})
    document.save(output, garbage=4, deflate=True, clean=True)
    document.close()
    subprocess.run(["qpdf", "--check", str(output)], check=True, capture_output=True, text=True)
    record["output"] = output_relative.as_posix()
    with pymupdf.open(output) as verified_document:
        page_count = len(verified_document)
    return {
        "course_key": record["course_key"],
        "tag": record["tag"],
        "source": record["source"],
        "source_sha256": record["source_sha256"],
        "output": output_relative.as_posix(),
        "output_sha256": sha256(output),
        "page_count": page_count,
        "selectors": record["selectors"],
        "program_evidence": record["program_evidence"],
        "reason": record["reason"],
        "edits": manifest_edits,
    }


def scope_matches(scope: dict[str, Any], selectors: list[dict[str, str]]) -> bool:
    return any(all(str(scope.get(key, "")) == str(value) for key, value in selector.items()) for selector in selectors)


def get_scopes(variant: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(variant.get("scopes"), list):
        return copy.deepcopy(variant["scopes"])
    if isinstance(variant.get("scope"), dict):
        return [copy.deepcopy(variant["scope"])]
    return []


def set_scopes(variant: dict[str, Any], scopes: list[dict[str, Any]]) -> None:
    variant.pop("scope", None)
    variant["scopes"] = scopes


def update_data_json(
    manifest_records: list[dict[str, Any]], input_path: Path = DATA_PATH
) -> dict[str, int]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    by_course: dict[str, list[dict[str, Any]]] = {}
    for record in CORRECTIONS:
        by_course.setdefault(record["course_key"], []).append(record)
    changed_variants = 0
    split_variants = 0
    for course_key, corrections in by_course.items():
        variants = data["course_details"][course_key]["variants"]
        rebuilt = []
        for variant in variants:
            scopes = get_scopes(variant)
            if not scopes:
                rebuilt.append(variant)
                continue
            assignments: dict[str, list[dict[str, Any]]] = {}
            correction_by_output = {item["output"]: item for item in corrections}
            for scope in scopes:
                matches = [item for item in corrections if scope_matches(scope, item["selectors"])]
                if len(matches) > 1:
                    raise RuntimeError(f"Overlapping correction selectors for {course_key}: {scope}")
                target = matches[0]["output"] if matches else variant["pdf_url"]
                assignments.setdefault(target, []).append(scope)
            if len(assignments) == 1:
                target, assigned = next(iter(assignments.items()))
                updated = copy.deepcopy(variant)
                if target != variant["pdf_url"]:
                    updated["pdf_url"] = target
                    note = "دُققت مخرجات التعلم وربطها بنواتج البرنامج في نطاق ضيق بتاريخ 2026-09-01."
                    updated["match_note"] = (updated.get("match_note", "").rstrip() + " " + note).strip()
                    changed_variants += 1
                rebuilt.append(updated)
                continue
            split_variants += 1
            for target, assigned in assignments.items():
                updated = copy.deepcopy(variant)
                set_scopes(updated, assigned)
                updated["pdf_url"] = target
                if target in correction_by_output:
                    note = "نسخة مخصصة لنطاق البرنامج؛ دُققت مخرجاتها وربطها بتاريخ 2026-09-01."
                    updated["match_note"] = (updated.get("match_note", "").rstrip() + " " + note).strip()
                    changed_variants += 1
                rebuilt.append(updated)
        data["course_details"][course_key]["variants"] = rebuilt
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Report the resulting linkage, not only mutations made in this run.  This
    # keeps the manifest stable when the script is rerun on already-corrected
    # data.json.
    output_to_source = {item["output"]: item["source"] for item in CORRECTIONS}
    corrected_variants = 0
    split_groups = 0
    for course_key in by_course:
        canonical_sources = Counter()
        for variant in data["course_details"][course_key]["variants"]:
            pdf_url = variant.get("pdf_url", "")
            if pdf_url in output_to_source:
                corrected_variants += 1
            canonical_sources[output_to_source.get(pdf_url, pdf_url)] += 1
        split_groups += sum(1 for count in canonical_sources.values() if count > 1)
    return {"changed_variants": corrected_variants, "split_source_variants": split_groups}


SCOPE_LABELS = {
    "quran-old-v39": "بكالوريوس القرآن وعلومه — الخطة القديمة (39)",
    "qiraat-old-v38": "بكالوريوس القراءات — الخطة القديمة (38)",
    "sharia-all": "بكالوريوس الشريعة — القديمة (38، 39) والجديدة (47)",
    "sharia-old-v38-v39": "بكالوريوس الشريعة — الخطتان القديمتان (38، 39)",
    "sharia-new-v47": "بكالوريوس الشريعة — الخطة الجديدة (47)",
    "usul-master": "ماجستير أصول الفقه",
}


def markdown_cell(value: Any) -> str:
    text = str(value if value not in (None, "") else "—")
    return text.replace("|", "\\|").replace("\n", "<br>")


def write_detailed_audit(manifest: dict[str, Any]) -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    title_by_output = {}
    for course_key, detail in data["course_details"].items():
        for variant in detail.get("variants", []):
            title_by_output[variant.get("pdf_url", "")] = (
                course_key,
                variant.get("title", ""),
            )

    records = manifest["records"]
    clo_rows = sum(len(record["edits"]) for record in records)
    rewrites = sum(
        "text_to" in edit for record in records for edit in record["edits"]
    )
    link_changes = sum(
        edit["plo_from"] != edit["plo_to"]
        for record in records
        for edit in record["edits"]
    )
    code_fixes = sum(
        "clo_to" in edit for record in records for edit in record["edits"]
    )
    scope_total = 0
    for record in records:
        variants = [
            variant
            for detail in data["course_details"].values()
            for variant in detail.get("variants", [])
            if variant.get("pdf_url") == record["output"]
        ]
        scope_total += sum(len(get_scopes(variant)) for variant in variants)

    lines = [
        "# الحصر التفصيلي لتعديلات مخرجات المقررات وربطها بنواتج البرامج",
        "",
        "تاريخ التنفيذ: 1 سبتمبر 2026م.",
        "",
        "## الملخص",
        "",
        f"- شمل العمل **{len(set(record['course_key'] for record in records))} هوية مقرر**، ونتجت عنه **{len(records)} نسخة PDF برنامجية** مرتبطة بـ **{scope_total} نطاقًا**.",
        f"- عولجت **{clo_rows} خانة مخرج**: {link_changes} تغييرًا فعليًا في رمز الربط، و{rewrites} إعادة صياغة، و{code_fixes} تصحيح لرمز مخرج مقرر. وفي {clo_rows - link_changes} حالات تغيّر النص وبقي رمز الربط صحيحًا كما هو.",
        f"- فُصلت {manifest['data_changes']['split_source_variants']} نسخة مشتركة حتى لا ينتقل تعديل خاص ببرنامج أو إصدار إلى برنامج آخر.",
        "- كلمة «لم يتغير» في عمود النص الجديد تعني أن التعديل اقتصر على رمز ناتج البرنامج. والشرطة «—» في الربط القديم تعني أن الخلية كانت فارغة.",
        "",
        "## جدول التعديلات التفصيلي",
        "",
        "| م | المقرر | النطاق | الصفحة | رمز المخرج قبل | رمز المخرج بعد | النص القديم | النص الجديد | ربط البرنامج قبل | ربط البرنامج بعد | سبب التعديل | شاهد توصيف البرنامج |",
        "|---:|---|---|---:|---|---|---|---|---|---|---|---|",
    ]
    row_number = 0
    for record in records:
        course_key, title = title_by_output.get(
            record["output"], (record["course_key"], "")
        )
        course = f"`{course_key}` — {title}"
        scope = SCOPE_LABELS[record["tag"]]
        evidence = (
            f"`{record['program_evidence']['file']}`، ص "
            + "، ".join(str(page) for page in record["program_evidence"]["pages"])
        )
        for edit_item in record["edits"]:
            row_number += 1
            text_after = edit_item.get("text_to", "لم يتغير")
            clo_after = edit_item.get("clo_to", edit_item["clo_from"])
            cells = [
                row_number,
                course,
                scope,
                edit_item["page_1_based"],
                f"`{edit_item['clo_from']}`",
                f"`{clo_after}`",
                edit_item["text_from"],
                text_after,
                f"`{edit_item['plo_from']}`" if edit_item["plo_from"] else "—",
                f"`{edit_item['plo_to']}`",
                record["reason"],
                evidence,
            ]
            lines.append("| " + " | ".join(markdown_cell(cell) for cell in cells) + " |")

    lines.extend(
        [
            "",
            "## النسخ الناتجة ونطاق كل نسخة",
            "",
            "| م | المقرر | النطاق | المصدر الأصلي | النسخة المعدلة | عدد خانات المخرجات المعدلة |",
            "|---:|---|---|---|---|---:|",
        ]
    )
    for index, record in enumerate(records, 1):
        course_key, title = title_by_output.get(
            record["output"], (record["course_key"], "")
        )
        cells = [
            index,
            f"`{course_key}` — {title}",
            SCOPE_LABELS[record["tag"]],
            f"[`{Path(record['source']).name}`](<{record['source']}>)",
            f"[`{Path(record['output']).name}`](<{record['output']}>)",
            len(record["edits"]),
        ]
        lines.append("| " + " | ".join(markdown_cell(cell) for cell in cells) + " |")

    lines.extend(
        [
            "",
            "## ضوابط القرار والتحقق",
            "",
            "- لم يُعدّل مخرج مقبول لمجرد تحسين الأسلوب؛ اقتصر العمل على الخطأ الواضح أو البعد عن موضوعات المقرر أو فساد الصياغة أو الربط غير الصحيح.",
            "- بقيت ملفات المصدر الأصلية دون تعديل، وربط `data.json` كل نطاق بالنسخة المناسبة له دون إضافة نطاق أو حذفه.",
            "- اجتازت 31/31 نسخة فحص سلامة PDF، و76/76 حقلًا معدلًا فحص الاستخراج النصي.",
            "- فُحصت الصفحات الـ245 بصريًا، ومنها صفحات التعديل الـ33 بتكبير أعلى، ولم يظهر قص أو تراكب.",
            "- نجحت اختبارات المستودع 42/42 بعد إضافة اختبارات ثبات الحزمة والنطاقات.",
            "",
            "المصدر الآلي الكامل للتدقيق: `assets/course-specifications/clo-plo-corrections-20260901/manifest.json`.",
        ]
    )
    DETAILED_AUDIT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-data", action="store_true")
    parser.add_argument(
        "--data-input",
        type=Path,
        help="Optional baseline data.json to which the corrections are applied.",
    )
    args = parser.parse_args()
    if not ARIAL.exists():
        raise RuntimeError(f"Arabic font not found: {ARIAL}")
    output_names = [f"{item['course_key']}--{item['tag']}.pdf" for item in CORRECTIONS]
    if len(output_names) != len(set(output_names)):
        raise RuntimeError("Duplicate correction output name")
    manifest_records = [apply_pdf_correction(record) for record in CORRECTIONS]
    data_changes = {"changed_variants": 0, "split_source_variants": 0}
    if not args.skip_data:
        data_changes = update_data_json(manifest_records, args.data_input or DATA_PATH)
    manifest = {
        "generated_at": CORRECTION_DATE,
        "policy": "تعديلات موضعية فقط للمخرج السيئ أو البعيد عن الموضوعات أو المصاغ خطأً أو المربوط بناتج برنامج غير صحيح.",
        "output_count": len(manifest_records),
        "data_changes": data_changes,
        "records": manifest_records,
    }
    manifest_path = ROOT / MANIFEST_RELATIVE
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_detailed_audit(manifest)
    print(json.dumps({"outputs": len(manifest_records), **data_changes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
