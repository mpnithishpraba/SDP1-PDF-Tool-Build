"""
TWZ Pdf — Standalone Professional PDF Tool
Main Application Entry Point with Light/Dark Mode & Calibri Font
"""
import tkinter as tk
from tkinter import ttk, font
import sys
import os
from PIL import Image, ImageTk, ImageDraw

# Ensure we can find modules when running from PyInstaller bundle
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# DPI Awareness for Windows
try:
    from ctypes import windll, wintypes, Structure, byref
    # Try Per-Monitor V2 (2), fallback to System-Aware (1)
    try:
        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# Import feature modules
from pdf_to_image import PdfToImageFrame
from image_to_pdf import ImageToPdfFrame
from pdf_crop import PdfCropFrame
from pdf_split import PdfSplitFrame
from pdf_merge import PdfMergeFrame
from pdf_resize import PdfResizeFrame
from pdf_compress import PdfCompressFrame
from pdf_reorder import PdfReorderFrame
from pdf_magnifier import PdfMagnifierFrame


# ─── Color Palettes (Strictly MONOCHROME) ──────────────────────────────────
THEMES = {
    "dark": {
        "bg_dark":      "#000000",      # Pure Black background
        "bg_sidebar":   "#000000",      # Black Sidebar
        "bg_surface":   "#121212",      # Softer black for cards
        "bg_hover":     "#1e1e1e",      # Hover Gray
        "text":         "#ffffff",      # Pure White
        "text_dim":     "#a0a0a0",      # Muted Gray
        "accent":       "#ffffff",      # Pure White
        "accent_hover": "#e0e0e0",      # Light Gray
        "border":       "#333333",      # Soft Border
        "trough":       "#000000",      
    },
    "light": {
        "bg_dark":      "#ffffff",      # Pure White background
        "bg_sidebar":   "#ffffff",      # Pure White Sidebar
        "bg_surface":   "#f8f8f8",      # Very light grey for cards
        "bg_hover":     "#efefef",      # Hover Gray
        "text":         "#000000",      # Pure Black
        "text_dim":     "#757575",      # Gray
        "accent":       "#000000",      # Black
        "accent_hover": "#333333",      # Dim Black
        "border":       "#e0e0e0",      # Light Border
        "trough":       "#ffffff",
    }
}


class TWZPdfApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Towards Zero Error PDF Tool")
        
        # Robust Scaling: Get Work Area (excludes taskbar)
        def get_work_area():
            try:
                from ctypes import windll, wintypes, byref, Structure
                class RECT(Structure):
                    _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG),
                                ('right', wintypes.LONG), ('bottom', wintypes.LONG)]
                rect = RECT()
                # SPI_GETWORKAREA = 0x0030
                windll.user32.SystemParametersInfoW(0x0030, 0, byref(rect), 0)
                return rect.right - rect.left, rect.bottom - rect.top
            except Exception:
                # Fallback to standard winfo
                return self.root.winfo_screenwidth(), self.root.winfo_screenheight()

        work_w, work_h = get_work_area()
        
        # Initial size: 82% width, 88% height of WORK AREA
        win_w = int(work_w * 0.82)
        win_h = int(work_h * 0.88)
        
        # Center the window in the work area
        pos_x = (work_w - win_w) // 2
        pos_y = (work_h - win_h) // 2
        
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.root.minsize(950, 680)

        # Initialize attributes first
        self.frames = {}
        self.current_tool = None
        self.active_frame_id = None
        self.convert_menu_active = False
        
        # Theme State - Default: LIGHT
        self.current_theme = "light"
        self.colors = THEMES[self.current_theme]

        # Font configuration
        self._setup_fonts()

        # Set icon
        self._set_icon()

        # Configure styles
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self._apply_theme()

        # Build layout
        self._build_sidebar()
        self._build_main_area()
        self._build_status_bar()

        # Initialize all tool frames
        self._init_tool_frames()

        # Bindings
        self.root.bind("<Control-l>", lambda e: self._toggle_theme())

        # Show Convert (PDF→Image) by default
        self._switch_tool("convert")

    def _setup_fonts(self):
        """Configure application fonts with larger base sizes."""
        available_fonts = font.families()
        if "Calibri" in available_fonts:
            self.main_font = "Calibri"
        else:
            self.main_font = "Segoe UI"
        
        # Increased base sizes for better readability on High DPI
        self.fonts = {
            "ui": (self.main_font, 14),
            "ui_bold": (self.main_font, 14, "bold"),
            "title": (self.main_font, 26, "bold"),
            "subtitle": (self.main_font, 17, "bold"),
            "small": (self.main_font, 12),
            "icon": ("Segoe UI Symbol", 20),
        }

    def _set_icon(self):
        """Set the window icon from ico file."""
        try:
            if getattr(sys, 'frozen', False):
                icon_path = os.path.join(BASE_DIR, "logo.ico")
            else:
                icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

    def _apply_theme(self):
        """Apply the current theme colors to all ttk styles."""
        c = self.colors
        
        # Root background
        self.root.configure(bg=c["bg_dark"])

        # Configure Styles
        self.style.configure(".", background=c["bg_dark"], foreground=c["text"],
                             fieldbackground=c["bg_surface"],
                             font=self.fonts["ui"])

        # Frames
        self.style.configure("TFrame", background=c["bg_dark"])
        self.style.configure("Sidebar.TFrame", background=c["bg_sidebar"])
        self.style.configure("Surface.TFrame", background=c["bg_surface"])

        # Labels
        self.style.configure("TLabel", background=c["bg_dark"], foreground=c["text"], font=self.fonts["ui"])
        self.style.configure("Title.TLabel", font=self.fonts["title"], foreground=c["text"])
        self.style.configure("Desc.TLabel", foreground=c["text_dim"], font=self.fonts["small"])
        self.style.configure("Path.TLabel", foreground=c["text"], font=self.fonts["ui_bold"])
        self.style.configure("Sidebar.TLabel", background=c["bg_sidebar"],
                             foreground=c["text_dim"], font=self.fonts["small"])
        self.style.configure("Logo.TLabel", background=c["bg_sidebar"],
                             foreground=c["text"], font=(self.main_font, 19, "bold"))
        self.style.configure("Status.TLabel", background=c["bg_surface"],
                             foreground=c["text_dim"], font=self.fonts["small"])

        # Buttons — custom rounded edges via PIL images (grey background)
        btn_grey = "#d0d0d0" if self.current_theme == "light" else "#3a3a3a"
        btn_grey_hover = "#bfbfbf" if self.current_theme == "light" else "#4a4a4a"
        self._create_rounded_button_images(c, btn_type="normal",
            bg=btn_grey, border=c["border"],
            active_bg=btn_grey_hover, active_border=c["accent"],
            pressed_bg=c["accent"], pressed_border=c["accent"])
        self.style.configure("TButton", foreground=c["text"], padding=(8, 3),
                             font=self.fonts["ui"], borderwidth=0, relief="flat")
        self.style.map("TButton",
                       foreground=[("active", c["text"]), ("pressed", c["bg_dark"])])

        # Accent Button — rounded filled
        btn_fg = "#ffffff" if self.current_theme == "light" else "#000000"
        self._create_rounded_button_images(c, btn_type="accent",
            bg=c["accent"], border=c["accent"],
            active_bg=c["accent_hover"], active_border=c["accent_hover"],
            pressed_bg=c["bg_hover"], pressed_border=c["border"])
        self.style.configure("Accent.TButton", foreground=btn_fg, padding=(10, 4),
                             font=self.fonts["ui_bold"], borderwidth=0, relief="flat")
        self.style.map("Accent.TButton",
                       foreground=[("active", btn_fg)])

        # Sidebar Buttons — no border (clean navigation look)
        self.style.configure("Sidebar.TButton", background=c["bg_sidebar"],
                             foreground=c["text_dim"], padding=(12, 10),
                             font=self.fonts["ui"], anchor="w", width=18, borderwidth=0,
                             relief="flat")
        self.style.map("Sidebar.TButton",
                       background=[("active", c["bg_sidebar"])],
                       foreground=[("active", c["text"])])

        # Active Sidebar Button
        self.style.configure("ActiveSidebar.TButton", background=c["bg_sidebar"],
                             foreground=c["text"], padding=(12, 10),
                             font=self.fonts["ui_bold"], anchor="w", width=18, borderwidth=0,
                             relief="flat")
        self.style.map("ActiveSidebar.TButton",
                       background=[("active", c["bg_sidebar"])],
                       foreground=[("active", c["text"])])
        
        # Theme Toggle Button — bordered box
        self.style.configure("Theme.TButton", background=c["bg_sidebar"], 
                             foreground=c["text"], font=("Segoe UI Symbol", 12),
                             borderwidth=2, relief="raised",
                             bordercolor=c["border"],
                             lightcolor=c["bg_sidebar"],
                             darkcolor=c["bg_sidebar"])
        self.style.map("Theme.TButton",
                       background=[("active", c["bg_hover"])],
                       bordercolor=[("active", c["accent"])])

        # LabelFrame — rounded border
        self.style.configure("TLabelframe", background=c["bg_dark"],
                             foreground=c["text_dim"], bordercolor=c["border"],
                             lightcolor=c["border"], darkcolor=c["border"],
                             borderwidth=2, relief="groove")
        self.style.configure("TLabelframe.Label", background=c["bg_dark"],
                             foreground=c["text_dim"], font=self.fonts["ui_bold"])

        # Entry — rounded border
        self.style.configure("TEntry", fieldbackground=c["bg_surface"],
                             foreground=c["text"], insertcolor=c["text"],
                             bordercolor=c["border"], lightcolor=c["border"],
                             darkcolor=c["border"], borderwidth=2, relief="groove")

        # Progressbar
        self.style.configure("TProgressbar", background=c["accent"],
                             troughcolor=c["trough"], thickness=6, borderwidth=0)

        # Radiobutton & Checkbutton
        self.style.configure("TRadiobutton", background=c["bg_dark"],
                             foreground=c["text"], font=self.fonts["ui"], indicatorbackground=c["bg_surface"], indicatorcolor=c["bg_surface"])
        self.style.map("TRadiobutton", indicatorbackground=[("selected", c["accent"])])

        # Custom tick-mark checkbox images
        self._create_checkbox_images(c)
        self.style.configure("TCheckbutton", background=c["bg_dark"],
                             foreground=c["text"], font=self.fonts["ui"])

        # Scale
        self.style.configure("TScale", background=c["bg_dark"],
                             troughcolor=c["trough"])

        # Scrollbar
        self.style.configure("TScrollbar", background=c["bg_surface"],
                             troughcolor=c["bg_dark"],
                             arrowcolor=c["text_dim"], borderwidth=0)
        
        # Listbox (standard tkinter widget, needs direct config)
        self._update_listboxes()
        
        # Setup Status Bar
        if hasattr(self, 'status_frame'):
            self.status_frame.config(bg=c["bg_surface"])
            self.status_label.config(bg=c["bg_surface"], fg=c["text_dim"])

        # Setup Separator
        if hasattr(self, 'sidebar_sep'):
           self.sidebar_sep.config(bg=c["border"])

        # Update Logo
        if hasattr(self, 'logo_label'):
            self._load_logo()
            self.logo_label.config(image=self._logo_photo, bg=c["bg_sidebar"])
            self.logo_label.image = self._logo_photo

    def _create_checkbox_images(self, c):
        """Generate custom checkbox indicator images with tick marks using PIL."""
        size = 18
        border_color = c["border"]
        bg_color = c["bg_surface"]
        check_color = c["accent"]

        def hex_to_rgb(h):
            h = h.lstrip('#')
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

        def make_box(bg, draw_tick=False, tick_color=None):
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([0, 0, size-1, size-1], radius=3,
                                    fill=hex_to_rgb(bg) + (255,),
                                    outline=hex_to_rgb(border_color) + (255,),
                                    width=1)
            if draw_tick and tick_color:
                tc = hex_to_rgb(tick_color) + (255,)
                points = [
                    (4, int(size*0.5)), (int(size*0.4), int(size*0.72)),
                    (int(size*0.78), int(size*0.25))
                ]
                draw.line(points, fill=tc, width=2)
            return img

        img_unchecked = make_box(bg_color, False)
        img_checked = make_box(bg_color, True, check_color)

        # On first call, create PhotoImages and register element.
        # On subsequent calls, update existing PhotoImages in-place via paste().
        if not hasattr(self, '_cb_img_unchecked'):
            self._cb_img_unchecked = ImageTk.PhotoImage(img_unchecked)
            self._cb_img_checked = ImageTk.PhotoImage(img_checked)

            self.style.element_create("custom_check", "image", self._cb_img_unchecked,
                                      ("selected", self._cb_img_checked),
                                      width=size, height=size, sticky="")

            self.style.layout("TCheckbutton", [
                ("Checkbutton.padding", {"sticky": "nswe", "children": [
                    ("custom_check", {"side": "left", "sticky": ""}),
                    ("Checkbutton.focus", {"side": "left", "sticky": "", "children": [
                        ("Checkbutton.label", {"sticky": "nswe"})
                    ]})
                ]})
            ])
        else:
            # Update images in-place so the existing element references stay valid
            self._cb_img_unchecked.paste(img_unchecked)
            self._cb_img_checked.paste(img_checked)

    def _create_rounded_button_images(self, c, btn_type, bg, border,
                                       active_bg, active_border,
                                       pressed_bg, pressed_border):
        """Generate rounded rectangle button background images for ttk buttons."""
        # Image size — large enough to slice; ttk will stretch the center
        w, h = 60, 28
        radius = 7

        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

        def make_btn_img(fill_color, outline_color):
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle(
                [1, 1, w - 2, h - 2], radius=radius,
                fill=hex_to_rgb(fill_color) + (255,),
                outline=hex_to_rgb(outline_color) + (255,),
                width=2)
            return img

        # Create state images
        img_normal = make_btn_img(bg, border)
        img_active = make_btn_img(active_bg, active_border)
        img_pressed = make_btn_img(pressed_bg, pressed_border)

        # Store PhotoImage refs to prevent GC
        if not hasattr(self, '_btn_images'):
            self._btn_images = {}

        key_n = f"{btn_type}_normal"
        key_a = f"{btn_type}_active"
        key_p = f"{btn_type}_pressed"
        elem_name = f"rounded_btn_{btn_type}"
        border_slice = (radius + 4, radius + 4, radius + 4, radius + 4)

        if key_n not in self._btn_images:
            # First call — create PhotoImages and register element
            self._btn_images[key_n] = ImageTk.PhotoImage(img_normal)
            self._btn_images[key_a] = ImageTk.PhotoImage(img_active)
            self._btn_images[key_p] = ImageTk.PhotoImage(img_pressed)

            self.style.element_create(elem_name, "image",
                self._btn_images[key_n],
                ("active", "!pressed", self._btn_images[key_a]),
                ("pressed", self._btn_images[key_p]),
                border=border_slice, sticky="nsew")

            style_name = "TButton" if btn_type == "normal" else "Accent.TButton"
            self.style.layout(style_name, [
                (elem_name, {"sticky": "nswe", "children": [
                    ("Button.padding", {"sticky": "nswe", "children": [
                        ("Button.label", {"sticky": "nswe"})
                    ]})
                ]})
            ])
        else:
            # Subsequent calls — update images in-place via paste()
            self._btn_images[key_n].paste(img_normal)
            self._btn_images[key_a].paste(img_active)
            self._btn_images[key_p].paste(img_pressed)

    def _update_listboxes(self):
        """Update standard tk widgets that don't use ttk styles."""
        if not hasattr(self, 'frames'):
            return

        c = self.colors
        
        # Helper to update known widgets
        def update_frame(frame):
            for child in frame.winfo_children():
                try:
                    if isinstance(child, tk.Listbox):
                        child.config(bg=c["bg_surface"], fg=c["text"], 
                                     selectbackground=c["accent"], 
                                     selectforeground="#ffffff" if self.current_theme == "light" else "#000000",
                                     highlightbackground=c["border"], highlightcolor=c["accent"])
                    elif isinstance(child, tk.Canvas):
                        child.config(bg=c["bg_sidebar"], highlightbackground=c["border"]) 
                except: 
                    pass

        for frame in self.frames.values():
            update_frame(frame)

    @staticmethod
    def add_placeholder(entry, placeholder_text, color="#888888"):
        """Add placeholder/hint text to a ttk.Entry that clears on focus."""
        entry._placeholder = placeholder_text
        entry._placeholder_color = color
        entry._has_placeholder = True

        # Get normal foreground
        style = ttk.Style()
        normal_fg = style.lookup("TEntry", "foreground") or "#000000"
        entry._normal_fg = normal_fg

        def show_placeholder():
            entry.delete(0, tk.END)
            entry.insert(0, placeholder_text)
            entry.config(foreground=color)
            entry._has_placeholder = True

        def on_focus_in(e):
            if entry._has_placeholder:
                entry.delete(0, tk.END)
                entry.config(foreground=entry._normal_fg)
                entry._has_placeholder = False

        def on_focus_out(e):
            if not entry.get().strip():
                show_placeholder()

        entry.bind("<FocusIn>", on_focus_in, add="+")
        entry.bind("<FocusOut>", on_focus_out, add="+")
        show_placeholder()

    @staticmethod
    def get_entry_value(entry):
        """Get the actual value of an entry, returning '' if it's showing placeholder."""
        if hasattr(entry, '_has_placeholder') and entry._has_placeholder:
            return ""
        return entry.get()

    def _toggle_theme(self):
        """Switch between light and dark modes."""
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.colors = THEMES[self.current_theme]
        self._apply_theme()
        
        # Update button icon
        btn_text = "☀" if self.current_theme == "dark" else "☾"
        if hasattr(self, 'theme_btn'):
            self.theme_btn.config(text=btn_text)
            
        # Refresh current tool to apply changes to non-ttk widgets (Canvas, Listbox)
        if self.active_frame_id:
            self._show_frame(self.active_frame_id)
        elif self.convert_menu_active:
             self._show_convert_submenu()
        elif self.current_tool:
            self._switch_tool(self.current_tool)

    def _load_logo(self):
        """Load and process logo based on current theme. Preserves internal white background."""
        try:
            base = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            logo_path = None
            for name in ("try.jpg", "logo.ico"):
                candidate = os.path.join(base, name)
                if os.path.exists(candidate):
                    logo_path = candidate
                    break
            
            if not logo_path: return

            logo_img = Image.open(logo_path).convert("RGBA")
            size = 160
            logo_img = logo_img.resize((size, size), Image.LANCZOS)
            
            # Use circular mask to hide only the outer corners
            # This keeps the white background INSIDE the logo while making the OUTSIDE transparent
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size-1, size-1), fill=255)
            
            output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            output.paste(logo_img, (0, 0), mask=mask)
            
            self._logo_photo = ImageTk.PhotoImage(output)
        except Exception:
            pass

    def _build_sidebar(self):
        """Build the left sidebar with tool navigation buttons."""
        self.sidebar = ttk.Frame(self.root, style="Sidebar.TFrame", width=220)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo / App name - TOP LEFT
        logo_frame = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        logo_frame.pack(fill="x", pady=(20, 15), padx=20, anchor="nw")

        self._load_logo()
        if hasattr(self, '_logo_photo'):
            self.logo_label = tk.Label(logo_frame, image=self._logo_photo,
                                      bg=self.colors["bg_sidebar"], bd=0, highlightthickness=0)
            self.logo_label.image = self._logo_photo
            self.logo_label.pack(side="left", padx=(0, 8))

        # Separator
        self.sidebar_sep = tk.Frame(self.sidebar, bg=self.colors["border"], height=1)
        self.sidebar_sep.pack(fill="x", padx=20, pady=(0, 15))

        # Tool buttons
        self.sidebar_buttons = {}
        # Simple Monochrome Labels
        tools = [
            ("convert",  "Convert"),
            ("merge",    "Merge"),
            ("split",    "Split"),
            ("crop",     "Crop"),
            ("resize",   "Resize"),
            ("compress", "Compress"),
            ("reorder",  "Reorder"),
            ("magnifier", "Magnifier"),
        ]

        for tool_id, label in tools:
            btn = ttk.Button(self.sidebar, text=label, style="Sidebar.TButton",
                             command=lambda t=tool_id: self._switch_tool(t))
            btn.pack(fill="x", padx=15, pady=2)
            self.sidebar_buttons[tool_id] = btn

        # Spacer
        spacer = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        spacer.pack(fill="both", expand=True)

        # Bottom Area
        bottom_frame = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        bottom_frame.pack(fill="x", padx=20, pady=20)

        # Theme Toggle
        toggle_char = "☾" # Start in LIGHT mode, so next is DARK (moon)
        self.theme_btn = ttk.Button(bottom_frame, text=toggle_char, style="Theme.TButton", 
                                    width=4, command=self._toggle_theme)
        self.theme_btn.pack(side="left")
        
        # Version
        ttk.Label(bottom_frame, text="v1.2", style="Sidebar.TLabel").pack(side="right")

    def _build_main_area(self):
        """Build the main content area where tool frames will be shown."""
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(side="left", fill="both", expand=True)

    def _build_status_bar(self):
        """Build the bottom status bar."""
        self.status_frame = tk.Frame(self.root, bg=self.colors["bg_surface"], height=30)
        self.status_frame.pack(side="bottom", fill="x", before=self.main_frame)
        self.status_frame.pack_propagate(False)

        self.status_label = tk.Label(self.status_frame, text="Ready",
                                     bg=self.colors["bg_surface"], fg=self.colors["text_dim"],
                                     font=self.fonts["small"], anchor="w", padx=15)
        self.status_label.pack(fill="both", expand=True)

    def _set_status(self, msg):
        """Update status bar (thread-safe)."""
        try:
            self.root.after(0, lambda: self.status_label.config(text=msg))
        except:
            pass

    def _init_tool_frames(self):
        """Create all tool frames."""
        self.frames["convert"] = PdfToImageFrame(self.main_frame, self._set_status)
        self.frames["img2pdf"] = ImageToPdfFrame(self.main_frame, self._set_status)
        self.frames["crop"] = PdfCropFrame(self.main_frame, self._set_status)
        self.frames["split"] = PdfSplitFrame(self.main_frame, self._set_status)
        self.frames["merge"] = PdfMergeFrame(self.main_frame, self._set_status)
        self.frames["resize"] = PdfResizeFrame(self.main_frame, self._set_status)
        self.frames["compress"] = PdfCompressFrame(self.main_frame, self._set_status)
        self.frames["reorder"] = PdfReorderFrame(self.main_frame, self._set_status)
        self.frames["magnifier"] = PdfMagnifierFrame(self.main_frame, self._set_status)

    def _update_standard_widgets_in_frame(self, frame):
        """Recursively update non-ttk widgets in a frame to match current theme."""
        c = self.colors
        for child in frame.winfo_children():
            try:
                if isinstance(child, tk.Listbox):
                    child.config(bg=c["bg_surface"], fg=c["text"], 
                                 selectbackground=c["accent"], 
                                 selectforeground="#ffffff" if self.current_theme == "light" else "#000000",
                                 highlightbackground=c["border"], highlightcolor=c["accent"])
                elif isinstance(child, tk.Canvas):
                    child.config(bg=c["bg_sidebar"]) 
                elif isinstance(child, tk.Label) and not hasattr(child, 'image'):
                    # Standard Labels (not themed by ttk) - except those with images
                    child.config(bg=c["bg_dark"], fg=c["text"])
                
                # Recursive call for children of this widget
                if child.winfo_children():
                    self._update_standard_widgets_in_frame(child)
            except: 
                pass

    def _switch_tool(self, tool_id):
        """Switch the visible tool in the main area."""
        self.convert_menu_active = False
        frame_map = {
            "convert": self._show_convert_submenu,
            "merge": lambda: self._show_frame("merge"),
            "split": lambda: self._show_frame("split"),
            "crop": lambda: self._show_frame("crop"),
            "resize": lambda: self._show_frame("resize"),
            "compress": lambda: self._show_frame("compress"),
            "reorder": lambda: self._show_frame("reorder"),
            "magnifier": lambda: self._show_frame("magnifier"),
        }

        # Update sidebar button styles - Simple Bold/Normal switch
        for bid, btn in self.sidebar_buttons.items():
            if bid == tool_id:
                btn.configure(style="ActiveSidebar.TButton")
            else:
                btn.configure(style="Sidebar.TButton")

        self.current_tool = tool_id
        action = frame_map.get(tool_id)
        if action:
            action()

    def _hide_all_frames(self):
        """Hide all tool frames and sub-widgets."""
        for widget in self.main_frame.winfo_children():
            widget.pack_forget()

    def _show_frame(self, frame_id):
        """Show a specific tool frame."""
        self.active_frame_id = frame_id
        self.convert_menu_active = False
        self._hide_all_frames()
        frame = self.frames[frame_id]
        frame.pack(fill="both", expand=True)
        self._update_standard_widgets_in_frame(frame)

    def _show_convert_submenu(self):
        """Show convert sub-options: PDF→Image and Image→PDF."""
        self.active_frame_id = None
        self.convert_menu_active = True
        self._hide_all_frames()

        container = ttk.Frame(self.main_frame)
        container.pack(fill="both", expand=True)
        
        # Center the content
        center_frame = ttk.Frame(container)
        center_frame.place(relx=0.5, rely=0.5, anchor="center")

        title = ttk.Label(center_frame, text="Select Tool", style="Title.TLabel")
        title.pack(pady=(0, 40))

        btn_frame = ttk.Frame(center_frame)
        btn_frame.pack()

        c = self.colors

        # Helper to create a card
        def create_card(parent, icon, title_text, desc_text, target_id):
            card = tk.Frame(parent, bg=c["bg_surface"], padx=20, pady=15,
                            highlightbackground=c["border"], highlightthickness=1, cursor="hand2")
            card.pack(side="left", padx=15)

        # Larger icon
        tk.Label(card, text=icon, font=("Segoe UI Symbol", 48), bg=c["bg_surface"],
                 fg=c["text"]).pack(pady=(10, 12))
        
        # Larger text labels
        tk.Label(card, text=title_text, font=(self.main_font, 18, "bold"),
                 bg=c["bg_surface"], fg=c["text"]).pack(pady=(0, 4))
        
        tk.Label(card, text=desc_text, font=(self.main_font, 13),
                 bg=c["bg_surface"], fg=c["text_dim"]).pack(pady=(0, 10))

            # Bindings
            def on_click(e): self._show_frame(target_id)
            def on_enter(e): card.config(bg=c["bg_hover"]); [w.config(bg=c["bg_hover"]) for w in card.winfo_children()]
            def on_leave(e): card.config(bg=c["bg_surface"]); [w.config(bg=c["bg_surface"]) for w in card.winfo_children()]

            card.bind("<Button-1>", on_click)
            for w in card.winfo_children(): w.bind("<Button-1>", on_click)
            
            card.bind("<Enter>", on_enter)
            card.bind("<Leave>", on_leave)
            
            return card

        create_card(btn_frame, "⎙", "PDF to Image", "Export pages as JPG / PNG", "convert")
        create_card(btn_frame, "❏", "Image to PDF", "Combine images into one PDF", "img2pdf")

    def run(self):
        """Start the application."""
        self.root.mainloop()


def main():
    app = TWZPdfApp()
    app.run()


if __name__ == "__main__":
    main()
