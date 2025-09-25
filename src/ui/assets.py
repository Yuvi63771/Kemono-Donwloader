import os
import sys
from PyQt5.QtGui import QIcon

_app_icon_cache = None

def get_app_icon_object():
    """
    Loads and caches the application icon from the assets folder.
    This function is now centralized to prevent circular imports.

    Returns:
        QIcon: The application icon object.
    """
    global _app_icon_cache
    if _app_icon_cache and not _app_icon_cache.isNull():
        return _app_icon_cache

    app_base_dir = ""
    
    if getattr(sys, 'frozen', False):
        app_base_dir = os.path.dirname(sys.executable)
    else:
        app_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    icon_path = os.path.join(app_base_dir, 'assets', 'Kemono.ico')
    
    if os.path.exists(icon_path):
        _app_icon_cache = QIcon(icon_path)
    else:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            fallback_icon_path = os.path.join(sys._MEIPASS, 'assets', 'Kemono.ico')
            if os.path.exists(fallback_icon_path):
                _app_icon_cache = QIcon(fallback_icon_path)
                return _app_icon_cache
        
        print(f"Warning: Application icon not found at {icon_path}")
        _app_icon_cache = QIcon() # Return an empty icon as a fallback
        
    return _app_icon_cache