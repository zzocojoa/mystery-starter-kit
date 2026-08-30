"""운영 문서의 Runtime 명령 예시 회귀 검증."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_approval_example_uses_waiting_task_id() -> None:
    """README Runtime 승인 Task ID는 실제 대기 Task와 일치한다."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "mystery-runtime approve RUN-... variation.approve" in readme
    assert "mystery-runtime approve RUN-... variation.generate" not in readme


def test_runtime_human_evidence_flow_is_documented() -> None:
    """README는 Evidence 제출과 동일 Run 재개 명령을 함께 제공한다."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "mystery-kit evidence-submit" in readme
    assert "mystery-runtime submit-input RUN-... reference.build_evidence" in readme
    assert "mystery-runtime resume RUN-..." in readme
    assert "bound_input_hashes" in readme
