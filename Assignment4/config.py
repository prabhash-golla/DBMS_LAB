import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'team-titans'
    DB_NAME = os.environ.get('DB_NAME') or '22CS30027'
    DB_USER = os.environ.get('DB_USER') or '22CS30027'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or '5243y6!J'
    DB_HOST = os.environ.get('DB_HOST') or '10.5.18.72'
    DB_PORT = os.environ.get('DB_PORT') or '5432'