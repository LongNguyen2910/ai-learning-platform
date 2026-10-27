"""Smart Hybrid Ingestion Router: Text-First, Vision-Fallback.

Routes PDF pages between local CPU digital text extraction (0 API tokens, 0ms latency)
and Gemini Vision API (for pages containing images, complex vector drawings, or math).
"""

from dataclasses import dataclass
from enum import Enum
import logging
from pathlib import Path
import re
import statistics

import pymupdf

from app.core.config import settings

logger = logging.getLogger(__name__)

# Keywords indicating math-focused fonts in PDF metadata
MATH_FONT_KEYWORDS = (
    "math",
    "cmsy",
    "cmr",
    "symbol",
    "cambriamath",
    "asms",
    "msam",
    "msbm",
    "mt-extra",
)

# Common mathematical symbols or LaTeX commands that necessitate Vision OCR
MATH_SYMBOLS_REGEX = re.compile(
    r"(\\[a-zA-Z]+|∫|∑|√|∂|≈|≤|≥|≠|∞|×|±|÷|∈|∉|⊂|⊃|⊆|⊇|∪|∩|∧|∨|∀|∃|¬|→|⇒|⇔)"
)

# Bullet points and ordered list indicators
LIST_PREFIX_REGEX = re.compile(
    r"^(?:[\u2022\u2023\u25E6\u2043\u2219\u00B7\*\-\+]|\d+[\.\)])\s+"
)


class PageRoute(str, Enum):
    """Routing destination for a PDF page."""

    EMPTY = "EMPTY"  # Completely blank page -> skip without LLM or indexing
    LOCAL_TEXT = "LOCAL_TEXT"  # Digital text -> local CPU extraction (0 tokens)
    VISION_REQUIRED = "VISION_REQUIRED"  # Images/diagrams/math -> Gemini Vision OCR


@dataclass
class PageClassificationResult:
    """Outcome of inspecting a PDF page."""

    page_number: int
    route: PageRoute
    reason: str
    extracted_markdown: str | None = None


class LocalTextExtractor:
    """Extracts digital text from PyMuPDF and formats it into Markdown.

    Applies font-size and block-level heuristics to infer headings (#, ##),
    preserves lists, and unwraps mid-sentence line breaks caused by PDF layout.
    """

    @staticmethod
    def extract_to_markdown(
        page: pymupdf.Page, min_text_chars: int = 30
    ) -> str | None:
        """Extracts text and normalizes into Markdown.

        Returns None if text is corrupt, unprintable, or shorter than min_text_chars,
        signaling a required fallback to Vision API.
        """
        page_dict = page.get_text("dict")
        raw_blocks = page_dict.get("blocks", [])

        # 1. Collect all span font sizes weighted by character length to determine body font size
        font_sizes: list[float] = []
        for block in raw_blocks:
            if block.get("type") != 0:  # 0 is text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "").strip()
                    if span_text:
                        font_sizes.extend([span["size"]] * len(span_text))

        if not font_sizes:
            return None

        body_font_size = statistics.median(font_sizes)

        # 2. Process text blocks into Markdown paragraphs / headings / lists
        markdown_blocks: list[str] = []

        for block in raw_blocks:
            if block.get("type") != 0:
                continue

            lines = block.get("lines", [])
            if not lines:
                continue

            # Reconstruct lines within the block
            extracted_lines: list[str] = []
            block_max_font_size = 0.0
            block_is_bold = False

            for line in lines:
                line_spans = line.get("spans", [])
                line_text = "".join(s.get("text", "") for s in line_spans).strip()
                if not line_text:
                    continue

                for s in line_spans:
                    size = s.get("size", 0.0)
                    if size > block_max_font_size:
                        block_max_font_size = size
                    if s.get("flags", 0) & 16 != 0 or "bold" in s.get("font", "").lower():
                        block_is_bold = True

                extracted_lines.append(line_text)

            if not extracted_lines:
                continue

            full_block_text = " ".join(extracted_lines).strip()

            # Heading Detection Heuristic:
            # Short text (< 250 chars), doesn't end with a period, and has larger font / bold
            is_heading = False
            heading_level = 0

            if len(full_block_text) < 250 and not full_block_text.endswith("."):
                if block_max_font_size >= body_font_size * 1.35:
                    heading_level = 1
                    is_heading = True
                elif block_max_font_size >= body_font_size * 1.18:
                    heading_level = 2
                    is_heading = True
                elif block_max_font_size >= body_font_size * 1.05 and block_is_bold:
                    heading_level = 3
                    is_heading = True

            if is_heading:
                prefix = "#" * heading_level + " "
                markdown_blocks.append(f"{prefix}{full_block_text}")
                continue

            # Standard paragraph or list processing
            # Unwrap hard-wrapped lines inside regular paragraphs
            processed_lines: list[str] = []
            current_sentence = ""

            for l_idx, line_str in enumerate(extracted_lines):
                # Check if this line is a bullet or numbered list
                if LIST_PREFIX_REGEX.match(line_str):
                    if current_sentence:
                        processed_lines.append(current_sentence)
                        current_sentence = ""
                    # Normalize bullet to markdown dash if it's a bullet character
                    norm_line = re.sub(
                        r"^[\u2022\u2023\u25E6\u2043\u2219\u00B7\*]\s*", "- ", line_str
                    )
                    processed_lines.append(norm_line)
                    continue

                if not current_sentence:
                    current_sentence = line_str
                else:
                    # If previous sentence part ended with punctuation, wrap into new line
                    if current_sentence.rstrip()[-1] in (".", "!", "?", ":", "—"):
                        processed_lines.append(current_sentence)
                        current_sentence = line_str
                    else:
                        current_sentence += " " + line_str

            if current_sentence:
                processed_lines.append(current_sentence)

            if processed_lines:
                markdown_blocks.append("\n".join(processed_lines))

        result = "\n\n".join(markdown_blocks).strip()

        # 3. Safety & Fallback Validation
        if len(result) < min_text_chars:
            logger.debug(
                "Extracted text too short (%d chars < min %d), triggering fallback",
                len(result),
                min_text_chars,
            )
            return None

        # Check for garbled/non-printable character ratio (corrupted ToUnicode mapping)
        non_printable_count = sum(
            1 for c in result if not c.isprintable() and c not in ("\n", "\t", "\r")
        )
        if non_printable_count / len(result) > 0.15:
            logger.warning(
                "Extracted text has high non-printable ratio (%.2f > 0.15), triggering fallback",
                non_printable_count / len(result),
            )
            return None

        return result


class PageClassifier:
    """Classifies PDF pages to determine whether Local CPU extraction or Gemini Vision is needed."""

    def __init__(
        self,
        max_drawings: int = 5,
        min_text_chars: int = 30,
    ) -> None:
        self.max_drawings = max_drawings
        self.min_text_chars = min_text_chars
        self.extractor = LocalTextExtractor()

    def classify(self, page: pymupdf.Page, page_number: int) -> PageClassificationResult:
        """Inspects page objects, fonts, drawings, and text to decide routing."""
        raw_text = page.get_text("text").strip()
        images = page.get_images()
        drawings = page.get_drawings()

        # Fast check: Completely blank page
        if len(raw_text) == 0 and len(images) == 0 and len(drawings) == 0:
            return PageClassificationResult(
                page_number=page_number,
                route=PageRoute.EMPTY,
                reason="empty_page",
            )

        # Vision Factor 1: Embedded raster images
        if len(images) > 0:
            return PageClassificationResult(
                page_number=page_number,
                route=PageRoute.VISION_REQUIRED,
                reason=f"has_images({len(images)})",
            )

        # Vision Factor 2: Vector drawings (charts, geometric diagrams, circuit schemes)
        if len(drawings) > self.max_drawings:
            return PageClassificationResult(
                page_number=page_number,
                route=PageRoute.VISION_REQUIRED,
                reason=f"complex_drawings({len(drawings)})",
            )

        # Vision Factor 3: Math formulas (check font names and math symbol tokens)
        fonts = page.get_fonts()
        for font_info in fonts:
            basefont = str(font_info[3]).lower() if len(font_info) > 3 else ""
            fontname = str(font_info[4]).lower() if len(font_info) > 4 else ""
            if any(kw in basefont or kw in fontname for kw in MATH_FONT_KEYWORDS):
                return PageClassificationResult(
                    page_number=page_number,
                    route=PageRoute.VISION_REQUIRED,
                    reason=f"math_font_detected({basefont or fontname})",
                )

        if MATH_SYMBOLS_REGEX.search(raw_text):
            return PageClassificationResult(
                page_number=page_number,
                route=PageRoute.VISION_REQUIRED,
                reason="math_symbols_detected",
            )

        # Vision Factor 4: Text too short with elements (likely scanned fragment or logo)
        if len(raw_text) < self.min_text_chars and (len(drawings) > 0 or len(images) > 0):
            return PageClassificationResult(
                page_number=page_number,
                route=PageRoute.VISION_REQUIRED,
                reason=f"short_text_with_elements(chars={len(raw_text)},drawings={len(drawings)})",
            )

        # Attempt local CPU extraction
        markdown = self.extractor.extract_to_markdown(
            page, min_text_chars=self.min_text_chars
        )
        if markdown is None:
            # Fallback to Vision if local extraction fails safety checks
            return PageClassificationResult(
                page_number=page_number,
                route=PageRoute.VISION_REQUIRED,
                reason="local_extraction_fallback_corrupt_or_short",
            )

        return PageClassificationResult(
            page_number=page_number,
            route=PageRoute.LOCAL_TEXT,
            reason="plain_digital_text",
            extracted_markdown=markdown,
        )


class HybridPageRouter:
    """Coordinates PDF page classification and routing across the document."""

    def __init__(
        self,
        max_drawings: int | None = None,
        min_text_chars: int | None = None,
    ) -> None:
        self.max_drawings = (
            max_drawings
            if max_drawings is not None
            else getattr(settings, "HYBRID_ROUTER_MAX_DRAWINGS", 5)
        )
        self.min_text_chars = (
            min_text_chars
            if min_text_chars is not None
            else getattr(settings, "HYBRID_ROUTER_MIN_TEXT_CHARS", 30)
        )
        self.classifier = PageClassifier(
            max_drawings=self.max_drawings,
            min_text_chars=self.min_text_chars,
        )

    def classify_page(
        self,
        pdf_path: str | Path,
        page_number: int,
        pdf_doc: pymupdf.Document | None = None,
    ) -> PageClassificationResult:
        """Classifies a single page. If pdf_doc is supplied, inspects it in-memory."""
        try:
            if pdf_doc is not None:
                if page_number < 1 or page_number > len(pdf_doc):
                    return PageClassificationResult(
                        page_number=page_number,
                        route=PageRoute.EMPTY,
                        reason="out_of_bounds",
                    )
                return self.classifier.classify(pdf_doc[page_number - 1], page_number)

            path = Path(pdf_path)
            if not path.is_file():
                return PageClassificationResult(
                    page_number=page_number,
                    route=PageRoute.VISION_REQUIRED,
                    reason="file_not_found_fallback",
                )
            with pymupdf.open(str(path)) as doc:
                if page_number < 1 or page_number > len(doc):
                    return PageClassificationResult(
                        page_number=page_number,
                        route=PageRoute.EMPTY,
                        reason="out_of_bounds",
                    )
                return self.classifier.classify(doc[page_number - 1], page_number)
        except Exception as exc:
            logger.warning(
                "Router could not inspect page %d in %s: %s. Falling back to VISION_REQUIRED.",
                page_number,
                pdf_path,
                exc,
            )
            return PageClassificationResult(
                page_number=page_number,
                route=PageRoute.VISION_REQUIRED,
                reason=f"router_exception_fallback({exc})",
            )

    def route_document(self, pdf_path: str | Path) -> list[PageClassificationResult]:
        """Classifies all pages in a given PDF document."""
        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF file not found: {path}")

        results: list[PageClassificationResult] = []
        with pymupdf.open(str(path)) as doc:
            for page_idx, page in enumerate(doc):
                page_num = page_idx + 1
                result = self.classifier.classify(page, page_num)
                results.append(result)
        return results
