from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .live_asr import LiveASRService, SAMPLE_RATE


def local_socket(socket: WebSocket) -> bool:
    try:
        target = socket.url
        if target.hostname not in {"127.0.0.1", "localhost", "::1"}:
            return False
        if origin := socket.headers.get("origin"):
            source = urlsplit(origin)
            scheme = "https" if target.scheme == "wss" else "http"
            port = 443 if scheme == "https" else 80
            return (source.scheme, source.hostname, source.port or port) == (scheme, target.hostname, target.port or port)
        return True
    except ValueError:
        return False


def create_router(service: LiveASRService, languages: set[str]) -> APIRouter:
    router = APIRouter()

    @router.websocket("/api/asr/live")
    async def live_transcription(socket: WebSocket) -> None:
        if not local_socket(socket):
            await socket.close(code=1008)
            return
        await socket.accept()
        session = None
        tasks = []
        loop = asyncio.get_running_loop()
        events: asyncio.Queue = asyncio.Queue()

        def emit(event):
            try:
                if not loop.is_closed():
                    loop.call_soon_threadsafe(events.put_nowait, event)
            except RuntimeError:
                pass  # Server shutdown may finish after the socket's event loop.

        try:
            config = await asyncio.wait_for(socket.receive_json(), timeout=15)
            if not isinstance(config, dict) or config.get("type") != "start":
                raise ValueError("Start the live session before sending audio.")
            language = config.get("language", "auto")
            prompt = config.get("prompt", "")
            model_key = config.get("model", "whisper")
            if not isinstance(model_key, str):
                raise ValueError("Choose an available transcription model.")
            if not isinstance(language, str) or language not in languages or not isinstance(prompt, str) or len(prompt) > 1000:
                raise ValueError("Choose a supported language and vocabulary hints of at most 1,000 characters.")
            if config.get("sample_rate") != SAMPLE_RATE:
                raise ValueError("Live audio must be mono PCM16 at 16 kHz.")
            session = service.start(language, prompt, emit, model_key=model_key)

            async def receive():
                try:
                    while True:
                        message = await asyncio.wait_for(socket.receive(), timeout=30)
                        if message["type"] == "websocket.disconnect":
                            return
                        if message.get("bytes") is not None:
                            await asyncio.to_thread(session.feed, message["bytes"])
                        else:
                            if json.loads(message.get("text", "{}")) == {"type": "stop"}:
                                return
                            raise ValueError("Unsupported live transcription message.")
                except (ValueError, asyncio.TimeoutError) as exc:
                    emit({"type": "stopping", "message": str(exc) or "Audio input timed out. Saving the recording."})
                finally:
                    session.stop()

            async def send():
                while True:
                    event = await events.get()
                    await socket.send_json(event)
                    if event["type"] in {"complete", "error", "cancelled"}:
                        return

            tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            if tasks[0] in done:
                await tasks[1]
        except (WebSocketDisconnect, RuntimeError):
            pass
        except (ValueError, asyncio.TimeoutError) as exc:
            await socket.send_json({"type": "error", "message": str(exc) or "Live transcription setup timed out."})
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if session:
                session.stop()
                # Finish received audio even if the browser leaves or disconnects.
                await asyncio.to_thread(session.thread.join, 125)
            try:
                await socket.close()
            except RuntimeError:
                pass

    return router
