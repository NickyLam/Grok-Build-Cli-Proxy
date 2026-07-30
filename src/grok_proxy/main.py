from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from grok_proxy import __version__
from grok_proxy.auth import verify_request_auth
from grok_proxy.bootstrap import bootstrap_settings
from grok_proxy.concurrency import ConcurrencyGate
from grok_proxy.config import Settings, cwd_is_allowed, get_settings, resolve_cwd
from grok_proxy.errors import ProxyError, http_exception_handler, proxy_error_handler
from grok_proxy.grok_runner import GrokResult, GrokRunOptions, GrokRunner, map_usage
from grok_proxy.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessageOut,
    Choice,
    GrokMeta,
    ModelCard,
    ModelList,
    Usage,
)
from grok_proxy.model_resolve import RuntimeModels, resolve_request_model, resolve_runtime_models
from grok_proxy.openai_sse import new_completion_id, stream_openai_sse
from grok_proxy.prompt_builder import build_prompt
from grok_proxy.session_store import SessionStore

logger = logging.getLogger("grok_proxy")


def create_app(
    settings: Settings | None = None,
    *,
    bootstrap: bool = True,
    install_workbuddy: bool | None = None,
    print_banner: bool = False,
    runtime_models: RuntimeModels | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = settings if settings is not None else get_settings()
        models_rt = runtime_models
        if bootstrap:
            # Auto-generate API key if missing; write client-config for WorkBuddy etc.
            # Banner is usually printed by CLI; uvicorn import path may print once.
            result = bootstrap_settings(
                cfg,
                install_workbuddy=install_workbuddy,
                print_banner=print_banner,
            )
            cfg = result.settings
            models_rt = result.runtime_models
        elif not cfg.api_key.strip():
            cfg.require_api_key()
        if models_rt is None:
            models_rt = resolve_runtime_models(
                configured_default=cfg.default_model,
                configured_models=cfg.models,
                grok_bin=cfg.grok_bin,
            )
            # Keep settings in sync when not full-bootstrapped (tests may pass fixed model)
            if cfg.default_model in ("", "auto", "grok-build", "default"):
                cfg.default_model = models_rt.default_model
        app.state.settings = cfg
        app.state.runtime_models = models_rt
        app.state.gate = ConcurrencyGate(cfg.max_concurrent)
        app.state.runner = GrokRunner(cfg.grok_bin)
        app.state.sessions = SessionStore()
        logger.info(
            "grok-proxy v%s host=%s port=%s max_concurrent=%s model=%s",
            __version__,
            cfg.host,
            cfg.port,
            cfg.max_concurrent,
            cfg.default_model,
        )
        yield

    app = FastAPI(
        title="Grok Build CLI Proxy",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_exception_handler(ProxyError, proxy_error_handler)
    from fastapi import HTTPException

    app.add_exception_handler(HTTPException, http_exception_handler)

    def get_cfg(request: Request) -> Settings:
        return request.app.state.settings

    def require_auth(request: Request, cfg: Settings = Depends(get_cfg)) -> None:
        verify_request_auth(request, cfg)

    def health_payload(request: Request) -> dict[str, Any]:
        gate: ConcurrencyGate = request.app.state.gate
        cfg: Settings = request.app.state.settings
        host = cfg.host if cfg.host not in ("0.0.0.0", "::") else "127.0.0.1"
        return {
            "status": "ok",
            "version": __version__,
            "in_flight": gate.in_flight,
            "max_concurrent": gate.limit,
            "default_model": cfg.default_model,
            "base_url": f"http://{host}:{cfg.port}/v1",
            "model_id": cfg.default_model,
            # api_key intentionally omitted from health (see /v1/connection with auth)
        }

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        return health_payload(request)

    @app.get("/v1/health")
    async def v1_health(request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
        return health_payload(request)

    @app.get("/v1/connection")
    async def connection_info(
        request: Request,
        _: None = Depends(require_auth),
        cfg: Settings = Depends(get_cfg),
    ) -> dict[str, Any]:
        """Return base_url / api_key / model_id for agent clients (auth required)."""
        host = cfg.host if cfg.host not in ("0.0.0.0", "::") else "127.0.0.1"
        base_url = f"http://{host}:{cfg.port}/v1"
        return {
            "base_url": base_url,
            "api_key": cfg.api_key,
            "model_id": cfg.default_model,
            "model": cfg.default_model,
            "models": cfg.model_ids(),
            "workbuddy": {
                "id": cfg.default_model,
                "name": cfg.default_model,
                "vendor": "Custom",
                "url": base_url,
                "apiKey": cfg.api_key,
                "supportsToolCall": False,
                "supportsImages": False,
                "supportsReasoning": False,
                "useCustomProtocol": False,
            },
            "openai_sdk": {
                "base_url": base_url,
                "api_key": cfg.api_key,
                "model": cfg.default_model,
            },
        }

    @app.get("/v1/models", response_model=ModelList)
    async def list_models(
        request: Request,
        _: None = Depends(require_auth),
        cfg: Settings = Depends(get_cfg),
    ) -> ModelList:
        runtime: RuntimeModels = request.app.state.runtime_models
        ids = runtime.available or cfg.model_ids()
        return ModelList(
            data=[ModelCard(id=mid, created=0) for mid in ids],
        )

    def _resolve_request_cwd(body: ChatCompletionRequest, cfg: Settings) -> str:
        raw = body.cwd or cfg.default_cwd
        path = resolve_cwd(raw)
        if not path.exists() or not path.is_dir():
            raise ProxyError(
                f"cwd does not exist or is not a directory: {path}",
                status_code=400,
                code="invalid_cwd",
            )
        if not cwd_is_allowed(path, cfg.cwd_allowlist):
            raise ProxyError(
                f"cwd not allowed by GROK_PROXY_CWD_ALLOWLIST: {path}",
                status_code=403,
                code="cwd_forbidden",
            )
        return str(path)

    def _merge_rules(from_prompt: str | None, from_body: str | None) -> str | None:
        parts = [p for p in (from_prompt, from_body) if p and p.strip()]
        if not parts:
            return None
        return "\n\n".join(parts)

    def _to_openai_response(
        result: GrokResult,
        *,
        model: str,
    ) -> ChatCompletionResponse:
        pt, ct, tt = map_usage(result.usage)
        return ChatCompletionResponse(
            id=new_completion_id(),
            created=int(time.time()),
            model=model,
            choices=[
                Choice(
                    message=ChatMessageOut(content=result.text),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=tt,
            ),
            grok=GrokMeta(
                session_id=result.session_id,
                stop_reason=result.stop_reason,
                num_turns=result.num_turns,
                request_id=result.request_id,
                raw_usage=result.usage,
                exit_code=result.exit_code,
            ),
        )

    def _build_run_options(
        body: ChatCompletionRequest,
        *,
        cfg: Settings,
        prompt: str,
        rules: str | None,
        cwd: str,
        stream: bool,
        runtime: RuntimeModels,
    ) -> GrokRunOptions:
        model = resolve_request_model(body.model or cfg.default_model, runtime)
        timeout = body.timeout_sec if body.timeout_sec is not None else cfg.default_timeout_sec
        return GrokRunOptions(
            prompt=prompt,
            model=model,
            cwd=cwd,
            stream=stream,
            session_id=body.session_id,
            always_approve=body.resolved_always_approve(cfg.always_approve),
            max_turns=body.max_turns,
            sandbox=body.sandbox,
            rules=rules,
            tools_allow=body.tools_allow,
            tools_deny=body.tools_deny,
            permission_mode=body.permission_mode,
            allow=body.allow,
            deny=body.deny,
            reasoning_effort=body.reasoning_effort,
            worktree=body.worktree,
            timeout_sec=timeout,
            grok_bin=cfg.grok_bin,
        )

    @app.post("/v1/chat/completions")
    async def chat_completions(
        body: ChatCompletionRequest,
        request: Request,
        _: None = Depends(require_auth),
        cfg: Settings = Depends(get_cfg),
    ):
        sessions: SessionStore = request.app.state.sessions
        runner: GrokRunner = request.app.state.runner
        gate: ConcurrencyGate = request.app.state.gate
        runtime: RuntimeModels = request.app.state.runtime_models

        cwd = _resolve_request_cwd(body, cfg)
        if body.session_id:
            sessions.check_cwd(body.session_id, cwd, strict=cfg.strict_session_cwd)

        prompt, sys_rules = build_prompt(body.messages, session_id=body.session_id)
        rules = _merge_rules(sys_rules, body.rules)
        model = resolve_request_model(body.model or cfg.default_model, runtime)

        logger.info(
            "chat.completions model=%s requested=%s cwd=%s stream=%s resume=%s prompt_chars=%s",
            model,
            body.model,
            cwd,
            body.stream,
            bool(body.session_id),
            len(prompt),
        )

        opts = _build_run_options(
            body,
            cfg=cfg,
            prompt=prompt,
            rules=rules,
            cwd=cwd,
            stream=body.stream,
            runtime=runtime,
        )

        if body.stream:
            await gate.acquire()

            async def event_source():
                try:
                    def on_session(sid: str | None) -> None:
                        if sid:
                            sessions.remember(sid, cwd)

                    include_usage = bool(
                        body.stream_options and body.stream_options.include_usage
                    )
                    async for line in stream_openai_sse(
                        runner.stream(opts),
                        model=model,
                        include_thoughts=body.include_thoughts,
                        include_usage=include_usage,
                        on_session=on_session,
                    ):
                        yield line
                finally:
                    await gate.release()

            return StreamingResponse(
                event_source(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        async with gate:
            result = await runner.run(opts)
        if result.session_id:
            sessions.remember(result.session_id, cwd)
        return JSONResponse(content=_to_openai_response(result, model=model).model_dump())

    return app


# Default app for `uvicorn grok_proxy.main:app`
app = create_app()
