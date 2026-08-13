# Orange Lab — نظام تبادل العينات بين الفروع

## ⭐ ملف الـ deploy الرئيسي: `app.py`

## الملفات
| الملف | الدور | Streamlit؟ |
|---|---|---|
| **`app.py`** | **الواجهة — نقطة الدخول** | ✅ **ده اللي بيتعمله deploy** |
| `catalog.py` | قاموس التحاليل (40 تحليل) | ❌ |
| `schema.py` | الـ state machine + الثبات | ❌ |
| `store.py` | التخزين على GitHub | ❌ |
| `make_hash.py` | مولّد كلمات المرور (سطر أوامر) | ❌ |
| `test_sendout.py` | 52 اختبار | ❌ |

## التشغيل

```bash
pip install -r requirements.txt
python make_hash.py                # اعمل المستخدمين، الزق الناتج في secrets
streamlit run app.py
```

## `.streamlit/secrets.toml`

```toml
password_salt = "..."              # من make_hash.py — لا تغيّرها بعد كده

github_token  = "ghp_..."          # اختياري: من غيرهم بيحفظ محلياً
github_repo   = "username/orange-sendout-data"
github_branch = "main"

[users.hussein]
name = "حسين علي"
branch = "DIAMOND"                 # DIAMOND أو LACITE
role = "admin"                     # reception / tech / director / admin
password_hash = "..."
```

## الأدوار
| الدور | الصلاحيات |
|---|---|
| `reception` | إنشاء · إرسال · نقل وقفل |
| `tech` | استلام · رفض · إدخال نتائج |
| `director` | كل حاجة + الاعتماد الإكلينيكي |
| `admin` | كل حاجة |

**ليه دخول فردي مش باسورد فرع؟** ISO 15189:2022 عايز يعرف مين عمل التحليل
ومين راجعه **بالاسم**. الباسورد المشترك بيلغي المساءلة دي.

## الاختبارات
```bash
python test_sendout.py             # 52 اختبار
```

## قرارات محفورة في الكود
- **مفيش reference ranges** — نظام الفرع المرسِل هو مصدر الحقيقة الوحيد
- **الجلوكوز على سيرم عادي** — الـ NaF بيثبّط enolase (متأخر في السلسلة)
  فمابيمنعش النزول في أول ساعة. زمن النقل هو المتغيّر الحقيقي.
  عدّل `GLUCOSE_STABILITY_HOURS` في `catalog.py` لما تجمع بيانات فعلية.
- **الـ PTT ثباته 4 ساعات** — الاستلام بيتمنع بعدها، والتجاوز بيتسجّل بالاسم
- **ملف لكل يوم** — الأمان من `store.mutate()` مش من تقسيم الملفات

## ⛔ ماتعدلش من غير مراجعة
`store._put_with_retry` / `Store.mutate` — دي حماية فقدان البيانات وقت
الكتابة المتزامنة من الفرعين.
