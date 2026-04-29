"""
Pydantic models for all agent input/output schemas.

Matches the output schemas defined in REFACTOR.md section 8.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

type PopularityEstimate = str  # "low" | "medium" | "high"
type ControversyLevel = str  # "low" | "medium" | "high"
type StanceLabel = str  # "positive" | "negative" | "mixed" | "fringe" | other


class Claim(BaseModel):
    """A single claim within a worker's output."""

    claim: str
    supporting_evidence: list[str] = Field(default_factory=list)
    rebuttals: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    popularity_estimate: PopularityEstimate = "medium"


class WorkerOutput(BaseModel):
    """Structured output from a single worker agent (section 8.1)."""

    run_id: str
    stance_id: str
    stance_label: StanceLabel
    summary: str
    top_claims: list[Claim] = Field(default_factory=list)
    crossover_positions: list[str] = Field(default_factory=list)
    antagonistic_positions: list[str] = Field(default_factory=list)
    fringe_positions: list[str] = Field(default_factory=list)
    consensus_points: list[str] = Field(default_factory=list)
    axes_of_debate: list[str] = Field(default_factory=list)
    key_sources: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class InterrogationExchange(BaseModel):
    """A single question/answer pair during judge interrogation."""

    worker_id: str
    question: str
    answer: str


class JudgeAggregate(BaseModel):
    """Judge's aggregated output across all workers (section 8.2)."""

    run_id: str
    topic: str
    stances: list[str] = Field(default_factory=list)
    controversy_level: ControversyLevel = "medium"
    agreement_matrix: list[dict[str, object]] = Field(default_factory=list)
    rebuttal_graph: list[dict[str, object]] = Field(default_factory=list)
    shared_ground: list[str] = Field(default_factory=list)
    fringe_positions: list[str] = Field(default_factory=list)
    conversation_locus_shift: str = ""
    judge_notes: str = ""
    interrogation_log: list[InterrogationExchange] = Field(default_factory=list)


class StancePlan(BaseModel):
    """A single stance assignment from the judge's planning phase."""

    stance_id: str
    stance_label: StanceLabel
    description: str


class JudgePlan(BaseModel):
    """The judge's planning output after Tavily research."""

    run_id: str
    topic: str
    conversation_breadth: str
    is_polarized: bool
    major_axes: list[str] = Field(default_factory=list)
    stances: list[StancePlan] = Field(default_factory=list)


class FinalReport(BaseModel):
    """The summarizer's final report output (section 8.3)."""

    run_id: str
    topic: str
    report_json: dict[str, object] = Field(default_factory=dict)
    report_md: str = ""


class InterrogationRequest(BaseModel):
    """Request body for the worker interrogation endpoint."""

    question: str


class InterrogationResponse(BaseModel):
    """Response body from the worker interrogation endpoint."""

    answer: str
