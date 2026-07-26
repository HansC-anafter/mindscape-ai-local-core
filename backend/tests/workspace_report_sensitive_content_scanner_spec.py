import hashlib

import pytest

from backend.app.services.artifact_disclosure.policy_profile import (
    load_share_policy_profile,
)
from backend.app.services.artifact_disclosure.scanner import (
    scan_item_content,
)


def _scan(path, *, media_type="text/plain"):
    content = path.read_bytes()
    return scan_item_content(
        source_path=path,
        source_sha256=hashlib.sha256(content).hexdigest(),
        source_bytes=len(content),
        media_type=media_type,
        declared_classification=None,
        profile=load_share_policy_profile(),
    )


def test_sensitive_value_across_one_mib_boundary_is_redacted(tmp_path):
    path = tmp_path / "boundary.txt"
    path.write_bytes(
        b"x" * (1024 * 1024 - 7)
        + b" person@example.com"
        + b"\n"
    )

    result = _scan(path)

    assert result.classification == "confidential"
    assert result.findings[0].code == "email_address"
    assert b"person@example.com" not in result.transformed_content
    assert b"[REDACTED:EMAIL]" in result.transformed_content


def test_no_finding_stays_internal_and_active_content_is_bounded(
    tmp_path,
):
    plain = tmp_path / "plain.txt"
    plain.write_text("ordinary report evidence", encoding="utf-8")
    active = tmp_path / "active.html"
    active.write_text(
        "<script>synthetic()</script>",
        encoding="utf-8",
    )

    plain_result = _scan(plain)
    active_result = _scan(active, media_type="text/html")

    assert plain_result.classification == "internal"
    assert plain_result.findings == ()
    assert active_result.classification == "internal"
    assert [(item.code, item.count) for item in active_result.findings] == [
        ("active_content", 1)
    ]
    assert active_result.external_review_required is True


def test_malformed_text_and_binary_fail_to_unknown_not_public(tmp_path):
    malformed = tmp_path / "malformed.txt"
    malformed.write_bytes(b"\xff\xfe\x00")
    binary = tmp_path / "fixture.png"
    binary.write_bytes(b"\x89PNG\r\nsynthetic")

    malformed_result = _scan(malformed)
    binary_result = _scan(binary, media_type="image/png")

    assert malformed_result.classification == "unknown_binary"
    assert malformed_result.findings[0].code == "text_decode_failed"
    assert binary_result.classification == "unknown_binary"
    assert binary_result.findings[0].code == (
        "content_not_text_scanned"
    )


@pytest.mark.parametrize(
    ("value", "expected_code"),
    [
        ("-----BEGIN " + "PRIVATE " + "KEY-----", "private_key"),
        ("Bearer abcdefghijklmnop", "bearer_token"),
        ("eyJabcdefgh.abcdefgh.abcdefgh", "jwt"),
        ("api_key = abcdefghijklmnop", "api_secret"),
        ("4111 1111 1111 1111", "payment_card"),
        ("person@example.com", "email_address"),
        ("+1 (415) 555-2671", "phone_number"),
        ("192.168.1.1", "ip_address"),
        ("<script>synthetic()</script>", "active_content"),
    ],
)
def test_policy_scan_guard_preserves_every_detector(
    tmp_path,
    value,
    expected_code,
):
    path = tmp_path / "detector.txt"
    path.write_text(value, encoding="utf-8")

    result = _scan(path)

    assert expected_code in {
        finding.code for finding in result.findings
    }
