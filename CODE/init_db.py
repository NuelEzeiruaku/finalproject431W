import csv, sqlite3, hashlib
from pathlib import Path
from datetime import datetime
import random

BASE_DIR     = Path(__file__).resolve().parent
DB_PATH      = BASE_DIR / "database.db"
USERS_CSV    = BASE_DIR / "Users.csv"
SELLERS_CSV  = BASE_DIR / "Sellers.csv"
BIDDERS_CSV  = BASE_DIR / "Bidders.csv"
HELPDESK_CSV = BASE_DIR / "Helpdesk.csv"


def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def create_tables(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = OFF")
    drop_order = [
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
            address_id  INTEGER PRIMARY KEY AUTOINCREMENT,
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

    conn.commit()
    print("All tables created.")


def populate_users(conn):
    rows = load_csv(USERS_CSV)
    sellers_emails  = {r.get("email","").strip() for r in load_csv(SELLERS_CSV)}
    bidders_emails  = {r.get("email","").strip() for r in load_csv(BIDDERS_CSV)}
    helpdesk_emails = {r.get("email","").strip() for r in load_csv(HELPDESK_CSV)}

    # seed the pseudo helpdesk team account
    conn.execute(
        "INSERT OR IGNORE INTO Users(email, password) VALUES(?,?)",
        ("helpdeskteam@lsu.edu", hash_password("helpdeskteam")))

    ins = skp = 0
    for row in rows:
        email = row.get("email","").strip()
        pwd   = row.get("password","").strip()
        if not email or not pwd: skp += 1; continue
        conn.execute(
            "INSERT OR IGNORE INTO Users(email, password) VALUES(?,?)",
            (email, hash_password(pwd)))
        ins += 1
    conn.commit()
    print(f"Users: {ins} inserted, {skp} skipped")

def populate_helpdesk(conn):
    rows = load_csv(HELPDESK_CSV)
    ins  = 0
    for row in rows:
        email = row.get("email","").strip()
        pos   = row.get("Position", row.get("position","")).strip()
        if not conn.execute("SELECT 1 FROM Users WHERE email=?",(email,)).fetchone(): continue
        conn.execute("INSERT OR IGNORE INTO Helpdesk(email,position) VALUES(?,?)",(email,pos))
        ins += 1
    conn.commit()
    print(f"Helpdesk: {ins}")

def populate_zipcode_and_address(conn):
    """Seed a handful of zipcodes and return a map email→address_id for bidders."""
    zipcodes = [
        ("16802","State College","PA"),
        ("70803","Baton Rouge","LA"),
        ("10001","New York","NY"),
        ("94103","San Francisco","CA"),
        ("60601","Chicago","IL"),
    ]
    for zc,city,state in zipcodes:
        conn.execute(
            "INSERT OR IGNORE INTO Zipcode_Info(zipcode,city,state) VALUES(?,?,?)",
            (zc,city,state))
    conn.commit()

def populate_bidders(conn):
    rows = load_csv(BIDDERS_CSV)
    # pre-insert a default address row everyone can share
    conn.execute(
        "INSERT INTO Address(zipcode,street_num,street_name) VALUES(?,?,?)",
        ("16802","1","University Dr"))
    default_addr = conn.execute(
        "SELECT last_insert_rowid()").fetchone()[0]
    ins = 0
    for row in rows:
        email = row.get("email","").strip()
        if not conn.execute("SELECT 1 FROM Users WHERE email=?",(email,)).fetchone(): continue
        age = row.get("age","").strip()
        conn.execute(
            "INSERT OR IGNORE INTO Bidders(email,first_name,last_name,age,home_address_id,major)"
            " VALUES(?,?,?,?,?,?)",
            (email,
             row.get("first_name","").strip(),
             row.get("last_name","").strip(),
             int(age) if age.isdigit() else None,
             default_addr,
             row.get("major","").strip()))
        ins += 1
    conn.commit()
    print(f"Bidders: {ins}")

def populate_sellers(conn):
    rows = load_csv(SELLERS_CSV)
    ins  = 0
    for row in rows:
        email = row.get("email","").strip()
        # seller must already be a bidder
        if not conn.execute("SELECT 1 FROM Bidders WHERE email=?",(email,)).fetchone(): continue
        try: bal = float(row.get("balance","0").strip())
        except: bal = 0.0
        conn.execute(
            "INSERT OR IGNORE INTO Sellers(email,bank_routing_number,bank_account_number,balance)"
            " VALUES(?,?,?,?)",
            (email,
             row.get("bank_routing_number","").strip(),
             row.get("bank_account_number","").strip(),
             bal))
        ins += 1
    conn.commit()
    print(f"Sellers: {ins}")

def populate_categories(conn):
    tree = {
        "Electronics":         ["Laptops","Phones & Tablets","Cameras","Gaming","Audio"],
        "Books & Media":       ["Textbooks","Fiction","Non-Fiction","Music CDs","DVDs"],
        "Clothing & Apparel":  ["Men's","Women's","Kids'","Shoes","Accessories"],
        "Home & Garden":       ["Furniture","Kitchen","Tools","Decor","Outdoor"],
        "Sports & Outdoors":   ["Fitness Equipment","Bicycles","Camping","Team Sports","Water Sports"],
        "Collectibles & Art":  ["Coins","Stamps","Trading Cards","Fine Art","Antiques"],
        "Vehicles & Parts":    ["Cars","Motorcycles","Bicycle Parts","Car Parts","Accessories"],
        "Musical Instruments": ["Guitars","Keyboards","Drums","Wind Instruments","Recording Gear"],
    }
    # top-level: parent_category = NULL
    for parent, children in tree.items():
        conn.execute(
            "INSERT OR IGNORE INTO Categories(parent_category,category_name) VALUES(?,?)",
            (None, parent))
        for child in children:
            conn.execute(
                "INSERT OR IGNORE INTO Categories(parent_category,category_name) VALUES(?,?)",
                (parent, child))
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM Categories").fetchone()[0]
    print(f"Categories: {count}")

def populate_sample_listings(conn):
    # grab a few sellers
    sellers = [r[0] for r in conn.execute(
        "SELECT email FROM Sellers LIMIT 10").fetchall()]
    if not sellers:
        print("No sellers — skipping sample listings."); return

    now = datetime.now().strftime("%Y-%m-%d")
    rng = random.Random(42)

    samples = [
        ("Laptops",          "MacBook Pro 2022 Listing",   "MacBook Pro 2022",   "16-inch M1 Pro, lightly used",   899.00, 20),
        ("Textbooks",        "Calculus Textbook",           "Stewart Calculus 9e","Some highlighting ch1-3",        35.00,  10),
        ("Audio",            "Sony WH-1000XM5",             "Sony Headphones",    "Noise-cancelling, one semester", 180.00, 15),
        ("Bicycles",         "Trek 7.4 FX Bike",            "Hybrid Bike",        "24 speeds, recently tuned",      320.00, 12),
        ("Gaming",           "Nintendo Switch OLED Bundle", "Switch OLED",        "4 games included",               280.00, 18),
        ("Guitars",          "Yamaha FG800 Acoustic",       "Acoustic Guitar",    "Solid spruce top, gig bag",      150.00, 8),
        ("Phones & Tablets", "iPhone 13 128GB Unlocked",    "iPhone 13",          "Battery health 91%",             420.00, 20),
        ("Furniture",        "Dorm Futon + Cover",          "Futon",              "Black, folds flat, washable",    75.00,  10),
        ("Cameras",          "Canon Rebel SL3 Kit",         "DSLR Camera",        "18-55mm, 2 batteries, 32GB SD",  550.00, 25),
        ("Drums",            "Pearl Export Drum Kit",       "Full Drum Kit",      "5-piece, Zildjian cymbals",      600.00, 15),
    ]

    ins = 0
    # track per-seller listing_id counter
    seller_counters = {}
    for i, (cat, title, name, desc, reserve, max_bids) in enumerate(samples):
        seller = sellers[i % len(sellers)]
        lid    = seller_counters.get(seller, 0) + 1
        seller_counters[seller] = lid
        conn.execute(
            "INSERT INTO Auction_Listings"
            "(seller_email,listing_id,category,auction_title,product_name,"
            "product_description,quantity,reserve_price,max_bids,status)"
            " VALUES(?,?,?,?,?,?,?,?,?,1)",
            (seller, lid, cat, title, name, desc, 1, reserve, max_bids))
        ins += 1
    conn.commit()
    print(f"Sample listings: {ins}")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        create_tables(conn)
        populate_zipcode_and_address(conn)
        populate_users(conn)
        populate_helpdesk(conn)
        populate_bidders(conn)
        populate_sellers(conn)
        populate_categories(conn)
        populate_sample_listings(conn)

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
