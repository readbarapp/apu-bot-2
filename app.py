from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bot.catalogs import catalog_payload
from bot.logs import hub
from bot.manager import EngineError, manager
from bot.models import StartRequest
from bot.worker import SESSIONS_ROOT

ROOT = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    hub.info("system", "後台待命中：請由前端控制台啟動 Worker")
    yield
    if manager.running:
        await manager.stop(reason="伺服器關閉，正在停止所有 Worker")


app = FastAPI(title="HK iPhone Bot Console", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "templates" / "index.html")


@app.get("/api/catalog")
async def catalog() -> dict:
    return catalog_payload()


@app.get("/api/status")
async def status() -> dict:
    return manager.status()


@app.post("/api/start")
async def start(payload: StartRequest) -> dict:
    try:
        return await manager.start(payload)
    except EngineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/stop")
async def stop() -> dict:
    return await manager.stop()


@app.post("/api/workers/{worker_id}/focus")
async def focus_worker(worker_id: str) -> dict:
    try:
        return await manager.focus_worker(worker_id)
    except EngineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket) -> None:
    await ws.accept()
    queue = hub.subscribe()
    try:
        for item in hub.history():
            await ws.send_json(item)
        while True:
            await ws.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8765, reload=False)
