import fitz

from research_agent.services.pdf_processing import PdfProcessor


def _make_pdf(path, pages: int) -> None:
    document = fitz.open()
    for index in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {index + 1} vehicle routing evidence")
    document.save(path)
    document.close()


def test_pdf_processor_extracts_page_chunks(tmp_path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _make_pdf(pdf_path, pages=2)

    chunks = PdfProcessor().extract_text_chunks(pdf_path, max_pages=60)

    assert [chunk["page_number"] for chunk in chunks] == [1, 2]
    assert chunks[0]["chunk_index"] == 1
    assert chunks[0]["is_ocr"] is False
    assert "vehicle routing" in chunks[0]["text"]


def test_pdf_processor_limits_to_first_60_pages(tmp_path) -> None:
    pdf_path = tmp_path / "long.pdf"
    _make_pdf(pdf_path, pages=62)

    chunks = PdfProcessor().extract_text_chunks(pdf_path, max_pages=60)

    assert len(chunks) == 60
    assert chunks[-1]["page_number"] == 60
