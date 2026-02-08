"""
File service for handling file uploads and parsing.

Encapsulates all file-related business logic including
parsing, validation, and metadata extraction.
"""

import io
import logging
import re
from dataclasses import dataclass

import pandas as pd

from backend.core.config import get_settings
from backend.core.exceptions import FileTooLargeError, FileValidationError

logger = logging.getLogger(__name__)

# Security: Allowed filename characters (whitelist approach)
SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-\s]{0,198}[a-zA-Z0-9._]$")
# Characters that indicate path traversal attempts
PATH_TRAVERSAL_PATTERNS = ["..", "/", "\\", "\x00", "%2e", "%2f", "%5c"]


@dataclass
class FileMetadata:
    """Metadata extracted from a file."""

    filename: str
    columns: list[str]
    column_types: dict[str, str]
    nan_counts: dict[str, int]
    row_count: int
    size_bytes: int
    media_type: str


class FileService:
    """
    Service for file handling operations.

    Provides unified parsing for CSV and Excel files,
    validation, and metadata extraction.
    """

    # Supported file extensions and their MIME types
    SUPPORTED_EXTENSIONS = {
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
    }

    CHUNK_SIZE = 1024 * 1024  # 1 MB

    def __init__(self):
        settings = get_settings()
        self.max_file_size = settings.analysis.max_file_size_bytes

    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to prevent path traversal and injection attacks.

        Args:
            filename: The raw filename from upload

        Returns:
            Sanitized filename

        Raises:
            FileValidationError: If filename is malicious or invalid
        """
        if not filename:
            raise FileValidationError(message="Filename cannot be empty", filename="")

        # Remove any path components (prevent path traversal)
        filename = filename.split("/")[-1].split("\\")[-1]

        # Check for path traversal patterns
        filename_lower = filename.lower()
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern in filename_lower:
                logger.warning(f"Path traversal attempt detected in filename: {filename}")
                raise FileValidationError(
                    message="Invalid filename: contains forbidden characters", filename=filename
                )

        # Remove null bytes and control characters
        filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)

        # Check length
        if len(filename) > 255:
            raise FileValidationError(
                message="Filename too long (max 255 characters)", filename=filename
            )

        if len(filename) < 3:  # Minimum: "a.x"
            raise FileValidationError(message="Filename too short", filename=filename)

        return filename

    def validate_extension(self, filename: str) -> str:
        """
        Validate file extension and return the appropriate MIME type.

        Args:
            filename: The filename to validate

        Returns:
            The MIME type for the file extension

        Raises:
            FileValidationError: If extension is not supported
        """
        # First sanitize the filename
        filename = self.sanitize_filename(filename)
        filename_lower = filename.lower()

        for ext, mime_type in self.SUPPORTED_EXTENSIONS.items():
            if filename_lower.endswith(ext):
                return mime_type

        raise FileValidationError(
            message="Unsupported file format. Please upload a CSV or Excel (.xlsx, .xls) file.",
            filename=filename,
        )

    def is_excel_file(self, filename: str) -> bool:
        """Check if the file is an Excel file based on extension."""
        filename_lower = filename.lower() if filename else ""
        return filename_lower.endswith(".xlsx") or filename_lower.endswith(".xls")

    def get_excel_engine(self, filename: str) -> str:
        """Get the appropriate pandas Excel engine for the file type."""
        filename_lower = filename.lower() if filename else ""
        return "openpyxl" if filename_lower.endswith(".xlsx") else "xlrd"

    def read_file_content(self, file_obj, filename: str) -> tuple[bytes, int]:
        """
        Read file content with size validation.

        Args:
            file_obj: File-like object to read from
            filename: Original filename for error messages

        Returns:
            Tuple of (content bytes, size in bytes)

        Raises:
            FileTooLargeError: If file exceeds size limit
        """
        content = bytearray()

        while True:
            chunk = file_obj.read(self.CHUNK_SIZE)
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > self.max_file_size:
                raise FileTooLargeError(
                    filename=filename, size_bytes=len(content), max_size_bytes=self.max_file_size
                )

        return bytes(content), len(content)

    def parse_dataframe(self, content: bytes, filename: str) -> pd.DataFrame:
        """
        Parse file content into a DataFrame.

        Args:
            content: File content as bytes
            filename: Original filename for type detection

        Returns:
            Parsed pandas DataFrame

        Raises:
            FileValidationError: If parsing fails
        """
        try:
            if self.is_excel_file(filename):
                engine = self.get_excel_engine(filename)
                return pd.read_excel(io.BytesIO(content), engine=engine)
            else:
                return pd.read_csv(io.BytesIO(content))
        except Exception as e:
            file_type = "Excel" if self.is_excel_file(filename) else "CSV"
            logger.error(f"Failed to parse {file_type} file {filename}: {e}")
            raise FileValidationError(
                message=f"Invalid {file_type} file: Could not parse the file. {e!s}",
                filename=filename,
                file_type=file_type,
            )

    def validate_dataframe(self, df: pd.DataFrame, filename: str) -> None:
        """
        Validate that the DataFrame has valid content.

        Args:
            df: The DataFrame to validate
            filename: Original filename for error messages

        Raises:
            FileValidationError: If validation fails
        """
        columns = df.columns.tolist()

        if df.empty and len(columns) == 0:
            raise FileValidationError(message="Empty file - no data found", filename=filename)

        if len(columns) == 0:
            raise FileValidationError(message="No columns detected in the file", filename=filename)

    def extract_metadata(self, df: pd.DataFrame, filename: str, content: bytes) -> FileMetadata:
        """
        Extract metadata from a DataFrame.

        Args:
            df: The parsed DataFrame
            filename: Original filename
            content: Original file content

        Returns:
            FileMetadata with column information
        """
        columns = df.columns.tolist()

        # Determine column types
        column_types = {}
        nan_counts = {}

        for col in columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                column_types[col] = "numeric"
            else:
                column_types[col] = "object"
            nan_counts[col] = int(df[col].isna().sum())

        return FileMetadata(
            filename=filename,
            columns=columns,
            column_types=column_types,
            nan_counts=nan_counts,
            row_count=len(df),
            size_bytes=len(content),
            media_type=self.SUPPORTED_EXTENSIONS.get(
                next(
                    (ext for ext in self.SUPPORTED_EXTENSIONS if filename.lower().endswith(ext)),
                    ".csv",
                ),
                "text/csv",
            ),
        )

    def process_upload(self, file_obj, filename: str) -> tuple[bytes, FileMetadata]:
        """
        Full upload processing pipeline.

        Args:
            file_obj: Uploaded file object
            filename: Original filename

        Returns:
            Tuple of (file content, metadata)

        Raises:
            FileValidationError: If validation fails
            FileTooLargeError: If file is too large
        """
        # Validate extension
        self.validate_extension(filename)

        # Read content
        content, _ = self.read_file_content(file_obj, filename)

        # Parse DataFrame
        df = self.parse_dataframe(content, filename)

        # Validate content
        self.validate_dataframe(df, filename)

        # Extract metadata
        metadata = self.extract_metadata(df, filename, content)

        logger.info(f"File {filename} validated successfully. Columns: {metadata.columns}")

        return content, metadata

    def validate_columns_exist(
        self, df: pd.DataFrame, target_variable: str, features: dict[str, str]
    ) -> None:
        """
        Validate that target and feature columns exist in the DataFrame.

        Args:
            df: The DataFrame to check
            target_variable: Name of target column
            features: Dictionary of feature columns

        Raises:
            FileValidationError: If columns are missing
        """
        file_columns = df.columns.tolist()

        if target_variable not in file_columns:
            raise FileValidationError(
                message=f"Target variable '{target_variable}' does not exist in the uploaded file. Available columns: {', '.join(file_columns)}"
            )

        invalid_features = [f for f in features if f not in file_columns]
        if invalid_features:
            raise FileValidationError(
                message=f"Features do not exist in file: {', '.join(invalid_features)}"
            )

    def get_csv_metadata(self, content: bytes, filename: str) -> dict | None:
        """
        Get CSV metadata for display in run details.

        Args:
            content: File content
            filename: Original filename

        Returns:
            Dictionary with CSV metadata or None on error
        """
        try:
            df = self.parse_dataframe(content, filename)
            return {
                "filename": filename,
                "size_bytes": len(content),
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": df.columns.tolist(),
            }
        except Exception as e:
            logger.warning(f"Failed to parse file for metadata: {e}")
            return {
                "filename": filename,
                "size_bytes": len(content),
                "row_count": None,
                "column_count": None,
                "columns": [],
            }


# Singleton instance for dependency injection
_file_service: FileService | None = None


def get_file_service() -> FileService:
    """Get or create the FileService singleton."""
    global _file_service
    if _file_service is None:
        _file_service = FileService()
    return _file_service
