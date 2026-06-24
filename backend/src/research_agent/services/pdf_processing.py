from pathlib import Path
from typing import Dict, List

import fitz


class PdfTooLargeError(ValueError):
    pass


class PdfProcessor:
    def __init__(
        self,
        max_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self.max_bytes = max_bytes

    def extract_text_chunks(
        self,
        path: Path,
        max_pages: int = 60,
    ) -> List[Dict]:
        if path.stat().st_size > self.max_bytes:
            raise PdfTooLargeError("PDF exceeds 10 MB limit")

        chunks = []
        with fitz.open(path) as document:
            page_count = min(document.page_count, max_pages)
            chunk_index = 1
            for page_index in range(page_count):
                page = document.load_page(page_index)
                text = page.get_text("text").strip()
                if not text:
                    continue
                chunks.append(
                    {
                        "page_number": page_index + 1,
                        "chunk_index": chunk_index,
                        "section": "",
                        "text": text,
                        "is_ocr": False,
                    }
                )
                chunk_index += 1
        return chunks

    @staticmethod
    def needs_ocr(chunks: List[Dict]) -> bool:
        total_chars = sum(len(chunk["text"].strip()) for chunk in chunks)
        return total_chars < 200
