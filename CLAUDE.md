# CLAUDE.md - voiceInput 開発ガイド

## プロジェクト概要

ローカル完結型の音声入力（Speech-to-Text）ツール。
OpenAI Whisper の高速実装 `faster-whisper` を使い、音声をローカルで文字起こしする。
音声データは外部サーバーに送信されず、完全にプライバシーが保たれる。

## ディレクトリ構成

```
voiceInput/
├── voice_web.py          # Web GUI 版サーバー（メインで使用）
├── voice_input.py        # CLI 版（Enter キーで録音制御、自動ペースト）
├── templates/
│   └── index.html        # Web GUI のフロントエンド（HTML/CSS/JS 単一ファイル）
├── requirements.txt      # Python 依存パッケージ
├── start.bat             # Windows 起動用バッチファイル
└── CLAUDE.md             # このファイル
```

## 技術スタック

| レイヤー | 技術 |
|----------|------|
| 音声認識エンジン | `faster-whisper`（Whisper の CTranslate2 最適化版） |
| バックエンド | Python, FastAPI, uvicorn |
| フロントエンド | Vanilla HTML/CSS/JS（フレームワークなし） |
| テンプレート | Jinja2（FastAPI 経由） |
| 通信 | WebSocket（リアルタイム双方向） |
| 音声キャプチャ(Web) | MediaRecorder API（WebM/Opus） |
| 音声キャプチャ(CLI) | `sounddevice`（PCM float32, 16kHz, mono） |
| クリップボード(CLI) | `pyperclip` + `pyautogui` |

## セットアップ

### 前提条件

- Python 3.7 以上
- マイクアクセス権限（ブラウザ / OS レベル）
- Windows（`start.bat` および CLI 版の `pyautogui` が Windows 向け）

### インストール

```bash
pip install -r requirements.txt
```

依存パッケージ:
- `faster-whisper` - 音声認識モデル
- `sounddevice` - オーディオキャプチャ（CLI 版）
- `numpy` - 音声バッファ操作（CLI 版）
- `pyperclip` - クリップボード操作（CLI 版）
- `pyautogui` - キーボード自動操作（CLI 版）
- `fastapi` - Web フレームワーク
- `uvicorn[standard]` - ASGI サーバー（WebSocket 対応）
- `jinja2` - テンプレートエンジン

### 起動方法

```bash
# Web 版（推奨）- ブラウザが自動で開く
python voice_web.py

# または Windows バッチから
start.bat

# CLI 版
python voice_input.py
```

Web 版は `http://127.0.0.1:8765` で起動する。

## アーキテクチャ

### Web 版（voice_web.py + index.html）

```
ブラウザ (index.html)
    │
    │  WebSocket (ws://127.0.0.1:8765/ws)
    ▼
FastAPI サーバー (voice_web.py)
    │
    │  asyncio.to_thread() でスレッドプールに委譲
    ▼
faster-whisper モデル (CPU, int8)
```

**サーバー側のグローバル状態:**
- `model` - Whisper モデルインスタンス（遅延ロード）
- `model_state` - `"unloaded"` → `"loading"` → `"loaded"`
- `last_used` - 最後に使用したタイムスタンプ（アイドルタイムアウト用）
- `clients` - 接続中の WebSocket クライアント集合

**アイドルタイムアウト:**
モデルロード後、5 分間（300 秒）操作がないと自動でアンロードしてメモリ解放する。
`idle_checker()` が 10 秒間隔でチェックし、タイムアウト時に `model = None` + `gc.collect()` を実行。

**非同期処理:**
Whisper の推論は CPU バウンドなので `asyncio.to_thread()` でスレッドプールに逃がし、
WebSocket のイベントループをブロックしないようにしている。

### WebSocket メッセージプロトコル

**クライアント → サーバー:**
```json
{"type": "load_model"}           // モデルロード要求
{"type": "unload_model"}         // モデルアンロード要求
{"type": "audio", "data": "..."}  // Base64 エンコードされた WebM 音声データ
```

**サーバー → クライアント:**
```json
{"type": "status", "model_state": "loaded", "idle_remaining": 280.5}
{"type": "transcribing"}          // 文字起こし処理中
{"type": "result", "text": "..."}  // 文字起こし結果
{"type": "error", "message": "..."}
```

ステータス変更時は `broadcast()` で全接続クライアントに通知する。

### CLI 版（voice_input.py）

起動時にモデルを即座にロード → Enter キーで録音開始/停止 → 結果をクリップボードにコピー＆ペースト。
`sounddevice.InputStream` のコールバックで音声バッファリングし、`threading.Event` で Enter キー待ちを実現。

## モデル設定

両バージョン共通の設定値（各ファイルの先頭で定義）:

```python
MODEL_SIZE = "small"        # Whisper モデルサイズ (tiny/base/small/medium/large)
DEVICE = "cpu"              # 推論デバイス (cpu/cuda)
COMPUTE_TYPE = "int8"       # 量子化タイプ (int8/int16/float16/float32)
LANGUAGE = "ja"             # 認識言語（日本語固定）
```

**推論パラメータ（`transcribe()` 呼び出し時）:**
```python
beam_size=1                       # ビームサーチ無効（最速）
vad_filter=True                   # 無音区間をスキップ
vad_parameters={"min_silence_duration_ms": 300}
condition_on_previous_text=False  # 前のテキストに依存しない（高速化）
```

## フロントエンド（templates/index.html）

単一 HTML ファイルに CSS・JS をすべて内包（499 行）。

**UI コンポーネント:**
- モデルステータス表示（ドットインジケータ + テキスト + アイドルカウントダウン）
- モデルのロード/アンロードボタン
- 円形マイクボタン（録音中はパルスアニメーション）
- 録音停止ボタン（録音中のみ表示）
- 結果表示エリア（`contentEditable` で直接編集可能）
- コピーボタン（トースト通知付き）
- ヘルプモーダル

**デザイン:**
- ダークテーマ（背景 `#1a1a2e`、カード `#16213e`、アクセント `#4ecca3`）
- コンテナ幅 520px、レスポンシブ対応（`max-width: 95vw`）

**音声録音フロー:**
1. `navigator.mediaDevices.getUserMedia({ audio: true })` でマイク取得
2. `MediaRecorder`（`audio/webm;codecs=opus`）で録音
3. 停止時に `Blob` → `FileReader.readAsDataURL()` → Base64 抽出
4. WebSocket で `{"type": "audio", "data": base64}` として送信

**自動コピー:**
文字起こし結果を受信すると `navigator.clipboard.writeText()` で自動的にクリップボードにコピーする。

## 開発上の注意事項

### Windows 固有の対応
- `voice_web.py` の冒頭で `sys.stdout` / `sys.stderr` を UTF-8 に再設定している（Windows のエンコーディング問題回避）
- `start.bat` は `cd /d "%~dp0"` でスクリプトのあるディレクトリに移動してから起動

### 音声ファイルの扱い（Web 版）
- 受信した Base64 音声データは `tempfile.NamedTemporaryFile(suffix=".webm")` で一時ファイルに書き出す
- faster-whisper に一時ファイルのパスを渡して推論
- 処理完了後 `os.unlink()` で必ず削除（`finally` ブロック内）

### エラーハンドリング
- WebSocket のエラーは `stderr` にトレースバック出力 + クライアントに JSON エラーメッセージ送信
- 切断されたクライアントは `broadcast()` 内で自動的に `clients` から除去

### UI の状態管理
- `modelState` 変数でボタンの有効/無効を一括制御
- `recording` フラグでマイクボタンの録音/停止トグルを管理
- アイドルカウントダウンはクライアント側で `setInterval` により毎秒更新

## 設計判断のまとめ

| 判断 | 理由 |
|------|------|
| ローカル完結 | プライバシー保護、オフライン動作可能 |
| 遅延ロード | 起動時間短縮、メモリ節約 |
| アイドルタイムアウト | 使わないときにメモリ解放（約 1GB） |
| WebSocket | リアルタイム双方向通信、ステータス更新の即時反映 |
| `asyncio.to_thread` | CPU バウンド推論でイベントループをブロックしない |
| `beam_size=1` + `int8` | 速度優先の設定 |
| 日本語固定 | ターゲットユーザーが日本語話者のため |
| フレームワークなし (フロント) | 依存を最小限にし、単一ファイルで完結 |
| `contentEditable` | 結果テキストの手動修正を可能にする |
