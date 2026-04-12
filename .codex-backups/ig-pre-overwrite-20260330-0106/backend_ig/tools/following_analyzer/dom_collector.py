"""
DOM collection and source-attribution state machine.

Houses the logic that scrapes accounts from the IG following dialog DOM
and routes them into the appropriate pool (following_list / suggestion /
unknown) based on the dialog_state state machine.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Set

from .scroll_context import ScrollContext
from .scroll_engine import with_timeout

logger = logging.getLogger(__name__)

_SUGGESTION_SECTION_MARKERS = (
    "suggested for you",
    "為你推薦",
    "推荐给你",
    "推薦給你",
)

_SUGGESTION_ROW_MARKERS = _SUGGESTION_SECTION_MARKERS + (
    "followed by ",
    "see all suggestions",
)


def _is_suggestion_section_label(value: Any) -> bool:
    """Return True when a DOM entry was captured from a recommendation section."""
    if value is None:
        return False
    text = str(value).strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _SUGGESTION_SECTION_MARKERS)


def _is_suggestion_row(entry: Dict[str, Any]) -> bool:
    """Return True when row-level DOM hints indicate a recommendation row."""
    if bool(entry.get("suggestion_row_hint")):
        return True
    for key in ("section_label", "bio", "row_text"):
        value = entry.get(key)
        if value is None:
            continue
        text = str(value).strip().lower()
        if text and any(marker in text for marker in _SUGGESTION_ROW_MARKERS):
            return True
    return bool(entry.get("dialog_has_suggestion_footer"))


async def collect_accounts_from_dom(ctx: ScrollContext) -> Set[str]:
    """Scrape accounts from DOM.  Returns the set of usernames currently visible.

    Routes new accounts to the appropriate pool based on ctx.dialog_state.
    """
    items = await with_timeout(
        ctx.dialog.evaluate(
            """
            (root) => {
              const results = [];
              const links = Array.from(root.querySelectorAll('a[href^="/"]'));
              const isValid = (u) => u && !['explore','reels','direct','stories','accounts','p','tv'].includes(u);
              const suggestionPhrases = ['suggested for you', '為你推薦', '推荐给你', '推薦給你'];
              const suggestionFooterPhrases = ['see all suggestions'];
              const isSuggestionText = (text) => {
                const normalized = (text || '').trim().toLowerCase();
                if (!normalized) return false;
                return suggestionPhrases.some((phrase) => normalized.includes(phrase));
              };
              const hasSuggestionFooter = (text) => {
                const normalized = (text || '').trim().toLowerCase();
                if (!normalized) return false;
                return suggestionFooterPhrases.some((phrase) => normalized.includes(phrase));
              };
              const rootText = root ? (root.textContent || '') : '';
              const dialogHasSuggestionFooter = hasSuggestionFooter(rootText);
              const detectSectionLabel = (row, rootNode) => {
                if (!row) return '';
                let node = row;
                for (let depth = 0; node && depth < 5; depth += 1, node = node.parentElement) {
                  let prev = node.previousElementSibling;
                  let scanned = 0;
                  while (prev && scanned < 6) {
                    const text = (prev.textContent || '').trim();
                    if (isSuggestionText(text)) return text;
                    prev = prev.previousElementSibling;
                    scanned += 1;
                  }
                  if (node === rootNode) break;
                }
                return '';
              };

              for (const a of links) {
                const href = a.getAttribute('href') || '';
                if (!href.startsWith('/')) continue;
                const username = href.replace(/^\\/+/, '').split('/')[0];
                if (!isValid(username)) continue;

                const row = a.closest('div') || a.parentElement;
                const externalUrl = `https://www.instagram.com/${username}/`;
                const sectionLabel = detectSectionLabel(row, root);
                const rowText = row ? (row.textContent || '') : '';
                const suggestionRowHint = (
                  isSuggestionText(sectionLabel)
                  || isSuggestionText(rowText)
                  || rowText.toLowerCase().includes('followed by ')
                  || dialogHasSuggestionFooter
                );

                const img = row ? row.querySelector('img') : null;
                const avatarUrl = img ? (img.getAttribute('src') || '') : '';
                const verified = row ? row.querySelector('svg[aria-label*="Verified"], svg[aria-label*="已驗證"]') : null;
                const isVerified = !!verified;

                let displayName = username;
                let bio = '';
                if (row) {
                  const spans = Array.from(row.querySelectorAll('span')).slice(0, 8);
                  const texts = [];
                  for (const s of spans) {
                    const t = (s.textContent || '').trim();
                    if (t) texts.push(t);
                  }
                  const dedup = [];
                  for (const t of texts) {
                    if (!dedup.includes(t)) dedup.push(t);
                  }
                  const filtered = dedup.filter(t => {
                    const tl = t.toLowerCase();
                    return !['following','follow','remove'].includes(tl) && !['追蹤中','追蹤','移除'].includes(t);
                  }).filter(t => t !== username);
                  if (filtered.length > 0) displayName = filtered[0] || username;
                  if (filtered.length > 1) bio = filtered[1] || '';
                }

                results.push({
                  username,
                  display_name: displayName,
                  bio,
                  is_verified: isVerified,
                  avatar_url: avatarUrl,
                  external_url: externalUrl,
                  section_label: sectionLabel,
                  row_text: rowText,
                  dialog_has_suggestion_footer: dialogHasSuggestionFooter,
                  suggestion_row_hint: suggestionRowHint,
                });
              }

              return results;
            }
            """
        ),
        timeout_seconds=6.0,
        default=[],
    )

    visible_now: set = set()
    if not isinstance(items, list):
        return visible_now

    for entry in items:
        try:
            username = (entry.get("username") or "").strip()
            if not username:
                continue
            visible_now.add(username)

            # Already in a higher-confidence pool — skip
            # Priority: following_list > suggestion > unknown
            if username in ctx.unique_accounts:
                continue

            account_data = {
                "username": username,
                "display_name": entry.get("display_name") or username,
                "bio": entry.get("bio") or "",
                "is_verified": bool(entry.get("is_verified")),
                "avatar_url": entry.get("avatar_url") or "",
                "account_link": entry.get("external_url")
                or f"https://www.instagram.com/{username}/",
                "external_url": entry.get("external_url")
                or f"https://www.instagram.com/{username}/",
                "fetched_at": datetime.now().isoformat(),
            }
            section_label = entry.get("section_label")
            if section_label:
                account_data["_section_label"] = section_label

            if _is_suggestion_section_label(section_label) or _is_suggestion_row(entry):
                account_data["_source_context"] = "suggestion"
                if username not in ctx.suggestion_accounts:
                    ctx.suggestion_accounts[username] = account_data
                ctx.unknown_accounts.pop(username, None)
                continue

            # Route to pool based on dialog state
            if ctx.dialog_state == "healthy":
                if ctx.degraded_consecutive == 1:
                    # Single pending replacement signal — ambiguous
                    account_data["_source_context"] = "unknown"
                    if username not in ctx.suggestion_accounts:
                        ctx.unknown_accounts[username] = account_data
                else:
                    account_data["_source_context"] = "following_list"
                    ctx.unique_accounts[username] = account_data
                    # Promote from weaker pools if present
                    ctx.unknown_accounts.pop(username, None)
                    ctx.suggestion_accounts.pop(username, None)
            elif ctx.dialog_state == "degraded":
                account_data["_source_context"] = "suggestion"
                if username not in ctx.suggestion_accounts:
                    ctx.suggestion_accounts[username] = account_data
                # Promote unknown→suggestion (stronger evidence)
                ctx.unknown_accounts.pop(username, None)
            else:  # unconfirmed
                account_data["_source_context"] = "unknown"
                if (
                    username not in ctx.suggestion_accounts
                    and username not in ctx.unknown_accounts
                ):
                    ctx.unknown_accounts[username] = account_data

            if ctx.max_accounts and len(ctx.unique_accounts) >= ctx.max_accounts:
                return visible_now
        except Exception:
            continue
    return visible_now


# ---------------------------------------------------------------------------
# Source-attribution helpers
# ---------------------------------------------------------------------------


def detect_scroll_advanced(
    pre_scroll_top,
    post_scroll_top,
    pre_window_top,
    post_window_top,
    js_metrics,
    pre_js_scroll_top,
) -> bool:
    """Return True if scroll position advanced by at least 50px in any source."""
    try:
        _sa_container = (
            pre_scroll_top is not None
            and post_scroll_top is not None
            and post_scroll_top > pre_scroll_top + 50
        )
        _sa_window = (
            pre_window_top is not None
            and post_window_top is not None
            and post_window_top > pre_window_top + 50
        )
        _sa_js = (
            isinstance(js_metrics, dict)
            and js_metrics.get("ok")
            and pre_js_scroll_top is not None
            and float(js_metrics.get("scrollTop", 0)) > pre_js_scroll_top + 50
        )
        return _sa_container or _sa_window or _sa_js
    except Exception:
        return False


def detect_replacement_signal(
    visible_now: set,
    visible_prev: set,
    scroll_advanced: bool,
    no_new_accounts_streak: int,
) -> bool:
    """Return True if DOM content looks like it was replaced (not scrolled)."""
    try:
        if visible_prev and len(visible_now) > 5:
            _overlap = visible_now & visible_prev
            _overlap_ratio = len(_overlap) / max(len(visible_prev), 1)
            return (
                _overlap_ratio < 0.15
                and not scroll_advanced
                and no_new_accounts_streak >= 3
            )
    except Exception:
        pass
    return False


def update_dialog_state(
    ctx: ScrollContext,
    iteration: int,
    before_count: int,
    after_count: int,
    replacement_signal: bool,
    visible_now: set,
    *,
    before_all_count: int = 0,
    after_all_count: int = 0,
) -> None:
    """Advance the source-attribution state machine.

    ``before_all_count`` / ``after_all_count`` track growth across ALL
    pools (unique + unknown + suggestion).  The unconfirmed → healthy
    transition uses these because accounts collected while still
    unconfirmed are routed to ``unknown_accounts``, not ``unique_accounts``.
    """
    try:
        if ctx.dialog_state == "unconfirmed":
            # Use all-pool growth to detect that scrolling produces new
            # accounts — evidence the dialog is showing the following list.
            growth_in_confirmable_pool = after_count > before_count or bool(
                ctx.unknown_accounts
            )
            if after_all_count > before_all_count and growth_in_confirmable_pool:
                ctx.dialog_state = "healthy"
                # Promote all accounts accumulated during unconfirmed phase
                # into the following_list pool now that we have evidence.
                promoted = 0
                for uname, data in list(ctx.unknown_accounts.items()):
                    if uname not in ctx.unique_accounts:
                        data["_source_context"] = "following_list"
                        ctx.unique_accounts[uname] = data
                        promoted += 1
                ctx.unknown_accounts.clear()
                ctx.dialog_state_transitions.append(
                    {
                        "iteration": iteration,
                        "from": "unconfirmed",
                        "to": "healthy",
                        "reason": "scroll_growth",
                        "promoted_from_unknown": promoted,
                    }
                )
                logger.info(
                    f"[IGFollowingAnalyzer] Dialog state → healthy at iter {iteration}. "
                    f"promoted {promoted} unknown → following_list"
                )
        elif ctx.dialog_state == "healthy":
            if replacement_signal:
                ctx.degraded_consecutive += 1
                if ctx.degraded_consecutive >= 2:
                    ctx.following_list_snapshot = set(ctx.unique_accounts.keys())
                    ctx.dialog_state = "degraded"
                    ctx.dialog_state_transitions.append(
                        {
                            "iteration": iteration,
                            "from": "healthy",
                            "to": "degraded",
                            "reason": "consecutive_replacement",
                            "following_list_snapshot_size": len(
                                ctx.following_list_snapshot
                            ),
                        }
                    )
                    logger.warning(
                        f"[IGFollowingAnalyzer] Dialog state → degraded at iter {iteration}. "
                        f"following_list={len(ctx.unique_accounts)}, snapshot={len(ctx.following_list_snapshot)}"
                    )
            else:
                ctx.degraded_consecutive = 0
        elif ctx.dialog_state == "degraded":
            # Recovery: pre-degraded following_list accounts reappear in DOM
            _reappeared = visible_now & ctx.following_list_snapshot
            _recovery_threshold = max(3, int(len(ctx.following_list_snapshot) * 0.1))
            if len(_reappeared) >= _recovery_threshold:
                ctx.dialog_state = "healthy"
                ctx.degraded_consecutive = 0
                ctx.dialog_state_transitions.append(
                    {
                        "iteration": iteration,
                        "from": "degraded",
                        "to": "healthy",
                        "reason": "following_list_reappeared",
                        "reappeared_count": len(_reappeared),
                        "threshold": _recovery_threshold,
                    }
                )
                logger.info(
                    f"[IGFollowingAnalyzer] Dialog state recovered → healthy at iter {iteration}. "
                    f"reappeared={len(_reappeared)}/{_recovery_threshold}"
                )
    except Exception:
        pass


def apply_terminal_promotion(ctx: ScrollContext, iteration: int) -> int:
    """Promote unknown → unique if state is still unconfirmed at loop exit.

    Covers small following lists where the initial collect grabs everything
    and subsequent scrolls produce no new accounts.  Returns the number of
    promoted accounts (0 if no promotion was needed).
    """
    if ctx.dialog_state != "unconfirmed" or not ctx.unknown_accounts:
        return 0

    if ctx.suggestion_accounts:
        logger.info(
            "[IGFollowingAnalyzer] Terminal promotion skipped: %d unknown and %d suggestion accounts remain ambiguous",
            len(ctx.unknown_accounts),
            len(ctx.suggestion_accounts),
        )
        return 0

    promoted = 0
    for uname, data in list(ctx.unknown_accounts.items()):
        if uname not in ctx.unique_accounts:
            data["_source_context"] = "following_list"
            ctx.unique_accounts[uname] = data
            promoted += 1
    ctx.unknown_accounts.clear()
    ctx.dialog_state = "healthy"
    ctx.dialog_state_transitions.append(
        {
            "iteration": iteration,
            "from": "unconfirmed",
            "to": "healthy",
            "reason": "terminal_promotion",
            "promoted_from_unknown": promoted,
        }
    )
    logger.info(
        f"[IGFollowingAnalyzer] Terminal promotion: {promoted} unknown → following_list "
        f"(dialog never left unconfirmed)"
    )
    return promoted
