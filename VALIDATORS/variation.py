"""재현 가능한 다축 Story Variation 후보 생성."""

import re
from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from math import gcd

from VALIDATORS.exceptions import ConfigurationError

PROJECT_ID_PATTERN = re.compile(r"^PRJ-[0-9]{3,}$")
USER_CASE_STATUSES = {"LOCKED", "FLEXIBLE", "UNKNOWN"}


def require_dimensions(catalog: Mapping[str, object]) -> dict[str, list[str]]:
    """Variation Catalog의 문자열 선택지 사전을 엄격하게 읽는다."""
    value = catalog.get("dimensions")
    if not isinstance(value, Mapping):
        raise ConfigurationError("variation_catalog.dimensions 객체가 필요합니다.")
    dimensions: dict[str, list[str]] = {}
    for name, choices in value.items():
        if (
            not isinstance(name, str)
            or not isinstance(choices, list)
            or not choices
            or not all(isinstance(choice, str) for choice in choices)
        ):
            raise ConfigurationError(
                f"Variation Dimension 형식이 올바르지 않습니다: dimension={name!r}"
            )
        dimensions[name] = list(choices)
    if not dimensions:
        raise ConfigurationError("Variation Dimension이 하나 이상 필요합니다.")
    return dimensions


def seed_offset(seed: str, dimension: str, size: int) -> int:
    """Seed와 Dimension 이름으로 안정적인 선택 시작점을 계산한다."""
    digest = sha256(f"{seed}:{dimension}".encode()).hexdigest()
    return int(digest[:16], 16) % size


def coprime_step(preferred_step: int, size: int) -> int:
    """선택지 전체를 순회할 수 있는 가장 가까운 보폭을 반환한다."""
    if size < 1:
        raise ConfigurationError(f"Variation 선택지 개수가 올바르지 않습니다: size={size}")
    step = preferred_step
    while gcd(step, size) != 1:
        step += 1
    return step


def choose_dimension_value(
    choices: list[str],
    seed: str,
    dimension: str,
    candidate_index: int,
    dimension_index: int,
) -> str:
    """후보와 차원마다 다른 보폭으로 선택지를 결정한다."""
    offset = seed_offset(seed, dimension, len(choices))
    step = coprime_step(dimension_index * 2 + 1, len(choices))
    return choices[(offset + candidate_index * step) % len(choices)]


def candidate_signature(selection: Mapping[str, str]) -> str:
    """후보의 모든 Dimension 값을 결합한 구조 서명을 만든다."""
    payload = "|".join(f"{key}={selection[key]}" for key in sorted(selection))
    return sha256(payload.encode()).hexdigest()


def generate_variation_candidates(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    catalog: Mapping[str, object],
) -> dict[str, object]:
    """Story 문장을 쓰지 않고 구조적으로 구분되는 후보군을 생성한다."""
    if PROJECT_ID_PATTERN.fullmatch(project_id) is None:
        raise ConfigurationError(f"Project ID 형식이 올바르지 않습니다: {project_id!r}")
    if not story_seed.strip():
        raise ConfigurationError("Story Variation Seed는 비어 있을 수 없습니다.")
    if candidate_count < 3:
        raise ConfigurationError(
            f"비교 가능한 Variation 후보는 3개 이상이어야 합니다: count={candidate_count}"
        )

    dimensions = require_dimensions(catalog)
    dimension_items = sorted(dimensions.items())
    candidates: list[dict[str, object]] = []
    signatures: set[str] = set()
    for candidate_index in range(candidate_count):
        selection = {
            name: choose_dimension_value(
                choices,
                story_seed,
                name,
                candidate_index,
                dimension_index,
            )
            for dimension_index, (name, choices) in enumerate(dimension_items)
        }
        signature = candidate_signature(selection)
        if signature in signatures:
            raise ConfigurationError(
                "Variation Catalog의 조합 수가 부족해 후보가 충돌했습니다: "
                f"candidate_index={candidate_index}"
            )
        signatures.add(signature)
        candidates.append(
            {
                "candidate_id": f"VAR-{candidate_index + 1:02d}",
                "selection": selection,
                "signature": signature,
                "selection_status": "PENDING",
            }
        )

    return {
        "project_id": project_id,
        "story_seed_hash": sha256(story_seed.encode()).hexdigest(),
        "candidate_count": candidate_count,
        "candidates": candidates,
        "approved_candidate_id": None,
        "override": None,
    }


def require_user_case_constraints(
    production_config: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """USER_CASE의 Field, Value, Status 계약을 엄격하게 읽는다."""
    source_mode = production_config.get("story_source_mode")
    constraints = production_config.get("user_case_constraints")
    if source_mode != "USER_CASE":
        if constraints is not None:
            raise ConfigurationError(
                "USER_CASE가 아닌 Production Config에는 user_case_constraints를 둘 수 없습니다."
            )
        return []
    if not isinstance(constraints, list) or not constraints or not all(
        isinstance(constraint, Mapping) for constraint in constraints
    ):
        raise ConfigurationError(
            "USER_CASE에는 하나 이상의 user_case_constraints 객체가 필요합니다."
        )

    fields: list[str] = []
    for constraint in constraints:
        field = constraint.get("field")
        status = constraint.get("status")
        value = constraint.get("value")
        if not isinstance(field, str) or not field:
            raise ConfigurationError("USER_CASE Constraint field 문자열이 필요합니다.")
        if status not in USER_CASE_STATUSES:
            raise ConfigurationError(
                f"USER_CASE Constraint status가 올바르지 않습니다: field={field}, status={status!r}"
            )
        if status == "UNKNOWN" and value is not None:
            raise ConfigurationError(
                f"UNKNOWN Constraint value는 null이어야 합니다: field={field}"
            )
        if status != "UNKNOWN" and (not isinstance(value, str) or not value):
            raise ConfigurationError(
                f"LOCKED/FLEXIBLE Constraint value 문자열이 필요합니다: field={field}"
            )
        fields.append(field)
    duplicate_fields = sorted({field for field in fields if fields.count(field) > 1})
    if duplicate_fields:
        raise ConfigurationError(
            f"USER_CASE Constraint field가 중복됩니다: fields={duplicate_fields}"
        )
    return list(constraints)


def apply_user_case_constraints(
    candidates_document: Mapping[str, object],
    production_config: Mapping[str, object],
) -> dict[str, object]:
    """USER_CASE의 LOCKED 값을 모든 후보에 적용하고 Signature를 다시 계산한다."""
    constraints = require_user_case_constraints(production_config)
    if not constraints:
        return deepcopy(dict(candidates_document))
    next_document = deepcopy(dict(candidates_document))
    candidates = next_document.get("candidates")
    if not isinstance(candidates, list) or not all(
        isinstance(candidate, dict) for candidate in candidates
    ):
        raise ConfigurationError("Variation Candidate 객체 배열이 필요합니다.")

    signatures: set[str] = set()
    for candidate in candidates:
        selection = candidate.get("selection")
        if not isinstance(selection, dict) or not all(
            isinstance(field, str) and isinstance(value, str)
            for field, value in selection.items()
        ):
            raise ConfigurationError("Variation Candidate selection 문자열 객체가 필요합니다.")
        missing_fields = sorted(
            field
            for constraint in constraints
            if isinstance((field := constraint.get("field")), str)
            and field not in selection
        )
        if missing_fields:
            raise ConfigurationError(
                "USER_CASE Constraint가 Variation Catalog Dimension에 없습니다: "
                f"fields={missing_fields}"
            )
        for constraint in constraints:
            field = constraint.get("field")
            value = constraint.get("value")
            if constraint.get("status") == "LOCKED":
                if not isinstance(field, str) or not isinstance(value, str):
                    raise ConfigurationError("검증된 LOCKED Constraint 형식이 손상됐습니다.")
                selection[field] = value
        signature = candidate_signature(selection)
        if signature in signatures:
            raise ConfigurationError(
                "USER_CASE LOCKED 값 적용 후 Variation 후보가 충돌했습니다: "
                f"candidate_id={candidate.get('candidate_id')!r}"
            )
        signatures.add(signature)
        candidate["signature"] = signature
    return next_document


def approve_variation_candidate(
    candidates_document: Mapping[str, object],
    candidate_id: str,
) -> dict[str, object]:
    """후보 하나만 APPROVED로 표시한 새 Variation 문서를 반환한다."""
    candidates = candidates_document.get("candidates")
    if not isinstance(candidates, list) or not all(
        isinstance(candidate, Mapping) for candidate in candidates
    ):
        raise ConfigurationError("variation_candidates.candidates 객체 배열이 필요합니다.")
    candidate_ids = {candidate.get("candidate_id") for candidate in candidates}
    if candidate_id not in candidate_ids:
        raise ConfigurationError(
            f"승인할 Variation 후보가 없습니다: candidate_id={candidate_id}"
        )

    next_document = deepcopy(dict(candidates_document))
    next_candidates = next_document.get("candidates")
    if not isinstance(next_candidates, list):
        raise ConfigurationError("복사된 Variation 후보 배열이 올바르지 않습니다.")
    for candidate in next_candidates:
        if not isinstance(candidate, dict):
            raise ConfigurationError("복사된 Variation 후보 객체가 올바르지 않습니다.")
        candidate["selection_status"] = (
            "APPROVED" if candidate.get("candidate_id") == candidate_id else "REJECTED"
        )
    next_document["approved_candidate_id"] = candidate_id
    return next_document
