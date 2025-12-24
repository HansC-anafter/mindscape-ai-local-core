"""IG Post tools for Instagram post generation and style analysis."""

# Auto-register tools when module is imported
def _auto_register():
    """Auto-register IG Post tools when module is imported."""
    from backend.app.services.tools.registry import register_ig_post_tools
    register_ig_post_tools()

_auto_register()

