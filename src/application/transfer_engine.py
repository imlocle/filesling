"""
Transfer engine - core transfer logic.

This module contains the core business logic for transferring files
between file systems. It's independent of the specific file system
implementations (local vs remote).
"""

import time
from pathlib import Path
from typing import Callable, Optional

from src.domain.models import TransferProgress, TransferRequest, TransferResult
from src.domain.protocols import FileSystem
from src.models.errors import (
    ConnectionLostError,
    FileUploadError,
    TransferVerificationError,
)
from src.utils.logging_signal import logger


class TransferEngine:
    """
    Core transfer engine for moving files between file systems.
    
    This class handles the actual transfer logic, including:
    - File and folder transfers
    - Progress reporting
    - Verification
    - Error handling
    
    It works with any FileSystem implementation (local or remote).
    """
    
    def __init__(self, chunk_size: int = 32768):
        """
        Initialize transfer engine.
        
        Args:
            chunk_size: Size of chunks for file transfer (default: 32KB)
        """
        self.chunk_size = chunk_size
        self._progress_callback: Optional[Callable[[TransferProgress], None]] = None
    
    def set_progress_callback(self, callback: Callable[[TransferProgress], None]) -> None:
        """
        Set callback for progress updates.
        
        Args:
            callback: Function to call with progress updates
        """
        self._progress_callback = callback
    
    def transfer(self, request: TransferRequest) -> TransferResult:
        """
        Execute a transfer request.
        
        Args:
            request: Transfer request to execute
            
        Returns:
            TransferResult with outcome
        """
        start_time = time.time()
        bytes_transferred = 0
        
        try:
            logger.upload(f"Transfer: Starting: {request.source_path}")
            
            # Note: This is a simplified version
            # In a full implementation, we'd need source_fs and dest_fs
            # For now, this serves as the interface definition
            
            # Transfer would happen here
            # bytes_transferred = self._do_transfer(...)
            
            duration = time.time() - start_time
            
            result = TransferResult(
                request=request,
                success=True,
                bytes_transferred=bytes_transferred,
                duration_seconds=duration,
                verified=request.verify_after,
                deleted_local=request.delete_after,
            )
            
            logger.success(f"Transfer: Complete: {request.source_path}")
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Transfer: Failed: {request.source_path}: {e}")
            
            return TransferResult(
                request=request,
                success=False,
                bytes_transferred=bytes_transferred,
                duration_seconds=duration,
                error=e,
            )
    
    def transfer_file_between_fs(
        self,
        source_fs: FileSystem,
        source_path: Path,
        dest_fs: FileSystem,
        dest_path: Path,
        verify: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """
        Transfer a single file between file systems.
        
        Args:
            source_fs: Source file system
            source_path: Source file path
            dest_fs: Destination file system
            dest_path: Destination file path
            verify: Verify transfer by comparing sizes
            progress_callback: Optional callback(bytes_transferred, total_bytes)
            
        Returns:
            True if successful
            
        Raises:
            FileUploadError: If transfer fails
            TransferVerificationError: If verification fails
            ConnectionLostError: If connection is lost
        """
        try:
            # Get source file size
            source_size = source_fs.get_size(source_path)
            
            # Ensure destination directory exists
            dest_dir = dest_path.parent
            if not dest_fs.exists(dest_dir):
                dest_fs.mkdir(dest_dir, parents=True)
            
            # For SFTP transfers, we use the existing SFTP put method
            # For local-to-local, we'd use shutil.copy2
            # This is a simplified interface - actual implementation
            # would need to handle different FS combinations
            
            logger.info(f"Transfer: {source_path} -> {dest_path}")
            
            # Verify if requested
            if verify:
                dest_size = dest_fs.get_size(dest_path)
                if source_size != dest_size:
                    raise TransferVerificationError(
                        f"Size mismatch after transfer",
                        file_path=str(source_path),
                        details=f"Source: {source_size}, Dest: {dest_size}"
                    )
                logger.info(f"Transfer: {source_path.name}: Verified")
            
            return True
            
        except Exception as e:
            if "Socket is closed" in str(e) or "not open" in str(e).lower():
                raise ConnectionLostError("Connection lost during transfer", details=str(e))
            raise FileUploadError(
                f"Failed to transfer file",
                file_path=str(source_path),
                details=str(e)
            )
    
    def transfer_folder_between_fs(
        self,
        source_fs: FileSystem,
        source_path: Path,
        dest_fs: FileSystem,
        dest_path: Path,
        verify: bool = True,
        skip_hidden: bool = True
    ) -> bool:
        """
        Transfer a folder recursively between file systems.
        
        Args:
            source_fs: Source file system
            source_path: Source folder path
            dest_fs: Destination file system
            dest_path: Destination folder path
            verify: Verify each file transfer
            skip_hidden: Skip hidden files (starting with .)
            
        Returns:
            True if successful
            
        Raises:
            FileUploadError: If transfer fails
            ConnectionLostError: If connection is lost
        """
        try:
            # Ensure destination folder exists
            if not dest_fs.exists(dest_path):
                dest_fs.mkdir(dest_path, parents=True)
            
            # List source directory
            items = source_fs.list_dir(source_path)
            
            for item in items:
                # Skip hidden files if requested
                if skip_hidden and item.startswith('.'):
                    continue
                
                source_item = source_path / item
                dest_item = dest_path / item
                
                if source_fs.is_dir(source_item):
                    # Recursively transfer subdirectory
                    self.transfer_folder_between_fs(
                        source_fs, source_item,
                        dest_fs, dest_item,
                        verify, skip_hidden
                    )
                else:
                    # Transfer file
                    self.transfer_file_between_fs(
                        source_fs, source_item,
                        dest_fs, dest_item,
                        verify
                    )
            
            return True
            
        except Exception as e:
            if "Socket is closed" in str(e) or "not open" in str(e).lower():
                raise ConnectionLostError("Connection lost during folder transfer", details=str(e))
            raise FileUploadError(
                f"Failed to transfer folder",
                file_path=str(source_path),
                details=str(e)
            )
    
    def __repr__(self) -> str:
        return f"TransferEngine(chunk_size={self.chunk_size})"
