import pytest
import pymupdf

from app.modules.documents.hybrid_router import (
    HybridPageRouter,
    LocalTextExtractor,
    PageClassifier,
    PageRoute,
)


@pytest.fixture
def empty_page():
    doc = pymupdf.open()
    page = doc.new_page()
    return doc, page


@pytest.fixture
def plain_text_page():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        "Chapter 1: Introduction to Intelligent Learning Systems.\n"
        "This platform provides personalized learning experiences for all students.\n"
        "Learners can track their progress and complete interactive exercises online.",
    )
    return doc, page


@pytest.fixture
def page_with_math():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        "Xét tích phân đường loại hai: \\int_{C} P dx + Q dy = \\iint_{D} (\\frac{\\partial Q}{\\partial x} - \\frac{\\partial P}{\\partial y}) dx dy",
    )
    return doc, page


@pytest.fixture
def page_with_drawings():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Biểu đồ hình học và đường bao xung quanh đối tượng.")
    # Add 8 drawing paths to exceed threshold of 5
    for i in range(8):
        page.draw_rect(pymupdf.Rect(50, 100 + i * 20, 200, 115 + i * 20))
    return doc, page


@pytest.fixture
def page_with_image():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Trang có hình ảnh minh họa đính kèm bên dưới.")
    # Create small dummy 10x10 pixmap and insert it
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), 1)
    pix.clear_with(255)
    img_bytes = pix.tobytes("png")
    page.insert_image(pymupdf.Rect(50, 100, 150, 200), stream=img_bytes)
    return doc, page


def test_classify_empty_page(empty_page):
    _doc, page = empty_page
    classifier = PageClassifier(max_drawings=5, min_text_chars=30)
    result = classifier.classify(page, page_number=1)

    assert result.page_number == 1
    assert result.route == PageRoute.EMPTY
    assert result.reason == "empty_page"
    assert result.extracted_markdown is None


def test_classify_plain_text_page(plain_text_page):
    _doc, page = plain_text_page
    classifier = PageClassifier(max_drawings=5, min_text_chars=30)
    result = classifier.classify(page, page_number=2)

    assert result.page_number == 2
    assert result.route == PageRoute.LOCAL_TEXT
    assert result.reason == "plain_digital_text"
    assert result.extracted_markdown is not None
    assert "Intelligent Learning Systems" in result.extracted_markdown


def test_classify_page_with_math_symbols(page_with_math):
    _doc, page = page_with_math
    classifier = PageClassifier(max_drawings=5, min_text_chars=30)
    result = classifier.classify(page, page_number=3)

    assert result.page_number == 3
    assert result.route == PageRoute.VISION_REQUIRED
    assert result.reason == "math_symbols_detected"
    assert result.extracted_markdown is None


def test_classify_page_with_drawings(page_with_drawings):
    _doc, page = page_with_drawings
    classifier = PageClassifier(max_drawings=5, min_text_chars=30)
    result = classifier.classify(page, page_number=4)

    assert result.page_number == 4
    assert result.route == PageRoute.VISION_REQUIRED
    assert "complex_drawings" in result.reason
    assert result.extracted_markdown is None


def test_classify_page_with_image(page_with_image):
    _doc, page = page_with_image
    classifier = PageClassifier(max_drawings=5, min_text_chars=30)
    result = classifier.classify(page, page_number=5)

    assert result.page_number == 5
    assert result.route == PageRoute.VISION_REQUIRED
    assert "has_images" in result.reason
    assert result.extracted_markdown is None


def test_local_text_extractor_headings_and_lists():
    doc = pymupdf.open()
    page = doc.new_page()
    # Heading with large font
    page.insert_text((50, 50), "Table of Contents Overview", fontsize=18)
    # Paragraph with normal body font
    page.insert_text(
        (50, 90),
        "This curriculum covers deep learning and modern RAG systems.",
        fontsize=11,
    )
    # Bullet points
    page.insert_text((50, 120), "• Chapter 1: Foundational Principles", fontsize=11)
    page.insert_text((50, 140), "• Chapter 2: Transformer Architectures", fontsize=11)

    markdown = LocalTextExtractor.extract_to_markdown(page, min_text_chars=20)
    assert markdown is not None
    assert "# Table of Contents Overview" in markdown
    assert "This curriculum covers deep learning" in markdown
    assert "- Chapter 1: Foundational Principles" in markdown
    assert "- Chapter 2: Transformer Architectures" in markdown


def test_local_text_extractor_corrupt_or_short_fallback():
    doc = pymupdf.open()
    page = doc.new_page()
    # Text shorter than min_text_chars (30)
    page.insert_text((50, 50), "Trang 1.")

    markdown = LocalTextExtractor.extract_to_markdown(page, min_text_chars=30)
    assert markdown is None  # Should return None to trigger Vision fallback


def test_hybrid_page_router_document(tmp_path):
    pdf_path = tmp_path / "sample_doc.pdf"
    doc = pymupdf.open()

    # Page 1: Empty
    doc.new_page()

    # Page 2: Plain text
    p2 = doc.new_page()
    p2.insert_text(
        (50, 50),
        "Lời nói đầu: Chào mừng các bạn đến với khóa học Trí tuệ Nhân tạo hiện đại.",
    )

    # Page 3: Math formula
    p3 = doc.new_page()
    p3.insert_text(
        (50, 50),
        "Công thức tổng: \\sum_{i=1}^{n} x_i^2 = \\frac{n(n+1)(2n+1)}{6}",
    )

    doc.save(str(pdf_path))
    doc.close()

    router = HybridPageRouter(max_drawings=5, min_text_chars=20)
    results = router.route_document(pdf_path)

    assert len(results) == 3
    assert results[0].page_number == 1
    assert results[0].route == PageRoute.EMPTY

    assert results[1].page_number == 2
    assert results[1].route == PageRoute.LOCAL_TEXT
    assert results[1].extracted_markdown is not None

    assert results[2].page_number == 3
    assert results[2].route == PageRoute.VISION_REQUIRED


@pytest.mark.asyncio
async def test_pipeline_all_local_text_zero_gemini_calls(tmp_path):
    """Verifies that a digital text PDF makes zero API calls to Gemini Vision."""
    from unittest.mock import MagicMock
    from app.modules.documents.service import IngestionService

    pdf_path = tmp_path / "all_digital_text.pdf"
    doc = pymupdf.open()

    p1 = doc.new_page()
    p1.insert_text(
        (50, 50),
        "Chapter 1: Foundational Artificial Intelligence Concepts.\n"
        "Machine learning focuses on training algorithms from empirical data.",
    )

    p2 = doc.new_page()
    p2.insert_text(
        (50, 50),
        "Chapter 2: Deep Neural Networks and Embeddings.\n"
        "Embeddings translate high-dimensional categorical features into dense vectors.",
    )

    doc.save(str(pdf_path))
    doc.close()

    vision_mock = MagicMock()
    vision_mock.parse_page_images_batch = MagicMock()
    vision_mock.parse_page_image = MagicMock()

    vector_mock = MagicMock()

    ingestion_service = IngestionService(
        vision_parser=vision_mock,
        vector_service=vector_mock,
        parsed_base_dir=str(tmp_path / "parsed"),
    )

    meta = await ingestion_service.run_ingestion_pipeline(
        document_id="doc_local_123",
        pdf_path=pdf_path,
        title="AI Foundations",
    )

    # ZERO calls to Gemini Vision!
    vision_mock.parse_page_images_batch.assert_not_called()
    vision_mock.parse_page_image.assert_not_called()

    # Document ready
    assert meta.status == "ready"
    assert meta.total_pages == 2
    assert len(meta.pages) == 2

    # Vector indexing called with correct metadata
    vector_mock.index_document_pages.assert_called_once()
    indexed_meta = vector_mock.index_document_pages.call_args[0][1]
    assert len(indexed_meta) == 2
    assert indexed_meta[0].page_number == 1
    assert indexed_meta[1].page_number == 2


@pytest.mark.asyncio
async def test_pipeline_hybrid_mixed_pages_deterministic_order(tmp_path):
    """Verifies that a document with mixed pages routes text to CPU and math to Vision,

    and stitches them in exact 1 -> 2 -> 3 page order.
    """
    from unittest.mock import AsyncMock, MagicMock
    from app.modules.documents.schemas import ParsedPageMetadata
    from app.modules.documents.service import IngestionService

    pdf_path = tmp_path / "mixed_doc.pdf"
    doc = pymupdf.open()

    # Page 1: Digital text
    p1 = doc.new_page()
    p1.insert_text(
        (50, 50),
        "Chapter 1: System Introduction and Overview.\n"
        "Here is the detailed overview of our hybrid RAG architecture.",
    )

    # Page 2: Math formula
    p2 = doc.new_page()
    p2.insert_text(
        (50, 50),
        "Mathematical Definition: \\int_{0}^{\\infty} e^{-x^2} dx = \\frac{\\sqrt{\\pi}}{2}",
    )

    # Page 3: Digital text
    p3 = doc.new_page()
    p3.insert_text(
        (50, 50),
        "Chapter 3: Experimental Evaluation and Conclusions.\n"
        "The experiments show that hybrid routing reduces token consumption by 85%.",
    )

    doc.save(str(pdf_path))
    doc.close()

    vision_mock = MagicMock()

    async def mock_vision_batch(pages_to_parse):
        # pages_to_parse is list of (page_num, png_bytes)
        res = {}
        for page_num, _ in pages_to_parse:
            res[page_num] = (
                f"# Page {page_num} Parsed by Gemini Vision\n$$\\int_{{0}}^{{\\infty}} e^{{-x^2}} dx = \\frac{{\\sqrt{{\\pi}}}}{{2}}$$",
                ParsedPageMetadata(
                    page_number=page_num,
                    has_formula=True,
                    has_image=False,
                    char_count=50,
                    file_path="",
                ),
            )
        return res

    vision_mock.parse_page_images_batch = AsyncMock(side_effect=mock_vision_batch)

    vector_mock = MagicMock()

    ingestion_service = IngestionService(
        vision_parser=vision_mock,
        vector_service=vector_mock,
        parsed_base_dir=str(tmp_path / "parsed"),
    )

    meta = await ingestion_service.run_ingestion_pipeline(
        document_id="doc_hybrid_456",
        pdf_path=pdf_path,
        title="Mixed Hybrid Document",
    )

    assert meta.status == "ready"
    assert meta.total_pages == 3

    # Vision parser was called ONLY for page 2!
    vision_mock.parse_page_images_batch.assert_called_once()
    called_pages = [p[0] for p in vision_mock.parse_page_images_batch.call_args[0][0]]
    assert called_pages == [2]

    # Verify deterministic merge order: 1 -> 2 -> 3
    full_doc_path = ingestion_service.get_full_doc_path("doc_hybrid_456")
    full_markdown = full_doc_path.read_text(encoding="utf-8")

    pos_p1 = full_markdown.find("PAGE_BREAK: 1")
    pos_p2 = full_markdown.find("PAGE_BREAK: 2")
    pos_p3 = full_markdown.find("PAGE_BREAK: 3")

    assert pos_p1 != -1 and pos_p2 != -1 and pos_p3 != -1
    assert pos_p1 < pos_p2 < pos_p3
