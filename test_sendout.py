# -*- coding: utf-8 -*-
"""
Orange Lab Send-Out — مجموعة اختبارات
أهم اختبار هنا هو test_concurrent_writes: بيثبت إن كتابة الفرعين
في نفس اللحظة على ملف اليوم مش بتضيّع بيانات.
"""

import os
import shutil
import tempfile
import threading
import traceback

import catalog
import schema
import store

PASS, FAIL = [], []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  ✅ {name}")
    except Exception as e:
        FAIL.append((name, e))
        print(f"  ❌ {name}\n     {type(e).__name__}: {e}")
        if os.environ.get("VERBOSE"):
            traceback.print_exc()


_DEFAULT_TESTS = [{"code": "ALT"}, {"code": "AST"}, {"code": "TBIL"}]


def sample(origin=catalog.DIAMOND, perf=catalog.LACITE, tests=None):
    # ملاحظة: لازم `is None` مش `or` — عشان tests=[] يوصل زي ما هو للاختبار
    tests = _DEFAULT_TESTS if tests is None else tests
    return schema.new_request(
        origin_branch=origin, performing_branch=perf,
        patient_name="محمد أحمد السيد", lab_code="D-24513",
        age="45Y", sex="M", phone="01001234567",
        complaint="ألم بالبطن + اصفرار",
        request_note="صايم 12 ساعة",
        tests=tests,
        tubes=[{"type": "Serum (Gel)", "count": 2}],
        created_by="reception_dmd",
    )


def full_cycle(req):
    schema.mark_sent(req, actor="rec1", courier="أحمد")
    schema.mark_received(req, actor="tech1")
    schema.mark_in_progress(req, actor="tech1")
    for t in req["tests"]:
        schema.set_result(req, t["key"], 42, actor="tech1")
    schema.mark_resulted(req, actor="tech1")
    schema.mark_verified(req, actor="dr_tarek")
    schema.mark_closed(req, actor="rec1")
    return req


# ══════════════════════════════════════════════════════════════════════════
print("\n[1] القاموس")


UNITLESS_OK = {"PH"}   # الـ pH نسبة لوغاريتمية — مالهاش وحدة أصلاً


def t_catalog_units():
    for c, t in catalog.TESTS.items():
        if (t.kind == catalog.KIND_NUMERIC and not t.unit
                and c not in UNITLESS_OK and not t.needs_review):
            raise AssertionError(f"{c} من غير وحدة")


def t_routes():
    lc = {t.code for t in catalog.tests_for_route(catalog.LACITE)}
    dm = {t.code for t in catalog.tests_for_route(catalog.DIAMOND)}
    assert {"ALT", "AST", "HBA1C", "FERR", "VITD"} <= lc, "ناقص في لاسيتيه"
    assert {"MG", "CKMB", "CBC", "LDH", "CPK", "RF_D"} <= dm, "ناقص في دياموند"
    assert not (lc & dm), f"تحليل في الاتنين: {lc & dm}"


def t_no_ref_ranges():
    """قرار تصميمي: مفيش ranges — ده اختبار بيمنع رجوعها بالغلط."""
    for t in catalog.TESTS.values():
        for bad in ("ref_range", "normal_low", "critical_high"):
            assert not hasattr(t, bad), f"{t.code} رجعت فيه {bad}"


def t_cbc_composite():
    t = catalog.get("CBC")
    assert t.kind == catalog.KIND_COMPOSITE
    assert len(t.components) == 15
    assert {a.code for a in t.components} >= {"HGB", "PLT", "WBC"}


def t_fmt():
    assert catalog.fmt("CREA", 1.2) == "1.20 mg/dL"
    assert catalog.fmt("NA", 139.4) == "139 mmol/L"
    assert catalog.fmt("ALT", 33) == "33 U/L"


check("كل تحليل رقمي ليه وحدة", t_catalog_units)
check("توزيع التحاليل على الفروع صح", t_routes)
check("مفيش reference ranges (بقرار)", t_no_ref_ranges)
check("CBC لوحة مركّبة بـ 15 مكوّن", t_cbc_composite)
check("تنسيق القيم بالخانات العشرية", t_fmt)

# ══════════════════════════════════════════════════════════════════════════
print("\n[2] بناء الطلب والتحقق")


def t_reject_same_branch():
    try:
        sample(origin=catalog.LACITE, perf=catalog.LACITE)
    except ValueError:
        return
    raise AssertionError("قبل نفس الفرع كمُرسِل ومُنفِّذ")


def t_reject_empty():
    for kw in ({"patient_name": ""}, {"lab_code": ""}):
        try:
            schema.new_request(origin_branch=catalog.DIAMOND,
                               performing_branch=catalog.LACITE,
                               patient_name=kw.get("patient_name", "س"),
                               lab_code=kw.get("lab_code", "X1"),
                               tests=[{"code": "ALT"}])
        except ValueError:
            continue
        raise AssertionError(f"قبل بيانات ناقصة: {kw}")


def t_reject_no_tests():
    try:
        sample(tests=[])
    except ValueError:
        return
    raise AssertionError("قبل طلب من غير تحاليل")


def t_reject_bad_code():
    try:
        sample(tests=[{"code": "NOPE"}])
    except ValueError:
        return
    raise AssertionError("قبل كود تحليل غلط")


def t_adhoc():
    r = sample(tests=[{"code": "ALT"},
                      {"custom_name": "Lipase", "custom_unit": "U/L"},
                      {"custom_name": ""}])          # الفاضية تتتجاهل
    assert len(r["tests"]) == 2
    x = r["tests"][1]
    assert x["custom"] and x["key"] == "X:LIPASE" and x["unit"] == "U/L"


def t_dedupe():
    r = sample(tests=[{"code": "ALT"}, {"code": "alt"}, {"code": "AST"}])
    assert len(r["tests"]) == 2, r["tests"]


def t_unique_ids():
    ids = {schema.new_request_id(catalog.DIAMOND) for _ in range(3000)}
    assert len(ids) == 3000, f"تكرار في الـ IDs: {3000 - len(ids)}"


def t_patient_key():
    a = schema.patient_key("محمد أحمد", "01001234567")
    b = schema.patient_key("محمد احمد مختلف", "0100 123 4567")
    assert a == b, "الموبايل المفروض يوحّد المفتاح"
    c = schema.patient_key("أحمد على", "")
    d = schema.patient_key("احمد على", "")
    assert c == d, "تطبيع الألف/الهمزة مشتغلش"


check("رفض نفس الفرع مُرسِل ومُنفِّذ", t_reject_same_branch)
check("رفض الاسم/الكود الفاضي", t_reject_empty)
check("رفض طلب من غير تحاليل", t_reject_no_tests)
check("رفض كود تحليل غير معروف", t_reject_bad_code)
check("تحاليل إضافية (ad-hoc) شغالة", t_adhoc)
check("منع تكرار نفس التحليل", t_dedupe)
check("3000 ID من غير تكرار", t_unique_ids)
check("مفتاح المريض ثابت عبر الزيارات", t_patient_key)

# ══════════════════════════════════════════════════════════════════════════
print("\n[3] الـ State Machine")


def t_happy_path():
    r = full_cycle(sample())
    assert r["status"] == schema.CLOSED
    acts = [e["action"] for e in r["events"]]
    for s in (schema.SENT, schema.RECEIVED, schema.IN_PROGRESS,
              schema.RESULTED, schema.VERIFIED, schema.CLOSED):
        assert f"→{s}" in acts, f"حدث ناقص: {s}"


def t_no_skip_receipt():
    """أهم اختبار: ممنوع القفز من الإرسال للنتيجة من غير استلام."""
    r = sample()
    schema.mark_sent(r, actor="rec1")
    try:
        schema.mark_in_progress(r, actor="tech1")
    except schema.TransitionError:
        return
    raise AssertionError("سمح بتخطي خطوة الاستلام!")


def t_no_result_before_received():
    r = sample()
    try:
        schema.mark_resulted(r, actor="t")
    except (schema.TransitionError, ValueError):
        return
    raise AssertionError("سمح بنتيجة قبل الاستلام")


def t_terminal_locked():
    r = full_cycle(sample())
    for target in (schema.SENT, schema.IN_PROGRESS, schema.VERIFIED):
        try:
            schema.transition(r, target, actor="x", branch=catalog.DIAMOND)
        except schema.TransitionError:
            continue
        raise AssertionError(f"طلب مقفول اتنقل لـ {target}")


def t_rejection():
    r = sample()
    schema.mark_sent(r, actor="rec1")
    schema.mark_rejected(r, actor="tech1", reason="عينة مُحلَّلة (Hemolyzed)",
                         note="اللون أحمر واضح")
    assert r["status"] == schema.REJECTED
    assert r["receipt"]["accepted"] is False
    assert r["notes"]["on_receipt"]
    try:
        schema.mark_received(r, actor="tech1")
    except schema.TransitionError:
        return
    raise AssertionError("طلب مرفوض اتقبل بعدين")


def t_rejection_needs_reason():
    r = sample()
    schema.mark_sent(r, actor="rec1")
    try:
        schema.mark_rejected(r, actor="t", reason="")
    except ValueError:
        return
    raise AssertionError("رفض من غير سبب")


def t_incomplete_results_blocked():
    r = sample()
    schema.mark_sent(r, actor="r")
    schema.mark_received(r, actor="t")
    schema.mark_in_progress(r, actor="t")
    schema.set_result(r, "ALT", 55, actor="t")
    try:
        schema.mark_resulted(r, actor="t")
    except ValueError as e:
        assert "AST" in str(e)
        return
    raise AssertionError("قبل نتيجة ناقصة")


def t_amend_logged():
    r = sample(tests=[{"code": "ALT"}])
    schema.mark_sent(r, actor="r"); schema.mark_received(r, actor="t")
    schema.mark_in_progress(r, actor="t")
    schema.set_result(r, "ALT", 55, actor="t")
    schema.set_result(r, "ALT", 88, actor="t2", note="أُعيد التحليل")
    assert r["results"]["ALT"]["revision"] == 2
    ev = [e for e in r["events"] if e["action"] == "RESULT_AMENDED"]
    assert len(ev) == 1 and ev[0]["detail"]["from"] == 55


check("الدورة الكاملة بتوصل CLOSED", t_happy_path)
check("⛔ ممنوع تخطي خطوة الاستلام", t_no_skip_receipt)
check("ممنوع نتيجة قبل الاستلام", t_no_result_before_received)
check("الطلب المقفول مبيتحركش", t_terminal_locked)
check("رفض العينة بيقفل المسار", t_rejection)
check("الرفض لازم يكون بسبب", t_rejection_needs_reason)
check("منع الاعتماد بنتايج ناقصة", t_incomplete_results_blocked)
check("تعديل نتيجة بيتسجّل كحدث", t_amend_logged)

# ══════════════════════════════════════════════════════════════════════════
print("\n[4] القيم الحرجة")


def t_critical_blocks_verify():
    r = sample(tests=[{"code": "K"}])
    schema.mark_sent(r, actor="r"); schema.mark_received(r, actor="t")
    schema.mark_in_progress(r, actor="t")
    schema.set_result(r, "K", 7.1, actor="t", critical=True,
                      note="أُعيد على عينة تانية")
    schema.mark_resulted(r, actor="t")
    try:
        schema.mark_verified(r, actor="dr_tarek")
    except ValueError:
        pass
    else:
        raise AssertionError("اعتمد وفي قيمة حرجة متبلّغتش")
    schema.record_read_back(r, "Potassium (K⁺)", called_by="tech1",
                            received_by="د. طارق")
    schema.mark_verified(r, actor="dr_tarek")
    assert r["status"] == schema.VERIFIED
    assert r["critical"][0]["read_back"]["received_by"] == "د. طارق"


check("قيمة حرجة بتمنع الاعتماد لحد الـ read-back", t_critical_blocks_verify)

# ══════════════════════════════════════════════════════════════════════════
print("\n[5] المخرجات")


def t_tsv():
    r = sample(tests=[{"code": "ALT"}, {"code": "NA"}])
    schema.mark_sent(r, actor="r"); schema.mark_received(r, actor="t")
    schema.mark_in_progress(r, actor="t")
    schema.set_result(r, "ALT", 55, actor="t")
    schema.set_result(r, "NA", 139, actor="t", note="عينة ليباميه")
    rows = schema.as_tsv(r).split("\n")
    assert len(rows) == 2
    assert rows[0].split("\t") == ["ALT (SGPT)", "55", "U/L", ""]
    assert rows[1].split("\t")[3] == "عينة ليباميه"


def t_tsv_cbc():
    r = sample(origin=catalog.LACITE, perf=catalog.DIAMOND,
               tests=[{"code": "CBC"}])
    schema.mark_sent(r, actor="r"); schema.mark_received(r, actor="t")
    schema.mark_in_progress(r, actor="t")
    schema.set_result(r, "CBC", None, actor="t",
                      components={"HGB": 11.2, "PLT": 250, "WBC": 6.8})
    rows = schema.as_tsv(r).split("\n")
    assert len(rows) == 3
    assert rows.__contains__("Hemoglobin\t11.2\tg/dL\t")


def t_summary_has_notes():
    r = sample()
    s = schema.summary_text(r)
    assert "صايم 12 ساعة" in s and r["id"] in s and "دياموند" in s


check("TSV جاهز للّصق", t_tsv)
check("TSV بيفكّ الـ CBC لمكوناته", t_tsv_cbc)
check("الملخص بيشمل الملاحظات", t_summary_has_notes)

# ══════════════════════════════════════════════════════════════════════════
print("\n[6] TAT")


def t_tat():
    r = full_cycle(sample())
    t = schema.tat(r)
    for k in ("transit", "bench", "total"):
        assert t[k] is not None and t[k] >= 0, f"{k} = {t[k]}"


def t_tat_partial():
    r = sample()
    schema.mark_sent(r, actor="r")
    t = schema.tat(r)
    assert t["create_to_send"] is not None
    assert t["transit"] is None and t["bench"] is None


check("TAT بيتحسب من الأحداث", t_tat)
check("TAT بيرجّع None للمراحل اللي محصلتش", t_tat_partial)

# ══════════════════════════════════════════════════════════════════════════
print("\n[7] التخزين — ملف لكل يوم")

TMP = tempfile.mkdtemp()


def t_roundtrip():
    st = store.Store(store.LocalBackend(TMP))
    r = sample()
    st.create(r)
    got = st.get(r["day"], r["id"])
    assert got and got["patient"]["name"] == "محمد أحمد السيد"
    assert got["notes"]["on_request"] == "صايم 12 ساعة"


def t_no_duplicate_id():
    st = store.Store(store.LocalBackend(TMP))
    r = sample()
    st.create(r)
    try:
        st.create(r)
    except store.StoreError:
        return
    raise AssertionError("سمح بـ ID مكرر")


def t_update_returns_saved():
    st = store.Store(store.LocalBackend(TMP))
    r = sample()
    st.create(r)
    saved = st.update(r["day"], r["id"],
                      lambda x: schema.mark_sent(x, actor="rec1", courier="علي"))
    assert saved["status"] == schema.SENT
    assert st.get(r["day"], r["id"])["transport"]["courier"] == "علي"


def t_find_by_id():
    st = store.Store(store.LocalBackend(TMP))
    r = sample()
    st.create(r)
    assert st.find(r["id"])["id"] == r["id"]
    assert st.find("SND-DMD-20200101-000000-XXXX") is None


def t_open_requests():
    root = tempfile.mkdtemp()
    st = store.Store(store.LocalBackend(root))
    a, b = sample(), sample()
    st.create(a); st.create(b)
    st.update(b["day"], b["id"], full_cycle)          # b بقى CLOSED
    op = st.open_requests(catalog.LACITE)
    ids = {x["id"] for x in op}
    assert a["id"] in ids and b["id"] not in ids
    shutil.rmtree(root)


def t_delta():
    root = tempfile.mkdtemp()
    st = store.Store(store.LocalBackend(root))
    old = sample(tests=[{"code": "CREA"}])
    st.create(old)
    st.update(old["day"], old["id"], lambda r: full_cycle(r))
    new = sample(tests=[{"code": "CREA"}])
    prev, when = st.previous_value(new["patient"]["key"], "CREA",
                                   exclude_id=new["id"])
    assert prev == 42, prev
    d = schema.delta_check(90, prev)
    assert d["flag"] is True and d["pct"] > 100
    assert schema.delta_check(45, prev)["flag"] is False
    shutil.rmtree(root)


check("حفظ واسترجاع بالعربي", t_roundtrip)
check("منع تكرار الـ ID", t_no_duplicate_id)
check("update بترجّع النسخة المحفوظة", t_update_returns_saved)
check("البحث بالـ ID", t_find_by_id)
check("قائمة الطلبات المفتوحة", t_open_requests)
check("delta check بالنتيجة السابقة", t_delta)

# ══════════════════════════════════════════════════════════════════════════
print("\n[8] ⚠️ التزامن — الفرعين بيكتبوا في نفس الوقت")


class FlakyBackend(store.LocalBackend):
    """بيرمي ConflictError في أول محاولتين لكل كتابة — محاكاة 409 من GitHub."""

    def __init__(self, root):
        super().__init__(root)
        self.fails = {}

    def write(self, day, data, sha):
        n = self.fails.get(day, 0)
        if n < 2:
            self.fails[day] = n + 1
            raise store.ConflictError("محاكاة 409")
        return super().write(day, data, sha)


def t_retry_on_conflict():
    root = tempfile.mkdtemp()
    st = store.Store(FlakyBackend(root))
    r = sample()
    st.create(r)                       # لازم ينجح بعد إعادة المحاولة
    assert st.get(r["day"], r["id"]) is not None
    shutil.rmtree(root)


def t_concurrent_no_data_loss():
    """
    ⚠️ ده الاختبار اللي بيبرر قرار 'ملف لكل يوم'.
    20 thread بيكتبوا في نفس ملف اليوم. لو الـ mutate مش سليم،
    هنلاقي طلبات ضاعت.
    """
    root = tempfile.mkdtemp()
    st = store.Store(store.LocalBackend(root))
    made, errs = [], []

    def worker(i):
        try:
            branch = catalog.DIAMOND if i % 2 == 0 else catalog.LACITE
            r = schema.new_request(
                origin_branch=branch,
                performing_branch=catalog.other_branch(branch),
                patient_name=f"مريض {i}", lab_code=f"C-{i:04d}",
                tests=[{"code": "ALT" if branch == catalog.DIAMOND else "MG"}])
            st.create(r)
            made.append(r["id"])
        except Exception as e:
            errs.append(e)

    ths = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in ths: t.start()
    for t in ths: t.join()

    assert not errs, f"أخطاء: {errs[:3]}"
    day = schema.today_key()
    stored = {r["id"] for r in st.list_day(day)}
    lost = set(made) - stored
    assert not lost, f"ضاع {len(lost)} طلب من {len(made)}!"
    assert len(stored) == 20, f"المتوقع 20، الموجود {len(stored)}"
    shutil.rmtree(root)


def t_concurrent_updates_same_request():
    """الفرعين بيعدّلوا طلبات مختلفة في نفس الملف في نفس اللحظة."""
    root = tempfile.mkdtemp()
    st = store.Store(store.LocalBackend(root))
    reqs = []
    for i in range(10):
        r = sample(tests=[{"code": "ALT"}])
        r["patient"]["lab_code"] = f"C-{i}"
        st.create(r)
        reqs.append(r)

    errs = []

    def worker(r):
        try:
            st.update(r["day"], r["id"], lambda x: schema.mark_sent(x, actor="r"))
            st.update(r["day"], r["id"], lambda x: schema.mark_received(x, actor="t"))
        except Exception as e:
            errs.append(e)

    ths = [threading.Thread(target=worker, args=(r,)) for r in reqs]
    for t in ths: t.start()
    for t in ths: t.join()

    assert not errs, f"أخطاء: {errs[:3]}"
    day = schema.today_key()
    for r in st.list_day(day):
        assert r["status"] == schema.RECEIVED, f"{r['id']} = {r['status']}"
    shutil.rmtree(root)


check("إعادة المحاولة عند التعارض 409", t_retry_on_conflict)
check("⚠️ 20 كتابة متزامنة — صفر فقدان بيانات", t_concurrent_no_data_loss)
check("تعديلات متزامنة على نفس الملف", t_concurrent_updates_same_request)

shutil.rmtree(TMP, ignore_errors=True)

# ══════════════════════════════════════════════════════════════════════════
print("\n[9] التحاليل الجديدة + الثبات")

from datetime import datetime, timedelta, timezone as _tz


def aged(hours, tests):
    """طلب متسحوب من كذا ساعة — لاختبار الثبات."""
    r = sample(tests=tests)
    r["collected_at"] = (datetime.now(_tz.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    return r


def t_new_tests_exist():
    lc = {t.code for t in catalog.tests_for_route(catalog.LACITE)}
    assert {"FBG", "PP2", "RBG", "PT", "PTT"} <= lc, "التحاليل الجديدة ناقصة"


def t_coag_matches_coatron():
    """مخرجات الـ Coatron: PT / PC / INR / PTT — بالترتيب ده بالظبط."""
    pt, ptt = catalog.get("PT"), catalog.get("PTT")
    assert pt.kind == catalog.KIND_COMPOSITE
    assert [a.code for a in pt.components] == ["PT_SEC", "PC", "INR"], \
        [a.code for a in pt.components]
    assert [a.unit for a in pt.components] == ["sec", "%", ""]
    # الـ PTT قيمة واحدة → تحليل رقمي بسيط مش لوحة
    assert ptt.kind == catalog.KIND_NUMERIC and ptt.unit == "sec"
    assert pt.tube == catalog.TUBE_CITRATE == ptt.tube
    assert catalog.DEVICE_NAMES[catalog.DEV_COAG] == "Coatron"


def t_tubes_auto():
    # ملحوظة: مش بنستخدم sample() هنا لإنها بتمرر tubes يدوية،
    # والتمرير اليدوي بيتخطى الاشتقاق التلقائي (وده السلوك الصح)
    r = schema.new_request(
        origin_branch=catalog.DIAMOND, performing_branch=catalog.LACITE,
        patient_name="اختبار", lab_code="T-1",
        tests=[{"code": "ALT"}, {"code": "PT"}, {"code": "FBG"}])
    types = {t["type"] for t in r["tubes"]}
    # الجلوكوز بقى سيرم → أنبوبتين بس مش تلاتة
    assert types == {catalog.TUBE_SERUM, catalog.TUBE_CITRATE}, types
    # وكل أنبوبة بتقول التحاليل بتاعتها
    cit = next(t for t in r["tubes"] if t["type"] == catalog.TUBE_CITRATE)
    assert "PT / PC / INR" in cit["for"]

    # التمرير اليدوي بيفضل مسيطر
    r2 = sample(tests=[{"code": "PT"}])
    assert r2["tubes"] == [{"type": "Serum (Gel)", "count": 2}]


def t_stability_ok():
    r = aged(1, [{"code": "PTT"}])
    assert stab_levels(r) == set()


def stab_levels(r):
    return {i["level"] for i in schema.stability_check(r)}


def t_stability_warns():
    r = aged(3.5, [{"code": "PTT"}])          # حد 4 ساعات → 87%
    assert "warning" in stab_levels(r)


def t_stability_expired_blocks_receipt():
    """⚠️ أهم اختبار جديد: aPTT عدّى 4 ساعات → الاستلام يتمنع."""
    r = aged(5, [{"code": "PTT"}])
    schema.mark_sent(r, actor="rec")
    try:
        schema.mark_received(r, actor="tech")
    except schema.StabilityError as e:
        assert "PTT" in str(e), str(e)
        return
    raise AssertionError("استلم عينة aPTT خلص وقتها!")


def t_stability_override_logged():
    r = aged(5, [{"code": "PTT"}])
    schema.mark_sent(r, actor="rec")
    schema.mark_received(r, actor="tech", override_stability=True,
                         note="اتصلنا بالطبيب ووافق")
    assert r["status"] == schema.RECEIVED
    assert r["receipt"]["stability_override"] is True
    ev = [e for e in r["events"] if e["action"] == "STABILITY_OVERRIDE"]
    assert len(ev) == 1 and ev[0]["actor"] == "tech"


def t_pt_more_tolerant():
    """PT ثباته 24 ساعة — 5 ساعات مش مشكلة، عكس aPTT."""
    r = aged(5, [{"code": "PT"}])
    schema.mark_sent(r, actor="rec")
    schema.mark_received(r, actor="tech")     # لازم يعدي
    assert r["status"] == schema.RECEIVED


def t_glucose_serum():
    """قرار حسين: سيرم عادي مش NaF."""
    for c in ("FBG", "PP2", "RBG"):
        t = catalog.get(c)
        assert t.tube == catalog.TUBE_SERUM, f"{c} = {t.tube}"
        assert t.stability_hours == catalog.GLUCOSE_STABILITY_HOURS
        assert t.stability_approved_by, f"{c} مفيش مين اعتمدها"


def t_fasting_warning():
    r = sample(tests=[{"code": "FBG"}])
    r["clinical"]["fasting"] = None
    w = schema.preanalytical_warnings(r)
    assert any("صيام" in x for x in w), w
    r["clinical"]["fasting"] = True
    assert not any("صيام" in x for x in schema.preanalytical_warnings(r))


def t_multi_tube_warning():
    r = sample(tests=[{"code": "ALT"}, {"code": "PTT"}])
    w = schema.preanalytical_warnings(r)
    assert any("أنابيب مختلفة" in x for x in w), w
    assert any("4 ساعة" in x or "4 ساع" in x for x in w), w


def t_transit_recorded():
    r = aged(2, [{"code": "ALT"}])
    schema.mark_sent(r, actor="rec")
    schema.mark_received(r, actor="tech")
    assert 1.9 <= r["receipt"]["hours_in_transit"] <= 2.1


def t_coag_tsv():
    r = sample(tests=[{"code": "PT"}])
    schema.mark_sent(r, actor="r"); schema.mark_received(r, actor="t")
    schema.mark_in_progress(r, actor="t")
    schema.set_result(r, "PT", None, actor="t",
                      components={"PT_SEC": 13.4, "PC": 92, "INR": 1.05})
    rows = schema.as_tsv(r).split("\n")
    assert len(rows) == 3, rows
    assert [x.split("\t")[0] for x in rows] == ["PT", "PC", "INR"]
    assert rows[1].split("\t")[1:3] == ["92", "%"]


check("التحاليل الخمسة الجديدة موجودة", t_new_tests_exist)
check("PT/PC/INR/PTT مطابقين للـ Coatron", t_coag_matches_coatron)
check("الأنابيب بتتحدد أوتوماتيك", t_tubes_auto)
check("عينة طازة = مفيش تحذير", t_stability_ok)
check("تحذير عند 75% من مدة الثبات", t_stability_warns)
check("⚠️ aPTT بعد 5 ساعات — الاستلام يتمنع", t_stability_expired_blocks_receipt)
check("التجاوز مسموح بس بيتسجّل باسم الفني", t_stability_override_logged)
check("PT (24س) بيعدي عادي بعد 5 ساعات", t_pt_more_tolerant)
check("تحاليل السكر على سيرم عادي", t_glucose_serum)
check("تحذير الصيام لـ FBG", t_fasting_warning)
check("تحذير تعدد الأنابيب", t_multi_tube_warning)
check("زمن النقل بيتسجّل عند الاستلام", t_transit_recorded)
def t_no_pending_reviews():
    """كل القرارات اتاخدت — مفيش تحليل معلّق."""
    assert catalog.review_queue() == [], \
        [t.code for t in catalog.review_queue()]


def t_decisions_applied():
    assert catalog.get("CKMB").unit == "U/L"
    assert catalog.get("PH").name_en == "pH"
    assert catalog.get("PH").unit == ""


def t_ptt_single_value():
    """الـ PTT قيمة واحدة — بيتدخّل زي أي تحليل رقمي."""
    r = sample(tests=[{"code": "PTT"}])
    schema.mark_sent(r, actor="r"); schema.mark_received(r, actor="t")
    schema.mark_in_progress(r, actor="t")
    schema.set_result(r, "PTT", 31.2, actor="t")
    assert schema.as_tsv(r) == "PTT\t31.2\tsec\t"


check("TSV بيطلّع PT/PC/INR بالترتيب", t_coag_tsv)
check("PTT قيمة واحدة", t_ptt_single_value)
check("قرارات حسين اتطبّقت", t_decisions_applied)
check("مفيش تحاليل معلّقة", t_no_pending_reviews)

# ══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 62)
print(f"نجح: {len(PASS)}   |   فشل: {len(FAIL)}")
if FAIL:
    print("\nالفاشل:")
    for n, e in FAIL:
        print(f"  • {n}: {e}")
else:
    print("✅ كل الاختبارات نجحت")

rq = catalog.review_queue()
if rq:
    print(f"\n⚠️  محتاج مراجعة د. طارق ({len(rq)}):")
    for t in rq:
        print(f"  • {t.code} — {t.note}")
print("═" * 62)

# ══════════════════════════════════════════════════════════════════════════
print("\n[10] الألوان واللوحات")


def t_status_visuals():
    """كل حالة ليها لون وأيقونة وخطوة تالية — مفيش حالة ناقصة."""
    all_st = {schema.DRAFT, schema.SENT, schema.RECEIVED, schema.REJECTED,
              schema.IN_PROGRESS, schema.RESULTED, schema.VERIFIED,
              schema.CLOSED, schema.CANCELLED}
    for name, d in (("STATUS_AR", schema.STATUS_AR),
                    ("STATUS_COLOR", schema.STATUS_COLOR),
                    ("STATUS_HEX", schema.STATUS_HEX),
                    ("NEXT_STEP", schema.NEXT_STEP)):
        assert set(d) == all_st, f"{name} ناقص: {all_st - set(d)}"


def t_colors_distinct():
    """الألوان مختلفة — عشان الحالة تتعرف من اللون من غير قراية."""
    fgs = [v[0] for v in schema.STATUS_HEX.values()]
    dupes = {c for c in fgs if fgs.count(c) > 1}
    assert not dupes, f"ألوان مكررة: {dupes}"
    for s, (fg, bg) in schema.STATUS_HEX.items():
        assert fg.startswith("#") and len(fg) == 7, f"{s}: {fg}"
        assert bg.startswith("#") and len(bg) == 7, f"{s}: {bg}"


def t_panels_valid():
    """كل كود في اللوحات لازم يكون تحليل موجود فعلاً."""
    for pname, codes in catalog.PANELS.items():
        assert codes, f"{pname} فاضية"
        for c in codes:
            assert catalog.get(c), f"{pname}: كود مش موجود {c}"


def t_panels_single_branch():
    """اللوحة الواحدة كل تحاليلها في نفس الفرع — عشان ماتبعتش لفرعين."""
    for pname, codes in catalog.PANELS.items():
        branches = {catalog.get(c).performed_at for c in codes}
        assert len(branches) == 1, f"{pname} متوزّعة على فروع: {branches}"


def t_both_branches_have_panels():
    for b in (catalog.LACITE, catalog.DIAMOND):
        assert catalog.panels_for_route(b), f"{b} من غير لوحات"


def t_panel_expands():
    liver = catalog.PANELS["🫀 وظائف كبد"]
    r = schema.new_request(origin_branch=catalog.DIAMOND,
                           performing_branch=catalog.LACITE,
                           patient_name="ت", lab_code="1",
                           tests=[{"code": c} for c in liver])
    assert len(r["tests"]) == len(liver) == 8


check("كل حالة ليها لون وأيقونة وخطوة", t_status_visuals)
check("ألوان الحالات كلها مختلفة", t_colors_distinct)
check("أكواد اللوحات كلها صحيحة", t_panels_valid)
check("كل لوحة في فرع واحد", t_panels_single_branch)
check("الفرعين عندهم لوحات", t_both_branches_have_panels)
check("اللوحة بتتفرد لتحاليلها", t_panel_expands)


# ══════════════════════════════════════════════════════════════════════════
print("\n[11] ترتيب التحاليل")

# ترتيب حسين الأصلي — الاختبار ده بيقفله عشان مايترجعش أبجدي بالغلط
HUSSEIN_ORDER = [
    "TBIL", "DBIL", "ALT", "AST", "ALP", "GGT", "TP", "ALB", "UREA", "CREA",
    "URIC", "NA", "K", "CA", "CAION", "PH", "CL", "PO4", "CHOL", "TRIG",
    "HDL", "LDL", "ASO", "CRP_B", "VITD",
    "FBG", "PP2", "PT", "PTT", "RBG",
    "HBA1C", "CRP_H", "RF_H", "FERR",
]
DIAMOND_ORDER = ["MG", "CKMB", "CBC", "LDH", "RF_D", "CPK"]


def t_lacite_order():
    got = [t.code for t in catalog.tests_for_route(catalog.LACITE)]
    assert got == HUSSEIN_ORDER, f"\nالمتوقع: {HUSSEIN_ORDER}\nالفعلي:  {got}"


def t_diamond_order():
    got = [t.code for t in catalog.tests_for_route(catalog.DIAMOND)]
    assert got == DIAMOND_ORDER, got


def t_not_alphabetical():
    """لو رجع أبجدي، Direct هيسبق Total و 2h-PP هيقفز للأول."""
    got = [t.name_en for t in catalog.tests_for_route(catalog.LACITE)]
    assert got != sorted(got), "الترتيب رجع أبجدي!"
    assert got.index("Bilirubin, Total") < got.index("Bilirubin, Direct")
    assert got.index("ALT (SGPT)") < got.index("2h Post-Prandial Glucose")


def t_adjacency():
    """الأزواج اللي بتتقرا مع بعض لازم تفضل ملزوقة."""
    o = [t.code for t in catalog.tests_for_route(catalog.LACITE)]
    for a, b_ in [("TBIL", "DBIL"), ("ALT", "AST"), ("CA", "CAION"),
                  ("NA", "K"), ("CHOL", "TRIG"), ("HDL", "LDL"), ("PT", "PTT")]:
        assert o.index(b_) - o.index(a) == 1, f"{a} و {b_} اتفرقوا"


def t_order_index_complete():
    assert set(catalog.ORDER_INDEX) == set(catalog.TESTS)
    assert catalog.ORDER_INDEX["TBIL"] == 0


check("ترتيب لاسيتيه مطابق لترتيب حسين", t_lacite_order)
check("ترتيب دياموند مطابق", t_diamond_order)
check("⚠️ الترتيب مش أبجدي", t_not_alphabetical)
check("الأزواج المترابطة جنب بعض", t_adjacency)
check("ORDER_INDEX كامل", t_order_index_complete)


def t_request_uses_catalog_order():
    """مهما كان ترتيب الضغط، الشيت بيطلع بترتيب القاموس."""
    r = schema.new_request(
        origin_branch=catalog.DIAMOND, performing_branch=catalog.LACITE,
        patient_name="ت", lab_code="1",
        tests=[{"code": c} for c in ["AST", "TBIL", "PT", "ALT", "DBIL"]])
    assert [t["code"] for t in r["tests"]] == ["TBIL", "DBIL", "ALT", "AST", "PT"]


def t_adhoc_goes_last():
    r = schema.new_request(
        origin_branch=catalog.DIAMOND, performing_branch=catalog.LACITE,
        patient_name="ت", lab_code="1",
        tests=[{"custom_name": "Lipase"}, {"code": "AST"}, {"code": "TBIL"}])
    codes = [t["code"] or t["name"] for t in r["tests"]]
    assert codes == ["TBIL", "AST", "Lipase"], codes


check("الطلب بيترتّب بترتيب القاموس مش الضغط", t_request_uses_catalog_order)
check("التحاليل الإضافية بتروح الآخر", t_adhoc_goes_last)


# ══════════════════════════════════════════════════════════════════════════
print("\n[12] TAT مع إعادة التشغيل")

from datetime import datetime as _dt, timedelta as _td, timezone as _tzz

_BASE = _dt(2026, 8, 13, 8, 0, tzinfo=_tzz.utc)


def _stamp(r, mins):
    """توقيتات ثابتة عشان الاختبار يبقى قاطع مش تقريبي."""
    r["created_at"] = _BASE.isoformat(timespec="seconds")
    assert len(mins) == len(r["events"]), f"{len(mins)} != {len(r['events'])}"
    for e, m in zip(r["events"], mins):
        e["at"] = (_BASE + _td(minutes=m)).isoformat(timespec="seconds")


def _run(rework=False):
    r = sample(tests=[{"code": "ALT"}])
    schema.mark_sent(r, actor="a"); schema.mark_received(r, actor="b")
    schema.mark_in_progress(r, actor="b")
    schema.set_result(r, "ALT", 50, actor="b"); schema.mark_resulted(r, actor="b")
    if rework:
        schema.transition(r, schema.IN_PROGRESS, actor="dr", branch=catalog.LACITE)
        schema.set_result(r, "ALT", 88, actor="b")
        schema.mark_resulted(r, actor="b")
    schema.mark_verified(r, actor="dr"); schema.mark_closed(r, actor="a")
    return r


def t_tat_clean_run():
    r = _run()
    _stamp(r, [5, 20, 25, 60, 65, 70, 75])
    t, w = schema.tat(r), schema.rework(r)
    assert (t["transit"], t["bench"], t["verify"], t["total"]) == (15, 45, 5, 75), t
    assert w["first_pass"] and w["reruns"] == 0


def t_tat_rework_verify_correct():
    """⚠️ الباج الأصلي: زمن الاعتماد كان بيتحسب من *أول* نتيجة."""
    r = _run(rework=True)
    #    SENT RECV INPR SET RESULTED  INPR AMEND RESULTED VERIF CLOSED
    _stamp(r, [5,  20,  25,  60, 65,      90,  95,   150,     155,  160])
    t = schema.tat(r)
    assert t["verify"] == 5, f"verify={t['verify']} — الباج رجع!"
    assert t["initial_result"] == 45      # أول نتيجة: 20 → 65
    assert t["bench"] == 130              # آخر نتيجة: 20 → 150
    assert t["transit"] == 15


def t_rework_metrics():
    r = _run(rework=True)
    _stamp(r, [5, 20, 25, 60, 65, 90, 95, 150, 155, 160])
    w = schema.rework(r)
    assert w["reruns"] == 1 and w["first_pass"] is False
    assert w["rework_minutes"] == 85      # 65 → 150
    assert w["amendments"] == 1


def t_rework_hidden_before():
    """الفرق بين الحالتين لازم يبان في الأرقام، مش يتخبّى."""
    a, b_ = _run(), _run(rework=True)
    _stamp(a, [5, 20, 25, 60, 65, 70, 75])
    _stamp(b_, [5, 20, 25, 60, 65, 90, 95, 150, 155, 160])
    assert schema.tat(a)["verify"] == schema.tat(b_)["verify"] == 5
    assert schema.tat(b_)["bench"] > schema.tat(a)["bench"]
    assert schema.rework(a)["reruns"] < schema.rework(b_)["reruns"]


def t_tat_partial_still_none():
    r = sample()
    schema.mark_sent(r, actor="r")
    t = schema.tat(r)
    assert t["create_to_send"] is not None
    assert t["transit"] is None and t["bench"] is None and t["verify"] is None


check("TAT سليم من غير إعادة", t_tat_clean_run)
check("⚠️ زمن الاعتماد صح بعد الإعادة (كان 496 بدل 5)", t_tat_rework_verify_correct)
check("مقاييس إعادة التشغيل", t_rework_metrics)
check("الإعادة بتبان في الأرقام مش بتتخبّى", t_rework_hidden_before)
check("المراحل اللي محصلتش لسه None", t_tat_partial_still_none)


# ══════════════════════════════════════════════════════════════════════════
print("\n[13] الثبات: مفيش افتراض ضمني")


def t_default_is_none():
    """⚠️ الافتراضي كان 8.0 — رقم مخترع كان بيمنع 31 تحليل بثقة كاذبة."""
    d = catalog.TestDef.__dataclass_fields__["stability_hours"].default
    assert d is None, f"الافتراضي رجع {d} — الافتراض الضمني رجع!"


def t_approved_have_owner():
    """أي مدة ثبات معتمدة لازم يكون معاها مين اعتمدها."""
    for t in catalog.TESTS.values():
        if t.stability_hours is not None:
            assert t.stability_approved_by, f"{t.code}: مدة من غير اعتماد"
            assert t.stability_hours > 0


def t_none_means_no_enforcement():
    """تحليل من غير مدة معتمدة مايتمنعش مهما طال النقل."""
    alt = catalog.get("ALT")
    assert alt.stability_hours is None
    r = sample(tests=[{"code": "ALT"}])
    r["collected_at"] = (_dt.now(_tzz.utc) - _td(hours=48)).isoformat(timespec="seconds")
    assert schema.stability_check(r) == []
    schema.mark_sent(r, actor="a")
    schema.mark_received(r, actor="b")        # لازم يعدّي
    assert r["status"] == schema.RECEIVED


def t_approved_still_enforced():
    """اللي ليه مدة معتمدة لسه بيتمنع — الحماية ماضاعتش."""
    r = sample(tests=[{"code": "PTT"}])
    r["collected_at"] = (_dt.now(_tzz.utc) - _td(hours=6)).isoformat(timespec="seconds")
    schema.mark_sent(r, actor="a")
    try:
        schema.mark_received(r, actor="b")
    except schema.StabilityError:
        return
    raise AssertionError("PTT عدّى رغم انتهاء مدته المعتمدة")


def t_mixed_request():
    """طلب فيه معتمد وغير معتمد: المنع على المعتمد بس."""
    r = sample(tests=[{"code": "PTT"}, {"code": "ALT"}, {"code": "GGT"}])
    r["collected_at"] = (_dt.now(_tzz.utc) - _td(hours=6)).isoformat(timespec="seconds")
    names = [i["test"] for i in schema.stability_check(r)]
    assert names == ["PTT"], names


def t_gap_is_visible():
    """الفجوة لازم تظهر للمستخدم مش تتخبّى."""
    r = sample(tests=[{"code": "ALT"}, {"code": "GGT"}])
    w = schema.preanalytical_warnings(r)
    assert any("مدة ثبات معتمدة" in x for x in w), w
    assert len(catalog.pending_stability()) > 0
    assert catalog.unvalidated(["ALT", "PTT"]) == ["ALT (SGPT)"]


def t_tightest_ignores_none():
    tight = catalog.tightest_stability(["ALT", "PTT", "GGT"])
    assert tight and tight[1] == "PTT" and tight[0] == 4


check("⚠️ الافتراضي = None مش 8 ساعات", t_default_is_none)
check("كل مدة معتمدة معاها مين اعتمدها", t_approved_have_owner)
check("غير معتمد = مفيش منع", t_none_means_no_enforcement)
check("المعتمد لسه بيتمنع", t_approved_still_enforced)
check("طلب مختلط: المنع على المعتمد بس", t_mixed_request)
check("الفجوة ظاهرة للمستخدم", t_gap_is_visible)
check("أقصر مدة بتتجاهل غير المعتمد", t_tightest_ignores_none)

print("\n" + "═" * 62)
print(f"الإجمالي النهائي — نجح: {len(PASS)} | فشل: {len(FAIL)}")
print("═" * 62)
