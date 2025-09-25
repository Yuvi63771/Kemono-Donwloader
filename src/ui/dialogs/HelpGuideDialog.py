import os
import sys
from PyQt5.QtCore import QUrl, QSize, Qt
from PyQt5.QtGui import QIcon, QDesktopServices
from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QStackedWidget, QListWidget, QFrame, QWidget, QScrollArea
)
from ...i18n.translator import get_translation
from ..main_window import get_app_icon_object
from ...utils.resolution import get_dark_theme

class TourStepWidget(QWidget):
    """
    A custom widget representing a single step or page in the feature guide.
    It neatly formats a title and its corresponding content.
    """
    def __init__(self, title_text, content_text, parent=None, scale=1.0):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title_font_size = int(14 * scale)
        content_font_size = int(11 * scale)

        title_label = QLabel(title_text)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"font-size: {title_font_size}pt; font-weight: bold; color: #E0E0E0; padding-bottom: 15px;")
        layout.addWidget(title_label)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("background-color: transparent;")

        content_label = QLabel(content_text)
        content_label.setWordWrap(True)
        content_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        content_label.setTextFormat(Qt.RichText)
        content_label.setOpenExternalLinks(True)
        content_label.setStyleSheet(f"font-size: {content_font_size}pt; color: #C8C8C8; line-height: 1.8;")
        scroll_area.setWidget(content_label)
        layout.addWidget(scroll_area, 1)


class HelpGuideDialog(QDialog):
    """A multi-page dialog for displaying the feature guide with a navigation list."""
    def __init__(self, steps_data, parent_app, parent=None):
        super().__init__(parent)
        self.steps_data = steps_data
        self.parent_app = parent_app

        scale = self.parent_app.scale_factor if hasattr(self.parent_app, 'scale_factor') else 1.0

        app_icon = get_app_icon_object()
        if app_icon and not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self.setModal(True)
        self.resize(int(800 * scale), int(650 * scale))

        dialog_font_size = int(11 * scale)
        
        current_theme_style = ""
        if hasattr(self.parent_app, 'current_theme') and self.parent_app.current_theme == "dark":
            current_theme_style = get_dark_theme(scale)
        else:
            # Basic light theme fallback
            current_theme_style = f"""
                QDialog {{ background-color: #F0F0F0; border: 1px solid #B0B0B0; }}
                QLabel {{ color: #1E1E1E; }}
                QPushButton {{ 
                    background-color: #E1E1E1; 
                    color: #1E1E1E; 
                    border: 1px solid #ADADAD; 
                    padding: {int(8*scale)}px {int(15*scale)}px; 
                    border-radius: 4px; 
                    min-height: {int(25*scale)}px; 
                    font-size: {dialog_font_size}pt; 
                }}
                QPushButton:hover {{ background-color: #CACACA; }}
                QPushButton:pressed {{ background-color: #B0B0B0; }}
            """

        self.setStyleSheet(current_theme_style)
        self._init_ui()
        if self.parent_app:
            self.move(self.parent_app.geometry().center() - self.rect().center())

    def _tr(self, key, default_text=""):
        """Helper to get translation based on current app language."""
        if callable(get_translation) and self.parent_app:
            return get_translation(self.parent_app.current_selected_language, key, default_text)
        return default_text

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Title
        title_label = QLabel(self._tr("help_guide_dialog_title", "Kemono Downloader - Feature Guide"))
        scale = getattr(self.parent_app, 'scale_factor', 1.0)
        title_font_size = int(16 * scale)
        title_label.setStyleSheet(f"font-size: {title_font_size}pt; font-weight: bold; color: #E0E0E0;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Content Layout (Navigation + Stacked Pages)
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout, 1)

        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(int(220 * scale))
        self.nav_list.setStyleSheet(f"""
            QListWidget {{
                background-color: #2E2E2E;
                border: 1px solid #4A4A4A;
                border-radius: 4px;
                font-size: {int(11 * scale)}pt;
            }}
            QListWidget::item {{
                padding: 10px;
                border-bottom: 1px solid #4A4A4A;
            }}
            QListWidget::item:selected {{
                background-color: #87CEEB;
                color: #2E2E2E;
                font-weight: bold;
            }}
        """)
        content_layout.addWidget(self.nav_list)

        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)

        for title_key, content_key in self.steps_data:
            title = self._tr(title_key, title_key)
            content = self._tr(content_key, f"Content for {content_key} not found.")
            
            self.nav_list.addItem(title)
            
            step_widget = TourStepWidget(title, content, scale=scale)
            self.stacked_widget.addWidget(step_widget)

        self.nav_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)
        if self.nav_list.count() > 0:
            self.nav_list.setCurrentRow(0)

        # Footer Layout (Social links and Close button)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 10, 0, 0)
        
        # Social Media Icons
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            assets_base_dir = sys._MEIPASS
        else:
            assets_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

        github_icon_path = os.path.join(assets_base_dir, "assets", "github.png")
        instagram_icon_path = os.path.join(assets_base_dir, "assets", "instagram.png")
        discord_icon_path = os.path.join(assets_base_dir, "assets", "discord.png")

        self.github_button = QPushButton(QIcon(github_icon_path), "")
        self.instagram_button = QPushButton(QIcon(instagram_icon_path), "")
        self.discord_button = QPushButton(QIcon(discord_icon_path), "")

        icon_dim = int(24 * scale)
        icon_size = QSize(icon_dim, icon_dim)
        
        for button, tooltip_key, url in [
            (self.github_button, "help_guide_github_tooltip", "https://github.com/Yuvi9587"),
            (self.instagram_button, "help_guide_instagram_tooltip", "https://www.instagram.com/uvi.arts/"),
            (self.discord_button, "help_guide_discord_tooltip", "https://discord.gg/BqP64XTdJN")
        ]:
            button.setIconSize(icon_size)
            button.setToolTip(self._tr(tooltip_key))
            button.setFixedSize(icon_size.width() + 8, icon_size.height() + 8)
            button.setStyleSheet("background-color: transparent; border: none;")
            button.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            footer_layout.addWidget(button)

        footer_layout.addStretch(1)

        self.finish_button = QPushButton(self._tr("tour_dialog_finish_button", "Finish"))
        self.finish_button.clicked.connect(self.accept)
        footer_layout.addWidget(self.finish_button)

        main_layout.addLayout(footer_layout)