from flask import Flask, request, redirect
import sqlite3
import os
import qrcode
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

# --------------------------------------------------
# APP CONFIG
# --------------------------------------------------
app = Flask(__name__)

DB_NAME = "printhub.db"
UPLOAD_FOLDER = "uploads"
QR_FOLDER = "static/qrcodes"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# --------------------------------------------------
# DATABASE
# --------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            username TEXT PRIMARY KEY,
            password TEXT,
            bw_price INTEGER,
            color_price INTEGER,
            upi_id TEXT,
            subscription_status TEXT,
            trial_end TEXT
        )
    """)

    c.execute("""
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

# MUST run for Render / Gunicorn
init_db()

# --------------------------------------------------
# QR GENERATION
# --------------------------------------------------
def generate_owner_qr(owner):
    base_url = request.host_url.rstrip("/")
    url = f"{base_url}/upload?owner={owner}"

    path = f"{QR_FOLDER}/{owner}.png"
    qrcode.make(url).save(path)
    return path

# --------------------------------------------------
# ROUTES
# --------------------------------------------------

@app.route("/")
def home():
    return """
    <h1>PrintHub</h1>
    <p>QR-based Xerox Automation SaaS</p>
    <a href="/register_owner">Register Shop</a> |
    <a href="/login">Owner Login</a>
    """

# --------------------------------------------------
# OWNER REGISTRATION
# --------------------------------------------------
@app.route("/register_owner", methods=["GET", "POST"])
def register_owner():
    if request.method == "POST":
        username = request.form.get("username")
        raw_password = request.form.get("password")
        bw_price = int(request.form.get("bw_price"))
        color_price = int(request.form.get("color_price"))
        upi_id = request.form.get("upi_id")

        password = generate_password_hash(raw_password)
        trial_end = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        try:
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO owners VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, password, bw_price, color_price, upi_id, "TRIAL", trial_end)
            )
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            return "<h3>Owner already exists ❌</h3>"

        qr_path = generate_owner_qr(username)

        return f"""
        <h2>Shop Registered ✅</h2>
        <p>Free Trial till: <b>{trial_end}</b></p>
        <p>Customer QR:</p>
        <img src='/{qr_path}' width='200'><br><br>
        <a href="/login"><button>Owner Login</button></a>
        """

    return """
    <h2>Register Xerox Shop</h2>
    <form method="POST">
        Username:<br><input name="username" required><br><br>
        Password:<br><input type="password" name="password" required><br><br>
        B/W Price:<br><input type="number" name="bw_price" required><br><br>
        Color Price:<br><input type="number" name="color_price" required><br><br>
        UPI ID:<br><input name="upi_id" required><br><br>
        <button type="submit">Register</button>
    </form>
    """

# --------------------------------------------------
# OWNER LOGIN
# --------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_db_connection()
        owner = conn.execute(
            "SELECT * FROM owners WHERE username=?",
            (username,)
        ).fetchone()
        conn.close()

        if not owner or not check_password_hash(owner["password"], password):
            return "<h3>Invalid login ❌</h3>"

        return redirect(f"/dashboard/{username}")

    return """
    <h2>Owner Login</h2>
    <form method="POST">
        Username:<br><input name="username" required><br><br>
        Password:<br><input type="password" name="password" required><br><br>
        <button type="submit">Login</button>
    </form>
    """

# --------------------------------------------------
# CUSTOMER UPLOAD
# --------------------------------------------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    owner = request.args.get("owner")
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
        name = request.form.get("name")
        copies = int(request.form.get("copies"))
        print_type = request.form.get("print_type")
        file = request.files.get("file")

        if not file:
            return "<h3>No file uploaded ❌</h3>"

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        price = owner_data["bw_price"] if print_type == "bw" else owner_data["color_price"]
        total = price * copies

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO orders
            (owner, customer_name, filename, copies, print_type, amount, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (owner, name, file.filename, copies, print_type, total, "CREATED"))
        conn.commit()
        conn.close()

        return f"""
        <h2>Payment</h2>
        <p>Amount: ₹{total}</p>
        <p>Pay via UPI: {owner_data['upi_id']}</p>
        <p><b>Payment confirmed manually by shop</b></p>
        """

    return f"""
    <h2>Upload for {owner}</h2>
    <form method="POST" enctype="multipart/form-data">
        Name:<br><input name="name" required><br><br>
        File:<br><input type="file" name="file" required><br><br>
        Copies:<br><input type="number" name="copies" value="1" min="1"><br><br>
        Type:<br>
        <select name="print_type">
            <option value="bw">B/W</option>
            <option value="color">Color</option>
        </select><br><br>
        <button type="submit">Upload</button>
    </form>
    """

# --------------------------------------------------
# OWNER DASHBOARD (SUBSCRIPTION CHECK)
# --------------------------------------------------
@app.route("/dashboard/<owner>")
def dashboard(owner):
    conn = get_db_connection()
    owner_data = conn.execute(
        "SELECT * FROM owners WHERE username=?",
        (owner,)
    ).fetchone()

    today = datetime.now().strftime("%Y-%m-%d")

    if owner_data["subscription_status"] != "ACTIVE" and today > owner_data["trial_end"]:
        conn.close()
        return """
        <h2>Trial Expired ❌</h2>
        <p>Your 30-day free trial has ended.</p>
        <p>Please subscribe for ₹199/month.</p>
        """

    orders = conn.execute(
        "SELECT * FROM orders WHERE owner=? ORDER BY id DESC",
        (owner,)
    ).fetchall()
    conn.close()

    html = f"<h2>Dashboard – {owner}</h2><hr>"

    if not orders:
        return html + "<p>No orders yet.</p>"

    html += """
    <table border="1" cellpadding="8">
        <tr>
            <th>ID</th><th>Customer</th><th>File</th>
            <th>Copies</th><th>Type</th><th>Amount</th>
            <th>Status</th><th>Update</th>
        </tr>
    """

    for o in orders:
        html += f"""
        <tr>
            <td>{o['id']}</td>
            <td>{o['customer_name']}</td>
            <td>{o['filename']}</td>
            <td>{o['copies']}</td>
            <td>{o['print_type']}</td>
            <td>₹{o['amount']}</td>
            <td>{o['status']}</td>
            <td>
                <a href="/status/{o['id']}/PAID">PAID</a> |
                <a href="/status/{o['id']}/PRINTING">PRINTING</a> |
                <a href="/status/{o['id']}/READY">READY</a> |
                <a href="/status/{o['id']}/COMPLETED">DONE</a>
            </td>
        </tr>
        """

    html += "</table>"
    return html

# --------------------------------------------------
# STATUS UPDATE
# --------------------------------------------------
@app.route("/status/<int:order_id>/<new_status>")
def update_status(order_id, new_status):
    conn = get_db_connection()
    conn.execute(
        "UPDATE orders SET status=? WHERE id=?",
        (new_status, order_id)
    )
    conn.commit()
    conn.close()
    return redirect(request.referrer)

# --------------------------------------------------
# RUN
# --------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
