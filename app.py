from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
import qrcode
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)

DB_NAME = "printhub.db"
UPLOAD_FOLDER = "uploads"
QR_FOLDER = "static/qrcodes"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# ---------------- DB ----------------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS owners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_name TEXT,
        mobile TEXT UNIQUE,
        password TEXT,
        bw_price INTEGER,
        color_price INTEGER,
        upi_id TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        customer_name TEXT,
        filename TEXT,
        copies INTEGER,
        print_type TEXT,
        amount INTEGER,
        status TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- QR ----------------
def generate_qr(owner_id):
    url = request.host_url + f"upload/{owner_id}"
    path = f"{QR_FOLDER}/{owner_id}.png"
    qrcode.make(url).save(path)
    return path

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return redirect("/register_owner")

# ---------- REGISTER OWNER ----------
@app.route("/register_owner", methods=["GET", "POST"])
def register_owner():
    if request.method == "POST":
        shop_name = request.form["shop_name"]
        mobile = request.form["mobile"]
        password = generate_password_hash(request.form["password"])
        bw_price = request.form["bw_price"]
        color_price = request.form["color_price"]
        upi_id = request.form["upi_id"]

        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO owners 
            (shop_name, mobile, password, bw_price, color_price, upi_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (shop_name, mobile, password, bw_price, color_price, upi_id, datetime.now()))
            conn.commit()
            owner_id = cur.lastrowid
        except sqlite3.IntegrityError:
            conn.close()
            return "Mobile already registered ❌"
        conn.close()

        generate_qr(owner_id)
        return redirect("/login")

    return render_template("register_owner.html")

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form["mobile"]
        password = request.form["password"]

        conn = get_db()
        owner = conn.execute(
            "SELECT * FROM owners WHERE mobile=?", (mobile,)
        ).fetchone()
        conn.close()

        if not owner or not check_password_hash(owner["password"], password):
            return "Invalid login ❌"

        return redirect(f"/dashboard/{owner['id']}")

    return render_template("login.html")

# ---------- CUSTOMER UPLOAD ----------
@app.route("/upload/<int:owner_id>", methods=["GET", "POST"])
def upload(owner_id):
    conn = get_db()
    owner = conn.execute(
        "SELECT * FROM owners WHERE id=?", (owner_id,)
    ).fetchone()
    conn.close()

    if not owner:
        return "Invalid QR ❌"

    if request.method == "POST":
        name = request.form["name"]
        copies = int(request.form["copies"])
        print_type = request.form["print_type"]
        file = request.files["file"]

        if not file:
            return "No file ❌"

        filename = file.filename
        file.save(os.path.join(UPLOAD_FOLDER, filename))

        price = owner["bw_price"] if print_type == "bw" else owner["color_price"]
        total = price * copies

        conn = get_db()
        conn.execute("""
        INSERT INTO orders 
        (owner_id, customer_name, filename, copies, print_type, amount, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (owner_id, name, filename, copies, print_type, total, "CREATED", datetime.now()))
        conn.commit()
        conn.close()

        return f"Payment Amount ₹{total} (Demo)"

    return render_template("upload.html", owner=owner)

# ---------- DASHBOARD ----------
@app.route("/dashboard/<int:owner_id>")
def dashboard(owner_id):
    conn = get_db()
    owner = conn.execute(
        "SELECT * FROM owners WHERE id=?", (owner_id,)
    ).fetchone()

    orders = conn.execute(
        "SELECT * FROM orders WHERE owner_id=? ORDER BY id DESC",
        (owner_id,)
    ).fetchall()
    conn.close()

    return render_template("dashboard.html", owner=owner, orders=orders)

# ---------- STATUS ----------
@app.route("/status/<int:order_id>/<status>")
def update_status(order_id, status):
    conn = get_db()
    conn.execute(
        "UPDATE orders SET status=? WHERE id=?",
        (status, order_id)
    )
    conn.commit()
    conn.close()
    return redirect(request.referrer)

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
