"""Legacy v1.1 Variation 재현성과 원자 Migration 검증."""

from hashlib import sha256
from pathlib import Path
from shutil import copytree

from VALIDATORS.io import load_json_object
from VALIDATORS.production_cli import run_cli
from VALIDATORS.variation import generate_legacy_variation_batch
from VALIDATORS.variation_registry import resolve_variation_runtime

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "legacy_v1_1"


def file_sha256(path: Path) -> str:
    """Fixture 파일의 SHA-256을 반환한다."""
    return sha256(path.read_bytes()).hexdigest()


def protected_hashes(project_path: Path) -> dict[str, str]:
    """Story와 Script Hash를 상대 경로로 반환한다."""
    paths = [project_path / "00_PROJECT" / "story_dna.json"]
    paths.extend(sorted((project_path / "07_SCRIPT").glob("*")))
    return {
        str(path.relative_to(project_path)): file_sha256(path) for path in paths if path.is_file()
    }


def test_legacy_seed_reproduces_base_candidate_signatures() -> None:
    """동일 Legacy Seed는 Base Candidate Selection과 Signature를 정확히 재현한다."""
    golden = load_json_object(FIXTURE_ROOT / "golden.json")
    legacy = load_json_object(FIXTURE_ROOT / "project" / "00_PROJECT" / "variation_candidates.json")
    config = {
        "channel_content_version": "1.1.0",
        "variation_engine_version": "1.0.0",
        "variation_catalog_version": "1.0.0",
    }
    runtime = resolve_variation_runtime(ROOT, config)
    generated = generate_legacy_variation_batch(
        str(golden["project_id"]),
        str(golden["story_seed"]),
        5,
        runtime,
        0,
    )
    generated_candidates = generated["candidates"]
    legacy_candidates = legacy["candidates"]
    assert isinstance(generated_candidates, list)
    assert isinstance(legacy_candidates, list)

    assert [candidate["selection"] for candidate in generated_candidates] == [
        candidate["selection"] for candidate in legacy_candidates
    ]
    assert [candidate["signature"] for candidate in generated_candidates] == [
        candidate["signature"] for candidate in legacy_candidates
    ]
    assert generated["story_seed_hash"] == legacy["story_seed_hash"]


def test_actual_legacy_fixture_migrates_without_story_or_script_change(
    tmp_path: Path,
) -> None:
    """신규 계약 파일이 없는 v1.1 Fixture를 내용 불변 상태로 원자 이전한다."""
    project_path = tmp_path / "PRJ-990"
    copytree(FIXTURE_ROOT / "project", project_path)
    absent_paths = (
        "00_PROJECT/project_constraints.json",
        "00_PROJECT/candidate_evaluation.json",
        "00_PROJECT/candidate_eligibility.json",
        "00_PROJECT/candidate_approval.json",
    )
    assert all(not (project_path / relative_path).exists() for relative_path in absent_paths)
    before_hashes = protected_hashes(project_path)
    before_variations = load_json_object(project_path / "00_PROJECT" / "variation_candidates.json")

    assert run_cli(["migrate-legacy-v1-1", str(project_path)]) == 0

    after_hashes = protected_hashes(project_path)
    config = load_json_object(project_path / "00_PROJECT" / "production_config.json")
    constraints = load_json_object(project_path / "00_PROJECT" / "project_constraints.json")
    variations = load_json_object(project_path / "00_PROJECT" / "variation_candidates.json")
    assert after_hashes == before_hashes
    assert config["variation_engine_version"] == "1.0.0"
    assert config["variation_catalog_version"] == "1.0.0"
    assert constraints["must_use"] == []
    assert constraints["must_not_use"] == []
    assert variations["approved_candidate_id"] == before_variations["approved_candidate_id"]
    before_candidates = before_variations["candidates"]
    after_candidates = variations["candidates"]
    assert isinstance(before_candidates, list)
    assert isinstance(after_candidates, list)
    assert [candidate["selection_status"] for candidate in after_candidates] == [
        candidate["selection_status"] for candidate in before_candidates
    ]
    assert all(
        candidate["variation_engine_version"] == "1.0.0"
        and candidate["variation_catalog_version"] == "1.0.0"
        for candidate in after_candidates
    )
    assert all(not (project_path / relative_path).exists() for relative_path in absent_paths[1:])
    change_log = (project_path / "00_PROJECT" / "change_log.jsonl").read_text(encoding="utf-8")
    assert "LEGACY_V1_1_MIGRATED" in change_log
    assert "MANUAL_REVIEW_REQUIRED" in change_log
    transaction_paths = list(
        (project_path / ".runtime" / "transactions").glob("*/transaction.json")
    )
    assert len(transaction_paths) == 1
    transaction = load_json_object(transaction_paths[0])
    assert transaction["status"] == "COMMITTED"
