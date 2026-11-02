
from database import get_connection
from werkzeug.security import generate_password_hash
from getpass import getpass

name = input("Enter Admin Name: ")
email = input("Enter Admin Email: ")
password = getpass("Enter Admin Password: ")

if len(password) < 8:
    print("Password must contain at least 8 characters.")
else:
    conn = get_connection()

    try:
        conn.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, 'admin')
        """, (
            name,
            email,
            generate_password_hash(password)
        ))

        conn.commit()
        print("Admin Account Created Successfully!")

    except Exception:
        print("Admin email already exists or details are invalid.")

    finally:
        conn.close()
