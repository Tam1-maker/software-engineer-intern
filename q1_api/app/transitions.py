"""Review state-transition rules for account application cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewTransition:
    """One allowed review transition."""

    current_status: str
    stage: int
    decision: str
    next_status: str


REVIEW_TRANSITIONS = (
    ReviewTransition("ocr_done", 1, "approve", "stage1_approved"),
    ReviewTransition("ocr_done", 1, "reject", "stage1_rejected"),
    ReviewTransition(
        "stage1_approved",
        2,
        "approve",
        "stage2_approved",
    ),
    ReviewTransition(
        "stage1_approved",
        2,
        "reject",
        "stage2_rejected",
    ),
)


TRANSITION_LOOKUP = {
    (
        transition.current_status,
        transition.stage,
        transition.decision,
    ): transition.next_status
    for transition in REVIEW_TRANSITIONS
}


def determine_next_status(
    current_status: str,
    stage: int,
    decision: str,
) -> str | None:
    """Return the next status when a transition is allowed."""

    return TRANSITION_LOOKUP.get(
        (current_status, stage, decision)
    )


def explain_invalid_transition(
    current_status: str,
    stage: int,
) -> str:
    """Explain why a requested review is invalid."""

    if current_status == "pending":
        return "case must complete OCR before review"

    if current_status == "ocr_failed":
        return "an OCR-failed case cannot be reviewed"

    if current_status in {
        "stage1_rejected",
        "stage2_rejected",
    }:
        return "a rejected case cannot be reviewed again"

    if stage == 2 and current_status != "stage1_approved":
        return "stage 2 review requires stage 1 approval"

    if current_status in {
        "stage1_approved",
        "stage2_approved",
        "exported",
    }:
        return "this review stage has already been completed"

    return (
        f"review stage {stage} is not allowed "
        f"while case status is {current_status}"
    )
