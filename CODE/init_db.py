import csv, sqlite3, hashlib
from pathlib import Path
from datetime import datetime
import random

BASE_DIR          = Path(__file__).resolve().parent
DB_PATH           = BASE_DIR / "database.db"
USERS_CSV         = BASE_DIR / "Users.csv"
SELLERS_CSV       = BASE_DIR / "Sellers.csv"
BIDDERS_CSV       = BASE_DIR / "Bidders.csv"
HELPDESK_CSV      = BASE_DIR / "Helpdesk.csv"
ADDRESS_CSV = BASE_DIR / "Address.csv"
ZIPCODE_CSV = BASE_DIR / "Zipcode_Info.csv"
CREDIT_CARDS_CSV = BASE_DIR / "Credit_Cards.csv"
LOCAL_VENDORS_CSV = BASE_DIR / "Local_Vendors.csv"
CATEGORIES_CSV = BASE_DIR / "Categories.csv"
LISTINGS_CSV = BASE_DIR / "Auction_Listings.csv"
BIDS_CSV = BASE_DIR / "Bids.csv"
TRANSACTIONS_CSV = BASE_DIR / "Transactions.csv"
RATINGS_CSV = BASE_DIR / "Ratings.csv"
REQUESTS_CSV = BASE_DIR / "Requests.csv"


def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def create_tables(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = OFF")
    drop_order = [
        "Promotions", "Watchlist",
        "Rating", "Transactions", "Bids", "Auction_Listings",
        "Categories", "Local_Vendors", "Sellers", "Credit_Cards",
        "Bidders", "Address", "Zipcode_Info", "Requests",
        "Helpdesk", "Users"
    ]
    for t in drop_order:
        cur.execute(f"DROP TABLE IF EXISTS {t}")
    cur.execute("PRAGMA foreign_keys = ON")

    # ── core user tables ───────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE Users (
            email    TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )""")

    cur.execute("""
        CREATE TABLE Helpdesk (
            email    TEXT PRIMARY KEY REFERENCES Users(email),
            position TEXT
        )""")

    cur.execute("""
        CREATE TABLE Requests (
            request_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_email         TEXT NOT NULL REFERENCES Users(email),
            helpdesk_staff_email TEXT NOT NULL DEFAULT 'helpdeskteam@lsu.edu',
            request_type         TEXT NOT NULL,
            request_desc         TEXT,
            request_status       INTEGER NOT NULL DEFAULT 0
        )""")

    # ── address tables ─────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE Zipcode_Info (
            zipcode TEXT PRIMARY KEY,
            city    TEXT,
            state   TEXT
        )""")

    cur.execute("""
        CREATE TABLE Address (
            address_id  TEXT PRIMARY KEY,
            zipcode     TEXT REFERENCES Zipcode_Info(zipcode),
            street_num  TEXT,
            street_name TEXT
        )""")

    # ── bidder / seller tables ─────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE Bidders (
            email           TEXT PRIMARY KEY REFERENCES Users(email),
            first_name      TEXT NOT NULL,
            last_name       TEXT NOT NULL,
            age             INTEGER,
            home_address_id INTEGER REFERENCES Address(address_id),
            major           TEXT
        )""")

    cur.execute("""
        CREATE TABLE Credit_Cards (
            credit_card_num TEXT PRIMARY KEY,
            card_type       TEXT,
            expire_month    TEXT,
            expire_year     TEXT,
            security_code   TEXT,
            owner_email     TEXT NOT NULL REFERENCES Bidders(email)
        )""")

    cur.execute("""
        CREATE TABLE Sellers (
            email               TEXT PRIMARY KEY REFERENCES Bidders(email),
            bank_routing_number TEXT,
            bank_account_number TEXT,
            balance             REAL DEFAULT 0
        )""")

    cur.execute("""
        CREATE TABLE Local_Vendors (
            email                        TEXT PRIMARY KEY REFERENCES Sellers(email),
            business_name                TEXT,
            business_address_id          INTEGER REFERENCES Address(address_id),
            customer_service_phone_number TEXT
        )""")

    # ── categories ─────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE Categories (
            parent_category TEXT,
            category_name   TEXT NOT NULL,
            PRIMARY KEY (parent_category, category_name)
        )""")

    # ── auction / bid / transaction / rating ───────────────────────────────────
    cur.execute("""
        CREATE TABLE Auction_Listings (
            seller_email      TEXT NOT NULL REFERENCES Sellers(email),
            listing_id        INTEGER NOT NULL,
            category          TEXT,
            auction_title     TEXT NOT NULL,
            product_name      TEXT,
            product_description TEXT,
            quantity          INTEGER DEFAULT 1,
            reserve_price     REAL NOT NULL,
            max_bids          INTEGER NOT NULL,
            status            INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (seller_email, listing_id)
        )""")

    cur.execute("""
        CREATE TABLE Bids (
            bid_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            listing_id   INTEGER NOT NULL,
            bidder_email TEXT NOT NULL REFERENCES Bidders(email),
            bid_price    REAL NOT NULL,
            FOREIGN KEY (seller_email, listing_id)
                REFERENCES Auction_Listings(seller_email, listing_id)
        )""")

    cur.execute("""
        CREATE TABLE Transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email   TEXT NOT NULL,
            listing_id     INTEGER NOT NULL,
            buyer_email    TEXT NOT NULL REFERENCES Bidders(email),
            date           TEXT NOT NULL,
            payment        REAL NOT NULL,
            FOREIGN KEY (seller_email, listing_id)
                REFERENCES Auction_Listings(seller_email, listing_id)
        )""")

    cur.execute("""
        CREATE TABLE Rating (
            bidder_email TEXT NOT NULL REFERENCES Bidders(email),
            seller_email TEXT NOT NULL REFERENCES Sellers(email),
            date         TEXT NOT NULL,
            rating       INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            rating_desc  TEXT,
            PRIMARY KEY (bidder_email, seller_email, date)
        )""")

    cur.execute("""
        CREATE TABLE Watchlist (
            buyer_email  TEXT NOT NULL REFERENCES Bidders(email),
            seller_email TEXT NOT NULL,
            listing_id   INTEGER NOT NULL,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (buyer_email, seller_email, listing_id),
            FOREIGN KEY (seller_email, listing_id)
                REFERENCES Auction_Listings(seller_email, listing_id)
        )""")

    cur.execute("""
        CREATE TABLE Promotions (
            seller_email TEXT NOT NULL,
            listing_id   INTEGER NOT NULL,
            promoted_by  TEXT NOT NULL REFERENCES Sellers(email),
            promo_text   TEXT,
            active       INTEGER DEFAULT 1,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (seller_email, listing_id),
            FOREIGN KEY (seller_email, listing_id)
                REFERENCES Auction_Listings(seller_email, listing_id)
        )""")

    conn.commit()
    print("All tables created.")


def populate_users(conn):
    rows = load_csv(USERS_CSV)
    conn.execute(
        "INSERT OR IGNORE INTO Users(email, password) VALUES(?,?)",
        ("helpdeskteam@lsu.edu", hash_password("helpdeskteam")))
    ins = skp = 0
    for row in rows:
        email = row.get("email", "").strip()
        pwd = row.get("password", "").strip()
        if not email or not pwd:
            skp += 1;
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Users(email, password) VALUES(?,?)",
            (email, hash_password(pwd)))
        ins += 1
    conn.commit()
    print(f"Users: {ins} inserted, {skp} skipped")


def populate_helpdesk(conn):
    rows = load_csv(HELPDESK_CSV)
    ins = 0
    for row in rows:
        email = row.get("email", "").strip()
        pos = row.get("Position", row.get("position", "")).strip()
        if not conn.execute("SELECT 1 FROM Users WHERE email=?", (email,)).fetchone():
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Helpdesk(email, position) VALUES(?,?)", (email, pos))
        ins += 1
    conn.commit()
    print(f"Helpdesk: {ins}")


def populate_zipcode(conn):
    rows = load_csv(ZIPCODE_CSV)
    ins = 0
    for row in rows:
        zipcode = str(row.get("zipcode", "")).strip()
        city = row.get("city", "").strip()
        state = row.get("state", "").strip()
        if not zipcode:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Zipcode_Info(zipcode, city, state) VALUES(?,?,?)",
            (zipcode, city, state))
        ins += 1
    conn.commit()
    print(f"Zipcode_Info: {ins}")


def populate_address(conn):
    rows = load_csv(ADDRESS_CSV)
    ins = 0
    for row in rows:
        address_id = row.get("address_id", "").strip()
        zipcode = str(row.get("zipcode", "")).strip() or None
        street_num = str(row.get("street_num", "")).strip() or None
        street_name = row.get("street_name", "").strip() or None
        if not address_id:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Address(address_id, zipcode, street_num, street_name)"
            " VALUES(?,?,?,?)",
            (address_id, zipcode, street_num, street_name))
        ins += 1
    conn.commit()
    print(f"Address: {ins}")


def populate_bidders(conn):
    rows = load_csv(BIDDERS_CSV)
    ins = skp = 0
    for row in rows:
        email = row.get("email", "").strip()
        first = row.get("first_name", "").strip()
        last = row.get("last_name", "").strip()
        age = row.get("age", "").strip()
        addr_id = row.get("home_address_id", "").strip() or None
        major = row.get("major", "").strip() or None
        if not email:
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Users WHERE email=?", (email,)).fetchone():
            skp += 1;
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Bidders"
            "(email, first_name, last_name, age, home_address_id, major)"
            " VALUES(?,?,?,?,?,?)",
            (email, first or "N/A", last or "N/A",
             int(age) if age.isdigit() else None,
             addr_id, major))
        ins += 1
    conn.commit()
    print(f"Bidders: {ins} inserted, {skp} skipped")


def populate_credit_cards(conn):
    rows = load_csv(CREDIT_CARDS_CSV)
    ins = skp = 0
    for row in rows:
        card_num = row.get("credit_card_num", "").strip()
        owner = row.get("Owner_email", row.get("owner_email", "")).strip()
        if not card_num or not owner:
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Bidders WHERE email=?", (owner,)).fetchone():
            skp += 1;
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Credit_Cards"
            "(credit_card_num, card_type, expire_month, expire_year, security_code, owner_email)"
            " VALUES(?,?,?,?,?,?)",
            (card_num,
             row.get("card_type", "").strip() or None,
             str(row.get("expire_month", "")).strip() or None,
             str(row.get("expire_year", "")).strip() or None,
             str(row.get("security_code", "")).strip() or None,
             owner))
        ins += 1
    conn.commit()
    print(f"Credit_Cards: {ins} inserted, {skp} skipped")


def populate_sellers(conn):
    rows = load_csv(SELLERS_CSV)
    ins = skp = 0
    for row in rows:
        email = row.get("email", "").strip()
        routing = row.get("bank_routing_number", "").strip()
        account = str(row.get("bank_account_number", "")).strip()
        balance = row.get("balance", "0").strip()
        if not email:
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Users WHERE email=?", (email,)).fetchone():
            skp += 1;
            continue
        # Sellers must also be Bidders per schema; auto-insert a minimal Bidder row
        # for seller-only accounts (mirrors what register_seller does at runtime)
        if not conn.execute("SELECT 1 FROM Bidders WHERE email=?", (email,)).fetchone():
            conn.execute(
                "INSERT OR IGNORE INTO Bidders"
                "(email, first_name, last_name, home_address_id) VALUES(?,?,?,NULL)",
                (email, "N/A", "N/A"))
        try:
            balance = float(balance) if balance else 0.0
        except ValueError:
            balance = 0.0
        conn.execute(
            "INSERT OR IGNORE INTO Sellers"
            "(email, bank_routing_number, bank_account_number, balance)"
            " VALUES(?,?,?,?)",
            (email, routing, account, balance))
        ins += 1
    conn.commit()
    print(f"Sellers: {ins} inserted, {skp} skipped")


def populate_local_vendors(conn):
    rows = load_csv(LOCAL_VENDORS_CSV)
    ins = skp = 0
    for row in rows:
        email = row.get("Email", row.get("email", "")).strip()
        biz_name = row.get("Business_Name", "").strip()
        biz_addr = row.get("Business_Address_ID", "").strip() or None
        phone = row.get("Customer_Service_Phone_Number", "").strip() or None
        if not email:
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Sellers WHERE email=?", (email,)).fetchone():
            skp += 1;
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Local_Vendors"
            "(email, business_name, business_address_id, customer_service_phone_number)"
            " VALUES(?,?,?,?)",
            (email, biz_name, biz_addr, phone))
        ins += 1
    conn.commit()
    print(f"Local_Vendors: {ins} inserted, {skp} skipped")


def populate_categories(conn):
    rows = load_csv(CATEGORIES_CSV)
    ins = 0
    for row in rows:
        parent = row.get("parent_category", "").strip()
        parent = None if (not parent or parent == "Root") else parent #Set to null if it is a root
        name = row.get("category_name", "").strip()
        if not name:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Categories(parent_category, category_name) VALUES(?,?)",
            (parent, name))
        ins += 1
    conn.commit()
    print(f"Categories: {ins}")


def populate_listings(conn):
    rows = load_csv(LISTINGS_CSV)
    ins = skp = 0
    for row in rows:
        seller = row.get("Seller_Email", "").strip()
        lid = row.get("Listing_ID", "").strip()
        category = row.get("Category", "").strip() or None
        title = row.get("Auction_Title", "").strip()
        pname = row.get("Product_Name", "").strip() or None
        pdesc = row.get("Product_Description", "").strip() or None
        quantity = row.get("Quantity", "1").strip()
        reserve = row.get("Reserve_Price", "0").strip().lstrip("$").strip()
        maxbids = row.get("Max_bids", "1").strip()
        status = row.get("Status", "1").strip()
        if not seller or not lid or not title:
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Sellers WHERE email=?", (seller,)).fetchone():
            skp += 1;
            continue
        try:
            lid = int(lid)
            reserve = float(reserve) if reserve else 0.0
            maxbids = int(maxbids) if maxbids.isdigit() else 1
            quantity = int(quantity) if quantity.isdigit() else 1
            status = int(status) if status.isdigit() else 1
        except ValueError:
            skp += 1;
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Auction_Listings"
            "(seller_email, listing_id, category, auction_title, product_name,"
            " product_description, quantity, reserve_price, max_bids, status)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (seller, lid, category, title, pname, pdesc, quantity, reserve, maxbids, status))
        ins += 1
    conn.commit()
    print(f"Auction_Listings: {ins} inserted, {skp} skipped")


def populate_bids(conn):
    rows = load_csv(BIDS_CSV)
    ins = skp = 0
    for row in rows:
        seller = row.get("Seller_Email", "").strip()
        lid = row.get("Listing_ID", "").strip()
        bidder = row.get("Bidder_Email", "").strip()
        price_r = row.get("Bid_Price", "").strip()
        if not seller or not lid or not bidder or not price_r:
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Bidders WHERE email=?", (bidder,)).fetchone():
            skp += 1;
            continue
        try:
            lid = int(lid)
            price = float(price_r)
        except ValueError:
            skp += 1;
            continue
        if not conn.execute(
                "SELECT 1 FROM Auction_Listings WHERE seller_email=? AND listing_id=?",
                (seller, lid)
        ).fetchone():
            skp += 1;
            continue
        conn.execute(
            "INSERT INTO Bids(seller_email, listing_id, bidder_email, bid_price)"
            " VALUES(?,?,?,?)",
            (seller, lid, bidder, price))
        ins += 1
    conn.commit()
    print(f"Bids: {ins} inserted, {skp} skipped")


def populate_transactions(conn):
    rows = load_csv(TRANSACTIONS_CSV)
    ins = skp = 0
    for row in rows:
        seller = row.get("Seller_Email", "").strip()
        lid = row.get("Listing_ID", "").strip()
        buyer = row.get("Bidder_Email", "").strip()
        date = row.get("Date", "").strip()
        payment = row.get("Payment", "").strip()
        if not seller or not lid or not buyer or not date or not payment:
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Bidders WHERE email=?", (buyer,)).fetchone():
            skp += 1;
            continue
        try:
            lid = int(lid)
            payment = float(payment)
        except ValueError:
            skp += 1;
            continue
        if not conn.execute(
                "SELECT 1 FROM Auction_Listings WHERE seller_email=? AND listing_id=?",
                (seller, lid)
        ).fetchone():
            skp += 1;
            continue
        conn.execute(
            "INSERT INTO Transactions(seller_email, listing_id, buyer_email, date, payment)"
            " VALUES(?,?,?,?,?)",
            (seller, lid, buyer, date, payment))
        ins += 1
    conn.commit()
    print(f"Transactions: {ins} inserted, {skp} skipped")


def populate_ratings(conn):
    rows = load_csv(RATINGS_CSV)
    ins = skp = 0
    for row in rows:
        bidder = row.get("Bidder_Email", "").strip()
        seller = row.get("Seller_Email", "").strip()
        date = row.get("Date", "").strip()
        rating = row.get("Rating", "").strip()
        desc = row.get("Rating_Desc", "").strip() or None
        if not bidder or not seller or not date or not rating:
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Bidders WHERE email=?", (bidder,)).fetchone():
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Sellers WHERE email=?", (seller,)).fetchone():
            skp += 1;
            continue
        try:
            rating = int(rating)
            if not (1 <= rating <= 5):
                raise ValueError
        except ValueError:
            skp += 1;
            continue
        conn.execute(
            "INSERT OR IGNORE INTO Rating(bidder_email, seller_email, date, rating, rating_desc)"
            " VALUES(?,?,?,?,?)",
            (bidder, seller, date, rating, desc))
        ins += 1
    conn.commit()
    print(f"Rating: {ins} inserted, {skp} skipped")


def populate_requests(conn):
    rows = load_csv(REQUESTS_CSV)
    ins = skp = 0
    for row in rows:
        sender = row.get("sender_email", "").strip()
        hd_email = row.get("helpdesk_staff_email", "helpdeskteam@lsu.edu").strip()
        req_type = row.get("request_type", "").strip()
        req_desc = row.get("request_desc", "").strip() or None
        status = row.get("request_status", "0").strip()
        if not sender or not req_type:
            skp += 1;
            continue
        if not conn.execute("SELECT 1 FROM Users WHERE email=?", (sender,)).fetchone():
            skp += 1;
            continue
        try:
            status = int(status)
        except ValueError:
            status = 0
        conn.execute(
            "INSERT INTO Requests"
            "(sender_email, helpdesk_staff_email, request_type, request_desc, request_status)"
            " VALUES(?,?,?,?,?)",
            (sender, hd_email or "helpdeskteam@lsu.edu", req_type, req_desc, status))
        ins += 1
    conn.commit()
    print(f"Requests: {ins} inserted, {skp} skipped")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        create_tables(conn)
        populate_users(conn)
        populate_helpdesk(conn)
        populate_zipcode(conn)
        populate_address(conn)
        populate_bidders(conn)
        populate_credit_cards(conn)
        populate_sellers(conn)
        populate_local_vendors(conn)
        populate_categories(conn)
        populate_listings(conn)
        populate_bids(conn)
        populate_transactions(conn)
        populate_ratings(conn)
        populate_requests(conn)

        print("\nSample login credentials:")
        for tbl, label in [("Bidders","buyer"), ("Sellers","seller"), ("Helpdesk","helpdesk")]:
            r = conn.execute(
                f"SELECT u.email FROM Users u JOIN {tbl} b ON u.email=b.email LIMIT 1"
            ).fetchone()
            if r: print(f"  {label}: {r['email']}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
