"""
File Storage Service for Course Production

Handles file upload and storage for voice samples and video files
"""

import logging
import uuid
from pathlib import Path
from typing import Optional, Tuple
from fastapi import UploadFile

logger = logging.getLogger(__name__)


class CourseProductionFileStorage:
    """File storage service for course production files"""

    def __init__(self, base_storage_path: Optional[str] = None):
        """
        Initialize file storage

        Args:
            base_storage_path: Base storage path (defaults to uploads/course_production/)
        """
        if base_storage_path:
            self.base_path = Path(base_storage_path)
        else:
            # Default to uploads/course_production/ in project root
            self.base_path = Path(__file__).parent.parent.parent.parent / "uploads" / "course_production"

        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_voice_sample(
        self,
        file: UploadFile,
        profile_id: str
    ) -> Tuple[str, str]:
        """
        Save voice sample file

        Args:
            file: Uploaded file
            profile_id: Voice profile ID

        Returns:
            Tuple of (file_id, file_path)
        """
        # Create profile-specific directory
        profile_dir = self.base_path / "samples" / profile_id
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique file ID
        file_id = str(uuid.uuid4())

        # Get file extension
        original_filename = file.filename or "sample"
        ext = Path(original_filename).suffix or ".wav"

        # Save file
        file_path = profile_dir / f"{file_id}{ext}"

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Saved voice sample: {file_path} (profile: {profile_id})")

        return file_id, str(file_path)

    async def save_video_file(
        self,
        file: UploadFile,
        instructor_id: str,
        course_id: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Save video file

        Args:
            file: Uploaded file
            instructor_id: Instructor ID
            course_id: Optional course ID

        Returns:
            Tuple of (file_id, file_path)
        """
        # Create directory structure
        if course_id:
            video_dir = self.base_path / "videos" / instructor_id / course_id
        else:
            video_dir = self.base_path / "videos" / instructor_id / "raw"

        video_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique file ID
        file_id = str(uuid.uuid4())

        # Get file extension
        original_filename = file.filename or "video"
        ext = Path(original_filename).suffix or ".mp4"

        # Save file
        file_path = video_dir / f"{file_id}{ext}"

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Saved video file: {file_path} (instructor: {instructor_id})")

        return file_id, str(file_path)

    def get_file_path(self, file_id: str, file_type: str = "sample") -> Optional[Path]:
        """
        Get file path by file ID

        Args:
            file_id: File ID
            file_type: File type ('sample' or 'video')

        Returns:
            File path or None if not found
        """
        if file_type == "sample":
            search_dir = self.base_path / "samples"
        elif file_type == "video":
            search_dir = self.base_path / "videos"
        else:
            return None

        # Search for file with matching ID
        for file_path in search_dir.rglob(f"{file_id}*"):
            if file_path.is_file():
                return file_path

        return None

    def delete_file(self, file_path: str) -> bool:
        """
        Delete file

        Args:
            file_path: File path to delete

        Returns:
            True if deleted, False otherwise
        """
        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                path.unlink()
                logger.info(f"Deleted file: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False


# Global instance
_file_storage: Optional[CourseProductionFileStorage] = None


def get_file_storage() -> CourseProductionFileStorage:
    """Get file storage instance (singleton)"""
    global _file_storage
    if _file_storage is None:
        _file_storage = CourseProductionFileStorage()
    return _file_storage
