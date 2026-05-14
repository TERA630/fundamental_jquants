"""GUI layer: Tkinter application wiring and presentation logic."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app.gui_controller import FundamentalGuiController
from app.gui_state import GuiState, build_default_output_filename, build_stock_choices, get_selected_stock


class FundamentalApp:
    """GUI層: 画面表示・UI状態管理・ユースケース呼び出しを担当。"""

    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title("J-Quants ファンダメンタル評価 v7（プレーンテキスト / 株価yFinance固定）")
        self.master.geometry("1040x820")

        self.state = GuiState()
        self.controller = FundamentalGuiController()

        self.api_key_var = tk.StringVar(value=os.environ.get("JQUANTS_API_KEY", ""))
        self.path_var = tk.StringVar(value="監視銘柄ファイル未選択")
        self.stock_var = tk.StringVar()
        self.status_var = tk.StringVar(value="監視銘柄ファイルを読み込んでください。")

        self._build_ui()

    def _build_ui(self):
        root = ttk.Frame(self.master, padding=10)
        root.pack(fill="both", expand=True)

        api_frame = ttk.Frame(root)
        api_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(api_frame, text="J-Quants APIキー").pack(side="left")
        self.api_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, show="*", width=56)
        self.api_entry.pack(side="left", padx=(8, 8))
        ttk.Label(api_frame, text="環境変数 JQUANTS_API_KEY も可").pack(side="left")

        top = ttk.Frame(root)
        top.pack(fill="x", pady=(0, 8))
        self.open_button = ttk.Button(top, text="監視銘柄ファイルを開く", command=self.open_watchlist)
        self.open_button.pack(side="left")
        ttk.Label(top, textvariable=self.path_var).pack(side="left", padx=10, fill="x", expand=True)

        control = ttk.Frame(root)
        control.pack(fill="x", pady=(0, 8))
        ttk.Label(control, text="銘柄選択").pack(side="left")
        self.stock_combo = ttk.Combobox(control, textvariable=self.stock_var, state="readonly", width=42)
        self.stock_combo.pack(side="left", padx=(8, 12))
        self.stock_combo.bind("<<ComboboxSelected>>", self.on_stock_selected)
        ttk.Label(control, text="株価: yFinance固定").pack(side="left", padx=(0, 12))
        self.fetch_button = ttk.Button(control, text="取得", command=self.generate_text)
        self.fetch_button.pack(side="left", padx=(0, 6))
        self.copy_button = ttk.Button(control, text="コピー", command=self.copy_text)
        self.copy_button.pack(side="left", padx=(0, 6))
        self.save_button = ttk.Button(control, text="保存", command=self.save_text)
        self.save_button.pack(side="left")

        ttk.Label(root, textvariable=self.status_var).pack(fill="x", pady=(0, 6))

        text_frame = ttk.Frame(root)
        text_frame.pack(fill="both", expand=True)
        self.text = tk.Text(text_frame, wrap="word", font=("Yu Gothic UI", 11))
        self.text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scroll.set)

    def set_busy(self, busy: bool, status: str | None = None):
        self.state.is_fetching = busy
        state = "disabled" if busy else "normal"
        readonly_state = "disabled" if busy else "readonly"
        self.open_button.configure(state=state)
        self.fetch_button.configure(state=state)
        self.copy_button.configure(state=state)
        self.save_button.configure(state=state)
        self.api_entry.configure(state=state)
        self.stock_combo.configure(state=readonly_state)
        if status is not None:
            self.status_var.set(status)
        self.master.update_idletasks()

    def open_watchlist(self):
        path = filedialog.askopenfilename(
            title="監視銘柄ファイルを選択",
            filetypes=[("Markdown/Text", "*.md *.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            watchlist = self.controller.fetch_watchlist_entries(Path(path))
        except Exception as exc:
            messagebox.showerror("読込失敗", str(exc))
            return

        self.state.watchlist_path = Path(path)
        self.state.watchlist = watchlist
        self.state.output_cache.clear()
        self.path_var.set(str(self.state.watchlist_path))
        self._populate_stock_choices()

    def _populate_stock_choices(self) -> None:
        values, mapping = build_stock_choices(self.state.watchlist)
        self.state.display_to_code = mapping
        self.stock_combo["values"] = values

        if values:
            self.stock_var.set(values[0])
            self.status_var.set(f"{len(values)}件の監視銘柄を読み込みました。")
        else:
            self.stock_var.set("")
            self.text.delete("1.0", tk.END)
            self.status_var.set("銘柄が見つかりませんでした。")

    def on_stock_selected(self, _event=None):
        self.status_var.set("銘柄を選択しました。取得ボタンを押してください。")

    def selected_stock(self) -> tuple[str, str] | None:
        label = self.stock_var.get().strip()
        if not label:
            return None
        return get_selected_stock(self.state.display_to_code, label)

    def _require_selected_stock(self) -> tuple[str, str] | None:
        selected = self.selected_stock()
        if selected is None:
            self.status_var.set("先に監視銘柄ファイルと銘柄を選んでください。")
            return None
        return selected

    def _require_api_key(self) -> str | None:
        api_key = self.api_key_var.get().strip()
        if api_key:
            return api_key
        messagebox.showerror("APIキー未入力", "J-Quants APIキーを入力してください。")
        return None

    def _render_output(self, output: str, status: str):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", output)
        self.set_busy(False, status)

    def _handle_fetch_error(self, message: str):
        self.set_busy(False, "取得に失敗しました。")
        messagebox.showerror("取得失敗", message)

    def _fetch_worker(self, name: str, code4: str, api_key: str):
        try:
            output = self.controller.fetch_analysis_output(
                api_key=api_key,
                name=name,
                code4=code4,
                output_cache=self.state.output_cache,
            )
            self.master.after(0, lambda: self._render_output(output, f"生成完了: {name} ({code4}) / 財務=J-Quants / 株価=yFinance"))
        except Exception as exc:
            error_message = str(exc)
            self.master.after(0, lambda msg=error_message: self._handle_fetch_error(msg))

    def generate_text(self):
        if self.state.is_fetching:
            return

        selected = self._require_selected_stock()
        if selected is None:
            return

        api_key = self._require_api_key()
        if api_key is None:
            return

        name, code4 = selected
        cached_output = self.state.output_cache.get(code4)
        if cached_output is not None:
            self._render_output(cached_output, f"キャッシュ表示: {name} ({code4})")
            return

        self.set_busy(True, f"取得中: {name} ({code4}) / 財務=J-Quants / 株価=yFinance")
        thread = threading.Thread(target=self._fetch_worker, args=(name, code4, api_key), daemon=True)
        thread.start()

    def copy_text(self):
        content = self.text.get("1.0", tk.END).strip()
        if not content:
            self.status_var.set("コピーするテキストがありません。")
            return
        self.master.clipboard_clear()
        self.master.clipboard_append(content)
        self.status_var.set("クリップボードにコピーしました。")

    def save_text(self):
        content = self.text.get("1.0", tk.END).strip()
        if not content:
            self.status_var.set("保存するテキストがありません。")
            return
        selected = self.selected_stock()
        default_name = build_default_output_filename(selected)
        initial_dir = str(self.state.watchlist_path.parent) if self.state.watchlist_path else str(Path.cwd())
        path = filedialog.asksaveasfilename(
            title="保存先を選択",
            defaultextension=".txt",
            initialdir=initial_dir,
            initialfile=default_name,
            filetypes=[("Text files", "*.txt"), ("Markdown files", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(content + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("保存失敗", f"ファイルを書き込めませんでした: {exc}")
            self.status_var.set("保存に失敗しました。")
            return
        self.status_var.set(f"保存完了: {path}")


__all__ = ["FundamentalApp"]
