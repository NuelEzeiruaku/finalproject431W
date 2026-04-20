import csv
import sqlite3
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "database.db"
USERS_CSV = BASE_DIR / "Users.csv"
SELLERS_CSV = BASE_DIR / "Sellers.csv"
BIDDERS_CSV = BASE_DIR / "Bidders.csv"
HELPDESK_CSV = BASE_DIR / "Helpdesk.csv"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_email_set(csv_path: Path) -> set[str]:
    emails = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row.get("email", "").strip()
            if email:
                emails.add(email)
    return emails


def determine_role(email: str, seller_emails: set[str], bidder_emails: set[str], helpdesk_emails: set[str]) -> str | None:
    if email in helpdesk_emails:
        return "helpdesk"
    if email in seller_emails:
        return "seller"
    if email in bidder_emails:
        return "buyer"
    return None


def create_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS users")
    cur.execute("""
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('seller', 'buyer', 'helpdesk'))
        )
    """)
    conn.commit()


def populate_users(conn: sqlite3.Connection) -> None:
    seller_emails = load_email_set(SELLERS_CSV)
    bidder_emails = load_email_set(BIDDERS_CSV)
    helpdesk_emails = load_email_set(HELPDESK_CSV)

    inserted = 0
    skipped = 0

    with open(USERS_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cur = conn.cursor()

        for row in reader:
            email = row.get("email", "").strip()
            password = row.get("password", "").strip()

            if not email or not password:
                skipped += 1
                continue

            role = determine_role(email, seller_emails, bidder_emails, helpdesk_emails)

            if role is None:
                skipped += 1
                continue

            password_hash = hash_password(password)

            cur.execute("""
                INSERT INTO users (email, password_hash, role)
                VALUES (?, ?, ?)
            """, (email, password_hash, role))
            inserted += 1

    conn.commit()

    print(f"Inserted users: {inserted}")
    print(f"Skipped rows: {skipped}")

    cur = conn.cursor()
    for role in ["seller", "buyer", "helpdesk"]:
        cur.execute("SELECT email FROM users WHERE role = ? LIMIT 1", (role,))
        row = cur.fetchone()
        if row:
            print(f"Sample {role} account: {row[0]}")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        create_table(conn)
        populate_users(conn)

        cur = conn.cursor()
        cur.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
        print("\nRole counts:")
        for role, cnt in cur.fetchall():
            print(f"{role}: {cnt}")

        cur.execute("SELECT email, role, password_hash FROM users LIMIT 5")
        print("\nPreview:")
        for row in cur.fetchall():
            print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()