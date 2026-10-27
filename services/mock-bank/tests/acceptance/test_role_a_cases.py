from __future__ import annotations

from pathlib import Path

from mock_bank.acceptance import run_role_a_acceptance
from mock_bank.config import Settings


DIRECT_CASES = {
    "transfer_01",
    "transfer_04",
    "transfer_05",
    "transfer_06",
    "mandate_02",
    "mandate_03",
    "mandate_06",
    "mandate_08",
    "mandate_09",
}


def test_direct_role_a_cases_pass_with_machine_evidence(
    bank_settings: Settings, fixture_root: Path
) -> None:
    catalog = fixture_root.parent / "benchmark" / "acceptance_cases.json"
    report = run_role_a_acceptance(bank_settings, fixture_root, catalog)
    results = {case.case_id: case for case in report.cases}
    assert DIRECT_CASES <= results.keys()
    for case_id in DIRECT_CASES:
        assert results[case_id].status == "PASS"
        assert results[case_id].evidence
        assert results[case_id].owner.startswith("A+")
    assert report.fail_count == 0

