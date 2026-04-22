from flask import (Flask, render_template, request,
                   redirect, url_for, session, flash)
import sqlite3, hashlib
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DB_PATH  = BASE_DIR / "database.db"

app = Flask(__name__)
app.secret_key = "nittany_auction_secret_2026"


# ── helpers ───────────────────────────────────────────────────────────────────

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def current_user():
    return session.get("email"), session.get("role")

def require_role(*roles):
    email, role = current_user()
    return email if (email and role in roles) else None

def get_role(conn, email):
    if conn.execute("SELECT 1 FROM Helpdesk WHERE email=?",(email,)).fetchone():
        return "helpdesk"
    if conn.execute("SELECT 1 FROM Sellers WHERE email=?",(email,)).fetchone():
        return "seller"
    if conn.execute("SELECT 1 FROM Bidders WHERE email=?",(email,)).fetchone():
        return "buyer"
    return "user"

def build_category_tree(conn):
    rows = conn.execute(
        "SELECT parent_category, category_name FROM Categories ORDER BY category_name"
    ).fetchall()
    # top-level: parent_category IS NULL
    roots, children_map = [], {}
    for r in rows:
        node = {"name": r["category_name"], "parent": r["parent_category"], "children": []}
        if r["parent_category"] is None:
            roots.append(node)
        else:
            children_map.setdefault(r["parent_category"], []).append(node)
    for root in roots:
        root["children"] = children_map.get(root["name"], [])
        for child in root["children"]:
            child["children"] = children_map.get(child["name"], [])
    return roots

def get_bid_count(conn, seller_email, listing_id):
    return conn.execute(
        "SELECT COUNT(*) FROM Bids WHERE seller_email=? AND listing_id=?",
        (seller_email, listing_id)
    ).fetchone()[0]

def get_top_bid(conn, seller_email, listing_id):
    row = conn.execute(
        "SELECT MAX(bid_price) FROM Bids WHERE seller_email=? AND listing_id=?",
        (seller_email, listing_id)
    ).fetchone()
    return row[0] if row else None

def process_ended_auctions(conn):
    """Close any active listings that have reached max_bids."""
    ended = conn.execute("""
        SELECT al.seller_email, al.listing_id, al.reserve_price
        FROM Auction_Listings al
        WHERE al.status = 1
          AND (SELECT COUNT(*) FROM Bids b
               WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id)
              >= al.max_bids
    """).fetchall()
    for al in ended:
        top = conn.execute("""
            SELECT bidder_email, MAX(bid_price) AS price
            FROM Bids WHERE seller_email=? AND listing_id=?
        """,(al["seller_email"], al["listing_id"])).fetchone()
        if top and top["price"] and top["price"] >= al["reserve_price"]:
            conn.execute(
                "UPDATE Auction_Listings SET status=2 WHERE seller_email=? AND listing_id=?",
                (al["seller_email"], al["listing_id"]))
            conn.execute(
                "INSERT INTO Transactions(seller_email,listing_id,buyer_email,date,payment)"
                " VALUES(?,?,?,?,?)",
                (al["seller_email"], al["listing_id"],
                 top["bidder_email"], today_str(), top["price"]))
            conn.execute(
                "UPDATE Sellers SET balance=balance+? WHERE email=?",
                (top["price"], al["seller_email"]))
        else:
            # reserve not met — mark inactive (0)
            conn.execute(
                "UPDATE Auction_Listings SET status=0 WHERE seller_email=? AND listing_id=?",
                (al["seller_email"], al["listing_id"]))
    if ended:
        conn.commit()


# ── auth ──────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    _, role = current_user()
    if role == "buyer":    return redirect(url_for("buyer_home"))
    if role == "seller":   return redirect(url_for("seller_home"))
    if role == "helpdesk": return redirect(url_for("helpdesk_home"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email","").strip()
        pwd   = request.form.get("password","").strip()
        conn  = get_db()
        user  = conn.execute(
            "SELECT email FROM Users WHERE email=? AND password=?",
            (email, hash_password(pwd))
        ).fetchone()
        if not user:
            error = "Invalid email or password."
        else:
            role = get_role(conn, email)
            conn.close()
            session["email"] = email
            session["role"]  = role
            return redirect(url_for("home"))
        conn.close()
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── registration ──────────────────────────────────────────────────────────────

@app.route("/register")
def register():
    return render_template("register_choose.html")

@app.route("/register/bidder", methods=["GET","POST"])
def register_bidder():
    errors, form = {}, {}
    if request.method == "POST":
        form    = request.form.to_dict()
        email   = form.get("email","").strip()
        pwd     = form.get("password","").strip()
        confirm = form.get("confirm_password","").strip()
        first   = form.get("first_name","").strip()
        last    = form.get("last_name","").strip()
        age     = form.get("age","").strip()
        card_num = form.get("credit_card_num","").strip()

        if not email:        errors["email"]    = "Email is required."
        if not pwd:          errors["password"] = "Password is required."
        elif len(pwd) < 6:   errors["password"] = "Minimum 6 characters."
        if pwd != confirm:   errors["confirm_password"] = "Passwords do not match."
        if not first:        errors["first_name"] = "Required."
        if not last:         errors["last_name"]  = "Required."
        if age and not age.isdigit(): errors["age"] = "Must be a number."
        if not card_num:     errors["credit_card_num"] = "Credit card number is required."

        if not errors:
            conn = get_db()
            if conn.execute("SELECT 1 FROM Users WHERE email=?",(email,)).fetchone():
                errors["email"] = "Account with this email already exists."
            else:
                try:
                    # address
                    zipcode = form.get("zipcode","").strip()
                    conn.execute(
                        "INSERT OR IGNORE INTO Zipcode_Info(zipcode,city,state) VALUES(?,?,?)",
                        (zipcode, form.get("city","").strip(), form.get("state","").strip()))
                    conn.execute(
                        "INSERT INTO Address(zipcode,street_num,street_name) VALUES(?,?,?)",
                        (zipcode or None,
                         form.get("street_num","").strip() or None,
                         form.get("street_name","").strip() or None))
                    addr_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.execute(
                        "INSERT INTO Users(email,password) VALUES(?,?)",
                        (email, hash_password(pwd)))
                    conn.execute(
                        "INSERT INTO Bidders(email,first_name,last_name,age,home_address_id,major)"
                        " VALUES(?,?,?,?,?,?)",
                        (email, first, last,
                         int(age) if age.isdigit() else None,
                         addr_id,
                         form.get("major","").strip() or None))
                    conn.execute(
                        "INSERT INTO Credit_Cards(credit_card_num,card_type,expire_month,"
                        "expire_year,security_code,owner_email) VALUES(?,?,?,?,?,?)",
                        (card_num,
                         form.get("card_type","").strip() or None,
                         form.get("expire_month","").strip() or None,
                         form.get("expire_year","").strip() or None,
                         form.get("security_code","").strip() or None,
                         email))
                    conn.commit(); conn.close()
                    flash("Account created! Please log in.", "success")
                    return redirect(url_for("login"))
                except Exception as ex:
                    conn.rollback()
                    errors["general"] = f"Registration failed: {ex}"
            conn.close()
    return render_template("register_bidder.html", errors=errors, form=form)

@app.route("/register/seller", methods=["GET","POST"])
def register_seller():
    errors, form = {}, {}
    if request.method == "POST":
        form    = request.form.to_dict()
        email   = form.get("email","").strip()
        pwd     = form.get("password","").strip()
        confirm = form.get("confirm_password","").strip()
        routing = form.get("bank_routing_number","").strip()
        account = form.get("bank_account_number","").strip()
        is_vendor = bool(form.get("is_local_vendor"))

        if not email:   errors["email"]    = "Email is required."
        if not pwd:     errors["password"] = "Password is required."
        elif len(pwd)<6:errors["password"] = "Minimum 6 characters."
        if pwd!=confirm:errors["confirm_password"] = "Passwords do not match."
        if not routing: errors["bank_routing_number"] = "Required."
        if not account: errors["bank_account_number"] = "Required."
        if is_vendor:
            if not form.get("business_name","").strip():
                errors["business_name"] = "Required for vendors."

        if not errors:
            conn = get_db()
            if conn.execute("SELECT 1 FROM Users WHERE email=?",(email,)).fetchone():
                errors["email"] = "Account with this email already exists."
            else:
                try:
                    # sellers must also be bidders per schema
                    first = form.get("first_name","").strip() or "N/A"
                    last  = form.get("last_name","").strip()  or "N/A"
                    conn.execute(
                        "INSERT INTO Address(zipcode,street_num,street_name) VALUES(NULL,NULL,NULL)")
                    addr_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.execute(
                        "INSERT INTO Users(email,password) VALUES(?,?)",
                        (email, hash_password(pwd)))
                    conn.execute(
                        "INSERT INTO Bidders(email,first_name,last_name,home_address_id)"
                        " VALUES(?,?,?,?)",
                        (email, first, last, addr_id))
                    conn.execute(
                        "INSERT INTO Sellers(email,bank_routing_number,bank_account_number)"
                        " VALUES(?,?,?)",
                        (email, routing, account))
                    if is_vendor:
                        biz_zip = form.get("biz_zipcode","").strip()
                        conn.execute(
                            "INSERT OR IGNORE INTO Zipcode_Info(zipcode,city,state) VALUES(?,?,?)",
                            (biz_zip, form.get("biz_city","").strip(),
                             form.get("biz_state","").strip()))
                        conn.execute(
                            "INSERT INTO Address(zipcode,street_num,street_name) VALUES(?,?,?)",
                            (biz_zip or None,
                             form.get("biz_street_num","").strip() or None,
                             form.get("biz_street_name","").strip() or None))
                        biz_addr = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                        conn.execute(
                            "INSERT INTO Local_Vendors(email,business_name,"
                            "business_address_id,customer_service_phone_number) VALUES(?,?,?,?)",
                            (email,
                             form.get("business_name","").strip(),
                             biz_addr,
                             form.get("customer_service_phone","").strip() or None))
                    conn.commit(); conn.close()
                    flash("Account created! Please log in.", "success")
                    return redirect(url_for("login"))
                except Exception as ex:
                    conn.rollback()
                    errors["general"] = f"Registration failed: {ex}"
            conn.close()
    return render_template("register_seller.html", errors=errors, form=form)


# ── buyer ─────────────────────────────────────────────────────────────────────

@app.route("/buyer")
def buyer_home():
    email = require_role("buyer")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    process_ended_auctions(conn)
    bidder = conn.execute("SELECT * FROM Bidders WHERE email=?",(email,)).fetchone()
    recent = conn.execute("""
        SELECT al.seller_email, al.listing_id, al.auction_title, al.category,
               al.reserve_price, al.max_bids,
               (SELECT COUNT(*) FROM Bids b
                WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS bid_count,
               (SELECT MAX(bid_price) FROM Bids b
                WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS top_bid
        FROM Auction_Listings al
        WHERE al.status = 1
        ORDER BY al.listing_id DESC LIMIT 6
    """).fetchall()
    conn.close()
    return render_template("buyer_home.html", email=email, bidder=bidder, recent=recent)

@app.route("/buyer/profile", methods=["GET","POST"])
def edit_profile():
    email = require_role("buyer")
    if not email: return redirect(url_for("login"))
    conn   = get_db()
    errors = {}
    if request.method == "POST":
        age   = request.form.get("age","").strip()
        major = request.form.get("major","").strip()
        if age and not age.isdigit():
            errors["age"] = "Age must be a number."
        if not errors:
            conn.execute(
                "UPDATE Bidders SET age=?, major=? WHERE email=?",
                (int(age) if age.isdigit() else None, major or None, email))
            # update address
            street_num  = request.form.get("street_num","").strip()
            street_name = request.form.get("street_name","").strip()
            zipcode     = request.form.get("zipcode","").strip()
            city        = request.form.get("city","").strip()
            state       = request.form.get("state","").strip()
            if zipcode:
                conn.execute(
                    "INSERT OR IGNORE INTO Zipcode_Info(zipcode,city,state) VALUES(?,?,?)",
                    (zipcode, city, state))
            bidder = conn.execute(
                "SELECT home_address_id FROM Bidders WHERE email=?",(email,)).fetchone()
            if bidder and bidder["home_address_id"]:
                conn.execute(
                    "UPDATE Address SET zipcode=?,street_num=?,street_name=? WHERE address_id=?",
                    (zipcode or None, street_num or None, street_name or None,
                     bidder["home_address_id"]))
            conn.commit()
            flash("Profile updated.", "success")
            conn.close()
            return redirect(url_for("buyer_home"))
    bidder = conn.execute("SELECT * FROM Bidders WHERE email=?",(email,)).fetchone()
    addr   = None
    if bidder and bidder["home_address_id"]:
        addr = conn.execute(
            "SELECT a.*, z.city, z.state FROM Address a"
            " LEFT JOIN Zipcode_Info z ON a.zipcode=z.zipcode"
            " WHERE a.address_id=?",
            (bidder["home_address_id"],)).fetchone()
    cards = conn.execute(
        "SELECT * FROM Credit_Cards WHERE owner_email=?",(email,)).fetchall()
    conn.close()
    return render_template("edit_profile.html", bidder=bidder, addr=addr,
                           cards=cards, errors=errors)

@app.route("/buyer/cards/add", methods=["POST"])
def add_card():
    email = require_role("buyer")
    if not email: return redirect(url_for("login"))
    card_num = request.form.get("credit_card_num","").strip()
    if not card_num:
        flash("Card number is required.", "error")
        return redirect(url_for("edit_profile"))
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO Credit_Cards(credit_card_num,card_type,expire_month,"
            "expire_year,security_code,owner_email) VALUES(?,?,?,?,?,?)",
            (card_num,
             request.form.get("card_type","").strip() or None,
             request.form.get("expire_month","").strip() or None,
             request.form.get("expire_year","").strip() or None,
             request.form.get("security_code","").strip() or None,
             email))
        conn.commit()
        flash("Card added.", "success")
    except Exception as ex:
        flash(f"Could not add card: {ex}", "error")
    conn.close()
    return redirect(url_for("edit_profile"))

@app.route("/buyer/cards/remove/<card_num>", methods=["POST"])
def remove_card(card_num):
    email = require_role("buyer")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    conn.execute(
        "DELETE FROM Credit_Cards WHERE credit_card_num=? AND owner_email=?",
        (card_num, email))
    conn.commit(); conn.close()
    flash("Card removed.", "success")
    return redirect(url_for("edit_profile"))

@app.route("/buyer/mybids")
def my_bids():
    email = require_role("buyer")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    process_ended_auctions(conn)
    bids = conn.execute("""
        SELECT al.seller_email, al.listing_id, al.auction_title, al.status,
               al.max_bids,
               b.bid_price AS my_bid,
               (SELECT MAX(bid_price) FROM Bids b2
                WHERE b2.seller_email=al.seller_email AND b2.listing_id=al.listing_id) AS top_bid,
               (SELECT COUNT(*) FROM Bids b3
                WHERE b3.seller_email=al.seller_email AND b3.listing_id=al.listing_id) AS bid_count
        FROM Bids b
        JOIN Auction_Listings al ON b.seller_email=al.seller_email AND b.listing_id=al.listing_id
        WHERE b.bidder_email=?
        GROUP BY al.seller_email, al.listing_id
        ORDER BY b.bid_id DESC
    """,(email,)).fetchall()
    # listings where buyer won and hasn't yet rated
    won_unrated = conn.execute("""
        SELECT t.seller_email, t.listing_id FROM Transactions t
        WHERE t.buyer_email=?
          AND NOT EXISTS (
              SELECT 1 FROM Rating r
              WHERE r.bidder_email=? AND r.seller_email=t.seller_email
          )
    """,(email, email)).fetchall()
    won_keys = {(r["seller_email"], r["listing_id"]) for r in won_unrated}
    conn.close()
    return render_template("my_bids.html", bids=bids, won_keys=won_keys)

@app.route("/buyer/rate/<seller_email>/<int:listing_id>", methods=["GET","POST"])
def rate_seller(seller_email, listing_id):
    email = require_role("buyer")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    txn = conn.execute(
        "SELECT 1 FROM Transactions WHERE seller_email=? AND listing_id=? AND buyer_email=?",
        (seller_email, listing_id, email)
    ).fetchone()
    if not txn:
        flash("You can only rate sellers for auctions you won.", "error")
        conn.close(); return redirect(url_for("my_bids"))
    if request.method == "POST":
        stars = request.form.get("rating","").strip()
        desc  = request.form.get("rating_desc","").strip()
        if not stars.isdigit() or not (1 <= int(stars) <= 5):
            flash("Select a rating between 1 and 5.", "error")
        else:
            try:
                conn.execute(
                    "INSERT INTO Rating(bidder_email,seller_email,date,rating,rating_desc)"
                    " VALUES(?,?,?,?,?)",
                    (email, seller_email, today_str(), int(stars), desc or None))
                conn.commit(); conn.close()
                flash("Rating submitted!", "success")
                return redirect(url_for("my_bids"))
            except Exception as ex:
                flash(f"Could not submit rating: {ex}", "error")
    listing = conn.execute(
        "SELECT auction_title FROM Auction_Listings WHERE seller_email=? AND listing_id=?",
        (seller_email, listing_id)
    ).fetchone()
    conn.close()
    return render_template("rate_seller.html",
        listing=listing, seller_email=seller_email, listing_id=listing_id)

@app.route("/buyer/request-upgrade", methods=["GET","POST"])
def request_upgrade():
    email = require_role("buyer")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    existing = conn.execute(
        "SELECT 1 FROM Requests WHERE sender_email=? AND request_type='seller_upgrade'"
        " AND request_status=0", (email,)
    ).fetchone()
    if request.method == "POST":
        if existing:
            flash("You already have a pending upgrade request.", "info")
        else:
            desc = request.form.get("request_desc","").strip()
            conn.execute(
                "INSERT INTO Requests(sender_email,helpdesk_staff_email,request_type,"
                "request_desc,request_status) VALUES(?,?,?,?,0)",
                (email, "helpdeskteam@lsu.edu", "seller_upgrade", desc or None))
            conn.commit()
            flash("Upgrade request submitted.", "success")
        conn.close()
        return redirect(url_for("buyer_home"))
    conn.close()
    return render_template("request_upgrade.html", existing=existing)


# ── browse / product ──────────────────────────────────────────────────────────

@app.route("/browse")
def browse():
    email = require_role("buyer","seller","helpdesk")
    if not email: return redirect(url_for("login"))
    cat    = request.args.get("cat","").strip()
    search = request.args.get("q","").strip()
    conn   = get_db()
    process_ended_auctions(conn)
    tree   = build_category_tree(conn)

    current_cat = subcats = None
    products    = []

    if search:
        products = conn.execute("""
            SELECT al.seller_email, al.listing_id, al.auction_title, al.category,
                   al.reserve_price, al.max_bids,
                   (SELECT COUNT(*) FROM Bids b
                    WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS bid_count,
                   (SELECT MAX(bid_price) FROM Bids b
                    WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS top_bid
            FROM Auction_Listings al
            WHERE al.status=1
              AND (al.auction_title LIKE ? OR al.product_name LIKE ?
                   OR al.product_description LIKE ?)
            ORDER BY al.listing_id DESC
        """,(f"%{search}%",f"%{search}%",f"%{search}%")).fetchall()

    elif cat:
        current_cat = conn.execute(
            "SELECT * FROM Categories WHERE category_name=?",(cat,)).fetchone()
        subcats = conn.execute(
            "SELECT * FROM Categories WHERE parent_category=? ORDER BY category_name",(cat,)
        ).fetchall()
        # gather all descendant category names
        def all_descendants(name):
            result = [name]
            for ch in conn.execute(
                "SELECT category_name FROM Categories WHERE parent_category=?",(name,)
            ).fetchall():
                result += all_descendants(ch["category_name"])
            return result
        cat_names = all_descendants(cat)
        ph = ",".join("?"*len(cat_names))
        products = conn.execute(f"""
            SELECT al.seller_email, al.listing_id, al.auction_title, al.category,
                   al.reserve_price, al.max_bids,
                   (SELECT COUNT(*) FROM Bids b
                    WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS bid_count,
                   (SELECT MAX(bid_price) FROM Bids b
                    WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS top_bid
            FROM Auction_Listings al
            WHERE al.status=1 AND al.category IN ({ph})
            ORDER BY al.listing_id DESC
        """, cat_names).fetchall()

    conn.close()
    return render_template("browse.html",
        tree=tree, cat=cat, current_cat=current_cat,
        subcats=subcats, products=products, search=search)

@app.route("/product/<seller_email>/<int:listing_id>")
def product_detail(seller_email, listing_id):
    email = require_role("buyer","seller","helpdesk")
    if not email: return redirect(url_for("login"))
    _, role = current_user()
    conn = get_db()
    process_ended_auctions(conn)
    listing = conn.execute("""
        SELECT al.*,
               (SELECT COUNT(*) FROM Bids b
                WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS bid_count,
               (SELECT MAX(bid_price) FROM Bids b
                WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS top_bid,
               COALESCE((SELECT AVG(rating) FROM Rating r
                WHERE r.seller_email=al.seller_email), 0) AS seller_avg_rating,
               (SELECT COUNT(*) FROM Rating r WHERE r.seller_email=al.seller_email) AS seller_rating_count
        FROM Auction_Listings al
        WHERE al.seller_email=? AND al.listing_id=?
    """,(seller_email, listing_id)).fetchone()
    if not listing:
        flash("Listing not found.", "error")
        conn.close(); return redirect(url_for("browse"))
    bids = conn.execute("""
        SELECT bid_price, bidder_email FROM Bids
        WHERE seller_email=? AND listing_id=?
        ORDER BY bid_price DESC LIMIT 10
    """,(seller_email, listing_id)).fetchall()
    other = conn.execute("""
        SELECT listing_id, auction_title FROM Auction_Listings
        WHERE seller_email=? AND listing_id!=? AND status=1 LIMIT 4
    """,(seller_email, listing_id)).fetchall()
    min_bid = (listing["top_bid"] or 0) + 1
    bids_left = listing["max_bids"] - listing["bid_count"]
    can_rate = False
    if role == "buyer":
        txn = conn.execute(
            "SELECT 1 FROM Transactions WHERE seller_email=? AND listing_id=? AND buyer_email=?",
            (seller_email, listing_id, email)).fetchone()
        rated = conn.execute(
            "SELECT 1 FROM Rating WHERE bidder_email=? AND seller_email=?",
            (email, seller_email)).fetchone()
        can_rate = bool(txn) and not rated
    conn.close()
    return render_template("product_detail.html",
        listing=listing, bids=bids, other=other,
        min_bid=min_bid, bids_left=bids_left,
        role=role, viewer_email=email, can_rate=can_rate)

@app.route("/product/<seller_email>/<int:listing_id>/bid", methods=["POST"])
def place_bid(seller_email, listing_id):
    email = require_role("buyer")
    if not email: return redirect(url_for("login"))
    conn    = get_db()
    listing = conn.execute(
        "SELECT * FROM Auction_Listings WHERE seller_email=? AND listing_id=? AND status=1",
        (seller_email, listing_id)
    ).fetchone()
    if not listing:
        flash("This auction is no longer active.", "error")
        conn.close()
        return redirect(url_for("product_detail", seller_email=seller_email, listing_id=listing_id))
    if seller_email == email:
        flash("You cannot bid on your own listing.", "error")
        conn.close()
        return redirect(url_for("product_detail", seller_email=seller_email, listing_id=listing_id))
    bid_count = get_bid_count(conn, seller_email, listing_id)
    if bid_count >= listing["max_bids"]:
        flash("This auction has ended.", "error")
        conn.close()
        return redirect(url_for("product_detail", seller_email=seller_email, listing_id=listing_id))
    try:
        amount = float(request.form.get("amount",""))
    except ValueError:
        flash("Invalid bid amount.", "error")
        conn.close()
        return redirect(url_for("product_detail", seller_email=seller_email, listing_id=listing_id))
    top = get_top_bid(conn, seller_email, listing_id) or 0
    if amount < top + 1:
        flash(f"Bid must be at least ${top+1:.2f}.", "error")
        conn.close()
        return redirect(url_for("product_detail", seller_email=seller_email, listing_id=listing_id))
    conn.execute(
        "INSERT INTO Bids(seller_email,listing_id,bidder_email,bid_price) VALUES(?,?,?,?)",
        (seller_email, listing_id, email, amount))
    conn.commit()
    # immediately process if this bid fills max_bids
    process_ended_auctions(conn)
    conn.close()
    flash(f"Bid of ${amount:.2f} placed!", "success")
    return redirect(url_for("product_detail", seller_email=seller_email, listing_id=listing_id))


# ── seller ────────────────────────────────────────────────────────────────────

@app.route("/seller")
def seller_home():
    email = require_role("seller")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    process_ended_auctions(conn)
    seller = conn.execute("SELECT * FROM Sellers WHERE email=?",(email,)).fetchone()
    listings = conn.execute("""
        SELECT al.listing_id, al.auction_title, al.status, al.reserve_price, al.max_bids,
               (SELECT COUNT(*) FROM Bids b
                WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS bid_count,
               (SELECT MAX(bid_price) FROM Bids b
                WHERE b.seller_email=al.seller_email AND b.listing_id=al.listing_id) AS top_bid
        FROM Auction_Listings al WHERE al.seller_email=?
        ORDER BY al.listing_id DESC
    """,(email,)).fetchall()
    avg_rating = conn.execute(
        "SELECT AVG(rating) FROM Rating WHERE seller_email=?",(email,)).fetchone()[0]
    rating_count = conn.execute(
        "SELECT COUNT(*) FROM Rating WHERE seller_email=?",(email,)).fetchone()[0]
    is_vendor = conn.execute(
        "SELECT 1 FROM Local_Vendors WHERE email=?",(email,)).fetchone()
    conn.close()
    return render_template("seller_home.html",
        email=email, seller=seller, listings=listings,
        avg_rating=avg_rating, rating_count=rating_count, is_vendor=is_vendor)

@app.route("/seller/list", methods=["GET","POST"])
def list_product():
    email = require_role("seller")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    errors, form = {}, {}
    # leaf categories only
    categories = conn.execute("""
        SELECT category_name FROM Categories
        WHERE category_name NOT IN
              (SELECT DISTINCT parent_category FROM Categories WHERE parent_category IS NOT NULL)
        ORDER BY category_name
    """).fetchall()
    if request.method == "POST":
        form    = request.form.to_dict()
        title   = form.get("auction_title","").strip()
        cat     = form.get("category","").strip()
        reserve = form.get("reserve_price","").strip()
        maxb    = form.get("max_bids","").strip()
        if not title:  errors["auction_title"] = "Required."
        if not cat:    errors["category"]      = "Select a category."
        if not reserve:errors["reserve_price"] = "Required."
        else:
            try:
                if float(reserve) <= 0: errors["reserve_price"] = "Must be > 0."
            except: errors["reserve_price"] = "Enter a valid number."
        if not maxb:   errors["max_bids"] = "Required."
        else:
            try:
                if int(maxb) < 1: errors["max_bids"] = "Must be at least 1."
            except: errors["max_bids"] = "Must be a whole number."
        if not errors:
            # next listing_id for this seller
            last = conn.execute(
                "SELECT MAX(listing_id) FROM Auction_Listings WHERE seller_email=?",(email,)
            ).fetchone()[0] or 0
            new_id = last + 1
            try:
                conn.execute(
                    "INSERT INTO Auction_Listings(seller_email,listing_id,category,"
                    "auction_title,product_name,product_description,quantity,"
                    "reserve_price,max_bids,status) VALUES(?,?,?,?,?,?,?,?,?,1)",
                    (email, new_id, cat, title,
                     form.get("product_name","").strip() or None,
                     form.get("product_description","").strip() or None,
                     int(form.get("quantity","1") or 1),
                     float(reserve), int(maxb)))
                conn.commit(); conn.close()
                flash("Listing created!", "success")
                return redirect(url_for("seller_home"))
            except Exception as ex:
                errors["general"] = f"Failed: {ex}"
    conn.close()
    return render_template("list_product.html", errors=errors, form=form, categories=categories)

@app.route("/seller/listing/<int:listing_id>/terminate", methods=["POST"])
def terminate_listing(listing_id):
    email = require_role("seller")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    conn.execute(
        "UPDATE Auction_Listings SET status=0 WHERE seller_email=? AND listing_id=?",
        (email, listing_id))
    conn.commit(); conn.close()
    flash("Listing removed from market.", "success")
    return redirect(url_for("seller_home"))


# ── helpdesk ──────────────────────────────────────────────────────────────────

@app.route("/helpdesk")
def helpdesk_home():
    email = require_role("helpdesk")
    if not email: return redirect(url_for("login"))
    conn  = get_db()
    staff = conn.execute("SELECT * FROM Helpdesk WHERE email=?",(email,)).fetchone()
    pending = conn.execute("""
        SELECT r.request_id, r.sender_email, r.request_type, r.request_desc,
               r.helpdesk_staff_email
        FROM Requests r WHERE r.request_status=0 ORDER BY r.request_id
    """).fetchall()
    # marketing: auctions listed by seller major
    marketing = conn.execute("""
        SELECT b.major, COUNT(al.listing_id) AS listing_count
        FROM Auction_Listings al
        JOIN Bidders b ON al.seller_email=b.email
        WHERE b.major IS NOT NULL
        GROUP BY b.major ORDER BY listing_count DESC LIMIT 10
    """).fetchall()
    conn.close()
    return render_template("helpdesk_home.html",
        email=email, staff=staff, pending=pending, marketing=marketing)

@app.route("/helpdesk/request/<int:request_id>/assign", methods=["POST"])
def assign_request(request_id):
    email = require_role("helpdesk")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    conn.execute(
        "UPDATE Requests SET helpdesk_staff_email=? WHERE request_id=?",
        (email, request_id))
    conn.commit(); conn.close()
    flash("Request assigned to you.", "success")
    return redirect(url_for("helpdesk_home"))

@app.route("/helpdesk/request/<int:request_id>/complete", methods=["POST"])
def complete_request(request_id):
    email = require_role("helpdesk")
    if not email: return redirect(url_for("login"))
    conn = get_db()
    req  = conn.execute(
        "SELECT * FROM Requests WHERE request_id=?",(request_id,)).fetchone()
    if req:
        if req["request_type"] == "seller_upgrade":
            sender = req["sender_email"]
            # insert into Bidders if not already there
            if not conn.execute("SELECT 1 FROM Bidders WHERE email=?",(sender,)).fetchone():
                conn.execute(
                    "INSERT INTO Address(zipcode,street_num,street_name) VALUES(NULL,NULL,NULL)")
                addr = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    "INSERT INTO Bidders(email,first_name,last_name,home_address_id) VALUES(?,?,?,?)",
                    (sender, "N/A", "N/A", addr))
            conn.execute(
                "INSERT OR IGNORE INTO Sellers(email,bank_routing_number,bank_account_number)"
                " VALUES(?,?,?)", (sender,"",""))
        if req["request_type"] == "AddCategory":
            new_cat = req["request_desc"]
            if new_cat:
                conn.execute(
                    "INSERT OR IGNORE INTO Categories(parent_category,category_name) VALUES(NULL,?)",
                    (new_cat,))
        conn.execute(
            "UPDATE Requests SET request_status=1, helpdesk_staff_email=? WHERE request_id=?",
            (email, request_id))
    conn.commit(); conn.close()
    flash("Request marked complete.", "success")
    return redirect(url_for("helpdesk_home"))

@app.route("/helpdesk/categories", methods=["GET","POST"])
def manage_categories():
    if not require_role("helpdesk"): return redirect(url_for("login"))
    conn   = get_db()
    errors = {}
    if request.method == "POST":
        name   = request.form.get("category_name","").strip()
        parent = request.form.get("parent_category","").strip() or None
        if not name: errors["category_name"] = "Name is required."
        else:
            try:
                conn.execute(
                    "INSERT INTO Categories(parent_category,category_name) VALUES(?,?)",
                    (parent, name))
                conn.commit()
                flash(f'Category "{name}" added.', "success")
                conn.close()
                return redirect(url_for("manage_categories"))
            except Exception as ex:
                errors["general"] = f"Failed: {ex}"
    tree     = build_category_tree(conn)
    all_cats = conn.execute(
        "SELECT * FROM Categories ORDER BY category_name").fetchall()
    conn.close()
    return render_template("manage_categories.html",
        tree=tree, all_cats=all_cats, errors=errors)


if __name__ == "__main__":
    app.run(debug=True)
