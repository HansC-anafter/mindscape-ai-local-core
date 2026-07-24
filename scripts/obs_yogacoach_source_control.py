from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import websockets


DEFAULT_CONFIG_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "obs-studio"
    / "plugin_config"
    / "obs-websocket"
    / "config.json"
)
DEFAULT_SCENE_NAME = "Mindscape External Camera"
DEFAULT_BILIBILI_SOURCE = "Mindscape Bilibili Reference Source"
DEFAULT_FALLBACK_SOURCES = (
    "Mindscape Local Yoga Reference Source",
    "Mindscape RTSP Source",
)


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def load_obs_websocket_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_auth(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(hashlib.sha256(f"{password}{salt}".encode()).digest())
    return base64.b64encode(hashlib.sha256(secret + challenge.encode()).digest()).decode()


class ObsClient:
    def __init__(self, *, uri: str, password: str) -> None:
        self.uri = uri
        self.password = password
        self.socket: Any = None

    async def __aenter__(self) -> "ObsClient":
        self.socket = await websockets.connect(self.uri)
        hello = json.loads(await self.socket.recv())
        if hello.get("op") != 0:
            raise RuntimeError(f"unexpected OBS hello op: {hello.get('op')}")
        identify: dict[str, Any] = {"rpcVersion": 1}
        authentication = hello.get("d", {}).get("authentication")
        if authentication:
            identify["authentication"] = build_auth(
                self.password,
                authentication["salt"],
                authentication["challenge"],
            )
        await self.socket.send(json.dumps({"op": 1, "d": identify}))
        identified = json.loads(await self.socket.recv())
        if identified.get("op") != 2:
            raise RuntimeError(f"OBS identify failed: {identified}")
        return self

    async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        if self.socket is not None:
            await self.socket.close()

    async def request(self, request_type: str, request_data: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.socket is None:
            raise RuntimeError("OBS socket is not connected")
        request_id = str(uuid4())
        await self.socket.send(
            json.dumps(
                {
                    "op": 6,
                    "d": {
                        "requestType": request_type,
                        "requestId": request_id,
                        "requestData": request_data or {},
                    },
                }
            )
        )
        while True:
            response = json.loads(await self.socket.recv())
            if response.get("op") != 7:
                continue
            data = response.get("d", {})
            if data.get("requestId") != request_id:
                continue
            status = data.get("requestStatus", {})
            if not status.get("result"):
                raise RuntimeError(
                    f"OBS request {request_type} failed: "
                    f"{status.get('code')} {status.get('comment')}"
                )
            return data.get("responseData", {})


async def set_scene_item_enabled(
    client: ObsClient,
    *,
    scene_name: str,
    scene_items: list[dict[str, Any]],
    source_name: str,
    enabled: bool,
) -> dict[str, Any] | None:
    item = next((entry for entry in scene_items if entry.get("sourceName") == source_name), None)
    if item is None:
        return None
    await client.request(
        "SetSceneItemEnabled",
        {
            "sceneName": scene_name,
            "sceneItemId": item["sceneItemId"],
            "sceneItemEnabled": enabled,
        },
    )
    return {
        "source_name": source_name,
        "scene_item_id": item["sceneItemId"],
        "enabled": enabled,
    }


async def refresh_browser_source(client: ObsClient, *, source_name: str) -> dict[str, Any]:
    settings = await client.request("GetInputSettings", {"inputName": source_name})
    input_settings = dict(settings.get("inputSettings") or {})
    await client.request(
        "SetInputSettings",
        {
            "inputName": source_name,
            "inputSettings": input_settings,
            "overlay": True,
        },
    )
    return {
        "source_name": source_name,
        "url": input_settings.get("url"),
        "width": input_settings.get("width"),
        "height": input_settings.get("height"),
        "fps": input_settings.get("fps"),
    }


async def activate_yogacoach_source(args: argparse.Namespace) -> dict[str, Any]:
    config = load_obs_websocket_config(Path(args.config_path))
    port = int(args.port or config.get("server_port") or 4455)
    password = args.password if args.password is not None else str(config.get("server_password") or "")
    uri = f"ws://{args.host}:{port}"
    async with ObsClient(uri=uri, password=password) as client:
        version = await client.request("GetVersion")
        await client.request("SetCurrentProgramScene", {"sceneName": args.scene_name})
        await client.request("SetCurrentPreviewScene", {"sceneName": args.scene_name})
        scene_items_response = await client.request("GetSceneItemList", {"sceneName": args.scene_name})
        scene_items = scene_items_response.get("sceneItems") or []
        item_results: list[dict[str, Any]] = []
        primary_result = await set_scene_item_enabled(
            client,
            scene_name=args.scene_name,
            scene_items=scene_items,
            source_name=args.bilibili_source,
            enabled=True,
        )
        if primary_result is not None:
            item_results.append(primary_result)
        for source_name in args.fallback_source:
            fallback_result = await set_scene_item_enabled(
                client,
                scene_name=args.scene_name,
                scene_items=scene_items,
                source_name=source_name,
                enabled=False,
            )
            if fallback_result is not None:
                item_results.append(fallback_result)
        browser_source = await refresh_browser_source(client, source_name=args.bilibili_source)
        virtual_camera_before = await client.request("GetVirtualCamStatus")
        if not virtual_camera_before.get("outputActive"):
            await client.request("StartVirtualCam")
        virtual_camera_after = await client.request("GetVirtualCamStatus")
        screenshot_path = ""
        if args.screenshot_path:
            screenshot_path = str(Path(args.screenshot_path).expanduser())
            await client.request(
                "SaveSourceScreenshot",
                {
                    "sourceName": args.scene_name,
                    "imageFormat": "jpg",
                    "imageFilePath": screenshot_path,
                    "imageWidth": args.screenshot_width,
                    "imageHeight": args.screenshot_height,
                },
            )
        return {
            "event": "obs_yogacoach_source_activated",
            "obs_version": version.get("obsVersion"),
            "obs_websocket_version": version.get("obsWebSocketVersion"),
            "scene_name": args.scene_name,
            "browser_source": browser_source,
            "scene_item_results": item_results,
            "virtual_camera_before": virtual_camera_before,
            "virtual_camera_after": virtual_camera_after,
            "screenshot_path": screenshot_path,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Activate the OBS YogaCoach Bilibili reference scene and virtual camera.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--password")
    parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--scene-name", default=DEFAULT_SCENE_NAME)
    parser.add_argument("--bilibili-source", default=DEFAULT_BILIBILI_SOURCE)
    parser.add_argument(
        "--fallback-source",
        action="append",
        default=list(DEFAULT_FALLBACK_SOURCES),
    )
    parser.add_argument("--screenshot-path", default="")
    parser.add_argument("--screenshot-width", type=int, default=640)
    parser.add_argument("--screenshot-height", type=int, default=360)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(activate_yogacoach_source(args))
    emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
