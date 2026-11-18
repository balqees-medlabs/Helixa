"""FastAPI application entry point.

Internal-only bind (FR-021): run the API with
``uvicorn app.main:app --host 127.0.0.1`` so it never listens on the LAN
interface directly — it is fronted by Caddy (M0), which terminates TLS and
proxies to localhost. Routers are registered in later phases.
"""

from fastapi import FastAPI

from app.api import auth, roles, samples, users

app = FastAPI(
    title="Helixa Backend API",
    description=(
        "Single writer and authority for authentication, RBAC, the gated "
        "8-stage sample workflow, turnaround metrics, report storage, and "
        "push to the Genomic Data Portal. Internal-only service; access via "
        "Caddy. Every request is executed as the non-superuser helixa_app "
        "role with a per-transaction acting identity (audit + RLS)."
    ),
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(samples.router)
