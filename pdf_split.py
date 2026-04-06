"""
PDF Splitter Module
Lossless page extraction with smart size reduction.
Includes visual PDF preview with per-page checkbox selection.
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


class PdfSplitFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.pdf_path = None
        self.page_count = 0
        self._thumb_photos = []      # keep PhotoImage references alive
        self._page_vars = []          # BooleanVar per page
        self._thumb_widgets = []      # references to canvas window items
        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Top title row (spans full width)
        title = ttk.Label(self, text="PDF Splitter", style="Title.TLabel")
        title.pack(pady=(10, 2))

        desc = ttk.Label(self, text="Extract pages losslessly with smart size optimization",
                         style="Desc.TLabel")
        desc.pack(pady=(0, 10))

        # ── Two-pane container ──────────────────────────────────────────
        panes = ttk.Frame(self)
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        panes.columnconfigure(0, weight=3, uniform="pane")   # left controls
        panes.columnconfigure(1, weight=4, uniform="pane")   # right preview (balanced weights)
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
        self.file_label = ttk.Label(file_frame, text="No file selected",
                                    style="Path.TLabel")
        self.file_label.pack(side="left", padx=(10, 10), fill="x", expand=True)
        ttk.Button(file_frame, text="Browse",
                   command=self._browse_pdf).pack(side="right")

        self.info_label = ttk.Label(left, text="", style="Desc.TLabel")
        self.info_label.pack(anchor="w")

        # Split mode
        mode_frame = ttk.LabelFrame(left, text="Split Mode", padding=10)
        mode_frame.pack(fill="x", pady=10)

        self.mode_var = tk.StringVar(value="selected")

        # Selected pages (NEW – default)
        ttk.Radiobutton(mode_frame, text="Selected pages (use checkboxes →)",
                        variable=self.mode_var,
                        value="selected").pack(anchor="w", pady=3)

        # Range
        r1 = ttk.Frame(mode_frame)
        r1.pack(fill="x", pady=3)
        ttk.Radiobutton(r1, text="Page range:", variable=self.mode_var,
                        value="range").pack(side="left")
        self.range_entry = ttk.Entry(r1, width=20)
        self.range_entry.pack(side="left", padx=(10, 0))
        _add_placeholder(self.range_entry, "2-10")

        ttk.Label(mode_frame, text="e.g.  2-10  |  1,3,5-8  |  5",
                  style="Desc.TLabel").pack(anchor="w", pady=(0, 5))

        # Each page
        ttk.Radiobutton(mode_frame, text="Each page as separate PDF",
                        variable=self.mode_var,
                        value="each").pack(anchor="w", pady=3)

        # Multiple ranges
        r3 = ttk.Frame(mode_frame)
        r3.pack(fill="x", pady=3)
        ttk.Radiobutton(r3, text="Multi-range (;):",
                        variable=self.mode_var,
                        value="multi").pack(side="left")
        self.multi_entry = ttk.Entry(r3, width=20)
        self.multi_entry.pack(side="left", padx=(10, 0))
        _add_placeholder(self.multi_entry, "1-3; 5-8; 10-15")

        # Progress
        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(15, 5))

        self.progress_label = ttk.Label(left, text="", style="Desc.TLabel")
        self.progress_label.pack()

        # Split button
        ttk.Button(left, text="Split PDF", style="Accent.TButton",
                   command=self._start_split).pack(pady=15)

        # ── RIGHT PANE (preview) ────────────────────────────────────────
        right = ttk.Frame(panes)
        right.grid(row=0, column=1, sticky="nsew")

        # Toolbar row
        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(0, 5))
        ttk.Label(toolbar, text="PDF Preview",
                  style="Path.TLabel").pack(side="left")
        ttk.Button(toolbar, text="Select All",
                   command=self._select_all).pack(side="right", padx=(4, 0))
        ttk.Button(toolbar, text="Deselect All",
                   command=self._deselect_all).pack(side="right")

        # Scrollable canvas for thumbnails
        preview_container = ttk.Frame(right)
        preview_container.pack(fill="both", expand=True)

        self.preview_canvas = tk.Canvas(preview_container,
                                        highlightthickness=0, bd=0)
        self.v_scroll = ttk.Scrollbar(preview_container, orient="vertical",
                                      command=self.preview_canvas.yview)
        self.preview_canvas.configure(yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.preview_canvas.pack(side="left", fill="both", expand=True)

        # Inner frame inside canvas
        self.thumb_frame = ttk.Frame(self.preview_canvas)
        self._canvas_win = self.preview_canvas.create_window(
            (0, 0), window=self.thumb_frame, anchor="n")

        self.thumb_frame.bind("<Configure>", self._on_thumb_configure)
        self.preview_canvas.bind("<Configure>", self._on_canvas_resize)
        # Mouse-wheel scroll
        self.preview_canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

        # Placeholder text overlaid on canvas (fixed, not scrollable)
        self._placeholder = ttk.Label(
            preview_container,
            text="Load PDF to see preview",
            style="Desc.TLabel")
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # ── Canvas helpers ──────────────────────────────────────────────────
    def _on_thumb_configure(self, _event=None):
        self.preview_canvas.configure(
            scrollregion=self.preview_canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        # Update window width and keep it centered at relx=0.5
        self.preview_canvas.itemconfigure(self._canvas_win, width=event.width)
        self.preview_canvas.coords(self._canvas_win, event.width // 2, 0)

    def _on_mousewheel(self, event):
        # Only scroll if the mouse is over the preview canvas
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

    # ── Browse & render thumbnails ──────────────────────────────────────
    def _browse_pdf(self):
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf")]
        )
        if path:
            self.pdf_path = path
            self.file_label.config(text=os.path.basename(path))
            try:
                doc = fitz.open(path)
                self.page_count = len(doc)
                size_mb = os.path.getsize(path) / (1024 * 1024)
                self.info_label.config(
                    text=f"Pages: {self.page_count}  |  Size: {size_mb:.1f} MB")
                doc.close()
                # Render thumbnails in background
                self._render_thumbnails()
            except Exception as e:
                messagebox.showerror("Error", f"Cannot open PDF: {e}")
                self.pdf_path = None

    def _render_thumbnails(self):
        """Generate page thumbnails in a background thread."""
        # Hide fixed placeholder
        self._placeholder.place_forget()

        # Clear previous
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self._thumb_photos.clear()
        self._page_vars.clear()
        self._thumb_widgets.clear()

        # Show loading message
        loading = ttk.Label(self.thumb_frame, text="Rendering pages…",
                            style="Desc.TLabel")
        loading.grid(row=0, column=0, padx=40, pady=80)

        threading.Thread(target=self._render_worker, daemon=True).start()

    def _render_worker(self):
        """Background worker: render each page to a PIL image."""
        try:
            doc = fitz.open(self.pdf_path)
            images = []
            thumb_width = 300  # Increased to 300px to fill space and improve readability
            for i in range(len(doc)):
                page = doc[i]
                # Scale so width = thumb_width
                scale = thumb_width / page.rect.width
                mat = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)
            doc.close()

            # Schedule UI update on main thread
            self.after(0, lambda: self._populate_thumbs(images))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error",
                                                        f"Thumbnail error: {e}"))

    def _populate_thumbs(self, images):
        """Place thumbnails + checkboxes in the grid (main thread)."""
        # Clear loading label
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self._thumb_photos.clear()
        self._page_vars.clear()

        cols = 3  # Set to 3 columns as requested

        # Configure uniform column weights so cards spread evenly
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

        # Reset scroll position
        self.preview_canvas.yview_moveto(0)
        self._on_thumb_configure()

    # ── Parse helpers ───────────────────────────────────────────────────
    def _parse_ranges(self, text, max_page):
        pages = []
        for part in text.split(","):
            part = part.strip().replace("\u2013", "-").replace("\u2014", "-")
            if "-" in part:
                a, b = part.split("-", 1)
                a, b = int(a.strip()), int(b.strip())
                for p in range(a, b + 1):
                    if 1 <= p <= max_page:
                        pages.append(p - 1)
            else:
                p = int(part.strip())
                if 1 <= p <= max_page:
                    pages.append(p - 1)
        return sorted(set(pages))

    def _get_selected_pages(self):
        """Return 0-indexed page list from checkboxes."""
        return [i for i, var in enumerate(self._page_vars) if var.get()]

    # ── Split actions ───────────────────────────────────────────────────
    def _start_split(self):
        if not self.pdf_path:
            messagebox.showwarning("No File", "Please select a PDF file first.")
            return

        mode = self.mode_var.get()

        if mode == "selected":
            pages = self._get_selected_pages()
            if not pages:
                messagebox.showwarning("No Pages",
                                       "No pages selected. Use the checkboxes to pick pages.")
                return
            out_path = filedialog.asksaveasfilename(
                title="Save Split PDF",
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")]
            )
            if not out_path:
                return
            threading.Thread(target=self._split_selected,
                             args=(out_path, pages), daemon=True).start()
        elif mode == "each":
            out_dir = filedialog.askdirectory(title="Select Output Folder")
            if not out_dir:
                return
            threading.Thread(target=self._split_each,
                             args=(out_dir,), daemon=True).start()
        elif mode == "range":
            out_path = filedialog.asksaveasfilename(
                title="Save Split PDF",
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")]
            )
            if not out_path:
                return
            threading.Thread(target=self._split_range,
                             args=(out_path,), daemon=True).start()
        elif mode == "multi":
            out_dir = filedialog.askdirectory(title="Select Output Folder")
            if not out_dir:
                return
            threading.Thread(target=self._split_multi,
                             args=(out_dir,), daemon=True).start()

    # ── Split: selected pages (new) ─────────────────────────────────────
    def _split_selected(self, out_path, pages):
        try:
            self.status_callback(f"Extracting {len(pages)} selected pages...")
            self.after(0, lambda: self.progress.config(maximum=1, value=0))

            doc = fitz.open(self.pdf_path)
            doc.select(pages)
            doc.save(out_path, garbage=4, deflate=True, clean=True)
            doc.close()

            out_size = os.path.getsize(out_path) / (1024 * 1024)
            self.after(0, lambda: self.progress.config(value=1))
            self.status_callback(
                f"Split complete: {len(pages)} pages, {out_size:.1f} MB")
            self.after(0, lambda: messagebox.showinfo(
                "Done",
                f"Extracted {len(pages)} pages ({out_size:.1f} MB)\n{out_path}"))
            self.after(0, lambda: self.progress_label.config(text="Done!"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    # ── Split: range ────────────────────────────────────────────────────
    def _split_range(self, out_path):
        try:
            pages = self._parse_ranges(_get_entry_value(self.range_entry), self.page_count)
            if not pages:
                self.after(0, lambda: messagebox.showwarning(
                    "No Pages", "No valid pages."))
                return

            self.status_callback(f"Extracting {len(pages)} pages...")
            self.after(0, lambda: self.progress.config(maximum=1, value=0))

            doc = fitz.open(self.pdf_path)
            doc.select(pages)
            doc.save(out_path, garbage=4, deflate=True, clean=True)
            doc.close()

            out_size = os.path.getsize(out_path) / (1024 * 1024)
            self.after(0, lambda: self.progress.config(value=1))
            self.status_callback(
                f"Split complete: {len(pages)} pages, {out_size:.1f} MB")
            self.after(0, lambda: messagebox.showinfo(
                "Done",
                f"Extracted {len(pages)} pages ({out_size:.1f} MB)\n{out_path}"))
            self.after(0, lambda: self.progress_label.config(text="Done!"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    # ── Split: each page ────────────────────────────────────────────────
    def _split_each(self, out_dir):
        try:
            doc = fitz.open(self.pdf_path)
            total = len(doc)
            base = os.path.splitext(os.path.basename(self.pdf_path))[0]

            self.after(0, lambda: self.progress.config(maximum=total, value=0))
            self.status_callback(f"Splitting {total} pages individually...")

            for i in range(total):
                new_doc = fitz.open(self.pdf_path)
                new_doc.select([i])
                out_path = os.path.join(out_dir, f"{base}_page{i + 1}.pdf")
                new_doc.save(out_path, garbage=4, deflate=True, clean=True)
                new_doc.close()

                self.after(0, lambda v=i + 1: self.progress.config(value=v))
                self.after(0, lambda v=i + 1, t=total:
                           self.progress_label.config(text=f"Page {v}/{t}"))

            doc.close()
            self.status_callback(f"Split {total} pages into individual PDFs")
            self.after(0, lambda: messagebox.showinfo(
                "Done", f"Split {total} pages into:\n{out_dir}"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    # ── Split: multi-range ──────────────────────────────────────────────
    def _split_multi(self, out_dir):
        try:
            ranges_text = _get_entry_value(self.multi_entry)
            range_groups = [r.strip() for r in ranges_text.split(";")
                           if r.strip()]

            base = os.path.splitext(os.path.basename(self.pdf_path))[0]
            total = len(range_groups)
            self.after(0, lambda: self.progress.config(maximum=total, value=0))
            self.status_callback(f"Creating {total} split PDFs...")

            for idx, rg in enumerate(range_groups):
                pages = self._parse_ranges(rg, self.page_count)
                if not pages:
                    continue

                new_doc = fitz.open(self.pdf_path)
                new_doc.select(pages)
                label = rg.replace(",", "_").replace("-", "-").replace(" ", "")
                out_path = os.path.join(out_dir, f"{base}_{label}.pdf")
                new_doc.save(out_path, garbage=4, deflate=True, clean=True)
                new_doc.close()

                self.after(0, lambda v=idx + 1: self.progress.config(value=v))
                self.after(0, lambda v=idx + 1, t=total:
                           self.progress_label.config(text=f"Range {v}/{t}"))

            self.status_callback(f"Created {total} split PDFs")
            self.after(0, lambda: messagebox.showinfo(
                "Done", f"Created {total} files in:\n{out_dir}"))
            self.after(0, lambda: self.progress_label.config(text="Done!"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
