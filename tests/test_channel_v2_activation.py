"""Channel DNA 2.0 고정 Pin과 2.1 활성 Scaffold의 회귀 검증."""

from collections.abc import Mapping
from pathlib import Path

from VALIDATORS.channel_registry import resolve_project_channel
from VALIDATORS.compatibility import channel_dna_sha256
from VALIDATORS.io import load_json_object
from VALIDATORS.variation import generate_eligible_candidate_pool
from VALIDATORS.variation_registry import resolve_variation_runtime

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "channel_v2_activation" / "golden.json"


def candidate_projection(
    candidates: object,
) -> list[dict[str, object]]:
    """Golden 비교에 필요한 Candidate 식별자와 Signature만 투영한다."""
    assert isinstance(candidates, list)
    projected: list[dict[str, object]] = []
    for candidate in candidates:
        assert isinstance(candidate, Mapping)
        selection = candidate.get("selection")
        assert isinstance(selection, Mapping)
        assert selection.get("genre") == "CRIME_PSYCHOLOGICAL_THRILLER"
        projected.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "origin_batch_id": candidate.get("origin_batch_id"),
                "batch_candidate_id": candidate.get("batch_candidate_id"),
                "signature": candidate.get("signature"),
            }
        )
    return projected


def test_registered_v2_snapshot_and_active_v21_scaffold_are_independent() -> None:
    """기존 v2 Snapshot은 보존하고 활성 Alias와 신규 Scaffold만 v2.1에 결속한다."""
    active_path = ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"
    snapshot_path = (
        ROOT
        / "CHANNELS"
        / "mystery_main"
        / "versions"
        / "2.0.0"
        / "channel_dna.json"
    )
    active_snapshot_path = (
        ROOT
        / "CHANNELS"
        / "mystery_main"
        / "versions"
        / "2.1.0"
        / "channel_dna.json"
    )
    manifest = load_json_object(
        ROOT / "CHANNELS" / "mystery_main" / "channel_manifest.json"
    )
    config = load_json_object(
        ROOT / "TEMPLATES" / "PROJECT" / "00_PROJECT" / "production_config.json"
    )
    constraints = load_json_object(
        ROOT / "TEMPLATES" / "PROJECT" / "00_PROJECT" / "project_constraints.json"
    )
    active = load_json_object(active_path)
    v2_snapshot = load_json_object(snapshot_path)
    versions = manifest["available_versions"]
    limits = constraints["production_limits"]
    assert isinstance(versions, list)
    assert isinstance(limits, Mapping)
    v2_entry = next(
        entry
        for entry in versions
        if isinstance(entry, Mapping) and entry.get("content_version") == "2.0.0"
    )

    assert active_path.read_bytes() == active_snapshot_path.read_bytes()
    assert active["content_version"] == "2.1.0"
    assert manifest["active_content_version"] == "2.1.0"
    assert v2_entry["channel_dna"] == "versions/2.0.0/channel_dna.json"
    assert v2_entry["channel_dna_sha256"] == channel_dna_sha256(v2_snapshot)
    assert config["channel_content_version"] == "2.1.0"
    assert config["variation_engine_version"] == "2.1.0"
    assert config["variation_catalog_version"] == "2.1.0"
    assert config["genre"] == "CRIME_EVENT_THRILLER"
    assert limits["enforce_final_footprint"] is True


def test_v2_golden_candidate_pool_is_reproducible() -> None:
    """활성 v2 Engine과 Catalog는 Golden Candidate Pool을 정확히 재현해야 한다."""
    golden = load_json_object(GOLDEN_PATH)
    config = load_json_object(
        ROOT / "TEMPLATES" / "PROJECT" / "00_PROJECT" / "production_config.json"
    )
    config["channel_content_version"] = "2.0.0"
    config["variation_engine_version"] = "2.0.0"
    config["variation_catalog_version"] = "2.0.0"
    config["genre"] = "CRIME_PSYCHOLOGICAL_THRILLER"
    constraints = load_json_object(
        ROOT / "TEMPLATES" / "PROJECT" / "00_PROJECT" / "project_constraints.json"
    )
    project_id = golden["project_id"]
    story_seed = golden["story_seed"]
    assert isinstance(project_id, str)
    assert isinstance(story_seed, str)
    config["project_id"] = project_id
    constraints["project_id"] = project_id
    channel, _manifest, resolved_path = resolve_project_channel(ROOT, config, None)
    result = generate_eligible_candidate_pool(
        project_id,
        story_seed,
        5,
        resolve_variation_runtime(ROOT, config),
        "ORIGINAL_FICTION",
        config,
        constraints,
        channel,
        [],
        load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json"),
        load_json_object(ROOT / "STANDARD" / "candidate_projection_contract.json"),
        None,
        64,
    )
    actual = {
        "schema_family": "channel-v2-activation-golden",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "story_seed": story_seed,
        "channel_content_version": config["channel_content_version"],
        "channel_dna_sha256": channel_dna_sha256(channel),
        "variation_engine_version": result["variation_engine_version"],
        "variation_catalog_version": result["variation_catalog_version"],
        "catalog_sha256": result["catalog_sha256"],
        "algorithm_sha256": result["algorithm_sha256"],
        "implementation_sha256": result["implementation_sha256"],
        "candidate_count": result["candidate_count"],
        "batch_trace": result["batch_trace"],
        "candidates": candidate_projection(result["candidates"]),
    }

    assert resolved_path.relative_to(ROOT).as_posix() == (
        "CHANNELS/mystery_main/versions/2.0.0/channel_dna.json"
    )
    assert actual == golden
