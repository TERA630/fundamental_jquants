"""GUI layer: Tkinter application wiring and event handling."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from app.data.api_key_provider import fetch_api_key_fallback
from app.gui_controller import FundamentalGuiController
from app.gui_state import GuiState, build_default_output_filename, build_output_cache_key, build_stock_choices, get_selected_stock
from app.gui_view import FundamentalView
from app.gui_view_model import GuiViewModel


class FundamentalApp:
    """GUI層: 画面イベント連携と状態遷移を担当。"""

    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title("J-Quants ファンダメンタル評価 v7（プレーンテキスト / 株価yFinance固定）")
        self.master.geometry("1040x820")

        self.state = GuiState()
        self.controller = FundamentalGuiController()

        self.api_key_var = tk.StringVar(value=os.environ.get("JQUANTS_API_KEY", ""))
        self.path_var = tk.StringVar(value="監視銘柄ファイル未選択")
        self.kabutan_dir_var = tk.StringVar(value="株探HTMLフォルダ未選択")
        self.stock_var = tk.StringVar()
        self.status_var = tk.StringVar(value="監視銘柄ファイルを読み込んでください。")

        self.view_model = GuiViewModel()
        self.view = FundamentalView(
            self.master,
            self.api_key_var,
            self.path_var,
            self.stock_var,
            self.status_var,
            self.kabutan_dir_var,
        )
        self.view.build_ui(
            on_open=self.open_watchlist,
            on_select=self.on_stock_selected,
            on_fetch=self.generate_text,
            on_copy=self.copy_text,
            on_save=self.save_text,
            on_open_kabutan_dir=self.open_kabutan_html_dir,
        )

    def set_busy(self, busy: bool, status: str | None = None):
        self.state.is_fetching = busy
        self.view.set_busy(busy, status)

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

    def open_kabutan_html_dir(self):
        path = filedialog.askdirectory(title="株探HTML保存フォルダを選択")
        if not path:
            return
        self.state.kabutan_html_dir = Path(path)
        self.state.output_cache.clear()
        self.kabutan_dir_var.set(str(self.state.kabutan_html_dir))
        self.status_var.set("株探HTMLフォルダを設定しました（出力キャッシュをクリア）。")

    def _populate_stock_choices(self) -> None:
        values, mapping = build_stock_choices(self.state.watchlist)
        self.state.display_to_code = mapping
        self.view.set_stock_choices(values)

        if values:
            self.stock_var.set(values[0])
            self.status_var.set(self.view_model.build_loaded_status(len(values)))
        else:
            self.stock_var.set("")
            self.view.clear_text()
            self.status_var.set("銘柄が見つかりませんでした。")

    def on_stock_selected(self, _event=None):
        self.status_var.set(self.view_model.build_selected_status())

    def selected_stock(self) -> tuple[str, str] | None:
        return get_selected_stock(self.state.display_to_code, self.stock_var.get())

    def _require_selected_stock(self) -> tuple[str, str] | None:
        selected = self.selected_stock()
        if selected is None:
            self.status_var.set(self.view_model.build_missing_stock_status())
            return None
        return selected

    def _require_api_key(self) -> str | None:
        api_key = self.controller.fetch_api_key(self.api_key_var.get())
        if api_key:
            return api_key
        fallback_api_key = self._fetch_api_key_fallback()
        if fallback_api_key:
            self.api_key_var.set(fallback_api_key)
            return fallback_api_key
        messagebox.showerror("APIキー未入力", "J-Quants APIキーを入力してください。")
        return None

    @staticmethod
    def _fetch_api_key_fallback() -> str:
        return fetch_api_key_fallback()

    def _render_output(self, output: str, status: str):
        self.view.render_output(output)
        self.set_busy(False, status)

    def _handle_fetch_error(self, message: str):
        self.set_busy(False, "取得に失敗しました。")
        messagebox.showerror("取得失敗", message)

    def _fetch_worker(self, name: str, code4: str, api_key: str, cache_key: str):
        try:
            output = self.controller.fetch_analysis_output(
                api_key=api_key,
                name=name,
                code4=code4,
                output_cache=self.state.output_cache,
                output_cache_key=cache_key,
                kabutan_html_dir=self.state.kabutan_html_dir,
            )
            self.master.after(0, lambda: self._render_output(output, self.view_model.build_generated_status(name, code4)))
        except Exception as exc:
            self.master.after(0, lambda msg=str(exc): self._handle_fetch_error(msg))

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
        cache_key = build_output_cache_key(code4, self.state.kabutan_html_dir)
        cached_output = self.state.output_cache.get(cache_key)
        if cached_output is not None:
            self._render_output(cached_output, self.view_model.build_cached_status(name, code4))
            return

        self.set_busy(True, self.view_model.build_fetching_status(name, code4))
        thread = threading.Thread(target=self._fetch_worker, args=(name, code4, api_key, cache_key), daemon=True)
        thread.start()

    def copy_text(self):
        content = self.view.get_text_content()
        if not content:
            self.status_var.set(self.view_model.build_missing_copy_content_status())
            return
        self.master.clipboard_clear()
        self.master.clipboard_append(content)
        self.status_var.set(self.view_model.build_copied_status())

    def save_text(self):
        content = self.view.get_text_content()
        if not content:
            self.status_var.set(self.view_model.build_missing_save_content_status())
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
        self.status_var.set(self.view_model.build_saved_status(path))


__all__ = ["FundamentalApp"]
