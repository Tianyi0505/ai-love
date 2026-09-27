from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request

from plugin_runtime.contracts import PluginCommand, PluginError
from plugin_runtime.control import PluginControlClient

from ..auth.router import require_session

router = APIRouter(prefix="/ai-love-api/plugins", tags=["plugins"], dependencies=[Depends(require_session)])


class HostCommand(PluginCommand):
    host: str


async def same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (
        origin and urlsplit(origin).netloc != request.headers.get("host")
    ):
        raise HTTPException(403, "插件操作必须从当前管理页面提交")


def client(request: Request) -> PluginControlClient:
    control = getattr(request.app.state, "plugin_control", None)
    if control is None:
        raise HTTPException(503, "插件控制面尚未连接")
    return control


Control = Annotated[PluginControlClient, Depends(client)]


async def invoke(control, host: str, method: str, **data):
    try:
        return await control.call(host, method, **data)
    except PluginError as exc:
        status = {"not_found": 404, "invalid": 422, "unavailable": 503}.get(exc.code, 409)
        raise HTTPException(status, str(exc)) from exc
    except Exception as exc:
        # A timeout can happen after acceptance. Clients must reuse the operation ID.
        raise HTTPException(503, "宿主暂时无法响应；操作结果可能尚未返回，请刷新或使用原操作标识重试") from exc


@router.get("")
async def list_plugins(control: Control):
    return await control.list_hosts()


@router.post("/preflight", dependencies=[Depends(same_origin)])
async def preflight(payload: HostCommand, control: Control):
    return await invoke(control, payload.host, "preflight", command=payload.model_dump(exclude={"host"}))


@router.post("/operations", status_code=202, dependencies=[Depends(same_origin)])
async def operate(payload: HostCommand, control: Control):
    return await invoke(control, payload.host, "submit", command=payload.model_dump(exclude={"host"}))


@router.get("/operations/{host}/{operation_id}")
async def operation(host: str, operation_id: str, control: Control):
    return await invoke(control, host, "operation", operation_id=operation_id)


@router.post("/hosts/{host}/refresh", dependencies=[Depends(same_origin)])
async def refresh(host: str, control: Control):
    return await invoke(control, host, "refresh")
