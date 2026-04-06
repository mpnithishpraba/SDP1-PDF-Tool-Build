"""
PDF Crop Tool Module
Visual crop UI with drag selection, zoom, scrollbars, preview confirm,
and save as image/PDF options.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import fitz  # PyMuPDF
import os


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


class PdfCropFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.pdf_path = None
        self.doc = None
        self.page_count = 0
        self.current_page = 0
        self.preview_scale = 1.0
        self.zoom_level = 1.0
        self.crop_rect = None         # (x1, y1, x2, y2) in canvas coords
        self.page_crops = {}          # {page_index: (x1, y1, x2, y2)}
        self.drag_start = None
        self._rect_id = None
        self._tk_img = None
        self._preview_mode = False  # True when showing cropped preview
        self._build_ui()

    def _build_ui(self):
        title = ttk.Label(self, text="PDF Crop Tool", style="Title.TLabel")
        title.pack(pady=(10, 5))

        desc = ttk.Label(self, text="Draw a crop rectangle on the page preview",
                         style="Desc.TLabel")
        desc.pack(pady=(0, 10))

        # ── Two-pane container ──────────────────────────────────────────
        panes = ttk.Frame(self)
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        panes.columnconfigure(0, weight=3, uniform="pane")   # left controls
        panes.columnconfigure(1, weight=4, uniform="pane")   # right preview
        panes.rowconfigure(0, weight=1)
        panes.grid_propagate(False)

        # ── LEFT PANE (controls) ────────────────────────────────────────
        left = ttk.Frame(panes)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.pack_propagate(False)

        # File selection
        file_frame = ttk.Frame(left)
        file_frame.pack(fill="x", pady=5)
        ttk.Label(file_frame, text="PDF File:").pack(side="left")
        self.file_label = ttk.Label(file_frame, text="No file selected", style="Path.TLabel")
        self.file_label.pack(side="left", padx=(10, 5), fill="x", expand=True)
        ttk.Button(file_frame, text="Browse", command=self._browse_pdf).pack(side="right")

        # ── Apply options ────────────────────────────────────────────────
        apply_frame = ttk.LabelFrame(left, text="Apply Crop To", padding=10)
        apply_frame.pack(fill="x", pady=5)

        self.apply_var = tk.StringVar(value="current")
        ttk.Radiobutton(apply_frame, text="Current page only",
                         variable=self.apply_var, value="current").pack(anchor="w")
        ttk.Radiobutton(apply_frame, text="All pages",
                         variable=self.apply_var, value="all").pack(anchor="w")
        ttk.Radiobutton(apply_frame, text="Pages with custom crops",
                         variable=self.apply_var, value="custom").pack(anchor="w")

        fr = ttk.Frame(apply_frame)
        fr.pack(anchor="w")
        ttk.Radiobutton(fr, text="Page range:",
                         variable=self.apply_var, value="range").pack(side="left")
        self.range_entry = ttk.Entry(fr, width=15)
        self.range_entry.pack(side="left", padx=(5, 0))
        _add_placeholder(self.range_entry, "1-5")

        # ── Image export options ─────────────────────────────────────────
        img_frame = ttk.LabelFrame(left, text="Image Export Settings", padding=10)
        img_frame.pack(fill="x", pady=5)

        fmt_row = ttk.Frame(img_frame)
        fmt_row.pack(fill="x", pady=(0, 5))
        ttk.Label(fmt_row, text="Format:").pack(side="left")
        self.img_format_var = tk.StringVar(value="PNG")
        fmt_combo = ttk.Combobox(fmt_row, textvariable=self.img_format_var,
                                 values=["PNG", "JPG"], state="readonly", width=8)
        fmt_combo.pack(side="left", padx=(8, 0))
        fmt_combo.bind("<<ComboboxSelected>>", self._on_format_change)

        self.quality_row = ttk.Frame(img_frame)
        self.quality_row.pack(fill="x")
        ttk.Label(self.quality_row, text="Quality:").pack(side="left")
        self.quality_var = tk.IntVar(value=90)
        self.quality_scale = ttk.Scale(self.quality_row, from_=1, to=100,
                                       variable=self.quality_var, orient="horizontal")
        self.quality_scale.pack(side="left", fill="x", expand=True, padx=(8, 8))
        self.quality_val_label = ttk.Label(self.quality_row, text="90", width=4)
        self.quality_val_label.pack(side="left")
        self.quality_scale.configure(command=self._on_quality_slide)
        # Hide quality row initially (PNG doesn't need it)
        self.quality_row.pack_forget()

        # ── Action buttons ───────────────────────────────────────────────
        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x", pady=10)

        self.crop_count_label = ttk.Label(btn_frame, text="0 pages with custom crops",
                                          style="Desc.TLabel")
        self.crop_count_label.pack(pady=(0, 5))

        ttk.Button(btn_frame, text="Preview Crop", style="Accent.TButton",
                   command=self._show_crop_preview).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Save as PDF", style="Accent.TButton",
                   command=self._apply_crop_pdf).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Save as Image", style="Accent.TButton",
                   command=self._save_crop_image).pack(fill="x", pady=2)
        
        clear_opts = ttk.Frame(btn_frame)
        clear_opts.pack(fill="x", pady=(10, 0))
        ttk.Button(clear_opts, text="Clear This Page",
                   command=self._clear_page_crop).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(clear_opts, text="Clear All Pages",
                   command=self._clear_all_crops).pack(side="left", fill="x", expand=True, padx=(2, 0))

        # ── RIGHT PANE (preview) ────────────────────────────────────────
        right = ttk.Frame(panes)
        right.grid(row=0, column=1, sticky="nsew")
        right.pack_propagate(False)

        # ── Preview Toolbar (Title + Navigation + Zoom) ──────────────────
        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(0, 5))
        
        ttk.Label(toolbar, text="Page Preview", style="Path.TLabel").pack(side="left")
        
        # Zoom controls (top right)
        zoom_frame = ttk.Frame(toolbar)
        zoom_frame.pack(side="right")
        ttk.Button(zoom_frame, text="−", width=3, command=self._zoom_out).pack(side="left", padx=2)
        self.zoom_label = ttk.Label(zoom_frame, text="100%", width=6, anchor="center")
        self.zoom_label.pack(side="left", padx=2)
        ttk.Button(zoom_frame, text="+", width=3, command=self._zoom_in).pack(side="left", padx=2)
        ttk.Button(zoom_frame, text="Reset", command=self._zoom_reset).pack(side="left", padx=(6, 0))

        # ── Page navigation row ──────────────────────────────────────────
        nav_row = ttk.Frame(right)
        nav_row.pack(fill="x", pady=3)
        ttk.Button(nav_row, text="◄ Prev", command=self._prev_page).pack(side="left")
        self.page_label = ttk.Label(nav_row, text="Page 0/0")
        self.page_label.pack(side="left", padx=15)
        ttk.Button(nav_row, text="Next ►", command=self._next_page).pack(side="left")

        # ── Preview Backdrop (Canvas) ───────────────────────────────────
        self.preview_container = ttk.Frame(right)
        self.preview_container.pack(fill="both", expand=True)

        # ── Preview confirm bar (initially hidden) ──────────────────────
        self.preview_bar = ttk.Frame(self.preview_container)
        ttk.Button(self.preview_bar, text="◄ Back to Full Page",
                   command=self._exit_preview).pack(side="left", padx=5)
        ttk.Label(self.preview_bar, text="Crop Preview — confirm before saving",
                  foreground="#89b4fa").pack(side="left", padx=10)

        canvas_outer = ttk.Frame(self.preview_container)
        canvas_outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_outer, bg="#181825", highlightthickness=0,
                                cursor="crosshair", takefocus=1)
        self.v_scroll = ttk.Scrollbar(canvas_outer, orient="vertical", command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(canvas_outer, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set,
                               xscrollcommand=self.h_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")
        canvas_outer.grid_rowconfigure(0, weight=1)
        canvas_outer.grid_columnconfigure(0, weight=1)

        # Placeholder text overlaid on preview
        self._placeholder = ttk.Label(
            canvas_outer,
            text="Load a PDF to see preview",
            style="Desc.TLabel")
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        
        # Keyboard shortcuts (canvas needs focus)
        self.canvas.bind("<Left>", lambda e: self._prev_page())
        self.canvas.bind("<Right>", lambda e: self._next_page())
        self.canvas.bind("<FocusIn>", lambda e: self.canvas.config(highlightthickness=1, highlightcolor="#89b4fa"))
        self.canvas.bind("<FocusOut>", lambda e: self.canvas.config(highlightthickness=0))
        
        # Enable focus on click
        self.canvas.bind("<Button-1>", lambda e: self.canvas.focus_set(), add="+")

    # ── File handling ────────────────────────────────────────────────────

    def _browse_pdf(self):
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf")]
        )
        if path:
            try:
                if self.doc:
                    self.doc.close()
                self.doc = fitz.open(path)
                self.pdf_path = path
                self.page_count = len(self.doc)
                self.current_page = 0
                self.zoom_level = 1.0
                self.page_crops = {}
                self.crop_rect = None
                self._preview_mode = False
                self.file_label.config(text=os.path.basename(path))
                self._update_crop_count_label()
                self._render_page()
            except Exception as e:
                messagebox.showerror("Error", f"Cannot open PDF: {e}")

    # ── Rendering ────────────────────────────────────────────────────────

    def _render_page(self):
        if not self.doc or self.page_count == 0:
            return
        
        # Hide placeholder
        self._placeholder.place_forget()
        
        page = self.doc[self.current_page]
        self.page_label.config(text=f"Page {self.current_page + 1}/{self.page_count}")
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")

        if self._preview_mode:
            self._preview_mode = False
            self.preview_bar.pack_forget()

        # Get canvas size for base-scale calculation
        self.canvas.update_idletasks()
        cw = max(self.canvas.winfo_width(), 300)
        ch = max(self.canvas.winfo_height(), 400)

        pr = page.rect
        sx = cw / pr.width
        sy = ch / pr.height
        base_scale = min(sx, sy, 2.0)
        self.preview_scale = base_scale * self.zoom_level

        mat = fitz.Matrix(self.preview_scale, self.preview_scale)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

        self._set_canvas_image(pix)

        # Re-render existing crop ONLY if it exists for this page (no persistence across new pages)
        self.crop_rect = self.page_crops.get(self.current_page)

        if self.crop_rect:
            self._draw_crop_rect()
        else:
            if self._rect_id:
                self.canvas.delete(self._rect_id)
                self._rect_id = None

    # _set_canvas_image remains similar, just making sure it doesn't delete "all" 
    # if we want to be safe, but actually calling _draw_crop_rect AFTER _set_canvas_image 
    # as done in _render_page is the correct fix.

    def _set_canvas_image(self, pix):
        """Put a PyMuPDF Pixmap onto the canvas and update scrollregion."""
        try:
            from PIL import Image, ImageTk
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            self._tk_img = ImageTk.PhotoImage(img)
        except ImportError:
            mode = "P6"
            header = f"{mode}\n{pix.width} {pix.height}\n255\n".encode()
            ppm_data = header + pix.samples
            self._tk_img = tk.PhotoImage(data=ppm_data)

        self.canvas.delete("all")

        # Center the image on the canvas
        self.canvas.update_idletasks()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        # Use the larger of canvas or image size for scrollregion
        sr_w = max(pix.width, cw)
        sr_h = max(pix.height, ch)
        self.canvas.configure(scrollregion=(0, 0, sr_w, sr_h))

        # Place image at the center of the scrollregion
        cx = sr_w / 2
        cy = sr_h / 2
        self._img_offset_x = cx - pix.width / 2
        self._img_offset_y = cy - pix.height / 2
        self.canvas.create_image(cx, cy, anchor="center", image=self._tk_img)

    # ── Page navigation ──────────────────────────────────────────────────

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render_page()

    def _next_page(self):
        if self.current_page < self.page_count - 1:
            self.current_page += 1
            self._render_page()

    # ── Zoom ─────────────────────────────────────────────────────────────

    def _zoom_in(self):
        if self.zoom_level < 5.0:
            self.zoom_level = round(self.zoom_level + 0.25, 2)
            self._render_page()

    def _zoom_out(self):
        if self.zoom_level > 0.25:
            self.zoom_level = round(self.zoom_level - 0.25, 2)
            self._render_page()

    def _zoom_reset(self):
        self.zoom_level = 1.0
        self._render_page()

    # ── Scroll events ────────────────────────────────────────────────────

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_ctrl_mousewheel(self, event):
        if event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _on_shift_mousewheel(self, event):
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── Crop rectangle drawing ───────────────────────────────────────────

    def _on_press(self, event):
        if self._preview_mode:
            return
        # Convert to canvas coords (accounts for scroll position)
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        self.drag_start = (cx, cy)
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None

    def _on_drag(self, event):
        if self._preview_mode:
            return
        if self.drag_start:
            if self._rect_id:
                self.canvas.delete(self._rect_id)
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            x1, y1 = self.drag_start
            self._rect_id = self.canvas.create_rectangle(
                x1, y1, cx, cy,
                outline="red", width=2, dash=(4, 4)
            )

    def _on_release(self, event):
        if self._preview_mode:
            return
        if self.drag_start:
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            x1, y1 = self.drag_start
            # Normalize
            self.crop_rect = (min(x1, cx), min(y1, cy), max(x1, cx), max(y1, cy))
            # Save crop for this page
            self.page_crops[self.current_page] = self.crop_rect
            self._update_crop_count_label()
            self.drag_start = None

    def _draw_crop_rect(self):
        """Draw the current crop_rect on the canvas."""
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        if self.crop_rect:
            x1, y1, x2, y2 = self.crop_rect
            self._rect_id = self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="red", width=2, dash=(4, 4)
            )

    def _update_crop_count_label(self):
        count = len(self.page_crops)
        self.crop_count_label.config(text=f"{count} pages with custom crops")

    def _clear_page_crop(self):
        if self.current_page in self.page_crops:
            del self.page_crops[self.current_page]
            self._update_crop_count_label()
            self.status_callback(f"Crop removed for page {self.current_page + 1}")
        # Note: we keep the self.crop_rect visible as a template unless it's cleared all

    def _clear_all_crops(self):
        self.page_crops = {}
        self.crop_rect = None
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None
        self._update_crop_count_label()
        self.status_callback("All page crops cleared")

    def _canvas_to_pdf_rect(self, canvas_rect, p_idx=None):
        """Convert a canvas rect (x1, y1, x2, y2) to a PDF Rect, clipped to page."""
        if p_idx is None:
            p_idx = self.current_page
        
        page = self.doc[p_idx]
        pr = page.rect
        
        # Need to re-calculate scale/offset for the specific page if it's different
        self.canvas.update_idletasks()
        cw = max(self.canvas.winfo_width(), 300)
        ch = max(self.canvas.winfo_height(), 400)
        
        sx = cw / pr.width
        sy = ch / pr.height
        base_scale = min(sx, sy, 2.0)
        s = base_scale * self.zoom_level
        
        # Matrix/Pixmap dimensions for offset calculation
        mat = fitz.Matrix(s, s)
        pix_w = int(pr.width * s)
        pix_h = int(pr.height * s)
        
        # Centering offsets (same logic as in _set_canvas_image)
        # Use full scrollregion space if known, else assume center relative to content size
        sr_w = max(pix_w, cw)
        sr_h = max(pix_h, ch)
        ox = sr_w / 2 - pix_w / 2
        oy = sr_h / 2 - pix_h / 2

        cx1, cy1, cx2, cy2 = canvas_rect
        pdf_rect = fitz.Rect((cx1 - ox) / s, (cy1 - oy) / s,
                             (cx2 - ox) / s, (cy2 - oy) / s)
        
        # IMPORTANT: Clip to Page Rect and normalize
        pdf_rect.normalize()
        return pdf_rect.intersect(pr)

    def _crop_to_pdf_rect(self, p_idx=None):
        """Convert current canvas crop rect to PDF rect for specific page."""
        if not self.crop_rect:
            return None
        return self._canvas_to_pdf_rect(self.crop_rect, p_idx)

    # ── Crop Preview ─────────────────────────────────────────────────────

    def _show_crop_preview(self):
        if not self.doc:
            messagebox.showwarning("No File", "Please open a PDF first.")
            return
        if not self.crop_rect:
            messagebox.showwarning("No Selection", "Please draw a crop rectangle on the preview.")
            return

        page = self.doc[self.current_page]
        # Use current page-aware clip
        clip = self._crop_to_pdf_rect(self.current_page)
        
        if clip.is_empty:
             messagebox.showwarning("Invalid Selection", "The crop rectangle is outside the page area.")
             return

        # Render only the clipped area at current zoom
        mat = fitz.Matrix(self.preview_scale, self.preview_scale)
        pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csRGB)

        self._set_canvas_image(pix)
        self._preview_mode = True
        self.preview_bar.pack(side="top", fill="x", pady=(0, 5))

    def _exit_preview(self):
        self._preview_mode = False
        self.preview_bar.pack_forget()
        self._render_page()

    # ── Range parser ─────────────────────────────────────────────────────

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

    # ── Save as PDF (existing behaviour) ─────────────────────────────────

    def _apply_crop_pdf(self):
        if not self.doc:
            messagebox.showwarning("No File", "Please open a PDF first.")
            return
        if not self.crop_rect:
            messagebox.showwarning("No Selection", "Please draw a crop rectangle on the preview.")
            return

        out_path = filedialog.asksaveasfilename(
            title="Save Cropped PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")]
        )
        if not out_path:
            return

        threading.Thread(target=self._do_crop_pdf, args=(out_path,), daemon=True).start()

    def _do_crop_pdf(self, out_path):
        try:
            pages = self._get_target_pages()
            
            new_doc = fitz.open(self.pdf_path)
            self.status_callback(f"Cropping {len(pages)} pages...")

            for pg_num in pages:
                page = new_doc[pg_num]
                # Priority: 1. Per-page custom crop, 2. Global template crop
                target_canvas_rect = self.page_crops.get(pg_num) or self.crop_rect
                
                if target_canvas_rect:
                    pdf_rect = self._canvas_to_pdf_rect(target_canvas_rect, pg_num)
                    if not pdf_rect.is_empty:
                        page.set_cropbox(pdf_rect)

            new_doc.save(out_path, garbage=4, deflate=True)
            new_doc.close()

            self.status_callback(f"Cropped {len(pages)} pages saved")
            self.after(0, lambda: messagebox.showinfo("Done", f"Cropped PDF saved to:\n{out_path}"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    # ── Save as Image ────────────────────────────────────────────────────

    def _on_format_change(self, event=None):
        if self.img_format_var.get() == "JPG":
            self.quality_row.pack(fill="x")
        else:
            self.quality_row.pack_forget()

    def _on_quality_slide(self, val):
        self.quality_val_label.config(text=str(int(float(val))))

    def _save_crop_image(self):
        if not self.doc:
            messagebox.showwarning("No File", "Please open a PDF first.")
            return
        if not self.crop_rect:
            messagebox.showwarning("No Selection", "Please draw a crop rectangle on the preview.")
            return

        fmt = self.img_format_var.get()
        if fmt == "PNG":
            ext, ftype = ".png", [("PNG Image", "*.png")]
        else:
            ext, ftype = ".jpg", [("JPEG Image", "*.jpg")]

        out_path = filedialog.asksaveasfilename(
            title="Save Cropped Image",
            defaultextension=ext,
            filetypes=ftype + [("All files", "*.*")]
        )
        if not out_path:
            return

        quality = self.quality_var.get()
        threading.Thread(target=self._do_crop_image,
                         args=(out_path, fmt, quality), daemon=True).start()

    def _do_crop_image(self, out_path, fmt, quality):
        try:
            from PIL import Image

            default_pdf_rect = self._crop_to_pdf_rect()
            pages_to_export = self._get_target_pages()

            self.status_callback(f"Exporting {len(pages_to_export)} cropped page(s) as {fmt}...")

            save_kwargs = {}
            if fmt == "JPG":
                save_kwargs = {"quality": quality, "optimize": True}

            def save_img(img, path):
                if fmt == "JPG":
                    img = img.convert("RGB")  # ensure no alpha for JPEG
                img.save(path, **save_kwargs)

            # Define getter for per-page or current template clip
            def get_clip(p_idx):
                target_rect = self.page_crops.get(p_idx) or self.crop_rect
                if target_rect:
                    return self._canvas_to_pdf_rect(target_rect, p_idx)
                return None

            if len(pages_to_export) == 1:
                pg_num = pages_to_export[0]
                page = self.doc[pg_num]
                mat = fitz.Matrix(2.0, 2.0)
                clip = get_clip(pg_num)
                pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csRGB)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                save_img(img, out_path)
            else:
                base, ext = os.path.splitext(out_path)
                for i, pg_num in enumerate(pages_to_export):
                    page = self.doc[pg_num]
                    mat = fitz.Matrix(2.0, 2.0)
                    pix = page.get_pixmap(matrix=mat, clip=get_clip(pg_num), colorspace=fitz.csRGB)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    save_img(img, f"{base}_page{pg_num + 1}{ext}")

            self.status_callback(f"Cropped image(s) saved")
            self.after(0, lambda: messagebox.showinfo("Done", f"Cropped image saved to:\n{out_path}"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    def _get_target_pages(self):
        """Return list of page indices based on current apply_var selection."""
        val = self.apply_var.get()
        if val == "current":
            return [self.current_page]
        elif val == "all":
            return list(range(self.page_count))
        elif val == "custom":
            return sorted(self.page_crops.keys())
        else:
            return self._parse_ranges(_get_entry_value(self.range_entry), self.page_count)
