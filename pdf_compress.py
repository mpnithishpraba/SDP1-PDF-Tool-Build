"""
PDF & Image Compression Module
Compress PDFs or Images with presets, manual controls, and exact target-size mode.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import fitz  # PyMuPDF
import os
import io
from PIL import Image


class PdfCompressFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.file_path = None
        self.page_count = 0
        self.original_size_bytes = 0
        self._build_ui()

    # ═══════════════════════════════════════════════════════════════════
    #  UI
    # ═══════════════════════════════════════════════════════════════════

"""
PDF & Image Compression Module
Compress PDFs or Images with presets, manual controls, and exact target-size mode.
Includes visual file preview.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import fitz  # PyMuPDF
import os
import io
from PIL import Image, ImageTk


class PdfCompressFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.file_path = None
        self.page_count = 0
        self.original_size_bytes = 0
        self._thumb_photos = [] # Keep refs alive
        self._build_ui()

    def _build_ui(self):
        title = ttk.Label(self, text="Compress", style="Title.TLabel")
        title.pack(pady=(10, 5))

        desc = ttk.Label(self, text="Compress PDF or Image files",
                         style="Desc.TLabel")
        desc.pack(pady=(0, 10))

        # ── Two-pane container ──────────────────────────────────────────
        panes = ttk.Frame(self)
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        panes.columnconfigure(0, weight=3, uniform="pane")
        panes.columnconfigure(1, weight=4, uniform="pane")
        panes.rowconfigure(0, weight=1)
        panes.grid_propagate(False)

        # ── LEFT PANE (controls) ────────────────────────────────────────
        left = ttk.Frame(panes)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        # Mode selector
        mode_frame = ttk.LabelFrame(left, text="File Type", padding=8)
        mode_frame.pack(fill="x", pady=5)
        self.mode_var = tk.StringVar(value="pdf")
        ttk.Radiobutton(mode_frame, text="PDF", variable=self.mode_var,
                         value="pdf", command=self._switch_mode).pack(side="left", padx=15)
        ttk.Radiobutton(mode_frame, text="Image", variable=self.mode_var,
                         value="image", command=self._switch_mode).pack(side="left", padx=15)

        # File selection
        file_frame = ttk.Frame(left)
        file_frame.pack(fill="x", pady=5)
        ttk.Label(file_frame, text="File:").pack(side="left")
        self.file_label = ttk.Label(file_frame, text="No file selected", style="Path.TLabel")
        self.file_label.pack(side="left", padx=(10, 10), fill="x", expand=True)
        ttk.Button(file_frame, text="Browse", command=self._browse_file).pack(side="right")

        self.info_label = ttk.Label(left, text="", style="Desc.TLabel")
        self.info_label.pack(anchor="w")

        # Target Size
        target_frame = ttk.LabelFrame(left, text="Target File Size", padding=8)
        target_frame.pack(fill="x", pady=5)
        self.target_enable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(target_frame, text="Enable target size",
                         variable=self.target_enable_var,
                         command=self._toggle_target).pack(anchor="w")
        self.target_row = ttk.Frame(target_frame)
        self.target_size_var = tk.IntVar(value=500)
        self.target_scale = ttk.Scale(self.target_row, from_=50, to=10000,
                                       variable=self.target_size_var,
                                       orient="horizontal")
        self.target_scale.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.target_entry_var = tk.StringVar(value="500")
        self.target_entry = ttk.Entry(self.target_row, textvariable=self.target_entry_var, width=8)
        self.target_entry.pack(side="left", padx=(0, 4))
        self.target_unit_label = ttk.Label(self.target_row, text="KB", width=4)
        self.target_unit_label.pack(side="left")
        self.target_scale.config(command=self._on_target_slide)
        self.target_entry.bind("<Return>", self._on_target_entry)
        self.target_entry.bind("<FocusOut>", self._on_target_entry)
        self.target_row.pack_forget()

        # PDF Frame
        self.pdf_frame = ttk.Frame(left)
        preset_frame = ttk.LabelFrame(self.pdf_frame, text="Compression Preset", padding=10)
        preset_frame.pack(fill="x", pady=5)
        self.preset_var = tk.StringVar(value="low")
        presets = [("Low — visually lossless", "low"), ("Medium — balanced", "medium"), ("High — maximum compression", "high")]
        for text, val in presets:
            ttk.Radiobutton(preset_frame, text=text, variable=self.preset_var,
                             value=val, command=self._update_from_preset).pack(anchor="w", pady=1)

        ctrl_frame = ttk.LabelFrame(self.pdf_frame, text="Manual Controls", padding=10)
        ctrl_frame.pack(fill="x", pady=5)
        dpi_row = ttk.Frame(ctrl_frame); dpi_row.pack(fill="x", pady=3)
        ttk.Label(dpi_row, text="Max DPI:").pack(side="left")
        self.dpi_var = tk.IntVar(value=300)
        self.dpi_scale = ttk.Scale(dpi_row, from_=72, to=600, variable=self.dpi_var, orient="horizontal")
        self.dpi_scale.pack(side="left", fill="x", expand=True, padx=(10, 5))
        self.dpi_display = ttk.Label(dpi_row, text="300", width=5); self.dpi_display.pack(side="right")
        self.dpi_scale.config(command=lambda v: self.dpi_display.config(text=str(int(float(v)))))

        q_row = ttk.Frame(ctrl_frame); q_row.pack(fill="x", pady=3)
        ttk.Label(q_row, text="JPEG Quality:").pack(side="left")
        self.quality_var = tk.IntVar(value=85)
        self.quality_scale = ttk.Scale(q_row, from_=10, to=100, variable=self.quality_var, orient="horizontal")
        self.quality_scale.pack(side="left", fill="x", expand=True, padx=(10, 5))
        self.quality_display = ttk.Label(q_row, text="85", width=5); self.quality_display.pack(side="right")
        self.quality_scale.config(command=lambda v: self.quality_display.config(text=str(int(float(v)))))
        
        self.grayscale_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl_frame, text="Convert images to grayscale", variable=self.grayscale_var).pack(anchor="w", pady=3)
        self.pdf_frame.pack(fill="x")

        # Image Frame
        self.img_frame = ttk.Frame(left)
        img_ctrl = ttk.LabelFrame(self.img_frame, text="Image Settings", padding=10)
        img_ctrl.pack(fill="x", pady=5)
        fmt_row = ttk.Frame(img_ctrl); fmt_row.pack(fill="x", pady=3)
        ttk.Label(fmt_row, text="Output Format:").pack(side="left")
        self.img_format_var = tk.StringVar(value="JPG")
        ttk.Combobox(fmt_row, textvariable=self.img_format_var, values=["JPG", "PNG"], state="readonly", width=8).pack(side="left", padx=(8, 0))

        iq_row = ttk.Frame(img_ctrl); iq_row.pack(fill="x", pady=3)
        ttk.Label(iq_row, text="Quality:").pack(side="left")
        self.img_quality_var = tk.IntVar(value=80)
        self.img_quality_scale = ttk.Scale(iq_row, from_=5, to=100, variable=self.img_quality_var, orient="horizontal")
        self.img_quality_scale.pack(side="left", fill="x", expand=True, padx=(10, 5))
        self.img_quality_display = ttk.Label(iq_row, text="80", width=5); self.img_quality_display.pack(side="right")
        self.img_quality_scale.config(command=lambda v: self.img_quality_display.config(text=str(int(float(v)))))

        self.img_resize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(img_ctrl, text="Resize (max dimension):", variable=self.img_resize_var).pack(anchor="w", pady=3)
        self.img_max_dim_var = tk.IntVar(value=1920)
        dim_row = ttk.Frame(img_ctrl); dim_row.pack(fill="x", pady=3)
        ttk.Label(dim_row, text="Max px:").pack(side="left")
        self.img_dim_scale = ttk.Scale(dim_row, from_=200, to=8000, variable=self.img_max_dim_var, orient="horizontal")
        self.img_dim_scale.pack(side="left", fill="x", expand=True, padx=(10, 5))
        self.img_dim_display = ttk.Label(dim_row, text="1920", width=6); self.img_dim_display.pack(side="right")
        self.img_dim_scale.config(command=lambda v: self.img_dim_display.config(text=str(int(float(v)))))
        self.img_frame.pack_forget()

        # Progress
        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 5))
        self.progress_label = ttk.Label(left, text="", style="Desc.TLabel"); self.progress_label.pack()

        # Action
        ttk.Button(left, text="Compress File", style="Accent.TButton", command=self._start_compress).pack(pady=15)

        # ── RIGHT PANE (preview) ────────────────────────────────────────
        right = ttk.Frame(panes)
        right.grid(row=0, column=1, sticky="nsew")

        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(0, 5))
        ttk.Label(toolbar, text="File Preview", style="Path.TLabel").pack(side="left")

        preview_container = ttk.Frame(right)
        preview_container.pack(fill="both", expand=True)

        self.preview_canvas = tk.Canvas(preview_container, highlightthickness=0, bd=0)
        self.v_scroll = ttk.Scrollbar(preview_container, orient="vertical", command=self.preview_canvas.yview)
        self.preview_canvas.configure(yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.preview_canvas.pack(side="left", fill="both", expand=True)

        self._placeholder = ttk.Label(preview_container, text="Load a file to see preview", style="Desc.TLabel")
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self.thumb_frame = ttk.Frame(self.preview_canvas)
        self._canvas_win = self.preview_canvas.create_window((0, 0), window=self.thumb_frame, anchor="n")

        self.thumb_frame.bind("<Configure>", lambda e: self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all")))
        self.preview_canvas.bind("<Configure>", self._on_canvas_resize)
        self.preview_canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

        self._update_from_preset()

    def _on_canvas_resize(self, event):
        self.preview_canvas.itemconfig(self._canvas_win, width=event.width)
        self.preview_canvas.coords(self._canvas_win, event.width // 2, 0)

    def _on_mousewheel(self, event):
        self.preview_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ═══════════════════════════════════════════════════════════════════
    #  Preview Logic
    # ═══════════════════════════════════════════════════════════════════

    def _clear_preview_ui(self):
        for w in self.thumb_frame.winfo_children(): w.destroy()
        self._thumb_photos.clear()
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _render_preview(self):
        self._clear_preview_ui()
        self._placeholder.place_forget()
        
        loading = ttk.Label(self.thumb_frame, text="Rendering preview...", style="Desc.TLabel")
        loading.grid(row=0, column=0, padx=40, pady=40)
        
        threading.Thread(target=self._preview_worker, daemon=True).start()

    def _preview_worker(self):
        try:
            mode = self.mode_var.get()
            images = []
            info_text = ""
            thumb_width = 280

            if mode == "pdf":
                doc = fitz.open(self.file_path)
                pcount = len(doc)
                size_mb = os.path.getsize(self.file_path) / (1024 * 1024)
                info_text = f"Pages: {pcount}  |  Size: {size_mb:.2f} MB"
                
                for i in range(min(pcount, 20)):
                    page = doc[i]
                    scale = thumb_width / page.rect.width
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    images.append(img)
                doc.close()
            else:
                img = Image.open(self.file_path)
                w, h = img.size
                size_mb = os.path.getsize(self.file_path) / (1024 * 1024)
                info_text = f"Dimensions: {w}×{h}  |  Size: {size_mb:.2f} MB"
                
                scale = thumb_width*2 / max(w, h)
                img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
                images.append(img)

            self.after(0, lambda: self._populate_thumbs(images, info_text))
        except Exception as e:
            self.after(0, lambda: self.status_callback(f"Preview error: {e}"))

    def _populate_thumbs(self, images, info_text):
        for w in self.thumb_frame.winfo_children(): w.destroy()
        self._thumb_photos.clear()
        self.info_label.config(text=info_text)

        cols = 3 if self.mode_var.get() == "pdf" else 1
        for c in range(cols): self.thumb_frame.columnconfigure(c, weight=1)

        for idx, img in enumerate(images):
            photo = ImageTk.PhotoImage(img)
            self._thumb_photos.append(photo)
            
            card = ttk.Frame(self.thumb_frame, style="Surface.TFrame")
            card.grid(row=idx // cols, column=idx % cols, padx=5, pady=5)
            
            lbl = tk.Label(card, image=photo, bd=1, relief="solid")
            lbl.pack(padx=2, pady=2)
            
            if self.mode_var.get() == "pdf":
                ttk.Label(card, text=f"Page {idx+1}", style="Desc.TLabel").pack()

        self.preview_canvas.yview_moveto(0)

    # ═══════════════════════════════════════════════════════════════════
    #  Mode switching
    # ═══════════════════════════════════════════════════════════════════

    def _switch_mode(self):
        if self.mode_var.get() == "pdf":
            self.img_frame.pack_forget()
            self.pdf_frame.pack(fill="x")
        else:
            self.pdf_frame.pack_forget()
            self.img_frame.pack(fill="x")
        # Reset file
        self.file_path = None
        self.original_size_bytes = 0
        self.file_label.config(text="No file selected")
        self.info_label.config(text="")
        self.target_enable_var.set(False)
        self.target_row.pack_forget()
        self._clear_preview_ui()

    # ═══════════════════════════════════════════════════════════════════
    #  Target size slider
    # ═══════════════════════════════════════════════════════════════════

    def _toggle_target(self):
        if self.target_enable_var.get():
            self.target_row.pack(fill="x", pady=(5, 0))
        else:
            self.target_row.pack_forget()

    def _on_target_slide(self, val):
        kb = int(float(val))
        if kb >= 1024:
            self.target_entry_var.set(f"{kb / 1024:.1f}")
            self.target_unit_label.config(text="MB")
        else:
            self.target_entry_var.set(str(kb))
            self.target_unit_label.config(text="KB")

    def _on_target_entry(self, event=None):
        """User typed a value in the entry – update slider."""
        try:
            text = self.target_entry_var.get().strip()
            val = float(text)
            unit = self.target_unit_label.cget("text").strip()
            if unit == "MB":
                kb = int(val * 1024)
            else:
                kb = int(val)
            kb = max(50, min(kb, int(self.original_size_bytes / 1024)))
            self.target_size_var.set(kb)
        except ValueError:
            pass

    def _update_target_range(self):
        """Set slider range from 50 KB to original file size."""
        max_kb = max(int(self.original_size_bytes / 1024), 100)
        self.target_scale.config(from_=50, to=max_kb)
        self.target_size_var.set(max_kb // 2)
        self._on_target_slide(max_kb // 2)

    # ═══════════════════════════════════════════════════════════════════
    #  Presets (PDF)
    # ═══════════════════════════════════════════════════════════════════

    def _update_from_preset(self):
        preset = self.preset_var.get()
        if preset == "low":
            self.dpi_var.set(300); self.quality_var.set(85); self.grayscale_var.set(False)
        elif preset == "medium":
            self.dpi_var.set(200); self.quality_var.set(65); self.grayscale_var.set(False)
        elif preset == "high":
            self.dpi_var.set(150); self.quality_var.set(40); self.grayscale_var.set(False)
        self.dpi_display.config(text=str(self.dpi_var.get()))
        self.quality_display.config(text=str(self.quality_var.get()))

    # ═══════════════════════════════════════════════════════════════════
    #  File browsing
    # ═══════════════════════════════════════════════════════════════════

    def _browse_file(self):
        if self.mode_var.get() == "pdf":
            path = filedialog.askopenfilename(
                title="Select PDF",
                filetypes=[("PDF files", "*.pdf")]
            )
        else:
            path = filedialog.askopenfilename(
                title="Select Image",
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
                           ("All files", "*.*")]
            )
        if not path:
            return

        self.file_path = path
        self.file_label.config(text=os.path.basename(path))
        self.original_size_bytes = os.path.getsize(path)
        
        self._render_preview()
        self._update_target_range()

    # ═══════════════════════════════════════════════════════════════════
    #  Compress entry point
    # ═══════════════════════════════════════════════════════════════════

    def _start_compress(self):
        if not self.file_path:
            messagebox.showwarning("No File", "Please select a file first.")
            return

        out_path = filedialog.asksaveasfilename(
            title="Save Compressed File",
            defaultextension=".pdf" if self.mode_var.get() == "pdf" else ".jpg",
            filetypes=[("PDF files", "*.pdf")] if self.mode_var.get() == "pdf"
                      else [("JPEG", "*.jpg"), ("PNG", "*.png"), ("All", "*.*")]
        )
        if not out_path:
            return

        if self.mode_var.get() == "pdf":
            threading.Thread(target=self._do_compress_pdf, args=(out_path,), daemon=True).start()
        else:
            threading.Thread(target=self._do_compress_image, args=(out_path,), daemon=True).start()

    # ═══════════════════════════════════════════════════════════════════
    #  PDF compression (existing logic + target-size binary search)
    # ═══════════════════════════════════════════════════════════════════

    def _compress_pdf_once(self, quality, max_dpi, grayscale, out_path):
        """Run one PDF compression pass and return output size in bytes."""
        doc = fitz.open(self.file_path)
        total = len(doc)

        for page_num in range(total):
            page = doc[page_num]
            images = page.get_images(full=True)

            for img_info in images:
                xref = img_info[0]
                try:
                    img_data = doc.extract_image(xref)
                    if not img_data:
                        continue

                    img_bytes = img_data["image"]
                    pil_img = Image.open(io.BytesIO(img_bytes))

                    w, h = pil_img.size
                    dpi_info = pil_img.info.get("dpi", (300, 300))
                    cur_dpi = max(dpi_info) if isinstance(dpi_info, tuple) else dpi_info

                    if cur_dpi > max_dpi:
                        scale = max_dpi / cur_dpi
                        pil_img = pil_img.resize(
                            (max(int(w * scale), 50), max(int(h * scale), 50)),
                            Image.LANCZOS)

                    if grayscale:
                        pil_img = pil_img.convert("L")
                    elif pil_img.mode not in ("RGB", "L"):
                        pil_img = pil_img.convert("RGB")

                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
                    new_bytes = buf.getvalue()

                    if len(new_bytes) < len(img_bytes):
                        doc.update_stream(xref, new_bytes)
                        doc.xref_set_key(xref, "Filter", "/DCTDecode")
                        doc.xref_set_key(xref, "Width", str(pil_img.width))
                        doc.xref_set_key(xref, "Height", str(pil_img.height))
                        cs = "/DeviceGray" if grayscale else "/DeviceRGB"
                        doc.xref_set_key(xref, "ColorSpace", cs)
                        doc.xref_set_key(xref, "BitsPerComponent", "8")
                except Exception:
                    pass

            self.after(0, lambda v=page_num + 1: self.progress.config(value=v))
            self.after(0, lambda v=page_num + 1, t=total:
                       self.progress_label.config(text=f"Page {v}/{t}"))

        doc.save(out_path, garbage=4, deflate=True, clean=True)
        doc.close()
        return os.path.getsize(out_path)

    def _do_compress_pdf(self, out_path):
        try:
            max_dpi = self.dpi_var.get()
            quality = self.quality_var.get()
            grayscale = self.grayscale_var.get()
            total = fitz.open(self.file_path).__len__()

            self.after(0, lambda: self.progress.config(maximum=total, value=0))

            if self.target_enable_var.get():
                target_bytes = self.target_size_var.get() * 1024
                self.status_callback(f"Target: {self.target_size_var.get()} KB — searching...")

                lo, hi = 1, quality
                best_quality = lo
                best_size = self.original_size_bytes

                for iteration in range(20):  # more iterations for precision
                    mid = (lo + hi) // 2
                    self.after(0, lambda: self.progress.config(value=0))
                    self.status_callback(f"Trying quality={mid} (attempt {iteration + 1})...")

                    out_size = self._compress_pdf_once(mid, max_dpi, grayscale, out_path)

                    # Track best quality that stays at or under target
                    if out_size <= target_bytes:
                        if out_size > best_size or best_size > target_bytes:
                            best_quality = mid
                            best_size = out_size
                        lo = mid + 1
                    else:
                        hi = mid - 1

                    # Close enough (±1%) and under target
                    if out_size <= target_bytes and abs(out_size - target_bytes) / max(target_bytes, 1) <= 0.01:
                        break

                    if lo > hi:
                        # Final pass with best found quality that was under target
                        self._compress_pdf_once(best_quality, max_dpi, grayscale, out_path)
                        break
            else:
                self.status_callback(f"Compressing (DPI:{max_dpi}, Q:{quality})...")
                self._compress_pdf_once(quality, max_dpi, grayscale, out_path)

            orig_size = self.original_size_bytes / (1024 * 1024)
            out_size = os.path.getsize(out_path) / (1024 * 1024)
            reduction = ((orig_size - out_size) / orig_size * 100) if orig_size > 0 else 0

            self.status_callback(f"Compressed: {orig_size:.2f} MB → {out_size:.2f} MB ({reduction:.0f}%)")
            self.after(0, lambda: messagebox.showinfo("Done",
                f"Size: {orig_size:.2f} MB → {out_size:.2f} MB\n"
                f"Reduction: {reduction:.0f}%\n{out_path}"))
            self.after(0, lambda: self.progress_label.config(text="Done!"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    # ═══════════════════════════════════════════════════════════════════
    #  Image compression (+ target-size binary search)
    # ═══════════════════════════════════════════════════════════════════

    def _compress_image_once(self, pil_img, quality, fmt, out_path):
        """Save image at given quality, return output size in bytes."""
        save_kwargs = {"optimize": True}
        if fmt == "JPG":
            save_kwargs["format"] = "JPEG"
            save_kwargs["quality"] = quality
            if pil_img.mode == "RGBA":
                pil_img = pil_img.convert("RGB")
        else:
            save_kwargs["format"] = "PNG"

        pil_img.save(out_path, **save_kwargs)
        return os.path.getsize(out_path)

    def _do_compress_image(self, out_path):
        try:
            self.after(0, lambda: self.progress.config(maximum=100, value=10))

            pil_img = Image.open(self.file_path)
            fmt = self.img_format_var.get()
            quality = self.img_quality_var.get()

            # Resize if enabled
            if self.img_resize_var.get():
                max_dim = self.img_max_dim_var.get()
                w, h = pil_img.size
                if max(w, h) > max_dim:
                    ratio = max_dim / max(w, h)
                    pil_img = pil_img.resize(
                        (max(int(w * ratio), 1), max(int(h * ratio), 1)),
                        Image.LANCZOS)

            self.after(0, lambda: self.progress.config(value=30))

            if self.target_enable_var.get() and fmt == "JPG":
                target_bytes = self.target_size_var.get() * 1024
                self.status_callback(f"Target: {self.target_size_var.get()} KB — searching...")

                lo, hi = 1, quality
                best_quality = lo
                best_size = self.original_size_bytes

                for iteration in range(20):
                    mid = (lo + hi) // 2
                    self.status_callback(f"Trying quality={mid} (attempt {iteration + 1})...")
                    out_size = self._compress_image_once(pil_img, mid, fmt, out_path)

                    pct = min(30 + (iteration + 1) * 3, 90)
                    self.after(0, lambda p=pct: self.progress.config(value=p))

                    # Track best quality that stays at or under target
                    if out_size <= target_bytes:
                        if out_size > best_size or best_size > target_bytes:
                            best_quality = mid
                            best_size = out_size
                        lo = mid + 1
                    else:
                        hi = mid - 1

                    # Close enough (±1%) and under target
                    if out_size <= target_bytes and abs(out_size - target_bytes) / max(target_bytes, 1) <= 0.01:
                        break

                    if lo > hi:
                        self._compress_image_once(pil_img, best_quality, fmt, out_path)
                        break
            else:
                self.status_callback(f"Compressing image as {fmt}...")
                self._compress_image_once(pil_img, quality, fmt, out_path)

            self.after(0, lambda: self.progress.config(value=100))

            orig_size = self.original_size_bytes / (1024 * 1024)
            out_size = os.path.getsize(out_path) / (1024 * 1024)
            reduction = ((orig_size - out_size) / orig_size * 100) if orig_size > 0 else 0

            self.status_callback(f"Compressed: {orig_size:.2f} MB → {out_size:.2f} MB ({reduction:.0f}%)")
            self.after(0, lambda: messagebox.showinfo("Done",
                f"Size: {orig_size:.2f} MB → {out_size:.2f} MB\n"
                f"Reduction: {reduction:.0f}%\n{out_path}"))
            self.after(0, lambda: self.progress_label.config(text="Done!"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
