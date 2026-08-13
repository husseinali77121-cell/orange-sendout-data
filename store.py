# -*- coding: utf-8 -*-
"""
Orange Lab — Inter-Branch Send-Out System
store.py — التخزين (GitHub JSON، ملف لكل يوم)

⚠️ المشكلة اللي الملف ده بيحلّها:
ملف واحد لليوم معناه إن الفرعين بيكتبوا في نفس الملف. لو دياموند بيسجّل طلب
جديد ولاسيتيه بتحفظ نتيجة في نفس اللحظة → الـ SHA بيختلف → GitHub بيرجّع 409
→ واحد من الاتنين بيضيع من غير ما حد ياخد باله.

الحل: mutate() مش save(). بنبعت *دالة تعديل* مش النسخة الكاملة.
لو حصل 409 بنقرا الملف من الأول ونعيد تطبيق التعديل على النسخة الجديدة.
لإن كل تعديل بيمس record واحد بس، إعادة التطبيق آمنة تماماً.

⛔ ماتعدّلش الدالة _put_with_retry من غير إذن صريح — دي حماية فقدان البيانات.
"""

from __future__ import annotations

import base64
import json
import os
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import schema

DATA_DIR = "data/sendouts"
MAX_RETRIES = 6
_LOCK = threading.Lock()   # حماية داخل نفس الـ process


class StoreError(Exception):
    pass


class ConflictError(StoreError):
    pass


def _empty_day(day: str) -> Dict[str, Any]:
    return {"schema_version": schema.SCHEMA_VERSION, "day": day, "requests": {}}


def _path(day: str) -> str:
    return f"{DATA_DIR}/{day}.json"


# ══════════════════════════════════════════════════════════════════════════
# Backend: ملفات محلية (للتطوير والاختبار وكـ offline fallback)
# ══════════════════════════════════════════════════════════════════════════

class LocalBackend:
    def __init__(self, root: str = "."):
        self.root = root

    def _abs(self, day):
        return os.path.join(self.root, _path(day))

    def read(self, day):
        p = self._abs(day)
        if not os.path.exists(p):
            return _empty_day(day), None
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data, str(os.path.getmtime(p))

    def write(self, day, data, sha):
        p = self._abs(day)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        cur = str(os.path.getmtime(p)) if os.path.exists(p) else None
        if sha is not None and cur is not None and sha != cur:
            raise ConflictError("الملف اتغيّر")
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)          # كتابة ذرّية
        return str(os.path.getmtime(p))

    def list_days(self):
        d = os.path.join(self.root, DATA_DIR)
        if not os.path.isdir(d):
            return []
        return sorted((f[:-5] for f in os.listdir(d) if f.endswith(".json")),
                      reverse=True)


# ══════════════════════════════════════════════════════════════════════════
# Backend: GitHub Contents API
# ══════════════════════════════════════════════════════════════════════════

class GitHubBackend:
    def __init__(self, token: str, repo: str, branch: str = "main"):
        if not token or not repo:
            raise StoreError("github_token و github_repo مطلوبين")
        self.token, self.repo, self.branch = token, repo, branch
        self.api = f"https://api.github.com/repos/{repo}/contents"

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    def read(self, day):
        import requests
        r = requests.get(f"{self.api}/{_path(day)}",
                         headers=self._headers(),
                         params={"ref": self.branch}, timeout=25)
        if r.status_code == 404:
            return _empty_day(day), None
        if r.status_code != 200:
            raise StoreError(f"قراءة فشلت [{r.status_code}]: {r.text[:200]}")
        j = r.json()
        raw = base64.b64decode(j["content"]).decode("utf-8")
        return json.loads(raw), j["sha"]

    def write(self, day, data, sha):
        import requests
        body = {
            "message": f"sendout: {day} @ {schema.now_iso()}",
            "content": base64.b64encode(
                json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            ).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            body["sha"] = sha
        r = requests.put(f"{self.api}/{_path(day)}",
                         headers=self._headers(), json=body, timeout=25)
        if r.status_code in (409, 422):
            raise ConflictError(f"تعارض [{r.status_code}]")
        if r.status_code not in (200, 201):
            raise StoreError(f"كتابة فشلت [{r.status_code}]: {r.text[:200]}")
        return r.json()["content"]["sha"]

    def list_days(self):
        import requests
        r = requests.get(f"{self.api}/{DATA_DIR}", headers=self._headers(),
                         params={"ref": self.branch}, timeout=25)
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            raise StoreError(f"فهرسة فشلت [{r.status_code}]")
        return sorted((it["name"][:-5] for it in r.json()
                       if it["name"].endswith(".json")), reverse=True)


# ══════════════════════════════════════════════════════════════════════════
# الواجهة
# ══════════════════════════════════════════════════════════════════════════

class Store:
    def __init__(self, backend):
        self.backend = backend

    # ── القلب: mutate بدل save ────────────────────────────────────────────
    def mutate(self, day: str, fn: Callable[[Dict[str, Any]], Any]) -> Any:
        """
        fn بتاخد dict اليوم وتعدّله in-place وترجّع أي حاجة تحبها.
        لو حصل تعارض، بنقرا من الأول ونستدعي fn تاني على النسخة الجديدة.

        ⚠️ لازم fn تبقى قابلة لإعادة التنفيذ (idempotent-ish) — يعني
        متعملش حاجة ليها أثر خارجي (زي إرسال واتساب) جواها.
        """
        with _LOCK:
            last = None
            for attempt in range(MAX_RETRIES):
                data, sha = self.backend.read(day)
                data.setdefault("requests", {})
                result = fn(data)
                try:
                    self.backend.write(day, data, sha)
                    return result
                except ConflictError as e:
                    last = e
                    # backoff عشوائي — يمنع الفرعين من إعادة المحاولة معاً
                    time.sleep(min(0.4 * (2 ** attempt), 5) * (0.5 + random.random()))
            raise ConflictError(
                f"فشل بعد {MAX_RETRIES} محاولات — جرّب تاني بعد شوية ({last})"
            )

    # ── عمليات ────────────────────────────────────────────────────────────
    def create(self, req: Dict[str, Any]) -> str:
        day = req["day"]

        def _fn(data):
            if req["id"] in data["requests"]:
                raise StoreError(f"الـ ID موجود بالفعل: {req['id']}")
            data["requests"][req["id"]] = req
            return req["id"]

        return self.mutate(day, _fn)

    def update(self, day: str, rid: str,
               apply_fn: Callable[[Dict[str, Any]], Any]) -> Dict[str, Any]:
        """
        apply_fn بتاخد الـ request وتعدّله.
        بترجّع النسخة المحفوظة فعلاً — مش النسخة اللي كانت في السيشن.
        """
        def _fn(data):
            r = data["requests"].get(rid)
            if r is None:
                raise StoreError(f"الطلب مش موجود: {rid}")
            apply_fn(r)
            return r

        return self.mutate(day, _fn)

    def get(self, day: str, rid: str) -> Optional[Dict[str, Any]]:
        data, _ = self.backend.read(day)
        return data.get("requests", {}).get(rid)

    def list_day(self, day: str) -> List[Dict[str, Any]]:
        data, _ = self.backend.read(day)
        return sorted(data.get("requests", {}).values(),
                      key=lambda r: r.get("created_at", ""), reverse=True)

    def list_days(self) -> List[str]:
        return self.backend.list_days()

    def find(self, rid: str, days_back: int = 30) -> Optional[Dict[str, Any]]:
        """بحث بالـ ID عبر الأيام — الـ ID نفسه فيه التاريخ فبنجرّبه الأول."""
        parts = rid.split("-")
        if len(parts) >= 3 and len(parts[2]) == 8:
            d = f"{parts[2][:4]}-{parts[2][4:6]}-{parts[2][6:]}"
            r = self.get(d, rid)
            if r:
                return r
        for d in self.list_days()[:days_back]:
            r = self.get(d, rid)
            if r:
                return r
        return None

    def open_requests(self, branch: str, days_back: int = 7) -> List[Dict[str, Any]]:
        """الطلبات المفتوحة الخاصة بفرع معيّن (كمُرسِل أو كمُنفِّذ)."""
        out = []
        for d in self.list_days()[:days_back]:
            for r in self.list_day(d):
                if r["status"] in schema.TERMINAL:
                    continue
                if branch in (r["origin_branch"], r["performing_branch"]):
                    out.append(r)
        return out

    def patient_history(self, pkey: str, days_back: int = 180) -> List[Dict[str, Any]]:
        """تاريخ نتائج المريض — للـ delta check."""
        out = []
        for d in self.list_days()[:days_back]:
            for r in self.list_day(d):
                if r.get("patient", {}).get("key") == pkey and r.get("results"):
                    out.append(r)
        return out

    def previous_value(self, pkey: str, test_key: str, exclude_id: str = ""):
        """آخر قيمة سابقة لنفس المريض ونفس التحليل."""
        for r in self.patient_history(pkey):
            if r["id"] == exclude_id:
                continue
            res = r["results"].get(test_key)
            if res and res.get("value") not in (None, ""):
                return res["value"], r["created_at"]
        return None, None


# ── إنشاء الـ store من إعدادات Streamlit ─────────────────────────────────

def from_secrets(secrets: dict, local_root: str = ".") -> Store:
    tok = secrets.get("github_token")
    repo = secrets.get("github_repo")
    if tok and repo:
        return Store(GitHubBackend(tok, repo, secrets.get("github_branch", "main")))
    return Store(LocalBackend(local_root))
