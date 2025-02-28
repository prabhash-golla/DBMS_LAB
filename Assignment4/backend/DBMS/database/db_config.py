import psycopg2
from config import Config

def get_db_connection():
    conn = psycopg2.connect(
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        host=Config.DB_HOST,
        port=Config.DB_PORT
    )
    conn.autocommit = True
    return conn

def get_db_cursor():
    conn = get_db_connection()
    return conn, conn.cursor()

def close_db_connection(conn, cur):
    if cur:
        cur.close()
    if conn:
        conn.close()