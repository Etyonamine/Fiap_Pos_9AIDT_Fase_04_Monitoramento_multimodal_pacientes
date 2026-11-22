import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.database import initialize
from app.routers.audio import executor as audio_executor, router as audio_router
from app.routers.camera import router as camera_router, shutdown as shutdown_camera
from app.routers.clinical_data import router as clinical_data_router
from app.routers.video import executor, load_samples, router
from app.routers.monitor import router as monitor_router, shutdown as shutdown_monitor
from app.routers.incidents import router as incidents_router
from app.routers.notifications import router as notifications_router
from app.routers.synthetic_stream import router as synthetic_stream_router
from app.services.webhook_notifications import start_worker, stop_worker


@asynccontextmanager
async def lifespan(app):
    initialize()
    start_worker()
    try:
        try:
            load_samples()
        except HTTPException as error:
            logging.getLogger(__name__).error("Exemplos indisponíveis: %s", error.detail)
        yield
    finally:
        try:
            shutdown_camera()
            executor.shutdown(wait=True)
            shutdown_monitor()
            audio_executor.shutdown(wait=True)
        finally:
            stop_worker()


app = FastAPI(title="Monitoramento multimodal de pacientes", lifespan=lifespan)
app.include_router(router)
app.include_router(audio_router)
app.include_router(monitor_router)
app.include_router(camera_router)
app.include_router(incidents_router)
app.include_router(clinical_data_router)
app.include_router(notifications_router)
app.include_router(synthetic_stream_router)


@app.websocket("/api/ws")
async def connection_status(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"status": "connected"})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logging.getLogger(__name__).debug("Cliente desconectado de /api/ws")