import os
import json
import re
from collections import defaultdict
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QListWidget, QRadioButton,
    QButtonGroup, QCheckBox, QSplitter, QGroupBox, QDialog, QStackedWidget,
    QScrollArea, QListWidgetItem, QSizePolicy, QProgressBar, QAbstractItemView, QFrame,
    QMainWindow, QAction, QGridLayout, 
)
from PyQt5.QtCore import Qt

class ExportLinksDialog(QDialog):
    """
    A dialog for exporting extracted links with various format options, including custom templates.
    """
    def __init__(self, links_data, parent=None):
        super().__init__(parent)
        self.links_data = links_data
        self.setWindowTitle("Export Extracted Links")
        self.setMinimumWidth(550)
        self._setup_ui()
        self._update_options_visibility()

    def _setup_ui(self):
        """Initializes the UI components of the dialog."""
        main_layout = QVBoxLayout(self)

        # Format Selection (Top Level)
        format_group = QGroupBox("Export Format")
        format_layout = QHBoxLayout()
        self.radio_txt = QRadioButton("Plain Text (.txt)")
        self.radio_json = QRadioButton("JSON (.json)")
        self.radio_txt.setChecked(True)
        format_layout.addWidget(self.radio_txt)
        format_layout.addWidget(self.radio_json)
        format_group.setLayout(format_layout)
        main_layout.addWidget(format_group)

        # TXT Options Group
        self.txt_options_group = QGroupBox("TXT Options")
        txt_options_layout = QVBoxLayout()
        
        self.txt_mode_group = QButtonGroup(self)
        self.radio_simple = QRadioButton("Simple (URL only, one per line)")
        self.radio_detailed = QRadioButton("Detailed (with checkboxes)")
        self.radio_custom = QRadioButton("Custom Format Template")
        
        self.txt_mode_group.addButton(self.radio_simple)
        self.txt_mode_group.addButton(self.radio_detailed)
        self.txt_mode_group.addButton(self.radio_custom)
        
        txt_options_layout.addWidget(self.radio_simple)
        txt_options_layout.addWidget(self.radio_detailed)
        
        self.detailed_options_widget = QWidget()
        detailed_layout = QVBoxLayout(self.detailed_options_widget)
        detailed_layout.setContentsMargins(20, 5, 0, 5)
        self.check_include_titles = QCheckBox("Include post titles as separators")
        self.check_include_link_text = QCheckBox("Include link text/description")
        self.check_include_platform = QCheckBox("Include platform (e.g., Mega, GDrive)")
        detailed_layout.addWidget(self.check_include_titles)
        detailed_layout.addWidget(self.check_include_link_text)
        detailed_layout.addWidget(self.check_include_platform)
        txt_options_layout.addWidget(self.detailed_options_widget)

        txt_options_layout.addWidget(self.radio_custom)

        self.custom_format_widget = QWidget()
        custom_layout = QVBoxLayout(self.custom_format_widget)
        custom_layout.setContentsMargins(20, 5, 0, 5)
        placeholders_label = QLabel("Available placeholders: <b>{url} {post_title} {link_text} {platform} {key}</b>")
        self.custom_format_input = QTextEdit()
        self.custom_format_input.setAcceptRichText(False)
        self.custom_format_input.setPlaceholderText("Enter your format, e.g., ({url}) or Title: {post_title}\\nLink: {url}")
        self.custom_format_input.setText("{url}")
        self.custom_format_input.setFixedHeight(80)
        custom_layout.addWidget(placeholders_label)
        custom_layout.addWidget(self.custom_format_input)
        txt_options_layout.addWidget(self.custom_format_widget)

        separator = QLabel("-" * 70)
        txt_options_layout.addWidget(separator)
        self.check_separate_files = QCheckBox("Save each platform to a separate file (e.g., export_mega.txt)")
        txt_options_layout.addWidget(self.check_separate_files)
        
        self.txt_options_group.setLayout(txt_options_layout)
        main_layout.addWidget(self.txt_options_group)

        # File Path Selection
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.browse_button = QPushButton("Browse...")
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_button)
        main_layout.addLayout(path_layout)
        
        # Action Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        self.export_button = QPushButton("Export")
        self.cancel_button = QPushButton("Cancel")
        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

        # Connections
        self.radio_txt.toggled.connect(self._update_options_visibility)
        self.radio_simple.toggled.connect(self._update_options_visibility)
        self.radio_detailed.toggled.connect(self._update_options_visibility)
        self.radio_custom.toggled.connect(self._update_options_visibility)
        self.browse_button.clicked.connect(self._browse)
        self.export_button.clicked.connect(self._accept_and_export)
        self.cancel_button.clicked.connect(self.reject)
        
        self.radio_simple.setChecked(True)

    def _update_options_visibility(self):
        is_txt = self.radio_txt.isChecked()
        self.txt_options_group.setVisible(is_txt)
        
        self.detailed_options_widget.setVisible(is_txt and self.radio_detailed.isChecked())
        self.custom_format_widget.setVisible(is_txt and self.radio_custom.isChecked())
        
    def _browse(self, base_filepath):
        is_separate_files_mode = self.radio_txt.isChecked() and self.check_separate_files.isChecked()
        
        if is_separate_files_mode:
            dir_path = QFileDialog.getExistingDirectory(self, "Select Folder to Save Files")
            if dir_path:
                self.path_input.setText(os.path.join(dir_path, "exported_links"))
        else:
            default_filename = "exported_links"
            file_filter = "Text Files (*.txt)"
            if self.radio_json.isChecked():
                default_filename += ".json"
                file_filter = "JSON Files (*.json)"
            else:
                default_filename += ".txt"
            
            filepath, _ = QFileDialog.getSaveFileName(self, "Save Links", default_filename, file_filter)
            if filepath:
                self.path_input.setText(filepath)

    def _accept_and_export(self):
        filepath = self.path_input.text().strip()
        if not filepath:
            QMessageBox.warning(self, "Input Error", "Please select a file path or folder.")
            return

        try:
            if self.radio_txt.isChecked():
                self._write_txt_file(filepath)
            else:
                self._write_json_file(filepath)
            
            QMessageBox.information(self, "Export Successful", "Links successfully exported!")
            self.accept()
        except OSError as e:
            QMessageBox.critical(self, "Export Error", f"Could not write to file:\n{e}")

    def _write_txt_file(self, base_filepath):
        if self.check_separate_files.isChecked():
            links_by_platform = defaultdict(list)
            for _, _, link_url, platform, _ in self.links_data:
                sanitized_platform = re.sub(r'[<>:"/\\|?*]', '_', platform.lower().replace(' ', '_'))
                links_by_platform[sanitized_platform].append(link_url)
            
            base, ext = os.path.splitext(base_filepath)
            if not ext: ext = ".txt"

            for platform_key, links in links_by_platform.items():
                platform_filepath = f"{base}_{platform_key}{ext}"
                with open(platform_filepath, 'w', encoding='utf-8') as f:
                    for url in links:
                        f.write(url + "\n")
            return

        with open(base_filepath, 'w', encoding='utf-8') as f:
            if self.radio_simple.isChecked():
                for _, _, link_url, _, _ in self.links_data:
                    f.write(link_url + "\n")

            elif self.radio_detailed.isChecked():
                include_titles = self.check_include_titles.isChecked()
                include_text = self.check_include_link_text.isChecked()
                include_platform = self.check_include_platform.isChecked()
                current_title = None
                for post_title, link_text, link_url, platform, _ in self.links_data:
                    if include_titles and post_title != current_title:
                        if current_title is not None: f.write("\n" + "="*60 + "\n\n")
                        f.write(f"# Post: {post_title}\n")
                        current_title = post_title
                    line_parts = [link_url]
                    if include_platform: line_parts.append(f"Platform: {platform}")
                    if include_text and link_text: line_parts.append(f"Description: {link_text}")
                    f.write(" | ".join(line_parts) + "\n")
            
            elif self.radio_custom.isChecked():
                template = self.custom_format_input.toPlainText().replace("\\n", "\n")
                for post_title, link_text, link_url, platform, decryption_key in self.links_data:
                    formatted_line = template.format(
                        url=link_url,
                        post_title=post_title,
                        link_text=link_text,
                        platform=platform,
                        key=decryption_key or ""
                    )
                    f.write(formatted_line)
                    if not template.endswith('\n'):
                        f.write('\n')

    def _write_json_file(self, filepath):
        output_data = []
        for post_title, link_text, link_url, platform, decryption_key in self.links_data:
            output_data.append({
                "post_title": post_title,
                "url": link_url,
                "link_text": link_text,
                "platform": platform,
                "key": decryption_key or None
            })
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)