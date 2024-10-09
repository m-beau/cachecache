from pathlib import Path
import shutil
import os
from typing import Union

def has_write_permission(path: Union[str, Path]) -> bool:
    """Check if the given path is writable without creating it."""
    if isinstance(path, str):
            path = Path(path)
    if path.exists():
        return os.access(path, os.W_OK)
    elif path.parent.exists():
        return os.access(path.parent, os.W_OK)
    else:
        print(f"WARNING {path.parent} does not exist - caching aborted.")
        return False
    
def has_space_left(path: Union[str, Path],
                   required_space_mb: float = 100) -> bool:
    """
    Check if there's enough space left at the given path.
    
    Parameters:
    -----------
    path : str
        The path to check for available space.
    required_space_mb : float
        The required free space in megabytes.
        
    Returns:
    --------
    bool
        True if there's enough free space, False otherwise.
    """
    try:
        _, _, free = shutil.disk_usage(path)
        free_space_mb = free / (1024 * 1024)  # Convert bytes to megabytes
        return free_space_mb >= required_space_mb
    except OSError as e:
        print(f"Error checking space at {path}: {e}")
        return False

def is_writable(path: Union[str, Path],
                required_space_mb: float = 100) -> bool:
    
    return has_space_left(path, required_space_mb) & has_write_permission(path)