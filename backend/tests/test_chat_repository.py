from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from app.services.chat_repository import ChatRepository

USER_ID = UUID("4041afdc-252b-4d2a-938f-83e65f82f6ac")


class FakeEmbeddingService:
    def embed_query(self, text: str) -> list[float]:
        assert text == "What happened?"
        return [0.1, 0.2, 0.3]


class FakeRpcQuery:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.data)


class FakeTableQuery:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, object]] = []
        self.inserted: list[dict[str, object]] | None = None

    def select(self, columns: str) -> "FakeTableQuery":
        return self

    def eq(self, column: str, value: object) -> "FakeTableQuery":
        self.filters.append((column, value))
        return self

    def order(self, column: str, *, desc: bool) -> "FakeTableQuery":
        return self

    def limit(self, count: int) -> "FakeTableQuery":
        return self

    def insert(
        self,
        rows: list[dict[str, object]],
    ) -> "FakeTableQuery":
        self.inserted = rows
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.rows)


class FakeClient:
    def __init__(self) -> None:
        self.rpc_name: str | None = None
        self.rpc_params: dict[str, object] | None = None
        now = datetime.now(UTC).isoformat()
        self.history_query = FakeTableQuery(
            [
                {
                    "id": 2,
                    "video_id": 7,
                    "role": "assistant",
                    "content": "Answer",
                    "created_at": now,
                },
                {
                    "id": 1,
                    "video_id": 7,
                    "role": "user",
                    "content": "Question",
                    "created_at": now,
                },
            ]
        )
        self.insert_query = FakeTableQuery(
            [
                {
                    "id": 3,
                    "video_id": 7,
                    "role": "user",
                    "content": "What happened?",
                    "created_at": now,
                },
                {
                    "id": 4,
                    "video_id": 7,
                    "role": "assistant",
                    "content": "Something.",
                    "created_at": now,
                },
            ]
        )

    def rpc(
        self,
        name: str,
        params: dict[str, object],
    ) -> FakeRpcQuery:
        self.rpc_name = name
        self.rpc_params = params
        return FakeRpcQuery(
            [
                {
                    "content": "right video",
                    "metadata": {"video_id": 7, "start": 12},
                    "similarity": 0.9,
                },
                {
                    "content": "wrong video",
                    "metadata": {"video_id": 8, "start": 3},
                    "similarity": 0.99,
                },
            ]
        )

    def table(self, name: str) -> FakeTableQuery:
        if name != "chat_messages":
            raise AssertionError(f"Unexpected table: {name}")
        return self.history_query


def repository() -> tuple[ChatRepository, FakeClient]:
    client = FakeClient()
    return (
        ChatRepository(client, USER_ID, FakeEmbeddingService()),
        client,
    )


def test_retrieval_passes_video_id_to_rpc_and_defensively_filters() -> None:
    repo, client = repository()

    chunks = repo.retrieve("What happened?", video_id=7, top_k=5)

    assert client.rpc_name == "match_documents"
    assert client.rpc_params == {
        "query_embedding": [0.1, 0.2, 0.3],
        "match_video_id": 7,
        "match_count": 5,
    }
    assert [chunk.content for chunk in chunks] == ["right video"]


def test_history_is_video_scoped_and_returned_oldest_first() -> None:
    repo, client = repository()

    history = repo.list_history(7, limit=6)

    assert ("video_id", 7) in client.history_query.filters
    assert [message.id for message in history] == [1, 2]


def test_exchange_is_one_bulk_insert_owned_by_authenticated_user() -> None:
    repo, client = repository()
    client.history_query = client.insert_query

    repo.save_exchange(7, "What happened?", "Something.")

    inserted = client.insert_query.inserted
    assert inserted is not None
    assert [row["role"] for row in inserted] == ["user", "assistant"]
    assert {row["user_id"] for row in inserted} == {str(USER_ID)}
    assert {row["video_id"] for row in inserted} == {7}
