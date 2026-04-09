#!/usr/bin/env python3
"""Mindscape wrapper around mlx_vlm.server with progress-aware watchdog state."""

from __future__ import annotations

import argparse
import contextvars
import functools
import importlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

import mlx.core as mx
import mlx.nn as nn
import uvicorn
from fastapi import Request
from mlx_lm.generate import maybe_quantize_kv_cache
from mlx_lm.sample_utils import make_logits_processors, make_sampler

import mlx_vlm.server as base_server

vlm_generate = importlib.import_module("mlx_vlm.generate")


_REQUEST_CONTEXT: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "mindscape_mlx_request_context",
    default={},
)
_PROGRESS_TRACKER: contextvars.ContextVar["ProgressTracker | None"] = contextvars.ContextVar(
    "mindscape_mlx_progress_tracker",
    default=None,
)

_WATCHDOG_STATE_DIR = Path(
    os.getenv(
        "MLX_WATCHDOG_STATE_DIR",
        str(Path(__file__).resolve().parents[2] / "logs" / "mlx-watchdog"),
    )
)
_WATCHDOG_STATE_FILE = _WATCHDOG_STATE_DIR / "inflight_request.json"

_PREFILL_PROGRESS_MIN_INTERVAL_SECONDS = max(
    0.5,
    float(os.getenv("MLX_PROGRESS_PREFILL_INTERVAL_SECONDS", "1.5")),
)
_TOKEN_PROGRESS_MIN_INTERVAL_SECONDS = max(
    0.5,
    float(os.getenv("MLX_PROGRESS_TOKEN_INTERVAL_SECONDS", "2.0")),
)
_TOKEN_PROGRESS_INTERVAL = max(
    1,
    int(os.getenv("MLX_PROGRESS_TOKEN_INTERVAL", "16")),
)

_PROGRESS_REQUEST_ID_HEADER = "x-mlx-request-id"
_PROGRESS_REFERENCE_ID_HEADER = "x-mlx-reference-id"
_PROGRESS_PROFILE_HEADER = "x-mlx-analysis-profile"
_PROGRESS_MODEL_HEADER = "x-mlx-model-id"
_PROGRESS_PAYLOAD_COUNT_HEADER = "x-mlx-image-payload-count"
_PROGRESS_PAYLOAD_BYTES_HEADER = "x-mlx-image-payload-bytes"

_ORIGINAL_GENERATE = base_server.generate
_ORIGINAL_GENERATE_STEP = vlm_generate.generate_step
_ORIGINAL_GET_CACHED_MODEL = base_server.get_cached_model


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _write_watchdog_state(payload: Dict[str, Any]) -> None:
    _WATCHDOG_STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _WATCHDOG_STATE_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    tmp_path.replace(_WATCHDOG_STATE_FILE)


def _clear_watchdog_state(request_id: str) -> None:
    try:
        if not _WATCHDOG_STATE_FILE.exists():
            return
        payload = json.loads(_WATCHDOG_STATE_FILE.read_text(encoding="utf-8"))
        if request_id and str(payload.get("request_id") or "") != request_id:
            return
        _WATCHDOG_STATE_FILE.unlink(missing_ok=True)
    except Exception:
        return


class ProgressTracker:
    def __init__(self, metadata: Dict[str, Any]) -> None:
        now = time.time()
        self.request_id = str(metadata.get("request_id") or f"mlxsrv_{int(now * 1000)}")
        self.reference_id = str(metadata.get("reference_id") or "")
        self.analysis_profile = str(metadata.get("analysis_profile") or "unknown")
        self.model_id = str(metadata.get("model_id") or "")
        self.image_payload_count = _safe_int(metadata.get("image_payload_count"))
        self.image_payload_total_bytes = _safe_int(
            metadata.get("image_payload_total_bytes")
        )
        self.started_at_epoch = float(metadata.get("started_at_epoch") or now)
        self.current_phase = ""
        self.phase_seq = 0
        self.progress_seq = 0
        self.phase_entered_at_epoch = self.started_at_epoch
        self.last_prefill_emit_at_epoch = 0.0
        self.last_token_emit_at_epoch = 0.0
        self.prompt_tokens = 0
        self.prefill_total_tokens = 0
        self.prefill_tokens_processed = 0
        self.generation_tokens = 0

    def bind_model(self, model_id: str) -> None:
        if model_id:
            self.model_id = str(model_id)

    def emit(
        self,
        *,
        phase: str,
        kind: str,
        prompt_tokens: Optional[int] = None,
        prefill_total_tokens: Optional[int] = None,
        prefill_tokens_processed: Optional[int] = None,
        generation_tokens: Optional[int] = None,
        prompt_tps: Optional[float] = None,
        generation_tps: Optional[float] = None,
        peak_memory_gb: Optional[float] = None,
        force: bool = False,
        error: str = "",
    ) -> None:
        now = time.time()
        if phase != self.current_phase:
            self.current_phase = phase
            self.phase_seq += 1
            self.phase_entered_at_epoch = now

        if prompt_tokens is not None:
            self.prompt_tokens = int(prompt_tokens)
        if prefill_total_tokens is not None:
            self.prefill_total_tokens = int(prefill_total_tokens)
        if prefill_tokens_processed is not None:
            self.prefill_tokens_processed = int(prefill_tokens_processed)
        if generation_tokens is not None:
            self.generation_tokens = int(generation_tokens)

        self.progress_seq += 1
        payload: Dict[str, Any] = {
            "status": "active",
            "source": "mlx_server_progress",
            "request_id": self.request_id,
            "reference_id": self.reference_id,
            "analysis_profile": self.analysis_profile,
            "model_id": self.model_id,
            "started_at_epoch": self.started_at_epoch,
            "heartbeat_at_epoch": now,
            "progress_at_epoch": now,
            "progress_kind": kind,
            "progress_phase": self.current_phase,
            "phase_seq": self.phase_seq,
            "progress_seq": self.progress_seq,
            "phase_entered_at_epoch": self.phase_entered_at_epoch,
            "prompt_tokens": self.prompt_tokens,
            "prefill_total_tokens": self.prefill_total_tokens,
            "prefill_tokens_processed": self.prefill_tokens_processed,
            "generation_tokens": self.generation_tokens,
            "image_payload_count": self.image_payload_count,
            "image_payload_total_bytes": self.image_payload_total_bytes,
        }
        if prompt_tps is not None:
            payload["prompt_tps"] = round(float(prompt_tps), 4)
        if generation_tps is not None:
            payload["generation_tps"] = round(float(generation_tps), 4)
        if peak_memory_gb is not None:
            payload["peak_memory_gb"] = round(float(peak_memory_gb), 4)
        if error:
            payload["error"] = error[:500]
        _write_watchdog_state(payload)

        if force and kind == "prefill":
            self.last_prefill_emit_at_epoch = now
        if force and kind == "token":
            self.last_token_emit_at_epoch = now

    def maybe_emit_prefill(
        self,
        *,
        prompt_tokens: int,
        prefill_total_tokens: int,
        prefill_tokens_processed: int,
    ) -> None:
        now = time.time()
        should_emit = (
            prefill_tokens_processed >= prefill_total_tokens
            or (now - self.last_prefill_emit_at_epoch) >= _PREFILL_PROGRESS_MIN_INTERVAL_SECONDS
        )
        if not should_emit:
            return
        self.last_prefill_emit_at_epoch = now
        self.emit(
            phase="prefill",
            kind="prefill",
            prompt_tokens=prompt_tokens,
            prefill_total_tokens=prefill_total_tokens,
            prefill_tokens_processed=prefill_tokens_processed,
            force=True,
        )

    def maybe_emit_generation(
        self,
        *,
        prompt_tokens: int,
        generation_tokens: int,
        prompt_tps: float,
        generation_tps: float,
        peak_memory_gb: float,
        force: bool = False,
    ) -> None:
        now = time.time()
        should_emit = force or generation_tokens <= 1 or generation_tokens % _TOKEN_PROGRESS_INTERVAL == 0
        if not should_emit and (now - self.last_token_emit_at_epoch) < _TOKEN_PROGRESS_MIN_INTERVAL_SECONDS:
            return
        self.last_token_emit_at_epoch = now
        self.emit(
            phase="generating",
            kind="token",
            prompt_tokens=prompt_tokens,
            generation_tokens=generation_tokens,
            prompt_tps=prompt_tps,
            generation_tps=generation_tps,
            peak_memory_gb=peak_memory_gb,
            force=True,
        )

    def clear(self) -> None:
        _clear_watchdog_state(self.request_id)


def _current_tracker() -> ProgressTracker | None:
    return _PROGRESS_TRACKER.get()


def _extract_request_context(request: Request) -> Dict[str, Any]:
    headers = request.headers
    return {
        "request_id": headers.get(_PROGRESS_REQUEST_ID_HEADER, "").strip(),
        "reference_id": headers.get(_PROGRESS_REFERENCE_ID_HEADER, "").strip(),
        "analysis_profile": headers.get(_PROGRESS_PROFILE_HEADER, "").strip(),
        "model_id": headers.get(_PROGRESS_MODEL_HEADER, "").strip(),
        "image_payload_count": _safe_int(headers.get(_PROGRESS_PAYLOAD_COUNT_HEADER)),
        "image_payload_total_bytes": _safe_int(headers.get(_PROGRESS_PAYLOAD_BYTES_HEADER)),
        "started_at_epoch": time.time(),
    }


def _patched_generate_step(
    input_ids: mx.array,
    model: nn.Module,
    pixel_values,
    mask,
    *,
    max_tokens: int = 256,
    temperature: float = 0.0,
    repetition_penalty: Optional[float] = None,
    repetition_context_size: Optional[int] = 20,
    top_p: float = 1.0,
    logit_bias: Optional[Dict[int, float]] = None,
    prompt_cache: Optional[List[Any]] = None,
    max_kv_size: Optional[int] = None,
    kv_bits: Optional[int] = None,
    kv_group_size: int = 64,
    quantized_kv_start: int = 0,
    sampler: Optional[Callable[[mx.array], mx.array]] = None,
    logits_processors: Optional[List[Callable[[mx.array, mx.array], mx.array]]] = None,
    prefill_step_size: Optional[int] = vlm_generate.DEFAULT_PREFILL_STEP_SIZE,
    **kwargs,
) -> Generator[Tuple[mx.array, mx.array], None, None]:
    tracker = _current_tracker()
    if tracker is None:
        yield from _ORIGINAL_GENERATE_STEP(
            input_ids,
            model,
            pixel_values,
            mask,
            max_tokens=max_tokens,
            temperature=temperature,
            repetition_penalty=repetition_penalty,
            repetition_context_size=repetition_context_size,
            top_p=top_p,
            logit_bias=logit_bias,
            prompt_cache=prompt_cache,
            max_kv_size=max_kv_size,
            kv_bits=kv_bits,
            kv_group_size=kv_group_size,
            quantized_kv_start=quantized_kv_start,
            sampler=sampler,
            logits_processors=logits_processors,
            prefill_step_size=prefill_step_size,
            **kwargs,
        )
        return

    quantize_cache_fn = functools.partial(
        maybe_quantize_kv_cache,
        quantized_kv_start=quantized_kv_start,
        kv_group_size=kv_group_size,
        kv_bits=kv_bits,
    )

    if sampler is None:
        sampler = make_sampler(temperature, top_p)

    processors = make_logits_processors(
        logit_bias, repetition_penalty, repetition_context_size
    )
    if logits_processors is not None:
        processors.extend(logits_processors)

    y = input_ids
    tokens = mx.array([], dtype=input_ids.dtype)
    prompt_token_count = int(input_ids.size)
    thinking_budget_criteria = kwargs.pop("thinking_budget_criteria", None)

    if prompt_cache is None:
        prompt_cache = vlm_generate.cache.make_prompt_cache(
            model.language_model,
            max_kv_size=max_kv_size,
        )

    def _step(y, inputs_embeds=None):
        nonlocal tokens, kwargs

        with mx.stream(vlm_generate.generation_stream):
            if "decoder_input_ids" in kwargs:
                outputs = model.language_model(
                    cache=prompt_cache,
                    **kwargs,
                )
            else:
                outputs = model.language_model(
                    y,
                    inputs_embeds=inputs_embeds,
                    cache=prompt_cache,
                    **kwargs,
                )

            logits = outputs.logits[:, -1, :]

            if len(processors) > 0 and len(y) > 0:
                tokens = mx.concat([tokens, y.flatten()])

                for processor in processors:
                    logits = processor(tokens, logits)

            quantize_cache_fn(prompt_cache)

            logprobs = logits - mx.logsumexp(logits)
            y = sampler(logprobs)

            if outputs.cross_attention_states is not None:
                kwargs = {"cross_attention_states": outputs.cross_attention_states}
            elif outputs.encoder_outputs is not None:
                kwargs = {"encoder_outputs": outputs.encoder_outputs}
            else:
                kwargs = {}

            return y, logprobs.squeeze(0)

    with mx.stream(vlm_generate.generation_stream):
        tracker.emit(
            phase="embedding",
            kind="phase",
            prompt_tokens=prompt_token_count,
            force=True,
        )

        embedding_output = model.get_input_embeddings(
            input_ids, pixel_values, mask=mask, **kwargs
        )

        inputs_embeds = embedding_output.inputs_embeds
        prefill_total_tokens = int(inputs_embeds.shape[1])

        kwargs.update(
            {
                k: v
                for k, v in embedding_output.to_dict().items()
                if k != "inputs_embeds" and v is not None
            }
        )
        tracker.emit(
            phase="prefill",
            kind="phase",
            prompt_tokens=prompt_token_count,
            prefill_total_tokens=prefill_total_tokens,
            prefill_tokens_processed=0,
            force=True,
        )

        if prefill_step_size is not None and inputs_embeds.shape[1] > prefill_step_size:
            processed_tokens = 0
            while inputs_embeds.shape[1] > 1:
                n_to_process = min(prefill_step_size, inputs_embeds.shape[1] - 1)
                model.language_model(
                    inputs=input_ids[:, :n_to_process],
                    inputs_embeds=inputs_embeds[:, :n_to_process],
                    cache=prompt_cache,
                    n_to_process=n_to_process,
                    **kwargs,
                )
                quantize_cache_fn(prompt_cache)
                mx.eval([c.state for c in prompt_cache])
                inputs_embeds = inputs_embeds[:, n_to_process:]
                input_ids = input_ids[:, n_to_process:]
                processed_tokens += n_to_process
                mx.clear_cache()
                tracker.maybe_emit_prefill(
                    prompt_tokens=prompt_token_count,
                    prefill_total_tokens=prefill_total_tokens,
                    prefill_tokens_processed=processed_tokens,
                )

            input_ids = input_ids[:, -1:]

        y, logprobs = _step(input_ids, inputs_embeds=inputs_embeds)
        tracker.emit(
            phase="decode_ready",
            kind="phase",
            prompt_tokens=prompt_token_count,
            prefill_total_tokens=prefill_total_tokens,
            prefill_tokens_processed=prefill_total_tokens,
            force=True,
        )

    mx.async_eval(y)

    n = 0
    while True:
        if n != max_tokens:
            next_y, next_logprobs = _step(y[None])
            mx.async_eval(next_y)
        if n == 0:
            mx.eval(y)
        if n == max_tokens:
            break

        generation_tokens = n + 1
        tracker.maybe_emit_generation(
            prompt_tokens=prompt_token_count,
            generation_tokens=generation_tokens,
            prompt_tps=0.0,
            generation_tps=0.0,
            peak_memory_gb=mx.get_peak_memory() / 1e9,
            force=generation_tokens == 1,
        )
        yield y.item(), logprobs
        if n % 256 == 0:
            mx.clear_cache()

        if thinking_budget_criteria is not None:
            next_y = thinking_budget_criteria.apply_forced_token(next_y)
        y, logprobs = next_y, next_logprobs
        n += 1


def _patched_generate(
    model: nn.Module,
    processor,
    prompt: str,
    image=None,
    audio=None,
    verbose: bool = False,
    **kwargs,
) -> vlm_generate.GenerationResult:
    tracker = _current_tracker()
    if tracker is None:
        return _ORIGINAL_GENERATE(
            model,
            processor,
            prompt,
            image=image,
            audio=audio,
            verbose=verbose,
            **kwargs,
        )

    text = ""
    last_response = None
    tokenizer = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    eos_tokens = kwargs.get("eos_tokens", None)
    stopping_criteria = kwargs.get("stopping_criteria", None)

    if eos_tokens is not None:
        tokenizer.stopping_criteria.add_eos_token_ids(eos_tokens)
    elif stopping_criteria is not None:
        if isinstance(stopping_criteria, vlm_generate.StoppingCriteria) or callable(
            stopping_criteria
        ):
            tokenizer.stopping_criteria = stopping_criteria
        else:
            raise ValueError(
                "stopping_criteria must be an instance of StoppingCriteria or a callable"
            )
    else:
        tokenizer.stopping_criteria.reset(model.config.eos_token_id)

    try:
        for response in vlm_generate.stream_generate(
            model,
            processor,
            prompt,
            image,
            audio,
            **kwargs,
        ):
            if verbose:
                print(response.text, end="", flush=True)
            text += response.text
            last_response = response

        if last_response is None:
            tracker.emit(
                phase="completed",
                kind="phase",
                prompt_tokens=0,
                generation_tokens=0,
                force=True,
            )
            tracker.clear()
            return vlm_generate.GenerationResult(
                text="",
                token=None,
                logprobs=None,
                prompt_tokens=0,
                generation_tokens=0,
                total_tokens=0,
                prompt_tps=0.0,
                generation_tps=0.0,
                peak_memory=mx.get_peak_memory() / 1e9,
            )

        tracker.emit(
            phase="completed",
            kind="phase",
            prompt_tokens=last_response.prompt_tokens,
            generation_tokens=last_response.generation_tokens,
            prompt_tps=last_response.prompt_tps,
            generation_tps=last_response.generation_tps,
            peak_memory_gb=last_response.peak_memory,
            force=True,
        )
        tracker.clear()
        return vlm_generate.GenerationResult(
            text=text,
            token=last_response.token,
            logprobs=last_response.logprobs,
            prompt_tokens=last_response.prompt_tokens,
            generation_tokens=last_response.generation_tokens,
            total_tokens=last_response.total_tokens,
            prompt_tps=last_response.prompt_tps,
            generation_tps=last_response.generation_tps,
            peak_memory=last_response.peak_memory,
        )
    except Exception as exc:
        tracker.emit(
            phase="failed",
            kind="phase",
            error=str(exc),
            force=True,
        )
        tracker.clear()
        raise


def _patched_get_cached_model(model_name: str, adapter_path: Optional[str]):
    tracker = _current_tracker()
    if tracker is None:
        return _ORIGINAL_GET_CACHED_MODEL(model_name, adapter_path)

    tracker.bind_model(model_name)
    tracker.emit(
        phase="model_loading",
        kind="phase",
        force=True,
    )
    result = _ORIGINAL_GET_CACHED_MODEL(model_name, adapter_path)
    tracker.emit(
        phase="model_ready",
        kind="phase",
        force=True,
    )
    return result


def _install_patches() -> None:
    if getattr(base_server.app.state, "mindscape_progress_patch_installed", False):
        return

    @base_server.app.middleware("http")
    async def _mindscape_progress_context(request: Request, call_next):
        if request.url.path not in {"/chat/completions", "/v1/chat/completions"}:
            return await call_next(request)

        context_payload = _extract_request_context(request)
        request_token = _REQUEST_CONTEXT.set(context_payload)
        tracker = ProgressTracker(context_payload)
        tracker_token = _PROGRESS_TRACKER.set(tracker)
        tracker.emit(phase="accepted", kind="phase", force=True)
        try:
            return await call_next(request)
        finally:
            _PROGRESS_TRACKER.reset(tracker_token)
            _REQUEST_CONTEXT.reset(request_token)

    base_server.generate = _patched_generate
    base_server.get_cached_model = _patched_get_cached_model
    vlm_generate.generate_step = _patched_generate_step
    base_server.app.state.mindscape_progress_patch_installed = True


_install_patches()
app = base_server.app


def main() -> None:
    parser = argparse.ArgumentParser(description="Mindscape MLX VLM HTTP server.")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument(
        "--prefill-step-size",
        type=int,
        default=vlm_generate.DEFAULT_PREFILL_STEP_SIZE,
    )
    parser.add_argument("--kv-bits", type=int, default=0)
    parser.add_argument("--kv-group-size", type=int, default=64)
    parser.add_argument("--max-kv-size", type=int, default=0)
    parser.add_argument(
        "--quantized-kv-start",
        type=int,
        default=vlm_generate.DEFAULT_QUANTIZED_KV_START,
    )
    args = parser.parse_args()

    if args.trust_remote_code:
        os.environ["MLX_TRUST_REMOTE_CODE"] = "true"
    os.environ["PREFILL_STEP_SIZE"] = str(args.prefill_step_size)
    os.environ["KV_BITS"] = str(args.kv_bits)
    os.environ["KV_GROUP_SIZE"] = str(args.kv_group_size)
    os.environ["MAX_KV_SIZE"] = str(args.max_kv_size)
    os.environ["QUANTIZED_KV_START"] = str(args.quantized_kv_start)

    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
