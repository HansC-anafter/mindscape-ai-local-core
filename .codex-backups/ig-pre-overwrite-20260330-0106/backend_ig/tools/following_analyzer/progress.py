from typing import Any, Dict, List


def generate_summary(accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate summary statistics from account list.
    """
    total = len(accounts)
    verified_count = sum(1 for acc in accounts if acc.get("is_verified", False))
    with_bio = sum(1 for acc in accounts if acc.get("bio"))
    with_page_stats = sum(1 for acc in accounts if "follower_count_text" in acc)

    return {
        "total_accounts": total,
        "verified_accounts": verified_count,
        "accounts_with_bio": with_bio,
        "accounts_with_page_stats": with_page_stats,
        "verified_percentage": (verified_count / total * 100) if total > 0 else 0,
        "bio_percentage": (with_bio / total * 100) if total > 0 else 0,
    }

