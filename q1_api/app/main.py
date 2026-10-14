"""Securities account identity verification API entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from app.batch_service import (
    CSVImportError,
    get_batch_details,
    import_batch,
    list_batch_cases,
)
from app.database import init_database


ALLOWED_CASE_STATUSES = {
    "pending",
    "ocr_done",
    "ocr_failed",
    "stage1_approved",
    "stage1_rejected",
    "stage2_approved",
    "stage2_rejected",
    "exported",
}


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialize application resources at startup."""

    init_database()
    yield


app = FastAPI(
    title="Securities Account Identity Verification",
    lifespan=lifespan,
)


@app.get("/api/health")
def health():
    """Return the API liveness status."""

    return {"status": "ok"}


@app.post("/api/batches", status_code=201)
async def create_batch(file: UploadFile = File(...)):
    """Import account applications from an uploaded CSV file."""

    filename = file.filename or "uploaded.csv"
    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="uploaded CSV file is empty",
        )

    try:
        return import_batch(filename, content)
    except CSVImportError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.get("/api/batches/{batch_id}")
def read_batch(batch_id: int):
    """Return batch details and case counts by status."""

    batch = get_batch_details(batch_id)

    if batch is None:
        raise HTTPException(
            status_code=404,
            detail="batch not found",
        )

    return batch


@app.get("/api/batches/{batch_id}/cases")
def read_batch_cases(
    batch_id: int,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """List cases with optional status filtering and pagination."""

    if status is not None and status not in ALLOWED_CASE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="invalid case status",
        )

    result = list_batch_cases(
        batch_id=batch_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="batch not found",
        )

    return result
