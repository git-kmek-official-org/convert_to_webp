"""
WebP Converter インストーラ
- %LOCALAPPDATA%\WebP_Converter\ にファイルをコピー
- スタートメニューとデスクトップにショートカットを作成
- コントロールパネルのアンインストール一覧に登録
"""
import os
import sys
import shutil
import winreg
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

APP_NAME    = "WebP Converter"
APP_VERSION = "1.0"
EXE_NAME    = "WebP_Converter.exe"
INSTALL_DIR = Path(os.environ["LOCALAPPDATA"]) / "WebP_Converter"
UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\WebPConverter"


def create_shortcut(target: Path, shortcut_path: Path, description: str = ""):
    """PowerShell を使ってショートカットを作成"""
    import subprocess
    ps = (
        f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{shortcut_path}");'
        f'$s.TargetPath="{target}";'
        f'$s.WorkingDirectory="{target.parent}";'
        f'$s.Description="{description}";'
        f'$s.Save()'
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
    )
    return result.returncode == 0


def get_startmenu_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def get_desktop_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", "")) / "Desktop"


def register_uninstaller(install_dir: Path, uninstall_exe: Path):
    """コントロールパネルのアンインストール一覧に登録"""
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        winreg.SetValueEx(key, "DisplayName",        0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion",     0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "InstallLocation",    0, winreg.REG_SZ, str(install_dir))
        winreg.SetValueEx(key, "UninstallString",    0, winreg.REG_SZ, f'"{uninstall_exe}" /uninstall')
        winreg.SetValueEx(key, "NoModify",           0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair",           0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
    except Exception as e:
        print(f"レジストリ登録エラー: {e}")


def unregister_uninstaller():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except Exception:
        pass


# ── GUI ──────────────────────────────────────────────────────────────────────

BG      = "#ececec"
SURFACE = "#f5f5f5"
BORDER  = "#d1d1d6"
ACCENT  = "#007aff"
FG      = "#1c1c1e"
FG_DIM  = "#8e8e93"
FONT    = "Helvetica Neue"


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} セットアップ")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("460x320")
        self._build_ui()
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.focus_force()

        # アンインストールモード
        if len(sys.argv) > 1 and sys.argv[1] == "/uninstall":
            self.after(100, self._start_uninstall)

    def _build_ui(self):
        # ヘッダー
        hdr = tk.Frame(self, bg=SURFACE, pady=14,
                       highlightbackground=BORDER, highlightthickness=1)
        hdr.pack(fill="x")
        tk.Label(hdr, text=APP_NAME, bg=SURFACE, fg=FG,
                 font=(FONT, 14, "bold")).pack(side="left", padx=18)
        tk.Label(hdr, text=f"v{APP_VERSION}", bg=SURFACE, fg=FG_DIM,
                 font=(FONT, 9)).pack(side="left")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # インストール先
        tk.Label(body, text="インストール先", bg=BG, fg=FG_DIM,
                 font=(FONT, 9, "bold")).pack(anchor="w")
        wrap = tk.Frame(body, bg=BORDER, padx=1, pady=1)
        wrap.pack(fill="x", pady=(4, 14))
        tk.Label(wrap, text=str(INSTALL_DIR), bg=SURFACE, fg=FG,
                 font=(FONT, 9), anchor="w", padx=8, pady=6).pack(fill="x")

        # オプション
        self.desktop_var = tk.BooleanVar(value=True)
        tk.Checkbutton(body, text="デスクトップにショートカットを作成",
                       variable=self.desktop_var,
                       bg=BG, fg=FG, selectcolor=SURFACE,
                       activebackground=BG, font=(FONT, 10)).pack(anchor="w")
        self.startmenu_var = tk.BooleanVar(value=True)
        tk.Checkbutton(body, text="スタートメニューに追加",
                       variable=self.startmenu_var,
                       bg=BG, fg=FG, selectcolor=SURFACE,
                       activebackground=BG, font=(FONT, 10)).pack(anchor="w", pady=(4, 0))

        # プログレスバー
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TProgressbar", background=ACCENT, troughcolor=BORDER,
                    borderwidth=0, thickness=4)
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(14, 6))

        self.status_var = tk.StringVar(value="インストールの準備ができました")
        tk.Label(body, textvariable=self.status_var, bg=BG, fg=FG_DIM,
                 font=(FONT, 9)).pack(anchor="w")

        # ボタン
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=(0, 16))
        self.cancel_btn = self._btn(btn_row, "キャンセル", self.destroy, muted=True)
        self.cancel_btn.pack(side="left", padx=(0, 8))
        self.install_btn = self._btn(btn_row, "インストール", self._start_install, primary=True)
        self.install_btn.pack(side="left")

    def _btn(self, parent, text, command, primary=False, muted=False):
        if primary:
            bg, fg, hover = ACCENT, "white", "#0051d5"
        elif muted:
            bg, fg, hover = BORDER, FG_DIM, "#c0c0c8"
        else:
            bg, fg, hover = SURFACE, FG, BORDER
        b = tk.Button(parent, text=text, command=command,
                      bg=bg, fg=fg, relief="flat", bd=0,
                      font=(FONT, 10, "bold" if primary else "normal"),
                      padx=16, pady=6, cursor="hand2",
                      activebackground=hover, activeforeground=fg)
        b.bind("<Enter>", lambda _: b.config(bg=hover))
        b.bind("<Leave>", lambda _: b.config(bg=bg))
        return b

    def _set_status(self, msg: str, pct: int):
        self.status_var.set(msg)
        self.progress["value"] = pct
        self.update_idletasks()

    def _start_install(self):
        self.install_btn.config(state="disabled")
        self.cancel_btn.config(state="disabled")

        try:
            # PyInstaller --onefile の場合は _MEIPASS、通常実行時は相対パス
            if getattr(sys, "frozen", False):
                src = Path(sys._MEIPASS) / "app_files"
            else:
                src = Path(__file__).parent / "dist" / "WebP_Converter"
            if not src.exists():
                messagebox.showerror("エラー",
                    f"配布フォルダが見つかりません:\n{src}")
                self.install_btn.config(state="normal")
                self.cancel_btn.config(state="normal")
                return

            self._set_status("インストール先を準備中…", 10)
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)

            self._set_status("ファイルをコピー中…", 30)
            if (INSTALL_DIR / "_internal").exists():
                shutil.rmtree(INSTALL_DIR / "_internal")
            shutil.copy2(src / EXE_NAME, INSTALL_DIR / EXE_NAME)
            shutil.copytree(src / "_internal", INSTALL_DIR / "_internal")

            exe_path = INSTALL_DIR / EXE_NAME
            self._set_status("ショートカットを作成中…", 70)

            if self.startmenu_var.get():
                sm = get_startmenu_dir() / f"{APP_NAME}.lnk"
                create_shortcut(exe_path, sm, APP_NAME)

            if self.desktop_var.get():
                dt = get_desktop_dir() / f"{APP_NAME}.lnk"
                create_shortcut(exe_path, dt, APP_NAME)

            self._set_status("アンインストーラーを登録中…", 90)
            register_uninstaller(INSTALL_DIR, exe_path)

            self._set_status("完了！", 100)
            if messagebox.askyesno("インストール完了",
                                   f"{APP_NAME} をインストールしました。\n今すぐ起動しますか？"):
                import subprocess
                subprocess.Popen([str(exe_path)], close_fds=True)
            self.destroy()

        except Exception as e:
            messagebox.showerror("インストールエラー", str(e))
            self.install_btn.config(state="normal")
            self.cancel_btn.config(state="normal")

    def _start_uninstall(self):
        if not messagebox.askyesno("アンインストール",
                                   f"{APP_NAME} をアンインストールしますか？"):
            self.destroy()
            return
        try:
            # ショートカット削除
            for path in [
                get_startmenu_dir() / f"{APP_NAME}.lnk",
                get_desktop_dir()   / f"{APP_NAME}.lnk",
            ]:
                path.unlink(missing_ok=True)
            unregister_uninstaller()
            # ファイル削除（自身は実行中なので遅延削除バッチを使う）
            bat = Path(os.environ["TEMP"]) / "uninstall_webp.bat"
            bat.write_text(
                f'@echo off\ntimeout /t 2 /nobreak >nul\n'
                f'rd /s /q "{INSTALL_DIR}"\ndel "%~f0"',
                encoding="utf-8"
            )
            import subprocess
            subprocess.Popen(["cmd", "/c", str(bat)], close_fds=True,
                             creationflags=subprocess.CREATE_NO_WINDOW)
            messagebox.showinfo("完了", f"{APP_NAME} をアンインストールしました。")
        except Exception as e:
            messagebox.showerror("エラー", str(e))
        self.destroy()


if __name__ == "__main__":
    app = InstallerApp()
    app.mainloop()
