from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
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
