from __future__ import annotations

import re

from app.schemas import QualityIssue, Requirement


VAGUE = {"fast", "secure", "easy", "appropriate", "efficient", "robust", "user-friendly", "adequate"}
UNDEFINED_TERMS = {"etc", "as needed", "where applicable", "appropriate", "suitable"}


def analyse(requirements: list[Requirement]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for req in requirements:
        statement = req.statement.lower()
        if any(word in statement for word in VAGUE):
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Ambiguity", severity="Medium", message="The requirement contains a qualitative term without a measurable threshold.", recommendation="Define an observable metric, limit, or acceptance test."))
        if not req.evidence:
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Missing evidence", severity="High", message="No source evidence is attached.", recommendation="Link an approved source or mark the item as an explicit stakeholder decision."))
        if not req.acceptance_criteria or any("reviewer" in item.lower() for item in req.acceptance_criteria):
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Lack of testability", severity="Medium", message="Acceptance criteria are absent or not yet measurable.", recommendation="Add pass/fail criteria, test data, and expected outcome."))
        if not any(category.value in {"Security", "Privacy", "Regulatory"} for category in req.categories):
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Missing security or compliance requirements", severity="Low", message="This item has no linked security, privacy, or regulatory control.", recommendation="Confirm whether a control is not applicable or add an evidence-backed control."))
        if any(term in statement for term in UNDEFINED_TERMS):
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Undefined terminology", severity="Medium", message="The requirement contains a term whose meaning or boundary is not defined.", recommendation="Define the term in a glossary or replace it with an observable condition."))
        if len(req.statement.split()) < 7:
            issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=req.id, check="Potential incompleteness", severity="Medium", message="The requirement is too brief to identify actor, condition, and expected outcome.", recommendation="Clarify the actor, trigger, rule, outcome, and exception path with a stakeholder."))
    for index, first in enumerate(requirements):
        normalized = set(re.findall(r"[a-z]{5,}", first.statement.lower()))
        for second in requirements[index + 1:]:
            other = set(re.findall(r"[a-z]{5,}", second.statement.lower()))
            if normalized and len(normalized & other) / len(normalized | other) > 0.72:
                issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=first.id, check="Duplication", severity="Medium", message=f"Potential overlap with {second.id}.", recommendation="Merge, differentiate scope, or link the requirements."))
            negation_words = {"not", "never", "without", "prohibit"}
            shared = normalized & other
            if shared and bool(negation_words & set(first.statement.lower().split())) != bool(negation_words & set(second.statement.lower().split())):
                issues.append(QualityIssue(id=f"QI-{len(issues)+1:03d}", requirement_id=first.id, check="Potential conflict", severity="High", message=f"Potentially opposing statements detected with {second.id}.", recommendation="Ask the accountable stakeholders to resolve the conflict and record the decision."))
    return issues


def clarification_questions(issues: list[QualityIssue]) -> list[str]:
    """Turn deterministic findings into a small, actionable human-review queue."""
    questions: list[str] = []
    seen: set[tuple[str | None, str]] = set()
    templates = {
        "Ambiguity": "What measurable threshold or observable outcome should replace the qualitative wording?",
        "Potential incompleteness": "Who performs this action, what triggers it, and what happens when it cannot complete?",
        "Lack of testability": "What pass/fail acceptance test, test data, and expected result will verify this requirement?",
        "Missing evidence": "Which approved stakeholder statement, policy, or source document supports this requirement?",
        "Undefined terminology": "How should the undefined term be defined in the project glossary or business rules?",
        "Potential conflict": "Which accountable stakeholder should resolve the conflicting expectations, and what is the decision?",
        "Duplication": "Should the overlapping requirements be merged, separated by scope, or explicitly linked?",
        "Missing security or compliance requirements": "Has the security, privacy, and compliance applicability for this requirement been confirmed?",
    }
    for issue in issues:
        key = (issue.requirement_id, issue.check)
        if key in seen:
            continue
        seen.add(key)
        prefix = f"{issue.requirement_id}: " if issue.requirement_id else "Project: "
        questions.append(prefix + templates.get(issue.check, issue.recommendation))
    return questions
