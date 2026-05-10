Analyze the code
fundamental_jquants



会話
差分
ログ

fundamental_jquants_v7.py
fundamental_jquants_v7.py
+17
-51

@@ -1187,100 +1187,55 @@ def build_output(name: str, code4: str, master: dict[str, Any] | None, summary_r
        f"配当利回り：{fmt_plain_pct(metrics.get('div_yield'))}",
        f"配当性向：{fmt_plain_pct(metrics.get('payout'))}",
        "",
        "■評価コメント",
    ])

    if metrics.get("yoy_sales") is not None and metrics["yoy_sales"] >= 10:
        lines.append("売上は高成長。")
    if metrics.get("op_yoy") is not None and metrics["op_yoy"] >= 10:
        lines.append("営業利益も増益基調。")
    if metrics.get("forecast_op_yoy") is not None and metrics["forecast_op_yoy"] >= 10:
        lines.append("今期会社予想も増益基調で、ファンダ面では監視優先度は高い。")
    elif metrics.get("forecast_op_yoy") is not None and metrics["forecast_op_yoy"] < 0:
        lines.append("今期会社予想は営業減益であり、実績が良くても今期の減速リスクを重視する。")
    if len(lines) > 0 and lines[-1] == "■評価コメント":
        lines.append("明確な強弱は限定的。テクニカル位置と決算進捗を併せて判断する。")

    lines.extend([
        "",
        "■業種補正コメント",
        sector_comment(f"{sector33} {sector17} {market_segment}"),
    ])
    return "\n".join(lines)


class FundamentalAnalyzer:
    """取得・計算・レンダリングをGUIから分離する薄いアプリケーション層。"""

    def __init__(self, api_key: str, file_cache: FileCache | None = None):
        self.client = JQuantsClient(api_key)
        self.cache = file_cache or FileCache()

    def fetch_master(self, code4: str) -> dict[str, Any] | None:
        code5 = normalize_code(code4)
        return self.cache.get_or_fetch(
            f"master_{code5}",
            CACHE_TTL_MASTER_SEC,
            lambda: self.client.get_master(code4),
        )

    def fetch_summary_rows(self, code4: str) -> list[dict[str, Any]]:
        code5 = normalize_code(code4)
        rows = self.cache.get_or_fetch(
            f"summary_{code5}",
            CACHE_TTL_SUMMARY_SEC,
            lambda: self.client.get_summary(code4),
        )
        return rows if isinstance(rows, list) else []

    def fetch_price_snapshot(self, code4: str) -> dict[str, float | None]:
        """株価・時価総額はyFinance固定。J-Quants daily closeにはフォールバックしない。"""
        snapshot = self.cache.get_or_fetch(
            f"yf_{code4}",
            CACHE_TTL_YF_SEC,
            lambda: fetch_yfinance_snapshot(code4),
        )
        if not isinstance(snapshot, dict):
            return {"price": None, "market_cap": None}
        return {
            "price": safe_float(snapshot.get("price")),
            "market_cap": safe_float(snapshot.get("market_cap")),
        }

    def analyze_one(self, name: str, code4: str) -> str:
        master = self.fetch_master(code4)
        summary_rows = self.fetch_summary_rows(code4)
        price_snapshot = self.fetch_price_snapshot(code4)
        return build_output(
            name=name,
            code4=code4,
            master=master,
            summary_rows=summary_rows,
            price=price_snapshot.get("price"),
            market_cap=price_snapshot.get("market_cap"),
        )



from layers import DataRepository, FundamentalAnalysisService

class FundamentalApp:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title("J-Quants ファンダメンタル評価 v7（プレーンテキスト / 株価yFinance固定）")
        self.master.geometry("1040x820")

        self.watchlist_path: Path | None = None
        self.watchlist: list[tuple[str, str]] = []
        self.display_to_code: dict[str, tuple[str, str]] = {}
        self.output_cache: dict[tuple[str, bool], str] = {}
        self.file_cache = FileCache()
        self.is_fetching = False

        self.api_key_var = tk.StringVar(value=os.environ.get("JQUANTS_API_KEY", ""))
        self.path_var = tk.StringVar(value="監視銘柄ファイル未選択")
        self.stock_var = tk.StringVar()
        self.status_var = tk.StringVar(value="監視銘柄ファイルを読み込んでください。")

        self._build_ui()

    def _build_ui(self):
        root = ttk.Frame(self.master, padding=10)
        root.pack(fill="both", expand=True)

@@ -1365,52 +1320,63 @@ class FundamentalApp:
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
        return self.display_to_code.get(label)

    def _render_output(self, output: str, status: str):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", output)
        self.set_busy(False, status)

    def _handle_fetch_error(self, message: str):
        self.set_busy(False, "取得に失敗しました。")
        messagebox.showerror("取得失敗", message)

    def _fetch_worker(self, name: str, code4: str, api_key: str):
        try:
            analyzer = FundamentalAnalyzer(api_key=api_key, file_cache=self.file_cache)
            output = analyzer.analyze_one(name, code4)
            repository = DataRepository(
                api_key=api_key,
                file_cache=self.file_cache,
                client_factory=JQuantsClient,
                normalize_code=normalize_code,
                safe_float=safe_float,
                fetch_yfinance_snapshot=fetch_yfinance_snapshot,
                cache_ttl_master_sec=CACHE_TTL_MASTER_SEC,
                cache_ttl_summary_sec=CACHE_TTL_SUMMARY_SEC,
                cache_ttl_yf_sec=CACHE_TTL_YF_SEC,
            )
            service = FundamentalAnalysisService(repository=repository, build_output=build_output)
            output = service.analyze_one(name, code4)
            self.output_cache[code4] = output
            self.master.after(0, lambda: self._render_output(output, f"生成完了: {name} ({code4}) / 財務=J-Quants / 株価=yFinance"))
        except Exception as exc:
            self.master.after(0, lambda: self._handle_fetch_error(str(exc)))

    def generate_text(self):
        if self.is_fetching:
            return

        selected = self.selected_stock()
        if selected is None:
            self.status_var.set("先に監視銘柄ファイルと銘柄を選んでください。")
            return
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("APIキー未入力", "J-Quants APIキーを入力してください。")
            return

        name, code4 = selected
        cache_key = code4
        if cache_key in self.output_cache:
            self._render_output(self.output_cache[cache_key], f"キャッシュ表示: {name} ({code4})")
            return

        self.set_busy(True, f"取得中: {name} ({code4}) / 財務=J-Quants / 株価=yFinance")
layers.py
layers.py
新規
+79
-0

from __future__ import annotations

from typing import Any, Callable


class DataRepository:
    """データ層: 外部API・キャッシュアクセスを担当。"""

    def __init__(
        self,
        api_key: str,
        file_cache,
        client_factory: Callable[[str], Any],
        normalize_code: Callable[[str], str],
        safe_float: Callable[[Any], float | None],
        fetch_yfinance_snapshot: Callable[[str], dict[str, float | None]],
        cache_ttl_master_sec: int | float,
        cache_ttl_summary_sec: int | float,
        cache_ttl_yf_sec: int | float,
    ):
        self.client = client_factory(api_key)
        self.cache = file_cache
        self.normalize_code = normalize_code
        self.safe_float = safe_float
        self.fetch_yfinance_snapshot = fetch_yfinance_snapshot
        self.cache_ttl_master_sec = cache_ttl_master_sec
        self.cache_ttl_summary_sec = cache_ttl_summary_sec
        self.cache_ttl_yf_sec = cache_ttl_yf_sec

    def fetch_master(self, code4: str) -> dict[str, Any] | None:
        code5 = self.normalize_code(code4)
        return self.cache.get_or_fetch(
            f"master_{code5}",
            self.cache_ttl_master_sec,
            lambda: self.client.get_master(code4),
        )

    def fetch_summary_rows(self, code4: str) -> list[dict[str, Any]]:
        code5 = self.normalize_code(code4)
        rows = self.cache.get_or_fetch(
            f"summary_{code5}",
            self.cache_ttl_summary_sec,
            lambda: self.client.get_summary(code4),
        )
        return rows if isinstance(rows, list) else []

    def fetch_price_snapshot(self, code4: str) -> dict[str, float | None]:
        snapshot = self.cache.get_or_fetch(
            f"yf_{code4}",
            self.cache_ttl_yf_sec,
            lambda: self.fetch_yfinance_snapshot(code4),
        )
        if not isinstance(snapshot, dict):
            return {"price": None, "market_cap": None}
        return {
            "price": self.safe_float(snapshot.get("price")),
            "market_cap": self.safe_float(snapshot.get("market_cap")),
        }


class FundamentalAnalysisService:
    """ビジネスロジック層: データを組み合わせて評価テキストを生成。"""

    def __init__(self, repository: DataRepository, build_output: Callable[..., str]):
        self.repository = repository
        self.build_output = build_output

    def analyze_one(self, name: str, code4: str) -> str:
        master = self.repository.fetch_master(code4)
        summary_rows = self.repository.fetch_summary_rows(code4)
        price_snapshot = self.repository.fetch_price_snapshot(code4)
        return self.build_output(
            name=name,
            code4=code4,
            master=master,
            summary_rows=summary_rows,
            price=price_snapshot.get("price"),
            market_cap=price_snapshot.get("market_cap"),
        )
