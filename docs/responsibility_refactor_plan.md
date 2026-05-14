# 責務分離の現状整理（ファイル単位）とリファクタープラン

## 目的
- 現在の実装を**データ層 / ドメイン層 / GUI層**の観点で棚卸しし、責務の混在箇所を明確にする。
- 保守性・可読性を高めるための段階的な改善計画を定義する。

## 現在の責務分離（ファイル単位）

### ルート層

#### `app/main.py`
- 主責務: アプリ起動エントリポイント。
- 層分類: GUI層のブートストラップ。
- 所見: 責務は明確で軽量。依存方向も `main -> gui` で適切。

#### `layers.py`
- 主責務: 層構造の実験・移行補助の可能性がある単一ファイル実装（実態は legacy 寄り）。
- 層分類: 混在（データ取得/計算/出力生成の同居リスク）。
- 所見: 現行 `app/*` 構成と重複する可能性が高く、将来的に削除または `legacy/` 隔離が望ましい。

#### `fundamental_jquants_v7.py`
- 主責務: 従来版の中核ロジック（監視銘柄読み込み・出力生成など）。
- 層分類: プレゼンテーション補助＋ドメイン/データの混在（legacy 一体型）。
- 所見: `app/presenters.py` から参照されており、移行のボトルネック。

#### `Fundamental_Summary_MD_v2.py`
- 主責務: 旧来のサマリ生成系スクリプト。
- 層分類: legacy 混在層。
- 所見: 利用経路を明確化し、未使用なら凍結対象。

### `app/` 配下

#### `app/repositories.py`
- 主責務:
  - J-Quants / yfinance 取得
  - キャッシュ（`FileCache`）
  - 取得値の最小整形
- 層分類: データ層。
- 良い点:
  - APIクライアントとキャッシュが一箇所に集約され、呼び出し側の複雑性を低減。
- 改善余地:
  - `JQuantsClient` と `yfinance` 関連、`FileCache` が同居し、責務粒度がやや大きい。

#### `app/services.py`
- 主責務:
  - `FundamentalAnalysisService` によるユースケース実行
  - `calc_*`, `grade_*`, `rank_*` の計算/判定
- 層分類: ドメイン層。
- 良い点:
  - 命名ポリシー（`fetch_*`, `calc_*`, `grade_*`, `rank_*`）に概ね準拠。
- 改善余地:
  - ファイルサイズが大きく、ユースケースと純粋関数群の同居で見通しが落ちる。

#### `app/presenters.py`
- 主責務:
  - GUIが使う形へ legacy 関数を橋渡し
- 層分類: プレゼンテーション層（GUI補助）。
- 良い点:
  - 境界アダプターとして有効。
- 改善余地:
  - 実体が `fundamental_jquants_v7.py` 依存のため、移行完了まで技術的負債を保持。

#### `app/gui.py`
- 主責務:
  - Tkinter UI描画、状態管理、非同期実行制御
  - ユースケース呼び出し
- 層分類: GUI層。
- 良い点:
  - API通信を直接実装せず `service` 経由で呼ぶ設計。
- 改善余地:
  - Viewロジック・状態管理・イベント処理が単一クラスに集中。
  - `FileCache` 生成責務まで GUI が持っている点は依存逆転の観点で再検討余地。

#### `app/__init__.py`
- 主責務: パッケージ定義。
- 層分類: 補助。

### `docs/` 配下

#### `docs/architecture_layers.md`
- 主責務: レイヤ責務と命名ポリシーの明文化。
- 層分類: 設計ドキュメント。
- 所見: 方針は明確。現実装との差分管理（どこまで移行済みか）を追記すると運用しやすい。

## 課題サマリ（保守性/可読性の観点）
1. **legacy 依存の残存**: `app/presenters.py` が `fundamental_jquants_v7.py` に依存。
2. **ドメイン層の肥大化**: `app/services.py` にユースケースと判定関数が集中。
3. **GUIの責務集中**: `FundamentalApp` が状態・イベント・スレッド制御を一手に担当。
4. **データ層の集約過多**: APIクライアント・外部ソース・キャッシュが単一ファイル。

## リファクタープラン（段階的）

### Phase 1: 境界明確化（低リスク）
- `app/services.py` を分割:
  - `app/domain/usecases/fundamental_analysis.py`（`FundamentalAnalysisService`）
  - `app/domain/models/metrics.py`（`calc_*`）
  - `app/domain/policies/ranking.py`（`grade_*`, `rank_*`）
- `app/repositories.py` を分割:
  - `app/data/jquants_client.py`
  - `app/data/market_data_provider.py`（yfinance）
  - `app/data/file_cache.py`
- 目的: 変更時の影響範囲縮小、レビュー容易化。

### Phase 2: legacy 段階移管（中リスク）
- 進捗メモ(2026-05-13): 出力生成のエントリを `app/domain/builders/fundamental_output.py` へ新設し、`app/presenters.py` から呼び出す構成へ変更済み。
- `fundamental_jquants_v7.py` の `build_output` 相当を新規 `build_*` 関数として `app/domain/builders/` へ移植。
- `app/presenters.py` は一時的に façade として残し、内部実装を新ドメイン関数へ切替。
- 完了後に `fundamental_jquants_v7.py` 依存を外す。

### Phase 3: GUIのMVP分離（中リスク）
- 進捗メモ(2026-05-14): GUI状態を `app/gui_state.py` へ抽出し、`FundamentalApp` は画面描画とイベント連携を中心に担当する構成へ一歩前進。
- 進捗メモ(2026-05-14): `app/gui_controller.py` を追加し、監視銘柄読込と分析出力取得のユースケース仲介をGUI本体から分離。
- `app/gui.py` を以下へ分割:
  - `app/gui/view.py`（Widget構築）
  - `app/gui/view_model.py`（表示用状態）
  - `app/gui/controller.py`（イベント処理）
- 進捗メモ(2026-05-14): `app/gui_view.py` を追加し、Widget構築と描画更新を `FundamentalView` へ分離。
- 非同期取得は `controller` に集約し、`view` は描画専任化。

### Phase 4: 依存逆転とテスト戦略（中〜高リスク）
- `FundamentalAnalysisService` は具体クラスではなく抽象 repository/proxy を受け取る構成へ。
- 追加テスト:
  - ドメイン純粋関数（`calc_*`, `grade_*`, `rank_*`）の単体テスト
  - UseCaseのモックテスト
  - GUI最小の統合テスト（イベント起点）

## 命名ポリシー適用の強化
- 取得: `fetch_*`, `get_*`
- 計算: `calc_*`
- 判定: `grade_*`, `rank_*`
- 出力生成: `build_*`, `render_*`

追加ルール案:
- 真偽返却関数は `is_*` / `has_*` を補助的に許可（`grade_*` と用途が異なるため）。
- DTO変換は `build_*_dto` に統一。

## 直近2スプリント実行案
- Sprint 1:
  1. `services.py` 分割
  2. `repositories.py` 分割
  3. 既存 import 経路を互換維持（re-export）
- Sprint 2:
  1. `build_output` の新ドメイン移植
  2. `presenters.py` の内部差し替え
  3. `legacy` モジュールの依存削減率を計測（KPI化）

## 完了判定KPI
- `app/services.py` 行数: 現在比 40% 以上削減
- `app/gui.py` 行数: 現在比 35% 以上削減
- `fundamental_jquants_v7.py` 直接参照: 0 箇所
- ドメイン判定関数テストカバレッジ: 90% 以上
