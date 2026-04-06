"""
PDF & Image Resizer Module
Supports resizing PDF pages and standalone Images by Pixels or Ratio.
Includes visual file preview.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import fitz  # PyMuPDF
import os
import io
from PIL import Image, ImageTk


class PdfResizeFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.file_path = None
        self.file_type = "pdf"  # "pdf" or "image"
        self._thumb_photos = [] # references to keep PhotoImages alive
        self._build_ui()

    def _build_ui(self):
        title = ttk.Label(self, text="Resizer", style="Title.TLabel")
        title.pack(pady=(10, 5))

        desc = ttk.Label(self, text="Resize PDF pages or Images by dimensions or scale",
                         style="Desc.TLabel")
        desc.pack(pady=(0, 15))

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
        
        # Target Selection
        target_frame = ttk.LabelFrame(left, text="Target File Type", padding=8)
        target_frame.pack(fill="x", pady=5)
        self.target_var = tk.StringVar(value="pdf")
        ttk.Radiobutton(target_frame, text="PDF Document", variable=self.target_var, 
                         value="pdf", command=self._on_target_change).pack(side="left", padx=10)
        ttk.Radiobutton(target_frame, text="Image File", variable=self.target_var, 
                         value="image", command=self._on_target_change).pack(side="left")

        # File selection
        file_frame = ttk.Frame(left)
        file_frame.pack(fill="x", pady=10)
        self.file_type_label = ttk.Label(file_frame, text="PDF File:")
        self.file_type_label.pack(side="left")
        self.file_label = ttk.Label(file_frame, text="No file selected", style="Path.TLabel")
        self.file_label.pack(side="left", padx=(10, 10), fill="x", expand=True)
        ttk.Button(file_frame, text="Browse", command=self._browse_file).pack(side="right")

        self.info_label = ttk.Label(left, text="", style="Desc.TLabel")
        self.info_label.pack(anchor="w")

        # Resize Methods
        method_frame = ttk.LabelFrame(left, text="Resize Method", padding=10)
        method_frame.pack(fill="x", pady=10)

        self.method_var = tk.StringVar(value="pixels")
        ttk.Radiobutton(method_frame, text="By Pixels (Width x Height)", 
                         variable=self.method_var, value="pixels", command=self._update_method_ui).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(method_frame, text="By Ratio (Percentage %)", 
                         variable=self.method_var, value="ratio", command=self._update_method_ui).grid(row=1, column=0, sticky="w", pady=(5,0))

        # Input container
        self.inputs_container = ttk.Frame(method_frame)
        self.inputs_container.grid(row=2, column=0, columnspan=2, pady=10, sticky="w")

        # --- Pixel Inputs ---
        self.pixel_frame = ttk.Frame(self.inputs_container)
        ttk.Label(self.pixel_frame, text="Width:").pack(side="left")
        self.width_var = tk.StringVar(value="800")
        ttk.Entry(self.pixel_frame, textvariable=self.width_var, width=8).pack(side="left", padx=5)
        ttk.Label(self.pixel_frame, text="px").pack(side="left", padx=(0, 15))

        ttk.Label(self.pixel_frame, text="Height:").pack(side="left")
        self.height_var = tk.StringVar(value="600")
        ttk.Entry(self.pixel_frame, textvariable=self.height_var, width=8).pack(side="left", padx=5)
        ttk.Label(self.pixel_frame, text="px").pack(side="left")

        self.aspect_check = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.pixel_frame, text="Maintain Aspect Ratio", variable=self.aspect_check).pack(side="left", padx=20)

        # --- Ratio Input ---
        self.ratio_frame = ttk.Frame(self.inputs_container)
        ttk.Label(self.ratio_frame, text="Scale:").pack(side="left")
        self.ratio_val_var = tk.IntVar(value=50)
        self.ratio_scale = ttk.Scale(self.ratio_frame, from_=5, to=200, variable=self.ratio_val_var, orient="horizontal", command=self._on_ratio_slide)
        self.ratio_scale.pack(side="left", fill="x", expand=True, padx=10)
        self.ratio_label = ttk.Label(self.ratio_frame, text="50%", width=5)
        self.ratio_label.pack(side="left")

        self._update_method_ui()

        # Progress
        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(15, 5))

        self.progress_label = ttk.Label(left, text="", style="Desc.TLabel")
        self.progress_label.pack()

        # Action button
        self.action_btn = ttk.Button(left, text="Resize Now", style="Accent.TButton",
                                      command=self._start_resize)
        self.action_btn.pack(pady=20)

        # ── RIGHT PANE (preview) ────────────────────────────────────────
        right = ttk.Frame(panes)
        right.grid(row=0, column=1, sticky="nsew")

        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(0, 5))
        self._preview_title = ttk.Label(toolbar, text="File Preview", style="Path.TLabel")
        self._preview_title.pack(side="left")

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

    def _on_canvas_resize(self, event):
        self.preview_canvas.itemconfig(self._canvas_win, width=event.width)
        self.preview_canvas.coords(self._canvas_win, event.width // 2, 0)

    def _on_mousewheel(self, event):
        self.preview_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_target_change(self):
        target = self.target_var.get()
        self.file_type = target
        self.file_type_label.config(text="PDF File:" if target == "pdf" else "Image File:")
        self.file_path = None
        self.file_label.config(text="No file selected")
        self.info_label.config(text="")
        self.action_btn.config(text="Resize PDF" if target == "pdf" else "Resize Image")
        self._clear_preview_ui()

    def _update_method_ui(self):
        method = self.method_var.get()
        if method == "pixels":
            self.ratio_frame.pack_forget()
            self.pixel_frame.pack(fill="x")
        else:
            self.pixel_frame.pack_forget()
            self.ratio_frame.pack(fill="x")

    def _on_ratio_slide(self, val):
        self.ratio_label.config(text=f"{int(float(val))}%")

    def _browse_file(self):
        target = self.target_var.get()
        if target == "pdf":
            ftypes = [("PDF files", "*.pdf")]
        else:
            ftypes = [("Image files", "*.jpg *.jpeg *.png *.bmp *.webp")]

        path = filedialog.askopenfilename(title=f"Select {target.upper()}", filetypes=ftypes)
        if path:
            self.file_path = path
            self.file_label.config(text=os.path.basename(path))
            self._render_preview()

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
            target = self.target_var.get()
            images = []
            info_text = ""
            thumb_width = 280

            if target == "pdf":
                doc = fitz.open(self.file_path)
                pcount = len(doc)
                size_mb = os.path.getsize(self.file_path) / (1024 * 1024)
                info_text = f"Pages: {pcount} | Size: {size_mb:.1f} MB"
                
                # Render up to 20 pages for preview performance
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
                size_kb = os.path.getsize(self.file_path) / 1024
                info_text = f"Dimensions: {w}x{h} px | Size: {size_kb:.1f} KB"
                
                # Large single image preview
                scale = thumb_width*2 / max(w, h)
                img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
                images.append(img)
                
                # Pre-fill dimensions in pixels mode
                self.after(0, lambda: self.width_var.set(str(w)))
                self.after(0, lambda: self.height_var.set(str(h)))

            self.after(0, lambda: self._populate_thumbs(images, info_text))
        except Exception as e:
            self.after(0, lambda: self.info_label.config(text=f"Preview error: {e}"))

    def _populate_thumbs(self, images, info_text):
        for w in self.thumb_frame.winfo_children(): w.destroy()
        self._thumb_photos.clear()
        self.info_label.config(text=info_text)

        cols = 3 if self.target_var.get() == "pdf" else 1
        for c in range(cols): self.thumb_frame.columnconfigure(c, weight=1)

        for idx, img in enumerate(images):
            photo = ImageTk.PhotoImage(img)
            self._thumb_photos.append(photo)
            
            card = ttk.Frame(self.thumb_frame, style="Surface.TFrame")
            card.grid(row=idx // cols, column=idx % cols, padx=5, pady=5)
            
            lbl = tk.Label(card, image=photo, bd=1, relief="solid")
            lbl.pack(padx=2, pady=2)
            
            if self.target_var.get() == "pdf":
                ttk.Label(card, text=f"Page {idx+1}", style="Desc.TLabel").pack()

        self.preview_canvas.yview_moveto(0)

    def _start_resize(self):
        if not self.file_path:
            messagebox.showwarning("No File", "Please select a file first.")
            return

        method = self.method_var.get()
        target = self.target_var.get()

        try:
            if method == "pixels":
                tw = int(self.width_var.get())
                th = int(self.height_var.get())
                if tw <= 0 or th <= 0: raise ValueError
            else:
                ratio = int(self.ratio_val_var.get()) / 100.0
                if ratio <= 0: raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter valid numeric values for resizing.")
            return

        ext = ".pdf" if target == "pdf" else os.path.splitext(self.file_path)[1]
        out_path = filedialog.asksaveasfilename(
            title="Save Resized File",
            defaultextension=ext,
            filetypes=[(f"{target.upper()} files", f"*{ext}")]
        )
        if not out_path:
            return

        if target == "pdf":
            threading.Thread(target=self._do_resize_pdf, args=(out_path,), daemon=True).start()
        else:
            threading.Thread(target=self._do_resize_image, args=(out_path,), daemon=True).start()

    def _do_resize_image(self, out_path):
        try:
            self.after(0, lambda: self.progress.config(mode="indeterminate"))
            self.after(0, self.progress.start)
            self.status_callback("Resizing image...")

            img = Image.open(self.file_path)
            method = self.method_var.get()

            if method == "pixels":
                tw = int(self.width_var.get())
                th = int(self.height_var.get())
                if self.aspect_check.get():
                    img.thumbnail((tw, th), Image.LANCZOS)
                else:
                    img = img.resize((tw, th), Image.LANCZOS)
            else:
                ratio = self.ratio_val_var.get() / 100.0
                nw = int(img.width * ratio)
                nh = int(img.height * ratio)
                img = img.resize((nw, nh), Image.LANCZOS)

            img.save(out_path, optimize=True)
            
            self.after(0, self.progress.stop)
            self.after(0, lambda: self.progress.config(mode="determinate", value=100))
            self.status_callback("Image resize complete")
            self.after(0, lambda: messagebox.showinfo("Done", f"Resized image saved to:\n{out_path}"))
        except Exception as e:
            self._handle_error(e)

    def _do_resize_pdf(self, out_path):
        try:
            doc = fitz.open(self.file_path)
            total = len(doc)
            self.after(0, lambda: self.progress.config(maximum=total, value=0))
            self.status_callback(f"Resizing PDF ({total} pages)...")

            method = self.method_var.get()
            new_doc = fitz.open()

            for i in range(total):
                page = doc[i]
                pref = page.rect
                
                if method == "pixels":
                    tw = int(self.width_var.get())
                    th = int(self.height_var.get())
                    if self.aspect_check.get():
                        scale = min(tw / pref.width, th / pref.height)
                        sw, sh = pref.width * scale, pref.height * scale
                    else:
                        sw, sh = tw, th
                else:
                    ratio = self.ratio_val_var.get() / 100.0
                    sw, sh = pref.width * ratio, pref.height * ratio

                new_page = new_doc.new_page(width=sw, height=sh)
                mat = fitz.Matrix(sw / pref.width, sh / pref.height)
                new_page.show_pdf_page(new_page.rect, doc, i, matrix=mat)

                self.after(0, lambda v=i+1: self.progress.config(value=v))
                self.after(0, lambda v=i+1, t=total: self.progress_label.config(text=f"Page {v}/{t}"))

            new_doc.save(out_path, garbage=4, deflate=True)
            new_doc.close()
            doc.close()

            self.status_callback("PDF resize complete")
            self.after(0, lambda: messagebox.showinfo("Done", f"Resized PDF saved to:\n{out_path}"))
        except Exception as e:
            self._handle_error(e)

    def _handle_error(self, e):
        self.after(0, self.progress.stop)
        self.status_callback(f"Error: {e}")
        self.after(0, lambda: messagebox.showerror("Error", str(e)))
