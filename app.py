from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from flask import send_file
import qrcode
import os
from flask import Flask, render_template, session
from flask import redirect, url_for, flash, request
from functools import wraps
import sqlite3
from datetime import date, timedelta

from auth import auth
from database import get_connection, create_tables


# Create Flask Application
app = Flask(__name__)

create_tables()

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "smart-library-development-key-change-before-deployment"
)
app.config["APP_BASE_URL"] = os.environ.get(
    "APP_BASE_URL",
    "http://127.0.0.1:5000"
)

app.register_blueprint(auth)


# Generate QR Codes for a single book
def generate_book_qr(book_id):

    qr_folder = os.path.join("static", "qr_codes")
    os.makedirs(qr_folder, exist_ok=True)
    base_url = app.config.get("APP_BASE_URL", "http://127.0.0.1:5000")
    book_url = f"{base_url}/student/book/{book_id}"
    qr = qrcode.make(book_url)
    qr_path = os.path.join(qr_folder, f"book_{book_id}.png")
    qr.save(qr_path)


# Generate QR Codes for All Books
def generate_all_book_qr():

    conn = get_connection()

    books = conn.execute(
        "SELECT id FROM books"
    ).fetchall()

    conn.close()

    for book in books:
        generate_book_qr(book["id"])

    print("QR Codes Generated for All Books!")


# Role-based security
def role_required(role):

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):

            if "user_id" not in session:
                flash("Please login first.")
                return redirect(url_for("auth.login"))

            if session.get("role") != role:
                flash("Unauthorized access.")
                return redirect(url_for("home"))

            return function(*args, **kwargs)

        return wrapper

    return decorator


# Home page
@app.route("/")
def home():
    return render_template("index.html")


# Admin Dashboard
@app.route("/admin")
@role_required("admin")
def admin_dashboard():

    conn = get_connection()

    total_books = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM books"
    ).fetchone()[0]

    available_books = conn.execute(
        "SELECT COALESCE(SUM(available), 0) FROM books"
    ).fetchone()[0]

    total_students = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role='student'"
    ).fetchone()[0]

    issued_books = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE status='issued'"
    ).fetchone()[0]

    books = conn.execute(
        "SELECT * FROM books ORDER BY id DESC"
    ).fetchall()

    pending_requests = conn.execute(
        "SELECT COUNT(*) FROM borrow_requests WHERE status='pending'"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        available_books=available_books,
        total_students=total_students,
        issued_books=issued_books,
        pending_requests=pending_requests,
        books=books
    )


# Add New Book
@app.route("/admin/books/add", methods=["GET", "POST"])
@role_required("admin")
def add_book():

    if request.method == "POST":

        title = request.form["title"].strip()
        author = request.form["author"].strip()
        category = request.form["category"].strip()
        isbn = request.form["isbn"].strip() or None
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()

        conn = None

        try:
            quantity = int(request.form["quantity"])

            if not title or not author or quantity < 1:
                flash("Enter valid book details.")
                return redirect(url_for("add_book"))

            conn = get_connection()

            conn.execute("""
                INSERT INTO books
                (title, author, category, isbn, quantity,
                 available, description, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, author, category, isbn,
                quantity, quantity, description, image_url
            ))

            conn.commit()

            flash("Book added successfully!")
            return redirect(url_for("admin_dashboard"))

        except ValueError:
            flash("Quantity must be a valid positive number.")

        except sqlite3.IntegrityError:
            flash("This ISBN already exists.")

        except sqlite3.OperationalError:
            flash("Database is busy. Please try again.")

        finally:
            if conn is not None:
                conn.close()

    return render_template("add_book.html")

# Search Books
@app.route("/admin/search")
@role_required("admin")
def search_books():

    keyword = request.args.get("q", "").strip()

    conn = get_connection()

    books = conn.execute("""
        SELECT * FROM books
        WHERE title LIKE ? OR author LIKE ?
        ORDER BY title
    """, (
        f"%{keyword}%",
        f"%{keyword}%"
    )).fetchall()

    conn.close()

    return render_template(
        "search_books.html",
        books=books,
        keyword=keyword
    )


# Edit Book
@app.route("/admin/books/edit/<int:book_id>",
           methods=["GET", "POST"])
@role_required("admin")
def edit_book(book_id):

    conn = get_connection()

    book = conn.execute(
        "SELECT * FROM books WHERE id=?",
        (book_id,)
    ).fetchone()

    if book is None:
        conn.close()
        flash("Book not found.")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":

        title = request.form["title"].strip()
        author = request.form["author"].strip()
        category = request.form["category"].strip()
        isbn = request.form["isbn"].strip() or None
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()

        try:
            quantity = int(request.form["quantity"])

            issued = conn.execute("""
                SELECT COUNT(*) FROM transactions
                WHERE book_id=? AND status='issued'
            """, (book_id,)).fetchone()[0]

            if not title or not author or quantity < 1:
                flash("Enter valid book details.")

            elif quantity < issued:
                flash("Quantity cannot be less than currently issued copies.")

            else:
                available = quantity - issued

                conn.execute("""
                    UPDATE books
                    SET title=?, author=?, category=?,
                        isbn=?, quantity=?, available=?,
                        description=?, image_url=?
                    WHERE id=?
                """, (
                    title, author, category,
                    isbn, quantity, available,
                    description, image_url, book_id
                ))

                conn.commit()
                conn.close()

                flash("Book updated successfully!")
                return redirect(url_for("admin_dashboard"))

        except ValueError:
            flash("Enter a valid quantity.")

        except sqlite3.IntegrityError:
            flash("This ISBN already exists.")

    conn.close()

    return render_template("edit_book.html", book=book)


# Delete Book
@app.route("/admin/books/delete/<int:book_id>",
           methods=["POST"])
@role_required("admin")
def delete_book(book_id):

    conn = get_connection()

    try:
        conn.execute(
            "DELETE FROM books WHERE id=?",
            (book_id,)
        )

        conn.commit()
        flash("Book deleted successfully!")

    except sqlite3.IntegrityError:
        flash("Cannot delete this book because it has library records.")

    finally:
        conn.close()

    return redirect(url_for("admin_dashboard"))


# View Students
@app.route("/admin/students")
@role_required("admin")
def view_students():

    conn = get_connection()

    students = conn.execute("""
        SELECT id, name, email
        FROM users
        WHERE role='student'
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "students.html",
        students=students
    )




# Student Dashboard
@app.route("/student")
@role_required("student")
def student_dashboard():

    conn = get_connection()

    total_books = conn.execute("""
        SELECT COUNT(*) FROM books WHERE available > 0
    """).fetchone()[0]

    my_requests = conn.execute("""
        SELECT COUNT(*) FROM borrow_requests
        WHERE user_id=? AND status='pending'
    """, (session["user_id"],)).fetchone()[0]

    my_issued = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE user_id=? AND status='issued'
    """, (session["user_id"],)).fetchone()[0]

    # Recommend books based on previously borrowed categories
    recommended_books = conn.execute("""
        SELECT * FROM books
        WHERE available > 0
        AND category IN (
            SELECT DISTINCT b.category
            FROM transactions t
            JOIN books b ON t.book_id = b.id
            WHERE t.user_id = ?
        )
        ORDER BY title
        LIMIT 4
    """, (session["user_id"],)).fetchall()

    # Show latest available books if no recommendations are found
    if not recommended_books:
        recommended_books = conn.execute("""
            SELECT * FROM books
            WHERE available > 0
            ORDER BY id DESC
            LIMIT 4
        """).fetchall()

    conn.close()

    return render_template(
        "student_dashboard.html",
        total_books=total_books,
        my_requests=my_requests,
        my_issued=my_issued,
        recommended_books=recommended_books
    )

    # Get student details
    student = conn.execute("""
        SELECT id, name, email
        FROM users
        WHERE id = ?
    """, (session["user_id"],)).fetchone()

    # Get borrowing statistics
    total_borrowed = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE user_id = ?
    """, (session["user_id"],)).fetchone()[0]

    currently_issued = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE user_id = ? AND status = 'issued'
    """, (session["user_id"],)).fetchone()[0]

    returned_books = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE user_id = ? AND status = 'returned'
    """, (session["user_id"],)).fetchone()[0]

    # Get borrowing history
    history = conn.execute("""
        SELECT b.title, b.author,
               t.issue_date, t.due_date,
               t.return_date, t.fine, t.status
        FROM transactions t
        JOIN books b ON t.book_id = b.id
        WHERE t.user_id = ?
        ORDER BY t.id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "student_profile.html",
        student=student,
        total_borrowed=total_borrowed,
        currently_issued=currently_issued,
        returned_books=returned_books,
        history=history
    )

# Student Profile
@app.route("/student/profile")
@role_required("student")
def student_profile():

    conn = get_connection()

    student = conn.execute("""
        SELECT id, name, email
        FROM users
        WHERE id = ?
    """, (session["user_id"],)).fetchone()

    total_borrowed = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE user_id = ?
    """, (session["user_id"],)).fetchone()[0]

    currently_issued = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE user_id = ? AND status = 'issued'
    """, (session["user_id"],)).fetchone()[0]

    returned_books = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE user_id = ? AND status = 'returned'
    """, (session["user_id"],)).fetchone()[0]

    history = conn.execute("""
        SELECT b.title, b.author,
               t.issue_date, t.due_date,
               t.return_date, t.fine, t.status
        FROM transactions t
        JOIN books b ON t.book_id = b.id
        WHERE t.user_id = ?
        ORDER BY t.id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "student_profile.html",
        student=student,
        total_borrowed=total_borrowed,
        currently_issued=currently_issued,
        returned_books=returned_books,
        history=history
    )


# View and Search Books with Category Filter
@app.route("/student/books")
@role_required("student")
def student_books():
    print("BROWSE BOOKS SESSION:", dict(session))

    keyword = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    conn = get_connection()

    books = conn.execute("""
        SELECT * FROM books
        WHERE (
            title LIKE ?
            OR author LIKE ?
            OR category LIKE ?
        )
        AND (? = '' OR category = ?)
        AND available > 0
        ORDER BY title
    """, (
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%",
        category,
        category
    )).fetchall()

    conn.close()

    return render_template(
        "student_books.html",
        books=books,
        keyword=keyword,
        category=category
    )


# Student QR Code Scanner
@app.route("/student/scan")
@role_required("student")
def scan_book():
    return render_template("scan_book.html")



# Student Book Details
@app.route("/student/book/<int:book_id>")
@role_required("student")
def book_details(book_id):

    conn = get_connection()

    book = conn.execute("""
        SELECT * FROM books
        WHERE id = ?
    """, (book_id,)).fetchone()

    reviews = conn.execute("""
        SELECT reviews.*, users.name AS student_name
        FROM reviews
        JOIN users ON reviews.user_id = users.id
        WHERE reviews.book_id = ?
        ORDER BY reviews.created_at DESC
    """, (book_id,)).fetchall()

    rating_data = conn.execute("""
        SELECT AVG(rating) AS average_rating,
               COUNT(*) AS total_reviews
        FROM reviews
        WHERE book_id = ?
    """, (book_id,)).fetchone()

    conn.close()

    if book is None:
        flash("Book not found.")
        return redirect(url_for("student_books"))

    return render_template(
        "book_details.html",
        book=book,
        reviews=reviews,
        average_rating=rating_data["average_rating"],
        total_reviews=rating_data["total_reviews"]
    )

# Submit Book Review
@app.route("/student/review/<int:book_id>", methods=["POST"])
@role_required("student")
def submit_review(book_id):

    rating = request.form.get("rating")
    review = request.form.get("review")

    if not rating or not rating.isdigit() or not 1 <= int(rating) <= 5:
        flash("Please select a valid rating.")
        return redirect(url_for("book_details", book_id=book_id))

    conn = get_connection()

    book = conn.execute(
        "SELECT id FROM books WHERE id = ?",
        (book_id,)
    ).fetchone()

    if not book:
        conn.close()
        flash("Book not found.")
        return redirect(url_for("student_books"))

    conn.execute("""
        INSERT INTO reviews (user_id, book_id, rating, review)
        VALUES (?, ?, ?, ?)
    """, (session["user_id"], book_id, int(rating), review))

    conn.commit()
    conn.close()

    flash("Your review has been submitted successfully!")

    return redirect(url_for("book_details", book_id=book_id))

# View Student Wishlist
@app.route("/student/wishlist")
@role_required("student")
def wishlist():

    conn = get_connection()

    books = conn.execute("""
        SELECT books.*
        FROM wishlist
        JOIN books ON wishlist.book_id = books.id
        WHERE wishlist.user_id = ?
        ORDER BY wishlist.created_at DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template("wishlist.html", books=books)


# Add Book to Wishlist
@app.route("/student/wishlist/add/<int:book_id>", methods=["POST"])
@role_required("student")
def add_to_wishlist(book_id):

    conn = get_connection()

    book = conn.execute(
        "SELECT id FROM books WHERE id = ?",
        (book_id,)
    ).fetchone()

    if book is None:
        conn.close()
        flash("Book not found.")
        return redirect(url_for("student_books"))

    conn.execute("""
        INSERT OR IGNORE INTO wishlist (user_id, book_id)
        VALUES (?, ?)
    """, (session["user_id"], book_id))

    conn.commit()
    conn.close()

    flash("Book added to your wishlist!")
    return redirect(url_for("book_details", book_id=book_id))


# Remove Book from Wishlist
@app.route("/student/wishlist/remove/<int:book_id>", methods=["POST"])
@role_required("student")
def remove_from_wishlist(book_id):

    conn = get_connection()

    conn.execute("""
        DELETE FROM wishlist
        WHERE user_id = ? AND book_id = ?
    """, (session["user_id"], book_id))

    conn.commit()
    conn.close()

    flash("Book removed from your wishlist!")
    return redirect(url_for("wishlist"))
# View Student Notifications
@app.route("/student/notifications")
@role_required("student")
def student_notifications():

    conn = get_connection()

    today = date.today()
    user_id = session["user_id"]

    # Find currently issued books
    issued_books = conn.execute("""
        SELECT t.id, t.due_date, b.title
        FROM transactions t
        JOIN books b ON t.book_id = b.id
        WHERE t.user_id = ? AND t.status = 'issued'
    """, (user_id,)).fetchall()

    # Generate due-date notifications
    for book in issued_books:

        due = date.fromisoformat(book["due_date"])
        days_left = (due - today).days

        message = None

        if 0 <= days_left <= 3:
            message = (
                f"Reminder: Your book '{book['title']}' "
                f"is due on {book['due_date']}."
            )

        elif days_left < 0:
            late_days = abs(days_left)
            pending_fine = late_days * 5

            message = (
                f"Overdue: Your book '{book['title']}' "
                f"was due on {book['due_date']}. "
                f"Pending fine: Rs. {pending_fine}."
            )

        if message:

            existing = conn.execute("""
                SELECT id FROM notifications
                WHERE user_id = ? AND message = ?
            """, (user_id, message)).fetchone()

            if not existing:
                conn.execute("""
                    INSERT INTO notifications (user_id, message)
                    VALUES (?, ?)
                """, (user_id, message))

    conn.commit()

    # Display all notifications
    notifications = conn.execute("""
        SELECT *
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "notifications.html",
        notifications=notifications
    )
# Mark Notification as Read
@app.route("/student/notifications/read/<int:notification_id>", methods=["POST"])
@role_required("student")
def mark_notification_read(notification_id):

    conn = get_connection()

    conn.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE id = ? AND user_id = ?
    """, (notification_id, session["user_id"]))

    conn.commit()
    conn.close()

    flash("Notification marked as read!")

    return redirect(url_for("student_notifications"))
# Request a Book
@app.route("/student/request/<int:book_id>", methods=["POST"])
@role_required("student")
def request_book(book_id):

    user_id = session["user_id"]
    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")

        book = conn.execute("""
            SELECT * FROM books
            WHERE id=? AND available > 0
        """, (book_id,)).fetchone()

        if not book:
            flash("Book is currently unavailable.")

        else:
            existing = conn.execute("""
                SELECT id FROM borrow_requests
                WHERE user_id=? AND book_id=?
                AND status='pending'

                UNION ALL

                SELECT id FROM transactions
                WHERE user_id=? AND book_id=?
                AND status='issued'
            """, (user_id, book_id, user_id, book_id)).fetchone()

            if existing:
                flash("You already have a pending request or issued copy.")

            else:
                conn.execute("""
                    INSERT INTO borrow_requests
                    (user_id, book_id, request_date, status)
                    VALUES (?, ?, ?, 'pending')
                """, (user_id, book_id, date.today().isoformat()))

                flash("Book request submitted successfully!")

        conn.commit()

    except Exception:
        conn.rollback()
        flash("Unable to submit your request.")

    finally:
        conn.close()

    return redirect(url_for("student_books"))


# View My Requests
@app.route("/student/requests")
@role_required("student")
def my_requests():

    conn = get_connection()

    requests = conn.execute("""
        SELECT r.*, b.title, b.author
        FROM borrow_requests r
        JOIN books b ON r.book_id=b.id
        WHERE r.user_id=?
        ORDER BY r.id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "my_requests.html",
        requests=requests
    )

# View Issued Books and History
@app.route("/student/issued")
@role_required("student")
def issued_books():

    conn = get_connection()

    transactions = conn.execute("""
        SELECT t.*, b.title, b.author
        FROM transactions t
        JOIN books b ON t.book_id = b.id
        WHERE t.user_id = ?
        ORDER BY t.id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    today = date.today()
    book_list = []

    for t in transactions:
        book = dict(t)

        if book["status"] == "issued":
            due = date.fromisoformat(book["due_date"])
            days_left = (due - today).days

            late_days = max(0, (today - due).days)

            book["overdue_days"] = late_days
            book["pending_fine"] = late_days * 5

            if days_left < 0:
                book["reminder_status"] = "Overdue"
            elif days_left == 0:
                book["reminder_status"] = "Due Today"
            elif days_left <= 3:
                book["reminder_status"] = "Due Soon"
            else:
                book["reminder_status"] = "On Time"
        else:
            book["overdue_days"] = 0
            book["pending_fine"] = book["fine"] or 0
            book["reminder_status"] = "Returned"

        book_list.append(book)

    return render_template(
        "issued_books.html",
        transactions=book_list
    )


# Return a Book
@app.route("/student/return/<int:transaction_id>", methods=["POST"])
@role_required("student")
def return_book(transaction_id):

    user_id = session["user_id"]
    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")

        transaction = conn.execute("""
            SELECT * FROM transactions
            WHERE id=? AND user_id=? AND status='issued'
        """, (transaction_id, user_id)).fetchone()

        if not transaction:
            flash("Issued book record not found.")

        else:
            today = date.today()
            due = date.fromisoformat(transaction["due_date"])

            late_days = max(0, (today - due).days)
            fine = late_days * 5

            conn.execute("""
                UPDATE transactions
                SET return_date=?, fine=?, status='returned'
                WHERE id=?
            """, (today.isoformat(), fine, transaction_id))

            conn.execute("""
                UPDATE books
                SET available=available+1
                WHERE id=?
            """, (transaction["book_id"],))

            flash(f"Book returned successfully. Fine: Rs. {fine}")

            conn.execute("""
                INSERT INTO notifications (user_id, message)
                VALUES (?, ?)
            """, (
                user_id,
                f"Your book has been returned successfully. Fine: Rs. {fine}"
            ))

        conn.commit()

    except Exception:
        conn.rollback()
        flash("Unable to return book.")

    finally:
        conn.close()

    return redirect(url_for("issued_books"))


# Admin: View Borrow Requests
@app.route("/admin/requests")
@role_required("admin")
def admin_requests():

    conn = get_connection()

    requests_list = conn.execute("""
        SELECT r.*, u.name, u.email,
               b.title, b.author
        FROM borrow_requests r
        JOIN users u ON r.user_id=u.id
        JOIN books b ON r.book_id=b.id
        ORDER BY r.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin_requests.html",
        requests=requests_list
    )


# Admin: Approve or Reject Request
@app.route("/admin/requests/<int:request_id>/<action>",
           methods=["POST"])
@role_required("admin")
def process_request(request_id, action):

    if action not in ("approve", "reject"):
        flash("Invalid request action.")
        return redirect(url_for("admin_requests"))

    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")

        borrow = conn.execute("""
            SELECT * FROM borrow_requests
            WHERE id=? AND status='pending'
        """, (request_id,)).fetchone()

        if not borrow:
            flash("Request not found or already processed.")

        elif action == "reject":
            conn.execute("""
                UPDATE borrow_requests
                SET status='rejected'
                WHERE id=?
            """, (request_id,))

            conn.execute("""
                INSERT INTO notifications (user_id, message)
                VALUES (?, ?)
            """, (
                borrow["user_id"],
                "Your book request has been rejected by the admin."
            ))

            flash("Book request rejected.")

        else:
            book = conn.execute("""
                SELECT available FROM books WHERE id=?
            """, (borrow["book_id"],)).fetchone()

            if not book or book["available"] < 1:
                flash("No available copy of this book.")

            else:
                today = date.today()
                due = today + timedelta(days=14)

                conn.execute("""
                    UPDATE books
                    SET available=available-1
                    WHERE id=?
                """, (borrow["book_id"],))

                conn.execute("""
                    INSERT INTO transactions
                    (user_id, book_id, issue_date, due_date, status)
                    VALUES (?, ?, ?, ?, 'issued')
                """, (
                    borrow["user_id"],
                    borrow["book_id"],
                    today.isoformat(),
                    due.isoformat()
                ))

                conn.execute("""
                    UPDATE borrow_requests
                    SET status='approved'
                    WHERE id=?
                """, (request_id,))

                conn.execute("""
                    INSERT INTO notifications (user_id, message)
                    VALUES (?, ?)
                """, (
                    borrow["user_id"],
                    "Congratulations! Your book request has been approved and the book has been issued."
                ))

                flash("Request approved and book issued!")

        conn.commit()

    except Exception:
        conn.rollback()
        flash("Unable to process the request.")

    finally:
        conn.close()

    return redirect(url_for("admin_requests"))

# Admin Reports
@app.route("/admin/reports")
@role_required("admin")
def admin_reports():

    conn = get_connection()

    total_issued = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE status='issued'
    """).fetchone()[0]

    total_returned = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE status='returned'
    """).fetchone()[0]

    total_overdue = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE status='issued' AND due_date < ?
    """, (date.today().isoformat(),)).fetchone()[0]

    total_fines = conn.execute("""
        SELECT COALESCE(SUM(fine), 0)
        FROM transactions
        WHERE status='returned'
    """).fetchone()[0]

    records = conn.execute("""
        SELECT u.name, u.email, b.title,
               t.issue_date, t.due_date,
               t.return_date, t.fine, t.status
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        JOIN books b ON t.book_id = b.id
        ORDER BY t.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin_reports.html",
        total_issued=total_issued,
        total_returned=total_returned,
        total_overdue=total_overdue,
        total_fines=total_fines,
        records=records
    )


# Download Admin Reports as PDF
@app.route("/admin/reports/download")
@role_required("admin")
def download_admin_report():

    conn = get_connection()

    total_issued = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE status='issued'
    """).fetchone()[0]

    total_returned = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE status='returned'
    """).fetchone()[0]

    total_overdue = conn.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE status='issued' AND due_date < ?
    """, (date.today().isoformat(),)).fetchone()[0]

    total_fines = conn.execute("""
        SELECT COALESCE(SUM(fine), 0)
        FROM transactions
        WHERE status='returned'
    """).fetchone()[0]

    records = conn.execute("""
        SELECT u.name, u.email, b.title,
               t.issue_date, t.due_date,
               t.return_date, t.fine, t.status
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        JOIN books b ON t.book_id = b.id
        ORDER BY t.id DESC
    """).fetchall()

    conn.close()

    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(A4),
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=15*mm
    )

    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(
        "SMART LIBRARY - ADMIN REPORTS",
        styles["Title"]
    ))

    elements.append(Spacer(1, 15))

    elements.append(Paragraph(
        f"Report Date: {date.today().strftime('%d-%m-%Y')}",
        styles["Normal"]
    ))

    elements.append(Spacer(1, 15))

    summary_data = [
        ["Total Issued", "Total Returned",
         "Overdue Books", "Fines Collected"],
        [str(total_issued), str(total_returned),
         str(total_overdue), f"Rs. {total_fines}"]
    ]

    summary_table = Table(summary_data, colWidths=[60*mm]*4)

    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173d68")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#eaf1f8")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("PADDING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 25))

    elements.append(Paragraph(
        "Student Borrowing Records",
        styles["Heading2"]
    ))

    elements.append(Spacer(1, 10))

    table_data = [[
        "Student", "Email", "Book",
        "Issue Date", "Due Date",
        "Return Date", "Fine", "Status"
    ]]

    for r in records:
        table_data.append([
            r["name"],
            r["email"],
            r["title"],
            r["issue_date"],
            r["due_date"],
            r["return_date"] or "-",
            f"Rs. {r['fine'] or 0}",
            r["status"].title()
        ])

    records_table = Table(
        table_data,
        repeatRows=1,
        colWidths=[32*mm, 48*mm, 38*mm,
                   25*mm, 25*mm, 25*mm, 20*mm, 20*mm]
    )

    records_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173d68")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f1f5f9")]),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("PADDING", (0, 0), (-1, -1), 7)
    ]))

    elements.append(records_table)

    document.build(elements)

    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name="Smart_Library_Admin_Report.pdf",
        mimetype="application/pdf"
    )

# Display All Application Routes
print(app.url_map)


# Run Smart Library Application
if __name__ == "__main__":
    generate_all_book_qr()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1"
    )

