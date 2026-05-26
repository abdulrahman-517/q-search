# Q-Search 🔍

**YouTube Quality-First Search Engine** — يعيد ترتيب نتائج يوتيوب حسب جودة المحتوى الحقيقية بدلاً من المشاهدات.

### ✨ الميزات

- **RQS™ (Real Quality Score)**: خوارزمية تقيس الجودة الحقيقية للمحتوى (نسبة الإعجابات، تحليل المشاعر في التعليقات، مطابقة الكلمات المفتاحية، كشف clickbait، مدة الفيديو)
- **بحث ذكي**: اختيار تلقائي بين البحث في المقاطع الفردية أو قوائم التشغيل
- **دعم كامل للعربية**: واجهة بالعربية مع إمكانية التبديل للإنجليزية
- **نتائج محدّثة**: 5 نتائج فقط — الأفضل حسب الجودة وليس الكمية
- **تصميم متجاوب**: يعمل على الجوال والتابعت واللابتوب

### 🛠 التقنيات

| الطبقة | التقنية |
|--------|---------|
| Backend | Python + FastAPI |
| Frontend | HTML + CSS + JS (صفحة واحدة) |
| API | YouTube Data API v3 |
| تحليل النصوص | TextBlob + VADER |
| تخزين مؤقت | Redis (اختياري) |
| استضافة | Render (backend) + Netlify (frontend) |

### 🚀 التشغيل المحلي

```bash
git clone https://github.com/abdulrahman-517/q-search.git
cd q-search
python -m pip install -r requirements.txt
echo YOUTUBE_API_KEY=your_key_here > .env
python -m uvicorn main:app --reload
```

### ⚙️ RQS Score

- **30%** — Like/View Ratio
- **25%** — Comment Content Value
- **15%** — Title Keyword Match
- **10%** — Comment Sentiment
- **10%** — Duration Score
- **10%** — Quality (Clickbait Penalty + Educational Boost)

### 🌐 النشر

- **Backend**: [Render](https://render.com) — `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Frontend**: [Netlify](https://netlify.com) — رفع مجلد `static/`

---

**Q-Search v1.0** — ابحث بذكاء، لا بالمشاهدات.
