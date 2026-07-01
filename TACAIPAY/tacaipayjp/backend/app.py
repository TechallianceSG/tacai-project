"""TACAI Pay JP — Japan payroll FastAPI application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import DEFAULT_PORT

STATIC_DIR = Path(__file__).resolve().parent / "statics"

app = FastAPI(
    title="TACAI Pay JP",
    description="Japan payroll parameter management and calculation API",
    version="0.1.0",
)

# CORS — allow Vite dev server (port 5173) and local access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8017",
        "http://localhost:8017",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "module": "tacaipayjp"}


# ── Mount routers (import here to avoid circular imports) ──
from routers import auth_router  # noqa: E402
from routers import social_insurance, remuneration_grades, tax_brackets, accident_insurance  # noqa: E402
from routers import dashboard  # noqa: E402
from routers import salary_master, salary_master_page  # noqa: E402
from routers import monthly_sheets  # noqa: E402
from routers import release  # noqa: E402

app.include_router(salary_master.router)
app.include_router(monthly_sheets.router)
app.include_router(release.router)
app.include_router(dashboard.router)
app.include_router(salary_master_page.router)
app.include_router(auth_router.router)
app.include_router(social_insurance.router)
app.include_router(remuneration_grades.router)
app.include_router(tax_brackets.router)
app.include_router(accident_insurance.router)


# ── Serve Vue SPA in production ──
if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve Vue SPA — all non-API routes fall back to index.html."""
        file_path = STATIC_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            from fastapi.responses import FileResponse
            return FileResponse(str(file_path))
        from fastapi.responses import FileResponse
        return FileResponse(str(STATIC_DIR / "index.html"))
    print(f"[tacaipayjp] Serving Vue SPA from {STATIC_DIR}", flush=True)


if __name__ == "__main__":
    import uvicorn
    print(f"[tacaipayjp] Starting FastAPI on port {DEFAULT_PORT}", flush=True)
    uvicorn.run("app:app", host="127.0.0.1", port=DEFAULT_PORT, reload=True)
