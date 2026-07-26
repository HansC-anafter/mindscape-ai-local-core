"""Discover bounded local dependencies for a workspace HTML report."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import BinaryIO, Iterable
from urllib.parse import unquote, urlsplit

from backend.app.services.tools.reporting.workspace_reporting_paths import (
    contains_symlink,
    is_relative_to,
)


MAX_BUNDLE_FILES = 256
MAX_BUNDLE_SOURCE_BYTES = 128 * 1024 * 1024
_HTML_REFERENCE_ATTRIBUTES = {"href", "src", "poster", "data"}
_CSS_URL_RE = re.compile(
    r"url\(\s*(?P<quote>['\"]?)(?P<value>.*?)"
    r"(?P=quote)\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_CSS_IMPORT_RE = re.compile(
    r"@import\s+(?:url\(\s*)?['\"](?P<value>[^'\"]+)['\"]\s*\)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BundleSourceFile:
    """One regular source file included in a report bundle."""

    path: Path
    sandbox_relative_path: str
    size: int
    sha256: str
    _analysis_file: BinaryIO

    @property
    def analysis_file(self) -> BinaryIO:
        """Return the process-local anonymous snapshot handle."""
        return self._analysis_file

    def read_analysis_text(self) -> str:
        """Decode the bounded anonymous snapshot without a procfs path."""
        self._analysis_file.seek(0)
        content = self._analysis_file.read()
        self._analysis_file.seek(0)
        return content.decode("utf-8", errors="replace")

    def replace_analysis_content(self, content: bytes) -> None:
        """Replace the anonymous snapshot with derived sanitized bytes."""
        self._analysis_file.seek(0)
        self._analysis_file.truncate()
        self._analysis_file.write(content)
        self._analysis_file.flush()
        self._analysis_file.seek(0)

    def close(self) -> None:
        """Close the anonymous analysis snapshot."""
        self._analysis_file.close()


@dataclass(frozen=True)
class ReferenceLedgerEntry:
    """One non-included reference and its source context."""

    source: str
    reference: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        """Serialize the ledger entry."""
        return {
            "source": self.source,
            "reference": self.reference,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class ReportBundleGraph:
    """Bounded source graph used to create a deterministic report bundle."""

    report_path: Path
    source_root: Path
    source_root_relative: str
    files: tuple[BundleSourceFile, ...]
    missing_references: tuple[ReferenceLedgerEntry, ...]
    external_references: tuple[ReferenceLedgerEntry, ...]
    total_uncompressed_bytes: int

    @property
    def source_report_sha256(self) -> str:
        """Return the entry report digest."""
        for source_file in self.files:
            if source_file.path == self.report_path:
                return source_file.sha256
        raise RuntimeError("report file is missing from the bundle graph")

    def archive_path_for(self, source_file: BundleSourceFile) -> str:
        """Return a portable archive path that preserves relative references."""
        relative = source_file.path.relative_to(self.source_root).as_posix()
        return f"report/{relative}"

    @property
    def entrypoint(self) -> str:
        """Return the entry report path inside the archive."""
        relative = self.report_path.relative_to(self.source_root).as_posix()
        return f"report/{relative}"

    def close(self) -> None:
        """Release all bounded anonymous analysis snapshots."""
        for source_file in self.files:
            source_file.close()

    def __enter__(self) -> "ReportBundleGraph":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


class _HtmlReferenceParser(HTMLParser):
    """Collect URL-bearing HTML attributes and inline CSS references."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []
        self._in_style = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() == "style":
            self._in_style = True
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = raw_value or ""
            if not value:
                continue
            if name in _HTML_REFERENCE_ATTRIBUTES:
                self.references.append(value)
            elif name == "srcset":
                self.references.extend(_parse_srcset(value))
            elif name == "style":
                self.references.extend(_parse_css_references(value))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.references.extend(_parse_css_references(data))


def _parse_srcset(value: str) -> list[str]:
    references: list[str] = []
    for candidate in value.split(","):
        normalized = candidate.strip()
        if normalized:
            references.append(normalized.split()[0])
    return references


def _parse_css_references(value: str) -> list[str]:
    references = [
        match.group("value").strip()
        for match in _CSS_URL_RE.finditer(value)
        if match.group("value").strip()
    ]
    references.extend(
        match.group("value").strip()
        for match in _CSS_IMPORT_RE.finditer(value)
        if match.group("value").strip()
    )
    return references


def _read_references(source_file: BundleSourceFile) -> list[str]:
    suffix = source_file.path.suffix.lower()
    if suffix not in {".html", ".htm", ".css"}:
        return []
    text = source_file.read_analysis_text()
    if suffix == ".css":
        return _parse_css_references(text)
    parser = _HtmlReferenceParser()
    parser.feed(text)
    parser.close()
    return parser.references


def _snapshot_and_sha256(path: Path) -> tuple[BinaryIO, str]:
    """Read a source once into a bounded anonymous analysis snapshot."""
    digest = hashlib.sha256()
    snapshot = tempfile.SpooledTemporaryFile(
        max_size=64 * 1024,
        mode="w+b",
    )
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                snapshot.write(chunk)
        snapshot.flush()
        snapshot.seek(0)
        snapshot.fileno()
        return snapshot, digest.hexdigest()
    except BaseException:
        snapshot.close()
        raise


def _classify_reference(reference: str) -> tuple[str, str]:
    normalized = reference.strip()
    if not normalized or normalized.startswith("#"):
        return "ignored", normalized
    parsed = urlsplit(normalized)
    if parsed.scheme or parsed.netloc:
        return "external", normalized
    if parsed.path.startswith("/"):
        return "root_relative", normalized
    local_path = unquote(parsed.path).strip()
    if not local_path:
        return "ignored", normalized
    if "\\" in local_path:
        return "unsupported", normalized
    return "local", local_path


def _dedupe_ledger(
    entries: Iterable[ReferenceLedgerEntry],
) -> tuple[ReferenceLedgerEntry, ...]:
    unique = {
        (entry.source, entry.reference, entry.kind): entry for entry in entries
    }
    return tuple(
        unique[key]
        for key in sorted(unique, key=lambda item: (item[0], item[1], item[2]))
    )


def collect_report_bundle_graph(
    *,
    sandbox_root: Path,
    report_path: Path,
    include_linked_files: bool,
) -> ReportBundleGraph:
    """Collect and hash one bounded report dependency graph."""
    sandbox_root = sandbox_root.resolve()
    report_lexical = Path(os.path.abspath(report_path))
    if contains_symlink(report_lexical, sandbox_root):
        raise ValueError("report_path must not use symlinks")
    report_path = report_lexical.resolve()
    if not is_relative_to(report_path, sandbox_root):
        raise ValueError("report_path must remain under sandbox root")
    if not report_path.is_file():
        raise ValueError("report_path must reference an existing regular file")

    pending = [report_path]
    seen: set[Path] = set()
    source_files: list[BundleSourceFile] = []
    missing: list[ReferenceLedgerEntry] = []
    external: list[ReferenceLedgerEntry] = []
    total_bytes = 0

    while pending:
        source_path = pending.pop(0)
        if source_path in seen:
            continue
        seen.add(source_path)
        if len(seen) > MAX_BUNDLE_FILES:
            raise ValueError(
                f"report bundle exceeds the {MAX_BUNDLE_FILES} file limit"
            )
        if contains_symlink(source_path, sandbox_root):
            raise ValueError("report dependencies must not use symlinks")
        if not source_path.is_file():
            raise ValueError("report dependencies must be regular files")

        size = source_path.stat().st_size
        total_bytes += size
        if total_bytes > MAX_BUNDLE_SOURCE_BYTES:
            raise ValueError(
                "report bundle exceeds the 128 MiB uncompressed source limit"
            )
        source_relative = source_path.relative_to(sandbox_root).as_posix()
        analysis_file, source_sha256 = _snapshot_and_sha256(source_path)
        source_file = BundleSourceFile(
            path=source_path,
            sandbox_relative_path=source_relative,
            size=size,
            sha256=source_sha256,
            _analysis_file=analysis_file,
        )
        source_files.append(source_file)

        if not include_linked_files:
            continue

        for reference in _read_references(source_file):
            kind, normalized = _classify_reference(reference)
            if kind == "ignored":
                continue
            if kind != "local":
                external.append(
                    ReferenceLedgerEntry(
                        source=source_relative,
                        reference=reference,
                        kind=kind,
                    )
                )
                continue

            unresolved = source_path.parent / normalized
            lexical = Path(os.path.abspath(unresolved))
            resolved = unresolved.resolve()
            if not is_relative_to(lexical, sandbox_root) or not is_relative_to(
                resolved,
                sandbox_root,
            ):
                raise ValueError(
                    f"report dependency escapes sandbox: {reference}"
                )
            if contains_symlink(unresolved, sandbox_root):
                raise ValueError(
                    f"report dependency uses a symlink: {reference}"
                )
            if not resolved.exists():
                missing.append(
                    ReferenceLedgerEntry(
                        source=source_relative,
                        reference=reference,
                        kind="missing",
                    )
                )
                continue
            if not resolved.is_file():
                missing.append(
                    ReferenceLedgerEntry(
                        source=source_relative,
                        reference=reference,
                        kind="not_regular_file",
                    )
                )
                continue
            if resolved not in seen and resolved not in pending:
                pending.append(resolved)

    sorted_files = tuple(
        sorted(source_files, key=lambda item: item.sandbox_relative_path)
    )
    source_parents = [str(source_file.path.parent) for source_file in sorted_files]
    source_root = Path(os.path.commonpath(source_parents)).resolve()
    source_root_relative = (
        "."
        if source_root == sandbox_root
        else source_root.relative_to(sandbox_root).as_posix()
    )
    return ReportBundleGraph(
        report_path=report_path,
        source_root=source_root,
        source_root_relative=source_root_relative,
        files=sorted_files,
        missing_references=_dedupe_ledger(missing),
        external_references=_dedupe_ledger(external),
        total_uncompressed_bytes=total_bytes,
    )


__all__ = [
    "MAX_BUNDLE_FILES",
    "MAX_BUNDLE_SOURCE_BYTES",
    "BundleSourceFile",
    "ReferenceLedgerEntry",
    "ReportBundleGraph",
    "collect_report_bundle_graph",
]
