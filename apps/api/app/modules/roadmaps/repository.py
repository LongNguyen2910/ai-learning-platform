import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.documents.models import Document, Subject
from app.modules.roadmaps.models import Roadmap, RoadmapNode
from app.modules.roadmaps.roadmap_tree_builder import UnpersistedNode


class RoadmapRepository:
    """Encapsulates database access for Roadmaps and hierarchical RoadmapNodes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_roadmap(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID,
        title: str,
        target_date: date | None,
        available_hours_per_day: float,
    ) -> Roadmap:
        """Creates a new roadmap record in active status."""
        roadmap = Roadmap(
            id=uuid.uuid4(),
            user_id=user_id,
            subject_id=subject_id,
            title=title,
            target_date=target_date,
            available_hours_per_day=available_hours_per_day,
            status="generating",
            progress_percentage=0.0,
        )
        self.session.add(roadmap)
        await self.session.flush()
        return roadmap

    async def get_roadmap_by_id(
        self, roadmap_id: uuid.UUID
    ) -> Roadmap | None:
        """Fetches a roadmap including its flat list of nodes ordered by index."""
        query = (
            select(Roadmap)
            .where(Roadmap.id == roadmap_id)
            .options(selectinload(Roadmap.nodes))
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_subject_by_id(
        self, subject_id: uuid.UUID
    ) -> Subject | None:
        """Fetches a subject by ID."""
        query = select(Subject).where(Subject.id == subject_id)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_document_by_id(
        self, document_id: uuid.UUID
    ) -> Document | None:
        """Fetches a document by ID."""
        query = select(Document).where(Document.id == document_id)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_roadmaps_by_subject(
        self, subject_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> list[Roadmap]:
        """Fetches all roadmaps belonging to a subject, optionally filtered by user."""
        query = select(Roadmap).where(Roadmap.subject_id == subject_id)
        if user_id is not None:
            query = query.where(Roadmap.user_id == user_id)
        query = query.order_by(Roadmap.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def persist_tree_nodes(
        self,
        roadmap_id: uuid.UUID,
        nodes: list[UnpersistedNode],
    ) -> list[RoadmapNode]:
        """Batch persists hierarchical nodes preserving parent-child relationships."""
        if not nodes:
            return []

        doc_ids = {n.document_id for n in nodes if n.document_id is not None}
        valid_doc_ids: set[uuid.UUID] = set()
        if doc_ids:
            query = select(Document.id).where(Document.id.in_(doc_ids))
            result = await self.session.execute(query)
            valid_doc_ids = set(result.scalars().all())

        db_nodes: list[RoadmapNode] = []
        for node in nodes:
            doc_id = node.document_id if node.document_id in valid_doc_ids else None
            db_node = RoadmapNode(
                id=node.temp_id,
                roadmap_id=roadmap_id,
                parent_node_id=node.parent_temp_id,
                document_id=doc_id,
                title=node.title,
                description=node.description,
                order_index=node.order_index,
                target_page_start=node.target_page_start,
                target_page_end=node.target_page_end,
                estimated_minutes=node.estimated_minutes,
                is_unlocked=node.is_unlocked,
                is_completed=node.is_completed,
            )
            db_nodes.append(db_node)
            self.session.add(db_node)

        await self.session.flush()
        return db_nodes

    async def update_status(
        self, roadmap_id: uuid.UUID, status: str
    ) -> None:
        """Updates roadmap lifecycle status (generating, active, completed)."""
        roadmap = await self.get_roadmap_by_id(roadmap_id)
        if roadmap is None:
            return
        roadmap.status = status
        await self.session.flush()
