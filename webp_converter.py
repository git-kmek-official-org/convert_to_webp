import os
import glob
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import xml.etree.ElementTree as ET
import base64
import io
import re
import tempfile
from PIL import Image

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIC_AVAILABLE = True
except ImportError:
    _HEIC_AVAILABLE = False

try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    _SVG_AVAILABLE = True
except ImportError:
    _SVG_AVAILABLE = False

SVG_DPI = 96  # SVG レンダリング解像度 (Web 標準 96dpi)
SVG_CURRENT_COLOR = "#000000"  # currentColor のフォールバック値

SUPPORTED_EXTS = (
    "*.jpg", "*.jpeg", "*.gif", "*.png",
    "*.bmp", "*.tif", "*.tiff",
    "*.svg",
    "*.heic", "*.heif",
    "*.JPG", "*.JPEG", "*.GIF", "*.PNG",
    "*.BMP", "*.TIF", "*.TIFF",
    "*.SVG",
    "*.HEIC", "*.HEIF",
)
IMAGE_FILTER = [
    ("画像ファイル",
     "*.jpg *.jpeg *.gif *.png *.bmp *.tif *.tiff *.svg *.heic *.heif "
     "*.JPG *.JPEG *.GIF *.PNG *.BMP *.TIF *.TIFF *.SVG *.HEIC *.HEIF"),
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


def _try_extract_svg_images(svg_text: str) -> "Image.Image | None":
    """SVG内の埋め込みラスター画像を抽出してPIL Imageに合成する。

    Figmaなどが出力する fill="url(#patternN)" 形式のSVGに対応。
    パターン塗りが見つからない場合や解析失敗時はNoneを返す。
    """
    SVG_NS   = "http://www.w3.org/2000/svg"
    XLINK_NS = "http://www.w3.org/1999/xlink"

    def qtag(local: str) -> str:
        return f"{{{SVG_NS}}}{local}"

    def get_href(elem) -> str:
        return (elem.get(f"{{{XLINK_NS}}}href")
                or elem.get("href") or "")

    def decode_data_uri(href: str) -> "Image.Image | None":
        if not href.startswith("data:"):
            return None
        try:
            _, b64 = href.split(",", 1)
            return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
        except Exception:
            return None

    def get_float(elem, attr: str, default: float = 0.0) -> float:
        val = elem.get(attr)
        if val is None:
            return default
        val = re.sub(r"[a-zA-Z%\s]+$", "", val.strip())
        try:
            return float(val)
        except ValueError:
            return default

    try:
        root = ET.fromstring(svg_text.encode("utf-8"))
    except ET.ParseError:
        return None

    # キャンバスサイズ
    vb = root.get("viewBox", "")
    cw = get_float(root, "width", 0)
    ch = get_float(root, "height", 0)
    if vb:
        parts = re.split(r"[\s,]+", vb.strip())
        if len(parts) == 4:
            if cw == 0:
                cw = float(parts[2])
            if ch == 0:
                ch = float(parts[3])
    if cw <= 0 or ch <= 0:
        return None

    # <image id="..."> を収集（defs 内の参照用）
    images_by_id: dict[str, Image.Image] = {}
    for img_elem in root.iter(qtag("image")):
        img_id = img_elem.get("id")
        if img_id:
            pil = decode_data_uri(get_href(img_elem))
            if pil:
                images_by_id[img_id] = pil

    # <pattern> → PIL Image のマップを構築
    pattern_img: dict[str, Image.Image] = {}
    for pat in root.iter(qtag("pattern")):
        pat_id = pat.get("id")
        if not pat_id:
            continue
        for child in pat:
            local = child.tag.split("}")[-1]
            if local == "image":
                pil = decode_data_uri(get_href(child))
                if pil:
                    pattern_img[pat_id] = pil
                    break
            elif local == "use":
                ref = get_href(child)
                if ref.startswith("#") and ref[1:] in images_by_id:
                    pattern_img[pat_id] = images_by_id[ref[1:]]
                    break

    if not pattern_img:
        return None  # パターン塗りなし → svglib に任せる

    canvas = Image.new("RGBA", (int(cw), int(ch)), (255, 255, 255, 255))
    found_any = False

    def fill_pattern_id(elem) -> "str | None":
        for src in (elem.get("fill", ""),
                    re.search(r"fill\s*:\s*([^;]+)", elem.get("style", "") or "")):
            val = src if isinstance(src, str) else (src.group(1) if src else "")
            m = re.match(r"url\(#([^)]+)\)", val.strip())
            if m:
                return m.group(1)
        return None

    def shape_bbox(elem) -> tuple[float, float, float, float]:
        local = elem.tag.split("}")[-1]
        if local == "rect":
            return (get_float(elem, "x", 0), get_float(elem, "y", 0),
                    get_float(elem, "width", cw), get_float(elem, "height", ch))
        if local in ("circle", "ellipse"):
            cx = get_float(elem, "cx", cw / 2)
            cy = get_float(elem, "cy", ch / 2)
            rx = get_float(elem, "rx", 0) or get_float(elem, "r", 0)
            ry = get_float(elem, "ry", 0) or get_float(elem, "r", 0)
            return (cx - rx, cy - ry, rx * 2, ry * 2)
        return (0, 0, cw, ch)  # path など → キャンバス全体で近似

    for elem in root.iter():
        pid = fill_pattern_id(elem)
        if pid not in pattern_img:
            continue
        x, y, rw, rh = shape_bbox(elem)
        if rw <= 0 or rh <= 0:
            continue
        scaled = pattern_img[pid].resize(
            (max(1, int(rw)), max(1, int(rh))), Image.LANCZOS)
        canvas.paste(scaled, (int(x), int(y)), scaled)
        found_any = True

    # defs 外の直接 <image> 要素も処理
    defs_img_ids: set[str] = set()
    defs_elem = root.find(qtag("defs"))
    if defs_elem is not None:
        for e in defs_elem.iter(qtag("image")):
            if e.get("id"):
                defs_img_ids.add(e.get("id"))
    for img_elem in root.iter(qtag("image")):
        if img_elem.get("id") in defs_img_ids:
            continue
        pil = decode_data_uri(get_href(img_elem))
        if not pil:
            continue
        x   = get_float(img_elem, "x", 0)
        y   = get_float(img_elem, "y", 0)
        iw  = get_float(img_elem, "width",  pil.width)
        ih  = get_float(img_elem, "height", pil.height)
        scaled = pil.resize((max(1, int(iw)), max(1, int(ih))), Image.LANCZOS)
        canvas.paste(scaled, (int(x), int(y)), scaled)
        found_any = True

    return canvas if found_any else None


def _svg_to_pil(src: str) -> Image.Image:
    """SVGファイルをPIL Imageに変換する。

    優先順位:
    1. 埋め込みラスター画像の抽出（pattern塗り対応）
    2. svglib によるベクター描画
    """
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        svg_text = f.read()
    svg_text = svg_text.replace("currentColor", SVG_CURRENT_COLOR)

    img = _try_extract_svg_images(svg_text)
    if img is not None:
        return img

    if not _SVG_AVAILABLE:
        raise ImportError("svglib がインストールされていません")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".svg", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(svg_text)
        tmp_path = tf.name
    try:
        drawing = svg2rlg(tmp_path)
    finally:
        os.remove(tmp_path)
    if drawing is None:
        raise ValueError("SVG の読み込みに失敗しました")
    if drawing.width == 0 or drawing.height == 0:
        raise ValueError("SVG のサイズが 0 です (width/height または viewBox を確認してください)")
    return renderPM.drawToPIL(drawing, dpi=SVG_DPI)


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
        tk.Label(hdr, text="JPG / PNG / GIF / BMP / TIFF / HEIC → WebP", bg=SURFACE, fg=FG_DIM,
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
            self.status_var.set("対象ファイルなし (jpg/png/gif/bmp/tiff/heic)")

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
                ext = os.path.splitext(src)[1].lower()
                if ext == ".svg":
                    img = _svg_to_pil(src)
                else:
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
