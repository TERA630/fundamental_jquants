# レイヤード責務分離ガイド

このプロジェクトは、以下 3 層を明確に分離して開発する。

## 1. データ層（Repository）
- 対象: `app/repositories.py`
- 役割:
  - 外部APIとの通信（J-Quants, yfinance）
  - キャッシュ管理（`FileCache`）
  - 取得値の最低限の整形（`normalize_code`, safe float 変換など）
- やってはいけないこと:
  - 銘柄評価ロジック（スコア判定・ランク判定）
  - 画面表示ロジック（Tkinter widget 操作）

## 2. ドメイン層（Model / UseCase / 判定ロジック）
- 対象: `app/services.py`
- 役割:
  - ユースケース実行（`FundamentalAnalysisService`）
  - 計算ロジック（`calc_*`）
  - 判定ロジック（`grade_*`, `rank_*`）
  - 出力生成呼び出し（`build_*` の組み立て）
- やってはいけないこと:
  - HTTP通信・ファイルI/Oの直接実装
  - Tkinterの操作

## 3. GUI層（表示・表示状態）
- 対象: `fundamental_jquants_v7.py` の `FundamentalApp`（将来的に `app/gui.py` へ段階移管）
- 役割:
  - 画面描画
  - ユーザー入力受付
  - 表示状態管理（選択銘柄・表示テキスト・ボタン有効/無効）
  - ドメイン層ユースケース呼び出し
- やってはいけないこと:
  - 直接APIアクセス
  - 評価計算・ランク判定の本体実装

## 命名ポリシー
- 取得: `fetch_*`, `get_*`
- 計算: `calc_*`
- 判定: `grade_*`, `rank_*`
- 出力生成: `build_*`, `render_*`

## 直近の移行方針
1. GUI実体を `fundamental_jquants_v7.py` から `app/gui.py` へ段階移管する。
2. 出力生成ロジック（`build_output`）をドメイン層の `build_*` 関数へ移し、GUI からはユースケース経由でのみ利用する。
3. 新規機能追加時は、まず層の所属を決めてから実装する。
