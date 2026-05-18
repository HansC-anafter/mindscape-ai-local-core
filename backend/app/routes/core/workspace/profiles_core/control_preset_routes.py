
from fastapi import APIRouter

from backend.app.services.knob_presets import PRESETS

router = APIRouter()

@router.get(
    "/control-profile/presets",
    summary="Get control profile preset templates",
    description="""
    Get available control profile preset templates.

    Presets provide pre-configured knob values for common use cases:
    - **observer**: Low intervention, organize only
    - **advisor**: Medium-high intervention, proactive suggestions
    - **executor**: High intervention, ready-to-confirm drafts
    """,
    tags=["control-profile"],
    responses={200: {"description": "List of available preset templates"}},
)
async def get_control_profile_presets():
    """Get available control profile preset templates"""
    presets = [
        {
            "id": "observer",
            "name": "Observer mode",
            "description": "Organize information without proactive suggestions",
            "icon": "eye",
            "knob_values": PRESETS["observer"].knob_values,
        },
        {
            "id": "advisor",
            "name": "Advisor mode",
            "description": "Proactively provide suggestions and options",
            "icon": "lightbulb",
            "knob_values": PRESETS["advisor"].knob_values,
        },
        {
            "id": "executor",
            "name": "Executor mode",
            "description": "Produce confirmation-ready drafts directly",
            "icon": "rocket",
            "knob_values": PRESETS["executor"].knob_values,
        },
    ]
    return {"presets": presets}
