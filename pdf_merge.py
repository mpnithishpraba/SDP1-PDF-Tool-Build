"""
PDF Merger Module
Merge multiple PDFs with drag reorder, preserving quality.
Includes scrollable multi-page PDF preview for selected and merged PDFs.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import fitz  # PyMuPDF
import os
from PIL import Image, ImageTk


class PdfMergeFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.pdf_paths = []
        self._thumb_photos = []      # keep PhotoImage references alive
        self._merged_path = None     # path to last merged PDF
        self._showing_merged = False # whether merged preview is active
        self._build_ui()

    def _build_ui(self):
        title = ttk.Label(self, text="PDF Merger", style="Title.TLabel")
        title.pack(pady=(10, 5))

        desc = ttk.Label(self, text="Combine multiple PDFs into one, preserving all quality",
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

        # File list
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True, pady=5)

        self.listbox = tk.Listbox(list_frame, selectmode="single",
                                  bg="#313244", fg="#cdd6f4",
                                  selectbackground="#89b4fa", selectforeground="#1e1e2e",
                                  relief="flat", font=("Segoe UI", 12), height=3)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # No longer binding Selection to preview, as we show collective preview

        # Controls
        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Add PDFs", command=self._add_pdfs).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Remove", command=self._remove_selected).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="▲ Up", command=self._move_up).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="▼ Down", command=self._move_down).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self._clear_all).pack(side="left", padx=2)

        # Info
        self.info_label = ttk.Label(left, text="0 files added", style="Desc.TLabel")
        self.info_label.pack(padx=0, anchor="w")

        # Progress
        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 5))

        self.progress_label = ttk.Label(left, text="", style="Desc.TLabel")
        self.progress_label.pack()

        # Merge button
        ttk.Button(left, text="Merge PDFs", style="Accent.TButton",
                   command=self._start_merge).pack(pady=15)

        # ── RIGHT PANE (preview) ────────────────────────────────────────
        right = ttk.Frame(panes)
        right.grid(row=0, column=1, sticky="nsew")

        # Toolbar row
        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(0, 5))
        self._preview_title = ttk.Label(toolbar, text="PDF Preview",
                                         style="Path.TLabel")
        self._preview_title.pack(side="left")

        # Preview info (page count, size)
        self._preview_info = ttk.Label(toolbar, text="", style="Desc.TLabel")
        self._preview_info.pack(side="right")

        # Scrollable canvas for page thumbnails
        preview_container = ttk.Frame(right)
        preview_container.pack(fill="both", expand=True, pady=(0, 15))

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
            text="Load PDF to see preview",
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

    # ── Listbox selection → preview ─────────────────────────────────────
    # Collective preview of all files
    def _refresh_preview(self):
        """Trigger collective preview of all added PDF paths."""
        if self.pdf_paths:
            self._showing_merged = False
            self._render_preview(self.pdf_paths, label="PDF Preview")
        else:
            self._clear_preview_ui()

    def _clear_preview_ui(self):
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self._thumb_photos.clear()
        self._preview_info.config(text="")
        self._preview_title.config(text="PDF Preview")
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _on_listbox_select(self, event=None):
        pass

    # ── Render multi-page preview ───────────────────────────────────────
    def _render_preview(self, pdf_paths, label="PDF Preview"):
        """Render all pages of one or more PDFs as thumbnails in the preview panel."""
        if isinstance(pdf_paths, str):
            pdf_paths = [pdf_paths]
        self._placeholder.place_forget()
        # Clear previous thumbnails
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self._thumb_photos.clear()

        # Show loading
        loading = ttk.Label(self.thumb_frame, text="Rendering pages…",
                            style="Desc.TLabel")
        loading.grid(row=0, column=0, padx=40, pady=40)

        self._preview_title.config(text=label)
        self._preview_info.config(text="")

        threading.Thread(target=self._render_worker,
                         args=(pdf_paths, label), daemon=True).start()

    def _render_worker(self, pdf_paths, label):
        """Background worker: render pages from all provided PDFs to images."""
        try:
            images = []
            thumb_width = 300  # Standardized 3-column thumbnail width
            total_pages = 0
            total_size_bytes = 0

            for path in pdf_paths:
                doc = fitz.open(path)
                total_pages += len(doc)
                total_size_bytes += os.path.getsize(path)
                for i in range(len(doc)):
                    page = doc[i]
                    scale = thumb_width / page.rect.width
                    mat = fitz.Matrix(scale, scale)
                    pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    images.append(img)
                doc.close()

            size_mb = total_size_bytes / (1024 * 1024)
            count = len(pdf_paths)
            info_text = f"{count} files  •  {total_pages} pages  •  {size_mb:.1f} MB"

            self.after(0, lambda: self._populate_thumbs(images, label, info_text))
        except Exception as e:
            self.after(0, lambda: self._preview_info.config(
                text=f"Cannot preview: {e}"))

    def _populate_thumbs(self, images, label, info_text):
        """Place page thumbnails in a grid (main thread)."""
        # Clear loading
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self._thumb_photos.clear()

        self._preview_title.config(text=label)
        self._preview_info.config(text=info_text)

        cols = 3  # Force exactly 3 columns as requested

        for c in range(cols):
            self.thumb_frame.columnconfigure(c, weight=1)

        for idx, img in enumerate(images):
            photo = ImageTk.PhotoImage(img)
            self._thumb_photos.append(photo)

            row, col = divmod(idx, cols)

            # Card frame for each page
            card = ttk.Frame(self.thumb_frame, style="Surface.TFrame")
            card.grid(row=row, column=col, padx=4, pady=4, sticky="n")

            # Image label
            img_label = tk.Label(card, image=photo, bd=1, relief="solid")
            img_label.pack(padx=3, pady=(3, 1))

            # Page number label
            page_label = ttk.Label(card, text=f"Page {idx + 1}",
                                    style="Desc.TLabel")
            page_label.pack(pady=(0, 3))

        # Reset scroll position
        self.preview_canvas.yview_moveto(0)
        self._on_thumb_configure()

    # ── File management ─────────────────────────────────────────────────
    def _add_pdfs(self):
        paths = filedialog.askopenfilenames(
            title="Select PDFs",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        for p in paths:
            self.pdf_paths.append(p)
            try:
                doc = fitz.open(p)
                pages = len(doc)
                doc.close()
                self.listbox.insert("end", f"{os.path.basename(p)}  ({pages} pages)")
            except:
                self.listbox.insert("end", f"{os.path.basename(p)}  (error reading)")
        self.info_label.config(text=f"{len(self.pdf_paths)} files added")

        # Auto-preview collective
        if self.pdf_paths:
            self._refresh_preview()

    def _remove_selected(self):
        sel = self.listbox.curselection()
        if sel:
            idx = sel[0]
            self.listbox.delete(idx)
            self.pdf_paths.pop(idx)
            self.info_label.config(text=f"{len(self.pdf_paths)} files added")
            if not self.pdf_paths:
                self._clear_preview_ui()
            else:
                self._refresh_preview()

    def _move_up(self):
        sel = self.listbox.curselection()
        if sel and sel[0] > 0:
            idx = sel[0]
            self.pdf_paths[idx], self.pdf_paths[idx - 1] = self.pdf_paths[idx - 1], self.pdf_paths[idx]
            text = self.listbox.get(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx - 1, text)
            self._refresh_preview()
            self.listbox.select_set(idx - 1)

    def _move_down(self):
        sel = self.listbox.curselection()
        if sel and sel[0] < self.listbox.size() - 1:
            idx = sel[0]
            self.pdf_paths[idx], self.pdf_paths[idx + 1] = self.pdf_paths[idx + 1], self.pdf_paths[idx]
            text = self.listbox.get(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx + 1, text)
            self._refresh_preview()
            self.listbox.select_set(idx + 1)

    def _clear_all(self):
        self.listbox.delete(0, "end")
        self.pdf_paths.clear()
        self.info_label.config(text="0 files added")
        self._clear_preview_ui()
        self._merged_path = None
        self._showing_merged = False

    # ── Merge ───────────────────────────────────────────────────────────
    def _start_merge(self):
        if len(self.pdf_paths) < 2:
            messagebox.showwarning("Not Enough", "Please add at least 2 PDF files.")
            return

        out_path = filedialog.asksaveasfilename(
            title="Save Merged PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")]
        )
        if not out_path:
            return

        threading.Thread(target=self._do_merge, args=(out_path,), daemon=True).start()

    def _do_merge(self, out_path):
        try:
            total = len(self.pdf_paths)
            self.after(0, lambda: self.progress.config(maximum=total, value=0))
            self.status_callback(f"Merging {total} PDFs...")

            merged = fitz.open()

            for i, path in enumerate(self.pdf_paths):
                try:
                    src = fitz.open(path)
                    merged.insert_pdf(src)
                    src.close()
                except Exception as e:
                    self.status_callback(f"Warning: Error with {os.path.basename(path)}: {e}")

                self.after(0, lambda v=i + 1: self.progress.config(value=v))
                self.after(0, lambda v=i + 1, t=total: self.progress_label.config(
                    text=f"File {v}/{t}"))

            merged.save(out_path, garbage=4, deflate=True)
            merged.close()

            total_pages = 0
            try:
                check_doc = fitz.open(out_path)
                total_pages = len(check_doc)
                check_doc.close()
            except:
                pass

            out_size = os.path.getsize(out_path) / (1024 * 1024)
            self._merged_path = out_path
            self._showing_merged = True
            self.status_callback(f"Merged {total} PDFs ({total_pages} pages, {out_size:.1f} MB)")

            # Show merged PDF preview — all pages
            self.after(0, lambda: self._render_preview(out_path, label="Merged PDF Preview"))
            self.after(0, lambda: messagebox.showinfo("Done",
                                                       f"Merged {total} files ({total_pages} pages)\n"
                                                       f"Size: {out_size:.1f} MB\n{out_path}"))
            self.after(0, lambda: self.progress_label.config(text="Done!"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
