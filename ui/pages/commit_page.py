# ui/pages/commit_page.py - Enhanced with responsive design and corrected commit logic

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
import pytz
import threading

# Import from utils package
from utils.time_utils import get_current_times # Assuming this exists as per original code
from utils.file_utils import format_size
from utils.type_handler import FileTypeHandler

# Assuming standardized time/user functions are available if needed elsewhere
# from utils.time_utils import get_formatted_time, get_current_username


class ToolTip:
    """Tooltip class for adding hover help text to widgets."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.scheduled = None

        # Use bind tags to avoid conflicts with other bindings
        self.widget.bind("<Enter>", self.schedule_show, add="+")
        self.widget.bind("<Leave>", self.hide_tooltip, add="+")
        self.widget.bind("<ButtonPress>", self.hide_tooltip, add="+")

    def schedule_show(self, event=None):
        """Schedule tooltip to appear after a short delay."""
        self.cancel_schedule()
        self.scheduled = self.widget.after(600, self.show_tooltip)

    def cancel_schedule(self):
        """Cancel the scheduled tooltip appearance."""
        if self.scheduled:
            self.widget.after_cancel(self.scheduled)
            self.scheduled = None

    def show_tooltip(self, event=None):
        """Show tooltip window."""
        self.hide_tooltip()  # Ensure any existing tooltip is removed

        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        # Create tooltip window
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x-100}+{y}")

        # Create tooltip content
        frame = tk.Frame(self.tooltip, background="#ffffe0", borderwidth=1, relief="solid")
        frame.pack(fill="both", expand=True)

        label = tk.Label(
            frame,
            text=self.text,
            background="#ffffe0",
            foreground="#333333",
            font=("Segoe UI", 9),
            padx=5,
            pady=2,
            justify="left"
        )
        label.pack()

    def hide_tooltip(self, event=None):
        """Hide tooltip window."""
        self.cancel_schedule()
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


class CommitPage:
    """UI page for committing file changes with responsive design."""

    def __init__(self, parent, version_manager, backup_manager, settings_manager, shared_state, colors=None, ui_scale=1.0, font_scale=1.0):
        """Initialize commit page with necessary services and responsive design."""
        self.parent = parent
        self.version_manager = version_manager
        self.backup_manager = backup_manager
        self.settings_manager = settings_manager
        self.settings = settings_manager.settings
        self.shared_state = shared_state
        self.ui_scale = ui_scale
        self.font_scale = font_scale

        # Define standard padding scaled to screen size
        self.STANDARD_PADDING = int(10 * self.ui_scale)
        self.SMALL_PADDING = int(5 * self.ui_scale)
        self.LARGE_PADDING = int(20 * self.ui_scale)

        # Define color palette
        if colors:
            self.colors = colors
        else:
            # Default modernized color palette
            self.colors = {
                'primary': "#1976d2",       # Deeper blue for primary actions
                'primary_dark': "#004ba0",  # Darker variant for hover states
                'primary_light': "#63a4ff", # Lighter variant for backgrounds
                'secondary': "#546e7a",     # More muted secondary color
                'success': "#2e7d32",       # Deeper green for success
                'danger': "#c62828",        # Deeper red for errors/danger
                'warning': "#f57f17",       # Warmer orange for warnings
                'info': "#0277bd",          # Deep blue for information
                'light': "#f5f5f5",         # Light background
                'dark': "#263238",          # Deep dark for text
                'white': "#ffffff",         # Pure white
                'border': "#cfd8dc",        # Subtle border color
                'background': "#eceff1",    # Slightly blue-tinted background
                'card': "#ffffff",          # Card background
                'disabled': "#e0e0e0",      # Disabled elements
                'disabled_text': "#9e9e9e", # Disabled text
                'highlight': "#bbdefb"      # Highlight/selection color
            }

        # Initialize state
        self.selected_file = shared_state.get_selected_file()
        self.has_changes = False
        self.type_handler = FileTypeHandler()
        # Get username using the utility function if available, else fallback
        try:
            from utils.time_utils import get_current_username
            self.username = get_current_username()
        except ImportError:
            self.username = os.getlogin() # Fallback

        self.suggested_messages = []
        self.animation_running = False
        self._hide_feedback_timer = None
        self.current_layout = "wide"

        # Get settings
        self.backup_folder = self.settings.get("backup_folder", "backups")
        os.makedirs(self.backup_folder, exist_ok=True)

        # Set up UI components
        self._create_ui()

        # Register callbacks for file changes
        self.shared_state.add_file_callback(self._on_file_updated)
        self.shared_state.add_monitoring_callback(self._on_file_changed)

    def _create_ui(self):
        """Create the user interface with responsive grid layout."""
        # Create main frame with grid
        self.frame = ttk.Frame(self.parent)
        self.frame.grid(row=0, column=0, sticky='nsew')

        # Make frame responsive
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(0, weight=0)  # Header - fixed height
        self.frame.grid_rowconfigure(1, weight=0)  # File section - fixed height
        self.frame.grid_rowconfigure(2, weight=1)  # Info section - flexible height
        self.frame.grid_rowconfigure(3, weight=0)  # Commit section - fixed height

        # Create content sections
        self._create_header_section()
        self._create_file_section()
        self._create_file_info_section()
        self._create_commit_section()

        # Register for resize events with debounce
        self.resize_timer = None
        self.frame.bind('<Configure>', self._on_frame_configure)

        # Add cleanup on frame destruction
        self.frame.bind('<Destroy>', lambda e: self._cleanup())

    def _create_header_section(self):
        """Create responsive header section with title and status."""
        self.header_frame = self._create_card_container(
            self.frame,
            row=0,
            column=0,
            sticky='ew',
            padx=self.STANDARD_PADDING,
            pady=(self.STANDARD_PADDING, self.SMALL_PADDING)
        )

        # Title area
        self.title_label = tk.Label(
            self.header_frame,
            text="Commit Changes",
            font=("Segoe UI", int(18 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card']
        )
        self.title_label.pack(side='left', padx=self.STANDARD_PADDING, pady=self.STANDARD_PADDING)

        # Status indicator on right side
        self.status_indicator = tk.Label(
            self.header_frame,
            text="No file selected",
            font=("Segoe UI", int(10 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['card'],
            padx=self.STANDARD_PADDING
        )
        self.status_indicator.pack(side='right', padx=self.STANDARD_PADDING, pady=self.STANDARD_PADDING)

    def _create_file_section(self):
        """Create unified file section (selection or display) with card design."""
        # Create card container
        self.file_section = self._create_card_container(
            self.frame,
            row=1,
            column=0,
            sticky='ew',
            padx=self.STANDARD_PADDING,
            pady=self.SMALL_PADDING
        )

        # Section title
        self.file_title = tk.Label(
            self.file_section,
            text="File Selection",
            font=("Segoe UI", int(12 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card']
        )
        self.file_title.pack(anchor='w', padx=self.STANDARD_PADDING, pady=(self.STANDARD_PADDING, self.SMALL_PADDING))

        # Separator
        separator = ttk.Separator(self.file_section, orient='horizontal')
        separator.pack(fill='x', padx=self.STANDARD_PADDING, pady=(0, self.SMALL_PADDING))

        # Content area - will be filled by either file selector or file info
        self.file_content = tk.Frame(self.file_section, bg=self.colors['card'])
        self.file_content.pack(fill='x', expand=True, padx=self.STANDARD_PADDING, pady=(0, self.STANDARD_PADDING))

        # Either show file info or file selector
        if self.selected_file and os.path.exists(self.selected_file):
            self._show_file_info()
        else:
            self._show_file_selector()

    def _create_file_info_section(self):
        """Create responsive file information section with card design."""
        # Create card container
        self.info_section = self._create_card_container(
            self.frame,
            row=2,
            column=0,
            sticky='nsew',
            padx=self.STANDARD_PADDING,
            pady=self.SMALL_PADDING
        )

        # Section title
        self.info_title = tk.Label(
            self.info_section,
            text="File Information",
            font=("Segoe UI", int(12 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card']
        )
        self.info_title.pack(anchor='w', padx=self.STANDARD_PADDING, pady=(self.STANDARD_PADDING, self.SMALL_PADDING))

        # Separator
        separator = ttk.Separator(self.info_section, orient='horizontal')
        separator.pack(fill='x', padx=self.STANDARD_PADDING, pady=(0, self.SMALL_PADDING))

        # Status bar for change indicator
        self.status_bar = tk.Frame(
            self.info_section,
            height=int(4 * self.ui_scale),
            bg=self.colors['secondary']
        )
        self.status_bar.pack(fill='x', padx=self.STANDARD_PADDING)

        # Metadata area
        self.metadata_frame = tk.Frame(self.info_section, bg=self.colors['card'])
        self.metadata_frame.pack(fill='both', expand=True, padx=self.STANDARD_PADDING, pady=self.SMALL_PADDING)

        # Style for metadata display
        self.metadata_text = tk.Text(
            self.metadata_frame,
            height=int(10 * self.ui_scale),
            font=("Segoe UI", int(10 * self.font_scale)),
            wrap=tk.WORD,
            relief="flat",
            bd=0,
            bg=self.colors['card'],
            fg=self.colors['dark'],
            padx=self.SMALL_PADDING,
            pady=self.SMALL_PADDING,
            state=tk.DISABLED # Start disabled
        )
        self.metadata_text.pack(side='left', fill='both', expand=True)

        # Add scrollbar with modern styling
        scrollbar = ttk.Scrollbar(
            self.metadata_frame,
            orient="vertical",
            command=self.metadata_text.yview
        )
        scrollbar.pack(side='right', fill='y')
        self.metadata_text.configure(yscrollcommand=scrollbar.set)

        # Update the metadata display
        self._update_metadata_display()

    def _create_commit_section(self):
        """Create responsive commit section with card design."""
        # Create card container
        self.commit_section = self._create_card_container(
            self.frame,
            row=3,
            column=0,
            sticky='ew',
            padx=self.STANDARD_PADDING,
            pady=(self.SMALL_PADDING, self.STANDARD_PADDING)
        )

        # Section title
        self.commit_title = tk.Label(
            self.commit_section,
            text="Commit Changes",
            font=("Segoe UI", int(12 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card']
        )
        self.commit_title.pack(anchor='w', padx=self.STANDARD_PADDING, pady=(self.STANDARD_PADDING, self.SMALL_PADDING))

        # Separator
        separator = ttk.Separator(self.commit_section, orient='horizontal')
        separator.pack(fill='x', padx=self.STANDARD_PADDING, pady=(0, self.SMALL_PADDING))

        # Commit message label
        self.commit_label = tk.Label(
            self.commit_section,
            text="Describe your changes:",
            font=("Segoe UI", int(10 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card']
        )
        self.commit_label.pack(anchor='w', padx=self.STANDARD_PADDING, pady=(self.SMALL_PADDING, self.SMALL_PADDING))

        # Modern styled commit message entry
        self.entry_frame = tk.Frame(
            self.commit_section,
            bg=self.colors['white'],
            highlightbackground=self.colors['border'],
            highlightthickness=1,
            bd=0
        )
        self.entry_frame.pack(fill='x', padx=self.STANDARD_PADDING, pady=(0, self.STANDARD_PADDING))

        self.commit_message_entry = tk.Entry(
            self.entry_frame,
            font=("Segoe UI", int(11 * self.font_scale)),
            bd=0,
            relief='flat',
            bg=self.colors['white'],
            fg=self.colors['dark'],
            insertbackground=self.colors['dark']
        )
        self.commit_message_entry.pack(fill='x', expand=True, padx=self.STANDARD_PADDING, pady=self.STANDARD_PADDING)
        self.commit_message_entry.bind("<Return>", self._commit_file_action)
        self.commit_message_entry.bind("<KeyRelease>", self._suggest_messages)

        # Suggestions area
        self.suggestions_frame = tk.Frame(
            self.commit_section,
            bg=self.colors['card']
        )
        self.suggestions_frame.pack(fill='x', padx=self.STANDARD_PADDING, pady=(0, self.STANDARD_PADDING))

        self.suggestions_label = tk.Label(
            self.suggestions_frame,
            text="Quick suggestions:",
            font=("Segoe UI", int(9 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['card']
        )
        self.suggestions_label.pack(anchor='w', pady=(0, self.SMALL_PADDING))

        # Container for suggestion buttons
        self.suggestions_buttons = tk.Frame(
            self.suggestions_frame,
            bg=self.colors['card']
        )
        self.suggestions_buttons.pack(fill='x')

        # Action buttons (commit and reset)
        self.action_frame = tk.Frame(
            self.commit_section,
            bg=self.colors['card']
        )
        self.action_frame.pack(fill='x', padx=self.STANDARD_PADDING, pady=(self.SMALL_PADDING, self.STANDARD_PADDING))

        # Reset button
        self.reset_btn = self._create_button(
            self.action_frame,
            "Reset",
            self._reset_form,
            is_primary=False,
            icon="🔄"
        )
        self.reset_btn.pack(side='left', padx=(0, self.SMALL_PADDING))

        # Commit button
        self.commit_btn = self._create_button(
            self.action_frame,
            "Commit Changes",
            self._commit_file_action,
            is_primary=True,
            icon="💾"
        )
        self.commit_btn.pack(side='right')

        # Add tooltip to commit button
        ToolTip(self.commit_btn, "Save the current state of your file\nwith a descriptive message")

        # Initially disable commit components if no file is selected
        if not self.selected_file or not os.path.exists(self.selected_file):
            self.commit_message_entry.config(state=tk.DISABLED)
            self._set_button_state(self.commit_btn, False)
            self._set_button_state(self.reset_btn, False)

        # Generate suggestions
        self._update_suggestions()

    def _create_card_container(self, parent, row, column, sticky, padx, pady):
        """Create a card-like container with subtle shadow for sections."""
        container = tk.Frame(
            parent,
            bg=self.colors['card'],
            bd=1,
            relief="solid", # Use solid for a clear border
            highlightbackground=self.colors['border'], # Color of the border
            highlightthickness=1 # Thickness of the border
        )
        # Removed highlightcolor and focuscolor as they are less relevant for simple frames
        container.grid(row=row, column=column, sticky=sticky, padx=padx, pady=pady)
        return container

    def _show_file_selector(self):
        """Show file selection interface."""
        # Clear any existing content
        for widget in self.file_content.winfo_children():
            widget.destroy()

        # Create selector frame
        selector_frame = tk.Frame(
            self.file_content,
            bg=self.colors['card'],
            padx=self.STANDARD_PADDING,
            pady=self.STANDARD_PADDING
        )
        selector_frame.pack(fill='both', expand=True)

        # Icon
        icon_label = tk.Label(
            selector_frame,
            text="📄",
            font=("Segoe UI", int(36 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['card']
        )
        icon_label.pack(pady=(self.SMALL_PADDING, self.SMALL_PADDING))

        # Text
        text_label = tk.Label(
            selector_frame,
            text="Select a file to track",
            font=("Segoe UI", int(12 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['card']
        )
        text_label.pack(pady=(0, self.STANDARD_PADDING))

        # Select button
        self.select_btn = self._create_button(
            selector_frame,
            "Select File",
            self._select_file,
            is_primary=True
        )
        self.select_btn.pack(pady=self.SMALL_PADDING)

    def _show_file_info(self):
        """Show selected file information."""
        # Clear any existing content
        for widget in self.file_content.winfo_children():
            widget.destroy()

        # File info container
        file_info = tk.Frame(self.file_content, bg=self.colors['card'])
        file_info.pack(fill='x', expand=True)

        # Get file info
        category = self.type_handler.get_file_category(self.selected_file)
        icon = self.type_handler.get_category_icon(category)
        filename = os.path.basename(self.selected_file)
        filepath = os.path.dirname(self.selected_file)

        # File header with icon and name
        file_header = tk.Frame(file_info, bg=self.colors['card'])
        file_header.pack(fill='x', expand=True, pady=self.SMALL_PADDING)

        icon_label = tk.Label(
            file_header,
            text=icon,
            font=("Segoe UI", int(24 * self.font_scale)),
            bg=self.colors['card']
        )
        icon_label.pack(side='left', padx=(0, self.SMALL_PADDING))

        name_label = tk.Label(
            file_header,
            text=filename,
            font=("Segoe UI", int(12 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card']
        )
        name_label.pack(side='left', fill='x', expand=True, anchor='w')

        # Change file button
        change_btn = self._create_button(
            file_header,
            "Change",
            self._select_file,
            is_primary=False,
            icon="🔄"
        )
        change_btn.pack(side='right')

        # File path
        path_label = tk.Label(
            file_info,
            text=filepath,
            font=("Segoe UI", int(9 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['card'],
            anchor='w'
        )
        path_label.pack(fill='x', expand=True, pady=(self.SMALL_PADDING, self.STANDARD_PADDING))

    def _create_button(self, parent, text, command, is_primary=True, icon=None):
        """Create a modern styled button with optional icon and proper hover behavior."""
        btn_text = f"{icon} {text}" if icon else text

        # Store original colors for state management
        primary_bg = self.colors['primary']
        primary_hover_bg = self.colors['primary_dark']
        secondary_bg = self.colors['light']
        secondary_hover_bg = '#e2e6ea' # Slightly darker light gray

        # Scale padding based on UI scale
        padx = int(15 * self.ui_scale)
        pady = int(8 * self.ui_scale)

        btn = tk.Button(
            parent,
            text=btn_text,
            command=command,
            font=("Segoe UI", int(10 * self.font_scale), "bold" if is_primary else "normal"),
            bg=primary_bg if is_primary else secondary_bg,
            fg=self.colors['white'] if is_primary else self.colors['dark'],
            activebackground=primary_hover_bg if is_primary else secondary_hover_bg,
            activeforeground=self.colors['white'] if is_primary else self.colors['dark'],
            relief='flat',
            cursor='hand2',
            pady=pady,
            padx=padx,
            borderwidth=0
        )

        # Create more robust hover handlers with state checking
        def on_enter(event):
            if str(btn['state']) != 'disabled':
                btn.config(background=primary_hover_bg if is_primary else secondary_hover_bg)

        def on_leave(event):
            if str(btn['state']) != 'disabled':
                btn.config(background=primary_bg if is_primary else secondary_bg)

        # Add hover effect bindings
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)

        # Store original colors as attributes for state recovery
        btn.primary_bg = primary_bg
        btn.primary_hover_bg = primary_hover_bg
        btn.secondary_bg = secondary_bg
        btn.secondary_hover_bg = secondary_hover_bg
        btn.is_primary = is_primary

        return btn

    def _set_button_state(self, button, enabled=True):
        """Safely set button state while preserving hover effects."""
        if not hasattr(button, 'is_primary'): # Handle non-custom buttons if any
            button.config(state=tk.NORMAL if enabled else tk.DISABLED)
            return

        if enabled:
            button.config(state=tk.NORMAL)
            # Reset to normal background based on button type
            bg_color = button.primary_bg if button.is_primary else button.secondary_bg
            fg_color = self.colors['white'] if button.is_primary else self.colors['dark']
            button.config(background=bg_color, foreground=fg_color)
        else:
            button.config(state=tk.DISABLED)
            # Use consistent disabled colors
            button.config(background=self.colors['disabled'])
            button.config(foreground=self.colors['disabled_text'])

    def _create_suggestion_button(self, text):
        """Create a suggestion button with different styling."""
        btn = tk.Button(
            self.suggestions_buttons,
            text=text,
            font=("Segoe UI", int(9 * self.font_scale)),
            bg=self.colors['white'],
            fg=self.colors['dark'],
            relief='flat',
            bd=1, # Slight border for definition
            highlightbackground=self.colors['border'], # Border color
            highlightthickness=1,
            cursor='hand2',
            pady=int(5 * self.ui_scale),
            padx=int(10 * self.ui_scale),
            command=lambda: self._use_suggestion(text)
        )

        # Add hover effects with named functions
        def on_enter(e):
            if str(btn['state']) != 'disabled':
                 btn.config(background='#f0f0f0') # Slightly darker white

        def on_leave(e):
             if str(btn['state']) != 'disabled':
                 btn.config(background=self.colors['white'])

        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)

        return btn

    def _update_suggestions(self):
        """Update the suggestion buttons based on file type."""
        # Clear existing suggestions
        for widget in self.suggestions_buttons.winfo_children():
            widget.destroy()

        if not self.selected_file or not os.path.exists(self.selected_file):
            self.suggestions_label.pack_forget() # Hide label if no file
            return

        # Get contextual suggestions
        self.suggested_messages = self._get_contextual_suggestions()

        if self.suggested_messages:
             self.suggestions_label.pack(anchor='w', pady=(0, self.SMALL_PADDING)) # Show label
             # Create buttons for suggestions (limit to 4 for layout)
             for i, suggestion in enumerate(self.suggested_messages[:4]):
                 btn = self._create_suggestion_button(suggestion)
                 # Place buttons horizontally
                 btn.pack(side='left', padx=(0 if i == 0 else self.SMALL_PADDING), pady=(0, self.SMALL_PADDING))
        else:
             self.suggestions_label.pack_forget() # Hide if no suggestions

    def _get_contextual_suggestions(self):
        """Generate contextual suggestions based on file type and history."""
        if not self.selected_file:
            return []

        suggestions = []
        file_path = self.selected_file
        file_ext = os.path.splitext(file_path)[1].lower()
        filename = os.path.basename(file_path)

        # Get previous commit messages for this file
        past_messages = self._get_past_commit_messages(file_path)

        # First add any relevant past messages (limit to avoid clutter)
        if past_messages:
            suggestions.extend([msg for msg in past_messages[:2] if msg]) # Add non-empty messages

        # Image file suggestions
        if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp']:
            suggestions.extend([
                f"Update {filename}",
                "Image adjustments",
                "Optimize image quality",
                "Resize image"
            ])
        # Document suggestions
        elif file_ext in ['.txt', '.md', '.doc', '.docx', '.pdf', '.rtf']:
            suggestions.extend([
                "Update document content",
                "Fix typos and formatting",
                f"Revise {filename}",
                "Update documentation"
            ])
        # Code file suggestions
        elif file_ext in ['.py', '.js', '.java', '.cpp', '.cs', '.html', '.css', '.php', '.rb', '.go']:
            suggestions.extend([
                "Implement new feature",
                "Fix bug in code",
                "Code optimization",
                "Add documentation/comments",
                "Refactor for readability"
            ])
        # Default suggestions
        else:
            suggestions.extend([
                f"Update {filename}",
                "Minor changes",
                "Fix issues",
                "Routine update"
            ])

        # Remove duplicates while preserving order as much as possible
        unique_suggestions = []
        seen = set()
        for item in suggestions:
            if item and item not in seen: # Ensure item is not empty and not seen
                unique_suggestions.append(item)
                seen.add(item)

        return unique_suggestions

    def _get_backup_count(self, file_path):
        """Get actual backup count for a file from VersionManager."""
        try:
            # Use the method that counts *active* versions from metadata
            if hasattr(self.version_manager, 'get_active_file_versions'):
                 active_versions = self.version_manager.get_active_file_versions(file_path)
                 return len(active_versions)
            # Fallback if the specific method doesn't exist (less accurate)
            elif hasattr(self.version_manager, 'load_tracked_files'):
                 tracked_files = self.version_manager.load_tracked_files()
                 normalized_path = os.path.normpath(file_path)
                 if normalized_path in tracked_files:
                     versions = tracked_files[normalized_path].get("versions", {})
                     # Count versions not marked as deleted
                     return sum(1 for info in versions.values() if not info.get("deleted", False))
            return 0 # Default if unable to count
        except Exception as e:
            print(f"Error getting backup count: {e}")
            return 0

    def _get_past_commit_messages(self, file_path):
        """Get past commit messages for the file from VersionManager."""
        try:
            messages = []
            # Ensure we use the method that returns sorted versions if possible
            if hasattr(self.version_manager, 'get_active_file_versions'):
                 versions_data = self.version_manager.get_active_file_versions(file_path)
                 # Extract messages from sorted active versions (newest first)
                 messages = [info.get("commit_message") for _, info in versions_data if info.get("commit_message")]
            # Fallback to loading all tracked files
            elif hasattr(self.version_manager, 'load_tracked_files'):
                 tracked_files = self.version_manager.load_tracked_files()
                 normalized_path = os.path.normpath(file_path)
                 if normalized_path in tracked_files:
                     versions = tracked_files[normalized_path].get("versions", {})
                     # Sort by timestamp before extracting messages
                     sorted_versions = sorted(
                         versions.items(),
                         key=lambda x: datetime.strptime(x[1]["timestamp"], "%Y-%m-%d %H:%M:%S"),
                         reverse=True
                     )
                     messages = [info.get("commit_message") for _, info in sorted_versions if info.get("commit_message")]

            # Return unique messages, keeping recent ones first
            unique_messages = []
            seen = set()
            for msg in messages:
                if msg and msg not in seen:
                    unique_messages.append(msg)
                    seen.add(msg)
            return unique_messages
        except Exception as e:
            print(f"Error getting past commit messages: {e}")
            return []

    def _use_suggestion(self, text):
        """Use a suggestion as the commit message."""
        self.commit_message_entry.delete(0, tk.END)
        self.commit_message_entry.insert(0, text)
        self.commit_message_entry.focus_set() # Keep focus on entry

    def _suggest_messages(self, event=None):
        """Suggest messages based on current input (simple filter)."""
        current_text = self.commit_message_entry.get().lower().strip()
        if not current_text or len(current_text) < 2: # Require at least 2 chars to filter
            self._update_suggestions() # Show default suggestions if input is short
            return

        # Filter suggestions based on input (case-insensitive)
        filtered = []
        # Get full list of suggestions again to filter from
        all_suggestions = self._get_contextual_suggestions()
        for suggestion in all_suggestions:
            if current_text in suggestion.lower():
                 # Check if it's not exactly the same as current input
                 if suggestion.lower() != current_text:
                     filtered.append(suggestion)

        # Clear existing suggestion buttons
        for widget in self.suggestions_buttons.winfo_children():
            widget.destroy()

        # If we have filtered suggestions, update buttons
        if filtered:
            self.suggestions_label.pack(anchor='w', pady=(0, self.SMALL_PADDING)) # Ensure label is visible
            for i, suggestion in enumerate(filtered[:4]): # Limit displayed suggestions
                btn = self._create_suggestion_button(suggestion)
                btn.pack(side='left', padx=(0 if i == 0 else self.SMALL_PADDING), pady=(0, self.SMALL_PADDING))
        else:
             # If no filtered suggestions match, either show nothing or default ones
             # Option 1: Show nothing
             # self.suggestions_label.pack_forget()
             # Option 2: Revert to default suggestions if input is cleared etc.
              if not current_text:
                   self._update_suggestions()
              else:
                   self.suggestions_label.pack_forget() # Hide label if input exists but no matches

    def _select_file(self):
        """Open file dialog to select a file."""
        # Suggest starting directory based on current selection or user home
        initial_dir = os.path.dirname(self.selected_file) if self.selected_file else os.path.expanduser("~")

        file_path = filedialog.askopenfilename(
            title="Select File to Track",
            initialdir=initial_dir,
            filetypes=[
                ("All files", "*.*"),
                ("Text files", "*.txt;*.md"),
                ("Python files", "*.py"),
                ("Documents", "*.doc;*.docx;*.pdf;*.rtf"),
                ("Images", "*.jpg;*.jpeg;*.png;*.gif;*.svg;*.webp")
            ]
        )
        if file_path:
            # Disable UI elements during loading (briefly)
            if hasattr(self, 'select_btn') and self.select_btn.winfo_exists():
                self._set_button_state(self.select_btn, False)
            if hasattr(self, 'change_btn') and self.change_btn.winfo_exists():
                 self._set_button_state(self.change_btn, False)

            self.commit_message_entry.config(state=tk.DISABLED)
            self._set_button_state(self.commit_btn, False)
            self._set_button_state(self.reset_btn, False)

            # Update shared state - triggers _on_file_updated callback
            self.shared_state.set_selected_file(file_path)

            # Animation is handled within _on_file_updated now
        else:
             # If user cancelled selection, ensure state is cleared if needed
             if self.selected_file is None: # Only if no file was previously selected
                  self._on_file_updated(None) # Explicitly update UI to empty state


    def _animate_file_selected(self, file_path):
        """Show animation when a file is selected."""
        if self.animation_running:
            return

        self.animation_running = True
        filename = os.path.basename(file_path)

        # Create animation overlay (using Toplevel for simplicity)
        overlay = tk.Toplevel(self.parent)
        overlay.overrideredirect(True)
        overlay.attributes("-alpha", 0.9) # Semi-transparent
        overlay.attributes("-topmost", True) # Stay on top

        # Position at center of parent window
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()
        width = int(300 * self.ui_scale)
        height = int(150 * self.ui_scale)
        x = parent_x + (parent_width // 2) - (width // 2)
        y = parent_y + (parent_height // 2) - (height // 2)
        overlay.geometry(f"{width}x{height}+{x}+{y}")

        # Animation content
        anim_frame = tk.Frame(overlay, bg=self.colors['primary'], padx=int(20 * self.ui_scale), pady=int(15 * self.ui_scale))
        anim_frame.pack(fill='both', expand=True)

        icon = tk.Label(
            anim_frame,
            text="📄",
            font=("Segoe UI", int(40 * self.font_scale)),
            fg=self.colors['white'],
            bg=self.colors['primary']
        )
        icon.pack(pady=(self.SMALL_PADDING, 0))

        msg = tk.Label(
            anim_frame,
            text=f"File Selected",
            font=("Segoe UI", int(14 * self.font_scale), "bold"),
            fg=self.colors['white'],
            bg=self.colors['primary']
        )
        msg.pack()

        filename_label = tk.Label(
            anim_frame,
            text=filename,
            font=("Segoe UI", int(10 * self.font_scale)),
            fg=self.colors['white'],
            bg=self.colors['primary']
        )
        filename_label.pack(pady=(0, self.STANDARD_PADDING))

        # Animation sequence: close after short delay
        def close_animation():
            try:
                 if overlay.winfo_exists():
                     overlay.destroy()
            except tk.TclError:
                 pass # Ignore errors if window already destroyed
            self.animation_running = False

        # Show for a short time then close
        self.parent.after(600, close_animation) # Slightly longer duration

    def _on_file_changed(self, file_path: str, has_changes: bool) -> None:
        """Handle file change detection from the monitor."""
        if file_path == self.selected_file:
            self.has_changes = has_changes
            # Schedule UI update on main thread safely
            self.parent.after(0, self._update_ui_for_file_change)

    def _update_ui_for_file_change(self):
        """UI updates triggered by file change detection."""
        if not hasattr(self, 'status_bar') or not self.status_bar.winfo_exists():
             return # Prevent errors if UI not fully built or destroyed

        status_text = "Modified" if self.has_changes else "No changes"
        status_color = self.colors['danger'] if self.has_changes else self.colors['success']

        # Update status bar color
        self.status_bar.config(bg=status_color)

        # Update status indicator in header
        self.status_indicator.config(text=status_text, fg=status_color)

        # Update metadata display (which also reflects status)
        self._update_metadata_display()

    def _update_metadata_display(self):
        """Update the metadata display with file information."""
        if not hasattr(self, 'metadata_text') or not self.metadata_text.winfo_exists():
            return # Exit if UI elements aren't ready

        self.metadata_text.config(state=tk.NORMAL) # Enable writing
        self.metadata_text.delete(1.0, tk.END) # Clear existing text

        if not self.selected_file or not os.path.exists(self.selected_file):
            self._show_empty_metadata()
            self.metadata_text.config(state=tk.DISABLED) # Disable after writing
            return

        try:
            # Get metadata using version manager's method
            file_path = self.selected_file
            metadata = self.version_manager.get_file_metadata(file_path)
            if not metadata: # Handle case where metadata fetching fails
                 raise ValueError("Could not retrieve file metadata.")

            # Get the actual backup count (active versions)
            current_backups = self._get_backup_count(file_path)
            max_backups = self.settings.get('max_backups', 5) # Use setting

            category = self.type_handler.get_file_category(file_path)
            category_icon = self.type_handler.get_category_icon(category)

            # Determine change status based on monitor flag
            change_status = "Modified" if self.has_changes else "No changes"
            status_color = self.colors['danger'] if self.has_changes else self.colors['success']

            # Get current time in UTC (use utility function if available)
            try:
                 from utils.time_utils import get_formatted_time
                 current_time_utc = get_formatted_time(use_utc=True)
            except ImportError:
                 current_time_utc = datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S") # Fallback

            # --- Build Metadata Text ---
            info_text = ""

            # Header
            info_text += f"{category_icon} {os.path.basename(file_path)}\n\n"

            # Status section
            info_text += "File Status\n" # Section title
            info_text += f"├─ Status: {change_status}\n"
            info_text += f"├─ Type: {metadata.get('file_type', category.value)}\n" # Use metadata if available
            info_text += f"└─ Size: {format_size(metadata.get('size', 0))}\n\n" # Use metadata size

            # Times section
            info_text += "Time Information\n"
            mod_time = metadata.get('modification_time', {})
            info_text += f"├─ Modified (UTC): {mod_time.get('utc', 'N/A')}\n"
            info_text += f"├─ Modified (Local): {mod_time.get('local', 'N/A')}\n"
            info_text += f"└─ Current Time (UTC): {current_time_utc}\n\n"

            # Version control section
            info_text += "Version Control\n"
            info_text += f"├─ Active Backups: {current_backups}/{max_backups}\n"
            info_text += f"└─ Tracked by: {self.username}\n" # Use stored username

            # Insert text and apply styles
            self.metadata_text.insert(tk.END, info_text)
            self._apply_text_styles()

            # Update status bar color based on actual change status
            if hasattr(self, 'status_bar'):
                self.status_bar.config(bg=status_color)

        except Exception as e:
            print(f"Error updating metadata display: {e}")
            self._show_error_metadata(str(e)) # Display error in the text widget

        finally:
            self.metadata_text.config(state=tk.DISABLED) # Disable after writing


    def _show_empty_metadata(self):
        """Show empty state for metadata display."""
        empty_text = (
            "No file selected\n\n"
            "Please select a file using the 'Select File' or 'Change' button "
            "to view its information and commit changes."
        )
        # Assumes metadata_text is already enabled
        self.metadata_text.insert(tk.END, empty_text)
        # Apply a default style if needed
        self.metadata_text.tag_configure("empty", foreground=self.colors['secondary'], font=("Segoe UI", int(10 * self.font_scale)))
        self.metadata_text.tag_add("empty", "1.0", "end")

        # Gray status bar for empty state
        if hasattr(self, 'status_bar'):
            self.status_bar.config(bg=self.colors['secondary'])

        # Update status indicator
        if hasattr(self, 'status_indicator'):
             self.status_indicator.config(text="No file selected", fg=self.colors['secondary'])

    def _show_error_metadata(self, error_message):
        """Show error state for metadata display."""
        error_text = (
            "Error Retrieving File Information\n\n"
            f"Details: {error_message}\n\n"
            "Please check file permissions or if the file exists."
        )
        # Assumes metadata_text is already enabled
        self.metadata_text.insert(tk.END, error_text)
        # Apply error style
        self.metadata_text.tag_configure("error", foreground=self.colors['danger'], font=("Segoe UI", int(10 * self.font_scale), "bold"))
        self.metadata_text.tag_add("error", "1.0", "end")

        # Red status bar for error state
        if hasattr(self, 'status_bar'):
            self.status_bar.config(bg=self.colors['danger'])

        # Update status indicator
        if hasattr(self, 'status_indicator'):
             self.status_indicator.config(text="Error", fg=self.colors['danger'])

    def _apply_text_styles(self):
        """Apply text styles to metadata display."""
        # --- Define Tags ---
        self.metadata_text.tag_configure(
            "header",
            font=("Segoe UI", int(12 * self.font_scale), "bold"),
            foreground=self.colors['dark']
        )
        self.metadata_text.tag_configure(
            "section_title",
            font=("Segoe UI", int(11 * self.font_scale), "bold"),
            foreground=self.colors['secondary'],
            spacing1=5 # Add space before section titles
        )
        self.metadata_text.tag_configure(
            "status_modified",
            foreground=self.colors['danger'],
            font=("Segoe UI", int(10 * self.font_scale), "bold")
        )
        self.metadata_text.tag_configure(
            "status_ok",
            foreground=self.colors['success'],
            font=("Segoe UI", int(10 * self.font_scale), "bold")
        )
        self.metadata_text.tag_configure(
            "label", # For labels like 'Status:', 'Type:'
            foreground=self.colors['secondary']
        )

        # --- Apply Tags ---
        text_content = self.metadata_text.get("1.0", tk.END)
        lines = text_content.splitlines()

        # Apply header style to first line
        if lines:
            self.metadata_text.tag_add("header", "1.0", "1.end")

        # Apply styles line by line
        for i, line in enumerate(lines):
            line_num = i + 1
            start_index = f"{line_num}.0"
            end_index = f"{line_num}.end"

            # Section titles (heuristic: lines without ':', '├─', '└─' after the first line)
            if i > 0 and line.strip() and ":" not in line and not line.strip().startswith("├─") and not line.strip().startswith("└─"):
                self.metadata_text.tag_add("section_title", start_index, end_index)

            # Status line styling
            if line.strip().startswith("Status:"):
                 status_value_start = line.find(":") + 1
                 status_value_index = f"{line_num}.{status_value_start}"
                 self.metadata_text.tag_add("label", start_index, status_value_index) # Style "Status:"
                 if "Modified" in line:
                     self.metadata_text.tag_add("status_modified", status_value_index, end_index)
                 else:
                     self.metadata_text.tag_add("status_ok", status_value_index, end_index)

            # Style other labels (lines starting with box drawing chars)
            elif line.strip().startswith("├─") or line.strip().startswith("└─"):
                 label_end = line.find(":") + 1
                 if label_end > 0:
                      label_end_index = f"{line_num}.{label_end}"
                      # Apply label style up to the colon
                      self.metadata_text.tag_add("label", f"{line_num}.{line.find('─')+1}", label_end_index)


    # get_file_metadata was removed as it's now handled by VersionManager


    def _reset_form(self):
        """Reset the commit form."""
        self.commit_message_entry.delete(0, tk.END)
        self._update_suggestions() # Refresh suggestions

    def _commit_file_action(self, event=None):
        """Handle the commit action: validate, show progress, start background thread."""
        if not self.selected_file or not os.path.exists(self.selected_file):
            self._show_feedback("No valid file selected!", success=False)
            return

        commit_message = self.commit_message_entry.get().strip()
        if not commit_message:
            # Optionally, generate a default message instead of showing error
            # commit_message = f"Update {os.path.basename(self.selected_file)}"
            # self.commit_message_entry.insert(0, commit_message)
            self._show_feedback("Please enter a commit message!", success=False)
            return

        # Show progress UI and disable commit button
        self._show_progress_indicator("Committing changes...")
        self._set_button_state(self.commit_btn, False)
        self._set_button_state(self.reset_btn, False)
        self.commit_message_entry.config(state=tk.DISABLED)

        # Use threading to prevent UI freeze
        threading.Thread(target=self._perform_commit, args=(commit_message,), daemon=True).start()

    def _perform_commit(self, commit_message):
        """
        Perform the actual commit operation in background thread.
        Includes backup creation, version metadata update, and old backup deletion.
        """
        try:
            # --- 1. Check for Changes ---
            # Use VersionManager's method to check changes reliably
            tracked_files = self.version_manager.load_tracked_files()
            has_changed, current_hash, last_hash = self.version_manager.has_file_changed(
                self.selected_file,
                tracked_files
            )

            if not has_changed:
                # Ask for confirmation on main thread using messagebox
                # We need to pass necessary data to the confirmation handler
                self.parent.after(0, lambda: self._confirm_commit_no_changes(commit_message, current_hash, last_hash))
                # Don't proceed further in this thread yet
                return

            # --- If changed, proceed directly ---
            self._execute_commit_steps(commit_message, current_hash)

        except Exception as e:
            # Show error on main thread
            error_msg = str(e)
            print(f"Commit failed in _perform_commit: {error_msg}") # Log detailed error
            # Schedule feedback and UI reset on main thread
            self.parent.after(0, lambda error=error_msg: self._handle_commit_failure(error))

    def _confirm_commit_no_changes(self, commit_message, current_hash, last_hash):
        """Ask user confirmation on the main thread if no changes detected."""
        response = messagebox.askyesno(
            "No Changes Detected",
            "The file content appears unchanged since the last backup.\n\n"
            "Do you want to create a backup anyway (e.g., to update commit message or timestamp)?",
            parent=self.parent # Ensure messagebox is modal to the app
        )
        if response:
            # If user confirms, proceed with commit steps in a new thread or reuse existing logic
            # For simplicity, start a new thread for the execution part
            self._show_progress_indicator("Committing unchanged file...") # Update progress message
            threading.Thread(target=self._execute_commit_steps, args=(commit_message, current_hash), daemon=True).start()
        else:
            # User cancelled, hide progress and re-enable UI
            self._hide_progress_indicator()
            self._reset_commit_ui_state(success=False) # Re-enable buttons/entry


    def _execute_commit_steps(self, commit_message, current_hash):
        """Contains the core steps of backup, metadata update, and cleanup."""
        try:
            # --- 2. Create Physical Backup ---
            # BackupManager.create_backup now ONLY creates the file
            backup_path = self.backup_manager.create_backup(
                self.selected_file,
                file_hash=current_hash # Pass hash
            )

            if not backup_path:
                 raise RuntimeError("Backup file creation failed.") # Raise error to be caught

            # --- 3. Add Version Metadata & Get Hashes to Delete ---
            # Get metadata using VersionManager's method
            metadata = self.version_manager.get_file_metadata(self.selected_file)
            if not metadata:
                 raise RuntimeError("Failed to retrieve file metadata for commit.")

            # Call VersionManager.add_version (which now returns hashes_to_delete)
            hashes_to_delete = self.version_manager.add_version(
                self.selected_file,
                current_hash,
                metadata,
                commit_message
            )
            # add_version now handles saving tracked_files.json

            # --- 4. Delete Old Physical Backup Files ---
            if hashes_to_delete:
                self.backup_manager.delete_backup_files(
                    self.selected_file,
                    hashes_to_delete
                )

            # --- 5. Commit Successful: Schedule UI updates on main thread ---
            self.parent.after(0, self._handle_commit_success)

        except Exception as e:
            # Show error on main thread
            error_msg = str(e)
            print(f"Commit failed in _execute_commit_steps: {error_msg}")
            self.parent.after(0, lambda error=error_msg: self._handle_commit_failure(error))


    def _handle_commit_success(self):
        """UI updates to perform on the main thread after successful commit."""
        self._hide_progress_indicator()
        self._animate_commit_success() # Show success animation
        self._reset_commit_ui_state(success=True) # Reset entry, re-enable buttons
        self.shared_state.notify_version_change() # Notify other components (like HistoryPage)
        if self.shared_state.file_monitor:
            self.shared_state.file_monitor.refresh_tracked_files() # Update monitor's view
        self._update_metadata_display() # Refresh metadata view
        self._update_suggestions() # Refresh suggestions

    def _handle_commit_failure(self, error_message):
        """UI updates for commit failure on the main thread."""
        self._hide_progress_indicator()
        self._show_feedback(f"Commit failed: {error_message}", success=False)
        self._reset_commit_ui_state(success=False) # Re-enable buttons/entry without clearing

    def _reset_commit_ui_state(self, success: bool):
        """Resets buttons and entry field state after commit attempt."""
        if success:
             self.commit_message_entry.delete(0, tk.END) # Clear message on success

        # Re-enable UI elements if the file still exists
        if self.selected_file and os.path.exists(self.selected_file):
             self.commit_message_entry.config(state=tk.NORMAL)
             self._set_button_state(self.commit_btn, True)
             self._set_button_state(self.reset_btn, True)
        else:
             # If file somehow disappeared, keep them disabled
             self.commit_message_entry.config(state=tk.DISABLED)
             self._set_button_state(self.commit_btn, False)
             self._set_button_state(self.reset_btn, False)


    def _show_progress_indicator(self, message):
        """Show progress indicator overlay with message."""
        # Ensure it runs on the main thread if called from background
        if threading.current_thread() != threading.main_thread():
            self.parent.after(0, lambda msg=message: self._show_progress_indicator(msg))
            return

        if not hasattr(self, 'progress_overlay') or not self.progress_overlay.winfo_exists():
            # Create progress overlay frame
            self.progress_overlay = tk.Frame(
                self.frame, # Place it within the main commit page frame
                bg=self.colors['white'],
                bd=1,
                relief='solid',
                highlightbackground=self.colors['border'],
                highlightthickness=1
            )

            # Position it centered using place
            self.progress_overlay.place(
                relx=0.5, rely=0.5, # Center relative to the frame
                anchor='center',    # Anchor point is the center of the overlay
                width=int(300 * self.ui_scale),
                height=int(120 * self.ui_scale)
            )

            # Add spinner (simple text animation)
            self.progress_label = tk.Label(
                self.progress_overlay,
                text="⟳", # Initial spinner state
                font=("Segoe UI", int(24 * self.font_scale)),
                fg=self.colors['primary'],
                bg=self.colors['white']
            )
            self.progress_label.pack(pady=(int(15 * self.ui_scale), int(5 * self.ui_scale)))

            # Add message label
            self.progress_message = tk.Label(
                self.progress_overlay,
                text=message,
                font=("Segoe UI", int(11 * self.font_scale)),
                fg=self.colors['dark'],
                bg=self.colors['white']
            )
            self.progress_message.pack(pady=(0, int(15 * self.ui_scale)))

            # Start animation loop
            self._animate_spinner()
        else:
            # If overlay exists, just update message and lift it to top
            self.progress_message.config(text=message)
            self.progress_overlay.lift()


    def _animate_spinner(self):
        """Animate the spinner in the progress indicator."""
        if hasattr(self, 'progress_label') and self.progress_label.winfo_exists():
            spinner_chars = "⟳⟲◐◓◑◒" # More spinner options
            current_index = spinner_chars.find(self.progress_label.cget("text"))
            next_index = (current_index + 1) % len(spinner_chars)
            self.progress_label.config(text=spinner_chars[next_index])

            # Continue animation only if progress overlay still exists
            if hasattr(self, 'progress_overlay') and self.progress_overlay.winfo_exists():
                self._spinner_animation_job = self.parent.after(150, self._animate_spinner) # Speed up animation slightly
            else:
                 self._spinner_animation_job = None
        else:
             self._spinner_animation_job = None


    def _hide_progress_indicator(self):
        """Hide the progress indicator overlay."""
        # Ensure it runs on the main thread
        if threading.current_thread() != threading.main_thread():
            self.parent.after(0, self._hide_progress_indicator)
            return

        # Cancel pending animation job
        if hasattr(self, '_spinner_animation_job') and self._spinner_animation_job:
            self.parent.after_cancel(self._spinner_animation_job)
            self._spinner_animation_job = None

        if hasattr(self, 'progress_overlay') and self.progress_overlay.winfo_exists():
            self.progress_overlay.destroy()
            # Remove attribute to allow recreation
            delattr(self, 'progress_overlay')
            if hasattr(self, 'progress_label'): delattr(self, 'progress_label')
            if hasattr(self, 'progress_message'): delattr(self, 'progress_message')


    def _animate_commit_success(self):
        """Show animation for successful commit."""
         # Ensure it runs on the main thread
        if threading.current_thread() != threading.main_thread():
            self.parent.after(0, self._animate_commit_success)
            return

        # Create success overlay (similar to progress)
        success_overlay = tk.Frame(
            self.frame,
            bg=self.colors['success'],
            bd=1, relief='solid', highlightbackground=self.colors['success'] # Use success color for border too
        )
        success_overlay.place(
            relx=0.5, rely=0.5, anchor='center',
            width=int(300 * self.ui_scale), height=int(150 * self.ui_scale)
        )
        success_overlay.lift() # Bring to front

        # Add check mark
        check = tk.Label(
            success_overlay,
            text="✓",
            font=("Segoe UI", int(50 * self.font_scale), "bold"),
            fg=self.colors['white'],
            bg=self.colors['success']
        )
        check.pack(pady=(int(15 * self.ui_scale), int(5 * self.ui_scale)))

        # Add success message
        message = tk.Label(
            success_overlay,
            text="Changes Saved Successfully!",
            font=("Segoe UI", int(12 * self.font_scale), "bold"),
            fg=self.colors['white'],
            bg=self.colors['success']
        )
        message.pack(pady=(0, int(15 * self.ui_scale)))

        # Auto-hide after 1.2 seconds
        self.parent.after(1200, lambda: success_overlay.destroy() if success_overlay.winfo_exists() else None)


    def _show_feedback(self, message, success=True):
        """Show temporary feedback message in the header area."""
         # Ensure it runs on the main thread
        if threading.current_thread() != threading.main_thread():
            self.parent.after(0, lambda msg=message, suc=success: self._show_feedback(msg, suc))
            return

        # Cancel previous timer if exists
        if self._hide_feedback_timer:
            self.parent.after_cancel(self._hide_feedback_timer)
            self._hide_feedback_timer = None
        if hasattr(self, 'feedback_frame') and self.feedback_frame.winfo_exists():
            self.feedback_frame.destroy() # Remove old one immediately

        # Configure look based on success/failure
        bg_color = self.colors['success'] if success else self.colors['danger']
        fg_color = self.colors['white']

        # Create feedback frame next to status indicator
        self.feedback_frame = tk.Frame(
            self.header_frame, # Place inside header
            bg=bg_color,
            # bd=1, relief='solid', # Optional border
            # highlightbackground=bg_color
        )
        # Pack it to the right, before the status indicator if needed, or just right
        self.feedback_frame.pack(side='right', padx=(self.SMALL_PADDING, self.STANDARD_PADDING), pady=self.STANDARD_PADDING // 2)
        self.header_frame.update_idletasks() # Ensure packing takes effect

        self.feedback_label = tk.Label(
            self.feedback_frame,
            text=message,
            font=("Segoe UI", int(9 * self.font_scale), "bold"),
            fg=fg_color,
            bg=bg_color,
            padx=int(10 * self.ui_scale),
            pady=int(5 * self.ui_scale)
        )
        self.feedback_label.pack(fill='both', expand=True)

        # Auto-hide after 3 seconds
        self._hide_feedback_timer = self.parent.after(3000, self._hide_feedback)


    def _hide_feedback(self):
        """Hide the feedback message."""
         # Ensure it runs on the main thread
        if threading.current_thread() != threading.main_thread():
            self.parent.after(0, self._hide_feedback)
            return

        if hasattr(self, 'feedback_frame') and self.feedback_frame.winfo_exists():
            self.feedback_frame.destroy()
            # Delete attribute to allow recreation
            delattr(self, 'feedback_frame')
            if hasattr(self, 'feedback_label'): delattr(self, 'feedback_label')
        self._hide_feedback_timer = None


    def _on_file_updated(self, file_path):
        """Update UI when file selection changes via shared state."""
        self.selected_file = file_path
        self.has_changes = False # Reset change status on new file selection

        # Animate file selection
        if file_path and os.path.exists(file_path):
             self._animate_file_selected(file_path)

        # Schedule UI updates on main thread
        self.parent.after(0, self._update_ui_for_file_selection)


    def _update_ui_for_file_selection(self):
         """Updates UI elements based on the current self.selected_file."""
         if not hasattr(self, 'frame') or not self.frame.winfo_exists():
              return # Exit if frame is destroyed

         if self.selected_file and os.path.exists(self.selected_file):
            normalized_path = os.path.normpath(self.selected_file)

            # Ensure file monitor is tracking the correct file
            if self.shared_state.file_monitor:
                self.shared_state.file_monitor.set_file(normalized_path) # set_file should handle adding/switching
                # Immediately check for changes after setting
                self.has_changes = self.shared_state.file_monitor.check_for_changes()
                self._update_ui_for_file_change() # Update status based on initial check

            # Enable UI elements
            self.commit_message_entry.config(state=tk.NORMAL)
            self._set_button_state(self.commit_btn, True)
            self._set_button_state(self.reset_btn, True)

            # Update file display section
            self._show_file_info()

         else:
            # No valid file selected
            if self.shared_state.file_monitor:
                self.shared_state.file_monitor.set_file(None) # Stop monitoring

            # Disable UI elements
            self.commit_message_entry.delete(0, tk.END) # Clear message entry
            self.commit_message_entry.config(state=tk.DISABLED)
            self._set_button_state(self.commit_btn, False)
            self._set_button_state(self.reset_btn, False)

            # Show file selector instead of file display
            self._show_file_selector()

         # Update metadata display (will show empty state if no file)
         self._update_metadata_display()
         # Update suggestions (will clear if no file)
         self._update_suggestions()


    def refresh_layout(self):
        """Refresh layout on window resize or other events."""
        # Update any size-dependent elements
        if hasattr(self, 'frame') and self.frame.winfo_exists():
            self.frame.update_idletasks()

            # Get current width
            width = self.frame.winfo_width()

            # Check if we need to change layout (example thresholds)
            new_layout = "wide"
            if width < 600:
                new_layout = "narrow"
            elif width < 900:
                new_layout = "medium"

            # Only update if layout changed
            if new_layout != self.current_layout:
                self.current_layout = new_layout
                self._apply_responsive_layout(new_layout)


    def _apply_responsive_layout(self, layout_type):
        """Apply responsive layout based on width (example: adjust text width)."""
        # Adjust metadata text width based on layout
        if hasattr(self, 'metadata_text') and self.metadata_text.winfo_exists():
            if layout_type == "narrow":
                self.metadata_text.config(width=40) # Example width for narrow
            elif layout_type == "medium":
                self.metadata_text.config(width=60) # Example width for medium
            else: # Wide
                self.metadata_text.config(width=80) # Example width for wide


    def _on_frame_configure(self, event=None):
        """Handle frame resize with debounce."""
        # Debounce resize events
        if self.resize_timer:
            self.parent.after_cancel(self.resize_timer)

        # Schedule layout refresh after resize stops (e.g., 150ms delay)
        self.resize_timer = self.parent.after(150, self.refresh_layout)


    def _cleanup(self):
        """Clean up resources when frame is destroyed."""
        print("Cleaning up CommitPage...")
        # Remove callbacks from shared state
        try:
            # Use specific remove methods if they exist
            if hasattr(self.shared_state, 'remove_file_callback'):
                 self.shared_state.remove_file_callback(self._on_file_updated)
            if hasattr(self.shared_state, 'remove_monitoring_callback'):
                 self.shared_state.remove_monitoring_callback(self._on_file_changed)
            # Fallback if generic remove_callback exists
            elif hasattr(self.shared_state, 'remove_callback'):
                self.shared_state.remove_callback(self._on_file_updated)
                self.shared_state.remove_callback(self._on_file_changed)
        except Exception as e:
            print(f"Error during CommitPage callback cleanup: {e}")

        # Cancel any pending timers
        if hasattr(self, '_hide_feedback_timer') and self._hide_feedback_timer:
            try:
                self.parent.after_cancel(self._hide_feedback_timer)
            except: pass # Ignore errors if timer already cancelled
        if hasattr(self, 'resize_timer') and self.resize_timer:
            try:
                self.parent.after_cancel(self.resize_timer)
            except: pass
        if hasattr(self, '_spinner_animation_job') and self._spinner_animation_job:
             try:
                  self.parent.after_cancel(self._spinner_animation_job)
             except: pass
