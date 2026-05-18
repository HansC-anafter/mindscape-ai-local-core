from typing import Optional

from fastapi.responses import HTMLResponse

def _popup_close_response(success: bool, error: Optional[str] = None):
    """Return HTML page that posts message to opener and closes the popup."""
    status_msg = "success" if success else f"error: {error or 'unknown'}"
    html = f"""<!DOCTYPE html>
<html><head><title>OAuth</title></head>
<body>
<script>
  if (window.opener) {{
    window.opener.postMessage({{
      type: 'RUNTIME_OAUTH_RESULT',
      success: {'true' if success else 'false'},
      error: {f'"{error}"' if error else 'null'}
    }}, '*');
  }}
  window.close();
</script>
<p>{'Authorization successful. This window will close.' if success else f'Authorization failed: {error}. You may close this window.'}</p>
</body></html>"""

    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=html)


def _close_window_html(success: bool, error: str = "", email: str = "") -> str:
    """Return HTML that shows status and closes the window."""
    if success:
        status_text = f"Connected as {email}" if email else "Connected"
        status_color = "#22c55e"
    else:
        status_text = f"Error: {error}"
        status_color = "#ef4444"

    return f"""<!DOCTYPE html>
<html><head><title>OAuth {'Success' if success else 'Failed'}</title></head>
<body style="display:flex;align-items:center;justify-content:center;height:100vh;
font-family:system-ui;background:#111;color:#eee">
<div style="text-align:center">
  <p style="color:{status_color};font-size:1.2rem">{status_text}</p>
  <p style="color:#888">This window will close automatically...</p>
</div>
<script>
setTimeout(function(){{ window.close(); }}, 2000);
</script>
</body></html>"""
