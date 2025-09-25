# src/ui/utils/resolution.py

# --- Standard Library Imports ---
import os

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import (
    QSplitter, QScrollArea, QFrame, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QStackedWidget, QButtonGroup, QRadioButton, QCheckBox,
    QListWidget, QTextEdit, QApplication
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIntValidator, QFont # <-- Import QFont

# --- Local Application Imports ---
# Assuming execution from project root
from ..config.constants import *


def setup_ui(main_app):
    """
    Initializes and scales the user interface for the DownloaderApp.
    
    Args:
        main_app: The instance of the main DownloaderApp.
    """
    scale = float(main_app.settings.value(UI_SCALE_KEY, 1.0))
    main_app.scale_factor = scale

    default_font = QApplication.font()
    base_font_size = 9 # Use a standard base size
    default_font.setPointSize(int(base_font_size * scale))
    main_app.setFont(default_font)

    default_font = QApplication.font()
    base_font_size = 9 # Use a standard base size
    default_font.setPointSize(int(base_font_size * scale))
    main_app.setFont(default_font)
    # --- END: Improved Scaling Logic ---

    main_app.main_splitter = QSplitter(Qt.Horizontal)
    
    # --- Use a scroll area for the left panel for consistency ---
    left_scroll_area = QScrollArea()
    left_scroll_area.setWidgetResizable(True)
    left_scroll_area.setFrameShape(QFrame.NoFrame)

    left_panel_widget = QWidget()
    left_layout = QVBoxLayout(left_panel_widget)
    left_scroll_area.setWidget(left_panel_widget)

    right_panel_widget = QWidget()
    right_layout = QVBoxLayout(right_panel_widget)
    
    left_layout.setContentsMargins(10, 10, 10, 10)
    right_layout.setContentsMargins(10, 10, 10, 10)
    apply_theme_to_app(main_app, main_app.current_theme, initial_load=True)

    # --- URL and Page Range ---
    main_app.url_input_widget = QWidget()
    url_input_layout = QHBoxLayout(main_app.url_input_widget)
    url_input_layout.setContentsMargins(0, 0, 0, 0)
    main_app.url_label_widget = QLabel()
    url_input_layout.addWidget(main_app.url_label_widget)
    main_app.link_input = QLineEdit()
    main_app.link_input.setPlaceholderText("e.g., https://kemono.su/patreon/user/12345 or .../post/98765")
    main_app.link_input.textChanged.connect(main_app.update_custom_folder_visibility)
    url_input_layout.addWidget(main_app.link_input, 1)
    main_app.empty_popup_button = QPushButton("🎨")
    special_font_size = int(9.5 * scale) 
    main_app.empty_popup_button.setStyleSheet(f"""
        padding: {4*scale}px {6*scale}px;
        font-size: {special_font_size}pt;
    """)
    main_app.empty_popup_button.clicked.connect(main_app._show_empty_popup)
    url_input_layout.addWidget(main_app.empty_popup_button)
    main_app.page_range_label = QLabel(main_app._tr("page_range_label_text", "Page Range:"))
    main_app.page_range_label.setStyleSheet("font-weight: bold; padding-left: 10px;")
    url_input_layout.addWidget(main_app.page_range_label)
    main_app.start_page_input = QLineEdit()
    main_app.start_page_input.setPlaceholderText(main_app._tr("start_page_input_placeholder", "Start"))
    main_app.start_page_input.setFixedWidth(int(50 * scale))
    main_app.start_page_input.setValidator(QIntValidator(1, 99999))
    url_input_layout.addWidget(main_app.start_page_input)
    main_app.to_label = QLabel(main_app._tr("page_range_to_label_text", "to"))
    url_input_layout.addWidget(main_app.to_label)
    main_app.end_page_input = QLineEdit()
    main_app.end_page_input.setPlaceholderText(main_app._tr("end_page_input_placeholder", "End"))
    main_app.end_page_input.setFixedWidth(int(50 * scale))
    main_app.end_page_input.setToolTip(main_app._tr("end_page_input_tooltip", "For creator URLs: Specify the ending page number..."))
    main_app.end_page_input.setValidator(QIntValidator(1, 99999))
    url_input_layout.addWidget(main_app.end_page_input)
    main_app.url_placeholder_widget = QWidget()
    placeholder_layout = QHBoxLayout(main_app.url_placeholder_widget)
    placeholder_layout.setContentsMargins(0, 0, 0, 0)
    main_app.fav_mode_active_label = QLabel(main_app._tr("fav_mode_active_label_text", "⭐ Favorite Mode is active..."))
    main_app.fav_mode_active_label.setAlignment(Qt.AlignCenter)
    placeholder_layout.addWidget(main_app.fav_mode_active_label)
    main_app.url_or_placeholder_stack = QStackedWidget()
    main_app.url_or_placeholder_stack.addWidget(main_app.url_input_widget)
    main_app.url_or_placeholder_stack.addWidget(main_app.url_placeholder_widget)
    left_layout.addWidget(main_app.url_or_placeholder_stack)

    # --- Download Location ---
    main_app.download_location_label_widget = QLabel()
    left_layout.addWidget(main_app.download_location_label_widget)
    dir_layout = QHBoxLayout()
    main_app.dir_input = QLineEdit()
    main_app.dir_input.setPlaceholderText("Select folder where downloads will be saved")
    main_app.dir_button = QPushButton("Browse...")
    main_app.dir_button.clicked.connect(main_app.browse_directory)
    dir_layout.addWidget(main_app.dir_input, 1)
    dir_layout.addWidget(main_app.dir_button)
    left_layout.addLayout(dir_layout)

    # --- Filters and Custom Folder Container ---
    main_app.filters_and_custom_folder_container_widget = QWidget()
    filters_and_custom_folder_layout = QHBoxLayout(main_app.filters_and_custom_folder_container_widget)
    filters_and_custom_folder_layout.setContentsMargins(0, 5, 0, 0)
    filters_and_custom_folder_layout.setSpacing(10)
    main_app.character_filter_widget = QWidget()
    character_filter_v_layout = QVBoxLayout(main_app.character_filter_widget)
    character_filter_v_layout.setContentsMargins(0, 0, 0, 0)
    character_filter_v_layout.setSpacing(2)
    main_app.character_label = QLabel("🎯 Filter by Character(s) (comma-separated):")
    character_filter_v_layout.addWidget(main_app.character_label)
    char_input_and_button_layout = QHBoxLayout()
    char_input_and_button_layout.setContentsMargins(0, 0, 0, 0)
    char_input_and_button_layout.setSpacing(10)
    main_app.character_input = QLineEdit()
    main_app.character_input.setPlaceholderText("e.g., Tifa, Aerith, (Cloud, Zack)")
    char_input_and_button_layout.addWidget(main_app.character_input, 3)
    main_app.char_filter_scope_toggle_button = QPushButton()
    main_app._update_char_filter_scope_button_text()
    char_input_and_button_layout.addWidget(main_app.char_filter_scope_toggle_button, 1)
    character_filter_v_layout.addLayout(char_input_and_button_layout)
    
    # --- Custom Folder Widget Definition ---
    main_app.custom_folder_widget = QWidget()
    custom_folder_v_layout = QVBoxLayout(main_app.custom_folder_widget)
    custom_folder_v_layout.setContentsMargins(0, 0, 0, 0)
    custom_folder_v_layout.setSpacing(2)
    main_app.custom_folder_label = QLabel("🗄️ Custom Folder Name (Single Post Only):")
    main_app.custom_folder_input = QLineEdit()
    main_app.custom_folder_input.setPlaceholderText("Optional: Save this post to specific folder")
    custom_folder_v_layout.addWidget(main_app.custom_folder_label)
    custom_folder_v_layout.addWidget(main_app.custom_folder_input)
    main_app.custom_folder_widget.setVisible(False)
    
    filters_and_custom_folder_layout.addWidget(main_app.character_filter_widget, 1)
    filters_and_custom_folder_layout.addWidget(main_app.custom_folder_widget, 1)
    left_layout.addWidget(main_app.filters_and_custom_folder_container_widget)

    # --- Word Manipulation Container ---
    word_manipulation_container_widget = QWidget()
    word_manipulation_outer_layout = QHBoxLayout(word_manipulation_container_widget)
    word_manipulation_outer_layout.setContentsMargins(0, 0, 0, 0)
    word_manipulation_outer_layout.setSpacing(15)
    skip_words_widget = QWidget()
    skip_words_vertical_layout = QVBoxLayout(skip_words_widget)
    skip_words_vertical_layout.setContentsMargins(0, 0, 0, 0)
    skip_words_vertical_layout.setSpacing(2)
    main_app.skip_words_label_widget = QLabel()
    skip_words_vertical_layout.addWidget(main_app.skip_words_label_widget)
    skip_input_and_button_layout = QHBoxLayout()
    skip_input_and_button_layout.setContentsMargins(0, 0, 0, 0)
    skip_input_and_button_layout.setSpacing(10)
    main_app.skip_words_input = QLineEdit()
    main_app.skip_words_input.setPlaceholderText("e.g., WM, WIP, sketch, preview")
    skip_input_and_button_layout.addWidget(main_app.skip_words_input, 1)
    main_app.skip_scope_toggle_button = QPushButton()
    main_app._update_skip_scope_button_text()
    skip_input_and_button_layout.addWidget(main_app.skip_scope_toggle_button, 0)
    skip_words_vertical_layout.addLayout(skip_input_and_button_layout)
    word_manipulation_outer_layout.addWidget(skip_words_widget, 7)
    remove_words_widget = QWidget()
    remove_words_vertical_layout = QVBoxLayout(remove_words_widget)
    remove_words_vertical_layout.setContentsMargins(0, 0, 0, 0)
    remove_words_vertical_layout.setSpacing(2)
    main_app.remove_from_filename_label_widget = QLabel()
    remove_words_vertical_layout.addWidget(main_app.remove_from_filename_label_widget)
    main_app.remove_from_filename_input = QLineEdit()
    main_app.remove_from_filename_input.setPlaceholderText("e.g., patreon, HD")
    remove_words_vertical_layout.addWidget(main_app.remove_from_filename_input)
    word_manipulation_outer_layout.addWidget(remove_words_widget, 3)
    left_layout.addWidget(word_manipulation_container_widget)

    # --- File Filter Layout ---
    file_filter_layout = QVBoxLayout()
    file_filter_layout.setContentsMargins(0, 10, 0, 0)
    file_filter_layout.addWidget(QLabel("Filter Files:"))
    radio_button_layout = QHBoxLayout()
    radio_button_layout.setSpacing(10)
    main_app.radio_group = QButtonGroup(main_app)
    main_app.radio_all = QRadioButton("All")
    main_app.radio_images = QRadioButton("Images/GIFs")
    main_app.radio_videos = QRadioButton("Videos")
    main_app.radio_only_archives = QRadioButton("📦 Only Archives")
    main_app.radio_only_audio = QRadioButton("🎧 Only Audio")
    main_app.radio_only_links = QRadioButton("🔗 Only Links")
    main_app.radio_more = QRadioButton("More") 

    main_app.radio_all.setChecked(True)
    for btn in [main_app.radio_all, main_app.radio_images, main_app.radio_videos, main_app.radio_only_archives, main_app.radio_only_audio, main_app.radio_only_links, main_app.radio_more]:
        main_app.radio_group.addButton(btn)
        radio_button_layout.addWidget(btn)
    main_app.favorite_mode_checkbox = QCheckBox()
    main_app.favorite_mode_checkbox.setChecked(False)
    radio_button_layout.addWidget(main_app.favorite_mode_checkbox)
    radio_button_layout.addStretch(1)
    file_filter_layout.addLayout(radio_button_layout)
    left_layout.addLayout(file_filter_layout)

    # --- Checkboxes Group ---
    checkboxes_group_layout = QVBoxLayout()
    checkboxes_group_layout.setSpacing(10)
    row1_layout = QHBoxLayout()
    row1_layout.setSpacing(10)
    main_app.skip_zip_checkbox = QCheckBox("Skip archives")
    main_app.skip_zip_checkbox.setToolTip("Skip Common Archives (Eg.. Zip, Rar, 7z)")
    main_app.skip_zip_checkbox.setChecked(True)
    row1_layout.addWidget(main_app.skip_zip_checkbox)
    main_app.download_thumbnails_checkbox = QCheckBox("Download Thumbnails Only")
    row1_layout.addWidget(main_app.download_thumbnails_checkbox)
    main_app.scan_content_images_checkbox = QCheckBox("Scan Content for Images")
    main_app.scan_content_images_checkbox.setChecked(main_app.scan_content_images_setting)
    row1_layout.addWidget(main_app.scan_content_images_checkbox)
    main_app.compress_images_checkbox = QCheckBox("Compress to WebP")
    main_app.compress_images_checkbox.setToolTip("Compress images > 1.5MB to WebP format (requires Pillow).")
    row1_layout.addWidget(main_app.compress_images_checkbox)
    main_app.keep_duplicates_checkbox = QCheckBox("Keep Duplicates")
    main_app.keep_duplicates_checkbox.setToolTip("If checked, downloads all files from a post even if they have the same name.")
    row1_layout.addWidget(main_app.keep_duplicates_checkbox)
    row1_layout.addStretch(1)
    checkboxes_group_layout.addLayout(row1_layout)

    # --- Advanced Settings ---
    advanced_settings_label = QLabel("⚙️ Advanced Settings:")
    checkboxes_group_layout.addWidget(advanced_settings_label)
    advanced_row1_layout = QHBoxLayout()
    advanced_row1_layout.setSpacing(10)

    # --- REORDERED CHECKBOXES ---
    main_app.use_subfolder_per_post_checkbox = QCheckBox("Subfolder per Post")
    main_app.use_subfolder_per_post_checkbox.toggled.connect(main_app.update_ui_for_subfolders)
    main_app.use_subfolder_per_post_checkbox.setChecked(True)    
    advanced_row1_layout.addWidget(main_app.use_subfolder_per_post_checkbox)

    main_app.date_prefix_checkbox = QCheckBox("Date Prefix")
    main_app.date_prefix_checkbox.setToolTip("When 'Subfolder per Post' is active, prefix the folder name with the post's upload date.")
    advanced_row1_layout.addWidget(main_app.date_prefix_checkbox)
    
    main_app.use_subfolders_checkbox = QCheckBox("Separate Folders by Known.txt")
    main_app.use_subfolders_checkbox.setChecked(False)
    main_app.use_subfolders_checkbox.toggled.connect(main_app.update_ui_for_subfolders)
    advanced_row1_layout.addWidget(main_app.use_subfolders_checkbox)
    # --- END REORDER ---

    main_app.use_cookie_checkbox = QCheckBox("Use Cookie")
    main_app.use_cookie_checkbox.setChecked(main_app.use_cookie_setting)
    main_app.cookie_text_input = QLineEdit()
    main_app.cookie_text_input.setPlaceholderText("if no Select cookies.txt)")
    main_app.cookie_text_input.setText(main_app.cookie_text_setting)
    advanced_row1_layout.addWidget(main_app.use_cookie_checkbox)
    advanced_row1_layout.addWidget(main_app.cookie_text_input, 2)
    main_app.cookie_browse_button = QPushButton("Browse...")
    main_app.cookie_browse_button.setFixedWidth(int(80 * scale))
    advanced_row1_layout.addWidget(main_app.cookie_browse_button)
    advanced_row1_layout.addStretch(1)
    checkboxes_group_layout.addLayout(advanced_row1_layout)
    advanced_row2_layout = QHBoxLayout()
    advanced_row2_layout.setSpacing(10)
    multithreading_layout = QHBoxLayout()
    multithreading_layout.setContentsMargins(0, 0, 0, 0)
    main_app.use_multithreading_checkbox = QCheckBox("Use Multithreading")
    main_app.use_multithreading_checkbox.setChecked(True)
    multithreading_layout.addWidget(main_app.use_multithreading_checkbox)
    main_app.thread_count_label = QLabel("Threads:")
    multithreading_layout.addWidget(main_app.thread_count_label)
    main_app.thread_count_input = QLineEdit("4")
    main_app.thread_count_input.setFixedWidth(int(40 * scale))
    main_app.thread_count_input.setValidator(QIntValidator(1, MAX_THREADS))
    multithreading_layout.addWidget(main_app.thread_count_input)
    advanced_row2_layout.addLayout(multithreading_layout)
    main_app.external_links_checkbox = QCheckBox("Show External Links in Log")
    advanced_row2_layout.addWidget(main_app.external_links_checkbox)
    main_app.manga_mode_checkbox = QCheckBox("Renaming Mode")
    advanced_row2_layout.addWidget(main_app.manga_mode_checkbox)
    advanced_row2_layout.addStretch(1)
    checkboxes_group_layout.addLayout(advanced_row2_layout)
    left_layout.addLayout(checkboxes_group_layout)

    # --- Action Buttons ---
    main_app.standard_action_buttons_widget = QWidget()
    btn_layout = QHBoxLayout(main_app.standard_action_buttons_widget)
    btn_layout.setContentsMargins(0, 10, 0, 0)
    btn_layout.setSpacing(10)
    main_app.download_btn = QPushButton("⬇️ Start Download")
    font = main_app.download_btn.font()
    font.setBold(True)
    main_app.download_btn.setFont(font)
    main_app.download_btn.clicked.connect(main_app.start_download)
    main_app.pause_btn = QPushButton("⏸️ Pause Download")
    main_app.pause_btn.setEnabled(False)
    main_app.pause_btn.clicked.connect(main_app._handle_pause_resume_action)
    main_app.cancel_btn = QPushButton("❌ Cancel & Reset UI")
    main_app.cancel_btn.setEnabled(False)
    main_app.cancel_btn.clicked.connect(main_app.cancel_download_button_action)
    main_app.error_btn = QPushButton("Error")
    main_app.error_btn.setToolTip("View files skipped due to errors and optionally retry them.")
    main_app.error_btn.setEnabled(True)
    btn_layout.addWidget(main_app.download_btn)
    btn_layout.addWidget(main_app.pause_btn)
    btn_layout.addWidget(main_app.cancel_btn)
    btn_layout.addWidget(main_app.error_btn)
    main_app.favorite_action_buttons_widget = QWidget()
    favorite_buttons_layout = QHBoxLayout(main_app.favorite_action_buttons_widget)
    main_app.favorite_mode_artists_button = QPushButton("🖼️ Favorite Artists")
    main_app.favorite_mode_posts_button = QPushButton("📄 Favorite Posts")
    main_app.favorite_scope_toggle_button = QPushButton()
    favorite_buttons_layout.addWidget(main_app.favorite_mode_artists_button)
    favorite_buttons_layout.addWidget(main_app.favorite_mode_posts_button)
    favorite_buttons_layout.addWidget(main_app.favorite_scope_toggle_button)
    main_app.bottom_action_buttons_stack = QStackedWidget()
    main_app.bottom_action_buttons_stack.addWidget(main_app.standard_action_buttons_widget)
    main_app.bottom_action_buttons_stack.addWidget(main_app.favorite_action_buttons_widget)
    left_layout.addWidget(main_app.bottom_action_buttons_stack)
    left_layout.addSpacing(10)

    # --- Known Names Layout ---
    known_chars_label_layout = QHBoxLayout()
    known_chars_label_layout.setSpacing(10)
    main_app.known_chars_label = QLabel("🎭 Known Shows/Characters (for Folder Names):")
    known_chars_label_layout.addWidget(main_app.known_chars_label)
    main_app.open_known_txt_button = QPushButton("Open Known.txt")
    main_app.open_known_txt_button.setFixedWidth(int(120 * scale))
    known_chars_label_layout.addWidget(main_app.open_known_txt_button)
    main_app.character_search_input = QLineEdit()
    main_app.character_search_input.setPlaceholderText("Search characters...")
    known_chars_label_layout.addWidget(main_app.character_search_input, 1)
    left_layout.addLayout(known_chars_label_layout)
    main_app.character_list = QListWidget()
    main_app.character_list.setSelectionMode(QListWidget.ExtendedSelection)
    left_layout.addWidget(main_app.character_list, 1)
    char_manage_layout = QHBoxLayout()
    char_manage_layout.setSpacing(10)
    main_app.new_char_input = QLineEdit()
    main_app.new_char_input.setPlaceholderText("Add new show/character name")
    main_app.add_char_button = QPushButton("➕ Add")
    main_app.add_to_filter_button = QPushButton("⤵️ Add to Filter")
    main_app.add_to_filter_button.setToolTip("Select names... to add to the 'Filter by Character(s)' field.")
    main_app.delete_char_button = QPushButton("🗑️ Delete Selected")
    main_app.delete_char_button.setToolTip("Delete the selected name(s)...")
    main_app.add_char_button.clicked.connect(main_app._handle_ui_add_new_character)
    main_app.new_char_input.returnPressed.connect(main_app.add_char_button.click)
    main_app.delete_char_button.clicked.connect(main_app.delete_selected_character)
    char_manage_layout.addWidget(main_app.new_char_input, 2)
    char_manage_layout.addWidget(main_app.add_char_button, 0)
    main_app.known_names_help_button = QPushButton("?")
    main_app.known_names_help_button.setFixedWidth(int(45 * scale))
    main_app.known_names_help_button.clicked.connect(main_app._show_feature_guide)
    main_app.history_button = QPushButton("📜")
    main_app.history_button.setFixedWidth(int(45 * scale))
    main_app.history_button.setToolTip(main_app._tr("history_button_tooltip_text", "View download history"))
    main_app.future_settings_button = QPushButton("⚙️")
    main_app.future_settings_button.setFixedWidth(int(45 * scale))
    main_app.future_settings_button.clicked.connect(main_app._show_future_settings_dialog)
    main_app.support_button = QPushButton("❤️ Support")
    main_app.support_button.setFixedWidth(int(100 * scale))
    main_app.support_button.setToolTip("Support the application developer.")
    char_manage_layout.addWidget(main_app.add_to_filter_button, 1)
    char_manage_layout.addWidget(main_app.delete_char_button, 1)
    char_manage_layout.addWidget(main_app.known_names_help_button, 0)
    char_manage_layout.addWidget(main_app.history_button, 0)
    char_manage_layout.addWidget(main_app.future_settings_button, 0)
    char_manage_layout.addWidget(main_app.support_button, 0)
    left_layout.addLayout(char_manage_layout)
    left_layout.addStretch(0)

    # --- Right Panel (Logs) ---
    right_panel_widget.setLayout(right_layout)
    log_title_layout = QHBoxLayout()
    main_app.progress_log_label = QLabel("📜 Progress Log:")
    log_title_layout.addWidget(main_app.progress_log_label)
    log_title_layout.addStretch(1)
    main_app.link_search_input = QLineEdit()
    main_app.link_search_input.setPlaceholderText("Search Links...")
    main_app.link_search_input.setVisible(False)
    log_title_layout.addWidget(main_app.link_search_input)
    main_app.link_search_button = QPushButton("🔎")
    main_app.link_search_button.setVisible(False)
    main_app.link_search_button.setFixedWidth(int(30 * scale))
    log_title_layout.addWidget(main_app.link_search_button)
  
    discord_controls_layout = QHBoxLayout()

    main_app.discord_scope_toggle_button = QPushButton("Scope: Files")
    main_app.discord_scope_toggle_button.setVisible(False) # Hidden by default
    discord_controls_layout.addWidget(main_app.discord_scope_toggle_button)

    main_app.discord_message_limit_input = QLineEdit(main_app)
    main_app.discord_message_limit_input.setPlaceholderText("Msg Limit")
    main_app.discord_message_limit_input.setToolTip("Optional: Limit the number of recent messages to process.")
    main_app.discord_message_limit_input.setValidator(QIntValidator(1, 9999999, main_app))
    main_app.discord_message_limit_input.setFixedWidth(int(80 * scale))
    main_app.discord_message_limit_input.setVisible(False) # Hide it by default
    discord_controls_layout.addWidget(main_app.discord_message_limit_input)
    
    log_title_layout.addLayout(discord_controls_layout)
  
    main_app.manga_rename_toggle_button = QPushButton()
    main_app.manga_rename_toggle_button.setVisible(False)
    main_app.manga_rename_toggle_button.setFixedWidth(int(140 * scale))
    main_app._update_manga_filename_style_button_text()
    log_title_layout.addWidget(main_app.manga_rename_toggle_button)
    main_app.custom_rename_dialog_button = QPushButton("Open Dialog")
    main_app.custom_rename_dialog_button.setVisible(False) # Hide by default
    main_app.custom_rename_dialog_button.clicked.connect(main_app._show_custom_rename_dialog)
    log_title_layout.addWidget(main_app.custom_rename_dialog_button)
    main_app.manga_date_prefix_input = QLineEdit()
    main_app.manga_date_prefix_input.setPlaceholderText("Prefix for Manga Filenames")
    main_app.manga_date_prefix_input.setVisible(False)
    log_title_layout.addWidget(main_app.manga_date_prefix_input)
    main_app.multipart_toggle_button = QPushButton()
    main_app.multipart_toggle_button.setToolTip("Toggle between Multi-part and Single-stream downloads for large files.")
    main_app.multipart_toggle_button.setFixedWidth(int(130 * scale))
    main_app._update_multipart_toggle_button_text()
    log_title_layout.addWidget(main_app.multipart_toggle_button)
    main_app.EYE_ICON = "\U0001F441"
    main_app.CLOSED_EYE_ICON = "\U0001F648"
    main_app.log_verbosity_toggle_button = QPushButton(main_app.EYE_ICON)
    main_app.log_verbosity_toggle_button.setFixedWidth(int(45 * scale))
    main_app.log_verbosity_toggle_button.setStyleSheet(f"font-size: {11 * scale}pt; padding: {4 * scale}px {2 * scale}px;")
    log_title_layout.addWidget(main_app.log_verbosity_toggle_button)
    main_app.reset_button = QPushButton("🔄 Reset")
    main_app.reset_button.setFixedWidth(int(80 * scale))
    log_title_layout.addWidget(main_app.reset_button)
    right_layout.addLayout(log_title_layout)
    main_app.log_splitter = QSplitter(Qt.Vertical)
    main_app.log_view_stack = QStackedWidget()
    main_app.main_log_output = QTextEdit()
    main_app.main_log_output.setReadOnly(True)
    main_app.main_log_output.setLineWrapMode(QTextEdit.NoWrap)
    main_app.log_view_stack.addWidget(main_app.main_log_output)
    main_app.missed_character_log_output = QTextEdit()
    main_app.missed_character_log_output.setReadOnly(True)
    main_app.missed_character_log_output.setLineWrapMode(QTextEdit.NoWrap)
    main_app.log_view_stack.addWidget(main_app.missed_character_log_output)
    main_app.external_log_output = QTextEdit()
    main_app.external_log_output.setReadOnly(True)
    main_app.external_log_output.setLineWrapMode(QTextEdit.NoWrap)
    main_app.external_log_output.hide()
    main_app.log_splitter.addWidget(main_app.log_view_stack)
    main_app.log_splitter.addWidget(main_app.external_log_output)
    main_app.log_splitter.setSizes([main_app.height(), 0])
    right_layout.addWidget(main_app.log_splitter, 1)
    export_button_layout = QHBoxLayout()
    export_button_layout.addStretch(1)
    main_app.export_links_button = QPushButton(main_app._tr("export_links_button_text", "Export Links"))
    main_app.export_links_button.setFixedWidth(int(100 * scale))
    main_app.export_links_button.setEnabled(False)
    main_app.export_links_button.setVisible(False)
    export_button_layout.addWidget(main_app.export_links_button)
    main_app.download_extracted_links_button = QPushButton(main_app._tr("download_extracted_links_button_text", "Download"))
    main_app.download_extracted_links_button.setFixedWidth(int(100 * scale))
    main_app.download_extracted_links_button.setEnabled(False)
    main_app.download_extracted_links_button.setVisible(False)
    export_button_layout.addWidget(main_app.download_extracted_links_button)
    main_app.log_display_mode_toggle_button = QPushButton()
    main_app.log_display_mode_toggle_button.setFixedWidth(int(120 * scale))
    main_app.log_display_mode_toggle_button.setVisible(False)
    export_button_layout.addWidget(main_app.log_display_mode_toggle_button)
    right_layout.addLayout(export_button_layout)
    main_app.progress_label = QLabel("Progress: Idle")
    main_app.progress_label.setStyleSheet("padding-top: 5px; font-style: italic;")
    right_layout.addWidget(main_app.progress_label)
    main_app.file_progress_label = QLabel("")
    main_app.file_progress_label.setToolTip("Shows the progress of individual file downloads, including speed and size.")
    main_app.file_progress_label.setWordWrap(True)
    main_app.file_progress_label.setStyleSheet("padding-top: 2px; font-style: italic; color: #A0A0A0;")
    right_layout.addWidget(main_app.file_progress_label)

    # --- Final Assembly ---
    main_app.main_splitter.addWidget(left_scroll_area)
    main_app.main_splitter.addWidget(right_panel_widget)
    
    if main_app.width() >= 1920:
        # For wider resolutions, give more space to the log panel (right).
        main_app.main_splitter.setStretchFactor(0, 4)
        main_app.main_splitter.setStretchFactor(1, 6)
    else:
        # Default for lower resolutions, giving more space to controls (left).
        main_app.main_splitter.setStretchFactor(0, 7)
        main_app.main_splitter.setStretchFactor(1, 3)


    top_level_layout = QHBoxLayout(main_app)
    top_level_layout.setContentsMargins(0, 0, 0, 0)
    top_level_layout.addWidget(main_app.main_splitter)

    # --- Initial UI State Updates ---
    main_app.update_ui_for_subfolders(main_app.use_subfolders_checkbox.isChecked())
    main_app.update_external_links_setting(main_app.external_links_checkbox.isChecked())
    main_app.update_multithreading_label(main_app.thread_count_input.text())
    main_app.update_page_range_enabled_state()
    if main_app.manga_mode_checkbox:
        main_app.update_ui_for_manga_mode(main_app.manga_mode_checkbox.isChecked())
    if hasattr(main_app, 'link_input'):
        main_app.link_input.textChanged.connect(lambda: main_app.update_ui_for_manga_mode(main_app.manga_mode_checkbox.isChecked() if main_app.manga_mode_checkbox else False))
    main_app._load_creator_name_cache_from_json()
    main_app.load_known_names_from_util()
    main_app._update_cookie_input_visibility(main_app.use_cookie_checkbox.isChecked() if hasattr(main_app, 'use_cookie_checkbox') else False)
    main_app._handle_multithreading_toggle(main_app.use_multithreading_checkbox.isChecked())
    if hasattr(main_app, 'radio_group') and main_app.radio_group.checkedButton():
        main_app._handle_filter_mode_change(main_app.radio_group.checkedButton(), True)
        main_app.radio_group.buttonToggled.connect(main_app._handle_more_options_toggled)
        
    main_app._update_manga_filename_style_button_text()
    main_app._update_skip_scope_button_text()
    main_app._update_char_filter_scope_button_text()
    main_app._update_multithreading_for_date_mode()
    if hasattr(main_app, 'download_thumbnails_checkbox'):
        main_app._handle_thumbnail_mode_change(main_app.download_thumbnails_checkbox.isChecked())
    if hasattr(main_app, 'favorite_mode_checkbox'):
        main_app._handle_favorite_mode_toggle(False)

def get_dark_theme(scale=1):
    """
    Generates the stylesheet for the dark theme, scaled by the given factor.
    """
    # Adjust base font size for better readability
    font_size_base = 9.5
    font_size_small_base = 8.5
    
    # Apply scaling
    font_size = int(font_size_base * scale)
    font_size_small = int(font_size_small_base * scale)
    line_edit_padding = int(5 * scale)
    button_padding_v = int(5 * scale)
    button_padding_h = int(12 * scale)
    tooltip_padding = int(4 * scale)
    indicator_size = int(14 * scale)
    
    return f"""
    QWidget {{ 
        background-color: #2E2E2E; 
        color: #E0E0E0; 
        font-family: Segoe UI, Arial, sans-serif; 
        font-size: {font_size}pt;
    }}
    QLineEdit, QListWidget, QTextEdit {{ 
        background-color: #3C3F41; 
        border: 1px solid #5A5A5A; 
        padding: {line_edit_padding}px; 
        color: #F0F0F0; 
        border-radius: 4px; 
        font-size: {font_size}pt; 
    }}
    QTextEdit {{
        font-family: Consolas, Courier New, monospace;
    }}
    QPushButton {{ 
        background-color: #555; 
        color: #F0F0F0; 
        border: 1px solid #6A6A6A; 
        padding: {button_padding_v}px {button_padding_h}px; 
        border-radius: 4px; 
    }}
    QPushButton:hover {{ background-color: #656565; border: 1px solid #7A7A7A; }}
    QPushButton:pressed {{ background-color: #4A4A4A; }}
    QPushButton:disabled {{ background-color: #404040; color: #888; border-color: #555; }}
    QLabel {{ font-weight: bold; color: #C0C0C0; }}
    QRadioButton, QCheckBox {{ spacing: {int(5 * scale)}px; color: #E0E0E0; }}
    QRadioButton::indicator, QCheckBox::indicator {{ width: {indicator_size}px; height: {indicator_size}px; }}
    QListWidget {{ alternate-background-color: #353535; }}
    QListWidget::item:selected {{ background-color: #007ACC; color: #FFFFFF; }}
    QToolTip {{ 
        background-color: #4A4A4A; 
        color: #F0F0F0; 
        border: 1px solid #6A6A6A; 
        padding: {tooltip_padding}px; 
        border-radius: 3px; 
        font-size: {font_size}pt;
    }}
    QSplitter::handle {{ background-color: #5A5A5A; }}
    QSplitter::handle:horizontal {{ width: {int(5 * scale)}px; }}
    QSplitter::handle:vertical {{ height: {int(5 * scale)}px; }}
    """

def apply_theme_to_app(main_app, theme_name, initial_load=False):
    """
    Applies the selected theme and scaling to the main application window.
    """
    main_app.current_theme = theme_name
    if not initial_load:
        main_app.settings.setValue(THEME_KEY, theme_name)
        main_app.settings.sync()

    if theme_name == "dark":
        scale = getattr(main_app, 'scale_factor', 1)
        main_app.setStyleSheet(get_dark_theme(scale))
        if not initial_load:
            main_app.log_signal.emit("🎨 Switched to Dark Mode.")
    else:
        main_app.setStyleSheet("")
        if not initial_load:
            main_app.log_signal.emit("🎨 Switched to Light Mode.")
    main_app.update()
