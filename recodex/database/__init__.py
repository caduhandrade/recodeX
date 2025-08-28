"""Database models and statistics tracking for RecodeX."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func, select
import aiosqlite

Base = declarative_base()


class TranscodeRecord(Base):
    """Record of a completed transcoding job."""
    
    __tablename__ = "transcode_records"
    
    id = Column(Integer, primary_key=True)
    input_path = Column(String, nullable=False)
    output_path = Column(String, nullable=False)
    profile_name = Column(String, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Status
    status = Column(String, nullable=False)  # pending, running, completed, failed
    error_message = Column(Text)
    
    # File information
    original_size = Column(Integer)  # bytes
    final_size = Column(Integer)  # bytes
    original_codec = Column(String)
    final_codec = Column(String)
    duration = Column(Float)  # seconds
    
    # Processing information
    processing_time = Column(Float)  # seconds
    hardware_accel_used = Column(Boolean, default=False)
    
    @property
    def compression_ratio(self) -> Optional[float]:
        """Get compression ratio (original_size / final_size)."""
        if self.original_size and self.final_size and self.final_size > 0:
            return self.original_size / self.final_size
        return None
    
    @property
    def space_saved(self) -> Optional[int]:
        """Get space saved in bytes."""
        if self.original_size and self.final_size:
            return max(0, self.original_size - self.final_size)
        return None
    
    @property
    def space_saved_percentage(self) -> Optional[float]:
        """Get space saved as percentage."""
        if self.original_size and self.space_saved is not None:
            return (self.space_saved / self.original_size) * 100
        return None


class Statistics:
    """Statistics calculations and aggregations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_total_processed(self) -> int:
        """Get total number of files processed."""
        result = await self.session.execute(
            select(func.count(TranscodeRecord.id))
            .where(TranscodeRecord.status == "completed")
        )
        return result.scalar() or 0
    
    async def get_total_space_saved(self) -> int:
        """Get total space saved in bytes."""
        result = await self.session.execute(
            select(func.sum(TranscodeRecord.original_size - TranscodeRecord.final_size))
            .where(
                TranscodeRecord.status == "completed",
                TranscodeRecord.original_size.isnot(None),
                TranscodeRecord.final_size.isnot(None),
                TranscodeRecord.original_size > TranscodeRecord.final_size
            )
        )
        return result.scalar() or 0
    
    async def get_total_original_size(self) -> int:
        """Get total original size of processed files."""
        result = await self.session.execute(
            select(func.sum(TranscodeRecord.original_size))
            .where(
                TranscodeRecord.status == "completed",
                TranscodeRecord.original_size.isnot(None)
            )
        )
        return result.scalar() or 0
    
    async def get_average_compression_ratio(self) -> float:
        """Get average compression ratio."""
        records = await self.session.execute(
            select(TranscodeRecord.original_size, TranscodeRecord.final_size)
            .where(
                TranscodeRecord.status == "completed",
                TranscodeRecord.original_size.isnot(None),
                TranscodeRecord.final_size.isnot(None),
                TranscodeRecord.final_size > 0
            )
        )
        
        ratios = []
        for original, final in records:
            ratios.append(original / final)
        
        return sum(ratios) / len(ratios) if ratios else 0.0
    
    async def get_average_processing_time(self) -> float:
        """Get average processing time in seconds."""
        result = await self.session.execute(
            select(func.avg(TranscodeRecord.processing_time))
            .where(
                TranscodeRecord.status == "completed",
                TranscodeRecord.processing_time.isnot(None)
            )
        )
        return result.scalar() or 0.0
    
    async def get_top_space_savers(self, limit: int = 10) -> List[TranscodeRecord]:
        """Get top files by space saved."""
        result = await self.session.execute(
            select(TranscodeRecord)
            .where(
                TranscodeRecord.status == "completed",
                TranscodeRecord.original_size.isnot(None),
                TranscodeRecord.final_size.isnot(None),
                TranscodeRecord.original_size > TranscodeRecord.final_size
            )
            .order_by((TranscodeRecord.original_size - TranscodeRecord.final_size).desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def get_recent_records(self, limit: int = 20) -> List[TranscodeRecord]:
        """Get recent transcoding records."""
        result = await self.session.execute(
            select(TranscodeRecord)
            .order_by(TranscodeRecord.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def get_statistics_by_profile(self) -> dict:
        """Get statistics grouped by profile."""
        result = await self.session.execute(
            select(
                TranscodeRecord.profile_name,
                func.count(TranscodeRecord.id).label("count"),
                func.sum(TranscodeRecord.original_size - TranscodeRecord.final_size).label("space_saved"),
                func.avg(TranscodeRecord.processing_time).label("avg_time")
            )
            .where(
                TranscodeRecord.status == "completed",
                TranscodeRecord.original_size.isnot(None),
                TranscodeRecord.final_size.isnot(None)
            )
            .group_by(TranscodeRecord.profile_name)
        )
        
        stats = {}
        for row in result:
            stats[row.profile_name] = {
                "count": row.count,
                "space_saved": row.space_saved or 0,
                "avg_processing_time": row.avg_time or 0.0
            }
        
        return stats
    
    async def get_statistics_by_codec(self) -> dict:
        """Get statistics grouped by codec."""
        result = await self.session.execute(
            select(
                TranscodeRecord.final_codec,
                func.count(TranscodeRecord.id).label("count"),
                func.avg(TranscodeRecord.processing_time).label("avg_time")
            )
            .where(TranscodeRecord.status == "completed")
            .group_by(TranscodeRecord.final_codec)
        )
        
        stats = {}
        for row in result:
            stats[row.final_codec or "unknown"] = {
                "count": row.count,
                "avg_processing_time": row.avg_time or 0.0
            }
        
        return stats
    
    async def get_queue_status(self) -> dict:
        """Get current queue status."""
        # Pending jobs
        pending_result = await self.session.execute(
            select(func.count(TranscodeRecord.id))
            .where(TranscodeRecord.status == "pending")
        )
        pending_count = pending_result.scalar() or 0
        
        # Running jobs
        running_result = await self.session.execute(
            select(func.count(TranscodeRecord.id))
            .where(TranscodeRecord.status == "running")
        )
        running_count = running_result.scalar() or 0
        
        # Failed jobs
        failed_result = await self.session.execute(
            select(func.count(TranscodeRecord.id))
            .where(TranscodeRecord.status == "failed")
        )
        failed_count = failed_result.scalar() or 0
        
        return {
            "pending": pending_count,
            "running": running_count,
            "failed": failed_count
        }


class DatabaseManager:
    """Database connection and session management."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.session_factory = None
    
    async def initialize(self):
        """Initialize database connection."""
        # Convert sync URL to async for SQLite
        if self.database_url.startswith("sqlite:///"):
            async_url = self.database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        else:
            async_url = self.database_url
        
        self.engine = create_async_engine(async_url, echo=False)
        self.session_factory = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def get_session(self) -> AsyncSession:
        """Get a database session."""
        if self.session_factory is None:
            await self.initialize()
        return self.session_factory()
    
    async def close(self):
        """Close database connection."""
        if self.engine:
            await self.engine.dispose()
    
    async def add_record(self, record: TranscodeRecord) -> None:
        """Add a transcoding record to the database."""
        async with await self.get_session() as session:
            session.add(record)
            await session.commit()
    
    async def update_record(self, record_id: int, **updates) -> None:
        """Update a transcoding record."""
        async with await self.get_session() as session:
            result = await session.execute(
                select(TranscodeRecord).where(TranscodeRecord.id == record_id)
            )
            record = result.scalar_one_or_none()
            
            if record:
                for key, value in updates.items():
                    setattr(record, key, value)
                await session.commit()
    
    async def get_statistics(self) -> Statistics:
        """Get statistics helper."""
        session = await self.get_session()
        return Statistics(session)