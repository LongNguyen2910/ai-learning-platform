import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import app.core.models_registry  # noqa: F401
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.auth.models import User
from app.modules.auth.security import PasswordHasher, TokenManager
from app.modules.documents.models import Document, Subject
from sqlalchemy import select


async def seed():
    print("🚀 Đang khởi tạo dữ liệu mẫu cho module Lộ trình học tập (FR-12)...")

    async with AsyncSessionLocal() as session:
        # 1. Tìm hoặc tạo người dùng thử nghiệm
        user_query = select(User).where(User.email == "student@example.com")
        res = await session.execute(user_query)
        user = res.scalar_one_or_none()

        if not user:
            user = User(
                id=uuid.uuid4(),
                email="student@example.com",
                hashed_password=PasswordHasher.hash("Password123!"),
                full_name="Sinh Viên Giải Tích",
                role="user",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"✅ Đã tạo user: {user.email} (ID: {user.id})")
        else:
            print(f"ℹ️ User đã tồn tại: {user.email} (ID: {user.id})")

        # 2. Tạo môn học với ID 11111111-1111-1111-1111-111111111111
        subject_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        sub_query = select(Subject).where(Subject.id == subject_id)
        sub_res = await session.execute(sub_query)
        subject = sub_res.scalar_one_or_none()

        if not subject:
            subject = Subject(
                id=subject_id,
                user_id=user.id,
                name="Giải tích 1",
                code="MAT101",
                description="Học phần Giải tích 1 - Giới hạn, Vi phân, Tích phân hàm một biến",
                color_hex="#4F46E5",
            )
            session.add(subject)
            await session.commit()
            print(f"✅ Đã tạo môn học: {subject.name} (ID: {subject.id})")
        else:
            subject.user_id = user.id
            await session.commit()
            print(f"ℹ️ Môn học đã tồn tại: {subject.name} (ID: {subject.id})")

        # 3. Tạo tài liệu với ID 22222222-2222-2222-2222-222222222222
        doc_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        doc_query = select(Document).where(Document.id == doc_id)
        doc_res = await session.execute(doc_query)
        document = doc_res.scalar_one_or_none()

        if not document:
            document = Document(
                id=doc_id,
                user_id=user.id,
                subject_id=subject_id,
                title="Giáo trình Giải tích 1 (Toán cao cấp)",
                file_path=str(Path(settings.UPLOAD_DIR) / f"{doc_id}.pdf"),
                file_type="pdf",
                file_size_kb=2560,
                total_pages=50,
                status="ready",
            )
            session.add(document)
            await session.commit()
            print(f"✅ Đã tạo tài liệu: {document.title} (ID: {document.id})")
        else:
            document.user_id = user.id
            document.subject_id = subject_id
            await session.commit()
            print(f"ℹ️ Tài liệu đã tồn tại: {document.title} (ID: {document.id})")

        # 4. Tạo thư mục parsed storage và nội dung tài liệu mẫu
        parsed_dir = Path(settings.PARSED_DIR) / str(doc_id)
        pages_dir = parsed_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)

        meta_data = {
            "document_id": str(doc_id),
            "title": "Giáo trình Giải tích 1 (Toán cao cấp)",
            "file_path": str(Path(settings.UPLOAD_DIR) / f"{doc_id}.pdf"),
            "file_size_kb": 2560,
            "total_pages": 50,
            "status": "ready",
            "pages": [
                {"page_number": 1, "has_formula": True, "has_image": False, "char_count": 800, "file_path": str(pages_dir / "page_1.md")},
                {"page_number": 2, "has_formula": True, "has_image": False, "char_count": 1200, "file_path": str(pages_dir / "page_2.md")},
                {"page_number": 3, "has_formula": True, "has_image": False, "char_count": 1100, "file_path": str(pages_dir / "page_3.md")},
            ],
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        with open(parsed_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)

        full_doc_content = """# MỤC LỤC GIÁO TRÌNH GIẢI TÍCH 1
## Chương 1: Giới hạn và Liên tục (Trang 1 - 15)
- Bài 1: Định nghĩa giới hạn của hàm số và các tính chất cơ bản
- Bài 2: Các dạng vô định và quy tắc khử dạng vô định L'Hopital
- Bài 3: Tính liên tục của hàm số và định lý Bolzano-Cauchy

## Chương 2: Phép tính Vi phân hàm một biến (Trang 16 - 32)
- Bài 1: Khái niệm đạo hàm, ý nghĩa hình học và vật lý
- Bài 2: Bảng đạo hàm các hàm số sơ cấp và các quy tắc tính đạo hàm
- Bài 3: Định lý Rolle, Lagrange, Cauchy và công thức Taylor
- Bài 4: Khảo sát cực trị và tính lồi lõm của đồ thị hàm số

## Chương 3: Phép tính Tích phân (Trang 33 - 50)
- Bài 1: Nguyên hàm và tích phân bất định
- Bài 2: Phương pháp đổi biến số và tích phân từng phần
- Bài 3: Tích phân xác định Riemann và công thức Newton-Leibniz
- Bài 4: Ứng dụng tích phân tính diện tích hình phẳng và thể tích vật thể tròn xoay
"""
        with open(parsed_dir / "full_document.md", "w", encoding="utf-8") as f:
            f.write(full_doc_content)

        (pages_dir / "page_1.md").write_text("# Chương 1: Giới hạn và Liên tục\nNội dung bài 1: Định nghĩa giới hạn $\\lim_{x \\to x_0} f(x) = L$.", encoding="utf-8")
        (pages_dir / "page_2.md").write_text("# Chương 2: Phép tính Vi phân\nNội dung bài 2: Công thức đạo hàm $f'(x) = \\lim_{\\Delta x \\to 0} \\frac{\\Delta y}{\\Delta x}$.", encoding="utf-8")
        (pages_dir / "page_3.md").write_text("# Chương 3: Phép tính Tích phân\nNội dung bài 3: Tích phân Newton-Leibniz $\\int_a^b f(x)dx = F(b) - F(a)$.", encoding="utf-8")

        print(f"✅ Đã khởi tạo cấu trúc giáo trình mẫu tại: {parsed_dir}")

        # 5. Cấp phát JWT token cho user
        token = TokenManager.create_access_token(
            {"sub": str(user.id), "role": user.role},
            expires_delta=timedelta(days=30),
        )

        print("\n" + "=" * 70)
        print("🎉 KHỞI TẠO TEST DATA THÀNH CÔNG!")
        print("=" * 70)
        print(f"• User ID     : {user.id}")
        print(f"• Email       : {user.email}")
        print(f"• Mật khẩu    : Password123!")
        print(f"• Subject ID  : {subject_id}")
        print(f"• Document ID : {doc_id}")
        print(f"• JWT Token   :\n{token}\n")
        print("📋 Payload kiểm thử đúng như yêu cầu:")
        print(json.dumps({
            "subject_id": str(subject_id),
            "document_id": str(doc_id),
            "title": "Lộ trình Giải tích trong 4 tuần",
            "target_date": "2026-11-25",
            "available_hours_per_day": 2.0,
            "study_goal": "Đạt điểm A môn Giải tích 1"
        }, indent=2, ensure_ascii=False))
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed())
