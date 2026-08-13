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


def status_badge(status: str) -> str:
    """شارة ملوّنة — اللون بيقول الحالة قبل ما تقرا الكلام."""
    fg, bg = schema.STATUS_HEX.get(status, ("#616161", "#F5F5F5"))
    return (f'<span style="background:{bg};color:{fg};padding:.15rem .55rem;'
            f'border-radius:999px;font-size:.8rem;font-weight:700;'
            f'white-space:nowrap">{schema.STATUS_COLOR.get(status,"")} '
            f'{schema.STATUS_AR.get(status, status)}</span>')


def status_chip(req) -> str:
    return status_badge(req["status"])


def request_card(req, extra: str = "", show_next: bool = True):
    p = req["patient"]
    fg, _ = schema.STATUS_HEX.get(req["status"], ("#C1440E", ""))
    nxt = ""
    if show_next:
        nxt = (f'<br><span style="color:{fg};font-size:.78rem">'
               f'↩ {schema.NEXT_STEP.get(req["status"],"")}</span>')
    done = len(req.get("results", {}))
    prog = f" · {done}/{len(req['tests'])} نتيجة" if done else ""
    st.markdown(
        f"""<div class="ol-card" style="border-right-color:{fg}">
        <b>{p['name']}</b> &nbsp;·&nbsp; كود {p['lab_code']}
        {' · ' + p['age'] if p['age'] else ''}<br>
        <span class="ol-id">{req['id']}</span><br>
        {status_badge(req['status'])} &nbsp;
        {branch_ar(req['origin_branch'])} ← {branch_ar(req['performing_branch'])}
        &nbsp;·&nbsp; {len(req['tests'])} تحليل{prog} {extra}{nxt}
        </div>""", unsafe_allow_html=True)


def show_stability(req, at=None):
    """عرض حالة الثبات — بيرجّع True لو في تحليل خلص وقته."""
    # التبريد الضار أهم من الوقت: العينة ممكن تكون في الوقت
    # والنتيجة غلط أصلاً بسبب الحرارة.
    if req.get("cold_chain", True):
        keys = [t["code"] or t["key"] for t in req["tests"]]
        for t in catalog.cold_unsuitable(keys):
            st.markdown(f'<div class="ol-stop"><b>⛔ {t.name_en} — '
                        f'التبريد بيغيّر النتيجة</b><br>'
                        f'<small>{t.cold_note}</small></div>',
                        unsafe_allow_html=True)
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
                and r["status"] == schema.SENT]
    bench = [r for r in mine if r["performing_branch"] == b
             and r["status"] in (schema.RECEIVED, schema.IN_PROGRESS)]
    to_close = [r for r in mine if r["origin_branch"] == b
                and r["status"] == schema.VERIFIED]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("طلبات اليوم", len(mine))
    c2.metric("🚚 في الطريق إليك", len(incoming))
    c3.metric("🔬 على البنش", len(bench))
    c4.metric("✅ جاهزة للنقل", len(to_close))

    # الحاجات اللي محتاجة تصرّف منك — فوق وبالألوان
    urgent = []
    if incoming:
        urgent.append(("SENT", f"{len(incoming)} عينة مستنية استلام", "استلام"))
    if bench:
        urgent.append(("IN_PROGRESS", f"{len(bench)} عينة على البنش", "النتائج"))
    if to_close:
        urgent.append(("VERIFIED", f"{len(to_close)} نتيجة جاهزة للنقل", "نقل وقفل"))
    for status, msg, tab in urgent:
        fg, bg = schema.STATUS_HEX[status]
        st.markdown(f'<div style="background:{bg};border-right:4px solid {fg};'
                    f'padding:.6rem .9rem;border-radius:6px;margin:.25rem 0;'
                    f'color:{fg};font-weight:600">{msg} — روح لتبويب «{tab}»</div>',
                    unsafe_allow_html=True)
    if not urgent:
        st.success("مفيش حاجة مستنية منك دلوقتي. 👌")

    # ⏳ فجوة مدد الثبات — بتفضل ظاهرة لحد ما تتقفل
    pend = catalog.pending_stability()
    if pend and can(P_VERIFY):
        with st.expander(f"⏳ {len(pend)} تحليل مستني اعتماد مدة الثبات"):
            st.caption("التحاليل دي مفيش ليها نافذة ثبات معتمدة، فالنظام "
                       "**مش** بيمنع استلامهم مهما طال النقل. ده مقصود — "
                       "أحسن من رقم مخترع بيمنع عينات سليمة بثقة كاذبة. "
                       "حدّد المدة في `catalog.py` مع اسم اللي اعتمدها.")
            ok = [t for t in catalog.TESTS.values() if t.stability_hours is not None]
            st.markdown(f"**معتمدة ({len(ok)}):** " +
                        "، ".join(f"{t.code} {t.stability_hours:g}س" for t in ok))
            st.markdown(f"**مستنية ({len(pend)}):** " +
                        "، ".join(t.code for t in pend))

    st.divider()

    # مفتاح الألوان
    with st.expander("🎨 معنى الألوان"):
        for s in (schema.DRAFT, schema.SENT, schema.RECEIVED, schema.IN_PROGRESS,
                  schema.RESULTED, schema.VERIFIED, schema.CLOSED,
                  schema.REJECTED, schema.CANCELLED):
            st.markdown(f"{status_badge(s)} &nbsp; {schema.NEXT_STEP.get(s,'')}",
                        unsafe_allow_html=True)

    order = [schema.SENT, schema.RECEIVED, schema.IN_PROGRESS, schema.RESULTED,
             schema.VERIFIED, schema.DRAFT, schema.CLOSED,
             schema.REJECTED, schema.CANCELLED]
    opts = ["الكل"] + [f"{schema.STATUS_COLOR[s]} {schema.STATUS_AR[s]}"
                       for s in order if any(r["status"] == s for r in mine)]
    flt = st.selectbox("عرض", opts)

    shown = 0
    for s in order:
        group = [r for r in mine if r["status"] == s]
        if not group:
            continue
        if flt != "الكل" and flt != f"{schema.STATUS_COLOR[s]} {schema.STATUS_AR[s]}":
            continue
        st.markdown(f"**{schema.STATUS_COLOR[s]} {schema.STATUS_AR[s]}** "
                    f"({len(group)})")
        for r in group:
            extra = ""
            if s == schema.SENT:
                extra = f" · في الطريق من {schema.hours_since_collection(r):.1f} ساعة"
            request_card(r, extra)
            shown += 1
    if not shown:
        st.info("مفيش طلبات في العرض ده.")


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
    c7, c8 = st.columns(2)
    with c7:
        fasting = st.radio("الصيام", ["غير محدد", "صايم", "فاطر"], horizontal=True)
    with c8:
        temp = st.radio("النقل", ["❄️ مبرّد / ثلج", "🌡️ حرارة الغرفة"],
                        horizontal=True)
    cold = temp.startswith("❄️")
    note = st.text_area("ملاحظة على الطلب", height=70,
                        placeholder="مثال: صايم 12 ساعة · وقت بداية الأكل 9:30")

    st.markdown("#### التحاليل")

    # كل checkbox كان بيعمل rerun — 34 مربع = 34 دورة.
    # الـ multiselect بيعمل دورة واحدة مهما اخترت، وبيسمح بالبحث بالكتابة.
    if "picked" not in st.session_state:
        st.session_state.picked = []

    st.caption("لوحات جاهزة — ضغطة واحدة بتضيف المجموعة كلها")
    panels = catalog.panels_for_route(performing)
    pcols = st.columns(2)
    for i, (pname, pcodes) in enumerate(panels.items()):
        if pcols[i % 2].button(pname, key=f"pn_{i}", use_container_width=True):
            for c in pcodes:
                if c not in st.session_state.picked:
                    st.session_state.picked.append(c)
            st.rerun()

    all_tests = catalog.tests_for_route(performing)
    label_of = {t.code: f"{t.name_en} ({t.unit})" if t.unit else t.name_en
                for t in all_tests}
    picked = st.multiselect(
        "التحاليل المطلوبة", options=[t.code for t in all_tests],
        default=[c for c in st.session_state.picked if c in label_of],
        format_func=lambda c: label_of.get(c, c),
        placeholder="اكتب اسم التحليل أو اختار من اللوحات فوق")
    if picked != st.session_state.picked:
        st.session_state.picked = picked

    if picked:
        a, b_ = st.columns([3, 1])
        a.caption(f"مختار {len(picked)} تحليل")
        if b_.button("🗑 امسح الكل", use_container_width=True):
            st.session_state.picked = []
            st.rerun()

    chosen = [{"code": c} for c in picked]

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
                cold_chain=cold, tests=chosen)
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
                cold_chain=cold, tests=chosen, created_by=me()["username"])
            get_store().create(req)
            st.session_state.adhoc = [{"name": "", "unit": ""}]
            st.session_state.picked = []
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

    st.caption(f"{len(pending)} عينة مستنية — الاستلام ضغطة واحدة، "
               "والرفض جوّه القايمة.")

    for req in pending:
        fg, bg = schema.STATUS_HEX[schema.SENT]
        with st.container(border=True):
            request_card(req,
                         f" · في الطريق من {schema.hours_since_collection(req):.1f} ساعة",
                         show_next=False)
            temp_ic = "❄️ مبرّد" if req.get("cold_chain", True) else "🌡️ حرارة الغرفة"
            st.caption(f"{temp_ic} · 🧪 " + "، ".join(t["type"] for t in req["tubes"]))
            with st.expander(f"التحاليل ({len(req['tests'])})"):
                st.write("، ".join(t["name"] for t in req["tests"]))
            if req["notes"]["on_request"]:
                st.caption(f"📝 {req['notes']['on_request']}")

            expired = show_stability(req)

            # الاستلام السريع: زرار واحد. التفاصيل اختيارية جوّه القايمة.
            c1, c2 = st.columns([2, 1])
            if c1.button("📦 استلام", key=f"acc_{req['id']}", type="primary",
                         use_container_width=True, disabled=expired):
                try:
                    db.update(req["day"], req["id"], lambda x: schema.mark_received(
                        x, actor=me()["username"], condition="سليمة"))
                    st.rerun()
                except Exception as e:
                    st.error(f"مش قادر أسجّل الاستلام: {e}")

            with c2.popover("⋯ تفاصيل", use_container_width=True):
                cond = st.selectbox("حالة العينة", schema.SPECIMEN_CONDITIONS,
                                    key=f"cond_{req['id']}")
                note = st.text_input("ملاحظة الاستلام", key=f"rn_{req['id']}")
                override = False
                if expired:
                    override = st.checkbox(
                        "أتحمّل مسؤولية التشغيل رغم انتهاء وقت الثبات "
                        "(هيتسجّل باسمي)", key=f"ov_{req['id']}")
                if st.button("استلام بالتفاصيل دي", key=f"acd_{req['id']}",
                             type="primary"):
                    try:
                        db.update(req["day"], req["id"], lambda x: schema.mark_received(
                            x, actor=me()["username"], condition=cond, note=note,
                            override_stability=override))
                        st.rerun()
                    except schema.StabilityError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"فشل: {e}")

                st.divider()
                reason = st.selectbox("سبب الرفض", schema.REJECTION_REASONS,
                                      key=f"rr_{req['id']}")
                rnote = st.text_input("تفاصيل الرفض", key=f"rd_{req['id']}")
                if st.button("⛔ ارفض العينة", key=f"rj_{req['id']}"):
                    try:
                        db.update(req["day"], req["id"], lambda x: schema.mark_rejected(
                            x, actor=me()["username"], reason=reason, note=rnote))
                        st.warning("العينة اترفضت — بلّغ الفرع المرسِل.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"فشل: {e}")

            if expired:
                st.caption("⛔ الاستلام مقفول — افتح «تفاصيل» لو هتتحمّل المسؤولية.")


# ══════════════════════════════════════════════════════════════════════════
# شاشة 4 — إدخال النتيجة
# ══════════════════════════════════════════════════════════════════════════

def _build_sheet(req):
    """
    بيفرد الطلب لصفوف: صف لكل قيمة هتتكتب.
    اللوحات المركّبة (PT / CBC) بتتفرد لمكوّناتها، فالشيت بيبقى مسطّح
    والفني بيشوف كل حاجة قدامه مرة واحدة.
    بيرجّع (rows, meta) — meta فيها (مفتاح التحليل، كود المكوّن أو None)
    """
    rows, meta = [], []
    for t in req["tests"]:
        td = catalog.get(t["code"]) if t["code"] else None
        cur = req["results"].get(t["key"]) or {}
        if td and td.kind == catalog.KIND_COMPOSITE:
            comps = cur.get("components") or {}
            for j, a in enumerate(td.components):
                rows.append({
                    "التحليل": f"{td.name_en} · {a.name_en}",
                    "النتيجة": str(comps.get(a.code, "")),
                    "الوحدة": a.unit,
                    "ملاحظة": cur.get("note", "") if j == 0 else "",
                    "حرجة": bool(cur.get("critical")) if j == 0 else False,
                })
                meta.append((t["key"], a.code))
        else:
            rows.append({
                "التحليل": t["name"],
                "النتيجة": str(cur.get("value", "")),
                "الوحدة": t["unit"],
                "ملاحظة": cur.get("note", ""),
                "حرجة": bool(cur.get("critical")),
            })
            meta.append((t["key"], None))
    return rows, meta


def _collect(edited, meta):
    """بيجمّع صفوف الشيت تاني في نتائج لكل تحليل."""
    out = {}
    for i, (key, comp) in enumerate(meta):
        r = edited[i]
        val = str(r.get("النتيجة", "")).strip()
        note = str(r.get("ملاحظة", "")).strip()
        crit = bool(r.get("حرجة"))
        g = out.setdefault(key, {"value": None, "components": {},
                                 "note": "", "critical": False, "any": False})
        if comp is None:
            if val:
                g["value"] = _num(val); g["any"] = True
        else:
            if val:
                g["components"][comp] = _num(val); g["any"] = True
        if note and not g["note"]:
            g["note"] = note
        g["critical"] = g["critical"] or crit
    return out


def render_results(req, compact: bool = False):
    """
    عرض النتائج كجدول مقروء. الـ TSV للنسخ بيفضل موجود بس مطوي،
    لإن الفني بيقرا الأول وبينسخ تاني.
    """
    crit_names = {c["test"] for c in req.get("critical", [])}
    rows = []
    for t in req["tests"]:
        r = req["results"].get(t["key"])
        if not r:
            rows.append((t["name"], "—", t["unit"], "", False, False))
            continue
        td = catalog.get(t["code"]) if t["code"] else None
        is_crit = t["name"] in crit_names or r.get("critical")
        if td and td.kind == catalog.KIND_COMPOSITE:
            comps = r.get("components") or {}
            rows.append((td.name_en, "", "", r.get("note", ""), is_crit, True))
            for a in td.components:
                v = comps.get(a.code, "")
                if v != "":
                    rows.append((f"⌞ {a.name_en}", str(v), a.unit, "", False, False))
        else:
            rows.append((t["name"], str(r.get("value", "")), t["unit"],
                         r.get("note", ""), is_crit, False))

    html = ['<table style="width:100%;border-collapse:collapse;font-size:.92rem">']
    html.append('<tr style="background:#FAFAFA;color:#666;font-size:.8rem">'
                '<th style="text-align:right;padding:.4rem .6rem">التحليل</th>'
                '<th style="text-align:right;padding:.4rem .6rem">النتيجة</th>'
                '<th style="text-align:right;padding:.4rem .6rem">ملاحظة</th></tr>')
    for name, val, unit, note, is_crit, is_head in rows:
        if is_head:
            html.append(f'<tr style="background:#F5F5F5"><td colspan="3" '
                        f'style="padding:.4rem .6rem;font-weight:700">{name}'
                        + (f' <span style="color:#C62828">⚠️</span>' if is_crit else '')
                        + (f'<br><span style="font-weight:400;color:#666;'
                           f'font-size:.82rem">{note}</span>' if note else '')
                        + '</td></tr>')
            continue
        bg = "#FFEBEE" if is_crit else "#fff"
        fg = "#C62828" if is_crit else "#212121"
        weight = "700" if is_crit else "600"
        vtxt = f'{val} <span style="color:#888;font-weight:400">{unit}</span>' if val != "—" else "—"
        html.append(
            f'<tr style="background:{bg};border-bottom:1px solid #EEE">'
            f'<td style="padding:.45rem .6rem;color:#424242">{name}</td>'
            f'<td style="padding:.45rem .6rem;color:{fg};font-weight:{weight};'
            f'white-space:nowrap">{"⚠️ " if is_crit else ""}{vtxt}</td>'
            f'<td style="padding:.45rem .6rem;color:#757575;font-size:.85rem">'
            f'{note or ""}</td></tr>')
    html.append("</table>")
    st.markdown("".join(html), unsafe_allow_html=True)

    if compact:
        return
    for lbl, k in (("ملاحظة الاستلام", "on_receipt"), ("ملاحظة النتيجة", "on_result")):
        if req["notes"].get(k):
            st.info(f"📝 {lbl}: {req['notes'][k]}")


def screen_results():
    if not can(P_RESULT):
        st.info("دورك مايسمحش بإدخال النتائج.")
        return

    st.subheader("إدخال النتائج")
    db = get_store()
    b = me()["branch"]
    # ⚠️ لازم RESULTED تفضل هنا — من غيرها الطلب بيختفي من الشاشة
    # ومفيش طريقة تعتمده. ده كان طريق مسدود حقيقي.
    active = [r for r in db.open_requests(b, days_back=7)
              if r["performing_branch"] == b
              and r["status"] in (schema.RECEIVED, schema.IN_PROGRESS,
                                  schema.RESULTED)]

    if not active:
        st.info("مفيش عينات على البنش.")
        return

    # اللي مستني اعتماد ييجي الأول — ده أقرب حاجة للتسليم
    active.sort(key=lambda r: (r["status"] != schema.RESULTED,
                               r.get("created_at", "")))
    pend_v = [r for r in active if r["status"] == schema.RESULTED]
    if pend_v:
        st.markdown(f'<div class="ol-warn">📄 {len(pend_v)} نتيجة مستنية '
                    f'الاعتماد — اختارها من القايمة واعتمدها.</div>',
                    unsafe_allow_html=True)

    labels = {}
    for r in active:
        mark = "📄 " if r["status"] == schema.RESULTED else ""
        labels[f"{mark}{r['patient']['name']} — {r['patient']['lab_code']} "
               f"({len(r['results'])}/{len(r['tests'])})"] = r
    req = labels[st.selectbox("اختر العينة", list(labels))]

    request_card(req)
    for lbl, k in (("طلب", "on_request"), ("استلام", "on_receipt")):
        if req["notes"].get(k):
            st.caption(f"📝 {lbl}: {req['notes'][k]}")

    if req["status"] == schema.RECEIVED:
        if st.button("ابدأ التشغيل", type="primary"):
            db.update(req["day"], req["id"],
                      lambda x: schema.mark_in_progress(x, actor=me()["username"]))
            st.rerun()
        return

    # ── حالة RESULTED: النتائج خلصت — عرض ومراجعة واعتماد ────────────────
    if req["status"] == schema.RESULTED:
        st.divider()
        st.markdown("#### راجع النتائج قبل الاعتماد")
        render_results(req)

        openc = [c for c in req.get("critical", []) if c.get("read_back") is None]
        if openc:
            st.markdown('<div class="ol-stop"><b>⚠️ في قيم حرجة متبلّغتش</b><br>'
                        'الاعتماد مقفول لحد ما تسجّل الإبلاغ.</div>',
                        unsafe_allow_html=True)
            for c in openc:
                who = st.text_input(f"مين استلم إبلاغ {c['test']}؟",
                                    key=f"vrb_{req['id']}_{c['test']}")
                if st.button("سجّل الإبلاغ", key=f"vrbb_{req['id']}_{c['test']}",
                             disabled=not who.strip()):
                    db.update(req["day"], req["id"], lambda x: schema.record_read_back(
                        x, c["test"], called_by=me()["username"], received_by=who))
                    st.rerun()
            return

        st.divider()
        a, b2 = st.columns(2)
        if can(P_VERIFY):
            if a.button("✅ اعتماد إكلينيكي", type="primary"):
                try:
                    db.update(req["day"], req["id"],
                              lambda x: schema.mark_verified(x, actor=me()["username"]))
                    st.success(f"اتعتمدت — {branch_ar(req['origin_branch'])} "
                               "يقدر ينقلها دلوقتي.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        else:
            a.info("مستنية اعتماد مدير المعمل.")
        if b2.button("↩️ رجّعها للتعديل"):
            db.update(req["day"], req["id"], lambda x: schema.transition(
                x, schema.IN_PROGRESS, actor=me()["username"],
                branch=me()["branch"], detail={"reason": "تعديل نتيجة"}))
            st.rerun()
        return

    # ── الشيت: كل التحاليل مرة واحدة، حفظ واحد ────────────────────────────
    st.divider()
    st.caption("اكتب النتائج كلها، وبعدين احفظ مرة واحدة. "
               "علّم «حرجة» للقيم اللي تستدعي إبلاغ فوري.")

    rows, meta = _build_sheet(req)
    edited = st.data_editor(
        rows, key=f"sheet_{req['id']}", hide_index=True,
        use_container_width=True, num_rows="fixed",
        column_config={
            "التحليل": st.column_config.TextColumn(disabled=True, width="medium"),
            "النتيجة": st.column_config.TextColumn(width="small"),
            "الوحدة":  st.column_config.TextColumn(disabled=True, width="small"),
            "ملاحظة":  st.column_config.TextColumn(width="medium"),
            "حرجة":    st.column_config.CheckboxColumn(width="small"),
        })

    gnote = st.text_area("ملاحظة عامة على النتيجة", height=70,
                         value=req["notes"].get("on_result", ""),
                         key=f"gn_{req['id']}")

    collected = _collect(edited, meta)
    filled = [k for k, g in collected.items() if g["any"]]
    total = len(req["tests"])
    st.caption(f"متكتب: {len(filled)} من {total}")

    c1, c2 = st.columns(2)

    # حفظ الكل في عملية واحدة → commit واحد على GitHub مش 17
    if c1.button("💾 احفظ كل النتائج", type="primary", disabled=not filled):
        def _save(x):
            for key, g in collected.items():
                if not g["any"]:
                    continue
                schema.set_result(x, key, g["value"], actor=me()["username"],
                                  note=g["note"], components=g["components"] or None,
                                  critical=g["critical"])
            if gnote.strip():
                x["notes"]["on_result"] = gnote.strip()
        try:
            db.update(req["day"], req["id"], _save)
            st.success(f"اتحفظ {len(filled)} تحليل.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"الحفظ فشل: {e}")

    fresh = db.get(req["day"], req["id"])
    remaining = [t["name"] for t in fresh["tests"] if t["key"] not in fresh["results"]]
    openc = [c for c in fresh.get("critical", []) if c.get("read_back") is None]

    # ── الإبلاغ عن القيم الحرجة ───────────────────────────────────────────
    if openc:
        st.divider()
        st.markdown('<div class="ol-stop"><b>⚠️ قيم حرجة مستنية الإبلاغ</b><br>'
                    'الاعتماد مقفول لحد ما تسجّل الإبلاغ.</div>',
                    unsafe_allow_html=True)
        for c in openc:
            st.markdown(f"**{c['test']} = {c['value']}**")
            if fresh["patient"]["phone"]:
                msg = (f"⚠️ قيمة حرجة — Orange Lab\n{fresh['patient']['name']} "
                       f"(كود {fresh['patient']['lab_code']})\n{c['test']}: {c['value']}")
                st.link_button("📱 بلّغ على واتساب",
                               whatsapp_link(fresh["patient"]["phone"], msg))
            who = st.text_input("مين استلم الإبلاغ؟", key=f"rb_{req['id']}_{c['test']}",
                                placeholder="اسم الطبيب أو الشخص")
            if st.button("سجّل الإبلاغ", key=f"rbb_{req['id']}_{c['test']}",
                         disabled=not who.strip()):
                db.update(req["day"], req["id"], lambda x: schema.record_read_back(
                    x, c["test"], called_by=me()["username"], received_by=who))
                st.success("الإبلاغ اتسجّل.")
                st.rerun()

    # ── الإنهاء والاعتماد ─────────────────────────────────────────────────
    st.divider()
    if remaining:
        st.warning("ناقص: " + "، ".join(remaining))
        return
    if openc:
        return

    if fresh["status"] == schema.IN_PROGRESS and can(P_VERIFY):
        # حساب الفرع عنده الصلاحيتين — خطوة واحدة بدل اتنين
        st.caption("ده هينهي النتائج ويعتمدها، ويخلّي "
                   f"{branch_ar(fresh['origin_branch'])} يقدر ينقلها.")
        if c2.button("✅ إنهاء واعتماد", type="primary"):
            def _fin(x):
                schema.mark_resulted(x, actor=me()["username"], note=gnote)
                schema.mark_verified(x, actor=me()["username"])
            try:
                db.update(req["day"], req["id"], _fin)
                st.success(f"اتعتمدت — {branch_ar(fresh['origin_branch'])} "
                           "يقدر ينقلها دلوقتي.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    elif fresh["status"] == schema.IN_PROGRESS:
        if c2.button("أنهيت كل النتائج", type="primary"):
            try:
                db.update(req["day"], req["id"], lambda x: schema.mark_resulted(
                    x, actor=me()["username"], note=gnote))
                st.success("مستنية اعتماد مدير المعمل.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    elif fresh["status"] == schema.RESULTED:
        if can(P_VERIFY):
            if c2.button("✅ اعتماد إكلينيكي", type="primary"):
                db.update(req["day"], req["id"],
                          lambda x: schema.mark_verified(x, actor=me()["username"]))
                st.success("اتعتمدت.")
                st.rerun()
        else:
            st.info("النتائج كاملة — مستنية اعتماد مدير المعمل.")


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
    mine = [r for r in db.open_requests(b, days_back=14) if r["origin_branch"] == b]
    ready = [r for r in mine if r["status"] == schema.VERIFIED]

    # الطلبات اللي لسه في الطريق — بنقول للمستخدم واقفة فين بالظبط
    # بدل ما نخفيها ونسيبه يتساءل.
    waiting = [r for r in mine if r["status"] in
               (schema.DRAFT, schema.SENT, schema.RECEIVED,
                schema.IN_PROGRESS, schema.RESULTED)]

    if not ready and waiting:
        st.info("مفيش نتيجة جاهزة للنقل دلوقتي — دي حالة الطلبات المفتوحة:")
    elif not ready:
        st.info("مفيش طلبات مفتوحة.")

    if waiting:
        stage = {
            schema.DRAFT: "لسه ماتبعتتش من عندك",
            schema.SENT: "في الطريق — الفرع التاني لسه مستلمش",
            schema.RECEIVED: "اتستلمت — لسه ماتشغّلتش",
            schema.IN_PROGRESS: "تحت التشغيل",
            schema.RESULTED: "النتائج اتكتبت — مستنية الاعتماد",
        }
        with st.expander(f"طلبات لسه شغالة ({len(waiting)})", expanded=not ready):
            for r in waiting:
                done = len(r["results"])
                request_card(r, f" · {stage.get(r['status'],'')}"
                                + (f" ({done}/{len(r['tests'])} نتيجة)" if done else ""))

    if not ready:
        return

    labels = {f"{r['patient']['name']} — {r['patient']['lab_code']}": r for r in ready}
    req = labels[st.selectbox("اختر الطلب", list(labels))]

    request_card(req)

    st.markdown("#### النتائج")
    render_results(req)

    for c in req.get("critical", []):
        rb = c.get("read_back") or {}
        st.markdown(f'<div class="ol-warn">⚠️ <b>{c["test"]} = {c["value"]}</b> — '
                    f'اتبلّغت لـ {rb.get("received_by","—")} '
                    f'في {schema.local_str(rb.get("at",""))}</div>',
                    unsafe_allow_html=True)

    t, w = schema.tat(req), schema.rework(req)
    bits = []
    if t["transit"] is not None:
        bits.append(f"النقل {t['transit']:.0f} د")
    if t["bench"] is not None:
        bits.append(f"التشغيل {t['bench']:.0f} د")
    if not w["first_pass"]:
        bits.append(f"🔁 اتعادت {w['reruns']} مرة")
    if bits:
        st.caption(" · ".join(bits))

    with st.expander("📋 نسخة للّصق في نظامك (Tab-separated)"):
        st.caption("التحليل / القيمة / الوحدة / الملاحظة")
        st.code(schema.as_tsv(req), language=None)

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
    t, w = schema.tat(req), schema.rework(req)
    c = st.columns(4)
    for i, (k, lbl) in enumerate([("transit", "النقل"), ("bench", "التشغيل"),
                                  ("verify", "الاعتماد"), ("total", "الإجمالي")]):
        c[i].metric(lbl, f"{t[k]:.0f} د" if t[k] is not None else "—")
    if not w["first_pass"]:
        extra = (f" · ضاع {w['rework_minutes']:.0f} دقيقة"
                 if w["rework_minutes"] else "")
        st.warning(f"🔁 اتعاد تشغيلها {w['reruns']} مرة"
                   f" · {w['amendments']} تعديل نتيجة{extra}")
        st.caption(f"أول نتيجة طلعت بعد {t['initial_result']:.0f} دقيقة من الاستلام."
                   if t["initial_result"] else "")

    if req["results"]:
        st.markdown("#### النتائج")
        render_results(req)
        with st.expander("📋 نسخة للّصق"):
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
