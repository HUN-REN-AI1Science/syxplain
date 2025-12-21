"""
Base repository providing common CRUD operations.

Implements the Repository Pattern for abstracting data access,
enabling easier testing and separation of concerns.
"""
from typing import Generic, List, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from backend.infrastructure.database.models import Base

# Generic type for model classes
T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """
    Generic base repository with common CRUD operations.

    Provides a consistent interface for data access across all entities.
    Subclasses can override or extend these methods for entity-specific logic.

    Usage:
        class RunRepository(BaseRepository[Run]):
            def __init__(self, db: Session):
                super().__init__(Run, db)
    """

    def __init__(self, model: Type[T], db: Session):
        """
        Initialize the repository.

        Args:
            model: The SQLAlchemy model class to operate on
            db: Database session for queries
        """
        self.model = model
        self.db = db

    def get_by_id(self, id: UUID) -> Optional[T]:
        """
        Get an entity by its primary key.

        Args:
            id: The UUID primary key

        Returns:
            The entity if found, None otherwise
        """
        return self.db.query(self.model).filter(self.model.id == id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """
        Get all entities with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of entities
        """
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def create(self, entity: T) -> T:
        """
        Create a new entity.

        Args:
            entity: The entity instance to persist

        Returns:
            The persisted entity with generated ID
        """
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update(self, entity: T) -> T:
        """
        Update an existing entity.

        Args:
            entity: The entity instance with updated values

        Returns:
            The updated entity
        """
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, id: UUID) -> bool:
        """
        Delete an entity by ID.

        Args:
            id: The UUID of the entity to delete

        Returns:
            True if deleted, False if not found
        """
        entity = self.get_by_id(id)
        if entity:
            self.db.delete(entity)
            self.db.commit()
            return True
        return False

    def delete_entity(self, entity: T) -> None:
        """
        Delete an entity instance.

        Args:
            entity: The entity to delete
        """
        self.db.delete(entity)
        self.db.commit()

    def count(self) -> int:
        """
        Count all entities.

        Returns:
            Total number of entities
        """
        return self.db.query(self.model).count()

    def exists(self, id: UUID) -> bool:
        """
        Check if an entity exists.

        Args:
            id: The UUID to check

        Returns:
            True if exists, False otherwise
        """
        return self.db.query(self.model).filter(self.model.id == id).first() is not None
