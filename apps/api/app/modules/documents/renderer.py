import logging
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)


class PDFPageRenderer:
    """Renders PDF pages into images in-memory for Vision LLM consumption."""

    @staticmethod
    def get_page_count(pdf_path: str | Path) -> int:
        """Get total number of pages in a PDF file."""
        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF file not found: {path}")

        with pymupdf.open(str(path)) as doc:
            return len(doc)

    @staticmethod
    def render_page_to_png_bytes(
        pdf_path: str | Path, page_number: int, dpi: int = 150
    ) -> bytes:
        """Render a specific 1-indexed page from a PDF file to PNG bytes in RAM.

        Args:
            pdf_path: Path to the PDF file.
            page_number: 1-indexed page number.
            dpi: Resolution (dots per inch). 150 DPI provides sharp text and math formulas.

        Returns:
            PNG image bytes.
        """
        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF file not found: {path}")

        with pymupdf.open(str(path)) as doc:
            total_pages = len(doc)
            if page_number < 1 or page_number > total_pages:
                raise ValueError(
                    f"Page number {page_number} is out of bounds (1-{total_pages})"
                )

            page = doc[page_number - 1]
            pix = page.get_pixmap(dpi=dpi)
            return pix.tobytes(output="png")

    @staticmethod
    def is_page_empty(pdf_path: str | Path, page_number: int) -> bool:
        """Check if a page has no text, images, or drawings (blank page fast-path)."""
        path = Path(pdf_path)
        with pymupdf.open(str(path)) as doc:
            if page_number < 1 or page_number > len(doc):
                return True
            page = doc[page_number - 1]
            text = page.get_text("text").strip()
            image_list = page.get_images()
            drawings = page.get_drawings()
            return len(text) == 0 and len(image_list) == 0 and len(drawings) == 0
