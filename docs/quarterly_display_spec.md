# 四半期データ表示仕様（次実装用）

## 1. 目的
- J-Quants `/fins/summary` の生JSONから、`Sales→FSales→NxFSales` および `EPS→FEPS→NxFEPS` の流れを、
  **データ層 / ドメイン層 / GUI層** で責務分離して扱う。
- 会社予想（今期）と来期予想の比較を、最新四半期の進捗と同時に可視化する。

## 2. 現在のデータ成形フロー（実装準拠）

### 2.1 データ層（取得）
1. `JQuantsClient.get_summary(code)` で `/fins/summary` を取得。
2. キャッシュ経由で `summary_rows: list[dict]` として返す。

### 2.2 ドメイン層（期間正規化）
1. 1行ずつ `period_record` 相当へ変換（年度・期間種別 1Q/2Q/3Q/FY を決定）。
2. 同一年度・同一期間の重複は、開示日時で新しい行を優先。
3. 欠損補完が必要な場合は行マージ（片方にしかないキーを補完）。
4. `periods` に集約：
   - `latest_fy`, `prev_fy`, `latest_quarter`
   - `current_forecast`（今期予想アンカー）
   - `next_forecast`（来期予想アンカー）

### 2.3 ドメイン層（メトリクス計算）
- 取得優先順を決めて forecast 値を抽出：
  - 今期予想: `latest_quarter -> current_forecast -> latest_fy`
  - 来期予想: `next_forecast -> current_forecast -> latest_fy`
- キー吸収（短縮/表記ゆれ）:
  - 売上: `FSales`, `Fsales`, `NxFSales`, `NxFsales`
  - EPS: `FEPS`, `NxFEPS`
- YoY計算:
  - `forecast_sales_yoy = YoY(FSales, Sales)`
  - `forecast_eps_yoy = YoY(FEPS, EPS)`
  - `next_sales_yoy = YoY(NxFSales, FSales)`
  - `next_eps_yoy = YoY(NxFEPS, FEPS)`

### 2.4 GUI層（表示）
- ドメインの `metrics` を表示用テキストに整形。
- 生JSONキーには直接依存せず、`metrics` / `periods` のみ参照。

## 3. 次実装: 四半期表示仕様

## 3.1 表示ブロック
1. **四半期サマリ（最新四半期）**
   - 対象期間ラベル（例: `2025年度 3Q（2025-04-01〜2025-12-31 / 開示 2026-02-10 15:00）`）
   - 売上進捗（実績/通期予想）
   - 営業利益進捗（実績/通期予想）

2. **予想チェーン（Sales/EPS）**
   - 売上: `実績FY -> 今期予想(FSales) -> 来期予想(NxFSales)`
   - EPS: `実績FY -> 今期予想(FEPS) -> 来期予想(NxFEPS)`
   - 各矢印にYoYを併記。

3. **データソース注記**
   - `forecast_source_label` を明示（どの期間行から予想値を採用したか）。

## 3.2 表示フォーマット（テキスト）
- 売上チェーン（例）:
  - `売上チェーン: 3,000億円 -> 3,300億円 (YoY +10.0%) -> 3,630億円 (YoY +10.0%)`
- EPSチェーン（例）:
  - `EPSチェーン: 120.0円 -> 132.0円 (YoY +10.0%) -> 145.2円 (YoY +10.0%)`
- 欠損時:
  - 値が欠損なら `N/A`。
  - YoYの分母が0/負値/欠損なら `YoY N/A`。

## 3.3 層ごとの責務
- データ層:
  - API取得とキャッシュのみ。計算禁止。
- ドメイン層:
  - 期間正規化、forecast抽出、YoY計算、進捗計算。
  - 表示文言は持たず、表示向けDTO（ViewModel）を返す。
- GUI層:
  - ViewModelを人間可読テキスト/表へ render。

## 3.4 命名ポリシー適用
- 取得: `fetch_summary_rows`, `get_summary`
- 計算: `calc_metrics`, `calc_yoy`
- 判定: `rank_forecast_yoy`, `grade_summary`
- 出力生成: `build_output`, `render_quarter_table`

## 3.5 受け入れ条件
- `Sales/FSales/NxFSales` と `EPS/FEPS/NxFEPS` が同一ブロックで連続表示される。
- 表示値はすべて `metrics` 由来で、GUI層で生JSONを参照しない。
- 期間ソース注記が出る。
- 欠損時にクラッシュせず `N/A` 表示になる。
