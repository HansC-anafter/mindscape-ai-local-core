from backend.app.routes.core import capability_packs


def _reset_pack_yaml_cache():
    capability_packs._pack_yaml_cache = None
    capability_packs._pack_yaml_cache_time = 0
    capability_packs._clear_installed_capability_route_cache()
