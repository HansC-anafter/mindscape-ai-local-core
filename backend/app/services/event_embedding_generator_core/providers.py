import logging
from typing import List, Optional

logger = logging.getLogger("backend.app.services.event_embedding_generator")


async def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for text."""
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore

        settings_store = SystemSettingsStore()
        embedding_setting = settings_store.get_setting("embedding_model")

        if not embedding_setting:
            logger.warning("No embedding model configured")
            return None

        model_name = str(embedding_setting.value)
        provider = embedding_setting.metadata.get("provider", "openai")

        if provider == "vertex-ai":
            return await generate_embedding_vertex_ai(model_name, text, settings_store)
        return await generate_embedding_openai(model_name, text)

    except Exception as exc:
        logger.error("Failed to generate embedding: %s", exc, exc_info=True)
        return None


async def generate_embedding_openai(
    model_name: str, text: str
) -> Optional[List[float]]:
    """Generate embedding using OpenAI API."""
    try:
        import os
        import openai
        from backend.app.services.config_store import ConfigStore

        config_store = ConfigStore()
        config = config_store.get_or_create_config("default-user")

        api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OpenAI API key not configured for embedding generation")
            return None

        client = openai.OpenAI(api_key=api_key)
        response = client.embeddings.create(model=model_name, input=text)

        if response.data and len(response.data) > 0:
            return response.data[0].embedding

        return None
    except Exception as exc:
        logger.error("Failed to generate OpenAI embedding: %s", exc, exc_info=True)
        return None


async def generate_embedding_vertex_ai(
    model_name: str, text: str, settings_store
) -> Optional[List[float]]:
    """Generate embedding using Vertex AI."""
    try:
        import json
        import os
        from google.oauth2 import service_account
        from vertexai.language_models import TextEmbeddingModel
        import vertexai

        service_account_setting = settings_store.get_setting(
            "vertex_ai_service_account_json"
        )
        project_id_setting = settings_store.get_setting("vertex_ai_project_id")
        location_setting = settings_store.get_setting("vertex_ai_location")

        vertex_service_account_json = (
            service_account_setting.value
            if service_account_setting and service_account_setting.value
            else os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        vertex_project_id = (
            project_id_setting.value
            if project_id_setting and project_id_setting.value
            else os.getenv("GOOGLE_CLOUD_PROJECT")
        )
        vertex_location = (
            location_setting.value
            if location_setting and location_setting.value
            else os.getenv("VERTEX_LOCATION", "us-central1")
        )

        if not vertex_service_account_json or not vertex_project_id:
            logger.warning("Vertex AI credentials not configured for embedding generation")
            return None

        credentials = None
        if vertex_service_account_json:
            try:
                sa_info = json.loads(vertex_service_account_json)
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info
                )
                if not vertex_project_id and "project_id" in sa_info:
                    vertex_project_id = sa_info["project_id"]
            except (json.JSONDecodeError, ValueError):
                credentials = service_account.Credentials.from_service_account_file(
                    vertex_service_account_json
                )
                if not vertex_project_id:
                    with open(vertex_service_account_json, "r") as file_obj:
                        sa_info = json.load(file_obj)
                        if "project_id" in sa_info:
                            vertex_project_id = sa_info["project_id"]

        vertexai.init(
            project=vertex_project_id,
            location=vertex_location,
            credentials=credentials,
        )

        model = TextEmbeddingModel.from_pretrained(model_name)
        embeddings = model.get_embeddings([text])

        if embeddings and len(embeddings) > 0:
            return embeddings[0].values

        return None
    except Exception as exc:
        logger.error("Failed to generate Vertex AI embedding: %s", exc, exc_info=True)
        return None
