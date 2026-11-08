import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from app.database import initialize
from app.routers.video import executor, load_samples, router


@asynccontextmanager
async def lifespan(app):
    initialize()
    try:
        load_samples()
    except HTTPException as error:
        logging.getLogger(__name__).error("Exemplos indisponíveis: %s", error.detail)
    yield
    executor.shutdown(wait=True)


app = FastAPI(title="Laboratório de Análise Forense de Vídeo", lifespan=lifespan)
app.include_router(router)


@app.websocket("/api/ws")
async def connection_status(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"status": "connected"})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logging.getLogger(__name__).debug("Cliente desconectado de /api/ws")