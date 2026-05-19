"""Execution result helpers for special pack executors."""

from typing import Any, Dict, List


def build_execution_result(
    *,
    extracted_intents: List[str],
    files: List[str],
    file_contents: List[str],
) -> Dict[str, Any]:
    del file_contents
    if files:
        title = f"Extracted {len(extracted_intents)} intents from {len(files)} file(s)"
        summary = (
            f"Found {len(extracted_intents)} potential intents or projects from files"
        )
        result_message = f"Extracted {len(extracted_intents)} intents from uploaded files"
    else:
        title = f"Extracted {len(extracted_intents)} intents from message"
        summary = (
            f"Found {len(extracted_intents)} potential intents or projects from message"
        )
        result_message = f"Extracted {len(extracted_intents)} intents from message"

    return {
        "title": title,
        "summary": summary,
        "message": result_message,
        "intents": extracted_intents[:5],
        "files_processed": len(files),
        "source": "files" if files else "message",
    }
