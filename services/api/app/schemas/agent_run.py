from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AgentRunCreate(BaseModel):
    agent_id: int
    input_data: dict[str, Any] | None = None


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    status: str
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
