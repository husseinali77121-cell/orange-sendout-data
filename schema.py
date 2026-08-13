# -*- coding: utf-8 -*-
"""
Orange Lab — Inter-Branch Send-Out System
schema.py — الـ data model + الـ state machine + التحقق

المبدأ الأساسي: الطلب record واحد فيه events[] بتتضاف ومتتعدّلش أبداً.
ده بيدي audit trail مطلوب في ISO 15189:2022 + حساب TAT مجاناً.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import catalog

SCHEMA_VERSION = 1

# توقيت مصر — ثابت (مصر بتستخدم DST بس التخزين بالـ UTC والعرض محلي)
CAIRO = timezone(timedelta(hours=3))


# ══════════════════════════════════════════════════════════════════════════
# الحالات (State Machine)
# ══════════════════════════════════════════════════════════════════════════

DRAFT = "DRAFT"              # الفرع الأصلي بيكتب الطلب
SENT = "SENT"                # العينة اتسلّمت للمندوب/السواق
RECEIVED = "RECEIVED"        # الفرع المنفّذ استلم وقبل العينة
REJECTED = "REJECTED"        # الفرع المنفّذ رفض العينة (نهاية)
IN_PROGRESS = "IN_PROGRESS"  # شغّال على الجهاز
RESULTED = "RESULTED"        # النتيجة اتدخلت
VERIFIED = "VERIFIED"        # د. طارق راجع واعتمد
CLOSED = "CLOSED"            # الفرع الأصلي نقل النتيجة لنظامه — الحلقة اتقفلت
CANCELLED = "CANCELLED"      # اتلغى قبل التنفيذ (نهاية)

TERMINAL = {REJECTED, CLOSED, CANCELLED}

TRANSITIONS: Dict[str, set] = {
    DRAFT:       {SENT, CANCELLED},
    SENT:        {RECEIVED, REJECTED, CANCELLED},
    RECEIVED:    {IN_PROGRESS, REJECTED},
    IN_PROGRESS: {RESULTED, REJECTED},
    RESULTED:    {VERIFIED, IN_PROGRESS},   # رجوع لو النتيجة محتاجة إعادة
    VERIFIED:    {CLOSED, IN_PROGRESS},     # رجوع لو د. طارق رفض النتيجة
    REJECTED:    set(),
    CLOSED:      set(),
    CANCELLED:   set(),
}

STATUS_AR = {
    DRAFT: "مسودة", SENT: "تم التسليم", RECEIVED: "تم الاستلام",
    REJECTED: "مرفوضة", IN_PROGRESS: "تحت التشغيل",
    RESULTED: "النتيجة جاهزة", VERIFIED: "معتمدة",
    CLOSED: "خلص", CANCELLED: "ملغية",
}

STATUS_COLOR = {
    DRAFT: "📝", SENT: "🚚", RECEIVED: "📦", REJECTED: "⛔",
    IN_PROGRESS: "🔬", RESULTED: "📄", VERIFIED: "✅",
    CLOSED: "🏁", CANCELLED: "⚫",
}

# ألوان الحالات: (لون النص، لون الخلفية)
STATUS_HEX = {
    DRAFT:       ("#616161", "#F5F5F5"),
    SENT:        ("#1565C0", "#E3F2FD"),
    RECEIVED:    ("#6A1B9A", "#F3E5F5"),
    IN_PROGRESS: ("#E65100", "#FFF3E0"),
    RESULTED:    ("#00695C", "#E0F2F1"),
    VERIFIED:    ("#2E7D32", "#E8F5E9"),
    CLOSED:      ("#37474F", "#ECEFF1"),
    REJECTED:    ("#C62828", "#FFEBEE"),
    CANCELLED:   ("#455A64", "#ECEFF1"),
}

# الخطوة الجاية لكل حالة — بتتعرض للمستخدم بدل ما يتساءل
NEXT_STEP = {
    DRAFT: "سلّمها للمندوب",
    SENT: "الفرع التاني لسه مستلمش",
    RECEIVED: "لسه ماتشغّلتش",
    IN_PROGRESS: "بيتكتب فيها النتايج",
    RESULTED: "مستنية الاعتماد",
    VERIFIED: "جاهزة للنقل",
    CLOSED: "خلصت",
    REJECTED: "اترفضت — لازم عينة جديدة",
    CANCELLED: "اتلغت",
}

# أسباب رفض العينة (ISO 15189 §7.2 — pre-examination)
REJECTION_REASONS = [
    "عينة مُحلَّلة (Hemolyzed)",
    "كمية غير كافية (QNS)",
    "أنبوبة غير صحيحة / مانع تجلط خطأ",
    "عينة متجلطة (Clotted)",
    "بيانات ناقصة أو غير مطابقة",
    "بدون بيانات على الأنبوبة (Unlabeled)",
    "تأخر النقل / درجة حرارة غير مناسبة",
    "أنبوبة مكسورة أو مسرّبة",
    "عينة ليباميه (Lipemic)",
    "خلص وقت الثبات (Stability exceeded)",
    "أنبوبة citrate مش مليانة للعلامة",
    "أخرى",
]

SPECIMEN_CONDITIONS = ["سليمة", "مُحلَّلة قليلاً", "ليباميه", "كمية قليلة", "أخرى"]

TRANSPORT_MODES = ["مندوب", "سواق", "موظف", "أخرى"]


# ══════════════════════════════════════════════════════════════════════════
# أدوات
# ══════════════════════════════════════════════════════════════════════════

def now_iso() -> str:
    """UTC ISO — التخزين دايماً UTC عشان المقارنات تبقى سليمة."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_local(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(CAIRO)


def local_str(iso: str, fmt: str = "%Y-%m-%d %H:%M") -> str:
    try:
        return to_local(iso).strftime(fmt)
    except Exception:
        return iso or ""


def today_key() -> str:
    """مفتاح ملف اليوم — بتوقيت القاهرة (يوم العمل المحلي)."""
    return datetime.now(CAIRO).strftime("%Y-%m-%d")


_ISSUED: set = set()          # الـ IDs المتولّدة في الـ process ده
_ISSUED_LOCK = __import__("threading").Lock()
_ISSUED_MAX = 20000


def new_request_id(origin_branch: str) -> str:
    """
    SND-DMD-20260813-142233-A7F23B9C

    ⚠️ الـ random suffix كان 2 bytes (65536 قيمة) وده كان بيدي تكرار حقيقي:
    3000 طلب في نفس الثانية = ~79 تكرار (birthday problem). دلوقتي 4 bytes.
    وكمان في حارس داخل الـ process بيعيد التوليد لو حصل تصادم — عشان
    الضمان يبقى مؤكد مش احتمالي. (الحارس التاني هو فحص التكرار في store.create)
    """
    short = catalog.BRANCH_NAMES[origin_branch]["short"]
    stamp = datetime.now(CAIRO).strftime("%Y%m%d-%H%M%S")
    with _ISSUED_LOCK:
        for _ in range(50):
            rid = f"SND-{short}-{stamp}-{secrets.token_hex(4).upper()}"
            if rid not in _ISSUED:
                if len(_ISSUED) >= _ISSUED_MAX:
                    _ISSUED.clear()
                _ISSUED.add(rid)
                return rid
    raise RuntimeError("فشل توليد ID فريد — ده مش المفروض يحصل أبداً")


_PHONE_RE = re.compile(r"\D+")


def patient_key(name: str, phone: str = "") -> str:
    """
    مفتاح ثابت للمريض عبر الزيارات — لازم للـ delta check (مقارنة بالنتيجة السابقة).
    الموبايل هو الأساس لو موجود، والاسم المطبّع احتياطي.
    """
    digits = _PHONE_RE.sub("", phone or "")
    if len(digits) >= 10:
        return "P:" + digits[-10:]
    norm = re.sub(r"\s+", " ", (name or "").strip())
    norm = norm.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    return "N:" + norm.lower()


# ══════════════════════════════════════════════════════════════════════════
# بناء الطلب
# ══════════════════════════════════════════════════════════════════════════

def new_request(
    *,
    origin_branch: str,
    performing_branch: str,
    patient_name: str,
    lab_code: str,
    age: str = "",
    sex: str = "",
    phone: str = "",
    complaint: str = "",
    request_note: str = "",
    referring_doctor: str = "",
    fasting: Optional[bool] = None,
    collected_at: str = "",
    tests: Optional[List[Dict[str, Any]]] = None,
    tubes: Optional[List[Dict[str, Any]]] = None,
    created_by: str = "",
) -> Dict[str, Any]:
    """
    tests = [{"code": "ALT"}, {"custom_name": "Lipase", "custom_unit": "U/L"}]
      - الـ ad-hoc tests (اللي المستخدم بيكتبها) بتتخزّن بـ custom_name بدل code
    """
    if origin_branch == performing_branch:
        raise ValueError("الفرع المُرسِل والمُستقبِل لازم يكونوا مختلفين")
    if not (patient_name or "").strip():
        raise ValueError("اسم المريض مطلوب")
    if not (lab_code or "").strip():
        raise ValueError("كود المعمل مطلوب")

    rid = new_request_id(origin_branch)
    ts = now_iso()
    norm_tests = _normalize_tests(tests or [])
    keys = [t["code"] or t["key"] for t in norm_tests]

    return {
        "schema_version": SCHEMA_VERSION,
        "id": rid,
        "day": today_key(),
        "origin_branch": origin_branch,
        "performing_branch": performing_branch,
        "status": DRAFT,

        # ⏱️ وقت السحب الحقيقي — أساس حساب الثبات.
        # لو مااتكتبش بنفترض وقت إنشاء الطلب (تقدير متحفّظ).
        "collected_at": collected_at or ts,

        "patient": {
            "name": patient_name.strip(),
            "lab_code": lab_code.strip(),
            "age": (age or "").strip(),
            "sex": (sex or "").strip(),
            "phone": (phone or "").strip(),
            "key": patient_key(patient_name, phone),
        },

        "clinical": {
            "complaint": (complaint or "").strip(),
            "referring_doctor": (referring_doctor or "").strip(),
            "fasting": fasting,
        },

        # الملاحظات — 4 مستويات، كل واحد ليه صاحبه
        "notes": {
            "on_request": (request_note or "").strip(),   # دياموند وقت الإرسال
            "on_receipt": "",                              # لاسيتيه وقت الاستلام
            "on_result": "",                               # لاسيتيه ملاحظة عامة
            # المستوى الرابع (ملاحظة على كل تحليل لوحده) جوة results[code]["note"]
        },

        "tubes": tubes or [{"type": tb, "count": 1, "for": names}
                           for tb, names in catalog.required_tubes(keys).items()],
        "tests": norm_tests,
        "results": {},                 # {code_or_custom_key: {...}}

        "transport": {},               # يتملى عند SENT
        "receipt": {},                 # يتملى عند RECEIVED / REJECTED
        "critical": [],                # سجل القيم الحرجة + read-back
        "events": [],
        "created_at": ts,
        "created_by": created_by,
        "updated_at": ts,
    }


def _normalize_tests(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """توحيد شكل التحاليل + منع التكرار."""
    out, seen = [], set()
    for it in items:
        code = (it.get("code") or "").upper().strip()
        if code:
            t = catalog.get(code)
            if t is None:
                raise ValueError(f"كود تحليل غير معروف: {code}")
            key = code
            entry = {"key": key, "code": code, "name": t.name_en,
                     "unit": t.unit, "kind": t.kind, "custom": False}
        else:
            nm = (it.get("custom_name") or "").strip()
            if not nm:
                continue  # خانة فاضية — بنتجاهلها بهدوء
            key = "X:" + nm.upper()
            entry = {"key": key, "code": None, "name": nm,
                     "unit": (it.get("custom_unit") or "").strip(),
                     "kind": catalog.KIND_NUMERIC, "custom": True}
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    if not out:
        raise ValueError("لازم تختار تحليل واحد على الأقل")

    # ترتيب التحاليل بترتيب القاموس مش بترتيب ضغط المستخدم.
    # السبب: الشيت على البنش لازم يبقى شكله واحد كل مرة، عشان الفني
    # يحفظ مكان كل تحليل بعينه. التحاليل الإضافية بتروح الآخر.
    out.sort(key=lambda e: catalog.ORDER_INDEX.get(e["code"], 10_000)
             if e["code"] else 10_001)
    return out


# ══════════════════════════════════════════════════════════════════════════
# الانتقالات
# ══════════════════════════════════════════════════════════════════════════

class TransitionError(Exception):
    pass


class StabilityError(Exception):
    """العينة خلص وقت ثباتها — استلامها كده بينتج نتيجة غلط."""
    pass


def can(req: Dict[str, Any], target: str) -> bool:
    return target in TRANSITIONS.get(req.get("status", DRAFT), set())


def _event(req, action, actor, branch, detail=None):
    req.setdefault("events", []).append({
        "at": now_iso(), "action": action, "actor": actor or "",
        "branch": branch or "", "detail": detail or {},
    })
    req["updated_at"] = now_iso()


def transition(req: Dict[str, Any], target: str, *, actor: str,
               branch: str, detail: Optional[dict] = None) -> Dict[str, Any]:
    cur = req.get("status", DRAFT)
    if target not in TRANSITIONS.get(cur, set()):
        raise TransitionError(
            f"مش مسموح: {STATUS_AR.get(cur, cur)} ← {STATUS_AR.get(target, target)}"
        )
    req["status"] = target
    _event(req, f"→{target}", actor, branch, detail)
    return req


# ── أفعال جاهزة ───────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════
# ⏱️ الثبات — الحماية الأهم في نظام بين فروع
# ══════════════════════════════════════════════════════════════════════════

def hours_since_collection(req, at_iso: Optional[str] = None) -> float:
    """كام ساعة عدّت من السحب."""
    t0 = datetime.fromisoformat(req.get("collected_at") or req["created_at"])
    t1 = datetime.fromisoformat(at_iso) if at_iso else datetime.now(timezone.utc)
    return round((t1 - t0).total_seconds() / 3600, 2)


def stability_check(req, at_iso: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    فحص كل تحليل: هل العينة لسه صالحة؟
    بيرجّع قائمة بالمشاكل — فاضية يعني تمام.
    level: 'expired' = خلصت مدته | 'warning' = قرّب يخلص (>75%)
    """
    elapsed = hours_since_collection(req, at_iso)
    issues = []
    for t in req["tests"]:
        if t.get("custom") or not t.get("code"):
            continue
        td = catalog.get(t["code"])
        if td is None:
            continue
        limit = td.stability_hours
        if limit is None:
            # مفيش مدة معتمدة → مفيش منع. الفجوة بتتعرض في
            # preanalytical_warnings و catalog.pending_stability()
            continue
        if elapsed > limit:
            issues.append({"level": "expired", "test": td.name_en,
                           "elapsed": elapsed, "limit": limit,
                           "note": td.stability_note})
        elif elapsed > limit * 0.75:
            issues.append({"level": "warning", "test": td.name_en,
                           "elapsed": elapsed, "limit": limit,
                           "note": td.stability_note})
    return issues


def preanalytical_warnings(req) -> List[str]:
    """
    تحذيرات قبل الإرسال — بتظهر لموظف الاستقبال وهو بيجهّز العينة.
    تنبيهات مش موانع: الموظف هو اللي يقرر.
    """
    warns = []
    keys = [t["code"] or t["key"] for t in req["tests"]]

    need_fast = catalog.fasting_tests(keys)
    if need_fast and req["clinical"].get("fasting") is not True:
        warns.append("🍽️ " + "، ".join(need_fast) + " — بتتطلب صيام، والصيام مش مؤكّد في الطلب")

    tight = catalog.tightest_stability(keys)
    if tight and tight[0] <= 4:
        warns.append(f"⏱️ أقصر مدة ثبات: {tight[1]} = {tight[0]:g} ساعة. {tight[2]}")

    unval = catalog.unvalidated(keys)
    if unval:
        n = len(unval)
        sample_names = "، ".join(unval[:3]) + ("…" if n > 3 else "")
        warns.append(f"ℹ️ {n} تحليل مفيش ليهم مدة ثبات معتمدة "
                     f"({sample_names}) — النظام مش هيمنع استلامهم.")

    tubes = catalog.required_tubes(keys)
    if len(tubes) > 1:
        warns.append("🧪 محتاج " + str(len(tubes)) + " أنابيب مختلفة: " + "، ".join(tubes))

    if any(t.get("code") == "PP2" for t in req["tests"]):
        warns.append("🕐 سكر بعد ساعتين — سجّل وقت بداية الأكل في ملاحظة الطلب")

    return warns


def mark_sent(req, *, actor, mode="مندوب", courier="", note=""):
    req["transport"] = {"mode": mode, "courier": courier,
                        "at": now_iso(), "by": actor, "note": note}
    return transition(req, SENT, actor=actor, branch=req["origin_branch"],
                      detail={"mode": mode, "courier": courier})


def mark_received(req, *, actor, condition="سليمة", note="",
                  override_stability: bool = False):
    """
    ⚠️ لو العينة خلص وقت ثباتها، الاستلام بيتمنع إلا بتجاوز صريح
    من الفني — والتجاوز بيتسجّل في الـ audit trail باسمه.
    """
    expired = [i for i in stability_check(req) if i["level"] == "expired"]
    if expired and not override_stability:
        names = "، ".join(f"{i['test']} ({i['elapsed']:g}س / حد {i['limit']:g}س)"
                          for i in expired)
        raise StabilityError("خلص وقت الثبات: " + names)

    req["receipt"] = {"at": now_iso(), "by": actor, "condition": condition,
                      "accepted": True,
                      "hours_in_transit": hours_since_collection(req),
                      "stability_override": bool(expired and override_stability)}
    if note:
        req["notes"]["on_receipt"] = note.strip()

    if expired and override_stability:
        _event(req, "STABILITY_OVERRIDE", actor, req["performing_branch"],
               {"tests": [i["test"] for i in expired],
                "elapsed_hours": expired[0]["elapsed"]})
    return transition(req, RECEIVED, actor=actor,
                      branch=req["performing_branch"], detail={"condition": condition})


def mark_rejected(req, *, actor, reason, note=""):
    if not reason:
        raise ValueError("سبب الرفض مطلوب")
    req["receipt"] = {"at": now_iso(), "by": actor,
                      "accepted": False, "reason": reason}
    if note:
        req["notes"]["on_receipt"] = note.strip()
    return transition(req, REJECTED, actor=actor,
                      branch=req["performing_branch"], detail={"reason": reason})


def mark_in_progress(req, *, actor):
    return transition(req, IN_PROGRESS, actor=actor, branch=req["performing_branch"])


def set_result(req, key: str, value, *, actor: str, note: str = "",
               components: Optional[Dict[str, Any]] = None,
               critical: bool = False):
    """
    نتيجة تحليل واحد.
    - القيم المركّبة (CBC) بتتحط في components={"HGB": 11.2, ...}
    - critical=True → الفني علّم إنها قيمة حرجة (اختيار يدوي، مفيش جدول thresholds)
    """
    entry = next((t for t in req["tests"] if t["key"] == key), None)
    if entry is None:
        raise ValueError(f"التحليل ده مش في الطلب: {key}")

    if entry["kind"] == catalog.KIND_COMPOSITE:
        payload = {"components": components or {}, "value": None}
    else:
        if value in (None, ""):
            raise ValueError(f"قيمة فاضية: {entry['name']}")
        payload = {"value": value, "components": None}

    prev = req["results"].get(key)
    payload.update({
        "unit": entry["unit"],
        "note": (note or "").strip(),
        "critical": bool(critical),
        "by": actor,
        "at": now_iso(),
        "revision": (prev or {}).get("revision", 0) + 1,
    })
    req["results"][key] = payload

    if prev is not None:
        # تعديل نتيجة سابقة = حدث لازم يتسجّل (ISO: amended report)
        _event(req, "RESULT_AMENDED", actor, req["performing_branch"],
               {"test": entry["name"], "from": prev.get("value"),
                "to": payload.get("value"), "revision": payload["revision"]})
    else:
        _event(req, "RESULT_SET", actor, req["performing_branch"],
               {"test": entry["name"]})

    if critical:
        req.setdefault("critical", []).append({
            "test": entry["name"], "value": value,
            "flagged_at": now_iso(), "flagged_by": actor,
            "read_back": None,
        })
    return req


def record_read_back(req, test_name: str, *, called_by: str,
                     received_by: str, note: str = ""):
    """توثيق الإبلاغ عن قيمة حرجة — مين اتصل ومين استلم وإمتى."""
    for c in req.get("critical", []):
        if c["test"] == test_name and c.get("read_back") is None:
            c["read_back"] = {"at": now_iso(), "called_by": called_by,
                              "received_by": received_by, "note": note}
            _event(req, "CRITICAL_READBACK", called_by, req["performing_branch"],
                   {"test": test_name, "received_by": received_by})
            return req
    raise ValueError(f"مفيش قيمة حرجة مفتوحة للتحليل: {test_name}")


def mark_resulted(req, *, actor, note=""):
    missing = [t["name"] for t in req["tests"] if t["key"] not in req["results"]]
    if missing:
        raise ValueError("تحاليل من غير نتيجة: " + "، ".join(missing))
    if note:
        req["notes"]["on_result"] = note.strip()
    return transition(req, RESULTED, actor=actor, branch=req["performing_branch"])


def mark_verified(req, *, actor):
    """اعتماد إكلينيكي — د. طارق."""
    open_crit = [c["test"] for c in req.get("critical", []) if c.get("read_back") is None]
    if open_crit:
        raise ValueError("في قيم حرجة لسه متبلّغتش: " + "، ".join(open_crit))
    return transition(req, VERIFIED, actor=actor, branch=req["performing_branch"])


def mark_closed(req, *, actor, transcribed_by=""):
    """الفرع الأصلي نقل النتيجة لنظامه — دي الحلقة اللي بتقفل."""
    return transition(req, CLOSED, actor=actor, branch=req["origin_branch"],
                      detail={"transcribed_by": transcribed_by or actor})


def mark_cancelled(req, *, actor, reason=""):
    return transition(req, CANCELLED, actor=actor,
                      branch=req["origin_branch"], detail={"reason": reason})


# ══════════════════════════════════════════════════════════════════════════
# TAT — بيتحسب من الـ events
#
# ⚠️ الإصدار الأول كان بياخد *أول* حدث لكل مرحلة. ده غلط لما يحصل إعادة
# تشغيل: طلب راح RESULTED ← IN_PROGRESS ← RESULTED ← VERIFIED كان بيحسب
# زمن الاعتماد من النتيجة *الأولى*، فيطلع 496 دقيقة بدل 5.
# دلوقتي كل مرحلة بتاخد الحدث الصح (أول ولا آخر)، وفي مقاييس منفصلة
# لإعادة التشغيل بدل ما تتخبّى جوة الأرقام.
# ══════════════════════════════════════════════════════════════════════════

def _event_times(req, action) -> List[datetime]:
    """كل مرات حصول الحدث ده، بالترتيب."""
    return [datetime.fromisoformat(e["at"])
            for e in req.get("events", []) if e["action"] == action]


def _event_time(req, action, which: str = "first") -> Optional[datetime]:
    ts = _event_times(req, action)
    if not ts:
        return None
    return ts[0] if which == "first" else ts[-1]


def rework(req) -> Dict[str, Any]:
    """
    إعادة التشغيل: كام مرة رجع الطلب للبنش بعد ما طلعت نتيجة.
    ده رقم إداري مهم — بيقول لك جودة الشغل من أول مرة.
    """
    in_prog = _event_times(req, f"→{IN_PROGRESS}")
    resulted = _event_times(req, f"→{RESULTED}")
    reruns = max(0, len(in_prog) - 1)
    lost = None
    if reruns and len(resulted) >= 2:
        lost = round((resulted[-1] - resulted[0]).total_seconds() / 60, 1)
    return {"reruns": reruns, "first_pass": reruns == 0,
            "rework_minutes": lost,
            "amendments": len([e for e in req.get("events", [])
                               if e["action"] == "RESULT_AMENDED"])}


def tat(req) -> Dict[str, Optional[float]]:
    """
    مدد بالدقايق. None = المرحلة لسه محصلتش.
    - transit / bench: من أول استلام (مرة واحدة بطبيعتها)
    - initial_result: أول نتيجة — قياس السرعة من أول مرة
    - bench: لحد آخر نتيجة — الزمن الفعلي على البنش شامل الإعادة
    - verify: من *آخر* نتيجة لآخر اعتماد — ده اللي كان مكسور
    """
    created = datetime.fromisoformat(req["created_at"])
    sent = _event_time(req, f"→{SENT}")
    recv = _event_time(req, f"→{RECEIVED}")
    res_first = _event_time(req, f"→{RESULTED}", "first")
    res_last = _event_time(req, f"→{RESULTED}", "last")
    ver_last = _event_time(req, f"→{VERIFIED}", "last")
    closed = _event_time(req, f"→{CLOSED}", "last")

    def dm(a, b):
        return round((b - a).total_seconds() / 60, 1) if a and b else None

    return {
        "create_to_send": dm(created, sent),
        "transit": dm(sent, recv),                  # زمن النقل بين الفروع
        "initial_result": dm(recv, res_first),      # أول نتيجة
        "bench": dm(recv, res_last),                # شامل الإعادة
        "verify": dm(res_last, ver_last),           # آخر نتيجة → الاعتماد
        "transcribe": dm(ver_last, closed),
        "total": dm(created, closed or ver_last),
    }


def delta_check(current, previous, threshold_pct: float = 50.0):
    """
    مقارنة بالنتيجة السابقة لنفس المريض ونفس التحليل.
    ملاحظة: مفيش reference ranges في النظام (بقرار) — ده مش بديل عنها،
    ده بس تنبيه إن القيمة اتغيرت بشكل كبير، للمراجعة قبل الاعتماد.
    """
    try:
        c, p = float(current), float(previous)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    pct = (c - p) / abs(p) * 100
    return {"pct": round(pct, 1), "flag": abs(pct) >= threshold_pct,
            "prev": p, "curr": c}


# ══════════════════════════════════════════════════════════════════════════
# مخرجات النقل (نسخ للشاشة)
# ══════════════════════════════════════════════════════════════════════════

def as_tsv(req) -> str:
    """
    TSV منسّق للّصق في نظام الفرع الأصلي صف بصف.
    الأعمدة: التحليل / القيمة / الوحدة / ملاحظة
    """
    lines = []
    for t in req["tests"]:
        r = req["results"].get(t["key"])
        if not r:
            continue
        if t["kind"] == catalog.KIND_COMPOSITE:
            for a in (catalog.get(t["code"]).components if t["code"] else ()):
                v = (r.get("components") or {}).get(a.code, "")
                if v != "":
                    lines.append(f"{a.name_en}\t{v}\t{a.unit}\t")
        else:
            lines.append(f"{t['name']}\t{r['value']}\t{t['unit']}\t{r.get('note','')}")
    return "\n".join(lines)


def summary_text(req) -> str:
    """ملخص نصي — للواتساب أو للعرض السريع."""
    p = req["patient"]
    b = catalog.BRANCH_NAMES
    head = (f"🔬 {req['id']}\n"
            f"{b[req['origin_branch']]['ar']} ← {b[req['performing_branch']]['ar']}\n"
            f"👤 {p['name']} | كود {p['lab_code']}"
            + (f" | {p['age']}" if p['age'] else "") + "\n"
            f"الحالة: {STATUS_COLOR.get(req['status'],'')} {STATUS_AR.get(req['status'], req['status'])}")
    body = []
    for t in req["tests"]:
        r = req["results"].get(t["key"])
        if not r:
            body.append(f"• {t['name']}: —")
            continue
        if t["kind"] == catalog.KIND_COMPOSITE:
            comps = r.get("components") or {}
            inner = "، ".join(f"{k} {v}" for k, v in comps.items() if v != "")
            body.append(f"• {t['name']}: {inner}")
        else:
            mark = " ⚠️" if r.get("critical") else ""
            body.append(f"• {t['name']}: {r['value']} {t['unit']}{mark}"
                        + (f" ({r['note']})" if r.get("note") else ""))
    tail = []
    for label, key in (("ملاحظة الطلب", "on_request"),
                       ("ملاحظة الاستلام", "on_receipt"),
                       ("ملاحظة النتيجة", "on_result")):
        v = req["notes"].get(key)
        if v:
            tail.append(f"📝 {label}: {v}")
    return "\n".join([head, "", *body] + ([""] + tail if tail else []))
