"""
Repository for File entity data access.

Provides specialized queries for file management
including user-scoped lookups and statistics.
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.infrastructure.database.models import File
from backend.repositories.base import BaseRepository


class FileRepository(BaseRepository[File]):
    """
    Repository for File entity with specialized query methods.

    Extends BaseRepository with file-specific operations like
    finding by filename and user-scoped queries.
    """

    def __init__(self, db: Session):
        super().__init__(File, db)

    def get_latest_by_filename(
        self,
        filename: str,
        user_id: UUID
    ) -> Optional[File]:
        """
        Get the most recently uploaded file with the given filename for a user.

        Args:
            filename: The filename to search for
            user_id: The owner's UUID

        Returns:
            The most recent file if found, None otherwise
        """
        return self.db.query(File).filter(
            File.filename == filename,
            File.user_id == user_id
        ).order_by(File.created_at.desc()).first()

    def get_by_filename(
        self,
        filename: str,
        user_id: Optional[UUID] = None
    ) -> Optional[File]:
        """
        Get a file by filename, optionally scoped to a user.

        Note: If user_id is not provided, returns the most recent
        file with that filename (useful for public access scenarios).

        Args:
            filename: The filename to search for
            user_id: Optional user UUID for scoping

        Returns:
            The file if found, None otherwise
        """
        query = self.db.query(File).filter(File.filename == filename)
        if user_id:
            query = query.filter(File.user_id == user_id)
        return query.order_by(File.created_at.desc()).first()

    def get_user_files(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100
    ) -> List[File]:
        """
        Get all files for a user with pagination.

        Args:
            user_id: The user's UUID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of files
        """
        return self.db.query(File).filter(
            File.user_id == user_id
        ).order_by(
            File.created_at.desc()
        ).offset(skip).limit(limit).all()

    def count_for_user(self, user_id: UUID) -> int:
        """
        Count total files for a user.

        Args:
            user_id: The user's UUID

        Returns:
            Total file count
        """
        return self.db.query(File).filter(File.user_id == user_id).count()

    def get_earliest_for_user(self, user_id: UUID) -> Optional[File]:
        """
        Get the earliest file for a user.

        Args:
            user_id: The user's UUID

        Returns:
            Earliest file or None
        """
        return self.db.query(File).filter(
            File.user_id == user_id
        ).order_by(File.created_at.asc()).first()

    def delete_all_for_user(self, user_id: UUID) -> int:
        """
        Delete all files for a user (GDPR deletion).

        Args:
            user_id: The user's UUID

        Returns:
            Number of files deleted
        """
        count = self.db.query(File).filter(File.user_id == user_id).delete()
        self.db.commit()
        return count

    def create_file(
        self,
        filename: str,
        content: bytes,
        user_id: UUID,
        media_type: Optional[str] = None
    ) -> File:
        """
        Create a new file record.

        Args:
            filename: Original filename
            content: File content as bytes
            user_id: Owner's UUID
            media_type: MIME type of the file

        Returns:
            The created file entity
        """
        file = File(
            filename=filename,
            content=content,
            user_id=user_id,
            media_type=media_type
        )
        return self.create(file)
