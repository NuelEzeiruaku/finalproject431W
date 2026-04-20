from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"

app = Flask(__name__)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            error = "Please enter both email and password."
            return render_template("login.html", error=error)

        password_hash = hash_password(password)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT email, role
            FROM users
            WHERE email = ? AND password_hash = ?
        """, (email, password_hash))
        user = cur.fetchone()
        conn.close()

        if user is None:
            error = "Invalid email or password."
            return render_template("login.html", error=error)

        role = user["role"]

        if role == "seller":
            return redirect(url_for("seller_home", email=user["email"]))
        elif role == "buyer":
            return redirect(url_for("buyer_home", email=user["email"]))
        elif role == "helpdesk":
            return redirect(url_for("helpdesk_home", email=user["email"]))
        else:
            error = "Unknown role."
            return render_template("login.html", error=error)

    return render_template("login.html", error=error)


@app.route("/seller")
def seller_home():
    email = request.args.get("email", "")
    return render_template("seller_home.html", email=email)


@app.route("/buyer")
def buyer_home():
    email = request.args.get("email", "")
    return render_template("buyer_home.html", email=email)


@app.route("/helpdesk")
def helpdesk_home():
    email = request.args.get("email", "")
    return render_template("helpdesk_home.html", email=email)


if __name__ == "__main__":
    app.run(debug=True)