"""Web GUI版 ローカル音声入力ツール"""

import asyncio
import base64
import gc
import json
import os
import sys
import tempfile
import time
import traceback

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from faster_whisper import WhisperModel

# stdout/stderrのエンコーディング問題回避
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# --- 設定 ---
MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
LANGUAGE = "ja"
IDLE_TIMEOUT = 300  # 秒 (5分)

app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# --- グローバル状態 ---
model = None
model_state = "unloaded"  # "unloaded" | "loading" | "loaded"
last_used = 0.0
clients: set[WebSocket] = set()


async def broadcast(msg: dict):
    global clients
    dead = set()
    for ws in clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    clients -= dead


def status_msg():
    idle_remaining = None
    if model_state == "loaded":
        idle_remaining = max(0, IDLE_TIMEOUT - (time.time() - last_used))
    return {"type": "status", "model_state": model_state, "idle_remaining": idle_remaining}


def _load_model():
    """スレッド内でモデルをロード"""
    return WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)


def _transcribe(m, path):
    """スレッド内でジェネレータを消費して結果テキストを返す"""
    segments, _ = m.transcribe(
        path,
        language=LANGUAGE,
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        condition_on_previous_text=False,
    )
    return "".join(s.text for s in segments).strip()


async def idle_checker():
    global model, model_state
    while True:
        await asyncio.sleep(10)
        if model_state == "loaded" and time.time() - last_used > IDLE_TIMEOUT:
            model = None
            gc.collect()
            model_state = "unloaded"
            await broadcast(status_msg())


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(idle_checker())


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global model, model_state, last_used
    await ws.accept()
    clients.add(ws)
    await ws.send_json(status_msg())
    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)

            if data["type"] == "load_model":
                if model_state == "unloaded":
                    model_state = "loading"
                    await broadcast(status_msg())
                    try:
                        model = await asyncio.to_thread(_load_model)
                        model_state = "loaded"
                        last_used = time.time()
                    except Exception as e:
                        model_state = "unloaded"
                        print(f"Model load error: {e}", file=sys.stderr)
                        traceback.print_exc()
                        await ws.send_json({"type": "error", "message": f"Load failed: {e}"})
                    await broadcast(status_msg())

            elif data["type"] == "unload_model":
                if model_state == "loaded":
                    model = None
                    gc.collect()
                    model_state = "unloaded"
                    await broadcast(status_msg())

            elif data["type"] == "audio":
                if model is None:
                    await ws.send_json({"type": "error", "message": "Model not loaded"})
                    continue
                await ws.send_json({"type": "transcribing"})
                audio_bytes = base64.b64decode(data["data"])
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                        f.write(audio_bytes)
                        tmp_path = f.name
                    text = await asyncio.to_thread(_transcribe, model, tmp_path)
                    last_used = time.time()
                    await ws.send_json({"type": "result", "text": text})
                    await broadcast(status_msg())
                except Exception as e:
                    print(f"Transcribe error: {e}", file=sys.stderr)
                    traceback.print_exc()
                    await ws.send_json({"type": "error", "message": str(e)})
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)

    except WebSocketDisconnect:
        clients.discard(ws)
    except Exception as e:
        print(f"WebSocket error: {e}", file=sys.stderr)
        traceback.print_exc()
        clients.discard(ws)


if __name__ == "__main__":
    import webbrowser

    import uvicorn

    webbrowser.open("http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765)
