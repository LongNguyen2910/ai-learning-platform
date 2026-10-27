import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

logger = logging.getLogger(__name__)


class BlockType(str, Enum):
    HEADING = "heading"
    MATH_BLOCK = "math_block"
    TABLE = "table"
    PARAGRAPH = "paragraph"
    IMAGE_CAPTION = "image_caption"


@dataclass
class ParsedBlock:
    block_type: BlockType
    text: str
    token_count: int
    heading_path: list[str] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    """Fast token estimation for multilingual academic text (Vietnamese + LaTeX)."""
    words = len(text.split())
    chars = len(text)
    return max(1, max(words, int(chars / 3.5)))


class MarkdownStructureSplitter:
    """Structure-aware semantic splitter for academic Markdown documents.

    Maintains atomic integrity for LaTeX formula blocks ($$...$$), tables (|...|),
    and image captions. Automatically injects hierarchical Contextual Prefix
    headers for superior vector search recall.
    """

    def __init__(
        self,
        target_chunk_size: int = 600,
        max_chunk_size: int = 1500,
        chunk_overlap: int = 100,
    ) -> None:
        self.target_chunk_size = target_chunk_size
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap

    def parse_blocks(self, content: str) -> list[ParsedBlock]:
        """Parses raw page Markdown into structured atomic blocks using a finite state machine."""
        lines = content.splitlines()
        blocks: list[ParsedBlock] = []
        current_heading_hierarchy: dict[int, str] = {}
        i = 0
        n = len(lines)

        def get_current_heading_path() -> list[str]:
            return [
                current_heading_hierarchy[lvl]
                for lvl in sorted(current_heading_hierarchy.keys())
            ]

        while i < n:
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                i += 1
                continue

            # 1. Heading (#, ##, ###)
            heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if heading_match:
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                # Remove equal or deeper heading levels
                current_heading_hierarchy = {
                    k: v
                    for k, v in current_heading_hierarchy.items()
                    if k < level
                }
                current_heading_hierarchy[level] = heading_text

                blocks.append(
                    ParsedBlock(
                        block_type=BlockType.HEADING,
                        text=stripped,
                        token_count=estimate_tokens(stripped),
                        heading_path=get_current_heading_path(),
                    )
                )
                i += 1
                continue

            # 2. Math Block ($$ ... $$)
            if stripped.startswith("$$"):
                math_lines = [line]
                if stripped.endswith("$$") and len(stripped) > 2:
                    i += 1
                else:
                    i += 1
                    while i < n:
                        m_line = lines[i]
                        math_lines.append(m_line)
                        if "$$" in m_line:
                            i += 1
                            break
                        i += 1
                math_text = "\n".join(math_lines).strip()
                blocks.append(
                    ParsedBlock(
                        block_type=BlockType.MATH_BLOCK,
                        text=math_text,
                        token_count=estimate_tokens(math_text),
                        heading_path=get_current_heading_path(),
                    )
                )
                continue

            # 3. Table Block (| ... |)
            if stripped.startswith("|") and stripped.endswith("|"):
                table_lines = [line]
                i += 1
                while i < n:
                    t_line = lines[i]
                    t_stripped = t_line.strip()
                    if t_stripped.startswith("|") and t_stripped.endswith("|"):
                        table_lines.append(t_line)
                        i += 1
                    else:
                        break
                table_text = "\n".join(table_lines).strip()
                blocks.append(
                    ParsedBlock(
                        block_type=BlockType.TABLE,
                        text=table_text,
                        token_count=estimate_tokens(table_text),
                        heading_path=get_current_heading_path(),
                    )
                )
                continue

            # 4. Image Caption ([Hình vẽ trang X: ...] or ![...](...))
            if (
                stripped.startswith("[Hình vẽ trang")
                or (stripped.startswith("![") and stripped.endswith(")"))
            ):
                blocks.append(
                    ParsedBlock(
                        block_type=BlockType.IMAGE_CAPTION,
                        text=stripped,
                        token_count=estimate_tokens(stripped),
                        heading_path=get_current_heading_path(),
                    )
                )
                i += 1
                continue

            # 5. Normal Paragraph
            para_lines = [line]
            i += 1
            while i < n:
                p_line = lines[i]
                p_stripped = p_line.strip()
                if not p_stripped:
                    i += 1
                    break
                # Stop if encountering special block boundary
                if (
                    p_stripped.startswith("#")
                    or p_stripped.startswith("$$")
                    or (p_stripped.startswith("|") and p_stripped.endswith("|"))
                    or p_stripped.startswith("[Hình vẽ trang")
                ):
                    break
                para_lines.append(p_line)
                i += 1

            para_text = "\n".join(para_lines).strip()
            if para_text:
                blocks.append(
                    ParsedBlock(
                        block_type=BlockType.PARAGRAPH,
                        text=para_text,
                        token_count=estimate_tokens(para_text),
                        heading_path=get_current_heading_path(),
                    )
                )

        return blocks

    def split_page_to_nodes(
        self,
        content: str,
        page_number: int,
        doc_id: str,
        user_id: str | None = None,
        doc_title: str | None = None,
        start_chunk_idx: int = 0,
    ) -> list[TextNode]:
        """Assembles atomic blocks into TextNodes with Contextual Prefix and metadata."""
        blocks = self.parse_blocks(content)
        if not blocks:
            return []

        nodes: list[TextNode] = []
        current_blocks: list[ParsedBlock] = []
        current_tokens = 0
        chunk_idx = start_chunk_idx

        def emit_node(blist: list[ParsedBlock]) -> None:
            nonlocal chunk_idx
            if not blist:
                return

            # Find deepest heading path in this chunk
            best_heading_path: list[str] = []
            for b in blist:
                if len(b.heading_path) > len(best_heading_path):
                    best_heading_path = b.heading_path

            breadcrumb = " > ".join(best_heading_path) if best_heading_path else ""

            # Build contextual prefix
            if doc_title and breadcrumb:
                prefix = f"[Chủ đề: {doc_title} > {breadcrumb}]"
            elif breadcrumb:
                prefix = f"[Chủ đề: {breadcrumb}]"
            elif doc_title:
                prefix = f"[Chủ đề: {doc_title} - Trang {page_number}]"
            else:
                prefix = f"[Chủ đề: Trang {page_number}]"

            body = "\n\n".join(b.text for b in blist)
            full_text = f"{prefix}\n\n{body}"

            # Detect math formulas and image presence
            has_formula = bool(re.search(r"(?<!\\)\$.+?(?<!\\)\$", body, re.DOTALL))
            has_image = bool(re.search(r"\[Hình vẽ trang \d+:", body)) or "![" in body

            metadata: dict[str, Any] = {
                "doc_id": doc_id,
                "page_number": page_number,
                "chunk_index": chunk_idx,
                "section_heading": breadcrumb or doc_title or f"Trang {page_number}",
                "has_formula": has_formula,
                "has_image": has_image,
            }
            if user_id:
                metadata["user_id"] = str(user_id)

            # Generate deterministic RFC 4122 UUID required by Qdrant point store
            node_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_DNS,
                    f"{doc_id}_page_{page_number}_chunk_{chunk_idx}",
                )
            )
            node = TextNode(
                text=full_text,
                id_=node_id,
                metadata=metadata,
            )
            node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(
                node_id=doc_id
            )
            nodes.append(node)
            chunk_idx += 1

        for block in blocks:
            if current_tokens + block.token_count > self.target_chunk_size and current_blocks:
                overlap_block = None
                # Retain previous paragraph as overlap if reasonable in size
                if (
                    current_blocks[-1].block_type == BlockType.PARAGRAPH
                    and current_blocks[-1].token_count <= 150
                ):
                    overlap_block = current_blocks[-1]

                emit_node(current_blocks)
                current_blocks = [overlap_block] if overlap_block is not None else []
                current_tokens = overlap_block.token_count if overlap_block is not None else 0

            current_blocks.append(block)
            current_tokens += block.token_count

        if current_blocks:
            emit_node(current_blocks)

        return nodes
