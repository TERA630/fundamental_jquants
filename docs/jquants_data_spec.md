# J-Quants JSON取得と財務データ抽出仕様書

## 1. 目的
本仕様書は、J-Quants の `/fins/summary` JSON から以下をどのように抽出しているかを定義する。

- 通期実績データ（最新FY、前期FY）
- 四半期データ（最新 1Q/2Q/3Q）
- 今期末予想データ（Forecast）
- 来季予想データ（Next Forecast）

あわせて、データ層 / ドメイン層 / GUI層の責務分離を明確化する。

---

## 2. レイヤー責務（責務分離）

### 2.1 データ層
対象:
- `app/data/jquants_client.py`
- `app/domain/usecases/fundamental_analysis.py` のデータ取得メソッド（`fetch_*`）

責務:
- J-Quants API 呼び出し（`get`, `get_all`, `get_summary`, `get_master`）
- pagination_key を使った全件取得
- API呼び出し間隔制御（スロットリング）
- キャッシュ（master, summary, yfinance snapshot）

非責務:
- FY/Q判定ロジック
- 指標計算（YoY, PER など）
- 画面表示文言の組み立て

### 2.2 ドメイン層（モデル / ユースケース / リポジトリ相当）
対象:
- モデル: `app/domain/models/metrics.py`
- ユースケース: `app/domain/usecases/fundamental_analysis.py`
- 出力ビルダー: `app/domain/builders/fundamental_output_impl.py`

責務:
- summary行の期間正規化（FY, 1Q, 2Q, 3Q）
- 同年度同期間レコードのマージ戦略
- 実績・予想・進捗の各種計算（`calc_*`）
- 出力生成（`build_*`）

非責務:
- HTTP通信そのもの
- GUIウィジェット操作

### 2.3 GUI層（画面表示 / 表示データ）
対象:
- `app/gui.py`, `app/gui_controller.py`, `app/gui_view.py`, `app/gui_view_model.py`
- プレゼンテーション橋渡し: `app/presenters.py`

責務:
- 銘柄選択、実行トリガ、表示更新
- ユースケースから返された出力文字列の表示
- 表示状態管理

非責務:
- JSON生データの解釈ロジック
- 財務指標計算ロジック

---

## 3. J-Quants 取得仕様（データ層）

### 3.1 APIエンドポイント
- 財務サマリー: `GET /v2/fins/summary`
- 銘柄マスタ: `GET /v2/equities/master`

### 3.2 取得フロー
1. `FundamentalAnalysisService.fetch_summary_rows(code4)` を呼ぶ。
2. `JQuantsClient.get_summary(code)` が `/fins/summary` を呼ぶ。
3. `get_all` が `pagination_key` を辿り、全ページを連結。
4. 取得結果を list[dict] で返却。

### 3.3 レート制限・再試行
- リクエスト間隔は `sleep_sec`（既定13秒）で制御。
- HTTP 429/5xx を対象に `Retry(total=2, backoff_factor=2.0)`。

---

## 4. 期間データ抽出仕様（ドメイン層）

実装主体: `app/domain/builders/fundamental_output_impl.py::_build_periods`

### 4.1 期間種別（Period Type）正規化
`CurPerType` 等から文字列を取得し、以下へ正規化する。

- `1Q` 判定: `"1Q"` または `"Q1"` を含む
- `2Q` 判定: `"2Q"` または `"Q2"` または `"HALF"` を含む
- `3Q` 判定: `"3Q"` または `"Q3"` を含む
- `FY` 判定: `"FY"` または `"ANNUAL"` または `"FULL"` を含む

該当しない行は除外。

### 4.2 年度（fiscal_year）抽出
- `CurPerSt`（代替キー含む）先頭4桁を年度として採用。
- 年度が解釈不能な行は除外。

### 4.3 同年度同期間のマージ
同じ `fiscal_year + period_type` が複数ある場合:

- `disclosed_at` が新しい行を優先 (`preferred`)。
- ただし空値は旧行 (`supplement`) で補完。

これにより「最新開示を基本にしつつ、欠損列は過去開示で埋める」挙動となる。

### 4.4 通期実績データ（最新FY / 前期FY）
- `latest_fy`: FYを持つ年度のうち最大年度。
- `prev_fy`: 原則 `latest_fy.fiscal_year - 1` の FY。
- 上記が無い場合は FY年度降順の2番目を採用。

### 4.5 四半期データ（latest_quarter）
- 年度を降順に探索。
- 各年度で `3Q -> 2Q -> 1Q` の順に存在確認。
- 最初に見つかったレコードを `latest_quarter` とする。

### 4.6 今期末予想データ（current_forecast）
1. 予想アンカー `forecast_anchor_fy_end`（決算期末日）を決定:
   - 優先1: `latest_quarter.cur_per_en`
   - 優先2: `latest_any.cur_per_en`（かつ最新FY以上の年度）
   - 優先3: `latest_fy.cur_per_en`
2. 同一 `cur_per_en` を持つレコード群を候補化。
3. 候補群を `disclosed_at` 降順でマージし、`current_forecast` とする。

### 4.7 来季予想データ（next_forecast）
`current_forecast` と同じ候補群から、以下を最大化して選ぶ:

1. `NxF*` 系キーの非空件数（`NxFSales`, `NxFOP`, `NxFOdP`, `NxFNP`, `NxFEPS` など）
2. 同点時は `disclosed_at` が新しい方

---

## 5. 指標計算時の参照優先順位（モデル層）

実装主体: `app/domain/models/metrics.py::calc_metrics`

### 5.1 実績値
- 通期実績は `latest_fy` / `prev_fy` から取得。
- 直近四半期値は `latest_quarter` から取得。

### 5.2 今期末予想値（Forecast）
各値（売上・営業益・経常益・純利益・EPS）は以下順で探索:
1. `latest_quarter` 行
2. `current_forecast` 行
3. `latest_fy` 行

### 5.3 来季予想値（Next Forecast）
各値は以下順で探索:
1. `next_forecast` 行
2. `current_forecast` 行
3. `latest_fy` 行

---

## 6. GUI表示に必要なデータ

GUIで最終表示する文字列は、ドメイン層 `build_fundamental_output_text_impl` が生成する。GUIはこの文字列を表示するのみ。

表示に使われる主要データ:
- 銘柄名・コード
- 株価 / 時価総額
- 実績（latest_fy, prev_fy）
- 今期予想（forecast_*）
- 来期予想（next_*）
- 直近四半期 EPS/PER
- スコア/ランク

---

## 7. 命名ポリシー適合
本仕様に関わる主要関数は以下命名方針に適合している。

- 取得: `fetch_master`, `fetch_summary_rows`, `fetch_price_snapshot`, `get_summary`, `get_all`
- 計算: `calc_metrics`, `calc_yoy`
- 判定: `grade_summary`, `rank_*`
- 出力生成: `build_fundamental_output_text`, `build_fundamental_output_text_impl`

