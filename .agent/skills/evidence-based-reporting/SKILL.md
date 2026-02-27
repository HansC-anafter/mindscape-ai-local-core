---
name: evidence-based-reporting
description: Enforce evidence-first discipline in all reports, plans, and diagnostic documents. No unverified claims.
---

# Evidence-Based Reporting

## Core Rule

**Every factual claim in a report, plan, or diagnostic document MUST have a corresponding evidence source collected BEFORE the claim is written.**

Violation of this rule produces garbage reports that waste the user's time and destroy trust.

---

## What Counts as Evidence

| Claim Type | Required Evidence | NOT Acceptable |
|---|---|---|
| Runtime state (process running, port open, env var value) | `ps aux`, `docker inspect`, `env`, `curl` output | Reading source code and guessing what runs |
| Database content (row exists, column value) | `psql` / API query result | Inferring from code that writes to the table |
| Configuration (which file sets a value) | `grep` the actual file + confirm via `docker inspect` or process cmdline | Seeing one config file and assuming it's the only one |
| Code behavior (function does X) | Direct code citation with file path and line number | Paraphrasing from memory |
| Log evidence (event happened at time T) | `docker compose logs` grep output | "It probably logged something" |
| Connection state (WS connected, API reachable) | `curl` / `ps aux` / backend log grep | UI screenshot alone (could be cached/stale) |
| Network identity (IP belongs to X) | `host <IP>` or `nslookup` reverse DNS output | Guessing from IP range ownership |

---

## Prohibited Patterns

### 1. Inference-as-Fact

**WRONG**: "The function falls back to the first workspace because the resolver has a fallback path."

This reads code logic and assumes runtime behavior. The actual DB table was never queried.

**RIGHT**: Query the table first, then write the claim with evidence inline.

### 2. Single-Source Assumption

**WRONG**: "Setting X is configured in Dockerfile."

Only one config file was checked. Docker Compose merges multiple layers (Dockerfile, docker-compose.yml, overrides, .env). The actual process CMD was never verified.

**RIGHT**: Run `docker inspect <container> | jq '.[0].Config.Cmd'` to see the actual CMD, then trace back to the source file.

### 3. Negation Without Verification

**WRONG**: "Process X is not running" (without running `pgrep` or `ps aux`)

**RIGHT**: Run `ps aux | grep <process>`, paste the output (even if empty), then write the claim.

### 4. IP-as-Identity

**WRONG**: "Client connects from `<IP>` which belongs to `<cloud provider>`, therefore it's a cloud-hosted service."

Seeing an IP in a log and inferring the identity of the client based on IP range ownership. The IP could be a CDN, a reverse proxy, a tunnel endpoint, or anything else.

**RIGHT**: Run `host <IP>` to get reverse DNS, AND `ps aux | grep <relevant_process>` on all candidate machines to find where the process actually runs. Only then identify the client.

### 5. Wrong Execution Host (Container vs Host)

**WRONG**: "Env var `X` is not set in the container, so the subprocess can't reach the backend."

Investigated the Docker container's env vars and network, but the actual process runs on the HOST machine. Never ran `ps aux` on the host to verify where the process executes.

**RIGHT**: Before investigating ANY container internals, first determine WHERE the process runs:

```
# ALWAYS run on the HOST first
ps aux | grep <process_name>
# If found on host: investigate the host environment
# If NOT found on host: THEN check containers
```

### 6. Data Misinterpretation Without Code Verification

**WRONG**: "Field `X` is empty in the DB, so runtime event Y did not happen."

Interpreted a DB field value without first checking the code that writes it. The writer function may never populate that field — the empty value could be a default added downstream by a different layer.

**RIGHT**: Before interpreting any DB field value as evidence, trace the code path that writes it:

1. Find the function that populates the field (file path + line number)
2. Verify whether the field reflects actual runtime behavior or is a default/stub
3. Only then interpret the value

### 7. Premature Root Cause Declaration

**WRONG**: "Root cause: env var `X` defaults to wrong value. Fix: set it in the container."

Declared root cause after checking ONE config layer (container env vars) without checking other layers (settings files, process environment, CLI flags) that may already set the correct value. Also did not verify that the claimed cause actually produces the observed symptom.

**RIGHT**: A root cause declaration requires:

1. Full config layer search (env vars + settings files + process cmdline + Docker config)
2. Verification that the claimed cause actually produces the observed symptom
3. Evidence that fixing the cause would change the outcome

### 8. Incomplete Execution Path Trace

**WRONG**: Investigated container internals → container networking → container env vars. Concluded a subprocess can't reach a service from inside Docker.

The actual execution path ran entirely on the host machine — Docker was never in the execution path. The subprocess chain (client → executor → bridge → CLI → MCP server) all ran on the host.

**RIGHT**: Before investigating any specific hop, trace the FULL execution path first:

```
FOR a task execution investigation:
  1. ps aux | grep <process> on HOST — find where execution starts
  2. Read the process's env vars (ps eww -p <PID>)
  3. Read the code that spawns the next subprocess — find the command + env
  4. For each subprocess in the chain, verify: what binary, what cwd, what env, what config files
  5. Only investigate network/connectivity AFTER you know which machine the process runs on
```

---

## Mandatory Workflow

When writing any report, plan, or investigation document:

```
FOR EACH factual claim you are about to write:
  1. STOP writing
  2. Run the verification command (DB query, grep, ps, curl, docker inspect, etc.)
  3. Read the output
  4. Write the claim WITH the evidence inline or as a citation
  5. If the evidence contradicts your expectation, UPDATE your understanding — do NOT ignore it
```

### Execution Path Investigation Order

When investigating "why does X not work at runtime":

```
1. LOCATE the process: ps aux | grep <name> on HOST first, then containers
2. READ its env: ps eww -p <PID> | grep <VAR> (or /proc/<PID>/environ on Linux)
3. READ its config files: find the settings file the process actually reads
4. TEST connectivity FROM the correct machine: curl from where the process runs
5. ONLY THEN form a hypothesis and verify it
```

**NEVER skip step 1.** Investigating the wrong machine wastes all subsequent effort.

### Evidence Citation Format

Use one of these formats in the document:

**Inline evidence block**:

```
> **Evidence**: `<command that was run>`
> ```
> <actual output pasted here>
> ```
```

**Code citation**:

```
> **Evidence**: [filename.py:L120-L129](file:///path/to/file#L120-L129)
> ```python
> def relevant_function(...):
>     ...
> ```
```

---

## Pre-Commit Checklist for Reports

Before delivering any report or plan to the user, verify:

- [ ] Every "X is running / not running" claim has a `ps aux` or `pgrep` output
- [ ] Every "X is configured as Y" claim has the actual config file AND the runtime verification (`docker inspect`, env dump, process cmdline)
- [ ] Every database state claim has a query result
- [ ] Every "code does X" claim has a file path and line number
- [ ] Every log-based claim has the actual log lines pasted
- [ ] No claim is derived purely from reading code and inferring runtime behavior
- [ ] If multiple config layers exist (Dockerfile, docker-compose, overrides, .env, app settings files), ALL layers have been checked for the setting in question
- [ ] The execution host (HOST vs container) has been verified via `ps aux` BEFORE investigating env/config/network
- [ ] IP addresses in logs have been reverse-DNS verified before attributing them to any identity
- [ ] DB field values have been traced to the code that writes them before being interpreted as evidence

---

## Fix Verification Checklist

After applying a fix, verify at EVERY layer in the execution path, not just the layer you changed:

```
FOR a fix that changes tool/service availability:
  1. UNIT: The function you changed now returns the expected output
     → Run the function directly in the same import context as production
  2. API: The API endpoint returns the corrected response
     → curl/POST the endpoint and confirm the change is reflected
  3. CONSUMER: The consumer of the API (e.g., MCP gateway, CLI) receives the corrected data
     → Check the consumer's tool list or config
  4. END-TO-END: The original symptom is resolved
     → Trigger the same user-facing action that was failing
```

**Do NOT declare a fix verified after checking only one layer.** A fix at the function level may not propagate if there is caching, a stale process, or a different code path at the API layer.

### Common Verification Gaps

| Fixed Layer | Often Missed |
|---|---|
| Python function | API serves from a different worker with stale imports |
| Backend API | MCP gateway caches tool list from previous startup |
| Config file | Process needs restart to pick up new config |
| Docker image | Container uses mounted volume that overrides the image |

---

## Why This Exists

This skill was created after reports contained multiple unverified claims that wasted the user's time and destroyed trust.

### Incident 1 (2026-02-17)

Three errors from a single diagnostic report:

1. Claimed no DB records existed — wrong, table had active rows (never queried)
2. Claimed a setting was in one config file — wrong, it was in a different override file (only one layer checked)
3. Claimed a process was not running — wrong, a different process was already handling the same role (never ran `ps aux`)

Root cause: **writing conclusions before collecting evidence**.

### Incident 2 (2026-02-22)

Five errors from a tool availability investigation:

1. Attributed a log IP to a specific infrastructure role — wrong, it was a CDN/proxy (never ran `host` or `nslookup`)
2. Investigated env vars inside a Docker container — wrong, the process runs on the host (never ran `ps aux` on host)
3. Interpreted an empty DB field as "event didn't happen" — wrong, the writer function never populates that field (code not checked before interpreting data)
4. Declared root cause after checking one config layer — wrong, a different config layer already had the correct value (incomplete layer search)
5. Reached a correct conclusion about process location by accident — wasted time investigating the wrong machine before checking the host

Root cause: **investigating the wrong machine because `ps aux` on the host was never run first**.
