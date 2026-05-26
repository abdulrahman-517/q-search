# Q-Search 🔍

**YouTube Quality-First Search Engine** — Re-ranks YouTube results by content quality instead of view count.

### ✨ Features

- **RQS™ (Real Quality Score)**: Multi-factor algorithm measuring content quality (like ratio, comment sentiment analysis, keyword matching, clickbait detection, video duration)
- **Smart Search**: Auto-detects between individual video search and playlist search (or manually toggle)
- **Fully Responsive**: Works on mobile, tablet, and desktop
- **Top 5 Only**: Shows only the highest quality results — quality over quantity
- **Arabic First**: Full Arabic interface with one-click English toggle

### 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python + FastAPI |
| Frontend | HTML + CSS + Vanilla JS (single page) |
| API | YouTube Data API v3 |
| NLP | TextBlob + VADER |
| Cache | Redis (optional) |
| Hosting | Render (backend) + Netlify (frontend) |

### 🚀 Local Development

```bash
git clone https://github.com/abdulrahman-517/q-search.git
cd q-search
python -m pip install -r requirements.txt
echo YOUTUBE_API_KEY=your_key_here > .env
python -m uvicorn main:app --reload
```

### ⚙️ RQS Formula

| Weight | Factor |
|--------|--------|
| 30% | Like/View Ratio |
| 25% | Comment Content Value |
| 15% | Title Keyword Match |
| 10% | Comment Sentiment |
| 10% | Duration Score |
| 10% | Quality (Clickbait Penalty + Educational Boost) |

### 🌐 Deployment

- **Backend**: [Render](https://render.com) — `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Frontend**: [Netlify](https://netlify.com) — Drag `static/` folder to Netlify Drop

---

**Q-Search v1.0** — Search smarter, not by views.
