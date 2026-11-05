#!/usr/bin/env python3
"""Dymo LetraTag LT-200B label maker with rich text formatting."""

import os
import subprocess
import tempfile
import tkinter as tk
import xml.sax.saxutils as saxutils
from tkinter import ttk

from PIL import Image, ImageTk

FONT_SIZE = 14
PREVIEW_SCALE = 4
PANGO_FONT = f"Sans {FONT_SIZE}"
FORMAT_TAGS = {"bold", "italic", "strike"}


class LabelMaker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Dymo Label Maker")
        self.root.resizable(False, False)
        self._tmp_image = None
        self._preview_photo = None
        self._setup_ui()
        self._setup_bindings()

    def _setup_ui(self):
        toolbar = ttk.Frame(self.root, padding=4)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="B", width=3, command=lambda: self._toggle("bold")).pack(side="left", padx=2)
        ttk.Button(toolbar, text="I", width=3, command=lambda: self._toggle("italic")).pack(side="left", padx=2)
        ttk.Button(toolbar, text="S̶", width=3, command=lambda: self._toggle("strike")).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(toolbar, text="Print", command=self._print).pack(side="right", padx=2)

        frame = ttk.Frame(self.root, padding=4)
        frame.pack(fill="x")

        self.text = tk.Text(frame, height=2, width=50, wrap="none", font=("Sans", 12))
        self.text.pack(fill="x")
        self.text.tag_configure("bold", font=("Sans", 12, "bold"))
        self.text.tag_configure("italic", font=("Sans", 12, "italic"))
        self.text.tag_configure("bold_italic", font=("Sans", 12, "bold italic"))
        self.text.tag_configure("strike", overstrike=True)

        preview_frame = ttk.LabelFrame(self.root, text="Preview", padding=8)
        preview_frame.pack(fill="x", padx=4, pady=4)

        self.preview_label = tk.Label(preview_frame, bg="white", relief="sunken",
                                      width=50, height=PREVIEW_SCALE * 30 // 16)
        self.preview_label.pack()
        self.status = ttk.Label(preview_frame, text="Type above to preview")
        self.status.pack()

    def _setup_bindings(self):
        self.text.bind("<KeyRelease>", self._on_change)
        self.text.bind("<ButtonRelease>", self._on_change)
        self.text.bind("<Return>", lambda e: "break")
        self.root.bind("<Control-b>", lambda e: self._toggle("bold"))
        self.root.bind("<Control-i>", lambda e: self._toggle("italic"))
        self.root.bind("<Control-p>", lambda e: self._print())

    def _toggle(self, tag):
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return

        if tag in self.text.tag_names(start):
            self.text.tag_remove(tag, start, end)
        else:
            self.text.tag_add(tag, start, end)

        self._sync_bold_italic(start, end)
        self._update_preview()

    def _sync_bold_italic(self, start, end):
        self.text.tag_remove("bold_italic", start, end)
        n = len(self.text.get("1.0", "end-1c"))
        for i in range(n):
            pos = f"1.{i}"
            tags = set(self.text.tag_names(pos))
            if "bold" in tags and "italic" in tags:
                self.text.tag_add("bold_italic", pos, f"1.{i + 1}")

    def _char_tags(self):
        content = self.text.get("1.0", "end-1c")
        return [
            (ch, frozenset(t for t in self.text.tag_names(f"1.{i}") if t in FORMAT_TAGS))
            for i, ch in enumerate(content)
        ]

    def _to_pango(self):
        chars = self._char_tags()
        if not chars:
            return None

        groups, cur_text, cur_tags = [], chars[0][0], chars[0][1]
        for ch, tags in chars[1:]:
            if tags == cur_tags:
                cur_text += ch
            else:
                groups.append((cur_text, cur_tags))
                cur_text, cur_tags = ch, tags
        groups.append((cur_text, cur_tags))

        parts = []
        for text, tags in groups:
            s = saxutils.escape(text)
            if "strike" in tags:
                s = f"<s>{s}</s>"
            if "italic" in tags:
                s = f"<i>{s}</i>"
            if "bold" in tags:
                s = f"<b>{s}</b>"
            parts.append(s)

        return f'<span font="{PANGO_FONT}">{"".join(parts)}</span>'

    def _on_change(self, _event=None):
        self._update_preview()

    def _update_preview(self, _event=None):
        markup = self._to_pango()
        if not markup:
            self.status.config(text="Type above to preview")
            return

        try:
            if self._tmp_image:
                try:
                    os.unlink(self._tmp_image)
                except OSError:
                    pass

            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            self._tmp_image = tmp.name
            tmp.close()

            result = subprocess.run(
                ["magick", "-background", "white", "-size", "x30", f"pango:{markup}", self._tmp_image],
                capture_output=True, text=True,
            )

            if result.returncode != 0:
                self.status.config(text=f"Error: {result.stderr.strip()[:80]}")
                return

            img = Image.open(self._tmp_image)
            w, h = img.size
            preview = img.resize((w * PREVIEW_SCALE, h * PREVIEW_SCALE), Image.NEAREST)
            self._preview_photo = ImageTk.PhotoImage(preview)
            self.preview_label.configure(image=self._preview_photo,
                                         width=w * PREVIEW_SCALE, height=h * PREVIEW_SCALE)
            self.status.config(text=f"{w}×{h}px — ready to print")

        except Exception as e:
            self.status.config(text=f"Error: {e}")

    def _print(self):
        if not self._tmp_image or not os.path.exists(self._tmp_image):
            self._update_preview()
        if not self._tmp_image or not os.path.exists(self._tmp_image):
            return
        result = subprocess.run(["dymo_bluetooth", self._tmp_image], capture_output=True, text=True)
        self.status.config(text="Printed!" if result.returncode == 0 else f"Error: {result.stderr.strip()[:80]}")

    def run(self):
        self.root.mainloop()
        if self._tmp_image:
            try:
                os.unlink(self._tmp_image)
            except OSError:
                pass


if __name__ == "__main__":
    LabelMaker().run()
