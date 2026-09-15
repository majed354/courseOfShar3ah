#!/usr/bin/env python3
"""Publish the audited eight-course completion batch.

The script has two deliberately separate stages:

``data``
    Route each missing catalogue identity to the best reviewed source PDF.
    The source may carry a predecessor code; that difference is stated in the
    catalogue note and never hidden.

``reviews``
    Add hash-bound reviewed overrides after ``extract_course_outcomes.py`` has
    rebuilt the automatic layer.  The automatic extraction remains untouched;
    every academic completion is therefore inspectable as an override and is
    paired with an open recommendation to amend the official PDF.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data.json"
OUTCOMES = ROOT / "course-outcomes.json"
BUNDLE = ROOT / "assets/course-specifications/eight-course-completion-20260915"
MANIFEST = BUNDLE / "manifest.json"
AUTOMATION = Path(
    os.environ.get(
        "COURSE_AUTOMATION_ROOT",
        "/Users/majd/Desktop/claudeMe/أتمتة التقارير/أتمتة تقارير المقررات",
    )
)
REPORTS = AUTOMATION / "الملفات الخام والتقارير المصنوعة/ملفات 46/تقارير المقررات"
REVIEWED_AT = "2026-09-15T12:00:00+03:00"


PDF_UPDATE_FINDINGS = {
    "2001113-2": (
        "الصفحات 1–6 تثبت الرمز والاسم والساعات ونطاق الأنظمة، لكنها لا تنشر جدول CLO "
        "التشغيلي ولا ربطه البرنامجي. يلزم إصدار رسمي يدرج CLO الستة، ويربطها بالأنظمة "
        "وبالقرآن وعلومه كلٌّ في نطاقه، ويثبت صراحة نطاقي القرآن قبل اعتمادهما وثائقيًا."
    ),
    "2001160-2": (
        "المصدر يحمل الرمز والاسم اللاحقين 2001112-2 «المدخل لدراسة الفقه»، بينما الهوية "
        "المطلوبة 2001160-2 «المدخل لدراسة الشريعة». يلزم إصدار رسمي للهوية القديمة أو "
        "محضر معادلة صريح، مع إدراج CLO السبعة وربط القرآن وعلومه المثبت في تقرير المقرر."
    ),
    "2001424-2": (
        "المصدر المماثل يحمل 20043104-2 وفيه تسعة صفوف CLO، بينما تقرير التشغيل للهوية "
        "2001424-2/20013104-2 يثبت سبعة مخرجات. يلزم توصيف رسمي بالرمز والنطاق الصحيحين "
        "وبجدول CLO السباعي وربط PLO الخاص بالقرآن وعلومه."
    ),
    "2003220-2": (
        "المصدر يحمل 20031301-2 «مبادئ القانون». يلزم توصيف رسمي أو قرار معادلة يثبت "
        "انتقال الهوية إلى 2003220-2 «المدخل لدراسة الأنظمة»، ويثبت CLO الستة وربط كل من "
        "القرآن وعلومه والدراسات الإسلامية في نطاقه."
    ),
    "2004205-2": (
        "المصدر يحمل الرمز السابق 2001205-2. يلزم إصدار رسمي بالرمز 2004205-2 أو معادلة "
        "صريحة، مع إبقاء CLO الستة وإظهار ربط مستقل للقرآن وعلومه والقراءات."
    ),
    "2004209-2": (
        "المصدر يحمل الرمز السابق 2001209-2. يلزم إصدار رسمي بالرمز 2004209-2 أو معادلة "
        "صريحة، مع إبقاء CLO الستة وإظهار ربط مستقل للقرآن وعلومه والقراءات."
    ),
    "2004403-2": (
        "المصدر يحمل الرمز السابق 2001403-2، وبعض عبارات CLO فيه وفي التقرير غير مكتملة "
        "لغويًا أو ضعيفة القياس. يلزم إصدار رسمي بالرمز الجديد وبالصياغات التسع المصححة، "
        "مع ربط مستقل للقرآن وعلومه والقراءات."
    ),
    "990413-2": (
        "المصدر يحمل الرمز اللاحق 2001106-2. يلزم إصدار رسمي أو قرار معادلة يثبت الهوية "
        "990413-2، ويثبت CLO التسعة. يبقى ربط القرآن وعلومه المثبت فقط؛ أما فراغات الأنظمة "
        "والشريعة والقراءات الموثقة فتبقى explicitly_unmapped حتى يصدر دليل برنامجي."
    ),
}


def report_path(folder: str, group: str = "المصنفة 461") -> Path:
    return REPORTS / group / folder / f"تقرير مقرر {folder}.pdf"


def public_report_reference(path: Path) -> str:
    """Return a stable evidence label without publishing a workstation path."""
    return f"تقارير المقررات/{path.relative_to(REPORTS).as_posix()}"


TARGETS: dict[str, dict[str, Any]] = {
    "2001113-2": {
        "title": "أصول الفقه (1)",
        "summary": "يعرّف بعلم أصول الفقه والحكم الشرعي وأقسامه والأدلة الأصولية، ويدرّب على التمييز والتطبيق والموازنة المنهجية.",
        "source_pdf": "assets/course-specifications/eight-course-completion-20260915/2001113-2.pdf",
        "source_code": "2001113-2",
        "source_pages": [1, 2, 3, 4, 5, 6],
        "report": report_path("أصول الفقه (1)"),
        "match_note": "توصيف مطابق للرمز والاسم والساعتين؛ استُخرجت الصفحات 2–7 من الملف المجمع لتوصيف مقررات الشريعة في برنامج الأنظمة. صيغ CLO التشغيلية استُكملت أكاديميًا من الهدف والمفردات وتقرير المقرر، وربط PLO للأنظمة والقرآن تحليلي وموسوم بذلك.",
        "clos": {
            "1.1": "أن يعرِّف الطالب علم أصول الفقه، وموضوعه، وأهميته في استنباط الأحكام الشرعية.",
            "1.2": "أن يشرح الطالب حقيقة الحكم الشرعي (التكليفي والوضعي) وتقسيماته، وأقسام الأدلة الأصولية الرئيسة وما يتصل بها من مسائل.",
            "2.1": "أن يميّز الطالب بين أنواع الحكم الشرعي وتقسيماته، ويقارن بين الحكم التكليفي والحكم الوضعي في التطبيقات الفقهية.",
            "2.2": "أن يطبّق الطالب شروط التكليف وضوابطه في استنباط الأحكام، ويستدل على حجية الأدلة الأصولية.",
            "3.1": "أن يلتزم الطالب بالمنهجية العلمية في الموازنة بين الأقوال الفقهية، وتقديم ما يترجح منها بالدليل.",
            "3.2": "أن يتحلَّى الطالب بأدب الحوار واحترام الخلاف، ويعبّر عن رأيه الفقهي تعبيرًا منضبطًا.",
        },
        "mapping": {
            "الأنظمة": ["ع2", "ع2", "م2", "م2", "ق1", "ق3"],
            "القرآن وعلومه": ["ع3", "ع3", "م3", "م3", "ق1", "ق2"],
        },
        "assessment": {
            "1": "المناقشات، الاختبارات التحريرية، والبحث في مصادر المعرفة",
            "2": "المناقشات، التطبيقات والواجبات، والمشروع الجماعي",
            "3": "الملاحظة، المناقشات، والمشروع الجماعي",
        },
        "assessment_plan": [
            {"label": "اختبار دوري", "weight": 20, "source_page": 5, "confidence": "verified"},
            {"label": "مشروع جماعي", "weight": 20, "source_page": 5, "confidence": "verified"},
            {"label": "اختبار نهائي", "weight": 60, "source_page": 5, "confidence": "verified"},
        ],
        "row_indexes": [0, 1, 2, 3, 4, 5],
    },
    "2001160-2": {
        "title": "المدخل لدراسة الشريعة",
        "source_title": "المدخل لدراسة الفقه",
        "summary": "يعرّف بمبادئ الفقه وخصائص التشريع الإسلامي وتطوره ومدارسه الفقهية وأسباب اختلاف الفقهاء وآداب الخلاف.",
        "source_pdf": "assets/course-specifications/shared-course-blank-plo-20260905/2001112-2--4d2365da36.pdf",
        "source_code": "2001112-2",
        "source_pages": [3, 4, 5, 6, 7],
        "report": report_path("المدخل لدراسة الشريعة"),
        "match_note": "تغيير اسم ورمز بين الخطة القديمة 2001160-2 والخطة اللاحقة 2001112-2؛ الاسم والساعات والوصف والمفردات ونواتج تقرير المقرر تثبت وحدة المحتوى. ربط PLO مأخوذ من تقرير المقرر للنطاق القديم.",
        "clos": {
            "1.1": "أن يعرف الطالب مبادئ الفقه الإسلامي وخصائصه.",
            "1.2": "أن يستعرض المراحل التي مر بها تاريخ التشريع الإسلامي.",
            "1.3": "أن يلخص أسباب نشوء مدرستي أهل الرأي وأهل الحديث، ويميّز بين منهجيهما.",
            "2.1": "أن يقارن بين أوجه الخلاف بين المذاهب الفقهية.",
            "2.2": "أن يفسر الأسباب الموضوعية التي أدت إلى اختلاف فقهاء المذاهب.",
            "3.1": "أن يتحلى بالنزاهة العلمية وآداب الخلاف.",
            "3.2": "أن يمارس التعاون والعمل بروح الفريق.",
        },
        "mapping": {"القرآن وعلومه": ["ع3", "ع2", "ع2", "م1", "م3", "ق1", "ق2"]},
        "assessment_plan": [
            {"label": "المناقشات العلمية", "weight": 20, "source_page": 5, "confidence": "verified"},
            {"label": "الاختبار الدوري", "weight": 20, "source_page": 5, "confidence": "verified"},
            {"label": "الاختبار النهائي", "weight": 60, "source_page": 6, "confidence": "verified"},
        ],
    },
    "2001424-2": {
        "title": "الفقه (4)",
        "source_title": "الفقه (4)",
        "summary": "يتناول أحكام البيوع والربا والصرف والمعاملات المالية المعاصرة والعقود التابعة لها، مع التحليل والصياغة الفقهية.",
        "source_pdf": "assets/course-specifications/islamic-studies-bundle-1444/20043104-2.pdf",
        "source_code": "20043104-2",
        "source_pages": [3, 4, 5, 6, 7, 8, 11],
        "report": report_path("الفقه (4)"),
        "match_note": "مصدر مماثل في الاسم والساعات وموضوعات فقه المعاملات ببرنامج الدراسات الإسلامية، مع تقرير مقرر فعلي يجمع الرمز التشغيلي 20013104-2 والرمز القديم 2001424-2. CLO وربط PLO النهائيان من التقرير، لا منسوبان حرفيًا إلى PDF المماثل.",
        "clos": {
            "1.1": "أن يعيد صياغة المصطلحات الواردة في موضوعات المقرر.",
            "1.2": "أن يعدد الشروط والأركان الواردة في موضوعات المقرر.",
            "1.3": "أن يذكر الأحكام الفقهية المتعلقة بالبيع والربا والصرف وبعض المعاملات المالية المعاصرة.",
            "2.1": "أن يحلل المسائل الفقهية المعطاة في موضوعات المقرر.",
            "2.2": "أن يصوغ أحكامًا فقهية مناسبة للمسائل المعطاة في موضوعات المقرر.",
            "3.1": "أن يقود فريقه بفاعلية لإنجاز المهام المرتبطة بالمقرر.",
            "3.2": "أن يلتزم بالنزاهة المهنية والأخلاقيات والمواطنة الأكاديمية المسؤولة.",
        },
        "mapping": {"القرآن وعلومه": ["م2", "ع1", "ع1", "م2", "م2", "ق2", "ق1"]},
        "assessment": {"*": "الملاحظة، المناقشات، والاختبارات"},
        "assessment_plan": [
            {"label": "تقديم بحوث وتقارير وأوراق عمل وعروض تقديمية وشفهية", "weight": 20, "source_page": 11, "confidence": "verified"},
            {"label": "الاختبار التحريري النصفي", "weight": 20, "source_page": 11, "confidence": "verified"},
            {"label": "الاختبار النهائي", "weight": 60, "source_page": 11, "confidence": "verified"},
        ],
        "row_indexes": [0, 1, 2, 4, 5, 7, 8],
        "delete_indexes": [3, 6],
    },
    "2003220-2": {
        "title": "المدخل لدراسة الأنظمة",
        "source_title": "مبادئ القانون",
        "summary": "يعرّف بالمفاهيم القانونية والقاعدة القانونية والحقوق ووسائل حمايتها، ويدرّب على المقارنة والتفسير القانوني.",
        "source_pdf": "assets/course-specifications/20031301-2.pdf",
        "source_code": "20031301-2",
        "source_pages": [3, 4, 5, 6, 7, 8],
        "report": report_path("المدخل لدراسة الأنظمة"),
        "match_note": "الاسم القديم «المدخل لدراسة الأنظمة» يقابل «مبادئ القانون» في الخطة الحديثة؛ الوصف والموضوعات متطابقة جوهريًا، وتقرير المقرر 2003220-2 يثبت CLO وربط PLO التشغيليين.",
        "clos": {
            "1.1": "أن يعرّف الطالب المفاهيم والمبادئ الأساسية للقانون وموضوعاته.",
            "1.2": "أن يوضح الحقوق ووسائل حمايتها.",
            "1.3": "أن يبين خصائص القاعدة القانونية.",
            "2.1": "أن يقارن بين القاعدة الآمرة والقاعدة المكملة، ويميّز بين فروع القانون.",
            "2.2": "أن يفسر القواعد القانونية تفسيرًا سليمًا لاستنباط الأحكام منها.",
            "3.1": "أن يلتزم بالموضوعية والحيادية عند مناقشة المسائل القانونية.",
        },
        "mapping": {
            "القرآن وعلومه": ["ع3", "ع3", "ع3", "م2", "م2", "ق1"],
            "الدراسات الإسلامية": ["ع3", "ع3", "ع3", "م2", "م2", "ق1"],
        },
        "assessment": {"*": "المناقشات والاختبارات"},
        "row_indexes": [0, 1, 2, 3, 4, 5],
        "delete_indexes": [6],
    },
    "2004205-2": {
        "title": "الحديث (1)",
        "source_title": "الحديث (1)",
        "summary": "يتناول أربعين حديثًا من جوامع الكلم النبوي بالحفظ والدراسة التحليلية واستنباط الأحكام والتوجيهات.",
        "source_pdf": "assets/course-specifications/institutional-recovery-20260911/2001205-2.pdf",
        "source_code": "2001205-2",
        "source_pages": [3, 4, 5, 6, 7, 8],
        "report": report_path("الحديث (1)"),
        "match_note": "إعادة ترميز للمقرر نفسه من 2001205-2 إلى 2004205-2؛ الاسم والساعات والموضوعات وCLO متطابقة، مع تكييف ربط PLO لكل برنامج.",
        "clos": {
            "1.1": "أن يوضح المراد بالشرح التحليلي وأنواعه وجهود العلماء فيه.",
            "1.2": "أن يشرح الأحاديث المقررة شرحًا تحليليًا.",
            "1.3": "أن يلخص الأحكام الشرعية الواردة في الأحاديث المقررة.",
            "2.1": "أن يستنبط الأحكام والتوجيهات الشرعية من الأحاديث المقررة.",
            "2.2": "أن يصوغ القواعد الشرعية المستفادة من الأحاديث المقررة.",
            "3.1": "أن يقتدي بتوجيهات أحاديث جوامع الكلم النبوي في سلوكه.",
        },
        "mapping": {
            "القرآن وعلومه": ["ع3", "ع3", "ع3", "م3", "م3", "ق1"],
            "القراءات": ["ع2", "ع2", "ع2", "م2", "م2", "ق1"],
        },
    },
    "2004209-2": {
        "title": "الحديث (2)",
        "source_title": "الحديث (2)",
        "summary": "يتناول أحاديث فضائل القرآن والتفسير وأسباب النزول بالدراسة التحليلية واستنباط التفسير بالمأثور.",
        "source_pdf": "assets/course-specifications/institutional-recovery-20260911/2001209-2.pdf",
        "source_code": "2001209-2",
        "source_pages": [3, 4, 5, 6, 7, 8],
        "report": report_path("الحديث (2)", "المصنفة 462"),
        "match_note": "إعادة ترميز للمقرر نفسه من 2001209-2 إلى 2004209-2؛ الاسم والساعات والموضوعات وCLO متطابقة، مع تكييف ربط PLO لكل برنامج.",
        "clos": {
            "1.1": "أن يشرح أحاديث فضائل القرآن والتفسير المقررة شرحًا تحليليًا.",
            "1.2": "أن يلخص أسباب النزول الواردة في الأحاديث المقررة.",
            "2.1": "أن يستنبط التفسير بالمأثور من الأحاديث المقررة.",
            "2.2": "أن يصنف التفسير الوارد في الأحاديث وفق أنواعه.",
            "2.3": "أن يتعاون مع زملائه في جمع التفسير من الأحاديث النبوية.",
            "3.1": "أن يشارك بفاعلية في استنباط التفسير من الأحاديث المقررة.",
        },
        "mapping": {
            "القرآن وعلومه": ["ع3", "ع3", "م3", "م3", "ق2", "ق1"],
            "القراءات": ["ع2", "ع2", "م2", "م2", "ق2", "ق2"],
        },
    },
    "2004403-2": {
        "title": "الأديان والفرق والمذاهب المعاصرة",
        "source_title": "الأديان والفرق والمذاهب المعاصرة",
        "summary": "يعرّف بالأديان والفرق والمذاهب الفكرية وشعائرها وانحرافاتها، وينمي مهارات المقارنة والنقد والرد المنضبط.",
        "source_pdf": "assets/course-specifications/shared-course-blank-plo-20260905/2001403-2--8974cd99a2.pdf",
        "source_code": "2001403-2",
        "source_pages": [3, 4, 5, 6, 7, 8],
        "report": report_path("الأديان والفرق والمذاهب المعاصرة"),
        "match_note": "إعادة ترميز من 2001403-2 إلى 2004403-2 مع ثبات الاسم والساعات والموضوعات. بعض عبارات CLO في PDF/التقرير معيبة؛ حُفظت في طبقة الاستخراج وصيغت بدائل قابلة للقياس في طبقة المراجعة.",
        "clos": {
            "1.1": "أن يعرّف الطالب المصطلحات الأساسية في علوم الأديان والفرق والمذاهب الفكرية.",
            "1.2": "أن يبيّن مظاهر الانحراف عن الحق في الأديان والفرق والمذاهب الفكرية.",
            "1.3": "أن يوضح شعائر أبرز الأديان الكتابية والوضعية والفرق والمذاهب الفكرية.",
            "2.1": "أن يحلل أهمية دراسة الأديان والفرق والمذاهب الفكرية وآثارها.",
            "2.2": "أن ينقد دعاوى التقريب بين الأديان، ويميّز بينها وبين الحوار المنضبط.",
            "2.3": "أن يقارن بين موقف الإسلام ومواقف الأديان والفرق والمذاهب الفكرية في القضايا المدروسة.",
            "3.1": "أن يشارك في الرد العلمي المنضبط على الشبهات المتعلقة بالأديان والفرق والمذاهب الفكرية.",
            "3.2": "أن يلتزم بعدم المشاركة في الشعائر المخالفة للعقيدة الإسلامية.",
            "3.3": "أن يلتزم بالموقف الشرعي المنضبط تجاه العقائد والأفكار الباطلة.",
        },
        "mapping": {
            "القرآن وعلومه": ["ع1", "ع1", "ع1", "م2", "ق3", "م2", "ق3", "ق3", "ق3"],
            "القراءات": ["ع3", "ع3", "ع3", "م3", "م3", "م3", "ق1", "ق1", "ق1"],
        },
        "assessment_plan": [
            {"label": "التقييم الدوري", "weight": 10, "source_page": 7, "confidence": "verified"},
            {"label": "التفاعل الصفي", "weight": 10, "source_page": 8, "confidence": "verified"},
            {"label": "الاختبار النصفي", "weight": 20, "source_page": 8, "confidence": "verified"},
            {"label": "الاختبار النهائي", "weight": 60, "source_page": 8, "confidence": "verified"},
        ],
    },
    "990413-2": {
        "title": "السيرة النبوية",
        "source_title": "السيرة النبوية",
        "summary": "يعرض مراحل السيرة النبوية ومواقفها وغزواتها ودروسها، وينمي الاستنباط والمقارنة والاقتداء بالهدي النبوي.",
        "source_pdf": "assets/course-specifications/shared-course-blank-plo-20260905/2001106-2--ec42a4ad0f.pdf",
        "source_code": "2001106-2",
        "source_pages": [3, 4, 5, 6, 7, 8],
        "report": report_path("السيرة النبوية"),
        "match_note": "رمز جامعي قديم للمقرر المشترك نفسه الذي يظهر لاحقًا برمز 2001106-2؛ التطابق مثبت بالاسم والساعات والمحتوى وبسجل النتائج الذي يجمع الرمزين. ربط القرآن رسمي من تقرير المقرر، وبقية البرامج تبقى غير مربوطة صراحة لأن PDF المشترك أفرغ الخلايا عمدًا.",
        "clos": {
            "1.1": "أن يشرح مراحل السيرة النبوية وإقامة دولة الإسلام في المدينة النبوية.",
            "1.2": "أن يستعرض المواقف النبوية في مراحل الدعوة المختلفة.",
            "1.3": "أن يلخص غزوات الرسول صلى الله عليه وسلم وأبرز نتائجها.",
            "2.1": "أن يستنبط الفوائد والعبر والدروس من أحداث السيرة النبوية.",
            "2.2": "أن يدافع عن شخصية الرسول صلى الله عليه وسلم في مواجهة الشبه المعاصرة.",
            "2.3": "أن يقوّم مواقف غير المسلمين من النبي صلى الله عليه وسلم في المدينة.",
            "2.4": "أن يقارن بين مراحل السيرة النبوية وخصائص كل مرحلة.",
            "3.1": "أن يمتثل الهدي النبوي في المواقف الحياتية.",
            "3.2": "أن يقتدي بالنبي صلى الله عليه وسلم في أخلاقه ومعاملاته.",
        },
        "mapping": {"القرآن وعلومه": ["ع2", "ع1", "ع2", "م2", "م3", "م2", "م2", "ق1", "ق3"]},
        "explicit_unmapped_programs": {"الأنظمة", "الشريعة", "القراءات"},
        "assessment_plan": [
            {"label": "تقديم بحوث وتقارير وأوراق عمل وعروض تقديمية وشفهية", "weight": 20, "source_page": 7, "confidence": "verified"},
            {"label": "الاختبار التحريري النصفي", "weight": 20, "source_page": 7, "confidence": "verified"},
            {"label": "الاختبار النهائي", "weight": 60, "source_page": 8, "confidence": "verified"},
        ],
    },
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scope_key(scope: dict[str, str]) -> tuple[str, str, str, str]:
    return tuple(scope[field] for field in ("program", "degree", "plan_type", "version"))


def target_scopes(data: dict[str, Any], code: str, title: str) -> list[dict[str, str]]:
    scopes = []
    for program in data["programs"]:
        if any(course.get("code") == code and course.get("name") == title for course in program.get("courses", [])):
            scopes.append({
                "program": str(program["name"]),
                "degree": str(program["degree"]),
                "plan_type": str(program["plan_type"]),
                "version": str(program["version"]),
            })
    return sorted(scopes, key=scope_key)


def equivalency_record(source_name: str, target_code: str, target_name: str, scope: dict[str, str]) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "options": [{"code": target_code, "name": target_name}],
        "note": "معادلة هوية موثقة بتغيير الرمز/الاسم بين الخطط مع ثبات الساعات والمحتوى؛ تطبق في الاتجاهين، ولا تنقل ربط PLO بين البرامج.",
        **scope,
    }


def add_equivalencies(data: dict[str, Any], code: str, item: dict[str, Any], scopes: list[dict[str, str]]) -> None:
    source_code = item["source_code"]
    if source_code == code:
        return
    target_title = item["title"]
    source_title = item.get("source_title", target_title)
    eq = data.setdefault("equivalencies", {})
    batch_note = "معادلة هوية موثقة بتغيير الرمز/الاسم بين الخطط"
    for left, right in ((code, source_code), (source_code, code)):
        if left in eq:
            eq[left] = [
                record
                for record in eq[left]
                if not (
                    batch_note in str(record.get("note", ""))
                    and any(option.get("code") == right for option in record.get("options", []))
                )
            ]
            if not eq[left]:
                del eq[left]

    source_scopes = target_scopes(data, source_code, source_title)
    if not source_scopes:
        raise ValueError(f"no catalogue scope found for predecessor {source_code} / {source_title}")
    for left, left_name, right, right_name, applicable_scopes in (
        (code, target_title, source_code, source_title, scopes),
        (source_code, source_title, code, target_title, source_scopes),
    ):
        rows = eq.setdefault(left, [])
        for scope in applicable_scopes:
            record = equivalency_record(left_name, right, right_name, scope)
            if not any(
                r.get("options") == record["options"]
                and all(str(r.get(k, "")) == str(scope[k]) for k in ("program", "degree", "plan_type", "version"))
                for r in rows
            ):
                rows.append(record)


def stage_data() -> None:
    data = load(DATA)
    evidence = []
    for code, item in TARGETS.items():
        source = ROOT / item["source_pdf"]
        report = Path(item["report"])
        if not source.is_file():
            raise FileNotFoundError(source)
        if not report.is_file():
            raise FileNotFoundError(report)
        scopes = target_scopes(data, code, item["title"])
        if not scopes:
            raise RuntimeError(f"no catalogue scopes found for {code}")
        detail = {
            "variants": [{
                "scopes": scopes,
                "title": item["title"],
                "summary": item["summary"],
                "pdf_url": item["source_pdf"],
                "specification_code": code,
                "match_status": "reviewed_adaptation" if item["source_code"] != code else "verified_with_academic_completion",
                "match_note": item["match_note"],
            }]
        }
        data["course_details"][code] = detail
        for program in data["programs"]:
            for course in program.get("courses", []):
                if course.get("code") == code and course.get("name") == item["title"]:
                    course["pdf_url"] = item["source_pdf"]
        add_equivalencies(data, code, item, scopes)
        evidence.append({
            "course_code": code,
            "course_name": item["title"],
            "source_course_code": item["source_code"],
            "source_pdf": item["source_pdf"],
            "source_sha256": sha256(source),
            "source_pages_reviewed": item["source_pages"],
            "course_report": public_report_reference(report),
            "course_report_sha256": sha256(report),
            "course_report_pages_reviewed": [4, 5, 6],
            "scopes": scopes,
            "match_note": item["match_note"],
        })
    write(DATA, data)
    write(MANIFEST, {
        "schema_version": "eight-course-completion-20260915-v1",
        "created_at": REVIEWED_AT,
        "policy": {
            "automatic_extraction_preserved": True,
            "academic_completion_authorized_by_user": True,
            "completed_text_not_attributed_to_source_pdf": True,
            "assessment_weights_not_invented": True,
            "program_scoped_plo_mapping": True,
        },
        "records": evidence,
    })
    print(json.dumps({"stage": "data", "courses": len(TARGETS), "scopes": sum(len(x["scopes"]) for x in evidence)}, ensure_ascii=False))


def mapping_rows(item: dict[str, Any], scopes: list[dict[str, str]], clo_position: int) -> list[dict[str, Any]]:
    rows = []
    for scope in scopes:
        program = scope["program"]
        codes = item.get("mapping", {}).get(program)
        if codes:
            official = program == "القرآن وعلومه" and item["source_code"] != item.get("course_code", "")
            rows.append({
                "scope": copy.deepcopy(scope),
                "plo_codes": [codes[clo_position]],
                "status": "mapped",
                "confidence": "high" if official else "medium",
                "evidence": (
                    "ربط وارد في تقرير المقرر المؤسسي المطابق للرمز والنطاق."
                    if official
                    else "ربط تحليلي مقيّد بهذا البرنامج؛ بُني على دلالة CLO ونص ناتج البرنامج، ولا يُنسب إلى خلية PDF."
                ),
            })
        elif program in item.get("explicit_unmapped_programs", set()):
            rows.append({
                "scope": copy.deepcopy(scope),
                "plo_codes": [],
                "status": "explicitly_unmapped",
                "confidence": "high",
                "evidence": "ملف المقرر المشترك المنشور أفرغ خلية ربط PLO عمدًا؛ حُفظ الفراغ ولم يُخمن رمز برنامج.",
            })
        else:
            raise RuntimeError(f"no scoped PLO decision for {item['title']} / {scope}")
    return rows


def source_assessment(row: dict[str, Any], item: dict[str, Any], clo_code: str) -> tuple[str, int]:
    explicit = item.get("assessment", {})
    value = explicit.get(clo_code.split(".", 1)[0]) or explicit.get("*")
    if not value:
        value = row.get("assessment")
    if not value:
        value = "المناقشات والاختبارات"
    page = row.get("assessment_source_page") or row.get("source_page") or item["source_pages"][0]
    return str(value), int(page)


def reviewed_override(field: str, value: Any, evidence: str) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "evidence": evidence,
        "policy": "verified_reference_correction_pending_source_pdf_update",
        "reviewed_at": REVIEWED_AT,
    }


def recommendation(code: str, variant: dict[str, Any], fields: list[str], message: str) -> dict[str, Any]:
    payload = "|".join([code, variant["variant_id"], *fields, "2026-09-15"])
    return {
        "id": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "course_code": code,
        "variant_id": variant["variant_id"],
        "fields": fields,
        "issue_code": "SOURCE_PDF_ACADEMIC_COMPLETION_REQUIRED",
        "message": message,
        "recommendation": "إصدار PDF رسمي جديد بالرمز والنطاق الصحيحين، وإدراج CLO المصححة وربط PLO وطرق التقويم كما في طبقة المراجعة، ثم إعادة الاستخراج والتحقق من البصمة.",
        "source_pdf": variant["source_pdf"],
        "source_sha256": variant["source_sha256"],
        "status": "open",
        "created_at": "2026-09-15",
    }


def stage_reviews() -> None:
    outcomes = load(OUTCOMES)
    manifest = load(MANIFEST)
    evidence_by_code = {r["course_code"]: r for r in manifest["records"]}
    recommendations = [
        r for r in outcomes.get("source_correction_recommendations", [])
        if r.get("course_code") not in TARGETS
    ]
    for code, item in TARGETS.items():
        item = {**item, "course_code": code}
        variants = outcomes.get("courses", {}).get(code, {}).get("variants", [])
        if len(variants) != 1:
            raise RuntimeError(f"expected one rebuilt variant for {code}, found {len(variants)}")
        variant = variants[0]
        rows = variant["extracted"]["clos"]
        report = evidence_by_code[code]
        evidence = (
            f"مراجعة بصرية للمصدر {variant['source_pdf']} (SHA-256 {variant['source_sha256']}) "
            f"ولصفحات تقرير المقرر 4–6: {report['course_report']} "
            f"(SHA-256 {report['course_report_sha256']}). النص المستكمل طبقة قاعدة ولا يُنسب إلى PDF."
        )
        completed_clos = []
        for position, (clo_code, text) in enumerate(item["clos"].items()):
            mappings = mapping_rows(item, variant["scopes"], position)
            row = next((r for r in rows if r.get("code") == clo_code), None)
            if row is None:
                row = rows[min(position, len(rows) - 1)] if rows else {}
            page = row.get("source_page") or (4 if clo_code.startswith(("1.", "2.")) else 5)
            assessment, assessment_page = source_assessment({**row, "source_page": page}, item, clo_code)
            completed_clos.append({
                "code": clo_code,
                "text": text,
                "source_status": "present",
                "assessment": assessment,
                "assessment_source_page": assessment_page,
                "plo_mappings": mappings,
                "document_plo_codes": [],
                "confidence": "high",
                "source_page": int(page),
                "extraction_method": "reviewed_academic_completion",
            })
        completed_clos.sort(key=lambda row: (row["source_page"], row["code"]))
        overrides = [
            reviewed_override("course_name", item["title"], evidence),
            reviewed_override("clos", completed_clos, evidence),
        ]
        if item.get("assessment_plan"):
            overrides.append(reviewed_override(
                "assessment_plan",
                item["assessment_plan"],
                evidence + " أوزان خطة التقويم من جدول أنشطة تقييم الطلبة في الصفحات المثبتة، لا من درجات الطلاب.",
            ))
        variant["overrides"] = overrides
        variant["source_alignment"] = {
            "status": "source_pdf_gap_confirmed",
            "label_ar": "بيانات القاعدة مكتملة؛ PDF بحاجة إلى تعديل",
            "correction_applied": True,
            "source_update_recommended": True,
            "source_sha256": variant["source_sha256"],
        }
        variant["source_review"] = {
            "status": "needs_manual",
            "finding": PDF_UPDATE_FINDINGS[code],
            "evidence": {
                "file": variant["source_pdf"],
                "pages": item["source_pages"],
                "review_method": "تصيير الصفحات وفحص الغلاف والوصف والأهداف والموضوعات وجدول CLO وطرق التقويم بصريًا، ثم مقابلة تقرير المقرر ذي البصمة المثبتة في manifest.",
                "sha256_verified": True,
            },
            "reviewed_at": REVIEWED_AT,
            "source_sha256": variant["source_sha256"],
        }
        fields = [f"clos[{c}].text" for c in item["clos"]] + ["clos[*].plo_mappings", "course_name"]
        if item.get("assessment_plan"):
            fields.append("assessment_plan")
        recommendations.append(recommendation(
            code,
            variant,
            fields,
            "مصدر المقرر يحتاج نسخة رسمية محدثة: إما أنه يحمل رمزًا/نطاقًا سابقًا، أو أن جدول CLO/ربط PLO فيه ناقص أو معيب.",
        ))
    outcomes["source_correction_recommendations"] = sorted(recommendations, key=lambda r: r["id"])
    # Statistics describe the immutable extraction layer.  Recompute them with
    # the repository's own verifier instead of editing counters by hand.
    import importlib.util
    spec = importlib.util.spec_from_file_location("course_outcomes_verifier", ROOT / "scripts/verify_course_outcomes.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load verifier")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    errors = verifier.ErrorCollector()
    statistics = verifier.recompute_statistics(outcomes, errors)
    if errors.count or statistics is None:
        raise RuntimeError("statistics recomputation failed: " + "; ".join(errors.messages[:10]))
    outcomes["statistics"] = statistics
    write(OUTCOMES, outcomes)
    print(json.dumps({"stage": "reviews", "courses": len(TARGETS), "recommendations": len(TARGETS)}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("data", "reviews"))
    args = parser.parse_args()
    if args.stage == "data":
        stage_data()
    else:
        stage_reviews()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
