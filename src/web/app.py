"""FastAPI web application."""

from fastapi import FastAPI

app = FastAPI(
    title="AnimeAIDub",
    description="AI-powered anime dubbing pipeline",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/")
async def root():
    """Root endpoint - will serve Web UI."""
    return {"message": "AnimeAIDub v0.1.0", "docs": "/docs"}
