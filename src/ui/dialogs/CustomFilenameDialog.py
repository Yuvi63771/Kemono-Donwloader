from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QDialogButtonBox, QTextEdit
)
from PyQt5.QtCore import Qt

class CustomFilenameDialog(QDialog):
    """A dialog for creating a custom filename format string."""
    
    # --- REPLACE THE 'AVAILABLE_KEYS' LIST WITH THIS DICTIONARY ---
    DISPLAY_KEY_MAP = {
        "PostID": "id",
        "CreatorID": "user",
        "service": "service",
        "title": "title",
        "added": "added",
        "published": "published",
        "edited": "edited",
        "name": "name"
    }

    def __init__(self, current_format, current_date_format, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Filename Format")
        self.setMinimumWidth(500)

        self.current_format = current_format
        self.current_date_format = current_date_format
        
        # --- Main Layout ---
        layout = QVBoxLayout(self)

        # --- Description ---
        description_label = QLabel(
            "Create a filename format using placeholders. The date/time values for 'added', 'published', and 'edited' will be automatically shortened to your specified format."
        )
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        
        # --- Format Input ---
        format_label = QLabel("Filename Format:")
        layout.addWidget(format_label)
        self.format_input = QLineEdit(self)
        self.format_input.setText(self.current_format)
        self.format_input.setPlaceholderText("e.g., {published} {title} {id}")
        layout.addWidget(self.format_input)

        # --- Date Format Input ---
        date_format_label = QLabel("Date Format (for {added}, {published}, {edited}):")
        layout.addWidget(date_format_label)
        self.date_format_input = QLineEdit(self)
        self.date_format_input.setText(self.current_date_format)
        self.date_format_input.setPlaceholderText("e.g., YYYY-MM-DD or DD-MM-YYYY")
        layout.addWidget(self.date_format_input)

        # --- Available Keys Display ---
        keys_label = QLabel("Click to add a placeholder:")
        layout.addWidget(keys_label)
        
        keys_layout = QHBoxLayout()
        keys_layout.setSpacing(5)
        
        for display_key, internal_key in self.DISPLAY_KEY_MAP.items():
            key_button = QPushButton(f"{{{display_key}}}")
            # Use a lambda to pass the correct internal key when the button is clicked
            key_button.clicked.connect(lambda checked, key=internal_key: self.add_key_to_input(key))
            keys_layout.addWidget(key_button)
        keys_layout.addStretch()

        layout.addLayout(keys_layout)
        
        # --- OK/Cancel Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def add_key_to_input(self, key_to_insert):
        """Adds the corresponding internal key placeholder to the input field."""
        self.format_input.insert(f" {{{key_to_insert}}} ")
        self.format_input.setFocus()

    def get_format_string(self):
        """Returns the final format string from the input field."""
        return self.format_input.text().strip()

    def get_date_format_string(self):
        """Returns the date format string from its input field."""
        return self.date_format_input.text().strip()
