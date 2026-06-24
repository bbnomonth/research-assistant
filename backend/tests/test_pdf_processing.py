from pathlib import Path

import fitz

from research_agent.services.pdf_processing import PdfProcessor, TesseractOcrService


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


def test_pdf_processor_uses_ocr_when_text_is_missing(tmp_path) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    document = fitz.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    class FakeOcr:
        def __init__(self) -> None:
            self.paths = []

        def ocr_image(self, image_path: Path) -> str:
            self.paths.append(image_path)
            return "OCR vehicle routing evidence"

    ocr = FakeOcr()
    chunks = PdfProcessor(ocr_service=ocr).extract_text_chunks(pdf_path)

    assert len(chunks) == 1
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["is_ocr"] is True
    assert chunks[0]["text"] == "OCR vehicle routing evidence"
    assert ocr.paths[0].suffix == ".png"


def test_tesseract_ocr_service_uses_configured_language(tmp_path) -> None:
    calls = []

    def fake_runner(command):
        calls.append(command)
        output = Path(command[2]).with_suffix(".txt")
        output.write_text("OCR vehicle routing", encoding="utf-8")

    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake")
    service = TesseractOcrService(
        executable="tesseract",
        language="chi_sim+eng",
        runner=fake_runner,
    )

    text = service.ocr_image(image_path)

    assert text == "OCR vehicle routing"
    assert calls[0][0] == "tesseract"
    assert "-l" in calls[0]
    assert "chi_sim+eng" in calls[0]
