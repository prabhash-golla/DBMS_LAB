import psycopg2
from werkzeug.security import generate_password_hash
from database.db_config import get_db_connection

# User details
username = "admin"
email = "dbms@gmail.com"
password = "admin"
role_id = 1 

# Hash the password
hashed_password = generate_password_hash(password)

# Insert into database
try:
    conn = get_db_connection()
    cur = conn.cursor()
    
    insert_query = """
    INSERT INTO users (username, email, password_hash, role_id)
    VALUES (%s, %s, %s, %s)
    RETURNING user_id;
    """
    
    cur.execute(insert_query, (username, email, hashed_password, role_id))
    user_id = cur.fetchone()[0]  # Fetch the newly inserted user's ID

    conn.commit()
    print(f"User inserted with ID: {user_id}")

except psycopg2.Error as e:
    print(f"Error inserting user: {e}")
finally:
    cur.close()
    conn.close()