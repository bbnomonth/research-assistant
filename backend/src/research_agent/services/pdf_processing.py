from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Dict, List, Optional, Protocol

import fitz

from research_agent.services.privacy import scrub_pii


class PdfTooLargeError(ValueError):
    pass


class OcrService(Protocol):
    def ocr_image(self, image_path: Path) -> str:
        pass


class PdfProcessor:
    def __init__(
        self,
        max_bytes: int = 10 * 1024 * 1024,
        ocr_service: Optional[OcrService] = None,
        scrub_pii_enabled: bool = False,
    ) -> None:
        self.max_bytes = max_bytes
        self.ocr_service = ocr_service
        self.scrub_pii_enabled = scrub_pii_enabled

    def extract_text_chunks(
        self,
        path: Path,
        max_pages: int = 60,
    ) -> List[Dict]:
        if path.stat().st_size > self.max_bytes:
            raise PdfTooLargeError("PDF exceeds 10 MB limit")

        chunks = []
        pages_with_text = set()
        with fitz.open(path) as document:
            page_count = min(document.page_count, max_pages)
            chunk_index = 1
            for page_index in range(page_count):
                page = document.load_page(page_index)
                text = page.get_text("text").strip()
                if not text:
                    continue
                pages_with_text.add(page_index)
                chunks.append(
                    {
                        "page_number": page_index + 1,
                        "chunk_index": chunk_index,
                        "section": "",
                        "text": scrub_pii(text) if self.scrub_pii_enabled else text,
                        "is_ocr": False,
                    }
                )
                chunk_index += 1
            if self.ocr_service is not None and self.needs_ocr(chunks):
                chunk_index = self._append_ocr_chunks(
                    document=document,
                    chunks=chunks,
                    pages_with_text=pages_with_text,
                    page_count=page_count,
                    next_chunk_index=chunk_index,
                    pdf_path=path,
                )
        return chunks

    def _append_ocr_chunks(
        self,
        document: fitz.Document,
        chunks: List[Dict],
        pages_with_text: set[int],
        page_count: int,
        next_chunk_index: int,
        pdf_path: Path,
    ) -> int:
        assert self.ocr_service is not None
        with TemporaryDirectory(dir=pdf_path.parent) as temp_dir:
            temp_path = Path(temp_dir)
            for page_index in range(page_count):
                if page_index in pages_with_text:
                    continue
                page = document.load_page(page_index)
                image_path = temp_path / f"page-{page_index + 1}.png"
                page.get_pixmap(matrix=fitz.Matrix(2, 2)).save(image_path)
                text = self.ocr_service.ocr_image(image_path).strip()
                if not text:
                    continue
                chunks.append(
                    {
                        "page_number": page_index + 1,
                        "chunk_index": next_chunk_index,
                        "section": "",
                        "text": scrub_pii(text) if self.scrub_pii_enabled else text,
                        "is_ocr": True,
                    }
                )
                next_chunk_index += 1
        return next_chunk_index

    @staticmethod
    def needs_ocr(chunks: List[Dict]) -> bool:
        total_chars = sum(len(chunk["text"].strip()) for chunk in chunks)
        return total_chars < 200


class TesseractOcrService:
    def __init__(
        self,
        executable: str,
        language: str = "chi_sim+eng",
        runner=None,
    ) -> None:
        self.executable = executable
        self.language = language
        self.runner = runner or self._run

    def ocr_image(self, image_path: Path) -> str:
        with TemporaryDirectory(dir=image_path.parent) as temp_dir:
            output_base = Path(temp_dir) / "page"
            command = [
                self.executable,
                str(image_path),
                str(output_base),
                "-l",
                self.language,
            ]
            self.runner(command)
            output_file = output_base.with_suffix(".txt")
            return output_file.read_text(encoding="utf-8").strip()

    @staticmethod
    def _run(command: List[str]) -> None:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
