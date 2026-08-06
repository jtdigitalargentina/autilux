from app.db.database import Base, engine

# Importar todos los modelos para que SQLAlchemy los registre
from app.models.user import User

def init_db():
    Base.metadata.create_all(bind=engine)

