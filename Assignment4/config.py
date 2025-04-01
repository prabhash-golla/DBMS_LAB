import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret")
    DB_NAME = os.getenv("DB_NAME", "default-db")
    DB_USER = os.getenv("DB_USER", "default-user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "default-password")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")