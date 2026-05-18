from . import actions_routes, provider_routes

router = provider_routes.router
router.include_router(actions_routes.router)
