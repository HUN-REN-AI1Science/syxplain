"""
Repository for RunArtifact entity data access.

Provides specialized queries for artifact management.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from backend.infrastructure.database.models import RunArtifact
from backend.repositories.base import BaseRepository


class ArtifactRepository(BaseRepository[RunArtifact]):
    """
    Repository for RunArtifact entity with specialized query methods.

    Extends BaseRepository with artifact-specific operations.
    """

    def __init__(self, db: Session):
        super().__init__(RunArtifact, db)

    def get_by_run_and_filename(self, run_id: UUID, filename: str) -> RunArtifact | None:
        """
        Get an artifact by run ID and filename.

        Args:
            run_id: The run UUID
            filename: The artifact filename

        Returns:
            The artifact if found, None otherwise
        """
        return (
            self.db.query(RunArtifact)
            .filter(RunArtifact.run_id == run_id, RunArtifact.filename == filename)
            .first()
        )

    def get_run_artifacts(self, run_id: UUID) -> list[RunArtifact]:
        """
        Get all artifacts for a run.

        Args:
            run_id: The run UUID

        Returns:
            List of artifacts
        """
        return (
            self.db.query(RunArtifact)
            .filter(RunArtifact.run_id == run_id)
            .order_by(RunArtifact.created_at)
            .all()
        )

    def delete_for_run(self, run_id: UUID) -> int:
        """
        Delete all artifacts for a run.

        Args:
            run_id: The run UUID

        Returns:
            Number of artifacts deleted
        """
        count = self.db.query(RunArtifact).filter(RunArtifact.run_id == run_id).delete()
        self.db.commit()
        return count

    def create_artifact(
        self, run_id: UUID, filename: str, content: bytes, media_type: str | None = None
    ) -> RunArtifact:
        """
        Create a new artifact record.

        Args:
            run_id: The run UUID
            filename: Artifact filename
            content: Artifact content as bytes
            media_type: MIME type of the artifact

        Returns:
            The created artifact entity
        """
        artifact = RunArtifact(
            run_id=run_id, filename=filename, content=content, media_type=media_type
        )
        return self.create(artifact)
