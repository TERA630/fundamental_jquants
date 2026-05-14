"""GUI view-model: 画面表示用メッセージ/表示値の生成。"""

from __future__ import annotations


class GuiViewModel:
    """表示用文字列を生成する。"""

    @staticmethod
    def build_loaded_status(count: int) -> str:
        return f"{count}件の監視銘柄を読み込みました。"

    @staticmethod
    def build_selected_status() -> str:
        return "銘柄を選択しました。取得ボタンを押してください。"

    @staticmethod
    def build_missing_stock_status() -> str:
        return "先に監視銘柄ファイルと銘柄を選んでください。"

    @staticmethod
    def build_missing_copy_content_status() -> str:
        return "コピーするテキストがありません。"

    @staticmethod
    def build_copied_status() -> str:
        return "クリップボードにコピーしました。"

    @staticmethod
    def build_missing_save_content_status() -> str:
        return "保存するテキストがありません。"

    @staticmethod
    def build_saved_status(path: str) -> str:
        return f"保存完了: {path}"

    @staticmethod
    def build_fetching_status(name: str, code4: str) -> str:
        return f"取得中: {name} ({code4}) / 財務=J-Quants / 株価=yFinance"

    @staticmethod
    def build_generated_status(name: str, code4: str) -> str:
        return f"生成完了: {name} ({code4}) / 財務=J-Quants / 株価=yFinance"

    @staticmethod
    def build_cached_status(name: str, code4: str) -> str:
        return f"キャッシュ表示: {name} ({code4})"


__all__ = ["GuiViewModel"]
