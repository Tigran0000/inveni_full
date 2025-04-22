# ui/pages/restore_page.py - Enhanced with responsive design and corrected status logic

import os
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime, timedelta # Import timedelta for filtering
import pytz
import threading
import time

# Updated imports for new project structure
from utils.file_utils import format_size, calculate_file_hash
from utils.time_utils import format_timestamp_dual, get_formatted_time, get_current_username # Added get_current_username

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
        # Ensure widget exists before scheduling
        if self.widget.winfo_exists():
            self.scheduled = self.widget.after(600, self.show_tooltip)

    def cancel_schedule(self):
        """Cancel the scheduled tooltip appearance."""
        if self.scheduled:
             # Ensure widget exists before cancelling
            if self.widget.winfo_exists():
                 try:
                      self.widget.after_cancel(self.scheduled)
                 except ValueError: # Timer might already be cancelled
                      pass
            self.scheduled = None

    def show_tooltip(self, event=None):
        """Show tooltip window."""
        self.hide_tooltip()  # Ensure any existing tooltip is removed

        # Check if widget still exists
        if not self.widget.winfo_exists():
            return

        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        # Create tooltip window
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x-100}+{y}") # Adjust position if needed

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
            try:
                 if self.tooltip.winfo_exists():
                      self.tooltip.destroy()
            except tk.TclError:
                 pass # Ignore if already destroyed
            self.tooltip = None

class RestorePage:
    """UI for restoring previous file versions with responsive design."""

    def __init__(self, parent, version_manager, backup_manager, settings_manager, shared_state, colors=None, ui_scale=1.0, font_scale=1.0):
        """
        Initialize restore page with necessary services and responsive design.

        Args:
            parent: Parent tkinter container
            version_manager: Service for version management
            backup_manager: Service for backup operations
            settings_manager: Service for settings management
            shared_state: Shared application state
            colors: Color palette (optional)
            ui_scale: UI scaling factor (optional)
            font_scale: Font scaling factor (optional)
        """
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
                'highlight': "#bbdefb",      # Highlight/selection color
                'deleted_fg': "#757575",    # Specific color for deleted items text
                'separator_fg': "#bdbdbd"   # Color for separator line
            }

        # Initialize state
        self.selected_file = shared_state.get_selected_file()
        self.backup_folder = self.settings.get("backup_folder", "backups")
        try:
            self.username = get_current_username() # Use utility function
        except NameError: # Fallback if function not imported/available
            self.username = os.getlogin()
        self.current_time = get_formatted_time(use_utc=True)
        self.tooltip_window = None
        self.loading = False
        self.versions_data = [] # Store the raw data: [(hash, info), ...]
        self.resize_timer = None
        self.selected_version_hash = None # Store the full hash of the selected item

        # Create UI components
        self._create_ui()

        # Register callbacks
        self.shared_state.add_file_callback(self._on_file_updated)
        self.shared_state.add_version_callback(self._refresh_version_list) # Refresh when commit happens

        # Initial refresh
        self._refresh_version_list()

    def _create_ui(self):
        """Create the user interface with responsive grid layout."""
        # Create main frame with grid
        self.frame = ttk.Frame(self.parent)
        self.frame.grid(row=0, column=0, sticky='nsew')
        # Configure parent grid to allow frame expansion
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)

        # Make frame responsive
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(0, weight=0)  # Header - fixed height
        self.frame.grid_rowconfigure(1, weight=0)  # Metadata - fixed height
        self.frame.grid_rowconfigure(2, weight=1)  # Version history - flexible
        self.frame.grid_rowconfigure(3, weight=0)  # Actions - fixed height

        # Create content sections with card design
        self._create_header_section()
        self._create_metadata_section()
        self._create_version_history_section()
        self._create_action_section()

        # Register for resize events with debounce
        self.frame.bind('<Configure>', self._on_frame_configure)

        # Bind cleanup
        self.frame.bind('<Destroy>', lambda e: self._cleanup())

    def _create_header_section(self):
        """Create responsive header section with title and controls."""
        self.header_frame = self._create_card_container(
            self.frame,
            row=0,
            column=0,
            sticky='ew',
            padx=self.STANDARD_PADDING,
            pady=(self.STANDARD_PADDING, self.SMALL_PADDING)
        )

        # Header content with grid layout
        self.header_frame.grid_columnconfigure(1, weight=1) # Allow filter frame to stick right

        # Page title
        self.title_label = tk.Label(
            self.header_frame,
            text="Restore Version",
            font=("Segoe UI", int(18 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card']
        )
        self.title_label.grid(row=0, column=0, sticky='w', padx=self.STANDARD_PADDING, pady=self.STANDARD_PADDING)

        # Search and filter controls
        self.filter_frame = tk.Frame(self.header_frame, bg=self.colors['card'])
        self.filter_frame.grid(row=0, column=1, sticky='e', padx=self.STANDARD_PADDING, pady=self.STANDARD_PADDING)

        # Search entry
        self.search_var = tk.StringVar()
        self.search_frame = tk.Frame(
            self.filter_frame,
            bg=self.colors['white'],
            highlightbackground=self.colors['border'],
            highlightthickness=1,
            bd=0
        )
        self.search_frame.pack(side='left', padx=(0, self.STANDARD_PADDING))

        self.search_entry = tk.Entry(
            self.search_frame,
            textvariable=self.search_var,
            font=("Segoe UI", int(10 * self.font_scale)),
            width=20,
            bd=0,
            relief='flat',
            bg=self.colors['white']
        )
        self.search_entry.pack(side='left', padx=self.STANDARD_PADDING, pady=6)
        self.search_entry.bind("<KeyRelease>", self._filter_versions)

        # Search icon/button
        search_btn = tk.Button(
            self.search_frame,
            text="🔍",
            font=("Segoe UI", int(10 * self.font_scale)),
            bg=self.colors['white'],
            fg=self.colors['secondary'],
            bd=0,
            relief='flat',
            command=self._filter_versions # Trigger filter on button click too
        )
        search_btn.pack(side='right', padx=(0, 5))

        # Add placeholder text logic
        self.search_entry.insert(0, "Search versions...")
        self.search_entry.config(fg=self.colors['secondary'])

        def on_focus_in(e):
            if self.search_entry.get() == "Search versions...":
                self.search_entry.delete(0, 'end')
                self.search_entry.config(fg=self.colors['dark'])

        def on_focus_out(e):
            if self.search_entry.get() == '':
                self.search_entry.insert(0, "Search versions...")
                self.search_entry.config(fg=self.colors['secondary'])

        self.search_entry.bind('<FocusIn>', on_focus_in)
        self.search_entry.bind('<FocusOut>', on_focus_out)

        # Filter dropdown
        self.filter_var = tk.StringVar(value="All Versions")
        self.filter_menu = ttk.Combobox(
            self.filter_frame,
            textvariable=self.filter_var,
            font=("Segoe UI", int(10 * self.font_scale)),
            state="readonly",
            width=15,
            values=["All Versions", "Available Only", "Deleted Only", "Last 7 Days", "My Versions"] # Added Deleted Only
        )
        self.filter_menu.pack(side='left')
        self.filter_menu.bind("<<ComboboxSelected>>", self._filter_versions)

        # Add tooltip
        ToolTip(self.filter_menu, "Filter version history by availability or time")

    def _create_metadata_section(self):
        """Create responsive file metadata section with card design."""
        self.metadata_card = self._create_card_container(
            self.frame,
            row=1,
            column=0,
            sticky='ew',
            padx=self.STANDARD_PADDING,
            pady=self.SMALL_PADDING
        )

        # Section title
        self.metadata_title = tk.Label(
            self.metadata_card,
            text="Current File",
            font=("Segoe UI", int(12 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card']
        )
        self.metadata_title.pack(anchor='w', padx=self.STANDARD_PADDING, pady=(self.STANDARD_PADDING, self.SMALL_PADDING))

        # Separator
        separator = ttk.Separator(self.metadata_card, orient='horizontal')
        separator.pack(fill='x', padx=self.STANDARD_PADDING, pady=(0, self.SMALL_PADDING))

        # File info container
        self.file_info = tk.Frame(self.metadata_card, bg=self.colors['card'])
        self.file_info.pack(fill='x', expand=True, padx=self.STANDARD_PADDING, pady=(0, self.STANDARD_PADDING))

        # File info content with grid layout for responsive alignment
        self.file_info.grid_columnconfigure(1, weight=1) # Allow labels to expand

        # File icon
        self.file_icon_label = tk.Label(
            self.file_info,
            text="📄",
            font=("Segoe UI", int(32 * self.font_scale)),
            bg=self.colors['card'],
            fg=self.colors['secondary']
        )
        self.file_icon_label.grid(row=0, column=0, rowspan=3, padx=(0, self.STANDARD_PADDING), pady=self.SMALL_PADDING) # Span 3 rows

        # File name with larger font
        self.file_name_label = tk.Label(
            self.file_info,
            text="No file selected",
            font=("Segoe UI", int(14 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card'],
            anchor='w'
        )
        self.file_name_label.grid(row=0, column=1, sticky='w')

        # File details with better formatting
        self.file_details_label = tk.Label(
            self.file_info,
            text="Select a file to see its details",
            font=("Segoe UI", int(9 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['card'],
            justify=tk.LEFT,
            anchor='w'
        )
        self.file_details_label.grid(row=1, column=1, sticky='w', pady=(self.SMALL_PADDING, 0))

        # Status indicator (small colored bar)
        self.status_indicator_frame = tk.Frame(self.file_info, bg=self.colors['card'])
        self.status_indicator_frame.grid(row=2, column=1, sticky='w', pady=(self.SMALL_PADDING, 0))

        self.status_indicator = tk.Frame(
            self.status_indicator_frame,
            bg=self.colors['secondary'],  # Default neutral color
            width=int(80 * self.ui_scale),
            height=int(5 * self.ui_scale)
        )
        self.status_indicator.pack(side='left') # Pack inside its frame

        self.status_label = tk.Label(
            self.status_indicator_frame,
            text="Unknown",
            font=("Segoe UI", int(9 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['card']
        )
        self.status_label.pack(side='left', padx=(self.SMALL_PADDING, 0))


    def _create_version_history_section(self):
        """Create responsive version history section with card design."""
        self.version_card = self._create_card_container(
            self.frame,
            row=2, # Adjusted row index
            column=0,
            sticky='nsew',
            padx=self.STANDARD_PADDING,
            pady=self.SMALL_PADDING
        )
        self.version_card.grid_rowconfigure(2, weight=1) # Allow tree container to expand

        # Section title
        self.version_title = tk.Label(
            self.version_card,
            text="Version History",
            font=("Segoe UI", int(12 * self.font_scale), "bold"),
            fg=self.colors['dark'],
            bg=self.colors['card']
        )
        self.version_title.grid(row=0, column=0, sticky='w', padx=self.STANDARD_PADDING, pady=(self.STANDARD_PADDING, self.SMALL_PADDING))

        # Separator
        separator = ttk.Separator(self.version_card, orient='horizontal')
        separator.grid(row=1, column=0, sticky='ew', padx=self.STANDARD_PADDING, pady=(0, self.SMALL_PADDING))

        # Status bar at top of tree area (using grid)
        self.status_bar = tk.Frame(
            self.version_card,
            bg=self.colors['card'],
            bd=0
        )
        self.status_bar.grid(row=2, column=0, sticky='ew', padx=self.STANDARD_PADDING, pady=(0, self.SMALL_PADDING))
        self.status_bar.grid_columnconfigure(0, weight=1) # Allow label to expand

        # Left side: version count
        self.version_count_label = tk.Label(
            self.status_bar,
            text="No versions available",
            font=("Segoe UI", int(10 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['card']
        )
        self.version_count_label.grid(row=0, column=0, sticky='w')

        # Right side: refresh button (compact style)
        self.refresh_btn = self._create_button(
            self.status_bar,
            "Refresh",
            self._refresh_version_list,
            is_primary=False,
            icon="🔄",
            compact=True # Use compact style
        )
        self.refresh_btn.grid(row=0, column=1, sticky='e')

        # Tree view container using grid
        self.tree_container = tk.Frame(
            self.version_card,
            bg=self.colors['white'],
            bd=1,
            relief='solid',
            highlightbackground=self.colors['border'],
            highlightthickness=1
        )
        self.tree_container.grid(row=3, column=0, sticky='nsew', padx=self.STANDARD_PADDING, pady=(0, self.STANDARD_PADDING))
        self.version_card.grid_rowconfigure(3, weight=1) # Allow tree container to expand vertically

        # Make tree container responsive
        self.tree_container.grid_columnconfigure(0, weight=1)
        self.tree_container.grid_rowconfigure(0, weight=1)

        # Columns for our tree (Match the formatting functions)
        self.columns = (
            "Local Time", # From format_timestamp_dual
            "Message",    # From commit_message
            "User",       # From username
            "Size",       # From format_size
            "Hash",       # Shortened hash
            "Status"      # Derived status: Available, Missing, Deleted+Available, Deleted+Unavailable
        )

        # Create scrollbars
        y_scrollbar = ttk.Scrollbar(self.tree_container)
        y_scrollbar.grid(row=0, column=1, sticky='ns')

        x_scrollbar = ttk.Scrollbar(self.tree_container, orient='horizontal')
        x_scrollbar.grid(row=1, column=0, sticky='ew')

        # --- Configure Treeview Style ---
        style = ttk.Style()
        # Ensure theme is available, fallback if needed
        try:
             current_theme = style.theme_use()
        except tk.TclError:
             current_theme = "default" # Or 'clam', 'alt', etc.

        style_name = "ModernTree.Treeview"
        heading_style_name = f"{style_name}.Heading"

        style.configure(
            style_name,
            background=self.colors['white'],
            foreground=self.colors['dark'],
            rowheight=int(30 * self.ui_scale),
            fieldbackground=self.colors['white'],
            borderwidth=0,
            font=("Segoe UI", int(9 * self.font_scale))
        )

        style.configure(
            heading_style_name,
            background=self.colors['light'],
            foreground=self.colors['secondary'],
            font=("Segoe UI", int(9 * self.font_scale), "bold"),
            relief='flat',
            padding=5
        )

        # Selection colors
        style.map(style_name,
            background=[('selected', self.colors['primary'])],
            foreground=[('selected', self.colors['white'])]
        )
        # --- End Style Configuration ---


        # Create tree view
        self.version_tree = ttk.Treeview(
            self.tree_container,
            columns=self.columns,
            show='headings',
            style=style_name,
            selectmode='browse',
            yscrollcommand=y_scrollbar.set,
            xscrollcommand=x_scrollbar.set
        )
        self.version_tree.grid(row=0, column=0, sticky='nsew')

        # Configure scrollbars
        y_scrollbar.config(command=self.version_tree.yview)
        x_scrollbar.config(command=self.version_tree.xview)

        # Configure columns headers and initial widths
        column_widths = {
            "Local Time": int(150 * self.ui_scale),
            "Message": int(200 * self.ui_scale),
            "User": int(100 * self.ui_scale),
            "Size": int(80 * self.ui_scale),
            "Hash": int(120 * self.ui_scale),
            "Status": int(100 * self.ui_scale)
        }

        for col, width in column_widths.items():
            self.version_tree.heading(col, text=col, anchor='w')
            self.version_tree.column(col, width=width, minwidth=int(width * 0.8), anchor='w') # Allow some shrinking

        # Configure tags for available/unavailable versions
        self.version_tree.tag_configure('available', foreground=self.colors['success']) # Green for available
        self.version_tree.tag_configure('unavailable', foreground=self.colors['danger']) # Red for unavailable/missing backup
        self.version_tree.tag_configure('deleted', foreground=self.colors['deleted_fg']) # Gray for deleted metadata
        self.version_tree.tag_configure('deleted_unavailable', foreground=self.colors['disabled_text'], font=("Segoe UI", int(9*self.font_scale), "italic")) # Italic gray for deleted+unavailable
        self.version_tree.tag_configure('missing', foreground=self.colors['danger'], font=("Segoe UI", int(9*self.font_scale), "bold")) # Bold Red for missing active backup

        # Alternating row colors (Optional, can be distracting)
        # self.version_tree.tag_configure('even_row', background='#f8f9fa')
        # self.version_tree.tag_configure('odd_row', background=self.colors['white'])

        # Tag for the summary row
        self.version_tree.tag_configure('info', foreground=self.colors['info'], background='#f0f7ff')

        # Bind events
        self.version_tree.bind('<<TreeviewSelect>>', self._on_version_selected)
        self.version_tree.bind('<Double-1>', self._on_version_double_click)

        # Empty state message (placed via place)
        self.empty_message = tk.Label(
            self.tree_container,
            text="No versions available for this file",
            font=("Segoe UI", int(11 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['white']
        )
        # Will be shown/hidden in loading/populating functions

        # Loading indicator (placed via place)
        self.loading_frame = tk.Frame(self.tree_container, bg=self.colors['white'])
        self.loading_label = tk.Label(
            self.loading_frame,
            text="⟳",
            font=("Segoe UI", int(24 * self.font_scale)),
            fg=self.colors['primary'],
            bg=self.colors['white']
        )
        self.loading_label.pack(pady=(int(20 * self.ui_scale), int(10 * self.ui_scale)))

        self.loading_text = tk.Label(
            self.loading_frame,
            text="Loading versions...",
            font=("Segoe UI", int(11 * self.font_scale)),
            fg=self.colors['secondary'],
            bg=self.colors['white']
        )
        self.loading_text.pack()
        # Will be shown/hidden in loading functions

    def _create_action_section(self):
        """Create action buttons section with responsive design."""
        self.action_card = self._create_card_container(
            self.frame,
            row=3, # Adjusted row index
            column=0,
            sticky='ew',
            padx=self.STANDARD_PADDING,
            pady=(self.SMALL_PADDING, self.STANDARD_PADDING)
        )

        # Button container with right alignment
        self.button_frame = tk.Frame(self.action_card, bg=self.colors['card'])
        self.button_frame.pack(fill='x', padx=self.STANDARD_PADDING, pady=self.STANDARD_PADDING)
        # Push button to the right
        self.button_frame.grid_columnconfigure(0, weight=1)

        # Main restore button (right-aligned)
        self.restore_button = self._create_button(
            self.button_frame,
            "Restore Selected Version",
            self._restore_selected_version,
            is_primary=True,
            icon="♻️" # Changed icon
        )
        self.restore_button.grid(row=0, column=1, sticky='e') # Use grid for alignment
        self._set_button_state(self.restore_button, False) # Initially disabled

    def _create_card_container(self, parent, row, column, sticky, padx, pady):
        """Create a card-like container with subtle shadow for sections."""
        container = tk.Frame(
            parent,
            bg=self.colors['card'],
            bd=1,
            relief="solid",
            highlightbackground=self.colors['border'],
            highlightthickness=1
        )
        container.grid(row=row, column=column, sticky=sticky, padx=padx, pady=pady)
        # Make the container itself expand horizontally
        container.grid_columnconfigure(0, weight=1)
        return container

    def _create_button(self, parent, text, command, is_primary=True, icon=None, compact=False):
        """Create a modern styled button with optional icon and proper hover behavior."""
        btn_text = f"{icon} {text}" if icon else text

        # Scale padding based on UI scale
        padx = int((10 if compact else 15) * self.ui_scale)
        pady = int((6 if compact else 8) * self.ui_scale)

        # Store original colors for state management
        primary_bg = self.colors['primary']
        primary_hover_bg = self.colors['primary_dark']
        secondary_bg = self.colors['light']
        secondary_hover_bg = '#e2e6ea'

        btn = tk.Button(
            parent,
            text=btn_text,
            command=command,
            font=("Segoe UI", int((9 if compact else 10) * self.font_scale), "bold" if is_primary else "normal"),
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
            # Check if widget exists before accessing properties
             if event.widget.winfo_exists() and str(event.widget['state']) != 'disabled':
                 event.widget.config(background=primary_hover_bg if is_primary else secondary_hover_bg)

        def on_leave(event):
             # Check if widget exists before accessing properties
             if event.widget.winfo_exists() and str(event.widget['state']) != 'disabled':
                 event.widget.config(background=primary_bg if is_primary else secondary_bg)

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
         # Check if button exists before configuring
        if not button or not button.winfo_exists():
             return

        if not hasattr(button, 'is_primary'):
            button.config(state=tk.NORMAL if enabled else tk.DISABLED)
            return

        if enabled:
            button.config(state=tk.NORMAL)
            # Reset to normal background
            bg_color = button.primary_bg if button.is_primary else button.secondary_bg
            fg_color = self.colors['white'] if button.is_primary else self.colors['dark']
            button.config(background=bg_color, foreground=fg_color)
        else:
            button.config(state=tk.DISABLED)
            # Use a consistent disabled color
            button.config(background=self.colors['disabled'])
            button.config(foreground=self.colors['disabled_text'])

    def _check_backup_exists(self, file_path: str, version_hash: str) -> bool:
        """Check if backup file exists for given version using BackupManager."""
        try:
            # Use backup_manager if it has the method
            if hasattr(self.backup_manager, 'check_backup_exists'):
                return self.backup_manager.check_backup_exists(file_path, version_hash)
            else:
                 print("Warning: BackupManager missing 'check_backup_exists'. Falling back.")
                 # Fallback (less reliable if path structure changed)
                 backup_path = os.path.join(
                     self.backup_folder,
                     "versions",
                     os.path.basename(file_path),
                     f"{version_hash}.gz"
                 )
                 return os.path.exists(backup_path)
        except Exception as e:
             print(f"Error checking backup existence for {version_hash}: {e}")
             return False


    def _show_loading(self):
        """Show loading indicator."""
        # Check if UI elements exist
        if not hasattr(self, 'loading_frame') or not self.loading_frame.winfo_exists() or \
           not hasattr(self, 'version_tree') or not hasattr(self, 'empty_message'):
             return

        self.loading = True
        self.version_tree.grid_remove() # Hide tree
        self.empty_message.place_forget() # Hide empty message
        self.loading_frame.place(relx=0.5, rely=0.5, anchor='center') # Show loading frame
        self._animate_loading()

    def _hide_loading(self):
        """Hide loading indicator."""
         # Check if UI elements exist
        if not hasattr(self, 'loading_frame') or not self.loading_frame.winfo_exists() or \
           not hasattr(self, 'version_tree') or not hasattr(self, 'empty_message'):
             return

        self.loading = False
        self.loading_frame.place_forget() # Hide loading frame

        # Decide whether to show the tree or the empty message
        if self.version_tree.get_children():
            self.version_tree.grid() # Show tree if it has items
            self.empty_message.place_forget()
        else:
            self.version_tree.grid_remove()
            self.empty_message.place(relx=0.5, rely=0.5, anchor='center') # Show empty message


    def _animate_loading(self):
        """Animate the loading indicator."""
        if not self.loading:
            return
        # Check if label exists
        if not hasattr(self, 'loading_label') or not self.loading_label.winfo_exists():
            self.loading = False # Stop animation if label is gone
            return

        # Rotate the spinner character
        try:
            current_text = self.loading_label.cget("text")
            self.loading_label.config(text="⟲" if current_text == "⟳" else "⟳")
        except tk.TclError:
            self.loading = False # Stop animation if widget destroyed during config
            return


        # Schedule next animation frame, checking parent existence
        if self.parent and self.parent.winfo_exists():
             self.parent.after(250, self._animate_loading)
        else:
             self.loading = False # Stop if parent destroyed


    def _filter_versions(self, event=None):
        """Filter version list based on search and filter criteria."""
        # Check if UI elements exist
        if not hasattr(self, 'search_entry') or not self.search_entry.winfo_exists() or \
           not hasattr(self, 'filter_var') or not hasattr(self, 'version_tree'):
             return

        search_text = self.search_entry.get().lower()
        filter_option = self.filter_var.get()

        # Skip the placeholder text
        if search_text == "search versions...":
            search_text = ""

        # Get all versions from the stored data
        if not self.versions_data:
             self._populate_version_tree([]) # Ensure tree/empty message is shown correctly
             return

        filtered_versions = []
        now = datetime.now() # Get current time once for filtering

        for version_hash, info in self.versions_data:
            # --- Apply Filters ---
            is_deleted = info.get("deleted", False)
            backup_exists = self._check_backup_exists(self.selected_file, version_hash)

            if filter_option == "Available Only" and (is_deleted or not backup_exists):
                continue
            if filter_option == "Deleted Only" and not is_deleted:
                 continue

            if filter_option == "Last 7 Days":
                try:
                    # Attempt to parse timestamp, handle potential errors
                    version_dt_utc_str = info.get("timestamp")
                    if version_dt_utc_str:
                         # Assuming timestamp is UTC like "YYYY-MM-DD HH:MM:SS"
                         version_dt_utc = datetime.strptime(version_dt_utc_str, "%Y-%m-%d %H:%M:%S")
                         # Make it offset-aware for comparison
                         version_dt_utc = pytz.utc.localize(version_dt_utc)
                         now_utc = datetime.now(pytz.utc) # Get offset-aware current UTC time
                         if (now_utc - version_dt_utc) > timedelta(days=7):
                              continue
                    else:
                         continue # Skip if no valid timestamp
                except (ValueError, TypeError) as e:
                     print(f"Warning: Could not parse timestamp '{info.get('timestamp')}' for filtering: {e}")
                     continue # Skip if timestamp is invalid

            if filter_option == "My Versions" and info.get("username", "") != self.username:
                continue

            # --- Apply Search ---
            if search_text:
                # Search in message, username, timestamp (local format), and hash
                message = info.get("commit_message", "").lower()
                username_val = info.get("username", "").lower()
                timestamp_utc_str = info.get("timestamp", "")
                _, local_time_str = format_timestamp_dual(timestamp_utc_str) # Get local time string

                if (search_text not in message and
                    search_text not in username_val and
                    search_text not in local_time_str.lower() and # Search local time
                    search_text not in version_hash.lower()): # Search hash
                    continue

            # Add to filtered list if all checks passed
            filtered_versions.append((version_hash, info))

        # Display filtered versions
        self._populate_version_tree(filtered_versions)


    def _populate_version_tree(self, versions_to_display):
        """Populate tree with provided version data."""
        # Check if UI elements exist
        if not hasattr(self, 'version_tree') or not self.version_tree.winfo_exists() or \
           not hasattr(self, 'empty_message') or not hasattr(self, 'version_count_label'):
             return

        # Clear tree first
        self.version_tree.delete(*self.version_tree.get_children())

        if not versions_to_display:
            self.version_tree.grid_remove() # Hide tree
            self.empty_message.config(text="No versions match the current filter")
            self.empty_message.place(relx=0.5, rely=0.5, anchor='center') # Show empty message
            self.version_count_label.config(text="0 versions shown")
            return

        # Show tree, hide empty message
        self.empty_message.place_forget()
        self.version_tree.grid()

        # Sort the versions to display (newest first)
        # This sorting is crucial for the display order
        sorted_versions_to_display = sorted(
            versions_to_display,
            key=lambda x: datetime.strptime(x[1]["timestamp"], "%Y-%m-%d %H:%M:%S")
                if "timestamp" in x[1] else datetime.min,
            reverse=True
        )

        # Insert items into the tree
        for i, (version_hash, info) in enumerate(sorted_versions_to_display):
            is_deleted_flag = info.get("deleted", False)
            # Add to the end of the tree (ttk handles display order based on insertion)
            self.version_tree.insert(
                "", "end", iid=version_hash, # Use full hash as item ID
                values=self._format_version_values(version_hash, info, is_deleted=is_deleted_flag),
                tags=self._get_version_tags(i, version_hash, info, is_deleted=is_deleted_flag)
            )

        # Update version count label based on the *displayed* items
        self.version_count_label.config(text=f"{len(sorted_versions_to_display)} versions shown")


    def _format_version_values(self, version_hash, info, is_deleted=False):
        """Format values for a version to be displayed in the tree."""
        metadata = info.get("metadata", {})
        utc_time_str = info.get("timestamp", "N/A")
        utc_time, local_time = format_timestamp_dual(utc_time_str) # Use the utility

        # Check if backup exists using the reliable method
        backup_available = self._check_backup_exists(self.selected_file, version_hash)

        # Determine status text based on is_deleted flag and backup_available
        if is_deleted:
            status_text = f"Deleted ({'Available' if backup_available else 'Unavailable'})"
        elif backup_available:
            status_text = "Available"
        else:
            status_text = "Missing Backup!" # Active version but file is gone

        return (
            local_time, # Show local time in the tree
            info.get("commit_message", "No message"),
            info.get("username", self.username),
            format_size(metadata.get("size", 0)),
            version_hash[:12] + "...", # Show shortened hash
            status_text
        )

    def _get_version_tags(self, row_index, version_hash, info, is_deleted=False):
        """Get the tags for a version to be displayed in the tree."""
        # Check if backup exists
        backup_available = self._check_backup_exists(self.selected_file, version_hash)

        # Determine tags based on status
        tags = []
        if is_deleted:
            if backup_available:
                 tags.append('deleted') # Gray text
            else:
                 tags.append('deleted_unavailable') # Italic gray text
        elif backup_available:
            tags.append('available') # Green text (or default dark if not configured)
        else:
            tags.append('missing') # Bold red text

        # Add row index tag for potential alternating colors (if enabled)
        # tags.append('even_row' if row_index % 2 == 0 else 'odd_row')

        return tags


    def _refresh_version_list(self):
        """Refresh the version list, showing loading indicator."""
        # Check if UI exists
        if not hasattr(self, 'frame') or not self.frame.winfo_exists():
             return

        # Don't refresh if no file is selected
        if not self.selected_file: # No need to check os.path here, handle in load
            self._update_file_metadata(None) # Clear metadata display
            # Clear tree and show appropriate message
            if hasattr(self, 'version_tree'): self.version_tree.delete(*self.version_tree.get_children())
            if hasattr(self, 'empty_message'):
                 self.empty_message.config(text="No file selected")
                 self.empty_message.place(relx=0.5, rely=0.5, anchor='center')
            if hasattr(self, 'version_tree'): self.version_tree.grid_remove()
            if hasattr(self, 'version_count_label'): self.version_count_label.config(text="No file selected")
            return

        # Show loading indicator
        self._show_loading()

        # Use threading to prevent UI freeze
        threading.Thread(target=self._load_version_data_thread, daemon=True).start()


    def _load_version_data_thread(self):
        """Load version data in a background thread."""
        loaded_data = []
        error_message = None
        try:
            # Use version_manager to get tracked files
            # Ensure selected_file is valid before loading
            if not self.selected_file:
                 raise ValueError("No file selected.")

            tracked_files = self.version_manager.load_tracked_files()
            normalized_path = os.path.normpath(self.selected_file)

            if normalized_path in tracked_files:
                versions = tracked_files[normalized_path].get("versions", {})
                if versions:
                    # Convert to list of (version_hash, info) tuples
                    # No need to sort here, sorting happens during display/filtering
                    loaded_data = list(versions.items())

        except Exception as e:
            print(f"Error loading version data thread: {str(e)}")
            error_message = f"Failed to load versions: {str(e)}"

        finally:
             # Update UI on main thread, checking parent existence
             if self.parent and self.parent.winfo_exists():
                  self.parent.after(0, lambda data=loaded_data, err=error_message: self._update_ui_after_loading(data, err))


    def _update_ui_after_loading(self, loaded_data, error_message):
        """Update UI after version data is loaded (runs on main thread)."""
        # Hide loading indicator first
        self._hide_loading()

        if error_message:
            self._show_error(error_message)
            self.versions_data = [] # Clear data on error
        else:
            self.versions_data = loaded_data # Store the loaded data
            # Update file metadata display now that data is loaded
            self._update_file_metadata(self.selected_file)
            # Apply initial filter/search which will populate the tree
            self._filter_versions()


    def _show_error(self, message):
        """Show error message and update UI."""
        # Check if UI elements exist
        if not hasattr(self, 'version_count_label') or not self.version_count_label.winfo_exists() or \
           not hasattr(self, 'empty_message') or not hasattr(self, 'version_tree'):
             return

        self.version_count_label.config(text=f"Error")
        self.empty_message.config(text=message) # Show detailed error here
        self.empty_message.place(relx=0.5, rely=0.5, anchor='center')
        self.version_tree.grid_remove() # Hide tree on error


    def _update_file_metadata(self, file_path):
        """Update the file metadata display."""
        # Check if UI elements exist
        if not hasattr(self, 'file_name_label') or not self.file_name_label.winfo_exists() or \
           not hasattr(self, 'file_details_label') or not hasattr(self, 'file_icon_label') or \
           not hasattr(self, 'status_indicator') or not hasattr(self, 'status_label'):
             return

        if not file_path or not os.path.exists(file_path):
            # Reset to empty state
            self.file_name_label.config(text="No file selected")
            self.file_details_label.config(text="Select a file to see its details")
            self.file_icon_label.config(text="📄", fg=self.colors['secondary'])
            self.status_indicator.config(bg=self.colors['secondary'])
            self.status_label.config(text="Unknown", fg=self.colors['secondary'])
            return

        try:
            # Get file metadata
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(filename)[1].lower()

            # Use version_manager to get metadata if available
            if hasattr(self.version_manager, 'get_file_metadata'):
                metadata = self.version_manager.get_file_metadata(file_path)
                if not metadata: # Handle failure to get metadata
                     raise FileNotFoundError("Could not retrieve file metadata.")
            else:
                # Fallback to direct stat
                stat = os.stat(file_path)
                metadata = {
                    "size": stat.st_size,
                    "modification_time": {
                        "local": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S %Z"),
                        "utc": datetime.utcfromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    },
                    "file_type": file_ext
                }

            # Set file icon based on extension (using type_handler if available)
            icon = "📄"  # Default
            icon_color = self.colors['primary']
            if hasattr(self, 'type_handler'): # Check if CommitPage's handler is accessible/passed
                 category = self.type_handler.get_file_category(file_path)
                 icon = self.type_handler.get_category_icon(category)
                 # Optionally set color based on category too
            else: # Simple fallback based on extension
                 if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg']: icon = "🖼️"; icon_color = self.colors['info']
                 elif file_ext in ['.doc', '.docx', '.pdf', '.txt', '.md']: icon = "📝"; icon_color = self.colors['primary']
                 elif file_ext in ['.py', '.js', '.html', '.css', '.java']: icon = "💻"; icon_color = self.colors['success']
                 elif file_ext in ['.mp3', '.wav', '.ogg']: icon = "🎵"; icon_color = self.colors['warning']
                 elif file_ext in ['.mp4', '.avi', '.mov']: icon = "🎬"; icon_color = self.colors['danger']


            # Update UI elements
            self.file_name_label.config(text=filename)

            # Format details
            size_str = format_size(metadata.get('size', 0))
            mod_time = metadata.get('modification_time', {}).get('local', 'N/A')
            # Use self.versions_data which is now populated
            versions_count = len(self.versions_data) if self.versions_data else 0

            details = f"Size: {size_str}  •  Modified: {mod_time}  •  Versions: {versions_count}"
            self.file_details_label.config(text=details)

            # Update icon
            self.file_icon_label.config(text=icon, fg=icon_color)

            # Update status indicator based on file monitor state
            has_changes = False
            status_text = "Unknown"
            status_color = self.colors['secondary']
            if hasattr(self.shared_state, 'file_monitor') and self.shared_state.file_monitor:
                file_monitor = self.shared_state.file_monitor
                if hasattr(file_monitor, 'has_changes'): # Check if method exists
                    has_changes = file_monitor.has_changes(file_path)
                    status_text = "Modified" if has_changes else "Saved"
                    status_color = self.colors['danger'] if has_changes else self.colors['success']

            self.status_indicator.config(bg=status_color)
            self.status_label.config(text=status_text, fg=status_color if status_text != "Unknown" else self.colors['secondary'])


        except Exception as e:
            print(f"Error updating file metadata display: {e}")
            self.file_name_label.config(text=os.path.basename(file_path))
            self.file_details_label.config(text=f"Error retrieving details")
            self.file_icon_label.config(text="⚠️", fg=self.colors['warning'])
            self.status_indicator.config(bg=self.colors['warning'])
            self.status_label.config(text="Error", fg=self.colors['warning'])


    def _on_version_selected(self, event):
        """Handle version selection in tree view."""
        # Check if treeview exists
        if not hasattr(self, 'version_tree') or not self.version_tree.winfo_exists():
            return

        selection = self.version_tree.selection()
        if not selection:
            self.selected_version_hash = None
            self._set_button_state(self.restore_button, False)
            return

        # Get the item ID (which is the full hash)
        self.selected_version_hash = selection[0]

        # Get tags to determine availability
        item_data = self.version_tree.item(self.selected_version_hash)
        tags = item_data["tags"]

        # Check for tags indicating the backup file is present
        # 'available' tag is for active versions with backup
        # 'deleted' tag means metadata is deleted, but file *might* be available (check backup_exists)
        is_restorable = False
        if 'available' in tags: # Active version with backup
             is_restorable = True
        elif 'deleted' in tags: # Deleted metadata, check physical file status from values
             status_text = item_data["values"][self.columns.index("Status")] # Get status text
             if "Available" in status_text: # e.g., "Deleted (Available)"
                  is_restorable = True

        self._set_button_state(self.restore_button, is_restorable)

        if not is_restorable:
            # Show warning tooltip near the restore button if selection is not restorable
            self._show_warning_tooltip(
                "This version's backup file is not available.\n"
                "The backup may have been deleted or moved."
            )
        else:
             self._hide_tooltip() # Hide any previous warning


    def _on_version_double_click(self, event):
        """Handle double click on version."""
        # Check if treeview exists
        if not hasattr(self, 'version_tree') or not self.version_tree.winfo_exists():
            return

        selection = self.version_tree.selection()
        if not selection:
            return

        # Get tags to check availability before triggering restore
        item_data = self.version_tree.item(selection[0])
        tags = item_data["tags"]
        status_text = item_data["values"][self.columns.index("Status")]

        is_restorable = 'available' in tags or ('deleted' in tags and "Available" in status_text)

        if is_restorable:
            # Double-clicking on a restorable version triggers restore confirmation
            self._restore_selected_version()


    def _show_warning_tooltip(self, message):
        """Show warning tooltip near the restore button."""
        # Check if button exists
        if not hasattr(self, 'restore_button') or not self.restore_button.winfo_exists():
            return

        # Position tooltip near the restore button
        x = self.restore_button.winfo_rootx() + self.restore_button.winfo_width() // 2
        y = self.restore_button.winfo_rooty() - 30 # Position above the button

        # Close any existing tooltip
        self._hide_tooltip()

        # Create new tooltip Toplevel
        self.tooltip_window = tk.Toplevel(self.parent)
        self.tooltip_window.wm_overrideredirect(True)
        # Ensure position is calculated correctly relative to screen
        self.tooltip_window.wm_geometry(f"+{x-100}+{y}") # Adjust x offset if needed

        # Style the tooltip
        tooltip_frame = tk.Frame(
            self.tooltip_window,
            bg=self.colors['warning'],
            bd=0
        )
        tooltip_frame.pack(fill='both', expand=True)

        tooltip_label = tk.Label(
            tooltip_frame,
            text=message,
            font=("Segoe UI", int(9 * self.font_scale), "bold"),
            bg=self.colors['warning'],
            fg=self.colors['dark'],
            justify=tk.LEFT,
            padx=10,
            pady=8
        )
        tooltip_label.pack(fill='both')

        # Auto-hide after 3 seconds, checking parent existence
        if self.parent and self.parent.winfo_exists():
             self.parent.after(3000, self._hide_tooltip)


    def _animate_restore_success(self):
        """Show animation for successful restore."""
        # Check parent exists
        if not self.parent or not self.parent.winfo_exists():
             return

        # Create success overlay
        overlay = tk.Toplevel(self.parent)
        overlay.transient(self.parent)
        overlay.overrideredirect(True)
        overlay.attributes("-alpha", 0.9)
        overlay.attributes("-topmost", True)

        # Position at center of parent
        try:
             parent_width = self.parent.winfo_width()
             parent_height = self.parent.winfo_height()
             parent_x = self.parent.winfo_rootx()
             parent_y = self.parent.winfo_rooty()
             width = int(350 * self.ui_scale) # Slightly wider for message
             height = int(200 * self.ui_scale)
             x = parent_x + (parent_width // 2) - (width // 2)
             y = parent_y + (parent_height // 2) - (height // 2)
             overlay.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
             print("Error positioning success animation.")
             overlay.destroy()
             return


        # Create content
        success_frame = tk.Frame(overlay, bg=self.colors['success'], padx=int(40 * self.ui_scale), pady=int(30 * self.ui_scale))
        success_frame.pack(fill='both', expand=True)

        check_label = tk.Label(
            success_frame,
            text="✓",
            font=("Segoe UI", int(64 * self.font_scale), "bold"),
            fg=self.colors['white'],
            bg=self.colors['success']
        )
        check_label.pack(pady=(int(10 * self.ui_scale), 0))

        message = tk.Label(
            success_frame,
            text="Version Restored Successfully!",
            font=("Segoe UI", int(14 * self.font_scale), "bold"),
            fg=self.colors['white'],
            bg=self.colors['success']
        )
        message.pack(pady=(0, int(10 * self.ui_scale)))

        # Auto-close after 1.5 seconds, checking parent existence
        if self.parent and self.parent.winfo_exists():
             self.parent.after(1500, lambda: overlay.destroy() if overlay.winfo_exists() else None)


    def _restore_selected_version(self):
        """Restore a selected version with backup availability check."""
        # Check UI elements and selection
        if not self.selected_file or not self.selected_version_hash or \
           not hasattr(self, 'version_tree') or not self.version_tree.winfo_exists():
            messagebox.showwarning("Action Failed", "No file or version selected.", parent=self.parent)
            return

        # --- Re-verify Availability ---
        try:
            item_data = self.version_tree.item(self.selected_version_hash)
            tags = item_data["tags"]
            status_text = item_data["values"][self.columns.index("Status")]
            is_restorable = 'available' in tags or ('deleted' in tags and "Available" in status_text)

            if not is_restorable:
                self._show_warning_tooltip("Backup is unavailable. Cannot restore.")
                return

            # Get details for confirmation dialog
            local_time, message, user, size, _, _ = item_data["values"]

        except tk.TclError:
             messagebox.showerror("Error", "Could not retrieve version details. Please refresh.", parent=self.parent)
             return
        except IndexError:
             messagebox.showerror("Error", "Could not parse version details. Please refresh.", parent=self.parent)
             return


        # --- Show Confirmation Dialog ---
        confirm = self._create_improved_confirm_dialog(
            "Restore Version",
            f"Are you sure you want to restore this version?\nThis will replace the current file content.",
            {
                "Time": local_time,
                "Message": message,
                "Size": size,
                "User": user
            }
        )

        if confirm:
            try:
                # Show progress animation
                progress = self._show_progress_dialog("Restoring version...")

                # Restore in a separate thread
                threading.Thread(target=self._do_restore_thread, args=(progress,), daemon=True).start()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to start restore: {str(e)}", parent=self.parent)


    def _do_restore_thread(self, progress_dialog):
         """Background thread execution for the restore operation."""
         try:
             # --- Mark file as restoring (prevents commit dialog) ---
             if hasattr(self.shared_state, 'file_monitor'):
                 self.shared_state.file_monitor.mark_file_as_restoring(self.selected_file)

             # --- Perform Restore ---
             self.backup_manager.restore_file_version(self.selected_file, self.selected_version_hash)

             # Brief pause allows filesystem changes to settle
             time.sleep(0.2)

             # --- Reset File Monitoring ---
             if hasattr(self.shared_state, 'file_monitor'):
                 file_monitor = self.shared_state.file_monitor
                 normalized_path = os.path.normpath(self.selected_file)

                 # Use force_check or a similar method if available
                 if hasattr(file_monitor, 'force_check'):
                      file_monitor.force_check(normalized_path)
                      print(f"Forced check on {normalized_path} after restore.")
                 else:
                      # Manual reset (less ideal, copy logic from previous example if needed)
                      print("Warning: File monitor missing 'force_check'. Manual reset logic might be needed.")
                      # Example manual reset (adapt if necessary):
                      with file_monitor.lock:
                          if normalized_path in file_monitor.watched_files:
                               del file_monitor.watched_files[normalized_path] # Remove old state
                          if os.path.exists(normalized_path):
                               file_monitor.add_file(normalized_path) # Re-add to get fresh state


             # --- Success: Update UI on Main Thread ---
             if self.parent and self.parent.winfo_exists():
                 self.parent.after(0, lambda: (
                     progress_dialog.destroy() if progress_dialog.winfo_exists() else None,
                     self._animate_restore_success(),
                     self._refresh_version_list(), # Refresh history view
                     # Notify commit page/monitor about the change
                     self.shared_state.notify_external_change(self.selected_file)
                 ))

         except Exception as e:
             # --- Error Handling: Update UI on Main Thread ---
             error_msg = str(e)
             print(f"Error during restore thread: {error_msg}")
             if self.parent and self.parent.winfo_exists():
                 self.parent.after(0, lambda error=error_msg: (
                     progress_dialog.destroy() if progress_dialog.winfo_exists() else None,
                     messagebox.showerror("Restore Error", f"Failed to restore version: {error}", parent=self.parent)
                 ))
         finally:
              # --- Ensure restoring flag is cleared ---
              if hasattr(self.shared_state, 'file_monitor'):
                   self.shared_state.file_monitor.unmark_file_as_restoring(self.selected_file)


    def _show_progress_dialog(self, message):
        """Show a progress dialog for long operations."""
        # Check parent exists
        if not self.parent or not self.parent.winfo_exists():
             return None # Cannot create dialog without parent

        # Create dialog
        progress = tk.Toplevel(self.parent)
        progress.transient(self.parent)
        progress.title("Working...")
        progress.geometry(f"{int(300 * self.ui_scale)}x{int(120 * self.ui_scale)}")
        progress.resizable(False, False)

        # Position in center of parent
        try:
             parent_width = self.parent.winfo_width()
             parent_height = self.parent.winfo_height()
             parent_x = self.parent.winfo_rootx()
             parent_y = self.parent.winfo_rooty()
             x = parent_x + (parent_width // 2) - int(150 * self.ui_scale)
             y = parent_y + (parent_height // 2) - int(60 * self.ui_scale)
             progress.geometry(f"+{x}+{y}")
        except tk.TclError:
             print("Error positioning progress dialog.")
             # Position top-left as fallback
             progress.geometry(f"+{self.parent.winfo_rootx()+50}+{self.parent.winfo_rooty()+50}")


        # Dialog content
        content = tk.Frame(progress, padx=int(20 * self.ui_scale), pady=int(20 * self.ui_scale))
        content.pack(fill='both', expand=True)

        # Spinner
        spinner_label = tk.Label(
            content,
            text="⟳",
            font=("Segoe UI", int(24 * self.font_scale)),
            fg=self.colors['primary']
        )
        spinner_label.pack()

        # Message
        msg_label = tk.Label(
            content,
            text=message,
            font=("Segoe UI", int(11 * self.font_scale))
        )
        msg_label.pack(pady=(int(10 * self.ui_scale), 0))

        # Animate spinner
        spin_job = [None] # Use list to allow modification within nested function
        def spin():
            if progress.winfo_exists(): # Check if dialog still exists
                 current = spinner_label.cget("text")
                 spinner_label.config(text="⟲" if current == "⟳" else "⟳")
                 spin_job[0] = progress.after(250, spin)
            else:
                 spin_job[0] = None # Stop animation

        spin()

        # Prevent closing & make modal
        progress.protocol("WM_DELETE_WINDOW", lambda: None)
        progress.grab_set()
        progress.focus_force()

        return progress


    def _create_improved_confirm_dialog(self, title, message, details=None):
        """
        Create a larger confirmation dialog that shows all content and buttons.
        (This version seems robust, keeping it as is)
        """
        # Check parent exists
        if not self.parent or not self.parent.winfo_exists():
             return False # Cannot create dialog

        # Create dialog
        dialog = tk.Toplevel(self.parent)
        dialog.transient(self.parent)
        dialog.title(title)

        # Make dialog larger
        dialog_width = int(600 * self.ui_scale)
        dialog_height = int(450 * self.ui_scale)

        # Ensure it's visible on screen
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()

        # Keep dialog within screen bounds
        dialog_width = min(dialog_width, screen_width - 100)
        dialog_height = min(dialog_height, screen_height - 100)

        # Set size and position
        try:
             x = (screen_width - dialog_width) // 2
             y = (screen_height - dialog_height) // 2
             dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        except tk.TclError:
             print("Error positioning confirmation dialog.")
             dialog.geometry(f"{dialog_width}x{dialog_height}+50+50") # Fallback


        # Make dialog resizable
        dialog.resizable(True, True)

        # Use the entire dialog for content
        main_container = tk.Frame(dialog, padx=int(30 * self.ui_scale), pady=int(30 * self.ui_scale))
        main_container.pack(fill='both', expand=True)
        main_container.grid_columnconfigure(0, weight=1)
        main_container.grid_rowconfigure(1, weight=1)  # Details area can expand

        # Top section with icon and message
        top_frame = tk.Frame(main_container)
        top_frame.grid(row=0, column=0, sticky='ew', pady=(0, int(20 * self.ui_scale)))
        top_frame.grid_columnconfigure(1, weight=1)

        # Warning icon
        icon_label = tk.Label(
            top_frame,
            text="⚠️",
            font=("Segoe UI", int(36 * self.font_scale)),
            fg=self.colors['warning']
        )
        icon_label.grid(row=0, column=0, padx=(0, int(20 * self.ui_scale)), sticky='nw') # Align top-west

        # Message with plenty of space
        msg_label = tk.Label(
            top_frame,
            text=message,
            font=("Segoe UI", int(12 * self.font_scale)),
            justify=tk.LEFT,
            wraplength=int(dialog_width * 0.7), # Wrap based on dialog width
            anchor='w'
        )
        msg_label.grid(row=0, column=1, sticky='w')

        # Details section
        if details:
            # Create a frame for details with scrolling if needed
            details_frame = tk.Frame(
                main_container,
                bd=1,
                relief='solid',
                highlightbackground=self.colors['border'],
                highlightthickness=1
            )
            details_frame.grid(row=1, column=0, sticky='nsew', pady=(0, int(20 * self.ui_scale)))
            details_frame.grid_columnconfigure(0, weight=1)
            details_frame.grid_rowconfigure(0, weight=1)

            # Inner container with padding
            inner_frame = tk.Frame(details_frame, padx=int(20 * self.ui_scale), pady=int(15 * self.ui_scale))
            inner_frame.pack(fill='both', expand=True) # Use pack here
            inner_frame.grid_columnconfigure(1, weight=1) # Configure grid inside inner_frame

            # Add details as grid of labels
            row = 0
            for key, value in details.items():
                # Column for key
                key_label = tk.Label(
                    inner_frame,
                    text=f"{key}:",
                    font=("Segoe UI", int(11 * self.font_scale), "bold"),
                    anchor='w'
                )
                key_label.grid(row=row, column=0, sticky='nw', pady=5)

                # Column for value
                value_label = tk.Label(
                    inner_frame,
                    text=str(value),
                    font=("Segoe UI", int(11 * self.font_scale)),
                    anchor='w',
                    wraplength=int(dialog_width * 0.6) # Wrap value based on dialog width
                )
                value_label.grid(row=row, column=1, sticky='nw', padx=(15, 0), pady=5)

                row += 1

        # Button frame at very bottom, fixed height
        button_frame = tk.Frame(main_container)
        button_frame.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        button_frame.grid_columnconfigure(1, weight=1)  # Push buttons to right

        # Store result using a list to allow modification from lambda
        result = [False] # Default to False

        # Cancel button
        cancel_btn = tk.Button(
            button_frame,
            text="Cancel",
            font=("Segoe UI", int(11 * self.font_scale)),
            command=lambda: (dialog.destroy()), # Just destroy, result remains False
            bg=self.colors['light'],
            fg=self.colors['dark'],
            padx=25,
            pady=12,  # Taller buttons
            relief='flat'
        )
        cancel_btn.grid(row=0, column=1, sticky='e', padx=(0, 10))

        # Confirm button
        confirm_btn = tk.Button(
            button_frame,
            text="Restore Version",
            font=("Segoe UI", int(11 * self.font_scale), "bold"),
            command=lambda: (result.__setitem__(0, True), dialog.destroy()), # Set result to True and destroy
            bg=self.colors['primary'],
            fg=self.colors['white'],
            padx=25,
            pady=12,  # Taller buttons
            relief='flat'
        )
        confirm_btn.grid(row=0, column=2, sticky='e')

        # Make modal and wait for result
        dialog.protocol("WM_DELETE_WINDOW", lambda: (dialog.destroy())) # Destroy on close, result remains False
        dialog.grab_set()
        dialog.focus_force()
        dialog.wait_window()

        # Return result
        return result[0]

    def _on_file_updated(self, file_path):
        """Callback when file selection changes."""
        self.selected_file = file_path
        self.selected_version_hash = None # Reset selection on file change

        # Update UI based on selection, check parent existence
        if self.parent and self.parent.winfo_exists():
             # Add slight delay to allow other UI updates
             self.parent.after(50, self._refresh_version_list)
             self.parent.after(50, lambda: self._update_file_metadata(file_path)) # Update metadata too


    def _on_version_changed(self):
        """Callback when a new version is committed globally."""
        # Schedule data reload on main thread only if the current file is selected
        # Check if frame still exists before scheduling
        if hasattr(self, 'frame') and self.frame.winfo_exists():
             # Check if the change affects the currently selected file
             if self.shared_state.get_selected_file() == self.selected_file:
                  # Add a small delay, check parent existence
                  if self.parent and self.parent.winfo_exists():
                       self.parent.after(50, self._refresh_version_list)


    def _on_frame_configure(self, event=None):
        """Handle frame resize with debounce."""
        # Check parent exists before scheduling 'after'
        if not self.parent or not self.parent.winfo_exists():
             return

        # Debounce resize events
        if hasattr(self, 'resize_timer') and self.resize_timer:
            try:
                self.parent.after_cancel(self.resize_timer)
            except tk.TclError: pass # Ignore if already cancelled

        # Schedule layout refresh after resize stops
        self.resize_timer = self.parent.after(100, self.refresh_layout)


    def refresh_layout(self):
        """Refresh layout on window resize or other events."""
        # Update tree column widths
        if hasattr(self, 'version_tree') and self.version_tree.winfo_exists():
            try:
                 width = self.version_tree.winfo_width()
                 if width > 50:  # Only adjust if tree has been rendered
                     # Adjust column widths - these might need tweaking
                     # Weights: Time=0.20, Msg=0.30, User=0.15, Size=0.10, Hash=0.15, Status=0.10 => Sum=1.0
                     self.version_tree.column("Local Time", width=int(width * 0.20))
                     self.version_tree.column("Message", width=int(width * 0.30))
                     self.version_tree.column("User", width=int(width * 0.15))
                     self.version_tree.column("Size", width=int(width * 0.10))
                     self.version_tree.column("Hash", width=int(width * 0.15))
                     self.version_tree.column("Status", width=int(width * 0.10))
            except tk.TclError:
                 print("Error refreshing layout (widget might be destroyed).")


    def _cleanup(self):
        """Clean up resources when frame is destroyed."""
        print("Cleaning up RestorePage...")
        # Safely remove callbacks
        try:
            if hasattr(self.shared_state, 'remove_file_callback'):
                 self.shared_state.remove_file_callback(self._on_file_updated)
            if hasattr(self.shared_state, 'remove_version_callback'):
                 self.shared_state.remove_version_callback(self._on_version_changed)
            # Fallback if generic remove_callback exists
            elif hasattr(self.shared_state, 'remove_callback'):
                self.shared_state.remove_callback(self._on_file_updated)
                self.shared_state.remove_callback(self._on_version_changed) # Use correct callback name
        except Exception as e:
            # Log error but don't prevent cleanup
            print(f"Error during RestorePage callback cleanup: {e}")

        # Cancel any pending 'after' jobs if necessary, checking parent existence
        if self.parent and self.parent.winfo_exists():
            if hasattr(self, 'resize_timer') and self.resize_timer:
                try: self.parent.after_cancel(self.resize_timer)
                except tk.TclError: pass
            # Cancel tooltip timer if it exists
            self.hide_tooltip() # This handles cancelling its own timer

        self.resize_timer = None # Clear timer ID
