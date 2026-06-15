import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


async def regenerate_embedding(
    source_text: str,
    target_model: str,
    target_provider: str,
) -> Optional[List[float]]:
    try:
        from backend.app.services.config_store import ConfigStore

        config_store = ConfigStore()
        config = config_store.get_or_create_config("default-user")

        if target_provider == "openai":
            api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OpenAI API key not configured")
                return None

            import openai

            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(model=target_model, input=source_text)

            if response.data and len(response.data) > 0:
                return response.data[0].embedding

        elif target_provider == "gemini-api":
            api_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not api_key:
                logger.error("Google AI API key not configured")
                return None

            import google.generativeai as genai

            genai.configure(api_key=api_key)
            result = genai.embed_content(
                model=f"models/{target_model}",
                content=source_text,
            )
            embedding = result.get("embedding", [])
            return embedding if embedding else None

        elif target_provider == "vertex-ai":
            from backend.app.routes.core.system_settings.shared import settings_store

            service_account_setting = settings_store.get_setting(
                "vertex_ai_service_account_json"
            )
            project_id_setting = settings_store.get_setting("vertex_ai_project_id")
            location_setting = settings_store.get_setting("vertex_ai_location")

            vertex_sa_json = (
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

            if not vertex_sa_json or not vertex_project_id:
                logger.error("Vertex AI credentials not configured")
                return None

            import json
            import vertexai
            from google.oauth2 import service_account
            from vertexai.language_models import TextEmbeddingModel

            try:
                sa_info = json.loads(vertex_sa_json)
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info
                )
            except (json.JSONDecodeError, ValueError):
                credentials = service_account.Credentials.from_service_account_file(
                    vertex_sa_json
                )

            vertexai.init(
                project=vertex_project_id,
                location=vertex_location,
                credentials=credentials,
            )

            model = TextEmbeddingModel.from_pretrained(target_model)
            embeddings = model.get_embeddings([source_text])
            if embeddings and len(embeddings) > 0 and embeddings[0].values:
                return embeddings[0].values

        else:
            logger.error(f"Unsupported provider: {target_provider}")
            return None

    except Exception as e:
        logger.error(f"Failed to regenerate embedding: {e}", exc_info=True)
        return None

    return None
