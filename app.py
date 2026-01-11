from flask import Flask, request, redirect, render_template
import sqlite3, os, qrcode
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)

DB = "printhub.db"
UPLOAD_FOLDER = "uploads"
QR_FOLDER = "static/qrcodes"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
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
        upi TEXT,
        paper_sizes TEXT,
        print_modes TEXT,
        orientations TEXT,
        sides TEXT,
        trial_end TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        filename TEXT,
        paper_size TEXT,
        print_mode TEXT,
        orientation TEXT,
        sides TEXT,
        pages TEXT,
        status TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- QR ----------------
def generate_qr(owner_id):
    url = request.host_url.rstrip("/") + f"/upload?owner_id={owner_id}"
    path = f"{QR_FOLDER}/owner_{owner_id}.png"
    qrcode.make(url).save(path)
    return path

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template("home.html")

# -------- OWNER REGISTER --------
@app.route("/register_owner", methods=["GET", "POST"])
def register_owner():
    if request.method == "POST":
        shop_name = request.form.get("shop_name")
        mobile = request.form.get("mobile")
        password = request.form.get("password")
        upi = request.form.get("upi")

        paper = ",".join(request.form.getlist("paper"))
        mode = ",".join(request.form.getlist("mode"))
        orientation = ",".join(request.form.getlist("orientation"))
        side = ",".join(request.form.getlist("side"))

        conn = get_db()

        # ✅ SAFE duplicate check
        existing = conn.execute(
            "SELECT id FROM owners WHERE mobile=?",
            (mobile,)
        ).fetchone()

        if existing:
            conn.close()
            return "<h3>❌ Mobile number already registered</h3>"

        conn.execute("""
        INSERT INTO owners (
            shop_name, mobile, password, upi,
            paper_sizes, print_modes, orientations, sides,
            trial_end, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            shop_name,
            mobile,
            generate_password_hash(password),
            upi,
            paper,
            mode,
            orientation,
            side,
            (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            datetime.now().isoformat()
        ))

        conn.commit()

        owner_id = conn.execute(
            "SELECT id FROM owners WHERE mobile=?",
            (mobile,)
        ).fetchone()["id"]

        conn.close()

        qr = generate_qr(owner_id)

        return f"""
        <h2>Shop Registered ✅</h2>
        <p>Shop: <b>{shop_name}</b></p>
        <p>Mobile: <b>{mobile}</b></p>
        <img src='/{qr}' width='200'><br><br>
        <a href="/login">Owner Login</a>
        """

    return render_template("register_owner.html")

# -------- LOGIN --------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form.get("mobile")
        password = request.form.get("password")

        conn = get_db()
        owner = conn.execute(
            "SELECT * FROM owners WHERE mobile=?",
            (mobile,)
        ).fetchone()
        conn.close()

        if not owner or not check_password_hash(owner["password"], password):
            return "<h3>❌ Invalid login</h3>"

        return redirect(f"/dashboard/{owner['id']}")

    return render_template("login.html")

# -------- CUSTOMER UPLOAD --------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    owner_id = request.args.get("owner_id")
    if not owner_id:
        return "<h3>Invalid QR</h3>"

    conn = get_db()
    owner = conn.execute(
        "SELECT * FROM owners WHERE id=?",
        (owner_id,)
    ).fetchone()
    conn.close()

    if not owner:
        return "<h3>Owner not found</h3>"

    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            return "<h3>No file uploaded</h3>"

        filename = file.filename
        file.save(os.path.join(UPLOAD_FOLDER, filename))

        conn = get_db()
        conn.execute("""
        INSERT INTO orders (
            owner_id, filename, paper_size,
            print_mode, orientation, sides,
            pages, status, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            owner_id,
            filename,
            request.form.get("paper"),
            request.form.get("mode"),
            request.form.get("orientation"),
            request.form.get("side"),
            request.form.get("pages"),
            "PAID",
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()

        return f"""
        <h2>Payment</h2>
        <p>Pay to UPI: <b>{owner['upi']}</b></p>
        <p><b>Demo mode – Payment assumed successful</b></p>
        """

    return render_template("upload.html", owner=owner)

# -------- DASHBOARD --------
@app.route("/dashboard/<int:owner_id>")
def dashboard(owner_id):
    conn = get_db()
    owner = conn.execute(
        "SELECT * FROM owners WHERE id=?",
        (owner_id,)
    ).fetchone()

    orders = conn.execute(
        "SELECT * FROM orders WHERE owner_id=? ORDER BY id DESC",
        (owner_id,)
    ).fetchall()

    conn.close()

    return render_template("dashboard.html", owner=owner, orders=orders)

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
