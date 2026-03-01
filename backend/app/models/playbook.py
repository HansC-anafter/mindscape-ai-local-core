"""Playbook data models (compatibility re-export)."""

from .playbook_models import *  # noqa: F401,F403
from .playbook_models import __all__ as _PLAYBOOK_MODEL_ALL

__all__ = list(_PLAYBOOK_MODEL_ALL)

# Preserve legacy module path for model classes.
for _name in __all__:
    _obj = globals().get(_name)
    if isinstance(_obj, type) and _obj.__module__.startswith(
        "backend.app.models.playbook_models"
    ):
        _obj.__module__ = __name__

del _name

del _obj

del _PLAYBOOK_MODEL_ALL
