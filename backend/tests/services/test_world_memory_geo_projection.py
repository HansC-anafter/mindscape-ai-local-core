from backend.app.system_capabilities.world_memory_core.services.context_export_facade import (
    ContextExportFacade,
)


def test_world_memory_core_projects_geo_context():
    result = ContextExportFacade().export_context(
        workspace_id="ws-demo",
        geo_context={
            "provider": "google_maps_platform",
            "geo_anchor": {
                "lat": 25.033,
                "lng": 121.565,
                "place_id": "place-101",
            },
            "venue_context": {
                "name": "Taipei 101",
                "formatted_address": "Taipei City",
            },
            "route_context": {
                "mode": "walking",
                "distance_meters": 800,
                "duration_seconds": 600,
            },
        },
    )

    assert result["world_memory_packet"]["geo_anchor"]["place_id"] == "place-101"
    assert "Venue: Taipei 101" in result["world_card_text"]
    assert "Route(walking)" in result["world_card_text"]
