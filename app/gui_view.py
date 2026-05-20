"""GUI view: Tkinter widget構築と描画責務。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class FundamentalView:
    """Widget構築と表示更新を担当するView。"""

    def __init__(
        self,
        master: tk.Tk,
        api_key_var: tk.StringVar,
        path_var: tk.StringVar,
        stock_var: tk.StringVar,
        status_var: tk.StringVar,
        kabutan_dir_var: tk.StringVar,
    ):
        self.master = master
        self.api_key_var = api_key_var
        self.path_var = path_var
        self.stock_var = stock_var
        self.status_var = status_var
        self.kabutan_dir_var = kabutan_dir_var

    def build_ui(self, *, on_open, on_select, on_fetch, on_copy, on_save, on_open_kabutan_dir) -> None:
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
        self.open_button = ttk.Button(top, text="監視銘柄ファイルを開く", command=on_open)
        self.open_button.pack(side="left")
        ttk.Label(top, textvariable=self.path_var).pack(side="left", padx=10, fill="x", expand=True)

        kabutan_top = ttk.Frame(root)
        kabutan_top.pack(fill="x", pady=(0, 8))
        self.open_kabutan_dir_button = ttk.Button(kabutan_top, text="株探HTMLフォルダを選択", command=on_open_kabutan_dir)
        self.open_kabutan_dir_button.pack(side="left")
        ttk.Label(kabutan_top, textvariable=self.kabutan_dir_var).pack(side="left", padx=10, fill="x", expand=True)

        control = ttk.Frame(root)
        control.pack(fill="x", pady=(0, 8))
        ttk.Label(control, text="銘柄選択").pack(side="left")
        self.stock_combo = ttk.Combobox(control, textvariable=self.stock_var, state="readonly", width=42)
        self.stock_combo.pack(side="left", padx=(8, 12))
        self.stock_combo.bind("<<ComboboxSelected>>", on_select)
        ttk.Label(control, text="株価: yFinance固定").pack(side="left", padx=(0, 12))
        self.fetch_button = ttk.Button(control, text="取得", command=on_fetch)
        self.fetch_button.pack(side="left", padx=(0, 6))
        self.copy_button = ttk.Button(control, text="コピー", command=on_copy)
        self.copy_button.pack(side="left", padx=(0, 6))
        self.save_button = ttk.Button(control, text="保存", command=on_save)
        self.save_button.pack(side="left")

        ttk.Label(root, textvariable=self.status_var).pack(fill="x", pady=(0, 6))

        text_frame = ttk.Frame(root)
        text_frame.pack(fill="both", expand=True)
        self.text = tk.Text(text_frame, wrap="word", font=("Yu Gothic UI", 11))
        self.text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scroll.set)

    def set_stock_choices(self, values: list[str]) -> None:
        self.stock_combo["values"] = values

    def set_busy(self, busy: bool, status: str | None = None) -> None:
        state = "disabled" if busy else "normal"
        readonly_state = "disabled" if busy else "readonly"
        self.open_button.configure(state=state)
        self.open_kabutan_dir_button.configure(state=state)
        self.fetch_button.configure(state=state)
        self.copy_button.configure(state=state)
        self.save_button.configure(state=state)
        self.api_entry.configure(state=state)
        self.stock_combo.configure(state=readonly_state)
        if status is not None:
            self.status_var.set(status)
        self.master.update_idletasks()

    def clear_text(self) -> None:
        self.text.delete("1.0", tk.END)

    def get_text_content(self) -> str:
        return self.text.get("1.0", tk.END).strip()

    def render_output(self, output: str) -> None:
        self.clear_text()
        self.text.insert("1.0", output)


__all__ = ["FundamentalView"]
