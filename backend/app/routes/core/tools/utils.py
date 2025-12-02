"""
Utility functions for tools routes

Contains shared helper functions like OAuth HTML page rendering.
"""
from fastapi.responses import HTMLResponse
from typing import Optional, Dict, Any


def render_oauth_page(success: bool, message: str, meta: Optional[Dict[str, Any]] = None) -> HTMLResponse:
    """
    Render OAuth callback page with consistent styling

    Args:
        success: Whether OAuth flow succeeded
        message: Message to display
        meta: Additional metadata (e.g., connection_id, tools_count, error)

    Returns:
        HTMLResponse with styled OAuth callback page
    """
    meta = meta or {}
    status_code = 200 if success else (meta.get("status_code", 400))
    title = "Authorization Successful" if success else "Authorization Failed"
    title_color = "#28a745" if success else "#dc3545"
    icon = "✅" if success else "❌"

    # Build postMessage payload
    post_message_payload = {}
    if success:
        post_message_payload["success"] = True
        if "connection_id" in meta:
            post_message_payload["connection_id"] = meta["connection_id"]
        if "tools_count" in meta:
            post_message_payload["tools_count"] = meta["tools_count"]
    else:
        if "error" in meta:
            post_message_payload["error"] = meta["error"]
        else:
            post_message_payload["error"] = message

    # Escape message for HTML
    escaped_message = message.replace("'", "\\'").replace('"', '&quot;')

    html_content = f"""
    <!DOCTYPE html>
    <html>
        <head>
            <title>{title}</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: #f5f5f5;
                }}
                .container {{
                    text-align: center;
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                h1 {{ color: {title_color}; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{icon} {title}</h1>
                <p>{message}</p>
                <p><small>This window will close automatically...</small></p>
            </div>
            <script>
                window.opener.postMessage({post_message_payload}, '*');
                setTimeout(() => {{
                    window.close();
                }}, {1500 if success else 2000});
            </script>
        </body>
    </html>
    """

    return HTMLResponse(content=html_content, status_code=status_code)

