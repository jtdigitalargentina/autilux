from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from langfuse import get_client
from sqlalchemy.orm import Session

from app.core.security import get_current_username
from app.integrations.kimi.client import research_company
from app.db.session import get_db
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.schemas.agent_run import AgentRunCreate, AgentRunRead


router = APIRouter(
    prefix="/agent-runs",
    tags=["Agent Runs"],
)


@router.post("", response_model=AgentRunRead)
def create_agent_run(
    payload: AgentRunCreate,
    current_username: str = Depends(get_current_username),
    db: Session = Depends(get_db),
):
    agent = db.get(Agent, payload.agent_id)

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Agent not found",
        )

    if not agent.enabled:
        raise HTTPException(
            status_code=409,
            detail="Agent is disabled",
        )

    run = AgentRun(
        agent_id=agent.id,
        status="running",
        input_data=payload.input_data,
        started_at=datetime.now(timezone.utc),
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    langfuse = get_client()

    try:
        with langfuse.start_as_current_observation(
            as_type="span",
            name=f"agent-run:{agent.name}",
            input={
                "agent_run_id": run.id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "agent_type": agent.agent_type,
                "input_data": payload.input_data,
            },
            metadata={
                "service": "autilux-api",
                "agent_run_id": run.id,
                "agent_id": agent.id,
                "requested_by": current_username,
            },
        ) as observation:
            if agent.name == "company-research":
                output = research_company(payload.input_data)
            else:
                output = {
                    "message": "Agent runtime executed successfully",
                    "agent": agent.name,
                    "agent_run_id": run.id,
                }

            observation.update(output=output)

            run.status = "completed"
            run.output_data = output
            run.finished_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(run)

        langfuse.flush()

        return run

    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(run)

        raise HTTPException(
            status_code=500,
            detail="Agent run failed",
        )
