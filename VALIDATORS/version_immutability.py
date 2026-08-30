"""Base Branch에 등록된 Variation Version 파일의 불변성을 검증한다."""

import argparse
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object

ENGINE_REGISTRY_PATH = "STANDARD/variation_engines/registry.json"
CATALOG_REGISTRY_PATH = "STANDARD/variation_catalogs/registry.json"


def registry_mapping(document: Mapping[str, object], field: str) -> Mapping[str, object]:
    """Version Registry의 Entry 사전을 반환한다."""
    entries = document.get(field)
    if not isinstance(entries, Mapping):
        raise ConfigurationError(f"VARIATION_REGISTRY_INVALID: field={field}")
    return entries


def protected_registered_paths(
    engine_registry: Mapping[str, object],
    catalog_registry: Mapping[str, object],
) -> set[str]:
    """Base Registry에 이미 등록된 불변 파일 경로를 반환한다."""
    protected: set[str] = set()
    for entry in registry_mapping(engine_registry, "engines").values():
        if not isinstance(entry, Mapping):
            continue
        specification_path = entry.get("path")
        if isinstance(specification_path, str):
            protected.add(specification_path)
        implementation = entry.get("implementation")
        files = implementation.get("files") if isinstance(implementation, Mapping) else None
        if isinstance(files, list):
            protected.update(path for path in files if isinstance(path, str))
    for entry in registry_mapping(catalog_registry, "catalogs").values():
        if not isinstance(entry, Mapping):
            continue
        catalog_path = entry.get("path")
        if isinstance(catalog_path, str):
            protected.add(catalog_path)
    return protected


def changed_registry_entries(
    base_registry: Mapping[str, object],
    current_registry: Mapping[str, object],
    field: str,
    registry_path: str,
) -> list[str]:
    """Base에 등록된 Version Entry의 삭제·변경을 반환한다."""
    base_entries = registry_mapping(base_registry, field)
    current_entries = registry_mapping(current_registry, field)
    return [
        f"{registry_path}#{field}.{version}"
        for version, base_entry in sorted(base_entries.items())
        if current_entries.get(version) != base_entry
    ]


def registered_version_mutations(
    repository_root: Path,
    base_files: Mapping[str, bytes],
    base_engine_registry: Mapping[str, object],
    base_catalog_registry: Mapping[str, object],
) -> list[str]:
    """현재 Worktree에서 변경·누락된 Base 등록 파일을 반환한다."""
    current_engine_registry = load_json_object(repository_root / ENGINE_REGISTRY_PATH)
    current_catalog_registry = load_json_object(repository_root / CATALOG_REGISTRY_PATH)
    mutations: list[str] = [
        *changed_registry_entries(
            base_engine_registry,
            current_engine_registry,
            "engines",
            ENGINE_REGISTRY_PATH,
        ),
        *changed_registry_entries(
            base_catalog_registry,
            current_catalog_registry,
            "catalogs",
            CATALOG_REGISTRY_PATH,
        ),
    ]
    for relative_path in sorted(
        protected_registered_paths(base_engine_registry, base_catalog_registry)
    ):
        expected = base_files.get(relative_path)
        current_path = repository_root / relative_path
        if expected is None or not current_path.is_file():
            mutations.append(relative_path)
            continue
        try:
            current = current_path.read_bytes()
        except OSError as error:
            raise ConfigurationError(f"REGISTERED_VERSION_MUTATED: path={relative_path}") from error
        if current != expected:
            mutations.append(relative_path)
    return sorted(mutations)


def git_show_bytes(repository_root: Path, base_ref: str, relative_path: str) -> bytes | None:
    """Base Ref의 파일 Bytes를 Shell 해석 없이 읽는다."""
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{relative_path}"],
        cwd=repository_root,
        check=False,
        capture_output=True,
    )
    if result.returncode == 0:
        return result.stdout
    return None


def json_object_from_bytes(content: bytes, source: str) -> dict[str, object]:
    """Git Blob을 JSON 객체로 변환한다."""
    try:
        decoded = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"VARIATION_REGISTRY_INVALID: source={source}") from error
    if not isinstance(decoded, dict):
        raise ConfigurationError(f"VARIATION_REGISTRY_INVALID: source={source}")
    return cast(dict[str, object], decoded)


def mutations_against_base(repository_root: Path, base_ref: str) -> list[str]:
    """Base Ref Registry가 존재할 때 등록 Version 변조를 검사한다."""
    engine_bytes = git_show_bytes(repository_root, base_ref, ENGINE_REGISTRY_PATH)
    catalog_bytes = git_show_bytes(repository_root, base_ref, CATALOG_REGISTRY_PATH)
    if engine_bytes is None and catalog_bytes is None:
        return []
    if engine_bytes is None or catalog_bytes is None:
        raise ConfigurationError("REGISTERED_VERSION_MUTATED: Base Registry Bundle이 불완전합니다.")
    engine_registry = json_object_from_bytes(engine_bytes, ENGINE_REGISTRY_PATH)
    catalog_registry = json_object_from_bytes(catalog_bytes, CATALOG_REGISTRY_PATH)
    base_files = {
        path: content
        for path in protected_registered_paths(engine_registry, catalog_registry)
        if (content := git_show_bytes(repository_root, base_ref, path)) is not None
    }
    return registered_version_mutations(
        repository_root,
        base_files,
        engine_registry,
        catalog_registry,
    )


def parser() -> argparse.ArgumentParser:
    """Registered Version CI 검사 Argument Parser를 반환한다."""
    result = argparse.ArgumentParser(
        description="Base Branch에 등록된 Variation Version 파일의 변조를 검사합니다.",
    )
    result.add_argument("--base-ref", required=True)
    return result


def main() -> int:
    """CI에서 사용할 Registered Version 불변성 검사 종료 코드를 반환한다."""
    args = parser().parse_args()
    repository_root = Path.cwd()
    try:
        mutations = mutations_against_base(repository_root, str(args.base_ref))
    except ConfigurationError as error:
        print(str(error))
        return 1
    if mutations:
        print(f"REGISTERED_VERSION_MUTATED: 새 Version을 등록해야 합니다: paths={mutations}")
        return 1
    current_engine_registry = load_json_object(repository_root / ENGINE_REGISTRY_PATH)
    current_catalog_registry = load_json_object(repository_root / CATALOG_REGISTRY_PATH)
    protected_registered_paths(current_engine_registry, current_catalog_registry)
    print("REGISTERED_VERSION_IMMUTABILITY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
