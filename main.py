from __future__ import annotations

import json
import logging
import re
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from config import settings
from data_fetcher import YouTubeDataFetcher
from models import (
    ErrorResponse,
    PlaylistAnalysis,
    SearchResponse,
    VideoAnalysis,
)
from quality_analyzer import QualityAnalyzer

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

fetcher: Optional[YouTubeDataFetcher] = None
analyzer: Optional[QualityAnalyzer] = None
cache: Optional[redis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global fetcher, analyzer, cache
    import nltk
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)
    try:
        nltk.data.find("sentiment/vader_lexicon")
    except LookupError:
        nltk.download("vader_lexicon", quiet=True)
    try:
        nltk.data.find("taggers/averaged_perceptron_tagger")
    except LookupError:
        nltk.download("averaged_perceptron_tagger", quiet=True)
    fetcher = YouTubeDataFetcher(api_key=settings.YOUTUBE_API_KEY)
    analyzer = QualityAnalyzer()
    if settings.CACHE_ENABLED:
        try:
            cache = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True,
            )
            await cache.ping()
            logger.info("Redis cache connected")
        except Exception as exc:
            logger.warning("Redis unavailable, running without cache: %s", exc)
            cache = None
    yield
    if fetcher:
        await fetcher.close()
    if cache:
        await cache.aclose()


app = FastAPI(
    title="Q-Search: YouTube Quality-First Search Engine",
    version="1.0.0",
    description="Re-ranks YouTube search results by Real Quality Score (RQS)",
    lifespan=lifespan,
)


def get_search_type(query: str) -> str:
    stripped = query.strip().lower()
    if stripped.startswith(("كورس", "دورة", "course")):
        return "playlist"
    return "video"


def _build_cache_key(query: str) -> str:
    return f"qsearch:{query.lower().strip()}"


@app.get(
    "/search",
    response_model=SearchResponse,
    responses={429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def search(
    query: str = Query(..., min_length=1, max_length=200, description="Search query"),
    min_rqs: float = Query(
        0.45, ge=0.0, le=1.0, description="Minimum RQS threshold (0.0 to 1.0)"
    ),
):
    if not settings.YOUTUBE_API_KEY:
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "YouTube API key not configured",
                "error_code": "CONFIG_ERROR",
            },
        )

    search_type = get_search_type(query)
    cache_key = _build_cache_key(query)

    if cache:
        try:
            cached_data = await cache.get(cache_key)
            if cached_data:
                cached_obj = json.loads(cached_data)
                logger.info("Cache hit for query: %s", query)
                return SearchResponse(
                    query=query,
                    total_results=cached_obj.get("total", 0),
                    videos=[VideoAnalysis.model_validate(v) for v in cached_obj.get("videos", [])],
                    playlists=[PlaylistAnalysis.model_validate(p) for p in cached_obj.get("playlists", [])],
                    cached=True,
                    is_course=search_type == "playlist",
                )
        except Exception as exc:
            logger.warning("Cache read error: %s", exc)

    logger.info("Fetching fresh results for query: %s (type=%s)", query, search_type)

    if search_type == "playlist":
        try:
            raw_playlists = await fetcher.search_playlists_with_details(
                query=query,
                max_playlists=5,
                videos_per_playlist=5,
                max_comments=settings.MAX_COMMENTS,
            )
        except Exception as exc:
            logger.exception("Failed to fetch YouTube playlists")
            raise HTTPException(
                status_code=502,
                detail={
                    "detail": f"Failed to fetch playlists from YouTube API: {exc}",
                    "error_code": "FETCH_ERROR",
                },
            )

        playlist_analyses = []
        for pl, videos, comments_map in raw_playlists:
            analysis = analyzer.analyze_playlist(pl, videos, comments_map, search_query=query)
            playlist_analyses.append(analysis)

        playlist_analyses.sort(key=lambda x: x.rqs, reverse=True)
        top_playlists = [p for p in playlist_analyses if p.rqs >= min_rqs][:5]

        if cache:
            try:
                await cache.setex(
                    cache_key,
                    settings.REDIS_TTL,
                    json.dumps({
                        "total": len(top_playlists),
                        "videos": [],
                        "playlists": [p.model_dump() for p in top_playlists],
                    }),
                )
            except Exception as exc:
                logger.warning("Cache write error: %s", exc)

        return SearchResponse(
            query=query,
            total_results=len(top_playlists),
            videos=[],
            playlists=top_playlists,
            cached=False,
            is_course=True,
        )

    try:
        raw_results = await fetcher.search_with_details(
            query=query,
            max_videos=15,
            max_comments=settings.MAX_COMMENTS,
        )
    except Exception as exc:
        logger.exception("Failed to fetch YouTube data")
        raise HTTPException(
            status_code=502,
            detail={
                "detail": f"Failed to fetch data from YouTube API: {exc}",
                "error_code": "FETCH_ERROR",
            },
        )

    analyzed: list[VideoAnalysis] = []
    for metadata, comments in raw_results:
        analysis = analyzer.analyze(metadata, comments, search_query=query)
        analyzed.append(analysis)

    analyzed.sort(key=lambda x: x.rqs, reverse=True)
    top_videos = [v for v in analyzed if v.rqs >= min_rqs][:5]

    if cache:
        try:
            await cache.setex(
                cache_key,
                settings.REDIS_TTL,
                json.dumps({
                    "total": len(top_videos),
                    "videos": [v.model_dump() for v in top_videos],
                    "playlists": [],
                }),
            )
        except Exception as exc:
            logger.warning("Cache write error: %s", exc)

    return SearchResponse(
        query=query,
        total_results=len(top_videos),
        videos=top_videos,
        playlists=[],
        cached=False,
        is_course=False,
    )


@app.get("/debug-search")
async def debug_search(query: str = "test"):
    try:
        raw_results = await fetcher.search_with_details(
            query=query, max_videos=3, max_comments=5
        )
        return {"step": "search_ok", "count": len(raw_results)}
    except Exception as e:
        return {"step": "search_failed", "error": str(e), "type": type(e).__name__}


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    status = {"status": "healthy", "cache_enabled": cache is not None}
    if cache:
        try:
            await cache.ping()
            status["cache_connected"] = True
        except Exception:
            status["cache_connected"] = False
    return status
