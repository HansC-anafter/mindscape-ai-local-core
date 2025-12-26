"""IG Post style analyzer tool for analyzing visual style and generating design recommendations."""
import logging
import os
import tempfile
from typing import Dict, Any, Optional
import httpx
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_cloud_api_base_url() -> str:
    """Get cloud API base URL from environment or default."""
    return os.getenv("CLOUD_API_URL", "http://localhost:8000")


async def download_image_to_temp(image_url: str) -> str:
    """
    Download image from URL to temporary file.

    Args:
        image_url: Image URL to download

    Returns:
        Path to temporary file
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(image_url)
            response.raise_for_status()

            file_ext = Path(image_url).suffix or ".jpg"
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
            temp_file.write(response.content)
            temp_file.close()

            return temp_file.name
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to download image: {e.response.status_code} - {e.response.text}")
        raise ValueError(f"Failed to download image: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Image download request error: {e}")
        raise RuntimeError(f"Failed to download image: {str(e)}")


async def ig_post_style_analyzer(
    reference_image_path: Optional[str] = None,
    reference_image_url: Optional[str] = None,
    include_mood: bool = True
) -> Dict[str, Any]:
    """
    Analyze Instagram post style from reference image and generate design recommendations.

    Args:
        reference_image_path: Path to reference image file (local)
        reference_image_url: URL to reference image (will be downloaded to temp file)
        include_mood: Whether to include mood and narrative analysis

    Returns:
        Dictionary containing:
        - features: Extracted visual features from mind-lens
        - recommendations: IG Post design recommendations
        - suggested_format: Suggested post format (square, portrait, landscape)
        - color_palette: Recommended color palette
        - layout_type: Suggested layout type
    """
    if not reference_image_path and not reference_image_url:
        raise ValueError("Either reference_image_path or reference_image_url must be provided")

    temp_path = None
    try:
        if reference_image_url:
            temp_path = await download_image_to_temp(reference_image_url)
            image_path = temp_path
        else:
            image_path = reference_image_path

        base_url = _get_cloud_api_base_url()
        url = f"{base_url}/mind-lens/multimodal/extract-features"

        payload = {
            "image_path": image_path,
            "include_mood": include_mood
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            features = response.json()

        recommendations = _generate_ig_recommendations(features)

        return {
            "features": features,
            "recommendations": recommendations,
            "suggested_format": recommendations.get("suggested_format", "square"),
            "color_palette": recommendations.get("color_palette", []),
            "layout_type": recommendations.get("layout_type", "balanced")
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"Mind Lens API error: {e.response.status_code} - {e.response.text}")
        raise ValueError(f"Mind Lens API error: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Mind Lens request error: {e}")
        raise RuntimeError(f"Failed to connect to Mind Lens API: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {e}")


def _generate_ig_recommendations(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate IG Post design recommendations from extracted features.

    Args:
        features: Extracted visual features from mind-lens

    Returns:
        Dictionary containing design recommendations
    """
    recommendations = {
        "suggested_format": "square",
        "color_palette": [],
        "layout_type": "balanced",
        "text_overlay": False,
        "hashtag_suggestions": []
    }

    composition = features.get("composition", {})
    color_analysis = features.get("color_analysis", {})
    mood_analysis = features.get("mood_analysis", {})

    whitespace_ratio = composition.get("whitespace_ratio", 0.3)
    if whitespace_ratio > 0.5:
        recommendations["suggested_format"] = "portrait"
        recommendations["layout_type"] = "minimal"
    elif whitespace_ratio < 0.2:
        recommendations["suggested_format"] = "landscape"
        recommendations["layout_type"] = "dense"

    dominant_colors = color_analysis.get("dominant_colors", [])
    if dominant_colors:
        recommendations["color_palette"] = dominant_colors[:5]

    emotion_keywords = mood_analysis.get("emotion_keywords", [])
    if emotion_keywords:
        recommendations["hashtag_suggestions"] = [f"#{kw.replace(' ', '')}" for kw in emotion_keywords[:5]]

    return recommendations









