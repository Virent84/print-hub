from flask import Flask, request, redirect
import sqlite3
import os
import qrcode
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

# ==================================================
# APP CONFIG
# ==================================================
app = Flask(__name__)

DB_NAME = "printhub.db"
UPLOAD_FOLDER = "uploads"
QR_FOLDER = "static/qrcodes"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# ==================================================
# DATABASE
# ==================================================
def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
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
        status TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

def migrate_db():
    conn = get_db()
    c = conn.cursor()
    for col in ["subscription_status", "trial_end"]:
        try:
            c.execute(f"ALTER TABLE owners ADD COLUMN {col} TEXT")
        except:
            pass
    conn.commit()
    conn.close()

init_db()
migrate_db()

# ==================================================
# QR GENERATION
# ==================================================
def generate_qr(owner):
    url = f"{request.host_url.rstrip('/')}/upload?owner={owner}"
    path = f"{QR_FOLDER}/{owner}.png"
    qrcode.make(url).save(path)
    return path

# ==================================================
# HOME
# ==================================================
@app.route("/")
def home():
    return """
    <h1>PrintHub</h1>
    <p>Xerox Automation SaaS</p>
    <a href="/register">Register Shop</a> |
    <a href="/login">Owner Login</a>
    """

# ==================================================
# REGISTER OWNER
# ==================================================
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        bw = int(request.form["bw_price"])
        color = int(request.form["color_price"])
        upi = request.form["upi_id"]

        trial_end = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO owners VALUES (?,?,?,?,?,?,?)",
                (username, password, bw, color, upi, "TRIAL", trial_end)
            )
            conn.commit()
            conn.close()
        except:
            return "<h3>Owner already exists</h3>"

        qr = generate_qr(username)
        return f"""
        <h2>Shop Registered</h2>
        <p>Trial till: {trial_end}</p>
        <img src='/{qr}' width='200'><br><br>
        <a href="/login">Login</a>
        """

    return """
    <h2>Register Shop</h2>
    <form method="POST">
        Username:<br><input name="username" required><br>
        Password:<br><input type="password" name="password" required><br>
        BW Price:<br><input type="number" name="bw_price" required><br>
        Color Price:<br><input type="number" name="color_price" required><br>
        UPI ID:<br><input name="upi_id" required><br><br>
        <button>Register</button>
    </form>
    """

# ==================================================
# LOGIN
# ==================================================
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = get_db()
        owner = conn.execute(
            "SELECT * FROM owners WHERE username=?", (u,)
        ).fetchone()
        conn.close()

        if not owner or not check_password_hash(owner["password"], p):
            return "<h3>Invalid login</h3>"

        return redirect(f"/dashboard/{u}")

    return """
    <h2>Owner Login</h2>
    <form method="POST">
        Username:<br><input name="username" required><br>
        Password:<br><input type="password" name="password" required><br><br>
        <button>Login</button>
    </form>
    """

# ==================================================
# CUSTOMER UPLOAD
# ==================================================
@app.route("/upload", methods=["GET","POST"])
def upload():
    owner = request.args.get("owner")
    if not owner:
        return "<h3>Invalid QR</h3>"

    conn = get_db()
    shop = conn.execute(
        "SELECT * FROM owners WHERE username=?", (owner,)
    ).fetchone()
    conn.close()

    if not shop:
        return "<h3>Shop not found</h3>"

    if request.method == "POST":
        name = request.form["name"]
        copies = int(request.form["copies"])
        ptype = request.form["print_type"]
        file = request.files["file"]

        path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(path)

        price = shop["bw_price"] if ptype=="bw" else shop["color_price"]
        total = price * copies

        conn = get_db()
        conn.execute("""
            INSERT INTO orders
            (owner, customer_name, filename, copies, print_type, amount, status, created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (owner, name, file.filename, copies, ptype, total, "CREATED",
              datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()

        return f"""
        <h2>Payment</h2>
        <p>Amount: ₹{total}</p>
        <p>Pay to UPI: {shop['upi_id']}</p>
        <p>Owner will confirm payment</p>
        """

    return f"""
    <h2>Upload for {owner}</h2>
    <form method="POST" enctype="multipart/form-data">
        Name:<br><input name="name" required><br>
        File:<br><input type="file" name="file" required><br>
        Copies:<br><input type="number" name="copies" value="1"><br>
        Type:<br>
        <select name="print_type">
            <option value="bw">B/W</option>
            <option value="color">Color</option>
        </select><br><br>
        <button>Upload</button>
    </form>
    """

# ==================================================
# DASHBOARD (SUBSCRIPTION + ORDERS)
# ==================================================
@app.route("/dashboard/<owner>")
def dashboard(owner):
    conn = get_db()
    shop = conn.execute(
        "SELECT * FROM owners WHERE username=?", (owner,)
    ).fetchone()

    today = datetime.now().strftime("%Y-%m-%d")
    if shop["subscription_status"] != "ACTIVE" and today > shop["trial_end"]:
        conn.close()
        return f"""
        <h2>Trial Expired</h2>
        <a href="/subscribe/{owner}">Subscribe ₹199/month</a>
        """

    orders = conn.execute(
        "SELECT * FROM orders WHERE owner=? ORDER BY id DESC", (owner,)
    ).fetchall()
    conn.close()

    html = f"<h2>Dashboard – {owner}</h2><table border=1>"
    html += "<tr><th>ID</th><th>Customer</th><th>File</th><th>Amount</th><th>Status</th><th>Action</th></tr>"

    for o in orders:
        html += f"""
        <tr>
            <td>{o['id']}</td>
            <td>{o['customer_name']}</td>
            <td>{o['filename']}</td>
            <td>₹{o['amount']}</td>
            <td>{o['status']}</td>
            <td>
                <a href="/status/{o['id']}/PAID">PAID</a> |
                <a href="/status/{o['id']}/PRINTING">PRINT</a> |
                <a href="/status/{o['id']}/READY">READY</a> |
                <a href="/status/{o['id']}/COMPLETED">DONE</a>
            </td>
        </tr>
        """

    return html + "</table>"

# ==================================================
# SUBSCRIPTION
# ==================================================
@app.route("/subscribe/<owner>")
def subscribe(owner):
    return f"""
    <h2>PrintHub Pro</h2>
    <p>₹199 / month</p>
    <a href="/activate/{owner}">I Have Paid</a>
    """

@app.route("/activate/<owner>")
def activate(owner):
    conn = get_db()
    conn.execute(
        "UPDATE owners SET subscription_status='ACTIVE' WHERE username=?", (owner,)
    )
    conn.commit()
    conn.close()
    return redirect(f"/dashboard/{owner}")

# ==================================================
# ORDER STATUS
# ==================================================
@app.route("/status/<int:oid>/<status>")
def status(oid, status):
    conn = get_db()
    conn.execute(
        "UPDATE orders SET status=? WHERE id=?", (status, oid)
    )
    conn.commit()
    conn.close()
    return redirect(request.referrer)

# ==================================================
# RUN
# ==================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
