# models/metadata.py

import os
from datetime import datetime
from typing import Dict, Any, Optional, List

class FileMetadata:
    """Class to handle file metadata tracking."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.update()

    def update(self) -> None:
        """Update metadata from the current file state."""
        try:
            stat = os.stat(self.file_path)
            self.size = stat.st_size
            self.creation_time = datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
            self.modification_time = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            self.file_type = os.path.splitext(self.file_path)[1].lower()
            self.is_readable = os.access(self.file_path, os.R_OK)
            self.is_writable = os.access(self.file_path, os.W_OK)
        except Exception as e:
            raise Exception(f"Failed to get file metadata: {str(e)}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary format."""
        return {
            "size": self.size,
            "creation_time": self.creation_time,
            "modification_time": self.modification_time,
            "file_type": self.file_type,
            "is_readable": self.is_readable,
            "is_writable": self.is_writable
        }

    @staticmethod
    def format_size(size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"


class VersionTag:
    """Class to handle version tagging."""
    
    def __init__(self, version_hash: str):
        self.version_hash = version_hash
        self.tags: List[str] = []
        self.creation_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        self.last_modified = self.creation_time

    def add_tag(self, tag: str) -> None:
        """Add a tag if it doesn't exist."""
        tag = tag.strip().lower()
        if tag and tag not in self.tags:
            self.tags.append(tag)
            self.last_modified = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    def remove_tag(self, tag: str) -> None:
        """Remove a tag if it exists."""
        tag = tag.strip().lower()
        if tag in self.tags:
            self.tags.remove(tag)
            self.last_modified = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    def to_dict(self) -> Dict[str, Any]:
        """Convert tags to dictionary format."""
        return {
            "version_hash": self.version_hash,
            "tags": self.tags,
            "creation_time": self.creation_time,
            "last_modified": self.last_modified
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VersionTag':
        """Create VersionTag instance from dictionary."""
        tag = cls(data["version_hash"])
        tag.tags = data.get("tags", [])
        tag.creation_time = data.get("creation_time", tag.creation_time)
        tag.last_modified = data.get("last_modified", tag.last_modified)
        return tag