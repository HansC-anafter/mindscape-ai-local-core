#!/bin/sh
set -eu

source_path="${1:-}"
wal_file="${2:-}"
archive_dir="${3:-/var/lib/postgresql/wal_archive}"

if [ -z "$source_path" ] || [ -z "$wal_file" ]; then
  echo "usage: mindscape-archive-wal <source-path> <wal-file> [archive-dir]" >&2
  exit 2
fi

case "$wal_file" in
  "" | */*)
    echo "invalid WAL archive filename: $wal_file" >&2
    exit 2
    ;;
esac

if ! printf '%s\n' "$wal_file" | grep -Eq '^([0-9A-F]{24}|[0-9A-F]{8}\.history)$'; then
  echo "invalid WAL archive filename: $wal_file" >&2
  exit 2
fi

if [ ! -f "$source_path" ]; then
  echo "WAL source does not exist: $source_path" >&2
  exit 1
fi

if [ ! -d "$archive_dir" ]; then
  echo "WAL archive directory does not exist: $archive_dir" >&2
  exit 1
fi

destination="$archive_dir/$wal_file"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
tmp_path="$archive_dir/.tmp-$wal_file-$$-$timestamp"
corrupt_path="$archive_dir/.corrupt-$wal_file-$timestamp-$$"

cleanup() {
  rm -f "$tmp_path"
}
trap cleanup EXIT HUP INT TERM

if [ -f "$destination" ]; then
  if cmp -s "$source_path" "$destination"; then
    exit 0
  fi
  mv "$destination" "$corrupt_path"
fi

cp "$source_path" "$tmp_path"
chmod 0600 "$tmp_path"

if ! cmp -s "$source_path" "$tmp_path"; then
  echo "WAL archive copy verification failed for $wal_file" >&2
  exit 1
fi

mv "$tmp_path" "$destination"
trap - EXIT HUP INT TERM
exit 0
