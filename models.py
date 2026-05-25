from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class VideoMetadata(BaseModel):
    video_id: str
    title: str
    description: str
    duration_seconds: int
    view_count: int
    like_count: int
    dislike_count: int
    comment_count: int
    channel_title: str
    channel_id: str
    published_at: datetime
    thumbnail_url: str
    tags: List[str] = []


class CommentData(BaseModel):
    comment_id: str
    author: str
    text: str
    like_count: int
    published_at: datetime
    sentiment_score: Optional[float] = None


class VideoAnalysis(BaseModel):
    video: VideoMetadata
    comments: List[CommentData] = []
    rqs: float = 0.0
    engagement_score: float = 0.0
    sentiment_score: float = 0.0
    clickbait_penalty: float = 0.0
    like_view_ratio: float = 0.0
    comment_view_density: float = 0.0


class PlaylistMetadata(BaseModel):
    playlist_id: str
    title: str
    description: str
    channel_title: str
    channel_id: str
    item_count: int
    thumbnail_url: str
    video_count_analyzed: int = 0


class PlaylistAnalysis(BaseModel):
    playlist: PlaylistMetadata
    videos: List[VideoAnalysis] = []
    rqs: float = 0.0
    avg_engagement_score: float = 0.0
    avg_sentiment_score: float = 0.0


class SearchResponse(BaseModel):
    query: str
    total_results: int
    videos: List[VideoAnalysis] = Field(default_factory=list)
    playlists: List[PlaylistAnalysis] = Field(default_factory=list)
    cached: bool = False
    is_course: bool = False


class ErrorResponse(BaseModel):
    detail: str
    error_code: str
