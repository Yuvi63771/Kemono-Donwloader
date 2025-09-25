# src/app/dialogs/SupportDialog.py

# --- Standard Library Imports ---
import sys
import os

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSizePolicy
)
from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QFont, QPixmap, QDesktopServices

# --- Local Application Imports ---
from ...utils.resolution import get_dark_theme
from ..assets import get_app_icon_object

class SupportDialog(QDialog):
    """
    A redesigned dialog to showcase support and donation options in a more
    visually appealing card-based layout.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.setWindowTitle("❤️ Support the Developer")
        self.setMinimumWidth(500)

        self._init_ui()
        self._apply_theme()

    def _create_support_button(self, icon_path, title, subtitle, url, hover_color):
        """Creates a custom, clickable card widget for a support option."""
        button = QPushButton()
        button.setCursor(Qt.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        button.setMinimumHeight(120) # Give the cards some height

        # --- Button Stylesheet ---
        # Provides a modern card look with hover effects
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: #3E3E3E;
                border: 1px solid #555;
                border-radius: 8px;
                text-align: center;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
                border: 1px solid #777;
            }}
        """)

        # --- Layout for Icon and Text inside the button ---
        layout = QVBoxLayout(button)
        layout.setSpacing(5)

        # Icon
        icon_label = QLabel()
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            scale = getattr(self.parent_app, 'scale_factor', 1.0)
            icon_size = int(48 * scale)
            icon_label.setPixmap(pixmap.scaled(
                QSize(icon_size, icon_size), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            ))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        # Title Text
        title_font = self.font()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_label = QLabel(title)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("background-color: transparent; border: none;")
        layout.addWidget(title_label)

        # Subtitle Text
        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet("color: #B0B0B0; background-color: transparent; border: none;")
        subtitle_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle_label)

        # Connect click to open URL
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))

        return button

    def _init_ui(self):
        """Initializes all UI components and layouts for the dialog."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # --- Top Section ---
        app_icon = get_app_icon_object()
        if app_icon and not app_icon.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(app_icon.pixmap(QSize(64, 64)))
            icon_label.setAlignment(Qt.AlignCenter)
            main_layout.addWidget(icon_label)

        title_label = QLabel("Support the Project")
        font = title_label.font()
        font.setPointSize(16)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        info_label = QLabel(
            "If you find this application useful, please consider supporting its development. "
            "Your contribution is greatly appreciated and helps motivate future updates!"
        )
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(info_label)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)

        # --- Support Options ---
        options_layout = QHBoxLayout()
        options_layout.setSpacing(15)

        # Ko-fi Card
        kofi_button = self._create_support_button(
            get_asset_path("ko-fi.png"),
            "Ko-fi",
            "One-time support",
            "https://ko-fi.com/yuvi427183",
            "#292D32" # Darker hover for Ko-fi
        )
        
        # Patreon Card
        patreon_button = self._create_support_button(
            get_asset_path("patreon.png"),
            "Patreon",
            "Monthly support",
            "https://www.patreon.com/cw/Yuvi102", # <-- IMPORTANT: Change this URL
            "#3C2E2A" # Darker hover for Patreon
        )
        
        # Buy Me a Coffee Card
        bmac_button = self._create_support_button(
            get_asset_path("buymeacoffee.png"),
            "Buy Me a Coffee",
            "One-time support",
            "https://buymeacoffee.com/yuvi9587",
            "#403520" # Darker hover for BMAC
        )

        options_layout.addWidget(kofi_button)
        options_layout.addWidget(patreon_button)
        options_layout.addWidget(bmac_button)
        
        main_layout.addLayout(options_layout)

        # --- Close Button ---
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_button.setMinimumWidth(100)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def _apply_theme(self):
        """Applies the current theme from the parent application."""
        if self.parent_app and hasattr(self.parent_app, 'current_theme') and self.parent_app.current_theme == "dark":
            scale = getattr(self.parent_app, 'scale_factor', 1)
            self.setStyleSheet(get_dark_theme(scale))
        else:
            self.setStyleSheet("")

def get_asset_path(filename):
    """
    Gets the absolute path to a file in the assets folder,
    handling both development and frozen (PyInstaller) environments.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in a PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Running in a normal Python environment (adjust path as needed)
        # This assumes this file is in src/app/dialogs/
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    
    return os.path.join(base_path, 'assets', filename)