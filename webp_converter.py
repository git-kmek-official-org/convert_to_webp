import os
import glob
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image

SUPPORTED_EXTS = ("*.jpg", "*.jpeg", "*.gif", "*.png",
                  "*.JPG", "*.JPEG", "*.GIF", "*.PNG")
IMAGE_FILTER = [
    ("画像ファイル", "*.jpg *.jpeg *.gif *.png *.JPG *.JPEG *.GIF *.PNG"),
    ("すべてのファイル", "*.*"),
]
WEBP_QUALITY = 90

# ── カラーパレット (macOS ライト) ───────────────────────────
BG      = "#ececec"   # ウィンドウ背景 (macOS window gray)
SURFACE = "#f5f5f5"   # カード背景
SURFACE2= "#ffffff"   # 入力欄・テーブル
BORDER  = "#d1d1d6"   # 区切り線
ACCENT  = "#007aff"   # macOS Blue
ACCENT_H= "#0051d5"   # ホバー
FG      = "#1c1c1e"   # メインテキスト
FG_DIM  = "#8e8e93"   # サブテキスト (macOS secondary label)
SUCCESS = "#34c759"   # macOS Green
ERROR   = "#ff3b30"   # macOS Red


def unique_webp_path(base: str) -> str:
    candidate = base + ".webp"
    if not os.path.exists(candidate):
        return candidate
    n = 1
    while True:
        candidate = f"{base}({n}).webp"
        if not os.path.exists(candidate):
            return candidate
        n += 1


def find_images(directory: str) -> list[str]:
    files = []
    for ext in SUPPORTED_EXTS:
        files.extend(glob.glob(os.path.join(directory, ext)))
    seen = set()
    result = []
    for f in files:
        key = f.lower()
        if key not in seen:
            seen.add(key)
            result.append(f)
    return sorted(result)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WebP Converter")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(500, 230)
        self._apply_style()
        self._build_ui()
        initial_dir = os.path.dirname(os.path.abspath(__file__))
        self._set_directory(initial_dir)
        # 起動時に最前面へ
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.focus_force()

    # ── テーマ適用 ──────────────────────────────────────────
    def _apply_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("Treeview",
            background=SURFACE2, foreground=FG,
            fieldbackground=SURFACE2, borderwidth=0,
            rowheight=28, font=("Helvetica Neue", 10))
        s.configure("Treeview.Heading",
            background=SURFACE, foreground=FG_DIM,
            relief="flat", font=("Helvetica Neue", 9))
        s.map("Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "white")])
        s.map("Treeview.Heading",
            background=[("active", BORDER)])

        s.configure("Vertical.TScrollbar",
            background=BORDER, troughcolor=SURFACE,
            borderwidth=0, arrowcolor=FG_DIM, width=8)

        s.configure("TProgressbar",
            background=ACCENT, troughcolor=BORDER,
            borderwidth=0, thickness=5)

        s.configure("TScale",
            background=SURFACE, troughcolor=BORDER,
            sliderlength=28, sliderrelief="flat")
        s.map("TScale", background=[("active", ACCENT)])

    # ── UI構築 ──────────────────────────────────────────────
    def _build_ui(self):
        FONT    = "Helvetica Neue"
        FONT_SM = (FONT, 10, "bold")   # semibold 相当
        FONT_XS = (FONT, 9, "bold")    # ラベル semibold

        # ツールバー風ヘッダー（macOS タイトルバー下の帯）
        hdr = tk.Frame(self, bg=SURFACE, pady=10,
                       highlightbackground=BORDER, highlightthickness=1)
        hdr.pack(fill="x")
        tk.Label(hdr, text="WebP Converter", bg=SURFACE, fg=FG,
                 font=(FONT, 14, "bold")).pack(side="left", padx=18)
        tk.Label(hdr, text="JPG / PNG / GIF → WebP", bg=SURFACE, fg=FG_DIM,
                 font=(FONT, 9)).pack(side="left")

        # ── フッター（常に表示・先にパック） ────────────────
        footer = tk.Frame(self, bg=BG)
        footer.pack(side="bottom", fill="x", padx=18, pady=(0, 14))

        self.progress = ttk.Progressbar(footer, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 10))

        bottom = tk.Frame(footer, bg=BG)
        bottom.pack(fill="x")

        self.status_var = tk.StringVar(value="フォルダを選択してください")
        tk.Label(bottom, textvariable=self.status_var, anchor="w",
                 bg=BG, fg=FG_DIM, font=FONT_XS
                 ).pack(side="left", fill="x", expand=True)

        btn_row = tk.Frame(bottom, bg=BG)
        btn_row.pack(side="right")

        self.convert_btn = self._btn(btn_row, "変換開始", self._start_convert, primary=True)
        self.convert_btn.pack(side="left", padx=(0, 8))

        self.folder_btn = self._btn(btn_row, "フォルダを開く", lambda: None, primary=True)

        self.close_btn = self._btn(btn_row, "閉じる", self.destroy, muted=True)
        self.close_btn.pack(side="left")

        # ── body（ファイル一覧が縮む） ──────────────────────
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(14, 0))

        # ── フォルダ選択エリア ──────────────────────────────
        dir_outer = tk.Frame(body, bg=BORDER, padx=1, pady=1)
        dir_outer.pack(fill="x", pady=(0, 10))
        dir_card = tk.Frame(dir_outer, bg=SURFACE, padx=14, pady=10)
        dir_card.pack(fill="x")

        tk.Label(dir_card, text="選択中のファイル", bg=SURFACE,
                 fg=FG_DIM, font=FONT_XS).pack(anchor="w", pady=(0, 6))

        dir_row = tk.Frame(dir_card, bg=SURFACE)
        dir_row.pack(fill="x")

        self.dir_var = tk.StringVar()
        entry_wrap = tk.Frame(dir_row, bg=BORDER, padx=1, pady=1)
        entry_wrap.pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Entry(entry_wrap, textvariable=self.dir_var, state="readonly",
                 bg=SURFACE2, fg=FG, readonlybackground=SURFACE2,
                 relief="flat", font=FONT_SM, bd=0
                 ).pack(fill="x", ipady=5)

        self._btn(dir_row, "ファイルを選択", self._browse).pack(side="left")

        # ── ファイル一覧 ────────────────────────────────────
        list_outer = tk.Frame(body, bg=BORDER, padx=1, pady=1)
        list_outer.pack(fill="both", expand=True, pady=(0, 10))

        cols = ("file", "size", "status")
        self.tree = ttk.Treeview(list_outer, columns=cols, show="headings",
                                 selectmode="none")
        self.tree.heading("file",   text="ファイル名")
        self.tree.heading("size",   text="サイズ")
        self.tree.heading("status", text="ステータス")
        self.tree.column("file",   width=360, stretch=True)
        self.tree.column("size",   width=90,  anchor="e", stretch=False)
        self.tree.column("status", width=140, anchor="center", stretch=False)

        vsb = ttk.Scrollbar(list_outer, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("done",  foreground=SUCCESS)
        self.tree.tag_configure("error", foreground=ERROR)
        self.tree.tag_configure("skip",  foreground=FG_DIM)

        # ── オプションエリア ────────────────────────────────
        opt_outer = tk.Frame(body, bg=BORDER, padx=1, pady=1)
        opt_outer.pack(fill="x", pady=(0, 10))
        opt_card = tk.Frame(opt_outer, bg=SURFACE, padx=14, pady=10)
        opt_card.pack(fill="x")

        tk.Label(opt_card, text="変換オプション", bg=SURFACE, fg=FG_DIM,
                 font=FONT_XS).pack(anchor="w", pady=(0, 8))

        opt_row = tk.Frame(opt_card, bg=SURFACE)
        opt_row.pack(fill="x")

        # 品質スライダー: 低品質 ←スライダー→ 高品質
        tk.Label(opt_row, text="WebP 品質", bg=SURFACE, fg=FG,
                 font=FONT_SM).pack(side="left", padx=(0, 14))

        tk.Label(opt_row, text="低品質", bg=SURFACE, fg=FG_DIM,
                 font=FONT_XS).pack(side="left", padx=(0, 4))

        self.quality_var = tk.DoubleVar(value=WEBP_QUALITY)
        ttk.Scale(opt_row, from_=1, to=100, orient="horizontal",
                  variable=self.quality_var, length=200
                  ).pack(side="left")

        tk.Label(opt_row, text="高品質", bg=SURFACE, fg=FG_DIM,
                 font=FONT_XS).pack(side="left", padx=(4, 10))

        # キーボード入力対応の品質表示欄
        self.quality_entry = tk.Entry(opt_row, width=4, justify="center",
                                      font=(FONT, 10, "bold"),
                                      bg=ACCENT, fg="white",
                                      relief="flat", bd=4,
                                      insertbackground="white")
        self.quality_entry.insert(0, str(WEBP_QUALITY))
        self.quality_entry.pack(side="left", padx=(0, 22))

        def _slider_to_entry(*_):
            v = round(self.quality_var.get())
            self.quality_entry.delete(0, "end")
            self.quality_entry.insert(0, str(v))

        def _entry_to_slider(event=None):
            try:
                v = max(1, min(100, int(self.quality_entry.get())))
                self.quality_var.set(v)
                self.quality_entry.delete(0, "end")
                self.quality_entry.insert(0, str(v))
            except ValueError:
                _slider_to_entry()

        def _nudge(delta):
            try:
                v = max(1, min(100, int(self.quality_entry.get()) + delta))
            except ValueError:
                v = round(self.quality_var.get())
            self.quality_var.set(v)

        self.quality_var.trace_add("write", _slider_to_entry)
        self.quality_entry.bind("<Return>",    _entry_to_slider)
        self.quality_entry.bind("<FocusOut>",  _entry_to_slider)
        self.quality_entry.bind("<Up>",        lambda e: (_nudge(1),  "break")[1])
        self.quality_entry.bind("<Down>",      lambda e: (_nudge(-1), "break")[1])
        self.quality_entry.bind("<Shift-Up>",  lambda e: (_nudge(10), "break")[1])
        self.quality_entry.bind("<Shift-Down>",lambda e: (_nudge(-10),"break")[1])

        # 区切り線
        tk.Frame(opt_row, bg=BORDER, width=1).pack(side="left", fill="y", padx=(0, 16))

        self.delete_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opt_row, text="変換後に元ファイルを削除",
                       variable=self.delete_var,
                       bg=SURFACE, fg=FG, selectcolor=SURFACE2,
                       activebackground=SURFACE, activeforeground=FG,
                       font=FONT_SM).pack(side="left")


    # ── ボタンファクトリ ─────────────────────────────────────
    def _btn(self, parent, text, command, primary=False, muted=False):
        FONT = "Helvetica Neue"
        if primary:
            bg, fg, hover = ACCENT, "white", ACCENT_H
        elif muted:
            bg, fg, hover = BORDER, FG_DIM, "#c0c0c8"
        else:
            bg, fg, hover = SURFACE2, FG, BORDER

        b = tk.Button(parent, text=text, command=command,
                      bg=bg, fg=fg, relief="flat", bd=0,
                      font=(FONT, 10, "bold" if primary else "normal"),
                      padx=12, pady=5, cursor="hand2",
                      activebackground=hover, activeforeground=fg)
        b.bind("<Enter>", lambda _: b.config(bg=hover))
        b.bind("<Leave>", lambda _: b.config(bg=bg))
        return b

    # ── ファイル操作 ─────────────────────────────────────────
    def _browse(self):
        """ファイルダイアログで画像ファイルを直接選択する"""
        initial = self.dir_var.get() or "/"
        if not os.path.isdir(initial):
            initial = os.path.dirname(initial) or "/"
        files = filedialog.askopenfilenames(
            initialdir=initial,
            filetypes=IMAGE_FILTER,
            title="変換する画像ファイルを選択",
        )
        if files:
            self._set_files(list(files))

    def _set_directory(self, path: str):
        """起動時の初期スキャン用"""
        files = find_images(path)
        if files:
            self._set_files(files)
        else:
            self.dir_var.set(path)
            self.status_var.set("対象ファイルなし (jpg/jpeg/gif/png)")

    def _set_files(self, files: list[str]):
        first_dir = os.path.dirname(files[0]) if files else ""
        self.dir_var.set(first_dir)
        self.tree.delete(*self.tree.get_children())
        for f in files:
            size_str = f"{os.path.getsize(f)/1024:.1f} KB"
            self.tree.insert("", "end", iid=f, values=(
                os.path.basename(f), size_str, "待機中"))
        n = len(files)
        self.status_var.set(f"{n} 件のファイルを選択中")
        self.progress["value"] = 0

    # ── 変換処理 ─────────────────────────────────────────────
    def _start_convert(self):
        files = list(self.tree.get_children())
        if not files:
            messagebox.showinfo("情報", "変換対象のファイルがありません。")
            return
        self.convert_btn.config(state="disabled")
        self.progress["maximum"] = len(files)
        self.progress["value"] = 0
        threading.Thread(target=self._convert_all, args=(files,), daemon=True).start()

    def _convert_all(self, files: list[str]):
        quality = self.quality_var.get()
        delete_orig = self.delete_var.get()
        done = errors = 0

        for i, src in enumerate(files, 1):
            base, _ = os.path.splitext(src)
            out = unique_webp_path(base)
            out_name = os.path.basename(out)
            try:
                img = Image.open(src)
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGBA")
                else:
                    img = img.convert("RGB")
                img.save(out, "WEBP", quality=quality)
                if delete_orig:
                    os.remove(src)
                label = "完了" if out_name == os.path.basename(base) + ".webp" \
                    else f"完了 → {out_name}"
                self._update_row(src, label, "done")
                done += 1
            except Exception as e:
                self._update_row(src, "エラー", "error")
                print(f"[ERROR] {src}: {e}")
                errors += 1

            self.after(0, self._set_progress, i)

        msg = f"完了: {done}件  エラー: {errors}件"
        self.after(0, self.status_var.set, msg)
        self.after(0, self._on_convert_done)
        if errors:
            self.after(0, messagebox.showwarning, "変換完了",
                       f"{msg}\n\nエラーが発生したファイルがあります。")
        else:
            self.after(0, messagebox.showinfo, "変換完了", msg)

    def _on_convert_done(self):
        """変換完了後: 変換開始を再有効化、フォルダを開くボタンを表示"""
        self.convert_btn.config(state="normal")

        folder = self.dir_var.get() or ""
        self.folder_btn.config(command=lambda: self._open_folder(folder))
        # 閉じるの前に挿入
        self.close_btn.pack_forget()
        self.folder_btn.pack(side="left", padx=(0, 8))
        self.close_btn.pack(side="left")

    def _open_folder(self, folder: str):
        folder = os.path.normpath(folder)
        if folder and os.path.isdir(folder):
            os.startfile(folder)

    def _update_row(self, iid: str, status: str, tag: str):
        self.after(0, self._do_update_row, iid, status, tag)

    def _do_update_row(self, iid: str, status: str, tag: str):
        if self.tree.exists(iid):
            vals = list(self.tree.item(iid, "values"))
            vals[2] = status
            self.tree.item(iid, values=vals, tags=(tag,))

    def _set_progress(self, value: int):
        self.progress["value"] = value
        self.status_var.set(f"変換中… {value} / {int(self.progress['maximum'])}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
