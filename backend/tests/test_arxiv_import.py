import fitz

from research_agent.db.engine import Database
from research_agent.repositories.conversations import ConversationRepository
from research_agent.repositories.papers import PaperRepository
from research_agent.schemas.literature import ArxivPaper, RecommendedPaper
from research_agent.services.arxiv_import import ArxivPdfImportService


def _pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


class MemoryDownloader:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.url = ""

    def download(self, url, destination, max_bytes):
        self.url = url
        if len(self.content) > max_bytes:
            raise ValueError("download exceeds size limit")
        destination.write_bytes(self.content)


def _seed_arxiv_paper(db):
    project, _ = ConversationRepository(db).ensure_conversation(None, None)
    return PaperRepository(db).upsert_arxiv_papers(
        project.id,
        [
            RecommendedPaper(
                paper=ArxivPaper(
                    arxiv_id="2401.40001",
                    title="Importable Routing Paper",
                    authors=["A"],
                    abstract="Abstract",
                    published="2024-01-01",
                    categories=["cs.AI"],
                    entry_url="https://arxiv.org/abs/2401.40001",
                    pdf_url="https://arxiv.org/pdf/2401.40001",
                ),
                reason="",
                purpose_labels=[],
            )
        ],
    )[0]


def test_arxiv_import_downloads_parses_and_indexes_pdf(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()
    downloader = MemoryDownloader(
        _pdf_bytes("Imported vehicle routing evidence")
    )

    with database.session_factory() as db:
        paper = _seed_arxiv_paper(db)
        result = ArxivPdfImportService(
            db=db,
            upload_dir=tmp_path / "uploads",
            downloader=downloader,
        ).import_pdf(paper.id)
        db.commit()

    assert result.task.status == "completed"
    assert result.chunk_count == 1
    assert downloader.url == "https://arxiv.org/pdf/2401.40001"
    assert result.stored_path.exists()


def test_arxiv_import_rejects_non_http_pdf_url(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    with database.session_factory() as db:
        paper = _seed_arxiv_paper(db)
        paper.pdf_url = "file:///private/paper.pdf"

        try:
            ArxivPdfImportService(
                db=db,
                upload_dir=tmp_path / "uploads",
                downloader=MemoryDownloader(b"%PDF"),
            ).import_pdf(paper.id)
        except ValueError as exc:
            assert "HTTP" in str(exc)
        else:
            raise AssertionError("non-HTTP URL was accepted")
