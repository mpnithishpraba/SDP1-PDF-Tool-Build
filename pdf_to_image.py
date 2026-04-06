"""
PDF to Image Converter Module
Converts PDF pages to JPG/PNG at selectable DPI (150/300/600).
Includes scrollable PDF page preview on the right side.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import fitz  # PyMuPDF
import os
from PIL import Image, ImageTk


def _add_placeholder(entry, text, color="#888888"):
    """Add placeholder hint text to a ttk.Entry."""
    entry._placeholder = text
    entry._placeholder_color = color
    entry._has_placeholder = True
    style = ttk.Style()
    normal_fg = style.lookup("TEntry", "foreground") or "#000000"
    entry._normal_fg = normal_fg

    def show():
        entry.delete(0, tk.END)
        entry.insert(0, text)
        entry.config(foreground=color)
        entry._has_placeholder = True

    def on_in(e):
        if entry._has_placeholder:
            entry.delete(0, tk.END)
            entry.config(foreground=entry._normal_fg)
            entry._has_placeholder = False

    def on_out(e):
        if not entry.get().strip():
            show()

    entry.bind("<FocusIn>", on_in, add="+")
    entry.bind("<FocusOut>", on_out, add="+")
    show()


def _get_entry_value(entry):
    """Get actual value, returning '' if showing placeholder."""
    if hasattr(entry, '_has_placeholder') and entry._has_placeholder:
        return ""
    return entry.get()


class PdfToImageFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.pdf_path = None
        self.page_count = 0
        self._thumb_photos = []      # keep PhotoImage references alive
        self._page_vars = []         # BooleanVar per page for checkbox selection
        self._build_ui()

    def _build_ui(self):
        # Title
        title = ttk.Label(self, text="PDF → Image", style="Title.TLabel")
        title.pack(pady=(10, 5))

        desc = ttk.Label(self, text="Convert PDF pages to high-quality JPG or PNG images",
                         style="Desc.TLabel")
        desc.pack(pady=(0, 10))

        # ── Two-pane container ──────────────────────────────────────────
        panes = ttk.Frame(self)
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        panes.columnconfigure(0, weight=3, uniform="pane")   # left controls
        panes.columnconfigure(1, weight=4, uniform="pane")   # right preview (balanced)
        panes.rowconfigure(0, weight=1)
        panes.grid_propagate(False)

        # ── LEFT PANE (controls) ────────────────────────────────────────
        left = ttk.Frame(panes)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        left.pack_propagate(False)

        # File selection
        file_frame = ttk.Frame(left)
        file_frame.pack(fill="x", pady=5)
        ttk.Label(file_frame, text="PDF File:").pack(side="left")
        self.file_label = ttk.Label(file_frame, text="No file selected", style="Path.TLabel")
        self.file_label.pack(side="left", padx=(10, 10), fill="x", expand=True)
        ttk.Button(file_frame, text="Browse", command=self._browse_pdf).pack(side="right")

        # Options frame
        opts_frame = ttk.LabelFrame(left, text="Options", padding=10)
        opts_frame.pack(fill="x", pady=10)

        # Format
        fmt_frame = ttk.Frame(opts_frame)
        fmt_frame.pack(fill="x", pady=3)
        ttk.Label(fmt_frame, text="Format:").pack(side="left")
        self.format_var = tk.StringVar(value="PNG")
        ttk.Radiobutton(fmt_frame, text="PNG", variable=self.format_var, value="PNG").pack(side="left", padx=(10, 5))
        ttk.Radiobutton(fmt_frame, text="JPG", variable=self.format_var, value="JPG").pack(side="left")

        # DPI
        dpi_frame = ttk.Frame(opts_frame)
        dpi_frame.pack(fill="x", pady=3)
        ttk.Label(dpi_frame, text="DPI:").pack(side="left")
        self.dpi_var = tk.IntVar(value=300)
        for dpi in [150, 300, 600]:
            ttk.Radiobutton(dpi_frame, text=str(dpi), variable=self.dpi_var, value=dpi).pack(side="left", padx=(10, 5))

        # Page range
        range_frame = ttk.Frame(opts_frame)
        range_frame.pack(fill="x", pady=3)
        self.range_var = tk.StringVar(value="all")
        ttk.Radiobutton(range_frame, text="All pages", variable=self.range_var, value="all",
                         command=self._toggle_range).pack(side="left")
        ttk.Radiobutton(range_frame, text="Selected pages", variable=self.range_var, value="selected",
                         command=self._toggle_range).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(range_frame, text="Custom:", variable=self.range_var, value="custom",
                         command=self._toggle_range).pack(side="left", padx=(10, 0))
        self.range_entry = ttk.Entry(range_frame, width=15)
        self.range_entry.pack(side="left", padx=(5, 0))
        _add_placeholder(self.range_entry, "1-5,8,12")
        self.range_entry.config(state="disabled")

        # Select / Deselect buttons for checkbox mode
        sel_frame = ttk.Frame(opts_frame)
        sel_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(sel_frame, text="Select All", command=self._select_all).pack(side="left", padx=2)
        ttk.Button(sel_frame, text="Deselect All", command=self._deselect_all).pack(side="left", padx=2)

        self.page_info_label = ttk.Label(opts_frame, text="", style="Desc.TLabel")
        self.page_info_label.pack(fill="x", pady=(5, 0))

        # Progress
        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 5))

        self.progress_label = ttk.Label(left, text="", style="Desc.TLabel")
        self.progress_label.pack()

        # Convert button
        ttk.Button(left, text="Convert to Images", style="Accent.TButton",
                   command=self._start_convert).pack(pady=15)

        # ── RIGHT PANE (preview) ────────────────────────────────────────
        right = ttk.Frame(panes)
        right.grid(row=0, column=1, sticky="nsew")

        # Toolbar row
        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(0, 5))
        self._preview_title = ttk.Label(toolbar, text="PDF Preview",
                                         style="Path.TLabel")
        self._preview_title.pack(side="left")
        self._preview_info = ttk.Label(toolbar, text="", style="Desc.TLabel")
        self._preview_info.pack(side="right")

        # Scrollable canvas for page thumbnails
        preview_container = ttk.Frame(right)
        preview_container.pack(fill="both", expand=True)

        self.preview_canvas = tk.Canvas(preview_container,
                                        highlightthickness=0, bd=0)
        self.v_scroll = ttk.Scrollbar(preview_container, orient="vertical",
                                      command=self.preview_canvas.yview)
        self.preview_canvas.configure(yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.preview_canvas.pack(side="left", fill="both", expand=True)
        
        # Placeholder text overlaid on preview
        self._placeholder = ttk.Label(
            preview_container,
            text="Load a PDF to see page previews",
            style="Desc.TLabel")
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # Inner frame inside canvas
        self.thumb_frame = ttk.Frame(self.preview_canvas)
        self._canvas_win = self.preview_canvas.create_window(
            (0, 0), window=self.thumb_frame, anchor="n")

        self.thumb_frame.bind("<Configure>", self._on_thumb_configure)
        self.preview_canvas.bind("<Configure>", self._on_canvas_resize)
        self.preview_canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    # ── Canvas helpers ──────────────────────────────────────────────────
    def _on_thumb_configure(self, _event=None):
        self.preview_canvas.configure(
            scrollregion=self.preview_canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        # Update window width and keep it centered at relx=0.5
        self.preview_canvas.itemconfigure(self._canvas_win, width=event.width)
        self.preview_canvas.coords(self._canvas_win, event.width // 2, 0)

    def _on_mousewheel(self, event):
        widget = event.widget
        try:
            if self.preview_canvas.winfo_containing(event.x_root, event.y_root) \
                    in (self.preview_canvas, self.thumb_frame) or \
                    str(widget) == str(self.preview_canvas) or \
                    str(widget).startswith(str(self.thumb_frame)):
                self.preview_canvas.yview_scroll(
                    int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    # ── Select / Deselect ───────────────────────────────────────────────
    def _select_all(self):
        for var in self._page_vars:
            var.set(True)

    def _deselect_all(self):
        for var in self._page_vars:
            var.set(False)

    # ── Toggle range ────────────────────────────────────────────────────
    def _toggle_range(self):
        if self.range_var.get() == "custom":
            self.range_entry.config(state="normal")
        else:
            self.range_entry.config(state="disabled")

    # ── Browse & render preview ─────────────────────────────────────────
    def _browse_pdf(self):
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if path:
            self.pdf_path = path
            self.file_label.config(text=os.path.basename(path))
            try:
                doc = fitz.open(path)
                self.page_count = len(doc)
                self.page_info_label.config(text=f"Total pages: {self.page_count}")
                doc.close()
                # Render preview thumbnails
                self._render_preview(path)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot open PDF: {e}")
                self.pdf_path = None

    def _render_preview(self, pdf_path):
        """Render all pages as thumbnails in the preview panel."""
        # Hide placeholder
        self._placeholder.place_forget()
        
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self._thumb_photos.clear()
        self._page_vars.clear()

        loading = ttk.Label(self.thumb_frame, text="Rendering pages…",
                            style="Desc.TLabel")
        loading.grid(row=0, column=0, padx=40, pady=40)

        size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        name = os.path.basename(pdf_path)
        self._preview_title.config(text="PDF Preview")
        self._preview_info.config(
            text=f"{name}  •  {self.page_count} pages  •  {size_mb:.1f} MB")

        threading.Thread(target=self._render_worker,
                         args=(pdf_path,), daemon=True).start()

    def _render_worker(self, pdf_path):
        """Background worker: render each page to a PIL image."""
        try:
            doc = fitz.open(pdf_path)
            images = []
            thumb_width = 300  # Increased to 300px to fill space and improve readability
            for i in range(len(doc)):
                page = doc[i]
                scale = thumb_width / page.rect.width
                mat = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)
            doc.close()

            self.after(0, lambda: self._populate_thumbs(images))
        except Exception as e:
            self.after(0, lambda: self._preview_info.config(
                text=f"Cannot preview: {e}"))

    def _populate_thumbs(self, images):
        """Place page thumbnails with checkboxes in a grid (main thread)."""
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self._thumb_photos.clear()
        self._page_vars.clear()

        cols = 3  # Force exactly 3 columns as requested
        for c in range(cols):
            self.thumb_frame.columnconfigure(c, weight=1)



        for idx, img in enumerate(images):
            photo = ImageTk.PhotoImage(img)
            self._thumb_photos.append(photo)

            row, col = divmod(idx, cols)

            # Card frame for each page
            card = ttk.Frame(self.thumb_frame, style="Surface.TFrame")
            card.grid(row=row, column=col, padx=2, pady=2, sticky="n")

            # Image label
            img_label = tk.Label(card, image=photo, bd=1, relief="solid",
                                 cursor="hand2")
            img_label.pack(padx=3, pady=(3, 1))

            # Checkbox + page number
            var = tk.BooleanVar(value=True)
            self._page_vars.append(var)

            chk_frame = ttk.Frame(card, style="Surface.TFrame")
            chk_frame.pack(fill="x", padx=3, pady=(0, 3))
            cb = ttk.Checkbutton(chk_frame, variable=var,
                                 text=f"Page {idx + 1}",
                                 style="TCheckbutton")
            cb.pack(side="left")

            # Clicking the image toggles the checkbox
            img_label.bind("<Button-1>",
                           lambda e, v=var: v.set(not v.get()))

        self.preview_canvas.yview_moveto(0)
        self._on_thumb_configure()

    # ── Parse ranges ────────────────────────────────────────────────────
    def _parse_ranges(self, text, max_page):
        pages = []
        for part in text.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                a, b = int(a.strip()), int(b.strip())
                for p in range(a, b + 1):
                    if 1 <= p <= max_page:
                        pages.append(p - 1)
            else:
                p = int(part)
                if 1 <= p <= max_page:
                    pages.append(p - 1)
        return sorted(set(pages))

    # ── Convert ─────────────────────────────────────────────────────────
    def _start_convert(self):
        if not self.pdf_path:
            messagebox.showwarning("No File", "Please select a PDF file first.")
            return

        out_dir = filedialog.askdirectory(title="Select Output Folder")
        if not out_dir:
            return

        threading.Thread(target=self._do_convert, args=(out_dir,), daemon=True).start()

    def _do_convert(self, out_dir):
        try:
            doc = fitz.open(self.pdf_path)
            total = len(doc)

            mode = self.range_var.get()
            if mode == "all":
                pages = list(range(total))
            elif mode == "selected":
                # Use checkbox selections from preview
                pages = [i for i, var in enumerate(self._page_vars) if var.get()]
            else:
                pages = self._parse_ranges(_get_entry_value(self.range_entry), total)

            if not pages:
                self.after(0, lambda: messagebox.showwarning("No Pages", "No valid pages in range."))
                doc.close()
                return

            dpi = self.dpi_var.get()
            fmt = self.format_var.get().lower()
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)

            base_name = os.path.splitext(os.path.basename(self.pdf_path))[0]

            self.after(0, lambda: self.progress.config(maximum=len(pages), value=0))
            self.status_callback(f"Converting {len(pages)} pages at {dpi} DPI...")

            for i, page_num in enumerate(pages):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

                out_file = os.path.join(out_dir, f"{base_name}_page{page_num + 1}.{fmt}")

                if fmt == "jpg":
                    pix.save(out_file, jpg_quality=95)
                else:
                    pix.save(out_file)

                self.after(0, lambda v=i + 1: self.progress.config(value=v))
                self.after(0, lambda v=i + 1, t=len(pages): self.progress_label.config(
                    text=f"Page {v}/{t}"))

            doc.close()
            self.status_callback(f"Converted {len(pages)} pages to {fmt.upper()}")
            self.after(0, lambda: messagebox.showinfo("Done",
                                                       f"Exported {len(pages)} images to:\n{out_dir}"))
            self.after(0, lambda: self.progress_label.config(text="Done!"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
