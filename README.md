# WebP Converter

JPG / PNG / GIF 画像を WebP 形式に一括変換する Windows 用デスクトップアプリです。

---

## ファイル構成

```
convert_to_webp/
├── webp_converter.py          # アプリ本体のソースコード
├── install.py                 # インストーラーのソースコード
├── README.md                  # このファイル
└── dist/
    └── WebP_Converter_Setup.exe   # 配布用インストーラー（exe）
```

---

## アプリの概要

| 項目 | 内容 |
|---|---|
| 対応形式 | JPG / JPEG / PNG / GIF（大文字・小文字両対応） |
| 出力形式 | WebP |
| デフォルト品質 | 90（1〜100 で調整可能） |
| 動作環境 | Windows 10 / 11（管理者権限不要） |
| インストール先 | `%LOCALAPPDATA%\WebP_Converter\` |

---

## 使い方（エンドユーザー向け）

### インストール

`WebP_Converter_Setup.exe` は GitHub Releases からダウンロードできます。
https://github.com/git-kmek-official-org/convert_to_webp/releases/latest

1. `WebP_Converter_Setup.exe` をダブルクリック
2. インストール先が表示される（変更不可・固定）
3. ショートカットのオプションを選んで「インストール」をクリック
4. 完了後「今すぐ起動しますか？」→ はい

### アプリの操作

1. **「ファイルを選択」** をクリック
   - ファイルダイアログが開く（画像ファイルが確認できる）
   - 変換したいファイルを複数選択して「開く」
2. ファイル一覧に選択したファイルが表示される
3. **WebP 品質** スライダーで品質を調整（低品質 ←→ 高品質）
   - 右側の数値欄に直接キーボード入力も可能
   - 数値欄にフォーカスした状態で ↑ / ↓ キーで ±1、Shift+↑ / ↓ で ±10
4. 「変換後に元ファイルを削除」チェックボックスで削除可否を選択
5. **「変換開始」** をクリック
6. 変換完了後、**「フォルダを開く」** ボタンが追加表示され、変換先フォルダを開ける
   - 「変換開始」ボタンはそのまま押せる状態を維持（連続変換が可能）

### アンインストール

Windows の「設定 → アプリ → WebP Converter → アンインストール」から実行

---

## ビルド手順（開発者向け）

### 必要な環境

- Python 3.10 以上
- 以下のパッケージ

```bash
pip install pillow pyinstaller
```

### ① アプリ本体をビルド

```bash
python -m PyInstaller --onedir --noconsole -y --name "WebP_Converter" webp_converter.py
```

出力先: `dist/WebP_Converter/`

### ② インストーラー exe をビルド（アプリ一式を内包）

```bash
python -m PyInstaller --onefile --noconsole -y --name "WebP_Converter_Setup" --add-data "dist/WebP_Converter;app_files" install.py
```

出力先: `dist/WebP_Converter_Setup.exe` ← これを配布する

> **注意:** ① を完了してから ② を実行すること。順番を逆にすると最新のアプリが内包されない。

---

## ソースコードの説明

### webp_converter.py

| 関数 / クラス | 役割 |
|---|---|
| `unique_webp_path()` | 同名 .webp が存在する場合に `file(1).webp` のように連番を付ける |
| `find_images()` | 指定ディレクトリから対応画像を一覧取得（大文字小文字重複排除） |
| `App` クラス | tkinter GUI アプリ本体 |
| `_apply_style()` | ttk テーマ（macOS ライト風カラー）の適用 |
| `_build_ui()` | UI の構築（ヘッダー・ファイル選択・一覧・オプション・ボタン） |
| `_browse()` | ファイル選択ダイアログを開く（`askopenfilenames`） |
| `_set_files()` | 選択されたファイルを一覧に表示し `dir_var` にフォルダパスを保存 |
| `_start_convert()` | 変換をバックグラウンドスレッドで開始 |
| `_convert_all()` | 実際の変換処理（Pillow 使用）。RGBA/LA/P モードは RGBA に変換 |
| `_on_convert_done()` | 変換完了後のボタン状態変更（「変換開始」再有効化・「フォルダを開く」ボタン追加表示） |
| `_open_folder()` | `os.startfile()` でエクスプローラーを開く（`os.path.normpath` でパス正規化） |

### install.py

| 関数 / クラス | 役割 |
|---|---|
| `create_shortcut()` | PowerShell 経由で `.lnk` ショートカットを作成 |
| `register_uninstaller()` | `HKCU\SOFTWARE\...\Uninstall` にアンインストール情報を登録 |
| `unregister_uninstaller()` | レジストリからアンインストール情報を削除 |
| `InstallerApp` クラス | インストーラー GUI 本体 |
| `_start_install()` | ファイルコピー・ショートカット作成・レジストリ登録を実行 |
| `_start_uninstall()` | ショートカット削除・レジストリ削除・遅延バッチでフォルダ削除 |

---

## カラーパレット（UI テーマ）

macOS ライトテーマをベースにしています。変更する場合は `webp_converter.py` の上部定数を編集します。

| 定数 | 値 | 用途 |
|---|---|---|
| `BG` | `#ececec` | ウィンドウ背景 |
| `SURFACE` | `#f5f5f5` | カード背景 |
| `SURFACE2` | `#ffffff` | 入力欄・テーブル |
| `BORDER` | `#d1d1d6` | 区切り線 |
| `ACCENT` | `#007aff` | プライマリボタン・アクセント色 |
| `ACCENT_H` | `#0051d5` | ホバー時のアクセント色 |
| `FG` | `#1c1c1e` | メインテキスト |
| `FG_DIM` | `#8e8e93` | サブテキスト |
| `SUCCESS` | `#34c759` | 変換完了の緑色 |
| `ERROR` | `#ff3b30` | エラーの赤色 |

---

## よくある修正箇所

### デフォルト品質を変更したい
`webp_converter.py` の 14 行目
```python
WEBP_QUALITY = 90  # ← ここを変更
```

### バージョン番号を上げたい
`install.py` の 16 行目
```python
APP_VERSION = "1.0"  # ← ここを変更
```
変更後は必ずリビルドすること。

### 対応フォーマットを追加したい
`webp_converter.py` の `SUPPORTED_EXTS` と `IMAGE_FILTER` を両方編集する。
```python
SUPPORTED_EXTS = ("*.jpg", ..., "*.bmp", "*.BMP")  # 追加
IMAGE_FILTER = [
    ("画像ファイル", "*.jpg ... *.bmp *.BMP"),       # 追加
    ...
]
```

---

## バージョン履歴

### v1.1
- 変換完了後も「変換開始」ボタンが押せる状態を維持（連続変換に対応）
- 変換完了後に「フォルダを開く」ボタンが追加表示される
- WebP 品質の数値欄をキーボード入力対応に変更
  - 直接入力・↑↓ キーで ±1・Shift+↑↓ で ±10
- スライダーのつまみを大型化（18px → 28px）してつかみやすく改善
- ボタン・プログレスバーをフッターに固定し、ウィンドウを縮めても常に表示
- 最小ウィンドウサイズを緩和（680×540 → 500×230）

### v1.0
- 初回リリース

---

## 注意事項

- **元ファイル削除オプション**はデフォルトでオンになっている。誤って削除した場合は OS のゴミ箱に入らないため復元できない（Pillow の `os.remove()` を直接呼ぶため）。
- 同名の `.webp` ファイルが既に存在する場合、`file(1).webp` のように自動で連番が付く（上書きしない）。
- アンインストール時はインストールフォルダ全体が削除される。アプリ内で保存したデータがある場合は事前にバックアップすること（現バージョンではユーザーデータの保存はない）。
- インストーラーの exe は起動時に一時フォルダへ展開してから実行するため、初回起動は数秒かかる場合がある（インストール後のアプリ本体は速い）。
