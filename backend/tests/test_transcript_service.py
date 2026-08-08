import pytest

from app.config import Settings
from app.services.transcript_service import (
    InvalidYouTubeURL,
    TranscriptResult,
    TranscriptSegment,
    TranscriptService,
    extract_video_id,
)

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "value",
    [
        VIDEO_ID,
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com/watch?feature=share&v={VIDEO_ID}&t=10",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?si=abc",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}",
        f"youtu.be/{VIDEO_ID}",
    ],
)
def test_extract_video_id_from_common_forms(value: str) -> None:
    assert extract_video_id(value) == VIDEO_ID


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not a video",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=too-short",
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_extract_video_id_rejects_invalid_input(value: str) -> None:
    with pytest.raises(InvalidYouTubeURL):
        extract_video_id(value)


def test_chunk_metadata_tracks_source_timestamps() -> None:
    service = TranscriptService(
        Settings(
            transcript_chunk_size=100,
            transcript_chunk_overlap=20,
        )
    )
    transcript = TranscriptResult(
        segments=(
            TranscriptSegment(
                text="First sentence " * 5,
                start=0.0,
                duration=4.0,
            ),
            TranscriptSegment(
                text="Second sentence " * 5,
                start=4.0,
                duration=5.0,
            ),
            TranscriptSegment(
                text="Third sentence " * 5,
                start=9.0,
                duration=6.0,
            ),
        ),
        language_code="en",
        is_generated=True,
    )

    chunks = service.chunk(transcript)

    assert len(chunks) >= 2
    assert chunks[0].metadata["start"] == 0.0
    assert chunks[-1].metadata["start"] >= 4.0
    assert chunks[-1].metadata["end"] <= 15.0
    assert all(chunk.metadata["language_code"] == "en" for chunk in chunks)
    assert all(chunk.metadata["is_generated"] is True for chunk in chunks)
