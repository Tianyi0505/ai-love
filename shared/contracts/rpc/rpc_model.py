from pydantic import BaseModel, ConfigDict


class RpcModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SuccessResponse(RpcModel):
    ok: bool = True
