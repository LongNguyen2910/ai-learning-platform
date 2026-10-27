import pytest
from app.modules.documents.splitter import (
    BlockType,
    MarkdownStructureSplitter,
    estimate_tokens,
)


def test_estimate_tokens():
    text = "Đây là một câu kiểm tra tiếng Việt."
    tokens = estimate_tokens(text)
    assert tokens > 0


def test_parse_blocks_fsm():
    splitter = MarkdownStructureSplitter()
    markdown = """# Chương 1: Giới thiệu

Đoạn văn mở đầu.

## 1.1 Khái niệm cơ bản

Một công thức toán:
$$
\\int_0^1 x^2 dx = \\frac{1}{3}
$$

Bảng thông số:
| Tên | Giá trị |
| :--- | :--- |
| Alpha | 0.05 |

[Hình vẽ trang 1: Sơ đồ mô phỏng hệ thống]

Đoạn văn kết thúc trang.
"""
    blocks = splitter.parse_blocks(markdown)
    assert len(blocks) == 9

    # Block 0: Heading 1
    assert blocks[0].block_type == BlockType.HEADING
    assert blocks[0].heading_path == ["Chương 1: Giới thiệu"]

    # Block 1: Paragraph
    assert blocks[1].block_type == BlockType.PARAGRAPH
    assert blocks[1].heading_path == ["Chương 1: Giới thiệu"]

    # Block 2: Heading 2
    assert blocks[2].block_type == BlockType.HEADING
    assert blocks[2].heading_path == ["Chương 1: Giới thiệu", "1.1 Khái niệm cơ bản"]

    # Block 3: Paragraph
    assert blocks[3].block_type == BlockType.PARAGRAPH

    # Block 4: Math block
    assert blocks[4].block_type == BlockType.MATH_BLOCK
    assert "$$" in blocks[4].text
    assert "\\int_0^1" in blocks[4].text
    assert blocks[4].text.startswith("$$")
    assert blocks[4].text.endswith("$$")

    # Block 5: Paragraph ("Bảng thông số:")
    assert blocks[5].block_type == BlockType.PARAGRAPH
    assert "Bảng thông số:" in blocks[5].text

    # Block 6: Table
    assert blocks[6].block_type == BlockType.TABLE
    assert "| Tên | Giá trị |" in blocks[6].text
    assert "| Alpha | 0.05 |" in blocks[6].text

    # Block 7: Image caption
    assert blocks[7].block_type == BlockType.IMAGE_CAPTION
    assert "[Hình vẽ trang 1:" in blocks[7].text

    # Block 8: Paragraph
    assert blocks[8].block_type == BlockType.PARAGRAPH
    assert "Đoạn văn kết thúc trang." in blocks[8].text


def test_math_block_never_cut_across_chunks():
    # Small target chunk size to force splitting
    splitter = MarkdownStructureSplitter(target_chunk_size=30)
    markdown = """# Mục 1: Công thức

Đoạn mở đầu có độ dài vừa đủ để bắt đầu một chunk.

$$
f(x) = \\sum_{i=1}^n \\frac{a_i}{x_i^2 + b_i}
$$

Đoạn văn tiếp theo sau công thức toán.
"""
    nodes = splitter.split_page_to_nodes(
        content=markdown,
        page_number=2,
        doc_id="doc_math_test",
        doc_title="Giải Tích",
    )
    assert len(nodes) >= 2

    # Verify the entire math block is contained intact in one of the nodes
    math_found_intact = False
    for node in nodes:
        if "$$\nf(x) = \\sum" in node.text:
            math_found_intact = True
            assert node.metadata["has_formula"] is True
            assert "$$\n" in node.text
            assert "\n$$" in node.text
            assert "Giải Tích > Mục 1: Công thức" in node.text

    assert math_found_intact is True


def test_table_preservation_and_metadata():
    splitter = MarkdownStructureSplitter(target_chunk_size=500)
    markdown = """## Bảng Tra Cứu

| Mã | Tên gọi | Mô tả |
| :--- | :--- | :--- |
| A1 | Hạt nhân | Cấu trúc trung tâm |
| B2 | Vỏ electron | Chứa các hạt electron |
"""
    nodes = splitter.split_page_to_nodes(
        content=markdown,
        page_number=5,
        doc_id="doc_table_test",
        doc_title="Vật Lý Hạt",
    )
    assert len(nodes) == 1
    node = nodes[0]
    assert "[Chủ đề: Vật Lý Hạt > Bảng Tra Cứu]" in node.text
    assert "| Mã | Tên gọi | Mô tả |" in node.text
    assert "| B2 | Vỏ electron |" in node.text
    assert node.metadata["section_heading"] == "Bảng Tra Cứu"
    assert node.metadata["page_number"] == 5


def test_page_without_headings_fallback():
    splitter = MarkdownStructureSplitter(target_chunk_size=500)
    markdown = "Trang này chỉ là văn bản bài đọc không có bất kỳ tiêu đề nào."
    nodes = splitter.split_page_to_nodes(
        content=markdown,
        page_number=7,
        doc_id="doc_no_heading",
        doc_title="Văn Học",
    )
    assert len(nodes) == 1
    node = nodes[0]
    # Fallback to [Chủ đề: {doc_title} - Trang {page_number}]
    assert "[Chủ đề: Văn Học - Trang 7]" in node.text
    assert "Trang này chỉ là văn bản bài đọc" in node.text
