# -*- coding: utf-8 -*-
"""
Orange Lab — Inter-Branch Send-Out System
catalog.py — قاموس التحاليل

قرار تصميمي مهم: مفيش reference ranges هنا — ده مقصود.
النتيجة النهائية بتتطبع من نظام الفرع الأصلي، وهو مصدر الحقيقة للـ ranges.
لو كررناها هنا يبقى عندنا مصدرين للحقيقة، وأول ما واحد يتحدّث والتاني لأ
هتطلع تقارير متعارضة. الوحدة (unit) بس هي الإجبارية — الرقم لازم يسافر بوحدته.
"""

from dataclasses import dataclass, field
from typing import Tuple, Dict, List, Optional

# ── الفروع ────────────────────────────────────────────────────────────────
LACITE = "LACITE"
DIAMOND = "DIAMOND"

BRANCH_NAMES = {
    LACITE: {"ar": "لاسيتيه", "en": "La Cité", "short": "LCT"},
    DIAMOND: {"ar": "دياموند", "en": "Diamond", "short": "DMD"},
}

# ── الأجهزة ───────────────────────────────────────────────────────────────
DEV_BIOBASE = "BIOBASE_BK280"
DEV_HIPRO = "HIPRO"
DEV_HEMA = "HEMATOLOGY"
DEV_COAG = "COAGULOMETER"
DEV_OTHER = "OTHER"

DEVICE_NAMES = {
    DEV_BIOBASE: "BIOBASE BK-280",
    DEV_HIPRO: "HiPro",
    DEV_HEMA: "Hematology Analyzer",
    DEV_COAG: "Coatron",
    DEV_OTHER: "أخرى",
}

# ── الأنابيب ──────────────────────────────────────────────────────────────
TUBE_SERUM    = "Serum Gel (أصفر/أحمر)"
TUBE_CITRATE  = "Citrate 3.2% (أزرق)"
TUBE_EDTA     = "EDTA (بنفسجي)"
TUBE_FLUORIDE = "NaF/K-Ox (رمادي)"

# ⚙️ نافذة ثبات الجلوكوز (ساعات). عدّلها من هنا بس.
# النظام بيسجّل زمن النقل الحقيقي لكل عينة — بعد أسبوعين شغل هتبقى
# عندك بيانات فعلية تظبّط الرقم ده عليها بدل التخمين.
GLUCOSE_STABILITY_HOURS = 4.0

# أنواع التحليل
KIND_NUMERIC = "numeric"      # رقم واحد + وحدة
KIND_COMPOSITE = "composite"  # لوحة فيها عدة analytes (زي CBC)
KIND_TEXT = "text"            # نتيجة نصية (Positive/Negative مثلاً)


@dataclass(frozen=True)
class Analyte:
    """مكوّن واحد جوة لوحة مركّبة (CBC مثلاً)."""
    code: str
    name_en: str
    unit: str
    decimals: int = 1


@dataclass(frozen=True)
class TestDef:
    code: str
    name_en: str
    name_ar: str
    unit: str
    decimals: int
    device: str
    performed_at: Tuple[str, ...]   # الفرع/الفروع اللي بتعمل التحليل
    kind: str = KIND_NUMERIC
    components: Tuple[Analyte, ...] = field(default_factory=tuple)
    needs_review: bool = False      # محتاج تأكيد د. طارق على الوحدة/الطريقة
    note: str = ""

    # ⏱️ الثبات — أهم حقل في نظام بين فروع، لإن العينة بتقعد في النقل
    tube: str = ""                  # نوع الأنبوبة المطلوبة

    # ⚠️ الافتراضي None مقصود — يعني "مفيش مدة معتمدة".
    # كان 8.0، وده كان بيدي 31 تحليل نافذة ثبات محدش اعتمدها إكلينيكياً،
    # والنظام كان بيمنع استلامهم بناءً عليها. رقم مخترع أسوأ من مفيش رقم:
    # الأول بيمنع عينات سليمة بثقة كاذبة، والتاني على الأقل بيبان إنه ناقص.
    # التحاليل اللي None بيتعرضوا في قائمة "مستنية اعتماد مدة الثبات".
    stability_hours: Optional[float] = None      # في حرارة الغرفة
    stability_note: str = ""        # ليه الوقت ده بالذات
    stability_approved_by: str = "" # مين اعتمد المدة دي

    # ❄️ النقل المبرّد (2-8°م / ثلج)
    # التبريد بيطوّل المدة لمعظم التحاليل — بس مش كلها.
    # في تحاليل البرودة بتبوّظ نتيجتها، ودي cold_ok=False.
    stability_cold: Optional[float] = None
    cold_ok: bool = True
    cold_note: str = ""

    requires_fasting: bool = False

    @property
    def display(self) -> str:
        u = f" ({self.unit})" if self.unit else ""
        return f"{self.name_en}{u}"


# ── مكوّنات الـ CBC ────────────────────────────────────────────────────────
CBC_COMPONENTS: Tuple[Analyte, ...] = (
    Analyte("WBC", "WBC", "10³/µL", 1),
    Analyte("RBC", "RBC", "10⁶/µL", 2),
    Analyte("HGB", "Hemoglobin", "g/dL", 1),
    Analyte("HCT", "Hematocrit", "%", 1),
    Analyte("MCV", "MCV", "fL", 1),
    Analyte("MCH", "MCH", "pg", 1),
    Analyte("MCHC", "MCHC", "g/dL", 1),
    Analyte("RDW", "RDW-CV", "%", 1),
    Analyte("PLT", "Platelets", "10³/µL", 0),
    Analyte("MPV", "MPV", "fL", 1),
    Analyte("NEUT_P", "Neutrophils", "%", 1),
    Analyte("LYMPH_P", "Lymphocytes", "%", 1),
    Analyte("MONO_P", "Monocytes", "%", 1),
    Analyte("EOS_P", "Eosinophils", "%", 1),
    Analyte("BASO_P", "Basophils", "%", 1),
)


# ── مكوّنات تحاليل التجلط ─────────────────────────────────────────────────
# ترتيب المكوّنات = ترتيب خروجها من الـ Coatron بالظبط: PT / PC / INR
# (الـ PTT بيطلع لوحده فمعمول تحليل رقمي بسيط مش لوحة)
PT_COMPONENTS: Tuple[Analyte, ...] = (
    Analyte("PT_SEC", "PT", "sec", 1),
    Analyte("PC", "PC", "%", 0),
    Analyte("INR", "INR", "", 2),
)


def _T(code, en, ar, unit, dec, device, at, **kw) -> TestDef:
    return TestDef(code=code, name_en=en, name_ar=ar, unit=unit,
                   decimals=dec, device=device, performed_at=tuple(at), **kw)
# ══════════════════════════════════════════════════════════════════════════
# القاموس
#
# ⚠️ الترتيب هنا مقصود — هو ترتيب حسين وترتيب الشيت على البنش، مش أبجدي.
# الأبجدي كان بيفرّق حاجات المفروض تكون جنب بعض: Bilirubin Direct قبل
# Total، والـ 2h Post-Prandial يقفز لأول القايمة قبل ALT.
# لو ضفت تحليل جديد، حطه في مكانه الصح مش في الآخر.
#
# performed_at = الفرع اللي بيعمل التحليل (اللي العينة رايحة له)
# ══════════════════════════════════════════════════════════════════════════

TESTS: Dict[str, TestDef] = {t.code: t for t in [
    # ─── BIOBASE BK-280 @ لاسيتيه ─────────────────────────────────────────

    _T("TBIL",  "Bilirubin, Total",   "بيليروبين كلي",      "mg/dL", 2, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=8, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="⚠️ حساس للضوء — لازم يتغطى في النقل، بيتكسر بسرعة في الشمس",
       stability_cold=48,
       cold_note="التبريد بيطوّل المدة — بس الحماية من الضوء لسه لازمة"),
    _T("DBIL",  "Bilirubin, Direct",  "بيليروبين مباشر",     "mg/dL", 2, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=8, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="⚠️ حساس للضوء — لازم يتغطى في النقل",
       stability_cold=48,
       cold_note="التبريد بيطوّل المدة — بس الحماية من الضوء لسه لازمة"),
    _T("ALT",   "ALT (SGPT)",         "إنزيمات الكبد ALT",   "U/L",   0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت في حرارة الغرفة",
       stability_cold=72),
    _T("AST",   "AST (SGOT)",         "إنزيمات الكبد AST",   "U/L",   0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت في حرارة الغرفة",
       stability_cold=72),
    _T("ALP",   "Alkaline Phosphatase", "الفوسفاتيز القلوي", "U/L",   0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="النشاط بيزيد شوية بمرور الوقت — يفضّل التشغيل بدري",
       stability_cold=48),
    _T("GGT",   "GGT",                "جاما GT",            "U/L",   0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت جداً",
       stability_cold=72),
    _T("TP",    "Total Protein",      "بروتين كلي",          "g/dL",  1, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("ALB",   "Albumin",            "ألبيومين",            "g/dL",  1, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت جداً",
       stability_cold=72),
    _T("UREA",  "Urea",               "يوريا",               "mg/dL", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("CREA",  "Creatinine",         "كرياتينين",           "mg/dL", 2, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("URIC",  "Uric Acid",          "حمض بوليك",           "mg/dL", 1, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("NA",    "Sodium (Na⁺)",       "صوديوم",              "mmol/L", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("K",     "Potassium (K⁺)",     "بوتاسيوم",            "mmol/L", 1, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM, stability_hours=4,
       stability_note="⚠️ لازم فصل السيرم بسرعة — البوتاسيوم بيرتفع كذباً لو فضل على الكرات",
       stability_approved_by="حسين علي",
       stability_cold=72, cold_ok=False,
       cold_note="⛔ ممنوع تبريد الدم الكامل! مضخة Na/K بتقف في البرودة فالبوتاسيوم بيتسرّب من الكرات الحمرا ← pseudohyperkalemia (نتيجة عالية كذباً، ممكن توصل 6-7 وهو أصلاً 4). لازم تفصل السيرم الأول ثم تبرّد."),
    _T("CA",    "Calcium, Total",     "كالسيوم كلي",         "mg/dL", 1, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("CAION", "Calcium, Ionized",   "كالسيوم متأين",       "mmol/L", 2, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=1, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="⚠️⚠️ ساعة واحدة! لازم أنبوبة مقفولة (anaerobic) — التعرض للهوا بيرفع الـ pH فتقل القراءة. مش مناسب للنقل بين الفروع.",
       stability_cold=4,
       cold_note="❄️ الثلج بيطوّلها من ساعة لـ 4 — بس لازم تفضل anaerobic"),
    # قرار حسين. الترتيب في القايمة الأصلية (Ca / Ca++ / PH / Cl / PO4)
    # بيقول إنه الـ pH — لإن الكالسيوم المتأين بيتصحّح على pH 7.4.
    # من غير وحدة (نسبة لوغاريتمية). لو المقصود حاجة تانية: غيّر السطر ده وبس.
    _T("PH",    "pH",                 "الأس الهيدروجيني",     "", 2, DEV_BIOBASE, [LACITE],
        note="بيُستخدم لتصحيح الكالسيوم المتأين على pH 7.4",
       tube=TUBE_SERUM,
       stability_hours=1, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="⚠️⚠️ ساعة واحدة! لازم anaerobic — الـ CO₂ بيتسرب فالـ pH يرتفع.",
       stability_cold=4,
       cold_note="❄️ الثلج بيطوّلها من ساعة لـ 4 — بس لازم تفضل anaerobic"),
    _T("CL",    "Chloride (Cl⁻)",     "كلورايد",             "mmol/L", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("PO4",   "Phosphorus (PO₄)",   "فوسفور",              "mg/dL", 1, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=8, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="بيرتفع لو السيرم فضل على الكرات — افصله بسرعة",
       stability_cold=48),
    _T("CHOL",  "Cholesterol, Total", "كوليسترول كلي",       "mg/dL", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("TRIG",  "Triglycerides",      "دهون ثلاثية",         "mg/dL", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("HDL",   "HDL-Cholesterol",    "الكوليسترول النافع",   "mg/dL", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),
    _T("LDL",   "LDL-Cholesterol",    "الكوليسترول الضار",    "mg/dL", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت (أو محسوب من الباقي)",
       stability_cold=72),
    _T("ASO",   "ASO Titre",          "أنتي ستربتوليسين O",   "IU/mL", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت جداً",
       stability_cold=72),
    _T("CRP_B", "CRP (Biobase)",      "بروتين سي التفاعلي",   "mg/L",  1, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت جداً",
       stability_cold=72),
    _T("VITD",  "Vitamin D3 (25-OH)", "فيتامين د",           "ng/mL", 1, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت جداً",
       stability_cold=72),

    # ─── السكر والتجلط @ لاسيتيه ─────────────────────────────────────────

    # قرار حسين: سيرم عادي — مش NaF.
    # والقرار ده مدعوم علمياً: الـ NaF بيثبّط إنزيم enolase وهو *متأخر* في
    # سلسلة الـ glycolysis، فبيفضل الجلوكوز بينزل في أول ساعة تقريباً زي
    # السيرم العادي بالظبط. يعني NaF مش بيحل المشكلة، بيأجّلها.
    # اللي بيحلها فعلاً حاجتين بس: (أ) فصل السيرم بسرعة، (ب) قصر وقت النقل.
    # عشان كده المتغيّر الوحيد اللي بيهم هو زمن النقل — والنظام بيقيسه.
    _T("FBG",  "Fasting Blood Glucose", "سكر صائم",       "mg/dL", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM, stability_hours=GLUCOSE_STABILITY_HOURS, requires_fasting=True,
       stability_note="الجلوكوز بيقل ~6%/ساعة — زمن النقل هو المتغيّر الوحيد المهم",
       stability_approved_by="حسين علي",
       stability_cold=8,
       cold_note="❄️ البرودة بتبطّأ الـ glycolysis — من 4 ساعات لـ 8"),
    _T("PP2",  "2h Post-Prandial Glucose", "سكر بعد الأكل بساعتين", "mg/dL", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM, stability_hours=GLUCOSE_STABILITY_HOURS,
       stability_note="نفس تحذير الجلوكوز + لازم تسجّل وقت بداية الأكل",
       stability_approved_by="حسين علي",
       stability_cold=8,
       cold_note="❄️ البرودة بتبطّأ الـ glycolysis"),

    # ⚠️ أخطر اتنين في القايمة كلها بالنسبة لنظام بين فروع:
    # aPTT ثباته 4 ساعات بس (CLSI H21) — لو النقل اتأخر النتيجة تبقى غلط.
    # وكمان الأنبوبة الزرقا لازم تتملي لحد العلامة (نسبة 9:1) وإلا
    # النتيجة تطلع مطوّلة كذباً.
    _T("PT",   "PT / PC / INR",          "زمن البروثرومبين",  "", 1, DEV_COAG, [LACITE],
       kind=KIND_COMPOSITE, components=PT_COMPONENTS,
       tube=TUBE_CITRATE, stability_hours=24,
       stability_note="أنبوبة citrate مليانة للعلامة (9:1). ثبات 24 ساعة.",
       stability_approved_by="CLSI H21",
       stability_cold=24, cold_ok=False,
       cold_note="⛔ ممنوع التبريد! البرودة بتنشّط Factor VII فالـ PT يقصر كذباً. CLSI H21: النقل في 18-24°م."),
    _T("PTT",  "PTT",                   "زمن الثرومبوبلاستين", "sec", 1, DEV_COAG, [LACITE],
       tube=TUBE_CITRATE, stability_hours=4,
       stability_note="⚠️ ثبات 4 ساعات بس! لو المريض على هيبارين لازم فصل البلازما خلال ساعة.",
       stability_approved_by="CLSI H21",
       stability_cold=4, cold_ok=False,
       cold_note="⛔ ممنوع التبريد! البرودة بترسّب vWF/FVIII فالـ aPTT يطول كذباً. CLSI H21: النقل في 18-24°م."),
    _T("RBG",  "Random Blood Glucose", "سكر عشوائي",      "mg/dL", 0, DEV_BIOBASE, [LACITE],
       tube=TUBE_SERUM, stability_hours=GLUCOSE_STABILITY_HOURS,
       stability_note="الجلوكوز بيقل ~6%/ساعة — زمن النقل هو المتغيّر الوحيد المهم",
       stability_approved_by="حسين علي",
       stability_cold=8,
       cold_note="❄️ البرودة بتبطّأ الـ glycolysis"),

    # ─── HiPro @ لاسيتيه ──────────────────────────────────────────────────

    _T("HBA1C", "HbA1c",              "السكر التراكمي",       "%",     1, DEV_HIPRO, [LACITE],
       tube=TUBE_EDTA, stability_hours=72,
       stability_note="ثابت جداً — مفيش قلق من النقل",
       stability_approved_by="حسين علي",
       stability_cold=168),
    _T("CRP_H", "CRP (HiPro)",        "بروتين سي التفاعلي",   "mg/L",  1, DEV_HIPRO, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت جداً",
       stability_cold=72),
    _T("RF_H",  "Rheumatoid Factor",  "الروماتويد",           "IU/mL", 1, DEV_HIPRO, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت جداً",
       stability_cold=72),
    _T("FERR",  "Ferritin",           "فيريتين",              "ng/mL", 1, DEV_HIPRO, [LACITE],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت",
       stability_cold=72),

    # ─── @ دياموند (اللي لاسيتيه بتبعتله) ────────────────────────────────

    _T("MG",    "Magnesium",          "ماغنسيوم",             "mg/dL", 2, DEV_OTHER, [DIAMOND],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت — بس الهيموليزيس بيرفعه بشدة",
       stability_cold=72),
    _T("CKMB",  "CK-MB",              "إنزيم القلب CK-MB",    "U/L",   0, DEV_OTHER, [DIAMOND],
        note="قرار حسين: U/L (قياس نشاط). لو الكِت مناعي بالكتلة غيّرها لـ ng/mL.",
       tube=TUBE_SERUM,
       stability_hours=4, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="⚠️ النشاط الإنزيمي بيقل بسرعة في حرارة الغرفة",
       stability_cold=24,
       cold_note="التبريد بيحسّنها كتير — من 4 ساعات لـ 24"),
    _T("CBC",   "CBC",                "صورة دم كاملة",        "",      0, DEV_HEMA,  [DIAMOND],
        kind=KIND_COMPOSITE, components=CBC_COMPONENTS,
        tube=TUBE_EDTA, stability_hours=8,
        stability_note="بعد 8 ساعات الـ MCV بيرتفع والصفايح بتقل",
       stability_approved_by="حسين علي",
       stability_cold=24,
       cold_note="التبريد بيطوّلها لـ 24 ساعة — بس الفيلم يتعمل خلال 4 ساعات"),
    _T("LDH",   "LDH",                "إنزيم LDH",            "U/L",   0, DEV_OTHER, [DIAMOND],
       tube=TUBE_SERUM,
       stability_hours=8, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="⚠️ ماينفعش يتبرّد (LDH-4/5 بتتكسر بالبرودة). والهيموليزيس بيرفعه بشدة.",
       stability_cold=8, cold_ok=False,
       cold_note="⛔ ممنوع التبريد! إنزيمات LDH-4 و LDH-5 بتتكسر بالبرودة ← نتيجة أقل من الحقيقة. سيبها في حرارة الغرفة."),
    _T("RF_D",  "Rheumatoid Factor",  "الروماتويد",           "IU/mL", 1, DEV_OTHER, [DIAMOND],
       tube=TUBE_SERUM,
       stability_hours=24, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="ثابت جداً",
       stability_cold=72),
    _T("CPK",   "CPK (Total CK)",     "إنزيم العضلات CPK",    "U/L",   0, DEV_OTHER, [DIAMOND],
       tube=TUBE_SERUM,
       stability_hours=8, stability_approved_by="مراجع مخبرية — يحتاج توقيع د. طارق",
       stability_note="⚠️ بيقل بمرور الوقت + حساس للضوء",
       stability_cold=48,
       cold_note="التبريد بيحافظ على النشاط الإنزيمي"),
]}


# ── دوال مساعدة ───────────────────────────────────────────────────────────

def get(code: str) -> Optional[TestDef]:
    return TESTS.get(code.upper().strip())


# رقم ترتيب لكل تحليل حسب مكانه في القاموس فوق (الـ dict بيحافظ على الترتيب)
ORDER_INDEX: Dict[str, int] = {c: i for i, c in enumerate(TESTS)}


def tests_for_route(performing_branch: str) -> List[TestDef]:
    """
    التحاليل المتاحة في الفرع المُنفِّذ — بترتيب القاموس، مش أبجدي.
    ده مقصود: الفني بيمسح القايمة بعينه على الترتيب اللي حافظه،
    فاللي بيدوّر على AST بيلاقيه جنب ALT على طول.
    """
    return [t for t in TESTS.values() if performing_branch in t.performed_at]


def grouped_for_route(performing_branch: str) -> Dict[str, List[TestDef]]:
    """نفس اللي فوق بس مجمّعة بالجهاز — للعرض في الـ UI."""
    groups: Dict[str, List[TestDef]] = {}
    for t in tests_for_route(performing_branch):
        groups.setdefault(t.device, []).append(t)
    return groups


def other_branch(branch: str) -> str:
    return DIAMOND if branch == LACITE else LACITE


def review_queue() -> List[TestDef]:
    """التحاليل اللي محتاجة مراجعة د. طارق قبل التشغيل الفعلي."""
    return [t for t in TESTS.values() if t.needs_review]


def required_tubes(test_keys) -> Dict[str, List[str]]:
    """
    اشتقاق الأنابيب المطلوبة من التحاليل المختارة.
    بيمنع أشهر غلطة في الإرسال: بعت أنبوبة واحدة وهو محتاج تلاتة.
    بيرجّع {نوع الأنبوبة: [أسماء التحاليل]}
    """
    out: Dict[str, List[str]] = {}
    for k in test_keys:
        t = get(k) if not str(k).startswith("X:") else None
        tube = t.tube if t else "Serum Gel (أصفر/أحمر)"   # الافتراضي للتحاليل الإضافية
        out.setdefault(tube, []).append(t.name_en if t else str(k)[2:])
    return out


def tightest_stability(test_keys, cold: bool = False):
    """
    أقصر مدة ثبات *معتمدة* بين التحاليل المطلوبة — دي اللي بتحكم النقل.
    التحاليل اللي مالهاش مدة معتمدة بتتتجاهل هنا وبتظهر في unvalidated().
    بيرجّع (ساعات، اسم التحليل، الملاحظة) أو None.
    """
    best = None
    for k in test_keys:
        if str(k).startswith("X:"):
            continue
        t = get(k)
        w = window(t, cold) if t else None
        if w is None:
            continue
        note = (t.cold_note or t.stability_note) if cold else t.stability_note
        if best is None or w < best[0]:
            best = (w, t.name_en, note)
    return best


def unvalidated(test_keys) -> List[str]:
    """التحاليل المطلوبة اللي مفيش ليها مدة ثبات معتمدة."""
    out = []
    for k in test_keys:
        if str(k).startswith("X:"):
            continue
        t = get(k)
        if t is not None and t.stability_hours is None:
            out.append(t.name_en)
    return out


def window(t: TestDef, cold: bool) -> Optional[float]:
    """نافذة الثبات حسب ظروف النقل."""
    if cold and t.stability_cold is not None:
        return t.stability_cold
    return t.stability_hours


def cold_unsuitable(test_keys) -> List[TestDef]:
    """
    التحاليل اللي التبريد بيضرها.
    دي مش مسألة وقت — دي نتيجة غلط. عينة مبرّدة فيها LDH بتدي رقم أقل
    من الحقيقة، والبوتاسيوم بيدي رقم أعلى، والتجلط بيدي زمن مغلوط.
    """
    out = []
    for k in test_keys:
        if str(k).startswith("X:"):
            continue
        t = get(k)
        if t is not None and not t.cold_ok:
            out.append(t)
    return out


def pending_stability() -> List[TestDef]:
    """
    كل التحاليل المستنية اعتماد مدة ثبات — للعرض في لوحة المدير.
    الهدف إن الفجوة تفضل ظاهرة قدامك لحد ما تقفلها، مش تتنسى بصمت.
    """
    return [t for t in TESTS.values() if t.stability_hours is None]


def fasting_tests(test_keys) -> List[str]:
    """التحاليل اللي بتتطلب صيام."""
    return [t.name_en for k in test_keys
            if not str(k).startswith("X:") and (t := get(k)) and t.requires_fasting]


# ══════════════════════════════════════════════════════════════════════════
# اللوحات الجاهزة — التجميعات اللي بتتطلب مع بعض عادةً.
# الهدف: ضغطة واحدة بدل ما الموظف يدوّر على 8 تحاليل واحد واحد.
# ══════════════════════════════════════════════════════════════════════════

PANELS = {
    "🫀 وظائف كبد": ["TBIL", "DBIL", "ALT", "AST", "ALP", "GGT", "TP", "ALB"],
    "🫘 وظائف كلى": ["UREA", "CREA", "URIC", "NA", "K", "CL"],
    "🩸 دهون":      ["CHOL", "TRIG", "HDL", "LDL"],
    "🍬 سكر":       ["FBG", "PP2", "HBA1C"],
    "🧬 تجلط":      ["PT", "PTT"],
    "🔥 التهاب":    ["CRP_B", "ASO", "RF_H"],
    "🦴 معادن":     ["CA", "CAION", "PO4", "PH"],
    "💊 أنيميا":    ["FERR", "VITD"],
    # لوحة دياموند — إنزيمات القلب/العضلات بتتطلب مع بعض
    "❤️ إنزيمات قلب": ["CKMB", "CPK", "LDH"],
}


def panels_for_route(performing_branch: str) -> Dict[str, List[str]]:
    """اللوحات اللي كل تحاليلها متاحة في الفرع المُنفِّذ."""
    out = {}
    for name, codes in PANELS.items():
        avail = [c for c in codes
                 if (t := get(c)) and performing_branch in t.performed_at]
        if avail:
            out[name] = avail
    return out


def fmt(code: str, value) -> str:
    """تنسيق القيمة بعدد الخانات العشرية الصح + الوحدة."""
    t = get(code)
    if t is None or value in (None, ""):
        return str(value or "")
    try:
        s = f"{float(value):.{t.decimals}f}"
    except (TypeError, ValueError):
        s = str(value)
    return f"{s} {t.unit}".strip()
