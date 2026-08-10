from app.db.database import Base, engine

# Importar todos los modelos para que SQLAlchemy los registre
from app.models.user import User

def init_db():
    Base.metadata.create_all(bind=engine)

from app.db.database import Base, engine

# Importar todos los modelos para que SQLAlchemy los registre
from app.models.user import User
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.agent_event import AgentEvent


def init_db():
    Base.metadata.create_all(bind=engine)
