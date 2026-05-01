#!/usr/bin/env python3
"""Verify installed capability-page render proof with a headless browser."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


FORBIDDEN_PAGE_TEXT = (
    "No UI components available",
    "Component failed to render",
    "Capability 未找到",
)

FORBIDDEN_CONSOLE_SUBSTRINGS = (
    "Context key not found in bundle",
    "UI components not available",
    "Failed to import UI component",
    "Error in component",
    "Suspicious component paths from API",
)


def _fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _ensure_capability_installed(api_base_url: str, capability_code: str) -> dict[str, Any]:
    installed = _fetch_json(
        f"{api_base_url.rstrip('/')}/api/v1/capability-packs/installed-capabilities"
    )
    for entry in installed:
        if entry.get("code") == capability_code or entry.get("id") == capability_code:
            return entry
    raise RuntimeError(f"Capability '{capability_code}' is not installed")


def _load_ui_components(api_base_url: str, capability_code: str) -> list[dict[str, Any]]:
    components = _fetch_json(
        f"{api_base_url.rstrip('/')}/api/v1/capability-packs/installed-capabilities/"
        f"{urllib.parse.quote(capability_code, safe='')}/ui-components"
    )
    if not isinstance(components, list) or not components:
        raise RuntimeError(f"Capability '{capability_code}' returned no ui_components metadata")
    return components


def _iter_matching_console_messages(messages: Iterable[str]) -> list[str]:
    matched: list[str] = []
    for message in messages:
        if any(fragment in message for fragment in FORBIDDEN_CONSOLE_SUBSTRINGS):
            matched.append(message)
    return matched


def _extract_session_id_from_url(current_url: str) -> str | None:
    parsed = urllib.parse.urlparse(current_url)
    params = urllib.parse.parse_qs(parsed.query)
    session_ids = params.get("session_id") or []
    if not session_ids:
        return None
    session_id = str(session_ids[0] or "").strip()
    return session_id or None


def _session_has_expected_attachment(
    session_payload: dict[str, Any],
    *,
    owner_pack: str | None,
    object_kind: str | None,
    object_id: str | None,
    object_id_substring: str | None,
) -> bool:
    metadata = session_payload.get("metadata") or {}
    aol_metadata = metadata.get("addressable_object_layer") or {}
    context_entries = aol_metadata.get("context_entries") or []
    if not isinstance(context_entries, list):
        return False

    for entry in context_entries:
        if not isinstance(entry, dict):
            continue
        ref = entry.get("ref") or {}
        if not isinstance(ref, dict):
            continue
        if owner_pack and str(ref.get("owner_pack") or "").strip() != owner_pack:
            continue
        if object_kind and str(ref.get("object_kind") or "").strip() != object_kind:
            continue
        ref_object_id = str(ref.get("object_id") or "").strip()
        if object_id and ref_object_id != object_id:
            continue
        if object_id_substring and object_id_substring not in ref_object_id:
            continue
        return True
    return False


def _wait_for_panel_mode(page: Any, panel_testid: str, expected_mode: str, timeout_ms: int) -> None:
    page.wait_for_function(
        """
        ([panelTestId, expectedMode]) => {
          const panel = document.querySelector(`[data-testid="${panelTestId}"]`);
          return Boolean(panel) && panel.getAttribute('data-aol-mode') === expectedMode;
        }
        """,
        arg=[panel_testid, expected_mode],
        timeout=timeout_ms,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that an installed capability page resolves metadata, loads its component, "
            "renders without fallback UI, and optionally exercises the AOL host bridge."
        )
    )
    parser.add_argument("--api-base-url", default="http://localhost:8220")
    parser.add_argument("--web-base-url", default="http://localhost:3000")
    parser.add_argument(
        "--browser-executable",
        help=(
            "Optional browser executable path. Use when Playwright browser bundles are absent "
            "but the runtime provides a system Chromium/Chrome binary."
        ),
    )
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--capability-code", required=True)
    parser.add_argument("--component-code")
    parser.add_argument(
        "--page-url",
        help=(
            "Optional full page URL override. Use for installed capability surfaces that resolve "
            "through a nested session/run route instead of the capability root page."
        ),
    )
    parser.add_argument(
        "--expected-text",
        action="append",
        default=[],
        help="Text that must be visible on the capability page after render.",
    )
    parser.add_argument(
        "--expected-selector",
        action="append",
        default=[],
        help="CSS selector that must resolve before AOL interaction begins.",
    )
    parser.add_argument(
        "--anchor-testid",
        default="aol-global-anchor",
        help="Test id for the shared AOL global anchor.",
    )
    parser.add_argument(
        "--click-anchor-first",
        action="store_true",
        help="Click the shared AOL anchor before the page object trigger.",
    )
    parser.add_argument(
        "--expected-after-anchor-text",
        action="append",
        default=[],
        help="Text that must be visible after clicking the shared AOL anchor.",
    )
    parser.add_argument(
        "--preclick-text",
        help="Optional button label to click before the AOL host-bridge smoke.",
    )
    parser.add_argument(
        "--preclick-text-substring",
        help="Optional button label substring to click before the AOL host-bridge smoke.",
    )
    parser.add_argument(
        "--preclick-visible-text",
        help="Optional visible text to click before the AOL host-bridge smoke.",
    )
    parser.add_argument(
        "--preclick-visible-text-substring",
        help="Optional visible text substring to click before the AOL host-bridge smoke.",
    )
    parser.add_argument(
        "--preclick-selector",
        help="Optional CSS selector to click before the AOL host-bridge smoke.",
    )
    parser.add_argument(
        "--trigger-text",
        help="Optional button label to click for AOL host-bridge smoke.",
    )
    parser.add_argument(
        "--trigger-text-substring",
        help="Optional button label substring to click for AOL host-bridge smoke.",
    )
    parser.add_argument(
        "--trigger-selector",
        help="Optional CSS selector to click for AOL host-bridge smoke.",
    )
    parser.add_argument(
        "--expected-panel-text",
        action="append",
        default=[],
        help="Text expected after clicking the trigger button.",
    )
    parser.add_argument(
        "--panel-action-text",
        help="Optional panel action label to click after the AOL panel is visible.",
    )
    parser.add_argument(
        "--panel-action-text-substring",
        help="Optional panel action label substring to click after the AOL panel is visible.",
    )
    parser.add_argument(
        "--expected-url-substring",
        action="append",
        default=[],
        help="URL substring(s) that must be present after the optional panel action.",
    )
    parser.add_argument("--panel-testid", default="aol-host-panel")
    parser.add_argument(
        "--expected-panel-count",
        type=int,
        help="Optional exact count expected for the shared AOL panel after selection.",
    )
    parser.add_argument(
        "--expected-panel-mode",
        help="Optional data-aol-mode expected on the shared AOL panel after selection.",
    )
    parser.add_argument(
        "--expected-panel-mode-after-action",
        help="Optional data-aol-mode expected on the shared AOL panel after the panel action and route transition.",
    )
    parser.add_argument(
        "--verify-session-attachment-owner-pack",
        help="Optional owner_pack expected in meeting_session.metadata.addressable_object_layer.context_entries.",
    )
    parser.add_argument(
        "--verify-session-attachment-object-kind",
        help="Optional object_kind expected in meeting_session.metadata.addressable_object_layer.context_entries.",
    )
    parser.add_argument(
        "--verify-session-attachment-object-id",
        help="Optional exact object_id expected in meeting_session.metadata.addressable_object_layer.context_entries.",
    )
    parser.add_argument(
        "--verify-session-attachment-object-id-substring",
        help="Optional object_id substring expected in meeting_session.metadata.addressable_object_layer.context_entries.",
    )
    parser.add_argument("--timeout-ms", type=int, default=20000)
    args = parser.parse_args(argv)

    try:
        installed_entry = _ensure_capability_installed(args.api_base_url, args.capability_code)
        components = _load_ui_components(args.api_base_url, args.capability_code)
    except urllib.error.URLError as exc:
        print(f"FAILED: capability metadata probe failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    if args.component_code:
        if not any(component.get("code") == args.component_code for component in components):
            print(
                f"FAILED: component '{args.component_code}' not found in ui_components metadata",
                file=sys.stderr,
            )
            return 1

    if args.page_url:
        page_url = args.page_url
    else:
        page_url = (
            f"{args.web_base_url.rstrip('/')}/workspaces/"
            f"{urllib.parse.quote(args.workspace_id, safe='')}/capabilities/"
            f"{urllib.parse.quote(args.capability_code, safe='')}"
        )
        if args.component_code:
            page_url = f"{page_url}?component={urllib.parse.quote(args.component_code, safe='')}"

    console_messages: list[str] = []
    page_errors: list[str] = []
    current_url = page_url

    try:
        with sync_playwright() as playwright:
            launch_kwargs: dict[str, Any] = {"headless": True}
            if args.browser_executable:
                launch_kwargs["executable_path"] = args.browser_executable
            browser = playwright.chromium.launch(**launch_kwargs)
            page = browser.new_page()
            page.on(
                "console",
                lambda message: console_messages.append(f"{message.type}: {message.text}"),
            )
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            page.goto(page_url, wait_until="domcontentloaded", timeout=args.timeout_ms)

            for forbidden_text in FORBIDDEN_PAGE_TEXT:
                if page.get_by_text(forbidden_text).count() > 0:
                    raise RuntimeError(f"Forbidden fallback text rendered: {forbidden_text}")

            for expected_text in args.expected_text:
                page.get_by_text(expected_text, exact=False).first.wait_for(
                    state="visible", timeout=args.timeout_ms
                )

            for expected_selector in args.expected_selector:
                page.locator(expected_selector).first.wait_for(
                    state="visible", timeout=args.timeout_ms
                )

            if args.anchor_testid:
                page.get_by_test_id(args.anchor_testid).wait_for(
                    state="visible", timeout=args.timeout_ms
                )

            if args.click_anchor_first:
                page.get_by_test_id(args.anchor_testid).click()
                for anchor_text in args.expected_after_anchor_text:
                    page.get_by_text(anchor_text, exact=False).first.wait_for(
                        state="visible", timeout=args.timeout_ms
                    )

            if (
                args.preclick_text
                or args.preclick_text_substring
                or args.preclick_visible_text
                or args.preclick_visible_text_substring
                or args.preclick_selector
            ):
                if args.preclick_selector:
                    page.locator(args.preclick_selector).first.click()
                elif args.preclick_visible_text_substring:
                    page.get_by_text(args.preclick_visible_text_substring, exact=False).first.click()
                elif args.preclick_visible_text:
                    page.get_by_text(args.preclick_visible_text, exact=True).first.click()
                elif args.preclick_text_substring:
                    page.get_by_role("button", name=args.preclick_text_substring, exact=False).first.click()
                else:
                    page.get_by_role("button", name=args.preclick_text, exact=True).click()

            if args.trigger_text or args.trigger_text_substring or args.trigger_selector:
                if args.trigger_selector:
                    page.locator(args.trigger_selector).first.click()
                elif args.trigger_text_substring:
                    page.get_by_role("button", name=args.trigger_text_substring, exact=False).first.click()
                else:
                    page.get_by_role("button", name=args.trigger_text, exact=True).click()
                page.get_by_test_id(args.panel_testid).wait_for(
                    state="visible", timeout=args.timeout_ms
                )
                if args.expected_panel_count is not None:
                    panel_count = page.get_by_test_id(args.panel_testid).count()
                    if panel_count != args.expected_panel_count:
                        raise RuntimeError(
                            f"Expected {args.expected_panel_count} AOL panel(s), got {panel_count}"
                        )
                if args.expected_panel_mode:
                    _wait_for_panel_mode(
                        page,
                        args.panel_testid,
                        args.expected_panel_mode,
                        args.timeout_ms,
                    )
                    panel_mode = page.get_by_test_id(args.panel_testid).first.get_attribute("data-aol-mode")
                    if panel_mode != args.expected_panel_mode:
                        raise RuntimeError(
                            f"Expected panel mode '{args.expected_panel_mode}', got '{panel_mode}'"
                        )
                for panel_text in args.expected_panel_text:
                    page.get_by_text(panel_text, exact=False).first.wait_for(
                        state="visible", timeout=args.timeout_ms
                    )

            if args.panel_action_text or args.panel_action_text_substring:
                if args.panel_action_text_substring:
                    page.get_by_text(args.panel_action_text_substring, exact=False).first.click()
                else:
                    page.get_by_text(args.panel_action_text, exact=True).first.click()

                for expected_url_substring in args.expected_url_substring:
                    page.wait_for_url(
                        lambda current_url: expected_url_substring in current_url,
                        timeout=args.timeout_ms,
                    )
                if args.expected_panel_mode_after_action:
                    _wait_for_panel_mode(
                        page,
                        args.panel_testid,
                        args.expected_panel_mode_after_action,
                        args.timeout_ms,
                    )
                    panel_mode = page.get_by_test_id(args.panel_testid).first.get_attribute("data-aol-mode")
                    if panel_mode != args.expected_panel_mode_after_action:
                        raise RuntimeError(
                            "Expected panel mode "
                            f"'{args.expected_panel_mode_after_action}' after action, got '{panel_mode}'"
                        )

            current_url = page.url
            browser.close()
    except PlaywrightTimeoutError as exc:
        print(f"FAILED: render-proof smoke timed out: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"FAILED: render-proof smoke failed: {exc}", file=sys.stderr)
        return 1

    matching_console = _iter_matching_console_messages(console_messages)
    if page_errors or matching_console:
        print("FAILED: browser console emitted loader/render errors", file=sys.stderr)
        if page_errors:
            print("page errors:", file=sys.stderr)
            for entry in page_errors:
                print(f"  - {entry}", file=sys.stderr)
        if matching_console:
            print("console messages:", file=sys.stderr)
            for entry in matching_console:
                print(f"  - {entry}", file=sys.stderr)
        return 1

    if (
        args.verify_session_attachment_owner_pack
        or args.verify_session_attachment_object_kind
        or args.verify_session_attachment_object_id
        or args.verify_session_attachment_object_id_substring
    ):
        session_id = _extract_session_id_from_url(current_url)
        if not session_id:
            print(
                "FAILED: could not extract session_id from current URL for session attachment verification",
                file=sys.stderr,
            )
            return 1
        try:
            session_payload = _fetch_json(
                f"{args.api_base_url.rstrip('/')}/api/v1/workspaces/"
                f"{urllib.parse.quote(args.workspace_id, safe='')}/meeting-sessions/"
                f"{urllib.parse.quote(session_id, safe='')}"
            )
        except Exception as exc:
            print(f"FAILED: meeting session verification fetch failed: {exc}", file=sys.stderr)
            return 1

        if not _session_has_expected_attachment(
            session_payload,
            owner_pack=args.verify_session_attachment_owner_pack,
            object_kind=args.verify_session_attachment_object_kind,
            object_id=args.verify_session_attachment_object_id,
            object_id_substring=args.verify_session_attachment_object_id_substring,
        ):
            print(
                "FAILED: meeting session metadata did not include the expected AOL attachment",
                file=sys.stderr,
            )
            return 1

    print("render-proof verified")
    print(f"capability: {installed_entry.get('code') or installed_entry.get('id')}")
    print(f"page_url: {page_url}")
    print(f"current_url: {current_url}")
    print(f"ui_components: {[component.get('code') for component in components]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
