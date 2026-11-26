from __future__ import annotations

import re

from app.schemas import QualityIssue, Requirement


VAGUE = {"fast", "secure", "easy", "appropriate", "efficient", "robust", "user-friendly", "adequate"}


def analyse(requirements: list[Requirement]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for req in requirements:
        statement = req.statement.lower()
        if any(word in statement for word in VAGUE):
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Ambiguity", severity="Medium", message="The requirement contains a qualitative term without a measurable threshold.", recommendation="Define an observable metric, limit, or acceptance test."))
        if not req.evidence:
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Missing evidence", severity="High", message="No source evidence is attached.", recommendation="Link an approved source or mark the item as an explicit stakeholder decision."))
        if not req.acceptance_criteria or any("Human reviewer" in item for item in req.acceptance_criteria):
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Lack of testability", severity="Medium", message="Acceptance criteria are absent or not yet measurable.", recommendation="Add pass/fail criteria, test data, and expected outcome."))
        if not any(category.value in {"Security", "Privacy", "Regulatory"} for category in req.categories):
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Missing security or compliance requirements", severity="Low", message="This item has no linked security, privacy, or regulatory control.", recommendation="Confirm whether a control is not applicable or add an evidence-backed control."))
    for index, first in enumerate(requirements):
        normalized = set(re.findall(r"[a-z]{5,}", first.statement.lower()))
        for second in requirements[index + 1:]:
            other = set(re.findall(r"[a-z]{5,}", second.statement.lower()))
            if normalized and len(normalized & other) / len(normalized | other) > 0.72:
                issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=first.id, check="Duplication", severity="Medium", message=f"Potential overlap with {second.id}.", recommendation="Merge, differentiate scope, or link the requirements."))
    return issues


def clarification_questions(issues: list[QualityIssue]) -> list[str]:
    """Create an actionable stakeholder clarification queue from quality findings."""
    prompts = {
        "Ambiguity": "What measurable threshold or observable outcome should replace the qualitative wording?",
        "Potential incompleteness": "Who performs this action, what triggers it, and what happens if it cannot complete?",
        "Lack of testability": "What pass/fail test, test data, and expected result will verify this requirement?",
        "Missing evidence": "Which approved statement or source supports this requirement?",
        "Undefined terminology": "How should the undefined term be defined in the project glossary or business rules?",
        "Potential conflict": "Which accountable stakeholder should resolve the conflicting expectations?",
        "Duplication": "Should the overlapping requirements be merged, separated by scope, or linked?",
        "Missing security or compliance requirements": "Has security, privacy, and compliance applicability been confirmed?",
    }
    questions: list[str] = []
    seen: set[tuple[str | None, str]] = set()
    for issue in issues:
        key = (issue.requirement_id, issue.check)
        if key in seen:
            continue
        seen.add(key)
        prefix = f"{issue.requirement_id}: " if issue.requirement_id else "Project: "
        questions.append(prefix + prompts.get(issue.check, issue.recommendation))
    return questions
