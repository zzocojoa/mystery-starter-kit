"""Project별 Channel Content Version Registry 해석 검증."""

import shutil
from copy import deepcopy
from pathlib import Path

from VALIDATORS.channel_registry import resolve_project_channel
from VALIDATORS.compatibility import channel_dna_sha256
from VALIDATORS.io import load_json_object, write_json_object

ROOT = Path(__file__).resolve().parents[1]


def test_existing_project_keeps_v1_1_after_v2_activation(tmp_path: Path) -> None:
    """활성 버전이 2.0이 되어도 1.1 Project는 고정된 DNA를 읽어야 한다."""
    repository_root = tmp_path / "repository"
    shutil.copytree(ROOT / "CHANNELS", repository_root / "CHANNELS")
    schema_directory = repository_root / "STANDARD" / "schemas"
    schema_directory.mkdir(parents=True)
    shutil.copy2(
        ROOT / "STANDARD" / "schemas" / "channel_manifest.schema.json",
        schema_directory / "channel_manifest.schema.json",
    )
    channel_directory = repository_root / "CHANNELS" / "mystery_main"
    v1_channel = load_json_object(channel_directory / "channel_dna.json")
    v2_channel = deepcopy(v1_channel)
    v2_channel["content_version"] = "2.0.0"
    v2_path = channel_directory / "channel_dna_2.0.0.json"
    write_json_object(v2_path, v2_channel)
    manifest_path = channel_directory / "channel_manifest.json"
    manifest = load_json_object(manifest_path)
    versions = manifest["available_versions"]
    assert isinstance(versions, list)
    versions.append(
        {
            "content_version": "2.0.0",
            "channel_dna": "channel_dna_2.0.0.json",
            "channel_dna_sha256": channel_dna_sha256(v2_channel),
        }
    )
    manifest["active_content_version"] = "2.0.0"
    write_json_object(manifest_path, manifest)

    channel, _resolved_manifest, resolved_path = resolve_project_channel(
        repository_root,
        {
            "channel_id": "MYSTERY_MAIN",
            "channel_content_version": "1.1.0",
        },
        None,
    )

    assert channel["content_version"] == "1.1.0"
    assert resolved_path.name == "channel_dna.json"
