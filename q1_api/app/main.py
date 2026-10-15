"""Securities account identity verification API entry point."""

from contextlib import asynccontextmanager

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel

from app.batch_service import (
    CSVImportError,
    get_batch_details,
    import_batch,
    list_batch_cases,
)
from app.database import init_database
from app.ocr_processor import (
    get_pending_case_count,
    process_batch,
)
from app.review_service import (
    CaseNotFoundError,
    InvalidTransitionError,
    review_case,
)


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


class ReviewRequest(BaseModel):
    """Request body for one review decision."""

    stage: int
    decision: str


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


@app.post("/api/cases/{case_id}/review")
def create_case_review(
    case_id: int,
    request: ReviewRequest,
):
    """Apply a stage 1 or stage 2 review decision."""

    if request.stage not in {1, 2}:
        raise HTTPException(
            status_code=422,
            detail="stage must be 1 or 2",
        )

    if request.decision not in {"approve", "reject"}:
        raise HTTPException(
            status_code=422,
            detail="decision must be approve or reject",
        )

    try:
        return review_case(
            case_id=case_id,
            stage=request.stage,
            decision=request.decision,
        )
    except CaseNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post("/api/batches/{batch_id}/process", status_code=202)
def start_batch_processing(
    batch_id: int,
    background_tasks: BackgroundTasks,
):
    """Start OCR processing without waiting for completion."""

    pending_count = get_pending_case_count(batch_id)

    if pending_count is None:
        raise HTTPException(
            status_code=404,
            detail="batch not found",
        )

    if pending_count > 0:
        background_tasks.add_task(
            process_batch,
            batch_id,
        )

    return {
        "batch_id": batch_id,
        "processing_started": pending_count > 0,
        "pending_count": pending_count,
        "message": (
            "OCR processing started"
            if pending_count > 0
            else "no pending cases to process"
        ),
    }
