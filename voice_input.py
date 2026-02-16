"""ローカル音声入力ツール - faster-whisper を使った音声認識 & 自動ペースト"""

import os
import sys
import time
import threading
import numpy as np
import sounddevice as sd
import pyperclip
import pyautogui
from faster_whisper import WhisperModel

# --- 設定 ---
MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
LANGUAGE = "ja"
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"


def load_model():
    print("[...] モデルをロード中...")
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE, download_root=MODEL_DIR)
    print("[OK] モデルロード完了")
    return model


def record_audio():
    """Enterキーで録音開始/停止し、numpy配列を返す"""
    buffer = []
    stop_event = threading.Event()

    def callback(indata, frames, time_info, status):
        if status:
            print(f"  [sounddevice warning: {status}]", file=sys.stderr)
        buffer.append(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        callback=callback,
    )

    print("\n[REC] 録音中... (Enterで停止)")
    stream.start()

    # 別スレッドでEnter待ち（input()がブロッキングのため）
    def wait_for_enter():
        input()
        stop_event.set()

    t = threading.Thread(target=wait_for_enter, daemon=True)
    t.start()
    stop_event.wait()

    stream.stop()
    stream.close()

    if not buffer:
        return None

    audio = np.concatenate(buffer, axis=0).flatten()
    duration = len(audio) / SAMPLE_RATE
    print(f"  録音時間: {duration:.1f}秒")
    return audio


def transcribe(model, audio):
    print("[...] 変換中...")
    segments, info = model.transcribe(
        audio,
        language=LANGUAGE,
        beam_size=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
        condition_on_previous_text=False,
    )
    text = "".join(segment.text for segment in segments).strip()
    return text


def paste_text(text):
    pyperclip.copy(text)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")


def main():
    model = load_model()

    print("\n--- ローカル音声入力ツール ---")
    print("Enterキー: 録音開始/停止")
    print("Ctrl+C:    終了\n")

    try:
        while True:
            input("[待機中] Enterで録音開始 ")
            audio = record_audio()

            if audio is None or len(audio) == 0:
                print("  [!] 音声が取得できませんでした")
                continue

            text = transcribe(model, audio)

            if not text:
                print("  [!] テキストを認識できませんでした")
                continue

            print(f"  [結果] {text}")
            paste_text(text)
            print("  [OK] クリップボードにコピー＆ペースト完了")

    except KeyboardInterrupt:
        print("\n終了します")


if __name__ == "__main__":
    main()
