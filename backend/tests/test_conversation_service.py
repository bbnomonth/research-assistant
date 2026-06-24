import asyncio

from sqlalchemy import select

from research_agent.db.engine import Database
from research_agent.db.models import Message, ModelCallLog
from research_agent.services.conversations import ConversationService
from research_agent.services.model_gateway import FakeModelGateway


def test_service_streams_mode_tokens_and_done(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    async def collect():
        with database.session_factory() as db:
            service = ConversationService(
                db=db,
                model_gateway=FakeModelGateway(["回答", "内容"]),
            )
            return [
                event
                async for event in service.stream_reply(
                    content="什么是排队论",
                )
            ]

    events = asyncio.run(collect())

    assert [event.event for event in events] == [
        "mode",
        "metadata",
        "token",
        "token",
        "done",
    ]
    assert events[-1].data["content"] == "回答内容"

    with database.session_factory() as db:
        messages = list(db.scalars(select(Message).order_by(Message.created_at)))
        logs = list(db.scalars(select(ModelCallLog)))

    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].content == "回答内容"
    assert len(logs) == 1
    assert logs[0].success == 1


def test_service_does_not_call_model_for_unimplemented_mode(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    async def collect():
        with database.session_factory() as db:
            service = ConversationService(
                db=db,
                model_gateway=FakeModelGateway(["不应出现"]),
            )
            return [
                event
                async for event in service.stream_reply(
                    content="帮我搜索物流论文",
                )
            ]

    events = asyncio.run(collect())

    assert [event.event for event in events] == [
        "mode",
        "metadata",
        "token",
        "done",
    ]
    assert "后续阶段" in events[-1].data["content"]


def test_literature_failure_emits_safe_error_event(tmp_path) -> None:
    class FailingProvider:
        async def search(self, query):
            del query
            raise RuntimeError("network details must not leak")

    class QueryGateway:
        model_name = "fake"

        async def stream_chat(self, messages):
            del messages
            yield '{"english_query":"vehicle routing"}'

    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    async def collect():
        with database.session_factory() as db:
            service = ConversationService(
                db=db,
                model_gateway=QueryGateway(),
                arxiv_provider=FailingProvider(),
            )
            return [
                event
                async for event in service.stream_reply(
                    content="搜索车辆路径论文",
                )
            ]

    events = asyncio.run(collect())

    assert events[-1].event == "error"
    assert "arXiv" in events[-1].data["message"]
    assert "network details" not in events[-1].data["message"]
