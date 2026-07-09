"""CoWork API application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from .database import Base, engine
from .errors import AppError, app_error_handler
from .routers import admin, auth, bookings, health, rooms

app = FastAPI(title="CoWork API", version="1.0.0")

@app.get("/")
def root():
    return RedirectResponse(url="/docs")

Base.metadata.create_all(bind=engine)

app.add_exception_handler(AppError, app_error_handler)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(bookings.router)
app.include_router(admin.router)
