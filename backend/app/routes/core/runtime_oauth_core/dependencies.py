try:
    from backend.app.database.session import get_db_postgres as get_db
except ImportError:
    try:
        from backend.app.database import get_db_postgres as get_db
    except ImportError:
        from mindscape.di.providers import get_db_session as get_db

try:
    from backend.app.auth import get_current_user
    from backend.app.models.user import User
except ImportError:
    from typing import Any

    async def get_current_user() -> Any:
        """Placeholder for development."""
        return type("User", (), {"id": "dev-user"})()

    User = Any
