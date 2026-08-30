"""Project별 Channel Content Version Registry 해석 검증."""

import shutil
from pathlib import Path

import pytest

from VALIDATORS.channel_registry import resolve_project_channel
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object, write_json_object

ROOT = Path(__file__).resolve().parents[1]


def test_existing_project_keeps_v1_1_after_v2_activation() -> None:
    """활성 버전이 2.0이 되어도 1.1 Project는 고정된 DNA를 읽어야 한다."""
    channel_directory = ROOT / "CHANNELS" / "mystery_main"

    channel, _resolved_manifest, resolved_path = resolve_project_channel(
        ROOT,
        {
            "channel_id": "MYSTERY_MAIN",
            "channel_content_version": "1.1.0",
        },
        None,
    )

    assert channel["content_version"] == "1.1.0"
    assert resolved_path.relative_to(channel_directory).as_posix() == (
        "versions/1.1.0/channel_dna.json"
    )


def test_v2_snapshot_is_exact_active_dna_copy() -> None:
    """2.0.0 Snapshot은 현재 활성 DNA와 Byte 단위로 같아야 한다."""
    active = ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"
    snapshot = (
        ROOT
        / "CHANNELS"
        / "mystery_main"
        / "versions"
        / "2.0.0"
        / "channel_dna.json"
    )

    assert snapshot.read_bytes() == active.read_bytes()


def test_v1_1_snapshot_remains_distinct_and_registered() -> None:
    """기존 1.1.0 Snapshot은 활성 Alias와 분리된 등록 Version으로 남아야 한다."""
    active = load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json")
    legacy = load_json_object(
        ROOT
        / "CHANNELS"
        / "mystery_main"
        / "versions"
        / "1.1.0"
        / "channel_dna.json"
    )
    manifest = load_json_object(
        ROOT / "CHANNELS" / "mystery_main" / "channel_manifest.json"
    )

    assert active["content_version"] == "2.0.0"
    assert legacy["content_version"] == "1.1.0"
    assert manifest["active_content_version"] == "2.0.0"


def test_unregistered_pin_never_falls_back_to_active_version() -> None:
    """미등록 Pin은 Active DNA가 있어도 즉시 실패해야 한다."""
    with pytest.raises(ConfigurationError, match="CHANNEL_CONTENT_VERSION_NOT_FOUND"):
        resolve_project_channel(
            ROOT,
            {
                "channel_id": "MYSTERY_MAIN",
                "channel_content_version": "9.9.9",
            },
            None,
        )


def test_snapshot_change_fails_manifest_hash_binding(tmp_path: Path) -> None:
    """등록 Snapshot 내용이 변조되면 DNA Hash Binding이 실패한다."""
    repository_root = tmp_path / "repository"
    shutil.copytree(ROOT / "CHANNELS", repository_root / "CHANNELS")
    schema_directory = repository_root / "STANDARD" / "schemas"
    schema_directory.mkdir(parents=True)
    shutil.copy2(
        ROOT / "STANDARD" / "schemas" / "channel_manifest.schema.json",
        schema_directory / "channel_manifest.schema.json",
    )
    shutil.copy2(
        ROOT / "STANDARD" / "schemas" / "channel_dna.schema.json",
        schema_directory / "channel_dna.schema.json",
    )
    snapshot_path = (
        repository_root
        / "CHANNELS"
        / "mystery_main"
        / "versions"
        / "1.1.0"
        / "channel_dna.json"
    )
    changed = load_json_object(snapshot_path)
    changed["display_name"] = "변조된 Channel"
    write_json_object(snapshot_path, changed)
    with pytest.raises(ConfigurationError, match="CHANNEL_DNA_HASH_MISMATCH"):
        resolve_project_channel(
            repository_root,
            {
                "channel_id": "MYSTERY_MAIN",
                "channel_content_version": "1.1.0",
            },
            None,
        )
