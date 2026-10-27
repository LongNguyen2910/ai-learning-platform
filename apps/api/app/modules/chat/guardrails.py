"""Heuristic guardrails (0ms, no LLM call) for homework detection & prompt-injection defense.

See docs/SOCRATIC_PROMPT_AND_GUARDRAIL_DESIGN.md §5.
"""

import re
import unicodedata
from dataclasses import dataclass, field

# 1. Phát hiện yêu cầu giải trực tiếp
HOMEWORK_INTENT_PATTERNS: list[str] = [
    r"(giải|làm|tính)\s+(hộ|giúp|dùm|giùm|cho)\s+(mình|em|tôi|tớ)?\s*(bài|câu|đề|với|nhé|nha|này)",
    r"(cho|xin)\s+(mình\s+|em\s+|tôi\s+)?(đáp\s+án|kết\s+quả|lời\s+giải)",
    r"giải\s+chi\s+tiết\s+(bài|câu|đề)",
    r"hãy\s+giải\s+(bài|câu|toán|đề|phương\s+trình|hệ)",
    r"đáp\s+án\s+(là\s+gì|của\s+câu|của\s+bài|câu\s+\d+)",
    r"\b(solve|answer)\s+(this|the\s+following|my)\b",
    r"\bgive\s+me\s+the\s+(answer|solution)\b",
]

# 2. Phát hiện cấu trúc đề trắc nghiệm thi cử
EXAM_QUESTION_PATTERNS: list[str] = [
    r"(^|\n)\s*câu\s+\d+\s*[:.)]",
    r"(^|\s)[A-D][.)]\s+.*\n\s*[A-D][.)]\s+",
    r"(khoanh|chọn)\s+(vào\s+)?(đáp\s+án|phương\s+án|câu)\s+(đúng|sai)",
    r"khẳng\s+định\s+nào\s+sau\s+đây\s+(là\s+)?(đúng|sai)",
    r"phát\s+biểu\s+nào\s+sau\s+đây\s+(là\s+)?(đúng|sai)",
]

# 3. Phát hiện Prompt Injection & Bẻ khóa vai trò
JAILBREAK_PATTERNS: list[str] = [
    r"bỏ\s+qua\s+(hết\s+|toàn\s+bộ\s+|mọi\s+|các\s+)?(hướng\s+dẫn|chỉ\s+thị|quy\s+tắc|lệnh)(\s+trước)?",
    r"quên\s+(hết\s+|đi\s+)?(mọi\s+|các\s+|toàn\s+bộ\s+)?(hướng\s+dẫn|chỉ\s+thị|quy\s+tắc)",
    r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above)\s+(instructions|rules|prompts?)",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"tôi\s+là\s+(giáo\s+viên|giảng\s+viên|chuyên\s+gia|admin|quản\s+trị\s+viên)",
    r"đây\s+không\s+phải\s+là\s+bài\s+tập",
    r"act\s+as\s+an?\s+unrestricted",
    r"(developer|dan|god)\s+mode",
    r"chế\s+độ\s+(không\s+giới\s+hạn|nhà\s+phát\s+triển)",
    r"(system\s+prompt|chỉ\s+thị\s+hệ\s+thống)",
]

_HOMEWORK_RE = [re.compile(p, re.IGNORECASE) for p in HOMEWORK_INTENT_PATTERNS]
_EXAM_RE = [re.compile(p, re.IGNORECASE) for p in EXAM_QUESTION_PATTERNS]
_JAILBREAK_RE = [re.compile(p, re.IGNORECASE) for p in JAILBREAK_PATTERNS]

# 5.2. Thông điệp từ chối chuẩn khi Toggle OFF
HOMEWORK_REFUSAL_MESSAGE = (
    "Nhận thấy câu hỏi của bạn là một bài tập/câu hỏi ôn luyện. Để hỗ trợ bạn rèn luyện "
    "tư duy tự giải quyết vấn đề, hệ thống không cung cấp đáp án trực tiếp khi ở chế độ "
    "thường. Hãy bật **Chế độ Socratic Gia sư** trên góc màn hình để nhận gợi ý từng bước nhé!"
)

JAILBREAK_REFUSAL_MESSAGE = (
    "Mình là gia sư học tập nên luôn giữ nguyên các nguyên tắc sư phạm của nền tảng và "
    "không thể thay đổi vai trò hay cung cấp đáp án trực tiếp. Nếu bạn đang làm bài tập, "
    "hãy bật **Chế độ Socratic Gia sư** để mình cùng bạn đi từng bước nhé!"
)


@dataclass(frozen=True)
class GuardrailResult:
    is_homework: bool
    is_exam_structure: bool
    is_jailbreak: bool
    matched_patterns: list[str] = field(default_factory=list)

    @property
    def should_block_direct_answer(self) -> bool:
        """Fail-closed: any homework OR jailbreak signal blocks direct answering."""
        return self.is_homework or self.is_exam_structure or self.is_jailbreak


def normalize_text(text: str) -> str:
    """NFC-normalize (Vietnamese diacritics can arrive decomposed) and lowercase."""
    return unicodedata.normalize("NFC", text or "").lower()


def _match_any(patterns: list[re.Pattern[str]], text: str) -> list[str]:
    return [p.pattern for p in patterns if p.search(text)]


def detect_homework_intent(text: str) -> bool:
    normalized = normalize_text(text)
    return bool(_match_any(_HOMEWORK_RE, normalized) or _match_any(_EXAM_RE, normalized))


def detect_jailbreak(text: str) -> bool:
    return bool(_match_any(_JAILBREAK_RE, normalize_text(text)))


def analyze_query(text: str) -> GuardrailResult:
    normalized = normalize_text(text)
    homework = _match_any(_HOMEWORK_RE, normalized)
    exam = _match_any(_EXAM_RE, normalized)
    jailbreak = _match_any(_JAILBREAK_RE, normalized)
    return GuardrailResult(
        is_homework=bool(homework),
        is_exam_structure=bool(exam),
        is_jailbreak=bool(jailbreak),
        matched_patterns=homework + exam + jailbreak,
    )
