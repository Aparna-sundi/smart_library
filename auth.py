
import email
from unicodedata import name

from flask import Blueprint, render_template, request
from flask import redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from database import get_connection

auth = Blueprint("auth", __name__)


# Student Registration
@auth.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or not email or not password:
            flash("All fields are required.")
            return redirect(url_for("auth.register"))

        hashed_password = generate_password_hash(password)

        conn = get_connection()

        try:
            conn.execute(
                """
                INSERT INTO users (name, email, password, role)
                VALUES (?, ?, ?, 'student')
                """,
                (name, email, hashed_password),
            )
            conn.commit()
            flash("Registration successful! Please login.")
            return redirect(url_for("auth.login"))
        except Exception:
            flash("Email already registered or invalid details.")
        finally:
            conn.close()

    return render_template("register.html")


# Login for Admin and Student
@auth.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()

        user = conn.execute("""
            SELECT * FROM users WHERE email = ?
        """, (email,)).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"], password
        ):

            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            
            print("LOGIN SESSION:", dict(session))

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


# Logout
@auth.route("/logout")
def logout():

    session.clear()
    flash("You have logged out successfully.")

    return redirect(url_for("auth.login"))
