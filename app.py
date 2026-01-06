from flask import Flask, render_template, request, redirect, url_for, session
import os
import sqlite3
import qrcode

def init_db():
    conn = sqlite3.connect("printhub.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            username TEXT PRIMARY KEY,
            password TEXT,
            bw_price INTEGER,
            color_price INTEGER,
            upi_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT,
            customer_name TEXT,
            filename TEXT,
            copies INTEGER,
            print_type TEXT,
            amount INTEGER,
            status TEXT
        )
    """)

    conn.commit()
    conn.close()

# ------------------------------------
# APP CONFIG
# ------------------------------------
app = Flask(__name__)
init_db()
app.secret_key = "printhub_secret_key"

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ------------------------------------
# DATABASE
# ------------------------------------
def get_db_connection():
    conn = sqlite3.connect(
        "printhub.db",
        timeout=30,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            bw_price INTEGER,
            color_price INTEGER,
            upi_id TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT,
            customer TEXT,
            file TEXT,
            copies INTEGER,
            print_type TEXT,
            price INTEGER,
            status TEXT,
            txn_id TEXT
        )
    """)

    conn.commit()
    conn.close()

# ------------------------------------
# HOME
# ------------------------------------
@app.route("/")
def home():
    return render_template("home.html")

# ------------------------------------
# REGISTER OWNER
# ------------------------------------
@app.route("/register_owner", methods=["GET", "POST"])
def register_owner():
    if request.method == "POST":
        try:
            username = request.form["username"]
            password = request.form["password"]
            bw_price = int(request.form["bw_price"])
            color_price = int(request.form["color_price"])
            upi_id = request.form["upi_id"]

            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute(
                "INSERT INTO owners VALUES (?, ?, ?, ?, ?)",
                (username, password, bw_price, color_price, upi_id)
            )

            conn.commit()
            conn.close()

            qr_path = generate_owner_qr(username)

            return f"""
            <h2>Owner Registered ✅</h2>
            <p><b>Shop:</b> {username}</p>
            <img src='/{qr_path}' width='200'><br><br>
            <a href="/login">Login</a>
            """

        except sqlite3.IntegrityError:
            return "<h3>Owner already exists ❌<br>Please login.</h3>"

        except Exception as e:
            return f"<h3>Error ❌</h3><pre>{e}</pre>"

    return render_template("register_owner.html")

# ------------------------------------
# LOGIN
# ------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        owner = conn.execute(
            "SELECT * FROM owners WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if owner:
            session["owner"] = username
            return redirect(url_for("owner_dashboard", owner_name=username))

        return "<h3>Invalid login ❌</h3>"

    return render_template("login.html")

# ------------------------------------
# UPLOAD (CUSTOMER)
# ------------------------------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    owner = request.args.get("owner") or request.form.get("owner")
    if not owner:
        return "<h3>Invalid QR ❌</h3>"

    conn = get_db_connection()
    owner_data = conn.execute(
        "SELECT * FROM owners WHERE username=?",
        (owner,)
    ).fetchone()
    conn.close()

    if not owner_data:
        return "<h3>Owner not found ❌</h3>"

    if request.method == "POST":
        customer = request.form["customer_name"]
        copies = int(request.form["copies"])
        print_type = request.form["print_type"]
        file = request.files["document"]

        price_per_page = owner_data["bw_price"] if print_type == "bw" else owner_data["color_price"]
        total_price = copies * price_per_page

        filename = f"{owner}_{file.filename}"
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO orders
            (owner, customer, file, copies, print_type, price, status, txn_id)
            VALUES (?, ?, ?, ?, ?, ?, 'UNPAID', NULL)
        """, (owner, customer, filename, copies, print_type, total_price))
        conn.commit()
        conn.close()

        return redirect(url_for("payment", owner=owner, amount=total_price))

    return render_template("upload.html", owner=owner)

# ------------------------------------
# PAYMENT
# ------------------------------------
@app.route("/payment")
def payment():
    owner = request.args.get("owner")
    amount = request.args.get("amount")

    conn = get_db_connection()
    upi = conn.execute(
        "SELECT upi_id FROM owners WHERE username=?",
        (owner,)
    ).fetchone()["upi_id"]
    conn.close()

    qr = generate_upi_qr(owner, amount)

    return render_template(
        "payment.html",
        owner=owner,
        amount=amount,
        upi_id=upi,
        qr_path="/" + qr
    )

# ------------------------------------
# SUBMIT PAYMENT
# ------------------------------------
@app.route("/submit_payment", methods=["POST"])
def submit_payment():
    owner = request.form["owner"]
    txn = request.form["txn_id"]

    conn = get_db_connection()
    conn.execute("""
        UPDATE orders
        SET status='PAYMENT_INITIATED', txn_id=?
        WHERE id = (
            SELECT id FROM orders
            WHERE owner=? AND status='UNPAID'
            ORDER BY id DESC LIMIT 1
        )
    """, (txn, owner))
    conn.commit()
    conn.close()

    return redirect("/login")

# ------------------------------------
# OWNER DASHBOARD
# ------------------------------------
@app.route("/owner/<owner_name>")
def owner_dashboard(owner_name):
    if session.get("owner") != owner_name:
        return redirect("/login")

    conn = get_db_connection()
    orders = conn.execute(
        "SELECT * FROM orders WHERE owner=? ORDER BY id DESC",
        (owner_name,)
    ).fetchall()
    conn.close()

    return render_template("owner_dashboard.html", owner=owner_name, orders=orders)

# ------------------------------------
# MARK PAID
# ------------------------------------
@app.route("/mark_paid/<int:order_id>")
def mark_paid(order_id):
    conn = get_db_connection()
    conn.execute("UPDATE orders SET status='PAID' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("owner_dashboard", owner_name=session["owner"]))

# ------------------------------------
# LOGOUT
# ------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------------------------
# QR HELPERS
# ------------------------------------
from flask import request   # make sure this is already imported

def generate_owner_qr(owner):
    base_url = request.host_url.rstrip("/")
    url = f"{base_url}/upload?owner={owner}"

    os.makedirs("static/qrcodes", exist_ok=True)
    path = f"static/qrcodes/{owner}_qr.png"
    qrcode.make(url).save(path)
    return path


def generate_upi_qr(owner, amount):
    conn = get_db_connection()
    upi = conn.execute(
        "SELECT upi_id FROM owners WHERE username=?",
        (owner,)
    ).fetchone()["upi_id"]
    conn.close()

    upi_url = f"upi://pay?pa={upi}&pn={owner}&am={amount}&cu=INR"
    os.makedirs("static/qrcodes", exist_ok=True)
    path = f"static/qrcodes/upi_{owner}.png"
    qrcode.make(upi_url).save(path)
    return path

# ------------------------------------
# START
# ------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
