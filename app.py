# -*- coding: utf-8 -*-
"""
Orange Lab — نظام تبادل العينات بين الفروع
app.py — ⭐ ده الملف الرئيسي اللي بيتعمله deploy على Streamlit

التشغيل:  streamlit run app.py
"""

import hashlib
import hmac
import urllib.parse
from datetime import datetime

import streamlit as st

import catalog
import schema
import store

# ══════════════════════════════════════════════════════════════════════════
# الإعداد
# ══════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Orange Lab — تبادل العينات",
                   page_icon="🔬", layout="wide",
                   initial_sidebar_state="collapsed")

BRAND = "#C1440E"      # البرتقالي المحروق بتاع Orange Lab

st.markdown(f"""<style>
  .stApp {{ direction: rtl; }}
  section.main > div {{ padding-top: 1rem; }}
  h1,h2,h3 {{ color:{BRAND}; }}
  div[data-testid="stMetricValue"] {{ font-size:1.4rem; }}
  .stButton>button {{ width:100%; }}
  .ol-card {{ border:1px solid #e6e6e6; border-right:4px solid {BRAND};
             border-radius:8px; padding:.7rem .9rem; margin-bottom:.5rem;
             background:#fff; }}
  .ol-id {{ font-family:ui-monospace,monospace; font-size:.78rem; color:#666; }}
  .ol-warn {{ background:#FFF4E5; border-right:4px solid #E8A33D;
              padding:.6rem .9rem; border-radius:6px; margin:.3rem 0; }}
  .ol-stop {{ background:#FDECEA; border-right:4px solid #C62828;
              padding:.6rem .9rem; border-radius:6px; margin:.3rem 0; }}
</style>""", unsafe_allow_html=True)

# الصلاحيات
P_CREATE, P_SEND, P_RECEIVE, P_RESULT, P_VERIFY, P_CLOSE = (
    "create", "send", "receive", "result", "verify", "close")

ROLES = {
    "reception": {P_CREATE, P_SEND, P_CLOSE},
    "tech":      {P_RECEIVE, P_RESULT},
    "director":  {P_CREATE, P_SEND, P_RECEIVE, P_RESULT, P_VERIFY, P_CLOSE},
    "admin":     {P_CREATE, P_SEND, P_RECEIVE, P_RESULT, P_VERIFY, P_CLOSE},
}
ROLE_AR = {"reception": "استقبال", "tech": "فني معمل",
           "director": "مدير المعمل", "admin": "مدير النظام"}


# ══════════════════════════════════════════════════════════════════════════
# الدخول — فردي لكل موظف، مش باسورد مشترك للفرع.
# السبب: ISO 15189 عايز يعرف مين عمل التحليل ومين راجعه بالاسم.
# الباسورد المشترك بيلغي المساءلة دي تماماً.
# ══════════════════════════════════════════════════════════════════════════

def hash_password(pw: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()


def verify_user(username: str, password: str):
    users = st.secrets.get("users", {})
    salt = st.secrets.get("password_salt", "orange-lab")
    u = users.get(username.strip().lower())
    if not u:
        return None
    if not hmac.compare_digest(hash_password(password, salt), u.get("password_hash", "")):
        return None
    return {"username": username.strip().lower(), "name": u.get("name", username),
            "branch": u.get("branch", catalog.DIAMOND),
            "role": u.get("role", "reception")}


def can(perm: str) -> bool:
    return perm in ROLES.get(st.session_state.user["role"], set())


def login_screen():
    st.title("🔬 Orange Lab")
    st.caption("نظام تبادل العينات بين الفروع")
    with st.form("login"):
        user = st.text_input("اسم المستخدم")
        pw = st.text_input("كلمة المرور", type="password")
        if st.form_submit_button("دخول", type="primary"):
            u = verify_user(user, pw)
            if u:
                st.session_state.user = u
                st.rerun()
            else:
                st.error("اسم المستخدم أو كلمة المرور غير صحيحة.")
    if not st.secrets.get("users"):
        st.warning("مفيش مستخدمين متسجّلين. شغّل `python make_hash.py` "
                   "وضيف الناتج في secrets.toml.")


# ══════════════════════════════════════════════════════════════════════════
# أدوات
# ══════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_store():
    return store.from_secrets(dict(st.secrets))


def me():
    return st.session_state.user


def branch_ar(b):
    return catalog.BRANCH_NAMES[b]["ar"]


def whatsapp_link(phone: str, text: str) -> str:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if digits.startswith("0"):
        digits = "2" + digits          # مصر
    return f"https://wa.me/{digits}?text={urllib.parse.quote(text)}"


def status_chip(req) -> str:
    return f"{schema.STATUS_COLOR.get(req['status'],'')} {schema.STATUS_AR.get(req['status'], req['status'])}"


def request_card(req, extra: str = ""):
    p = req["patient"]
    st.markdown(
        f"""<div class="ol-card">
        <b>{p['name']}</b> &nbsp;·&nbsp; كود {p['lab_code']}
        {' · ' + p['age'] if p['age'] else ''}<br>
        <span class="ol-id">{req['id']}</span><br>
        {status_chip(req)} &nbsp;·&nbsp;
        {branch_ar(req['origin_branch'])} ← {branch_ar(req['performing_branch'])}
        &nbsp;·&nbsp; {len(req['tests'])} تحليل {extra}
        </div>""", unsafe_allow_html=True)


def show_stability(req, at=None):
    """عرض حالة الثبات — بيرجّع True لو في تحليل خلص وقته."""
    issues = schema.stability_check(req, at)
    expired = [i for i in issues if i["level"] == "expired"]
    for i in issues:
        cls = "ol-stop" if i["level"] == "expired" else "ol-warn"
        icon = "🔴 خلص وقت الثبات" if i["level"] == "expired" else "🟡 قرّب يخلص"
        st.markdown(f"""<div class="{cls}"><b>{icon} — {i['test']}</b><br>
            عدّى {i['elapsed']:g} ساعة · الحد {i['limit']:g} ساعة<br>
            <small>{i['note']}</small></div>""", unsafe_allow_html=True)
    return bool(expired)


def result_inputs(test, prefix: str, existing=None):
    """
    خانات إدخال النتيجة — بتتعامل مع اللوحات المركّبة (PT / CBC)
    بنفس منطق التحليل المفرد. بترجّع (value, components).
    """
    td = catalog.get(test["code"]) if test["code"] else None
    if td and td.kind == catalog.KIND_COMPOSITE:
        comps = {}
        prev = (existing or {}).get("components") or {}
        cols = st.columns(min(len(td.components), 4))
        for i, a in enumerate(td.components):
            with cols[i % len(cols)]:
                v = st.text_input(f"{a.name_en} {'('+a.unit+')' if a.unit else ''}",
                                  value=str(prev.get(a.code, "")),
                                  key=f"{prefix}_{a.code}")
                if v.strip():
                    comps[a.code] = _num(v)
        return None, comps
    unit = test["unit"]
    v = st.text_input(f"النتيجة {'('+unit+')' if unit else ''}",
                      value=str((existing or {}).get("value", "")),
                      key=f"{prefix}_v")
    return (_num(v) if v.strip() else None), None


def _num(s):
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return s.strip()


# ══════════════════════════════════════════════════════════════════════════
# شاشة 1 — لوحة اليوم
# ══════════════════════════════════════════════════════════════════════════

def screen_dashboard():
    st.subheader("لوحة اليوم")
    db = get_store()
    b = me()["branch"]

    try:
        rows = db.list_day(schema.today_key())
    except Exception as e:
        st.error(f"مش قادر أقرا بيانات النهاردة: {e}")
        return

    mine = [r for r in rows if b in (r["origin_branch"], r["performing_branch"])]
    incoming = [r for r in mine if r["performing_branch"] == b
                and r["status"] in (schema.SENT,)]
    bench = [r for r in mine if r["performing_branch"] == b
             and r["status"] in (schema.RECEIVED, schema.IN_PROGRESS)]
    to_close = [r for r in mine if r["origin_branch"] == b
                and r["status"] == schema.VERIFIED]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("طلبات اليوم", len(mine))
    c2.metric("في الطريق إليك", len(incoming))
    c3.metric("على البنش", len(bench))
    c4.metric("جاهزة للنقل", len(to_close))

    if to_close:
        st.success(f"في {len(to_close)} نتيجة معتمدة مستنية النقل — روح لتبويب «نقل وقفل».")

    st.divider()
    flt = st.selectbox("عرض", ["الكل"] + [schema.STATUS_AR[s] for s in
                                          (schema.SENT, schema.RECEIVED, schema.IN_PROGRESS,
                                           schema.RESULTED, schema.VERIFIED, schema.CLOSED,
                                           schema.REJECTED)])
    for r in mine:
        if flt != "الكل" and schema.STATUS_AR.get(r["status"]) != flt:
            continue
        extra = ""
        if r["status"] in (schema.SENT,):
            extra = f" · في الطريق من {schema.hours_since_collection(r):.1f} ساعة"
        request_card(r, extra)


# ══════════════════════════════════════════════════════════════════════════
# شاشة 2 — طلب جديد
# ══════════════════════════════════════════════════════════════════════════

def screen_new():
    if not can(P_CREATE):
        st.info("دورك مايسمحش بإنشاء طلبات.")
        return

    origin = me()["branch"]
    performing = catalog.other_branch(origin)
    st.subheader(f"طلب جديد → {branch_ar(performing)}")

    c1, c2, c3 = st.columns(3)
    name = c1.text_input("اسم المريض *")
    code = c2.text_input("كود المعمل *")
    age = c3.text_input("السن", placeholder="45Y أو 8M")
    c4, c5, c6 = st.columns(3)
    sex = c4.selectbox("النوع", ["", "ذكر", "أنثى"])
    phone = c5.text_input("الموبايل", placeholder="01xxxxxxxxx")
    doctor = c6.text_input("الطبيب المحوِّل")

    complaint = st.text_input("الشكوى")
    fasting = st.radio("الصيام", ["غير محدد", "صايم", "فاطر"], horizontal=True)
    note = st.text_area("ملاحظة على الطلب", height=70,
                        placeholder="مثال: صايم 12 ساعة · وقت بداية الأكل 9:30")

    st.markdown("#### التحاليل")
    chosen = []
    for dev, tests in catalog.grouped_for_route(performing).items():
        with st.expander(f"🔬 {catalog.DEVICE_NAMES[dev]} ({len(tests)})",
                         expanded=(dev == catalog.DEV_BIOBASE)):
            cols = st.columns(3)
            for i, t in enumerate(tests):
                if cols[i % 3].checkbox(t.display, key=f"tk_{t.code}"):
                    chosen.append({"code": t.code})

    # تحاليل إضافية — كل ما تكتب واحد، خانة جديدة بتفتح
    st.markdown("#### تحاليل إضافية")
    if "adhoc" not in st.session_state:
        st.session_state.adhoc = [{"name": "", "unit": ""}]
    rows = st.session_state.adhoc
    for i, row in enumerate(rows):
        a, b_ = st.columns([3, 1])
        row["name"] = a.text_input("اسم التحليل", row["name"],
                                   key=f"ah_n{i}", label_visibility="collapsed",
                                   placeholder="اسم التحليل")
        row["unit"] = b_.text_input("الوحدة", row["unit"],
                                    key=f"ah_u{i}", label_visibility="collapsed",
                                    placeholder="الوحدة")
    if rows[-1]["name"].strip():
        rows.append({"name": "", "unit": ""})
        st.rerun()
    for row in rows:
        if row["name"].strip():
            chosen.append({"custom_name": row["name"], "custom_unit": row["unit"]})

    # معاينة حيّة: الأنابيب والتحذيرات
    if chosen:
        st.divider()
        try:
            preview = schema.new_request(
                origin_branch=origin, performing_branch=performing,
                patient_name=name or "—", lab_code=code or "—",
                fasting={"صايم": True, "فاطر": False}.get(fasting),
                tests=chosen)
            st.markdown("**الأنابيب المطلوبة**")
            for t in preview["tubes"]:
                st.markdown(f"- **{t['type']}** — {'، '.join(t['for'])}")
            for w in schema.preanalytical_warnings(preview):
                st.markdown(f'<div class="ol-warn">{w}</div>', unsafe_allow_html=True)
        except ValueError:
            pass

    st.divider()
    if st.button("احفظ الطلب", type="primary", disabled=not chosen):
        try:
            req = schema.new_request(
                origin_branch=origin, performing_branch=performing,
                patient_name=name, lab_code=code, age=age,
                sex=sex, phone=phone, complaint=complaint,
                referring_doctor=doctor, request_note=note,
                fasting={"صايم": True, "فاطر": False}.get(fasting),
                tests=chosen, created_by=me()["username"])
            get_store().create(req)
            st.session_state.adhoc = [{"name": "", "unit": ""}]
            st.session_state.last_new = req["id"]
            st.success(f"اتحفظ — {req['id']}")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"الحفظ فشل: {e}")

    # تسليم للمندوب
    if st.session_state.get("last_new"):
        st.divider()
        st.markdown("#### تسليم للنقل")
        rid = st.session_state.last_new
        req = get_store().find(rid)
        if req and req["status"] == schema.DRAFT:
            request_card(req)
            a, b_ = st.columns(2)
            mode = a.selectbox("وسيلة النقل", schema.TRANSPORT_MODES)
            courier = b_.text_input("اسم الشخص")
            if st.button("سلّمت العينة", type="primary"):
                try:
                    get_store().update(req["day"], rid, lambda x: schema.mark_sent(
                        x, actor=me()["username"], mode=mode, courier=courier))
                    st.session_state.pop("last_new", None)
                    st.success("اتسجّل الإرسال.")
                    st.rerun()
                except Exception as e:
                    st.error(f"مش قادر أسجّل الإرسال: {e}")


# ══════════════════════════════════════════════════════════════════════════
# شاشة 3 — استلام
# ══════════════════════════════════════════════════════════════════════════

def screen_receive():
    if not can(P_RECEIVE):
        st.info("دورك مايسمحش باستلام العينات.")
        return

    st.subheader("استلام العينات")
    db = get_store()
    b = me()["branch"]
    pending = [r for r in db.open_requests(b, days_back=3)
               if r["performing_branch"] == b and r["status"] == schema.SENT]

    if not pending:
        st.info("مفيش عينات مستنية الاستلام.")
        return

    for req in pending:
        with st.container(border=True):
            request_card(req, f" · في الطريق من {schema.hours_since_collection(req):.1f} ساعة")
            st.caption("الأنابيب: " + "، ".join(t["type"] for t in req["tubes"]))
            st.caption("التحاليل: " + "، ".join(t["name"] for t in req["tests"]))
            if req["notes"]["on_request"]:
                st.caption(f"📝 {req['notes']['on_request']}")

            expired = show_stability(req)

            c1, c2 = st.columns(2)
            cond = c1.selectbox("حالة العينة", schema.SPECIMEN_CONDITIONS,
                                key=f"cond_{req['id']}")
            note = c2.text_input("ملاحظة الاستلام", key=f"rn_{req['id']}")

            override = False
            if expired:
                override = st.checkbox(
                    "أتحمّل مسؤولية التشغيل رغم انتهاء وقت الثبات "
                    "(هيتسجّل باسمي في سجل التدقيق)",
                    key=f"ov_{req['id']}")

            a, b_ = st.columns(2)
            if a.button("✅ استلام", key=f"acc_{req['id']}", type="primary",
                        disabled=(expired and not override)):
                try:
                    db.update(req["day"], req["id"], lambda x: schema.mark_received(
                        x, actor=me()["username"], condition=cond, note=note,
                        override_stability=override))
                    st.success("اتسجّل الاستلام.")
                    st.rerun()
                except schema.StabilityError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"مش قادر أسجّل الاستلام: {e}")

            with b_.popover("❌ رفض العينة"):
                reason = st.selectbox("سبب الرفض", schema.REJECTION_REASONS,
                                      key=f"rr_{req['id']}")
                rnote = st.text_input("تفاصيل", key=f"rd_{req['id']}")
                if st.button("أكّد الرفض", key=f"rj_{req['id']}"):
                    try:
                        db.update(req["day"], req["id"], lambda x: schema.mark_rejected(
                            x, actor=me()["username"], reason=reason, note=rnote))
                        st.warning("العينة اترفضت — بلّغ الفرع المرسِل.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"مش قادر أسجّل الرفض: {e}")


# ══════════════════════════════════════════════════════════════════════════
# شاشة 4 — إدخال النتيجة
# ══════════════════════════════════════════════════════════════════════════

def screen_results():
    if not can(P_RESULT):
        st.info("دورك مايسمحش بإدخال النتائج.")
        return

    st.subheader("إدخال النتائج")
    db = get_store()
    b = me()["branch"]
    active = [r for r in db.open_requests(b, days_back=7)
              if r["performing_branch"] == b
              and r["status"] in (schema.RECEIVED, schema.IN_PROGRESS)]

    if not active:
        st.info("مفيش عينات على البنش.")
        return

    labels = {f"{r['patient']['name']} — {r['patient']['lab_code']} "
              f"({len(r['results'])}/{len(r['tests'])})": r for r in active}
    pick = st.selectbox("اختر العينة", list(labels))
    req = labels[pick]

    request_card(req)
    if req["notes"]["on_request"]:
        st.caption(f"📝 طلب: {req['notes']['on_request']}")
    if req["notes"]["on_receipt"]:
        st.caption(f"📝 استلام: {req['notes']['on_receipt']}")

    if req["status"] == schema.RECEIVED:
        if st.button("ابدأ التشغيل"):
            db.update(req["day"], req["id"],
                      lambda x: schema.mark_in_progress(x, actor=me()["username"]))
            st.rerun()
        return

    st.divider()
    for t in req["tests"]:
        existing = req["results"].get(t["key"])
        done = "✅" if existing else "⬜"
        with st.expander(f"{done} {t['name']}", expanded=not existing):
            val, comps = result_inputs(t, f"r_{req['id']}_{t['key']}", existing)

            # ملاحظة على كل تحليل لوحده — المستوى اللي طلبته
            note = st.text_input(
                "ملاحظة على التحليل ده",
                value=(existing or {}).get("note", ""),
                key=f"n_{req['id']}_{t['key']}",
                placeholder="مثال: اتعمل diluted 1:2 · hemolysis قد ترفع القيمة")

            crit = st.checkbox("⚠️ قيمة حرجة — تستدعي إبلاغ فوري",
                               value=(existing or {}).get("critical", False),
                               key=f"c_{req['id']}_{t['key']}")

            # مقارنة بالنتيجة السابقة لنفس المريض
            if val is not None:
                prev, when = db.previous_value(req["patient"]["key"], t["key"],
                                               exclude_id=req["id"])
                if prev is not None:
                    d = schema.delta_check(val, prev)
                    if d and d["flag"]:
                        st.markdown(
                            f'<div class="ol-warn">📈 فرق كبير عن آخر نتيجة: '
                            f'{prev} ← {val} ({d["pct"]:+g}%) بتاريخ '
                            f'{schema.local_str(when, "%Y-%m-%d")}. راجع قبل الاعتماد.'
                            f'</div>', unsafe_allow_html=True)

            if st.button("احفظ النتيجة", key=f"sv_{req['id']}_{t['key']}"):
                try:
                    db.update(req["day"], req["id"], lambda x: schema.set_result(
                        x, t["key"], val, actor=me()["username"], note=note,
                        components=comps, critical=crit))
                    st.success("اتحفظت.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    # إبلاغ القيم الحرجة
    fresh = db.get(req["day"], req["id"])
    openc = [c for c in fresh.get("critical", []) if c.get("read_back") is None]
    if openc:
        st.divider()
        st.markdown('<div class="ol-stop"><b>⚠️ قيم حرجة مستنية الإبلاغ</b><br>'
                    'الاعتماد مش هيشتغل قبل تسجيل الإبلاغ.</div>',
                    unsafe_allow_html=True)
        for c in openc:
            st.markdown(f"**{c['test']} = {c['value']}**")
            if fresh["patient"]["phone"]:
                msg = (f"⚠️ قيمة حرجة — Orange Lab\n{fresh['patient']['name']} "
                       f"(كود {fresh['patient']['lab_code']})\n{c['test']}: {c['value']}")
                st.link_button("📱 بلّغ على واتساب",
                               whatsapp_link(fresh["patient"]["phone"], msg))
            who = st.text_input("مين استلم الإبلاغ؟", key=f"rb_{c['test']}",
                                placeholder="اسم الطبيب أو الشخص")
            rnote = st.text_input("ملاحظة", key=f"rbn_{c['test']}")
            if st.button("سجّل الإبلاغ", key=f"rbb_{c['test']}", disabled=not who.strip()):
                db.update(req["day"], req["id"], lambda x: schema.record_read_back(
                    x, c["test"], called_by=me()["username"],
                    received_by=who, note=rnote))
                st.success("الإبلاغ اتسجّل.")
                st.rerun()

    st.divider()
    remaining = [t["name"] for t in fresh["tests"] if t["key"] not in fresh["results"]]
    gnote = st.text_area("ملاحظة عامة على النتيجة", height=70,
                         value=fresh["notes"].get("on_result", ""))
    c1, c2 = st.columns(2)
    if c1.button("أنهيت كل النتائج", type="primary", disabled=bool(remaining)):
        try:
            db.update(req["day"], req["id"], lambda x: schema.mark_resulted(
                x, actor=me()["username"], note=gnote))
            st.success("النتائج جاهزة للاعتماد.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    if remaining:
        c1.caption("ناقص: " + "، ".join(remaining))

    if fresh["status"] == schema.RESULTED and can(P_VERIFY):
        if c2.button("✅ اعتماد إكلينيكي", type="primary"):
            try:
                db.update(req["day"], req["id"],
                          lambda x: schema.mark_verified(x, actor=me()["username"]))
                st.success("اتعتمدت — الفرع المرسِل يقدر ينقلها دلوقتي.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))


# ══════════════════════════════════════════════════════════════════════════
# شاشة 5 — نقل وقفل
# ══════════════════════════════════════════════════════════════════════════

def screen_transcribe():
    if not can(P_CLOSE):
        st.info("دورك مايسمحش بنقل النتائج.")
        return

    st.subheader("نقل النتائج وقفل الطلب")
    db = get_store()
    b = me()["branch"]
    ready = [r for r in db.open_requests(b, days_back=14)
             if r["origin_branch"] == b and r["status"] == schema.VERIFIED]

    if not ready:
        st.info("مفيش نتائج معتمدة مستنية النقل.")
        return

    labels = {f"{r['patient']['name']} — {r['patient']['lab_code']}": r for r in ready}
    req = labels[st.selectbox("اختر الطلب", list(labels))]

    request_card(req)
    st.markdown("#### انسخ والصق في نظامك")
    st.caption("عمود التحليل / القيمة / الوحدة / الملاحظة — مفصولين بـ Tab.")
    st.code(schema.as_tsv(req), language=None)

    for label, key in (("ملاحظة الاستلام", "on_receipt"),
                       ("ملاحظة النتيجة", "on_result")):
        if req["notes"].get(key):
            st.info(f"📝 {label}: {req['notes'][key]}")

    for c in req.get("critical", []):
        rb = c.get("read_back") or {}
        st.markdown(f'<div class="ol-warn">⚠️ <b>{c["test"]} = {c["value"]}</b> — '
                    f'قيمة حرجة، اتبلّغت لـ {rb.get("received_by","—")} '
                    f'في {schema.local_str(rb.get("at",""))}</div>',
                    unsafe_allow_html=True)

    st.divider()
    who = st.text_input("مين نقل النتيجة؟", value=me()["name"])
    ok = st.checkbox("راجعت كل القيم بعد نقلها وطابقتها على الشاشة")
    if st.button("قفل الطلب", type="primary", disabled=not ok):
        try:
            db.update(req["day"], req["id"], lambda x: schema.mark_closed(
                x, actor=me()["username"], transcribed_by=who))
            st.success("الطلب اتقفل — الحلقة كملت.")
            st.rerun()
        except Exception as e:
            st.error(f"مش قادر أقفل الطلب: {e}")


# ══════════════════════════════════════════════════════════════════════════
# شاشة 6 — بحث وسجل
# ══════════════════════════════════════════════════════════════════════════

def screen_search():
    st.subheader("بحث وسجل التدقيق")
    db = get_store()
    rid = st.text_input("كود الطلب", placeholder="SND-DMD-20260813-...")
    if not rid.strip():
        return
    try:
        req = db.find(rid.strip().upper())
    except Exception as e:
        st.error(f"البحث فشل: {e}")
        return
    if not req:
        st.warning("مفيش طلب بالكود ده.")
        return

    request_card(req)
    t = schema.tat(req)
    c = st.columns(4)
    for i, (k, lbl) in enumerate([("transit", "النقل"), ("bench", "التشغيل"),
                                  ("verify", "الاعتماد"), ("total", "الإجمالي")]):
        c[i].metric(lbl, f"{t[k]:.0f} د" if t[k] is not None else "—")

    if req["results"]:
        st.code(schema.as_tsv(req), language=None)

    st.markdown("#### سجل التدقيق")
    for e in req["events"]:
        detail = "، ".join(f"{k}: {v}" for k, v in (e.get("detail") or {}).items())
        st.text(f"{schema.local_str(e['at'], '%m-%d %H:%M')}  "
                f"{e['action']:22} {e['actor']:14} {detail}")


# ══════════════════════════════════════════════════════════════════════════
# التشغيل
# ══════════════════════════════════════════════════════════════════════════

def main():
    if "user" not in st.session_state:
        login_screen()
        return

    u = me()
    c1, c2 = st.columns([4, 1])
    c1.markdown(f"### 🔬 Orange Lab · {branch_ar(u['branch'])}")
    c1.caption(f"{u['name']} — {ROLE_AR.get(u['role'], u['role'])}")
    if c2.button("خروج"):
        st.session_state.clear()
        st.rerun()

    tabs = ["لوحة اليوم"]
    if can(P_CREATE):  tabs.append("طلب جديد")
    if can(P_RECEIVE): tabs.append("استلام")
    if can(P_RESULT):  tabs.append("النتائج")
    if can(P_CLOSE):   tabs.append("نقل وقفل")
    tabs.append("بحث")

    fns = {"لوحة اليوم": screen_dashboard, "طلب جديد": screen_new,
           "استلام": screen_receive, "النتائج": screen_results,
           "نقل وقفل": screen_transcribe, "بحث": screen_search}
    for tab, name in zip(st.tabs(tabs), tabs):
        with tab:
            fns[name]()


if __name__ == "__main__":
    main()
