import os
import sys
from PyQt5.QtCore import pyqtSignal, Qt, QSettings, QCoreApplication
from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QStackedWidget, QScrollArea, QFrame, QWidget, QCheckBox
)
from ...i18n.translator import get_translation
from ..main_window import get_app_icon_object
from ...utils.resolution import get_dark_theme
from ...config.constants import (
    CONFIG_ORGANIZATION_NAME
)


class TourStepWidget(QWidget):
    """
    A custom widget representing a single step or page in the feature tour.
    It neatly formats a title and its corresponding content.
    """
    def __init__(self, title_text, content_text, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title_label = QLabel(title_text)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #E0E0E0; padding-bottom: 15px;")
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
        content_label.setStyleSheet("font-size: 11pt; color: #C8C8C8; line-height: 1.8;")
        scroll_area.setWidget(content_label)
        layout.addWidget(scroll_area, 1)


class TourDialog(QDialog):
    """
    A dialog that shows a multi-page tour to the user on first launch.
    Includes a "Never show again" checkbox and uses QSettings to remember this preference.
    """
    tour_finished_normally = pyqtSignal()
    tour_skipped = pyqtSignal()
    CONFIG_APP_NAME_TOUR = "ApplicationTour"
    TOUR_SHOWN_KEY = "neverShowTourAgainV19"

    def __init__(self, parent_app, parent=None):
        """
        Initializes the dialog.

        Args:
            parent_app (DownloaderApp): A reference to the main application window.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.settings = QSettings(CONFIG_ORGANIZATION_NAME, self.CONFIG_APP_NAME_TOUR)
        self.current_step = 0
        self.parent_app = parent_app

        self.setWindowIcon(get_app_icon_object())
        self.setModal(True)
        self.setFixedSize(600, 620)
        
        self._init_ui()
        self._apply_theme()
        self._center_on_screen()

    def _tr(self, key, default_text=""):
        """Helper for translation."""
        if callable(get_translation) and self.parent_app:
            return get_translation(self.parent_app.current_selected_language, key, default_text)
        return default_text

    def _init_ui(self):
        """Initializes all UI components and layouts."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)
        steps_content = [
            ("tour_dialog_step1_title", "tour_dialog_step1_content"),
            ("tour_dialog_step2_title", "tour_dialog_step2_content"),
            ("tour_dialog_step3_title", "tour_dialog_step3_content"),
            ("tour_dialog_step4_title", "tour_dialog_step4_content"),
            ("tour_dialog_step5_title", "tour_dialog_step5_content"),
            ("tour_dialog_step6_title", "tour_dialog_step6_content"),
            ("tour_dialog_step7_title", "tour_dialog_step7_content"),
            ("tour_dialog_step8_title", "tour_dialog_step8_content"),
        ]

        self.tour_steps_widgets = []
        for title_key, content_key in steps_content:
            title = self._tr(title_key, title_key)
            content = self._tr(content_key, "Content not found.")
            step_widget = TourStepWidget(title, content)
            self.tour_steps_widgets.append(step_widget)
            self.stacked_widget.addWidget(step_widget)

        self.setWindowTitle(self._tr("tour_dialog_title", "Welcome to Kemono Downloader!"))
        bottom_controls_layout = QVBoxLayout()
        bottom_controls_layout.setContentsMargins(15, 10, 15, 15)
        bottom_controls_layout.setSpacing(12)

        self.never_show_again_checkbox = QCheckBox(self._tr("tour_dialog_never_show_checkbox", "Never show this tour again"))
        bottom_controls_layout.addWidget(self.never_show_again_checkbox, 0, Qt.AlignLeft)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        self.skip_button = QPushButton(self._tr("tour_dialog_skip_button", "Skip Tour"))
        self.skip_button.clicked.connect(self._skip_tour_action)
        self.back_button = QPushButton(self._tr("tour_dialog_back_button", "Back"))
        self.back_button.clicked.connect(self._previous_step)
        self.next_button = QPushButton(self._tr("tour_dialog_next_button", "Next"))
        self.next_button.clicked.connect(self._next_step_action)
        self.next_button.setDefault(True)

        buttons_layout.addWidget(self.skip_button)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self.back_button)
        buttons_layout.addWidget(self.next_button)

        bottom_controls_layout.addLayout(buttons_layout)
        main_layout.addLayout(bottom_controls_layout)

        self._update_button_states()

    def _apply_theme(self):
        """Applies the current theme from the parent application."""
        if self.parent_app and self.parent_app.current_theme == "dark":
            scale = getattr(self.parent_app, 'scale_factor', 1)
            self.setStyleSheet(get_dark_theme(scale))
        else:
            self.setStyleSheet("QDialog { background-color: #f0f0f0; }")

    def _center_on_screen(self):
        """Centers the dialog on the screen."""
        try:
            screen_geo = QApplication.primaryScreen().availableGeometry()
            self.move(screen_geo.center() - self.rect().center())
        except Exception as e:
            print(f"[TourDialog] Error centering dialog: {e}")

    def _next_step_action(self):
        """Moves to the next step or finishes the tour."""
        if self.current_step < len(self.tour_steps_widgets) - 1:
            self.current_step += 1
            self.stacked_widget.setCurrentIndex(self.current_step)
        else:
            self._finish_tour_action()
        self._update_button_states()

    def _previous_step(self):
        """Moves to the previous step."""
        if self.current_step > 0:
            self.current_step -= 1
            self.stacked_widget.setCurrentIndex(self.current_step)
        self._update_button_states()

    def _update_button_states(self):
        """Updates the state and text of navigation buttons."""
        is_last_step = self.current_step == len(self.tour_steps_widgets) - 1
        self.next_button.setText(self._tr("tour_dialog_finish_button", "Finish") if is_last_step else self._tr("tour_dialog_next_button", "Next"))
        self.back_button.setEnabled(self.current_step > 0)

    def _skip_tour_action(self):
        """Handles the action when the tour is skipped."""
        self._save_settings_if_checked()
        self.tour_skipped.emit()
        self.reject()

    def _finish_tour_action(self):
        """Handles the action when the tour is finished normally."""
        self._save_settings_if_checked()
        self.tour_finished_normally.emit()
        self.accept()

    def _save_settings_if_checked(self):
        """Saves the 'never show again' preference to QSettings."""
        self.settings.setValue(self.TOUR_SHOWN_KEY, self.never_show_again_checkbox.isChecked())
        self.settings.sync()

    @staticmethod
    def should_show_tour():
        """Checks QSettings to see if the tour should be shown on startup."""
        settings = QSettings(TourDialog.CONFIG_ORGANIZATION_NAME, TourDialog.CONFIG_APP_NAME_TOUR)
        never_show = settings.value(TourDialog.TOUR_SHOWN_KEY, False, type=bool)
        return not never_show

    CONFIG_ORGANIZATION_NAME = CONFIG_ORGANIZATION_NAME

    def closeEvent(self, event):
        """Ensures settings are saved if the dialog is closed via the 'X' button."""
        self._skip_tour_action()
        super().closeEvent(event)
