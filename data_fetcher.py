from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from models import CommentData, PlaylistMetadata, VideoMetadata

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_calls: int, period: int):
        self.max_calls = max_calls
        self.period = period
        self._timestamps: List[float] = []

    async def acquire(self):
        now = time.monotonic()
        self._timestamps = [t for t in self._timestamps if now - t < self.period]
        if len(self._timestamps) >= self.max_calls:
            sleep_for = self._timestamps[0] + self.period - now
            if sleep_for > 0:
                logger.info("Rate limit reached, sleeping %.2fs", sleep_for)
                await asyncio.sleep(sleep_for)
        self._timestamps.append(time.monotonic())


class YouTubeDataFetcher:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = RateLimiter(
            settings.RATE_LIMIT_CALLS, settings.RATE_LIMIT_PERIOD
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.REQUEST_TIMEOUT),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TimeoutException)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def _get(self, endpoint: str, params: Dict) -> Dict:
        client = await self._get_client()
        await self._rate_limiter.acquire()
        params["key"] = self.api_key
        response = await client.get(f"{self.BASE_URL}/{endpoint}", params=params)
        if response.status_code == 429:
            logger.warning("YouTube API 429 rate limit hit, will retry")
        response.raise_for_status()
        return response.json()

    async def search_videos(self, query: str, max_results: int = 50) -> List[str]:
        video_ids: List[str] = []
        page_token: Optional[str] = None

        while len(video_ids) < max_results:
            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": min(50, max_results - len(video_ids)),
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._get("search", params)
            for item in data.get("items", []):
                video_ids.append(item["id"]["videoId"])

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return video_ids[:max_results]

    async def get_video_metadata(self, video_ids: List[str]) -> List[VideoMetadata]:
        results: List[VideoMetadata] = []
        chunk_size = 50

        for i in range(0, len(video_ids), chunk_size):
            chunk = video_ids[i : i + chunk_size]
            params = {
                "part": "snippet,contentDetails,statistics,topicDetails",
                "id": ",".join(chunk),
            }
            data = await self._get("videos", params)

            for item in data.get("items", []):
                metadata = self._parse_video_item(item)
                if metadata:
                    results.append(metadata)

        return results

    def _parse_video_item(self, item: Dict) -> Optional[VideoMetadata]:
        try:
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            content_details = item.get("contentDetails", {})

            duration_iso = content_details.get("duration", "PT0S")
            duration_seconds = self._iso_duration_to_seconds(duration_iso)

            return VideoMetadata(
                video_id=item["id"],
                title=snippet.get("title", ""),
                description=snippet.get("description", ""),
                duration_seconds=duration_seconds,
                view_count=int(statistics.get("viewCount", 0)),
                like_count=int(statistics.get("likeCount", 0)),
                dislike_count=int(statistics.get("dislikeCount", 0)),
                comment_count=int(statistics.get("commentCount", 0)),
                channel_title=snippet.get("channelTitle", ""),
                channel_id=snippet.get("channelId", ""),
                published_at=self._parse_datetime(snippet.get("publishedAt", "")),
                thumbnail_url=(
                    snippet.get("thumbnails", {})
                    .get("high", {})
                    .get("url", "")
                ),
                tags=snippet.get("tags", []),
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse video item: %s", exc)
            return None

    async def get_comments(
        self, video_id: str, max_results: int = 50
    ) -> List[CommentData]:
        comments: List[CommentData] = []
        page_token: Optional[str] = None

        while len(comments) < max_results:
            params = {
                "part": "snippet",
                "videoId": video_id,
                "order": "relevance",
                "maxResults": min(100, max_results - len(comments)),
                "textFormat": "plainText",
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                data = await self._get("commentThreads", params)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 403:
                    logger.warning("Comments disabled for video %s", video_id)
                else:
                    logger.warning(
                        "Failed to fetch comments for %s: %s", video_id, exc
                    )
                break

            for item in data.get("items", []):
                snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                comment = CommentData(
                    comment_id=item["id"],
                    author=snippet.get("authorDisplayName", ""),
                    text=snippet.get("textDisplay", ""),
                    like_count=int(snippet.get("likeCount", 0)),
                    published_at=self._parse_datetime(
                        snippet.get("publishedAt", "")
                    ),
                )
                comments.append(comment)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return comments[:max_results]

    async def fetch_all_comments(
        self, video_ids: List[str], max_comments_per_video: int = 50
    ) -> Dict[str, List[CommentData]]:
        semaphore = asyncio.Semaphore(5)

        async def _fetch(video_id: str) -> Tuple[str, List[CommentData]]:
            async with semaphore:
                comments = await self.get_comments(video_id, max_comments_per_video)
                return video_id, comments

        tasks = [_fetch(vid) for vid in video_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        comments_map: Dict[str, List[CommentData]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Comment fetch task failed: %s", result)
                continue
            video_id, comments = result
            comments_map[video_id] = comments

        return comments_map

    async def search_playlists(self, query: str, max_results: int = 10) -> List[str]:
        playlist_ids: List[str] = []
        page_token: Optional[str] = None

        while len(playlist_ids) < max_results:
            params = {
                "part": "snippet",
                "q": query,
                "type": "playlist",
                "maxResults": min(50, max_results - len(playlist_ids)),
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._get("search", params)
            for item in data.get("items", []):
                playlist_ids.append(item["id"]["playlistId"])

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return playlist_ids[:max_results]

    async def get_playlist_metadata(self, playlist_ids: List[str]) -> List[PlaylistMetadata]:
        results: List[PlaylistMetadata] = []
        chunk_size = 50

        for i in range(0, len(playlist_ids), chunk_size):
            chunk = playlist_ids[i : i + chunk_size]
            params = {
                "part": "snippet,contentDetails",
                "id": ",".join(chunk),
            }
            data = await self._get("playlists", params)

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})
                metadata = PlaylistMetadata(
                    playlist_id=item["id"],
                    title=snippet.get("title", ""),
                    description=snippet.get("description", ""),
                    channel_title=snippet.get("channelTitle", ""),
                    channel_id=snippet.get("channelId", ""),
                    item_count=int(content_details.get("itemCount", 0)),
                    thumbnail_url=(
                        snippet.get("thumbnails", {})
                        .get("high", {})
                        .get("url", "")
                    ),
                )
                results.append(metadata)

        return results

    async def get_playlist_items(
        self, playlist_id: str, max_results: int = 10
    ) -> List[str]:
        video_ids: List[str] = []
        page_token: Optional[str] = None

        while len(video_ids) < max_results:
            params = {
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": min(50, max_results - len(video_ids)),
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._get("playlistItems", params)
            for item in data.get("items", []):
                video_id = item.get("snippet", {}).get("resourceId", {}).get("videoId")
                if video_id:
                    video_ids.append(video_id)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return video_ids[:max_results]

    async def search_playlists_with_details(
        self,
        query: str,
        max_playlists: int = 5,
        videos_per_playlist: int = 5,
        max_comments: int = 20,
    ) -> List[Tuple[PlaylistMetadata, List[VideoMetadata], Dict[str, List[CommentData]]]]:
        playlist_ids = await self.search_playlists(query, max_playlists)
        if not playlist_ids:
            return []

        playlists = await self.get_playlist_metadata(playlist_ids)

        result = []
        for pl in playlists:
            video_ids = await self.get_playlist_items(pl.playlist_id, videos_per_playlist)
            if not video_ids:
                result.append((pl, [], {}))
                continue

            metadata_list = await self.get_video_metadata(video_ids)
            valid_ids = [m.video_id for m in metadata_list]
            comments_map = await self.fetch_all_comments(valid_ids, max_comments)
            result.append((pl, metadata_list, comments_map))

        return result

    async def search_with_details(
        self, query: str, max_videos: int = 50, max_comments: int = 50
    ) -> List[Tuple[VideoMetadata, List[CommentData]]]:
        video_ids = await self.search_videos(query, max_videos)
        if not video_ids:
            return []

        metadata_list = await self.get_video_metadata(video_ids)
        valid_ids = [m.video_id for m in metadata_list]

        comments_map = await self.fetch_all_comments(valid_ids, max_comments)

        result = []
        for meta in metadata_list:
            comments = comments_map.get(meta.video_id, [])
            result.append((meta, comments))

        return result

    @staticmethod
    def _iso_duration_to_seconds(duration: str) -> int:
        import re

        match = re.match(
            r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", duration
        )
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _parse_datetime(dt_str: str) -> datetime:
        from datetime import timezone

        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        return datetime.fromisoformat(dt_str)
