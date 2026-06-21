import json
import os
import subprocess
import sys
import time

from .auth import (
    _extract_auth_scope,
    _fetch_agent_context,
    _fetch_auth_env,
    _report_quota_exhausted,
)
from .config import (
    GEMINI_CLI,
    GEMINI_CLI_MODEL,
    MAX_OUTPUT,
    set_bridge_backend_url,
)
from .filesystem import (
    _diff_file_snapshots,
    _resolve_host_sandbox_path,
    _snapshot_files,
)
from .output import emit_result, log
from .response import (
    _extract_response,
    _looks_like_auth_error,
    _looks_like_quota_error,
)


def main() -> None:
    """Run one Gemini CLI runtime bridge dispatch."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        emit_result("failed", error=f"Invalid JSON payload: {e}")
        return

    task = payload.get("task", "")
    execution_id = payload.get("execution_id", "unknown")
    workspace_id = payload.get("workspace_id", "")
    max_duration = payload.get("max_duration", 600)
    context = payload.get("context", {})
    auth_workspace_id = context.get("auth_workspace_id", "") or ""
    source_workspace_id = context.get("source_workspace_id", "") or ""
    sandbox_path = context.get("sandbox_path", "")

    set_bridge_backend_url(payload.get("backend_api_url", ""))

    if not task:
        emit_result("failed", error="Empty task")
        return

    agent_ctx = _fetch_agent_context()
    instruction_parts = []
    if agent_ctx.get("role"):
        instruction_parts.append(agent_ctx["role"])
    if agent_ctx.get("data_guidance"):
        instruction_parts.append(f"\nIMPORTANT: {agent_ctx['data_guidance']}")
    tables = agent_ctx.get("tables", [])
    table_schemas = agent_ctx.get("table_schemas", {})
    if table_schemas:
        schema_lines = []
        for tname in sorted(table_schemas.keys()):
            cols = table_schemas[tname]
            schema_lines.append(f"- {tname}: {', '.join(cols)}")
        instruction_parts.append(
            f"\nAvailable database tables and columns:\n" + "\n".join(schema_lines)
        )
    elif tables:
        table_lines = "\n".join(f"- {t}" for t in tables)
        instruction_parts.append(f"\nAvailable database tables:\n{table_lines}")

    pack_guides = agent_ctx.get("installed_pack_guides", [])
    if pack_guides:
        guide_lines = ["\n## Installed Capability Pack Guides"]
        for pg in pack_guides:
            guide_lines.append(
                f"### {pg.get('display_name', '')} ({pg.get('pack_code', '')})\n"
                f"{pg.get('guide', '')}"
            )
        instruction_parts.append("\n".join(guide_lines))

    system_instruction = "\n".join(instruction_parts) if instruction_parts else ""
    conversation_context = context.get("conversation_context", "")

    uploaded_files = context.get("uploaded_files") or []
    uploaded_files_section = ""
    resolved_file_paths = []
    if uploaded_files:
        workspace_root = os.environ.get("MINDSCAPE_WORKSPACE_ROOT", "")
        print(
            f"[FileResolve] workspace_root={workspace_root}, uploaded_files={uploaded_files}",
            file=sys.stderr,
        )
        file_lines = []
        for f in uploaded_files:
            if isinstance(f, str):
                file_lines.append(f"- {f}")
                continue
            if not isinstance(f, dict):
                continue

            name = f.get("file_name", f.get("filename", f.get("file_id", "unknown")))
            ftype = f.get("file_type", f.get("mime_type", "unknown"))
            fpath = f.get("file_path", "")
            size = f.get("file_size", f.get("size_bytes", "?"))

            host_path = ""
            if fpath and workspace_root:
                rel = fpath
                if rel.startswith("/app/"):
                    rel = rel[5:]
                candidate = os.path.join(workspace_root, rel)
                if os.path.isfile(candidate):
                    host_path = candidate
                    file_stat = os.stat(candidate)
                    size = file_stat.st_size

            line = f"- {name} (type: {ftype}, size: {size})"
            if host_path:
                line += f"\n  Host path: {host_path}"
                if os.path.getsize(host_path) > 100:
                    resolved_file_paths.append(host_path)
            elif fpath:
                line += f"\n  Container path: {fpath} (not accessible from host)"
            file_lines.append(line)

        if file_lines:
            uploaded_files_section = "\n## Uploaded Files\n" + "\n".join(file_lines)
            if resolved_file_paths:
                uploaded_files_section += (
                    "\n\nYou can access these files directly at the host paths listed above."
                )

    prompt_parts = []
    if system_instruction:
        prompt_parts.append(system_instruction)
    if conversation_context:
        prompt_parts.append(f"\n## Conversation Context\n{conversation_context}")
    if uploaded_files_section:
        prompt_parts.append(uploaded_files_section)
    prompt_parts.append(task)

    prompt_parts.append(
        "\n\nIMPORTANT: After using any tools, you MUST provide a final "
        "text summary of your findings. Never end your response with "
        "only tool calls and no text output."
    )

    prompt_parts.append(
        f"\n\n[System Context] execution_id={execution_id}, "
        f"workspace_id={workspace_id}"
    )

    prompt = "\n".join(prompt_parts)

    workspace_root = os.environ.get("MINDSCAPE_WORKSPACE_ROOT", "")
    resolved_sandbox_path = _resolve_host_sandbox_path(sandbox_path, workspace_root)
    if resolved_sandbox_path:
        log(f"Resolved sandbox path {sandbox_path} -> {resolved_sandbox_path}")

    cwd = resolved_sandbox_path or os.getcwd()

    auth_env, api_model, selected_runtime_id, auth_trace = _fetch_auth_env(
        workspace_id=workspace_id,
        auth_workspace_id=auth_workspace_id,
        source_workspace_id=source_workspace_id,
    )

    effective_model = payload.get("model") or api_model or GEMINI_CLI_MODEL

    cmd = [
        GEMINI_CLI,
        "--model",
        effective_model,
        "--yolo",
        "-p",
        prompt,
        "-o",
        "json",
    ]

    log(f"Executing: {' '.join(cmd[:5])}... (model={effective_model}, cwd={cwd})")

    sub_env = {**os.environ, "GEMINI_CLI_EXECUTION_ID": execution_id}
    sub_env.update(auth_env)

    file_hint = context.get("file_hint", "")
    if file_hint:
        sub_env["MINDSCAPE_TASK_HINT"] = f"{task} {file_hint}"[:500]
    else:
        hint_parts = [task]
        for f in context.get("uploaded_files") or []:
            if isinstance(f, dict):
                fname = f.get("file_name", "")
                ftype = f.get("detected_type") or f.get("file_type", "")
                if fname:
                    hint_parts.append(f"[{ftype}: {fname}]")
        sub_env["MINDSCAPE_TASK_HINT"] = " ".join(hint_parts)[:500]

    rec_packs = context.get("recommended_pack_codes", [])
    if rec_packs:
        sub_env["MINDSCAPE_RECOMMENDED_PACKS"] = json.dumps(rec_packs)

    start = time.monotonic()
    before_files = _snapshot_files(cwd) if resolved_sandbox_path else {}
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=max_duration,
            env=sub_env,
        )

        duration = time.monotonic() - start
        after_files = _snapshot_files(cwd) if resolved_sandbox_path else {}
        files_created, files_modified = _diff_file_snapshots(
            before_files,
            after_files,
        )
        raw_stdout = (result.stdout or "")[:MAX_OUTPUT].strip()
        stdout, json_error = _extract_response(raw_stdout)
        stderr = (result.stderr or "")[:MAX_OUTPUT].strip()

        auth_in_stderr = _looks_like_auth_error(stderr)
        auth_in_json = _looks_like_auth_error(json_error or "")
        quota_in_stderr = _looks_like_quota_error(stderr)
        quota_in_json = _looks_like_quota_error(json_error or "")
        is_retriable = (
            auth_in_stderr or auth_in_json or quota_in_stderr or quota_in_json
        )
        if result.returncode != 0 and is_retriable:
            is_quota = quota_in_stderr or quota_in_json
            error_kind = "quota" if is_quota else "auth"
            log(f"{error_kind} error detected, retrying with fresh auth env")
            if is_quota:
                _report_quota_exhausted(selected_runtime_id)
            fresh_env, _, selected_runtime_id, auth_trace = _fetch_auth_env(
                workspace_id=workspace_id,
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
            )
            if fresh_env:
                sub_env.update(fresh_env)
                remaining = max_duration - duration
                if remaining > 10:
                    result = subprocess.run(
                        cmd,
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        timeout=int(remaining),
                        env=sub_env,
                    )
                    after_files = _snapshot_files(cwd) if resolved_sandbox_path else {}
                    files_created, files_modified = _diff_file_snapshots(
                        before_files,
                        after_files,
                    )
                    raw_stdout = (result.stdout or "")[:MAX_OUTPUT].strip()
                    stdout, json_error = _extract_response(raw_stdout)
                    stderr = (result.stderr or "")[:MAX_OUTPUT].strip()

        final_quota = _looks_like_quota_error(
            (result.stderr or "") + (json_error or "")
        )
        if result.returncode != 0 and final_quota:
            _report_quota_exhausted(selected_runtime_id)

        if result.returncode == 0:
            if json_error:
                emit_result(
                    "completed",
                    output=stdout or json_error,
                    runtime_id=selected_runtime_id,
                    auth_scope=_extract_auth_scope(auth_trace),
                    files_modified=files_modified,
                    files_created=files_created,
                )
            else:
                if not stdout:
                    log(
                        f"WARNING: empty response from CLI. raw_stdout={raw_stdout[:500]}"
                    )
                output = stdout or "(no response from agent)"
                emit_result(
                    "completed",
                    output=output,
                    runtime_id=selected_runtime_id,
                    auth_scope=_extract_auth_scope(auth_trace),
                    files_modified=files_modified,
                    files_created=files_created,
                )
        else:
            error_parts = []
            if json_error:
                error_parts.append(json_error)
            if stderr:
                error_parts.append(stderr[:500])
            error_msg = (
                " | ".join(error_parts)
                if error_parts
                else f"Exit code {result.returncode}"
            )
            emit_result(
                "failed",
                output=stdout,
                error=f"Exit code {result.returncode}: {error_msg}",
                runtime_id=selected_runtime_id,
                auth_scope=_extract_auth_scope(auth_trace),
                files_modified=files_modified,
                files_created=files_created,
            )

    except subprocess.TimeoutExpired:
        emit_result("timeout", error=f"Timed out after {max_duration}s")
    except FileNotFoundError:
        emit_result(
            "failed",
            error=f"Gemini CLI not found at {GEMINI_CLI}",
        )
    except Exception as e:
        emit_result("failed", error=str(e))
