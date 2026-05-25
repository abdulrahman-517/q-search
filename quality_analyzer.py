from __future__ import annotations

import logging
import math
import re
from typing import List, Optional

from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from models import CommentData, PlaylistAnalysis, PlaylistMetadata, VideoAnalysis, VideoMetadata

logger = logging.getLogger(__name__)


class TitleKeywordMatcher:
    STOP_WORDS = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "and",
        "or", "is", "are", "was", "were", "be", "been", "it", "its",
        "this", "that", "with", "from", "by", "as", "but", "not",
        "في", "على", "إلى", "من", "عن", "مع", "كان", "هذا", "هذه",
        "ذلك", "تلك", "و", "أو", "ثم", "لا", "ما", "لم", "لن",
    }

    def __init__(self, search_query: str):
        self._query_tokens = self._tokenize(search_query)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        tokens = text.split()
        return {t for t in tokens if t not in TitleKeywordMatcher.STOP_WORDS and len(t) > 1}

    def score_title(self, title: str) -> float:
        if not self._query_tokens:
            return 0.0
        title_tokens = self._tokenize(title)
        if not title_tokens:
            return 0.0
        matches = self._query_tokens & title_tokens
        if not matches:
            return 0.0
        coverage = len(matches) / len(self._query_tokens)
        return min(coverage * 1.5, 1.0)

    def score_description(self, description: str) -> float:
        if not self._query_tokens:
            return 0.0
        desc_tokens = self._tokenize(description)
        if not desc_tokens:
            return 0.0
        matches = self._query_tokens & desc_tokens
        if not matches:
            return 0.0
        coverage = len(matches) / len(self._query_tokens)
        return min(coverage * 0.8, 0.5)


class ContentValueDetector:
    EDUCATIONAL_KEYWORDS = {
        "learned", "learnt", "understanding", "understand", "explained",
        "explanation", "tutorial", "course", "lesson", "lecture",
        "educational", "informative", "useful", "helpful",
        "great explanation", "well explained", "clear explanation",
        "easy to understand", "thanks for", "thank you for",
        "finally understand", "helped me", "amazing explanation",
        "perfect explanation", "best tutorial", "highly recommend",
        "excellent content", "great course", "well structured",
        "شرح", "كورس", "درس", "دورة", "تعلمت", "فهمت",
        "استفدت", "مفيد", "شكرا", "شكراً", "ممتاز",
        "رائع", "جميل", "أفضل", "مفيد جدا", "درس رائع", "شرح رائع",
        "بارك الله", "نفع الله", "ما شاء الله", "مبدع", "ابداع",
        "جزاك الله", "أحسن", "نصائح", "خبرة", "احترافي",
        "واضح", "مفهوم", "بسيط", "منظم", "مكتمل", "شامل",
        "صبر", "أسلوب", "مشروح", "منهجي", "قيم", "راقي",
        "تستاهل", "نجمة", "full course", "complete", "beginner friendly",
        "recommended", "must watch", "quality content",
    }

    CLICKBAIT_KEYWORDS = {
        "shocking", "unbelievable", "you won't believe", "mind blowing",
        "crazy", "insane", "epic", "incredible", "stunning",
        "jaw-dropping", "never seen before", "destroyed", "savage",
        "gone wrong", "gone sexual", "will make you", "changed my life",
        "secret", "exposed", "they don't want you to know", "must see",
        "you need to see", "this is why", "the truth about", "what happens",
        "i can't believe", "omg", "wtf", "literally", "best ever",
        "worst ever", "number one", "top 10", "you'll never guess",
        "افضح", "فضيحة", "صادم", "لن تصدق", "سر", "خفي", "كارثة",
        "هتجنن", "مش هتصدق", "أقوى", "أسوأ", "أغرب", "أضخم",
    }

    NEGATIVE_CONTENT_KEYWORDS = {
        "boring", "confusing", "waste of time", "not helpful",
        "disappointed", "bad explanation", "poor quality", "terrible",
        "useless", "not clear", "difficult to follow", "skip",
        "ممل", "ما فهمت", "سيء", "ضعيف", "مضيعة وقت",
        "خسارة", "غير مفيد", "معقد", "كلام فاضي", "تعبان",
        "نصب", "خايس", "زفت", "رديء", "فاشل", "غير مفهوم",
    }

    def __init__(self):
        self._educational = re.compile(
            "|".join(re.escape(w) for w in self.EDUCATIONAL_KEYWORDS),
            re.IGNORECASE,
        )
        self._clickbait = re.compile(
            "|".join(re.escape(w) for w in self.CLICKBAIT_KEYWORDS),
            re.IGNORECASE,
        )
        self._negative = re.compile(
            "|".join(re.escape(w) for w in self.NEGATIVE_CONTENT_KEYWORDS),
            re.IGNORECASE,
        )

    def analyze_comments(
        self, comments: List[CommentData]
    ) -> tuple[float, float, float]:
        if not comments:
            return 0.0, 0.0, 0.0

        edu_score = 0.0
        cb_score = 0.0
        neg_score = 0.0
        total_weight = 0

        for comment in comments:
            text = comment.text
            weight = 1 + math.log1p(comment.like_count)
            comment_length = len(text.strip())

            long_comment_bonus = 1.0
            if comment_length > 50:
                long_comment_bonus = 1.5
            if comment_length > 100:
                long_comment_bonus = 2.0

            effective_weight = weight * long_comment_bonus
            total_weight += effective_weight

            edu_matches = self._educational.findall(text)
            if edu_matches:
                edu_score += len(edu_matches) * 0.5 * effective_weight

            cb_matches = self._clickbait.findall(text)
            if cb_matches:
                cb_score += len(cb_matches) * 0.4 * effective_weight

            neg_matches = self._negative.findall(text)
            if neg_matches:
                neg_score += len(neg_matches) * 0.6 * effective_weight

        if total_weight == 0:
            return 0.5, 0.0, 0.0

        content_value = min(edu_score / total_weight, 1.0)
        clickbait_signal = min(cb_score / total_weight, 1.0)
        negative_signal = min(neg_score / total_weight, 1.0)

        return content_value, clickbait_signal, negative_signal

    def analyze_title(self, title: str) -> tuple[float, float]:
        title_lower = title.lower()
        edu_score = 0.0
        cb_score = 0.0

        edu_matches = self._educational.findall(title_lower)
        cb_matches = self._clickbait.findall(title_lower)

        if edu_matches:
            edu_score = min(len(edu_matches) * 0.2, 0.5)

        if cb_matches:
            cb_score = min(len(cb_matches) * 0.25, 0.6)

        ALL_CAPS_PATTERN = re.compile(r"\b[A-Z]{4,}\b")
        caps = ALL_CAPS_PATTERN.findall(title)
        if caps:
            cb_score += min(len(caps) * 0.1, 0.2)

        EXCESSIVE_PUNCTUATION = re.compile(r"[!?]{2,}")
        punct = EXCESSIVE_PUNCTUATION.findall(title)
        if punct:
            cb_score += min(len(punct) * 0.1, 0.2)

        return edu_score, min(cb_score, 1.0)


class SentimentEngine:
    def __init__(self):
        self._vader = SentimentIntensityAnalyzer()

    def analyze_text(self, text: str) -> float:
        vader_scores = self._vader.polarity_scores(text)
        vader_compound = vader_scores["compound"]

        blob = TextBlob(text)
        tb_polarity = blob.sentiment.polarity

        combined = (vader_compound + tb_polarity) / 2
        normalized = (combined + 1) / 2
        return max(0.0, min(1.0, normalized))

    def analyze_comments(self, comments: List[CommentData]) -> float:
        if not comments:
            return 0.5

        scores = []
        for comment in comments:
            score = self.analyze_text(comment.text)
            scores.append(score)

        if not scores:
            return 0.5

        mean_score = sum(scores) / len(scores)

        like_weighted = sum(
            s * (1 + math.log1p(c.like_count))
            for s, c in zip(scores, comments)
        )
        total_weight = sum(1 + math.log1p(c.like_count) for c in comments)
        weighted_score = like_weighted / total_weight if total_weight > 0 else mean_score

        return max(0.0, min(1.0, weighted_score))


class Scorer:
    @staticmethod
    def like_view_ratio(like_count: int, view_count: int) -> float:
        if view_count <= 0:
            return 0.0
        ratio = like_count / view_count
        return min(ratio * 100, 1.0)

    @staticmethod
    def comment_view_density(comment_count: int, view_count: int) -> float:
        if view_count <= 0:
            return 0.0
        density = comment_count / view_count
        return min(density * 50, 1.0)

    @staticmethod
    def duration_score(duration_seconds: int) -> float:
        if duration_seconds <= 0:
            return 0.0

        if duration_seconds < 180:
            return max(0.1, duration_seconds / 180)

        if 180 <= duration_seconds < 300:
            return 0.6 + (duration_seconds - 180) / 300

        if 300 <= duration_seconds <= 900:
            return 1.0

        if 900 < duration_seconds <= 3600:
            return 1.0 - (duration_seconds - 900) / 5400

        if 3600 < duration_seconds <= 7200:
            return max(0.4, 0.7 - (duration_seconds - 3600) / 12000)

        return 0.3


class QualityAnalyzer:
    def __init__(self):
        self.sentiment_engine = SentimentEngine()
        self.content_detector = ContentValueDetector()
        self.scorer = Scorer()

    def analyze(
        self,
        metadata: VideoMetadata,
        comments: Optional[List[CommentData]] = None,
        search_query: str = "",
    ) -> VideoAnalysis:
        comments = comments or []

        for comment in comments:
            comment.sentiment_score = self.sentiment_engine.analyze_text(comment.text)

        sentiment_score = self.sentiment_engine.analyze_comments(comments)

        content_value, comment_clickbait, comment_negative = self.content_detector.analyze_comments(comments)
        title_edu, title_cb = self.content_detector.analyze_title(metadata.title)

        clickbait_penalty = max(title_cb, comment_clickbait)
        negative_penalty = comment_negative

        lv_ratio = self.scorer.like_view_ratio(metadata.like_count, metadata.view_count)
        duration_score = self.scorer.duration_score(metadata.duration_seconds)

        matcher = TitleKeywordMatcher(search_query)
        title_match_score = matcher.score_title(metadata.title)
        desc_match_score = matcher.score_description(metadata.description)
        title_relevance = max(title_match_score, desc_match_score)

        rqs = self._compute_rqs(
            like_view_ratio=lv_ratio,
            content_value_score=content_value,
            title_relevance=title_relevance,
            sentiment_score=sentiment_score,
            duration_score=duration_score,
            clickbait_penalty=clickbait_penalty,
            negative_penalty=negative_penalty,
            title_edu_boost=title_edu,
        )

        return VideoAnalysis(
            video=metadata,
            comments=comments,
            rqs=round(rqs, 4),
            engagement_score=round(cv_density, 4),
            sentiment_score=round(sentiment_score, 4),
            clickbait_penalty=round(clickbait_penalty, 4),
            like_view_ratio=round(lv_ratio, 6),
            comment_view_density=round(cv_density, 6),
        )

    def analyze_playlist(
        self,
        playlist: PlaylistMetadata,
        videos: List[VideoMetadata],
        comments_map: dict,
        search_query: str = "",
    ) -> PlaylistAnalysis:
        video_analyses = []
        rqs_sum = 0.0
        engagement_sum = 0.0
        sentiment_sum = 0.0
        count = 0

        for v in videos:
            comments = comments_map.get(v.video_id, [])
            analysis = self.analyze(v, comments, search_query)
            video_analyses.append(analysis)
            rqs_sum += analysis.rqs
            engagement_sum += analysis.engagement_score
            sentiment_sum += analysis.sentiment_score
            count += 1

        avg_rqs = rqs_sum / count if count > 0 else 0.0

        return PlaylistAnalysis(
            playlist=playlist,
            videos=video_analyses,
            rqs=round(avg_rqs, 4),
            avg_engagement_score=round(engagement_sum / count, 4) if count > 0 else 0.0,
            avg_sentiment_score=round(sentiment_sum / count, 4) if count > 0 else 0.0,
        )

    def _compute_rqs(
        self,
        like_view_ratio: float,
        content_value_score: float,
        title_relevance: float,
        sentiment_score: float,
        duration_score: float,
        clickbait_penalty: float,
        negative_penalty: float = 0.0,
        title_edu_boost: float = 0.0,
    ) -> float:
        w_like_view = 0.30
        w_content_value = 0.25
        w_title = 0.15
        w_sentiment = 0.10
        w_duration = 0.10
        w_quality = 0.10

        quality_score = max(0.0, 1.0 - clickbait_penalty - negative_penalty)
        educational_boost = min(title_edu_boost * 2, 1.0)
        quality_component = quality_score * 0.5 + educational_boost * 0.5

        rqs = (
            w_like_view * like_view_ratio
            + w_content_value * content_value_score
            + w_title * title_relevance
            + w_sentiment * sentiment_score
            + w_duration * duration_score
            + w_quality * quality_component
        )
        return max(0.0, min(1.0, rqs))
