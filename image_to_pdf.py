"""
Image to PDF Converter Module
Converts images (JPG, PNG, BMP, WEBP) to PDF with reordering and sizing options.
Includes image preview panel on the right side.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import fitz
from PIL import Image, ImageTk
import os
import io


class ImageToPdfFrame(ttk.Frame):
    def __init__(self, parent, status_callback=None):
        super().__init__(parent)
        self.status_callback = status_callback or (lambda msg: None)
        self.image_paths = []
        self._preview_photo = None
        self._build_ui()

    def _build_ui(self):
        title = ttk.Label(self, text="Image → PDF", style="Title.TLabel")
        title.pack(pady=(10, 5))

        desc = ttk.Label(self, text="Combine images into a PDF without quality loss",
                         style="Desc.TLabel")
        desc.pack(pady=(0, 10))

        panes = ttk.Frame(self)
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        panes.columnconfigure(0, weight=1, uniform="pane")
        panes.columnconfigure(1, weight=1, uniform="pane")
        panes.rowconfigure(0, weight=1)
        panes.grid_propagate(False)

        left = ttk.Frame(panes)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.pack_propagate(False)

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

        self.listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Add Images", command=self._add_images).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Remove", command=self._remove_selected).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="▲ Up", command=self._move_up).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="▼ Down", command=self._move_down).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self._clear_all).pack(side="left", padx=2)

        opts_frame = ttk.LabelFrame(left, text="Options", padding=10)
        opts_frame.pack(fill="x", pady=10)

        self.sizing_var = tk.StringVar(value="fit")
        ttk.Radiobutton(opts_frame, text="Fit page to image size",
                         variable=self.sizing_var, value="fit").pack(anchor="w")
        ttk.Radiobutton(opts_frame, text="Scale to A4 (210×297mm)",
                         variable=self.sizing_var, value="a4").pack(anchor="w")

        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 5))

        self.progress_label = ttk.Label(left, text="", style="Desc.TLabel")
        self.progress_label.pack()

        ttk.Button(left, text="Create PDF", style="Accent.TButton",
                   command=self._start_convert).pack(pady=15)

        right = ttk.Frame(panes)
        right.grid(row=0, column=1, sticky="nsew")

        self._preview_title = ttk.Label(right, text="PDF Preview",
                                         style="Path.TLabel")
        self._preview_title.pack(pady=(0, 5))

        self._preview_container = ttk.Frame(right)
        self._preview_container.pack(fill="both", expand=True, pady=(0, 15))

        self._preview_canvas = tk.Canvas(self._preview_container,
                                         highlightthickness=0, bd=0)
        self.v_scroll = ttk.Scrollbar(self._preview_container, orient="vertical",
                                      command=self._preview_canvas.yview)
        self._preview_canvas.configure(yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self._preview_canvas.pack(side="left", fill="both", expand=True)

        self._placeholder = ttk.Label(
            self._preview_container,
            text="Add images to see previews",
            style="Desc.TLabel")
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self.thumb_frame = ttk.Frame(self._preview_canvas)
        self._canvas_win = self._preview_canvas.create_window(
            (0, 0), window=self.thumb_frame, anchor="n")

        self.thumb_frame.bind("<Configure>", self._on_thumb_configure)
        self._preview_canvas.bind("<Configure>", self._on_canvas_resize)
        self._preview_canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

        self._preview_info = ttk.Label(right, text="", style="Desc.TLabel")
        self._preview_info.pack(pady=(5, 0))

    def _on_thumb_configure(self, _event=None):
        self._preview_canvas.configure(
            scrollregion=self._preview_canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        self._preview_canvas.itemconfigure(self._canvas_win, width=event.width)
        self._preview_canvas.coords(self._canvas_win, event.width // 2, 0)

    def _on_mousewheel(self, event):
        widget = event.widget
        try:
            if self._preview_canvas.winfo_containing(event.x_root, event.y_root) \
                    in (self._preview_canvas, self.thumb_frame) or \
                    str(widget) == str(self._preview_canvas) or \
                    str(widget).startswith(str(self.thumb_frame)):
                self._preview_canvas.yview_scroll(
                    int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _on_listbox_select(self, event=None):
        pass

    def _render_all_previews(self):
        self._placeholder.place_forget()
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        
        if not self.image_paths:
            self._placeholder.place(relx=0.5, rely=0.5, anchor="center")
            self._preview_info.config(text="")
            return

        self._preview_info.config(text=f"{len(self.image_paths)} images added")
        threading.Thread(target=self._render_worker, daemon=True).start()

    def _render_worker(self):
        try:
            images = []
            thumb_width = 250
            for path in self.image_paths:
                try:
                    img = Image.open(path)
                    scale = thumb_width / img.width
                    new_size = (int(img.width * scale), int(img.height * scale))
                    img = img.resize(new_size, Image.LANCZOS)
                    images.append(img)
                except:
                    continue
            
            self.after(0, lambda: self._populate_thumbs(images))
        except Exception as e:
            self.after(0, lambda: self._preview_info.config(
                text=f"Cannot preview: {e}"))

    def _populate_thumbs(self, images):
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self._preview_photos = []

        cols = 1

        for c in range(cols):
            self.thumb_frame.columnconfigure(c, weight=1)

        for idx, img in enumerate(images):
            photo = ImageTk.PhotoImage(img)
            self._preview_photos.append(photo)

            row, col = divmod(idx, cols)

            card = ttk.Frame(self.thumb_frame, style="Surface.TFrame")
            card.grid(row=row, column=col, padx=4, pady=4, sticky="n")

            img_label = tk.Label(card, image=photo, bd=1, relief="solid")
            img_label.pack(padx=3, pady=(3, 1))

            name = os.path.basename(self.image_paths[idx])
            if len(name) > 15: name = name[:12] + "..."
            lbl = ttk.Label(card, text=name, style="Desc.TLabel")
            lbl.pack(pady=(0, 3))

        self._preview_canvas.yview_moveto(0)
        self._on_thumb_configure()

    def _add_images(self):
        paths = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("All files", "*.*")
            ]
        )
        for p in paths:
            self.image_paths.append(p)
            self.listbox.insert("end", os.path.basename(p))
        self._render_all_previews()

    def _remove_selected(self):
        sel = self.listbox.curselection()
        if sel:
            idx = sel[0]
            self.listbox.delete(idx)
            self.image_paths.pop(idx)
            self._render_all_previews()

    def _move_up(self):
        sel = self.listbox.curselection()
        if sel and sel[0] > 0:
            idx = sel[0]
            self.image_paths[idx], self.image_paths[idx - 1] = self.image_paths[idx - 1], self.image_paths[idx]
            text = self.listbox.get(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx - 1, text)
            self._render_all_previews()
            self.listbox.select_set(idx - 1)

    def _move_down(self):
        sel = self.listbox.curselection()
        if sel and sel[0] < self.listbox.size() - 1:
            idx = sel[0]
            self.image_paths[idx], self.image_paths[idx + 1] = self.image_paths[idx + 1], self.image_paths[idx]
            text = self.listbox.get(idx)
            self.listbox.delete(idx)
            self.listbox.insert(idx + 1, text)
            self._render_all_previews()
            self.listbox.select_set(idx + 1)

    def _clear_all(self):
        self.listbox.delete(0, "end")
        self.image_paths.clear()
        self._render_all_previews()

    def _start_convert(self):
        if not self.image_paths:
            messagebox.showwarning("No Images", "Please add images first.")
            return

        out_path = filedialog.asksaveasfilename(
            title="Save PDF As",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")]
        )
        if not out_path:
            return

        threading.Thread(target=self._do_convert, args=(out_path,), daemon=True).start()

    def _do_convert(self, out_path):
        try:
            doc = fitz.open()
            total = len(self.image_paths)
            self.after(0, lambda: self.progress.config(maximum=total, value=0))
            self.status_callback(f"Creating PDF from {total} images...")

            A4_WIDTH = 595.28
            A4_HEIGHT = 841.89

            for i, img_path in enumerate(self.image_paths):
                try:
                    pil_img = Image.open(img_path)
                    if pil_img.mode == "RGBA":
                        bg = Image.new("RGB", pil_img.size, (255, 255, 255))
                        bg.paste(pil_img, mask=pil_img.split()[3])
                        pil_img = bg
                    elif pil_img.mode != "RGB":
                        pil_img = pil_img.convert("RGB")

                    img_w, img_h = pil_img.size

                    if self.sizing_var.get() == "a4":
                        page = doc.new_page(width=A4_WIDTH, height=A4_HEIGHT)
                        margin = 20
                        avail_w = A4_WIDTH - 2 * margin
                        avail_h = A4_HEIGHT - 2 * margin
                        scale = min(avail_w / img_w, avail_h / img_h)
                        new_w = img_w * scale
                        new_h = img_h * scale
                        x0 = (A4_WIDTH - new_w) / 2
                        y0 = (A4_HEIGHT - new_h) / 2
                        rect = fitz.Rect(x0, y0, x0 + new_w, y0 + new_h)
                    else:
                        page = doc.new_page(width=img_w, height=img_h)
                        rect = fitz.Rect(0, 0, img_w, img_h)

                    buf = io.BytesIO()
                    pil_img.save(buf, format="PNG")
                    buf.seek(0)
                    page.insert_image(rect, stream=buf.getvalue())

                except Exception as e:
                    self.status_callback(f"Warning: Skipped {os.path.basename(img_path)}: {e}")
                    continue

                self.after(0, lambda v=i + 1: self.progress.config(value=v))
                self.after(0, lambda v=i + 1, t=total: self.progress_label.config(
                    text=f"Image {v}/{t}"))

            doc.save(out_path, garbage=4, deflate=True)
            doc.close()

            self.status_callback(f"Created PDF with {total} images")
            self.after(0, lambda: messagebox.showinfo("Done", f"PDF saved to:\n{out_path}"))
            self.after(0, lambda: self.progress_label.config(text="Done!"))

        except Exception as e:
            self.status_callback(f"Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))