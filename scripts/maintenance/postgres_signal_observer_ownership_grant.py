#!/usr/bin/env python3
"""Materialize the exact request-bound PostgreSQL observer ownership grant."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.maintenance.postgres_signal_observer_preflight_core import (  # noqa: E402
    materialize_ownership_grant,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ownership-request-receipt", type=Path, required=True)
    parser.add_argument("--granted-owner", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    return parser


def _write_exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("ownership_grant_output_unavailable")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("ownership_grant_output_unavailable")
    temporary = parent / (
        f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    descriptor: int | None = None
    temporary_status: os.stat_result | None = None
    output_linked = False

    def unlink_owned(candidate: Path) -> bool:
        if temporary_status is None:
            return True
        try:
            current = os.lstat(candidate)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if (current.st_dev, current.st_ino) != (
            temporary_status.st_dev,
            temporary_status.st_ino,
        ):
            return False
        try:
            candidate.unlink()
        except OSError:
            return False
        return True

    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
            0o600,
        )
        temporary_status = os.fstat(descriptor)
        if not stat.S_ISREG(temporary_status.st_mode) or (
            stat.S_IMODE(temporary_status.st_mode) != 0o600
        ):
            raise OSError("ownership grant staging identity invalid")
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise OSError("ownership grant write did not progress")
            offset += written
        os.fsync(descriptor)
        final_status = os.fstat(descriptor)
        if (final_status.st_dev, final_status.st_ino) != (
            temporary_status.st_dev,
            temporary_status.st_ino,
        ) or final_status.st_size != len(encoded):
            raise OSError("ownership grant staging readback invalid")
        os.close(descriptor)
        descriptor = None
        os.link(temporary, path, follow_symlinks=False)
        output_linked = True
        linked_status = os.lstat(path)
        if (linked_status.st_dev, linked_status.st_ino) != (
            temporary_status.st_dev,
            temporary_status.st_ino,
        ):
            raise OSError("ownership grant output identity invalid")
        temporary.unlink()
    except OSError as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        cleanup_complete = True
        if output_linked:
            cleanup_complete = unlink_owned(path) and cleanup_complete
        cleanup_complete = unlink_owned(temporary) and cleanup_complete
        failure = (
            "ownership_grant_output_unavailable"
            if cleanup_complete
            else "ownership_grant_output_cleanup_incomplete"
        )
        raise ValueError(failure) from exc


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        grant = materialize_ownership_grant(
            args.ownership_request_receipt,
            granted_owner=args.granted_owner,
        )
        _write_exclusive_json(args.output_json, grant)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(grant, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
