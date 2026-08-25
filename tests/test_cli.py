"""호환성 CLI 통합 검증."""

from pathlib import Path

from VALIDATORS.cli import run_cli
from VALIDATORS.io import load_json_object

ROOT = Path(__file__).resolve().parents[1]


def test_cli_writes_pass_report(tmp_path: Path) -> None:
    """기준 입력으로 실행하면 PASS 보고서를 파일에 기록해야 한다."""
    output_path = tmp_path / "compatibility_report.json"
    exit_code = run_cli(
        (
            "--contract",
            str(ROOT / "STANDARD" / "compatibility_contract.json"),
            "--defaults",
            str(ROOT / "STANDARD" / "standard_defaults.json"),
            "--channel",
            str(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"),
            "--contract-schema",
            str(ROOT / "STANDARD" / "schemas" / "compatibility_contract.schema.json"),
            "--defaults-schema",
            str(ROOT / "STANDARD" / "schemas" / "standard_defaults.schema.json"),
            "--channel-schema",
            str(ROOT / "STANDARD" / "schemas" / "channel_dna.schema.json"),
            "--output",
            str(output_path),
        )
    )

    assert exit_code == 0
    assert load_json_object(output_path)["compatibility"] == "PASS"
