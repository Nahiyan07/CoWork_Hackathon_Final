# CoWork — Multi-Tenant Coworking Space Booking API

Fixed FastAPI/SQLAlchemy implementation for the ICT Fest Agentic AI Hackathon preliminary bug-fix challenge.

## Run

Recommended: Python 3.12 on Windows.

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Or:

```bash
docker compose up --build
```

If `pydantic-core` fails to build on Windows, install Visual Studio Build Tools with the C++ toolchain, or use Python 3.12.

Health check: `GET /health` returns `{"status":"ok"}`.
