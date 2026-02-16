# offline-voice-input
完全ローカルで音声入力をするために自作した音声入力アプリ。
OpenAI Whisper の高速実装（faster-whisper）モデルをダウンロードして利用し、音声をローカルで文字起こしするため、利用許可いらずです。


  セットアップ

  前提条件

  - Python 3.7 以上
  - Windows

  インストール

  git clone https://github.com/xxxxx/voiceInput.git
  cd voiceInput
  pip install -r requirements.txt

  初回起動時に Whisper モデル（約500MB）が自動ダウンロードされ、以降はオフラインで動作します。

  使い方

  start.bat をダブルクリックして起動します。ブラウザが自動で開きます。

  1. 「モデルをロード」ボタンを押す
  2. マイクボタンを押して話す
  3. 停止すると文字起こし結果が表示され、クリップボードに自動コピーされる

  5分間操作がないとモデルは自動でアンロードされます。
