import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.database import initialize
from app.routers.audio import executor as audio_executor, router as audio_router
from app.routers.camera import router as camera_router, shutdown as shutdown_camera
from app.routers.video import executor, load_samples, router
from app.routers.monitor import router as monitor_router, shutdown as shutdown_monitor


@asynccontextmanager
async def lifespan(app):
    initialize()
    try:
        load_samples()
    except HTTPException as error:
        logging.getLogger(__name__).error("Exemplos indisponíveis: %s", error.detail)
    yield
    shutdown_camera()
    executor.shutdown(wait=True)
    shutdown_monitor()
    audio_executor.shutdown(wait=True)


app = FastAPI(title="Monitoramento multimodal de pacientes", lifespan=lifespan)
app.include_router(router)
app.include_router(audio_router)
app.include_router(monitor_router)
app.include_router(camera_router)


@app.websocket("/api/ws")
async def connection_status(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"status": "connected"})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logging.getLogger(__name__).debug("Cliente desconectado de /api/ws")