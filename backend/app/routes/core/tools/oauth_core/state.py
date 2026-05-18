import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


OAUTH_CONFIGS: Dict[str, Dict[str, Any]] = {
    "twitter": {
        "authorize_url": "https://twitter.com/i/oauth2/authorize",
        "token_url": "https://api.twitter.com/2/oauth2/token",
        "scopes": ["tweet.read", "tweet.write", "users.read", "offline.access"],
        "client_id_env": "TWITTER_CLIENT_ID",
        "client_secret_env": "TWITTER_CLIENT_SECRET",
    },
    "facebook": {
        "authorize_url": "https://www.facebook.com/v18.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
        "scopes": ["pages_manage_posts", "pages_read_engagement", "pages_show_list"],
        "client_id_env": "FACEBOOK_CLIENT_ID",
        "client_secret_env": "FACEBOOK_CLIENT_SECRET",
    },
    "instagram": {
        "authorize_url": "https://api.instagram.com/oauth/authorize",
        "token_url": "https://api.instagram.com/oauth/access_token",
        "scopes": ["user_profile", "user_media"],
        "client_id_env": "INSTAGRAM_CLIENT_ID",
        "client_secret_env": "INSTAGRAM_CLIENT_SECRET",
    },
    "linkedin": {
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": ["openid", "profile", "email", "w_member_social"],
        "client_id_env": "LINKEDIN_CLIENT_ID",
        "client_secret_env": "LINKEDIN_CLIENT_SECRET",
    },
    "youtube": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
    },
    "line": {
        "authorize_url": "https://access.line.me/oauth2/v2.1/authorize",
        "token_url": "https://api.line.me/oauth2/v2.1/token",
        "scopes": ["profile", "openid", "email"],
        "client_id_env": "LINE_CHANNEL_ID",
        "client_secret_env": "LINE_CHANNEL_SECRET",
    },
}
