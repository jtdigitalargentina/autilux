from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Autilux API"
    VERSION: str = "0.1.0"

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    DATABASE_URL: str

    TWENTY_URL: str = ""
    TWENTY_API_KEY: str = ""

    OPENAI_API_KEY: str = ""
    KIMI_API_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
