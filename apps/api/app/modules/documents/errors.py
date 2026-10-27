"""User-friendly error formatting for the Document Ingestion pipeline."""


def format_user_friendly_error(stage: str | Exception, exc: Exception | None = None) -> str:
    """Translates raw Python exceptions into clear, localized Vietnamese error messages

    describing the specific pipeline stage that failed without leaking sensitive server traces.
    """
    if exc is None and isinstance(stage, Exception):
        exc = stage
        stage = "xử lý"
    elif not isinstance(stage, str):
        stage = str(stage)
    while hasattr(exc, "exceptions") and exc.exceptions:
        exc = exc.exceptions[0]

    err_str = str(exc).lower()

    # Rate limit / Quota
    if any(
        k in err_str
        for k in (
            "429",
            "resource_exhausted",
            "quota",
            "too many requests",
            "rate limit",
        )
    ):
        return f"Lỗi ở bước [{stage}]: Vượt quá giới hạn lượt gọi API (Rate limit / Quota). Vui lòng thử lại sau ít phút."

    # API Key / Authentication
    if any(
        k in err_str
        for k in (
            "api_key",
            "unauthenticated",
            "invalid_argument",
            "permission_denied",
            "forbidden",
            "401",
            "403",
        )
    ):
        return f"Lỗi ở bước [{stage}]: Khóa API không hợp lệ hoặc không có quyền truy cập. Vui lòng kiểm tra cấu hình API Key."

    # Qdrant / Vector DB
    if "qdrant" in err_str or "dimension mismatch" in err_str:
        if "dimension mismatch" in err_str:
            return f"Lỗi ở bước [{stage}]: Kích thước vector embedding không khớp với cấu hình cơ sở dữ liệu Qdrant."
        return f"Lỗi ở bước [{stage}]: Không thể kết nối hoặc lưu dữ liệu vào cơ sở dữ liệu vector Qdrant."

    # Network / Timeout
    if any(
        k in err_str
        for k in (
            "timeout",
            "timed out",
            "connecterror",
            "connection error",
            "remotedisconnected",
            "connection refused",
        )
    ):
        return f"Lỗi ở bước [{stage}]: Kết nối mạng bị gián đoạn hoặc quá thời gian chờ (Timeout). Vui lòng thử lại."

    # PDF / Corrupted file
    if any(
        k in err_str
        for k in (
            "filedataerror",
            "emptyfileerror",
            "cannot open",
            "corrupt",
            "not a pdf",
            "bad pdf",
        )
    ):
        return f"Lỗi ở bước [{stage}]: File PDF bị hỏng, mã hóa bảo vệ hoặc không thể đọc được nội dung."

    # Permission / File system security
    if (
        isinstance(exc, PermissionError)
        or "permissionerror" in err_str
        or "pathsec" in err_str
    ):
        return f"Lỗi ở bước [{stage}]: Lỗi quyền truy cập tập tin hệ thống trên máy chủ."

    # Fallback with stage name
    return f"Lỗi ở bước [{stage}]: Đã xảy ra sự cố trong quá trình xử lý. Vui lòng thử lại hoặc liên hệ quản trị viên."
