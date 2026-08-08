"""YouTube URL parsing, transcript retrieval, and timestamp-aware chunking."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import parse_qs, urlparse

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from requests import RequestException
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import CouldNotRetrieveTranscript
from youtube_transcript_api.proxies import WebshareProxyConfig

from app.config import Settings

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {
    "youtu.be",
    "youtube.com",
    "youtube-nocookie.com",
}
PATH_ID_PREFIXES = {"embed", "live", "shorts", "v"}


class InvalidYouTubeURL(ValueError):
    """Raised when input does not identify a supported YouTube video."""


class TranscriptServiceError(RuntimeError):
    """A safe transcript error that may be returned to an API client."""


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    text: str
    start: float
    duration: float


@dataclass(frozen=True, slots=True)
class TranscriptResult:
    segments: tuple[TranscriptSegment, ...]
    language_code: str
    is_generated: bool


def extract_video_id(value: str) -> str:
    """Extract an 11-character ID from common YouTube URL forms."""

    candidate = value.strip()
    if VIDEO_ID_PATTERN.fullmatch(candidate):
        return candidate

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    is_youtube_host = hostname in YOUTUBE_HOSTS or any(
        hostname.endswith(f".{host}") for host in YOUTUBE_HOSTS
    )
    if not is_youtube_host:
        raise InvalidYouTubeURL("Enter a valid YouTube video URL")

    path_parts = [part for part in parsed.path.split("/") if part]
    video_id: str | None = None

    if hostname == "youtu.be" and path_parts:
        video_id = path_parts[0]
    elif path_parts and path_parts[0].lower() in PATH_ID_PREFIXES:
        if len(path_parts) > 1:
            video_id = path_parts[1]
    elif parsed.path.rstrip("/") == "/watch":
        values = parse_qs(parsed.query).get("v", [])
        if values:
            video_id = values[0]

    if video_id and VIDEO_ID_PATTERN.fullmatch(video_id):
        return video_id
    raise InvalidYouTubeURL("Enter a valid YouTube video URL")


class TranscriptService:
    """Fetch and chunk transcripts without exposing provider error details."""

    def __init__(
        self,
        settings: Settings,
        *,
        fetcher: Callable[[str], TranscriptResult] | None = None,
    ) -> None:
        self.settings = settings
        self._fetcher = fetcher
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.transcript_chunk_size,
            chunk_overlap=settings.transcript_chunk_overlap,
            add_start_index=True,
            separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
        )

    def fetch(self, video_id: str) -> TranscriptResult:
        if self._fetcher is not None:
            return self._fetcher(video_id)

        api_options: dict[str, object] = {}
        if (
            self.settings.transcript_proxy_username
            and self.settings.transcript_proxy_password
        ):
            api_options["proxy_config"] = WebshareProxyConfig(
                proxy_username=self.settings.transcript_proxy_username,
                proxy_password=(
                    self.settings.transcript_proxy_password.get_secret_value()
                ),
            )

        try:
            transcript = YouTubeTranscriptApi(**api_options).fetch(
                video_id,
                languages=self.settings.transcript_language_list,
            )
        except CouldNotRetrieveTranscript as exc:
            error_name = type(exc).__name__
            if error_name in {"IpBlocked", "RequestBlocked"}:
                message = (
                    "YouTube blocked transcript access. Configure a residential "
                    "proxy and retry."
                )
            elif error_name in {
                "AgeRestricted",
                "NoTranscriptFound",
                "TranscriptsDisabled",
                "VideoUnavailable",
            }:
                message = "A transcript is not available for this video."
            else:
                message = "Unable to fetch the video transcript."
            raise TranscriptServiceError(message) from exc
        except RequestException as exc:
            raise TranscriptServiceError(
                "Unable to reach YouTube for the video transcript."
            ) from exc

        segments = tuple(
            TranscriptSegment(
                text=snippet.text,
                start=float(snippet.start),
                duration=float(snippet.duration),
            )
            for snippet in transcript
        )
        if not segments:
            raise TranscriptServiceError("The video transcript is empty.")

        return TranscriptResult(
            segments=segments,
            language_code=transcript.language_code,
            is_generated=bool(transcript.is_generated),
        )

    def chunk(self, transcript: TranscriptResult) -> list[Document]:
        segments = tuple(self._normalized_segments(transcript.segments))
        if not segments:
            raise TranscriptServiceError("The video transcript is empty.")

        segment_character_starts: list[int] = []
        text_parts: list[str] = []
        cursor = 0
        for segment in segments:
            if text_parts:
                cursor += 1
            segment_character_starts.append(cursor)
            text_parts.append(segment.text)
            cursor += len(segment.text)

        full_text = " ".join(text_parts)
        chunks = self._splitter.create_documents([full_text])

        for chunk in chunks:
            character_start = int(chunk.metadata.pop("start_index", 0))
            character_end = character_start + max(len(chunk.page_content) - 1, 0)
            first_index = max(
                0,
                bisect_right(segment_character_starts, character_start) - 1,
            )
            last_index = max(
                first_index,
                bisect_right(segment_character_starts, character_end) - 1,
            )
            last_segment = segments[min(last_index, len(segments) - 1)]
            chunk.metadata.update(
                {
                    "start": segments[first_index].start,
                    "end": last_segment.start + last_segment.duration,
                    "language_code": transcript.language_code,
                    "is_generated": transcript.is_generated,
                }
            )

        return chunks

    @staticmethod
    def _normalized_segments(
        segments: Iterable[TranscriptSegment],
    ) -> Iterable[TranscriptSegment]:
        for segment in segments:
            text = " ".join(segment.text.split())
            if text:
                yield TranscriptSegment(
                    text=text,
                    start=max(float(segment.start), 0.0),
                    duration=max(float(segment.duration), 0.0),
                )
