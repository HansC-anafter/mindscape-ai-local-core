"""
LLM Model Pull/Download Manager

Redis-backed pull progress tracking with Ollama streaming and HuggingFace
filesystem polling. Self-contained subsystem extracted from models.py.
"""

import asyncio
import json as _json
import logging
import os as _os
import time as _time
import threading as _threading
import uuid as _uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Body

logger = logging.getLogger(__name__)

router = APIRouter()

_PULL_TASK_TTL = 300  # seconds
_PULL_KEY_PREFIX = "pull_task:"

# Fallback in-memory store (used only when Redis is unavailable)
_pull_tasks_fallback: Dict[str, Dict[str, Any]] = {}


# ── Redis helpers ──


def _sync_redis():
    """Get a synchronous Redis client for use in download threads."""
    try:
        import redis
        return redis.Redis(
            host=_os.getenv("REDIS_HOST", "redis"),
            port=int(_os.getenv("REDIS_PORT", "6379")),
            password=_os.getenv("REDIS_PASSWORD") or None,
            db=int(_os.getenv("REDIS_DB", "0")),
            socket_connect_timeout=2,
            decode_responses=True,
        )
    except Exception:
        return None


async def _async_redis():
    """Get async Redis client."""
    try:
        from backend.app.services.cache.async_redis import get_async_redis_client
        return await get_async_redis_client()
    except Exception:
        return None


def _task_key(task_id: str) -> str:
    return f"{_PULL_KEY_PREFIX}{task_id}"


def _set_task_sync(r, task_id: str, fields: Dict[str, Any]):
    """Write task fields to Redis (sync, for use in threads)."""
    key = _task_key(task_id)
    if r:
        try:
            # Convert all values to strings for Redis
            str_fields = {k: str(v) for k, v in fields.items()}
            r.hset(key, mapping=str_fields)
            r.expire(key, _PULL_TASK_TTL)
            return
        except Exception:
            pass
    # Fallback
    if task_id not in _pull_tasks_fallback:
        _pull_tasks_fallback[task_id] = {}
    _pull_tasks_fallback[task_id].update(fields)


async def _set_task_async(task_id: str, fields: Dict[str, Any]):
    """Write task fields to Redis (async, for use in endpoints)."""
    r = await _async_redis()
    key = _task_key(task_id)
    if r:
        try:
            str_fields = {k: str(v) for k, v in fields.items()}
            await r.hset(key, mapping=str_fields)
            await r.expire(key, _PULL_TASK_TTL)
            return
        except Exception:
            pass
    # Fallback
    if task_id not in _pull_tasks_fallback:
        _pull_tasks_fallback[task_id] = {}
    _pull_tasks_fallback[task_id].update(fields)


def _get_task_sync(r, task_id: str) -> Optional[Dict[str, Any]]:
    """Read task from Redis (sync)."""
    key = _task_key(task_id)
    if r:
        try:
            data = r.hgetall(key)
            if data:
                return _parse_task(data)
        except Exception:
            pass
    return _pull_tasks_fallback.get(task_id)


async def _get_task_async(task_id: str) -> Optional[Dict[str, Any]]:
    """Read task from Redis (async)."""
    r = await _async_redis()
    key = _task_key(task_id)
    if r:
        try:
            data = await r.hgetall(key)
            if data:
                return _parse_task(data)
        except Exception:
            pass
    return _pull_tasks_fallback.get(task_id)


def _parse_task(data: Dict[str, str]) -> Dict[str, Any]:
    """Parse Redis hash string values back to proper types."""
    return {
        "status": data.get("status", ""),
        "progress_pct": int(float(data.get("progress_pct", "0"))),
        "downloaded_bytes": int(float(data.get("downloaded_bytes", "0"))),
        "total_bytes": int(float(data.get("total_bytes", "0"))),
        "message": data.get("message", ""),
        "model_name": data.get("model_name", ""),
        "model_id": data.get("model_id", ""),
        "provider": data.get("provider", ""),
        "updated_at": float(data.get("updated_at", "0")),
    }


def _is_cancelled_sync(r, task_id: str) -> bool:
    """Check if task has been cancelled (sync, for download threads)."""
    if r:
        try:
            val = r.hget(_task_key(task_id), "status")
            return val == "cancelled"
        except Exception:
            pass
    fb = _pull_tasks_fallback.get(task_id, {})
    return fb.get("status") == "cancelled"


def _task_to_response(task_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
    """Convert task dict to API response."""
    return {
        "task_id": task_id,
        "status": task.get("status", ""),
        "progress_pct": task.get("progress_pct", 0),
        "downloaded_bytes": task.get("downloaded_bytes", 0),
        "total_bytes": task.get("total_bytes", 0),
        "message": task.get("message", ""),
        "model_name": task.get("model_name", ""),
        "model_id": task.get("model_id", ""),
        "provider": task.get("provider", ""),
    }


# ── Background download tasks ──


async def _run_ollama_pull(task_id: str, model_name: str):
    """Background task: Ollama pull with streaming progress."""
    import requests
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        base_url_setting = await asyncio.to_thread(
            settings_store.get_setting, "ollama_base_url"
        )
        base_url = base_url_setting.value if base_url_setting else "http://localhost:11434"

        await _set_task_async(task_id, {
            "status": "downloading",
            "message": f"Pulling {model_name} from Ollama...",
            "updated_at": _time.time(),
        })

        def _stream_pull():
            r = _sync_redis()
            resp = requests.post(
                f"{base_url}/api/pull",
                json={"name": model_name, "stream": True},
                stream=True,
                timeout=3600,
            )
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = _json.loads(line)
                    status = data.get("status", "")
                    total = data.get("total", 0)
                    completed = data.get("completed", 0)

                    if _is_cancelled_sync(r, task_id):
                        break

                    update: Dict[str, Any] = {
                        "message": status,
                        "updated_at": _time.time(),
                    }
                    if total > 0:
                        update["total_bytes"] = total
                        update["downloaded_bytes"] = completed
                        update["progress_pct"] = min(99, int(completed * 100 / total))

                    if status == "success":
                        update["status"] = "completed"
                        update["progress_pct"] = 100
                        update["message"] = f"Successfully pulled {model_name}"

                    _set_task_sync(r, task_id, update)

                    if status == "success":
                        break
                except Exception:
                    pass

        await asyncio.to_thread(_stream_pull)

        task = await _get_task_async(task_id)
        if task and task.get("status") != "completed":
            await _set_task_async(task_id, {
                "status": "completed",
                "progress_pct": 100,
                "message": f"Pull completed for {model_name}",
                "updated_at": _time.time(),
            })

    except Exception as e:
        logger.error(f"Ollama pull failed for {model_name}: {e}", exc_info=True)
        await _set_task_async(task_id, {
            "status": "failed",
            "message": f"Pull failed: {str(e)}",
            "updated_at": _time.time(),
        })


async def _run_hf_download(task_id: str, model_name: str):
    """Background task: HuggingFace download using Python huggingface_hub API."""
    try:
        await _set_task_async(task_id, {
            "status": "downloading",
            "message": f"Downloading {model_name}...",
            "updated_at": _time.time(),
        })

        def _do_download():
            from huggingface_hub import snapshot_download
            import os
            import threading

            r = _sync_redis()

            # Get repo info to estimate total size
            try:
                from huggingface_hub import HfApi
                api = HfApi()
                repo_info = api.repo_info(model_name, repo_type="model")
                siblings = repo_info.siblings or []
                total_size = 0
                for s in siblings:
                    sz = getattr(s, 'size', None) or getattr(s, 'lfs', {})
                    if isinstance(sz, dict):
                        sz = sz.get('size', 0)
                    total_size += sz or 0
                if total_size > 0:
                    _set_task_sync(r, task_id, {
                        "total_bytes": total_size,
                        "message": f"Downloading {model_name} ({total_size / 1e9:.1f} GB)...",
                        "updated_at": _time.time(),
                    })
                    logger.info(f"HF download {model_name}: total_bytes={total_size}")
                else:
                    logger.warning(f"HF download {model_name}: could not determine total size from {len(siblings)} siblings")
            except Exception as e:
                logger.warning(f"HF download {model_name}: repo_info failed: {e}")

            # Monitor progress via file system polling
            download_done = threading.Event()
            download_error = None

            def _monitor_progress():
                cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
                model_dir_name = f"models--{model_name.replace('/', '--')}"
                model_cache = os.path.join(cache_dir, model_dir_name)

                while not download_done.is_set():
                    if _is_cancelled_sync(r, task_id):
                        break
                    try:
                        task = _get_task_sync(r, task_id)
                        if not task:
                            break

                        downloaded = 0
                        for scan_dir in [model_cache, os.path.join(model_cache, "blobs")]:
                            if not os.path.exists(scan_dir):
                                continue
                            for root, dirs, files in os.walk(scan_dir):
                                for f in files:
                                    try:
                                        downloaded += os.path.getsize(os.path.join(root, f))
                                    except OSError:
                                        pass
                        if downloaded > 0:
                            total = task.get("total_bytes", 0)
                            update: Dict[str, Any] = {
                                "downloaded_bytes": downloaded,
                                "updated_at": _time.time(),
                            }
                            if total > 0:
                                pct = min(99, int(downloaded * 100 / total))
                                update["progress_pct"] = pct
                                update["message"] = f"Downloading... {downloaded / 1e9:.1f}/{total / 1e9:.1f} GB"
                            else:
                                update["message"] = f"Downloading... {downloaded / 1e6:.0f} MB"
                            _set_task_sync(r, task_id, update)
                    except Exception:
                        pass
                    download_done.wait(1)

            monitor = threading.Thread(target=_monitor_progress, daemon=True)
            monitor.start()

            try:
                snapshot_download(model_name, repo_type="model")
            except Exception as e:
                download_error = e
            finally:
                download_done.set()
                monitor.join(timeout=5)

            if download_error:
                raise download_error

        await asyncio.to_thread(_do_download)

        await _set_task_async(task_id, {
            "status": "completed",
            "progress_pct": 100,
            "message": f"Successfully downloaded {model_name}",
            "updated_at": _time.time(),
        })

    except Exception as e:
        logger.error(f"HF download failed for {model_name}: {e}", exc_info=True)
        await _set_task_async(task_id, {
            "status": "failed",
            "message": f"Download failed: {str(e)}",
            "updated_at": _time.time(),
        })


# ── Endpoints ──


@router.post("/llm-models/pull", response_model=Dict[str, Any])
async def pull_model(
    payload: Dict[str, Any] = Body(..., description="Model pull payload")
):
    """Trigger model pull with progress tracking."""
    try:
        model_name = payload.get("model_name")
        provider = payload.get("provider")

        if not model_name:
            raise HTTPException(status_code=400, detail="model_name is required")

        if provider not in ["ollama", "huggingface"]:
            return {
                "success": False,
                "message": f"Pull only supported for Ollama and HuggingFace providers (got {provider})",
            }

        task_id = _uuid.uuid4().hex[:8]
        model_id = payload.get("model_id", "")
        init_fields = {
            "status": "starting",
            "progress_pct": 0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "message": f"Starting download for {model_name}...",
            "model_name": model_name,
            "model_id": model_id,
            "provider": provider,
            "updated_at": _time.time(),
        }
        await _set_task_async(task_id, init_fields)

        if provider == "huggingface":
            asyncio.create_task(_run_hf_download(task_id, model_name))
        else:
            asyncio.create_task(_run_ollama_pull(task_id, model_name))

        return {
            "success": True,
            "task_id": task_id,
            "message": f"Download started for {model_name}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pull model: {e}", exc_info=True)
        return {"success": False, "message": f"Pull failed: {str(e)}"}


@router.get("/llm-models/pull/active", response_model=List[Dict[str, Any]])
async def get_active_pulls():
    """Get all active pull tasks (for page reload recovery)."""
    results = []
    r = await _async_redis()
    if r:
        try:
            keys = await r.keys(f"{_PULL_KEY_PREFIX}*")
            for key in keys:
                data = await r.hgetall(key)
                if data and data.get("status") in ("starting", "downloading"):
                    task_id = key.replace(_PULL_KEY_PREFIX, "")
                    results.append(_task_to_response(task_id, _parse_task(data)))
        except Exception:
            pass
    # Also check fallback
    for tid, t in _pull_tasks_fallback.items():
        if t.get("status") in ("starting", "downloading"):
            results.append(_task_to_response(tid, t))
    return results


@router.get("/llm-models/pull/{task_id}/progress", response_model=Dict[str, Any])
async def get_pull_progress(task_id: str):
    """Get download progress for a pull task."""
    task = await _get_task_async(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or expired")
    return _task_to_response(task_id, task)


@router.post("/llm-models/pull/{task_id}/cancel", response_model=Dict[str, Any])
async def cancel_pull(task_id: str):
    """Cancel an in-progress pull task."""
    task = await _get_task_async(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or expired")
    if task.get("status") not in ("starting", "downloading"):
        return {"success": False, "message": f"Task already {task.get('status')}"}
    await _set_task_async(task_id, {
        "status": "cancelled",
        "message": "Download cancelled",
        "updated_at": _time.time(),
    })
    return {"success": True, "message": "Download cancelled"}
