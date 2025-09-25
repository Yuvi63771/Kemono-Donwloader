from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QRadioButton, QDialogButtonBox, QButtonGroup, QLabel, QComboBox, QHBoxLayout, QCheckBox
)
from PyQt5.QtCore import Qt
from ...utils.resolution import get_dark_theme

class MoreOptionsDialog(QDialog):
    """
    A dialog for selecting a scope, export format, and single PDF option.
    """
    SCOPE_CONTENT = "content"
    SCOPE_COMMENTS = "comments"

    def __init__(self, parent=None, current_scope=None, current_format=None, single_pdf_checked=False):
        super().__init__(parent)
        self.parent_app = parent
        self.setWindowTitle("More Options")
        self.setMinimumWidth(350)

        # ... (Layout and other widgets remain the same) ...

        layout = QVBoxLayout(self)
        self.description_label = QLabel("Please choose the scope for the action:")
        layout.addWidget(self.description_label)
        self.radio_button_group = QButtonGroup(self)
        self.radio_content = QRadioButton("Description/Content")
        self.radio_comments = QRadioButton("Comments")
        self.radio_button_group.addButton(self.radio_content)
        self.radio_button_group.addButton(self.radio_comments)
        layout.addWidget(self.radio_content)
        layout.addWidget(self.radio_comments)

        if current_scope == self.SCOPE_COMMENTS:
            self.radio_comments.setChecked(True)
        else:
            self.radio_content.setChecked(True)

        export_layout = QHBoxLayout()
        export_label = QLabel("Export as:")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PDF", "DOCX", "TXT"])

        if current_format and current_format.upper() in ["PDF", "DOCX", "TXT"]:
            self.format_combo.setCurrentText(current_format.upper())
        else:
            self.format_combo.setCurrentText("PDF")

        export_layout.addWidget(export_label)
        export_layout.addWidget(self.format_combo)
        export_layout.addStretch()
        layout.addLayout(export_layout)

        # --- UPDATED: Single PDF Checkbox ---
        self.single_pdf_checkbox = QCheckBox("Single PDF")
        self.single_pdf_checkbox.setToolTip("If checked, all text from matching posts will be compiled into one single PDF file.")
        self.single_pdf_checkbox.setChecked(single_pdf_checked)
        layout.addWidget(self.single_pdf_checkbox)

        self.format_combo.currentTextChanged.connect(self.update_single_pdf_checkbox_state)
        self.update_single_pdf_checkbox_state(self.format_combo.currentText())

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.setLayout(layout)
        self._apply_theme()
    def update_single_pdf_checkbox_state(self, text):
        """Enable the Single PDF checkbox only if the format is PDF."""
        is_pdf = (text.upper() == "PDF")
        self.single_pdf_checkbox.setEnabled(is_pdf)
        if not is_pdf:
            self.single_pdf_checkbox.setChecked(False)

    def get_selected_scope(self):
        if self.radio_comments.isChecked():
            return self.SCOPE_COMMENTS
        return self.SCOPE_CONTENT

    def get_selected_format(self):
        return self.format_combo.currentText().lower()

    def get_single_pdf_state(self):
        """Returns the state of the Single PDF checkbox."""
        return self.single_pdf_checkbox.isChecked() and self.single_pdf_checkbox.isEnabled()

    def _apply_theme(self):
        """Applies the current theme from the parent application."""
        if self.parent_app and self.parent_app.current_theme == "dark":
            # Get the scale factor from the parent app
            scale = getattr(self.parent_app, 'scale_factor', 1)
            # Call the imported function with the correct scale
            self.setStyleSheet(get_dark_theme(scale))
        else:
            # Explicitly set a blank stylesheet for light mode
            self.setStyleSheet("")
