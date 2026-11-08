import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

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