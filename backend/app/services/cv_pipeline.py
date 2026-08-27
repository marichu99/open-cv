"""Form extraction pipeline.

Defines the interface the rest of the backend codes against
(``ExtractionService.extract``), a deterministic mock used for tests/local
dev, and the real backend — Claude Vision (see claude_vision.py). Candidates
are discovered from the form itself (extraction returns names, not
pre-known ids) — see services/candidates.py for how those names become
Candidate rows.
"""

from __future__ import annotations

import hashlib
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import ElectivePosition


@dataclass
class FieldExtraction:
    candidate_name: str
    votes: int
    confidence: float
    party: str | None = None


@dataclass
class DetectedLocation:
    """The County/Constituency/Ward/Polling Station names read off the
    form's own header — compared against what the agent selected for the
    upload (see services/location_check.py) so a photo can't silently get
    recorded against the wrong station. Any field the model couldn't read
    stays None rather than guessing."""
    county: str | None = None
    constituency: str | None = None
    ward: str | None = None
    polling_station: str | None = None


@dataclass
class ExtractionResult:
    form_type_detected: str
    votes: list[FieldExtraction]
    total_votes_cast: int
    rejected_ballots: int
    total_votes_confidence: float
    rejected_ballots_confidence: float
    warnings: list[str] = field(default_factory=list)
    #: None means this backend doesn't read the form header at all (e.g. the
    #: mock backend) — location cross-checking is skipped in that case,
    #: rather than treating "nothing detected" as a mismatch.
    detected_location: DetectedLocation | None = None

    @property
    def overall_confidence(self) -> float:
        confidences = [v.confidence for v in self.votes] + [
            self.total_votes_confidence,
            self.rejected_ballots_confidence,
        ]
        return min(confidences) if confidences else 0.0


class ExtractionService(ABC):
    @abstractmethod
    def extract(self, image_path: str, position: "ElectivePosition", declared_form_type: str) -> ExtractionResult:
        ...


_MOCK_CANDIDATE_NAMES = ["Candidate A", "Candidate B", "Candidate C", "Candidate D"]


class MockExtractionService(ExtractionService):
    """Produces plausible, *deterministic* mock results — seeded from the
    image file's bytes so re-running extraction on the same photo (e.g. after
    a retake-vs-resubmit) gives a stable result rather than random noise.
    """

    def extract(self, image_path: str, position: "ElectivePosition", declared_form_type: str) -> ExtractionResult:
        with open(image_path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).digest()
        rng = random.Random(digest)

        votes: list[FieldExtraction] = []
        for name in _MOCK_CANDIDATE_NAMES:
            base = rng.randint(80, 420)
            confidence = rng.uniform(0.80, 0.99)
            # Occasionally simulate a hard-to-read handwritten cell.
            if rng.random() < 0.12:
                confidence = rng.uniform(0.55, 0.84)
            votes.append(FieldExtraction(candidate_name=name, votes=base, confidence=round(confidence, 4)))

        rejected = rng.randint(0, 12)
        total_cast = sum(v.votes for v in votes) + rejected

        warnings: list[str] = []
        # Rarely simulate a genuine arithmetic mismatch (mis-transcribed digit).
        if rng.random() < 0.08:
            total_cast += rng.choice([-1, 1]) * rng.randint(1, 15)
            warnings.append("sum(candidate votes) + rejected_ballots does not equal total_votes_cast")

        return ExtractionResult(
            form_type_detected=declared_form_type,
            votes=votes,
            total_votes_cast=total_cast,
            rejected_ballots=rejected,
            total_votes_confidence=round(rng.uniform(0.85, 0.99), 4),
            rejected_ballots_confidence=round(rng.uniform(0.85, 0.99), 4),
            warnings=warnings,
        )


def get_extraction_service(backend: str) -> ExtractionService:
    if backend == "claude":
        from app.services.claude_vision import ClaudeExtractionService

        return ClaudeExtractionService()
    return MockExtractionService()
