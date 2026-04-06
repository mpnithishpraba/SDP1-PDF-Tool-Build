"""
PDF & Image Magnifier Module
Provides high-precision zoom and navigation for inspecting documents and images.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import fitz  # PyMuPDF
import os
import io
from PIL import Image, ImageTk


class PdfMagnifierFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.file_path = None
        self.file_type = None  # "pdf" or "image"
        self.doc = None
        self.current_page = 0
        self.zoom = 1.0  # 1.0 = 100%
        self._photo = None
        self._drag_data = {"x": 0, "y": 0}
        self._render_after_id = None
        self._build_ui()

    def _build_ui(self):
        title = ttk.Label(self, text="Magnifier", style="Title.TLabel")
        title.pack(pady=(10, 5))

        desc = ttk.Label(self, text="High-precision zoom & inspection tool", style="Desc.TLabel")
        desc.pack(pady=(0, 10))

        # ── Controls ──────────────────────────────────────────────────
        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=20, pady=5)

        ttk.Button(controls, text="Open File", command=self._browse_file).pack(side="left", padx=5)
        self.file_label = ttk.Label(controls, text="No file selected", style="Path.TLabel")
        self.file_label.pack(side="left", padx=10, fill="x", expand=True)

        self.zoom_label = ttk.Label(controls, text="Zoom: 100%", style="Desc.TLabel")
        self.zoom_label.pack(side="right", padx=10)

        # PDF Navigation buttons (initially hidden)
        self.nav_frame = ttk.Frame(controls)
        ttk.Button(self.nav_frame, text="◀", width=3, command=self._prev_page).pack(side="left", padx=2)
        self.page_label = ttk.Label(self.nav_frame, text="Page 1 / 1", style="Desc.TLabel")
        self.page_label.pack(side="left", padx=5)
        ttk.Button(self.nav_frame, text="▶", width=3, command=self._next_page).pack(side="left", padx=2)
        # Hidden by default, shown only for PDFs
        
        # ── Canvas ────────────────────────────────────────────────────
        self.canvas_frame = ttk.Frame(self)
        self.canvas_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#181825", highlightthickness=0)
        self.h_scroll = ttk.Scrollbar(self.canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.v_scroll = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.placeholder = ttk.Label(self.canvas, text="Load file to see preview", style="Desc.TLabel")
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom_scroll)
        
        # Arrow key bindings (need focus)
        self.canvas.bind("<KeyPress>", self._on_key_press)
        self.canvas.focus_set()

    def _on_key_press(self, event):
        if self.file_type == "pdf":
            if event.keysym == "Left":
                self._prev_page()
                return
            elif event.keysym == "Right":
                self._next_page()
                return

        keys = {
            "Up":    ("scroll", -1, "units"),
            "Down":  ("scroll", 1, "units"),
        }
        if event.keysym in ["Up", "Down"]:
            self.canvas.yview(*keys[event.keysym])
        elif event.keysym == "Prior": # Page Up
            self._prev_page()
        elif event.keysym == "Next": # Page Down
            self._next_page()

    def _on_mousewheel(self, event):
        # Now scroll directly zooms
        if event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _on_zoom_scroll(self, event):
        # Keep this as backup or for consistency
        self._on_mousewheel(event)

    def _zoom_in(self):
        if self.zoom < 10.0:
            self.zoom *= 1.2
            self._render()

    def _zoom_out(self):
        if self.zoom > 0.1:
            self.zoom /= 1.2
            self._render()

    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self.canvas.focus_set()

    def _on_drag_motion(self, event):
        dx = self._drag_data["x"] - event.x
        dy = self._drag_data["y"] - event.y
        self.canvas.xview_scroll(dx, "pixels")
        self.canvas.yview_scroll(dy, "pixels")
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select PDF or Image",
            filetypes=[("All supported", "*.pdf *.jpg *.jpeg *.png *.bmp *.webp"),
                       ("PDF files", "*.pdf"),
                       ("Image files", "*.jpg *.jpeg *.png *.bmp *.webp")]
        )
        if path:
            self._load_file(path)

    def _load_file(self, path):
        self.placeholder.place_forget()
        self.file_path = path
        self.file_label.config(text=os.path.basename(path))
        self.zoom = 1.0
        self.current_page = 0
        
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            self.file_type = "pdf"
            self.doc = fitz.open(path)
            self.nav_frame.pack(side="right", padx=10)
        else:
            self.file_type = "image"
            if self.doc: self.doc.close()
            self.doc = Image.open(path)
            self.nav_frame.pack_forget()

        self._render()

    def _render(self):
        if not self.file_path: return
        
        self.zoom_label.config(text=f"Zoom: {int(self.zoom * 100)}%")
        self.status_callback("Rendering...")
        
        # Debounce: Cancel previous pending render
        if self._render_after_id:
            self.after_cancel(self._render_after_id)
            
        self._render_after_id = self.after(100, self._do_actual_render)

    def _do_actual_render(self):
        threading.Thread(target=self._render_worker, daemon=True).start()

    def _render_worker(self):
        try:
            if self.file_type == "pdf":
                page = self.doc[self.current_page]
                # High-res rendering: 
                # At zoom 1.0, use 2.0x for crispness.
                # At zoom 10.0, don't use 20.0x! Cap it.
                matrix_scale = min(max(2.0, self.zoom), 4.0)
                mat = fitz.Matrix(matrix_scale, matrix_scale)
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # If the rendered image is still not at the target zoom size, resize it
                target_w = int(page.rect.width * self.zoom)
                target_h = int(page.rect.height * self.zoom)
                if img.width != target_w:
                    img = img.resize((target_w, target_h), Image.Resampling.BILINEAR)

                total = len(self.doc)
                self.after(0, lambda: self.page_label.config(text=f"Page {self.current_page + 1} / {total}"))
            else:
                # Image mode
                w, h = self.doc.size
                nw, nh = int(w * self.zoom), int(h * self.zoom)
                # Performance: Use BILINEAR for large zooms to reduce latency
                resample = Image.Resampling.LANCZOS if self.zoom <= 1.5 else Image.Resampling.BILINEAR
                img = self.doc.resize((nw, nh), resample)

            self._photo = ImageTk.PhotoImage(img)
            self.after(0, self._update_canvas)
        except Exception as e:
            self.after(0, lambda: self.status_callback(f"Render error: {e}"))

    def _update_canvas(self, event=None):
        if not self._photo: return
        
        self.canvas.delete("all")
        
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        iw = self._photo.width()
        ih = self._photo.height()
        
        # Calculate centering offsets
        x = max(0, (cw - iw) // 2)
        y = max(0, (ch - ih) // 2)
        
        self.canvas.create_image(x, y, anchor="nw", image=self._photo)
        self.canvas.config(scrollregion=(0, 0, max(cw, iw), max(ch, ih)))
        self.status_callback("Ready")

    def _on_canvas_resize(self, event):
        self._update_canvas()

    def _prev_page(self):
        if self.file_type == "pdf" and self.current_page > 0:
            self.current_page -= 1
            self._render()

    def _next_page(self):
        if self.file_type == "pdf" and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self._render()
