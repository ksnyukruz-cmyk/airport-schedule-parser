"""Веб-сервер табло."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.http_client import SourceError
from app.service import get_schedule, list_airports, today_moscow

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

app = FastAPI(
    title="Табло аэропортов",
    description="Парсер табло крупных аэропортов мира.",
    version=__version__,
)


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.get("/api/airports")
def airports():
    return {"airports": list_airports()}


@app.get("/api/schedule")
def schedule(
    airport: str = Query(..., min_length=3, max_length=3, description="Код IATA"),
    direction: str = Query("departure", pattern="^(departure|arrival)$"),
    day: date | None = Query(None, alias="date"),
    refresh: bool = False,
):
    chosen = day or today_moscow()
    try:
        return get_schedule(airport, direction, chosen, refresh=refresh)
    except KeyError:
        raise HTTPException(status_code=404, detail="Этот аэропорт пока не подключён") from None
    except SourceError as error:
        detail = str(error)
        if "429" in detail or "http" in detail.lower():
            detail = "Лента рейсов сейчас перегружена. Подождите минуту и нажмите «Обновить»."
        raise HTTPException(status_code=502, detail=detail) from error


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
