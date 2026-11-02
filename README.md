# Smart Library

Smart Library is a Flask-based library management system designed for students and administrators. It supports book catalog management, borrowing requests, return tracking, QR-based access, notifications, and PDF reporting.

## Features

- Admin dashboard with analytics and book management
- Student login and registration
- Book search, category filtering, and detail views
- Borrow request workflow with approval/rejection
- Issued book tracking and due-date notifications
- Student wishlist and reviews
- QR code generation for book access links
- Admin PDF report download
- SQLite database for a lightweight local setup

## Tech Stack

- Python 3
- Flask
- SQLite
- ReportLab
- QRCode

## Project Structure

- `app.py` - main Flask application
- `auth.py` - authentication routes
- `database.py` - SQLite schema and connection setup
- `create_admin.py` - helper script to create the first admin account
- `static/` - CSS and generated QR images
- `templates/` - HTML templates
- `requirements.txt` - Python dependencies

## Requirements

- Python 3.10+
- pip

## Local Setup

1. Clone the repository:
   ```bash
   git clone <your-repository-url>
   cd smart_library
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   ```

   On Windows:
   ```bash
   .venv\Scripts\activate
   ```

   On macOS/Linux:
   ```bash
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Create an admin user:
   ```bash
   python create_admin.py
   ```

5. Run the app:
   ```bash
   flask --app app run --debug
   ```

6. Open the app in your browser:
   ```text
   http://127.0.0.1:5000
   ```

## Environment Variables

You can set the following variables before deployment:

```bash
SECRET_KEY=change-me
APP_BASE_URL=http://127.0.0.1:5000
PORT=5000
FLASK_DEBUG=1
```

A sample file is included as `.env.example`.

## Admin Access

Use the admin account created with `create_admin.py` to access the admin dashboard and manage books, requests, and reports.

## Deployment Notes

This project is ready for GitHub-based deployment to platforms such as Render, Railway, or Heroku. For production deployment, run the app with Gunicorn:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

Set the environment variables above on your hosting platform before launch.

## License

This project is for educational and personal use.

## Notes

- The app creates and uses a local SQLite database file named `smart_library.db`.
- Generated QR codes are saved in `static/qr_codes/`.
- The default secret key is only for local development and should be replaced in production.
