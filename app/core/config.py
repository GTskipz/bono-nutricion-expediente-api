from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:admin123@localhost:5432/MIS"

    class Config:
        env_file = ".env"

settings = Settings()
