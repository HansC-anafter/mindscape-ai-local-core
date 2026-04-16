"""
Legacy local-core compatibility shim for `shared.schemas.pose_signal`.

Canonical owner-pack contract lives in `capabilities.layer_asset_forge.schema.pose_signal`.
"""

from capabilities.layer_asset_forge.schema.pose_signal import *  # noqa: F401,F403
from capabilities.layer_asset_forge.schema.pose_signal import __all__
