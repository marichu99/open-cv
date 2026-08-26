"""Real extraction backend — Claude Vision reads the candidate table straight
off the form photo/scan. Replaces the never-implemented YOLOv8 field-level
model (see git history for that stub); the whole-page prototype at
runs/train/form34a_detector was never sufficient for per-field extraction
anyway.

Uses a forced tool call (not free-text JSON parsing) so the response shape
is guaranteed — see the `claude-api` skill's guidance on structured output
via tool_choice.
"""

import base64
import mimetypes

import anthropic

from app.services.cv_pipeline import ExtractionResult, ExtractionService, FieldExtraction

MODEL = "claude-opus-5"

_POSITION_LABELS = {
    "president": "President",
    "governor": "Governor",
    "senator": "Senator",
    "woman_representative": "Woman Representative",
    "member_of_parliament": "Member of Parliament",
    "mca": "Member of County Assembly (MCA)",
}

_TOOL = {
    "name": "record_form_results",
    "description": "Record the election results read from the IEBC results form image.",
    "input_schema": {
        "type": "object",
        "properties": {
            "legible": {
                "type": "boolean",
                "description": "False if the handwriting/print is too unclear to be confident in the figures.",
            },
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Candidate's full name exactly as printed on the form."},
                        "party": {"type": ["string", "null"], "description": "Party name if printed, else null."},
                        "votes": {"type": "integer", "description": "Number of valid votes for this candidate."},
                    },
                    "required": ["name", "votes"],
                    "additionalProperties": False,
                },
            },
            "total_votes_cast": {"type": "integer", "description": "Total number of valid votes cast, as printed on the form."},
            "rejected_ballots": {"type": "integer", "description": "Total number of rejected ballot papers, as printed on the form."},
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "ONLY genuine concerns a human reviewer must double-check, e.g. an "
                    "unclear digit, an apparent alteration, or a total that does not "
                    "match the sum of candidate votes. Leave this an EMPTY array if the "
                    "form is clear and internally consistent — do NOT include "
                    "confirmations, positive notes, or restate that something checks out."
                ),
            },
        },
        "required": ["legible", "candidates", "total_votes_cast", "rejected_ballots", "warnings"],
        "additionalProperties": False,
    },
    "strict": True,
}


class ClaudeExtractionService(ExtractionService):
    def __init__(self):
        self.client = anthropic.Anthropic()

    def extract(self, image_path: str, position, declared_form_type: str) -> ExtractionResult:
        with open(image_path, "rb") as fh:
            image_bytes = fh.read()
        media_type = mimetypes.guess_type(image_path)[0] or "image/png"
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        position_label = _POSITION_LABELS.get(position.name, position.name)

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=(
                "You are transcribing a Kenyan IEBC election results form (Form "
                f"{declared_form_type}) for the {position_label} race, photographed or "
                "scanned by a field agent. Read every candidate row in the results "
                "table exactly as printed/handwritten, along with the total valid "
                "votes cast and rejected ballots. Call record_form_results with what "
                "you read. If any figure is genuinely illegible, set legible=false "
                "and explain why in warnings rather than guessing a number."
            ),
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "record_form_results"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": f"Extract the results from this {position_label} form."},
                ],
            }],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        data = tool_use.input

        legible = data["legible"]
        confidence = 0.95 if legible else 0.6
        warnings = list(data.get("warnings") or [])
        if not legible:
            warnings.append("Claude Vision flagged this form as difficult to read — verify manually.")

        votes = [
            FieldExtraction(
                candidate_name=c["name"],
                party=c.get("party"),
                votes=c["votes"],
                confidence=confidence,
            )
            for c in data["candidates"]
        ]

        return ExtractionResult(
            form_type_detected=declared_form_type,
            votes=votes,
            total_votes_cast=data["total_votes_cast"],
            rejected_ballots=data["rejected_ballots"],
            total_votes_confidence=confidence,
            rejected_ballots_confidence=confidence,
            warnings=warnings,
        )
