import hashlib
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def calculate_file_hash(file_path: Path, algorithm: str = 'md5') -> str:
    """Calculate hash of a file"""
    if algorithm == 'md5':
        hash_obj = hashlib.md5()
    elif algorithm == 'sha256':
        hash_obj = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")
    
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except (OSError, IOError) as e:
        logger.error(f"Error calculating hash for {file_path}: {e}")
        return ""

def calculate_data_hash(data: bytes, algorithm: str = 'md5') -> str:
    """Calculate hash of data bytes"""
    if algorithm == 'md5':
        hash_obj = hashlib.md5()
    elif algorithm == 'sha256':
        hash_obj = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")
    
    hash_obj.update(data)
    return hash_obj.hexdigest()

def format_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"
