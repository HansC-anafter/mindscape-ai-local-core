"""Helpers for filtering non-runtime capability/pack directories."""


def is_ignored_runtime_pack_dir(dir_name: str) -> bool:
    return (
        dir_name.startswith("_")
        or dir_name.startswith(".")
        or ".__bak" in dir_name
        or ".bak" in dir_name
    )
