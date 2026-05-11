# Pull Request

## Scope Summary

Describe the purpose of this change and the Local Core surface it affects.

## Local Core Boundary Check

- [ ] This change stays within the Local Core repository boundary.
- [ ] This change does not add cloud tenant, billing, provider control-plane, or managed remote execution service logic to Local Core.
- [ ] This change does not publish capability-internal service implementation details as Local Core architecture.
- [ ] This change does not add provider-native credentials, private payloads, generated runtime artifacts, or local data to tracked source.
- [ ] This change does not modify ignored or CI-protected runtime output paths.

## Sensitive Path Check

If this PR changes any of these paths, explain why the change belongs in Local Core:

- `backend/app/capabilities/**`
- `backend/playbooks/specs/**`
- `web-console/src/app/capabilities/**`
- `backend/app/routes/core/**`
- `mcp-mindscape-gateway/**`
- `device-node/**`
- `monitoring/**`
- `ocr-service/**`
- `scripts/**`

## Change Type

- [ ] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] Documentation
- [ ] Test
- [ ] Build or tooling
- [ ] Boundary or guardrail change

## Modular Entry Check

- [ ] This change opens or confirms a modular entrypoint before behavior changes in inherited, large, or boundary-crossing code.
- [ ] Legacy entrypoint is reduced to a thin wrapper where applicable.
- [ ] Leaf-only exception claimed

Exception justification:

Changed files:

Why leaf-only:

Why no new boundary:

Why future refactor cost does not increase:

## Validation

List the commands, checks, or manual validation performed for this change.

## Documentation

- [ ] Public documentation is English-only and contains no private paths, work logs, validation captures, or unreleased API references.
- [ ] Internal implementation notes, if any, are stored under internal documentation paths.
- [ ] Relative links in public Markdown were checked.

## Notes

Add reviewer context, risks, or follow-up work here.
