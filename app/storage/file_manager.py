import os
import shutil
from typing import Generator
from fastapi import UploadFile

# Save uploads in the parent workspace directory to prevent Uvicorn hot-reload from killing background tasks.
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads")

class FileManager:
    def __init__(self, upload_dir: str = UPLOAD_DIR):
        self.upload_dir = upload_dir
        self.ensure_upload_dir_exists()

    def ensure_upload_dir_exists(self):
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir, exist_ok=True)

    def save_file(self, file_id: str, file: UploadFile) -> str:
        """
        Saves an uploaded file to the local directory.
        Returns the absolute file path.
        """
        self.ensure_upload_dir_exists()
        # Use file ID as the saved filename to prevent conflicts
        file_extension = os.path.splitext(file.filename)[1] if file.filename else ".pdf"
        saved_filename = f"{file_id}{file_extension}"
        file_path = os.path.join(self.upload_dir, saved_filename)
        
        # Reset current read cursor
        file.file.seek(0)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        return file_path

    def get_file_path(self, filename: str) -> str:
        """Get path for a filename under the upload directory."""
        return os.path.join(self.upload_dir, filename)

    def delete_file(self, filename: str) -> bool:
        """Deletes a file from the upload directory."""
        file_path = self.get_file_path(filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

    def file_exists(self, filename: str) -> bool:
        """Checks if a file exists."""
        return os.path.exists(self.get_file_path(filename))

file_manager = FileManager()
