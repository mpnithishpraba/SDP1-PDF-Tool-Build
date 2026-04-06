"""
PDF Reorder Module
Allows users to visually reorder PDF pages by dragging thumbnails.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import fitz  # PyMuPDF
import os
import io
from PIL import Image, ImageTk


class PdfReorderFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.pdf_path = None
        self.page_order = []  # List of original indices in current order
        self._thumb_photos = {} # page_index -> PhotoImage
        self._drag_obj = None
        self._drag_data = {"x": 0, "y": 0, "item": None}
        self._build_ui()

    def _build_ui(self):
        title = ttk.Label(self, text="PDF Page Reorder", style="Title.TLabel")
        title.pack(pady=(10, 5))

        desc = ttk.Label(self, text="Drag thumbnails to change page order",
                         style="Desc.TLabel")
        desc.pack(pady=(0, 10))

        # Main Layout: Controls top, scrollable grid bottom
        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=20, pady=5)

        ttk.Button(controls, text="Open PDF", command=self._browse_pdf).pack(side="left", padx=5)
        self.file_label = ttk.Label(controls, text="No file selected", style="Path.TLabel")
        self.file_label.pack(side="left", padx=10, fill="x", expand=True)
        
        ttk.Button(controls, text="Save As...", style="Accent.TButton", 
                   command=self._start_save).pack(side="right", padx=5)

        self.info_label = ttk.Label(self, text="", style="Desc.TLabel")
        self.info_label.pack(padx=20, anchor="w")

        # Scrollable area for thumbnails
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=20, pady=10)

        self.canvas = tk.Canvas(container, bg="#181825", highlightthickness=0)
        self.v_scroll = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.thumb_frame = ttk.Frame(self.canvas)
        self._canvas_win = self.canvas.create_window((0, 0), window=self.thumb_frame, anchor="nw")

        self.thumb_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

        self.placeholder = ttk.Label(self.canvas, text="Load PDF to see preview", style="Desc.TLabel")
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # Progress
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", padx=20, pady=(0, 10))

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self._canvas_win, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _browse_pdf(self):
        path = filedialog.askopenfilename(title="Select PDF", filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_path = path
            self.file_label.config(text=os.path.basename(path))
            threading.Thread(target=self._load_pdf, args=(path,), daemon=True).start()

    def _load_pdf(self, path):
        try:
            self.after(0, lambda: self.placeholder.place_forget())
            doc = fitz.open(path)
            total = len(doc)
            self.page_order = list(range(total))
            self._thumb_photos = {}
            
            self.after(0, lambda: self._clear_thumbs())
            self.after(0, lambda: self.progress.config(maximum=total, value=0))
            self.status_callback(f"Loading {total} pages...")

            thumb_width = 280
            for i in range(total):
                page = doc[i]
                scale = thumb_width / page.rect.width
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                photo = ImageTk.PhotoImage(img)
                self._thumb_photos[i] = photo
                
                self.after(0, lambda v=i+1: self.progress.config(value=v))

            doc.close()
            self.after(0, self._render_grid)
            self.after(0, lambda: self.info_label.config(text=f"Total Pages: {total}"))
            self.status_callback("Ready to reorder")
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to load PDF: {e}"))

    def _clear_thumbs(self):
        for w in self.thumb_frame.winfo_children():
            w.destroy()

    def _render_grid(self):
        self._clear_thumbs()
        cols = 5
        # Ensure equal spacing
        for c in range(cols):
            self.thumb_frame.columnconfigure(c, weight=1, uniform="thumb")
        
        for idx, page_idx in enumerate(self.page_order):
            card = ttk.Frame(self.thumb_frame, style="Surface.TFrame", padding=5)
            card.grid(row=idx // cols, column=idx % cols, padx=10, pady=10)
            
            # Thumbnail
            lbl = tk.Label(card, image=self._thumb_photos[page_idx], bg="#1e1e2e", bd=1, relief="solid")
            lbl.pack()
            
            # Drag events on the label
            lbl.bind("<ButtonPress-1>", lambda e, i=idx: self._on_drag_start(e, i))
            lbl.bind("<B1-Motion>", self._on_drag_motion)
            lbl.bind("<ButtonRelease-1>", self._on_drag_stop)

            # Page number
            num_lbl = ttk.Label(card, text=f"Page {page_idx + 1}", style="Desc.TLabel")
            num_lbl.pack(pady=(2, 0))

    def _on_drag_start(self, event, index):
        self._drag_data["item"] = index
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self.status_callback(f"Moving page {self.page_order[index] + 1}...")

    def _on_drag_motion(self, event):
        # We don't actually move the widget visually for simplicity, 
        # but we could add a shadow if needed. 
        pass

    def _on_drag_stop(self, event):
        if self._drag_data["item"] is None: return
        
        # Find which card we are over
        x, y = event.x_root, event.y_root
        target_idx = None
        
        for idx, child in enumerate(self.thumb_frame.winfo_children()):
            x1 = child.winfo_rootx()
            y1 = child.winfo_rooty()
            x2 = x1 + child.winfo_width()
            y2 = y1 + child.winfo_height()
            
            if x1 <= x <= x2 and y1 <= y <= y2:
                target_idx = idx
                break
        
        if target_idx is not None and target_idx != self._drag_data["item"]:
            # Move item in list
            item = self.page_order.pop(self._drag_data["item"])
            self.page_order.insert(target_idx, item)
            self._render_grid()
            self.status_callback(f"Moved page {item+1} to position {target_idx+1}")
        
        self._drag_data["item"] = None

    def _start_save(self):
        if not self.pdf_path:
            messagebox.showwarning("No File", "Please open a PDF first.")
            return
            
        out_path = filedialog.asksaveasfilename(
            title="Save Reordered PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")]
        )
        if out_path:
            threading.Thread(target=self._do_save, args=(out_path,), daemon=True).start()

    def _do_save(self, out_path):
        try:
            self.status_callback("Saving reordered PDF...")
            src = fitz.open(self.pdf_path)
            new_doc = fitz.open()
            
            for page_idx in self.page_order:
                new_doc.insert_pdf(src, from_page=page_idx, to_page=page_idx)
            
            new_doc.save(out_path, garbage=4, deflate=True)
            new_doc.close()
            src.close()
            
            self.status_callback("Save complete")
            self.after(0, lambda: messagebox.showinfo("Done", f"Reordered PDF saved to:\n{out_path}"))
        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
