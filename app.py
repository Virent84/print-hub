from flask import Flask, render_template, request, redirect, url_for
import sqlite3, os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import qrcode

app = Flask(__name__)

DB = "printhub.db"
UPLOAD_FOLDER = "uploads"
QR_FOLDER = "static/qrcodes"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# ---------------- DB ----------------
def db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db().cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS owners(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_name TEXT,
        mobile TEXT UNIQUE,
        password TEXT,
        upi TEXT,
        paper_sizes TEXT,
        print_modes TEXT,
        orientations TEXT,
        sides TEXT,
        trial_end TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        filename TEXT,
        paper_size TEXT,
        print_mode TEXT,
        orientation TEXT,
        sides TEXT,
        pages TEXT,
        status TEXT
    )
    """)
    c.connection.commit()

init_db()

# ---------------- QR ----------------
def generate_qr(owner_id):
    url = request.host_url + f"upload?owner_id={owner_id}"
    path = f"{QR_FOLDER}/{owner_id}.png"
    qrcode.make(url).save(path)
    return path

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template("home.html")

# ---------- OWNER REGISTER ----------
@app.route("/register_owner", methods=["GET","POST"])
def register_owner():
    if request.method == "POST":
        data = request.form
        try:
            db().execute("""
            INSERT INTO owners VALUES (NULL,?,?,?,?,?,?,?,?)
            """,(
                data["shop_name"],
                data["mobile"],
                generate_password_hash(data["password"]),
                data["upi"],
                ",".join(request.form.getlist("paper")),
                ",".join(request.form.getlist("mode")),
                ",".join(request.form.getlist("orientation")),
                ",".join(request.form.getlist("side")),
                (datetime.now()+timedelta(days=30)).strftime("%Y-%m-%d")
            ))
            db().commit()
        except:
            return "Mobile already registered"

        owner_id = db().execute("SELECT id FROM owners WHERE mobile=?", (data["mobile"],)).fetchone()["id"]
        qr = generate_qr(owner_id)
        return f"<h3>Registered</h3><img src='/{qr}' width=200><br><a href='/login'>Login</a>"

    return render_template("register_owner.html")

# ---------- LOGIN ----------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        owner = db().execute("SELECT * FROM owners WHERE mobile=?", (request.form["mobile"],)).fetchone()
        if owner and check_password_hash(owner["password"], request.form["password"]):
            return redirect(f"/dashboard/{owner['id']}")
        return "Invalid Login"
    return render_template("login.html")

# ---------- CUSTOMER UPLOAD ----------
@app.route("/upload", methods=["GET","POST"])
def upload():
    owner_id = request.args.get("owner_id")
    owner = db().execute("SELECT * FROM owners WHERE id=?", (owner_id,)).fetchone()
    if not owner:
        return "Invalid QR"

    if request.method == "POST":
        f = request.files["file"]
        f.save(os.path.join(UPLOAD_FOLDER, f.filename))

        db().execute("""
        INSERT INTO orders VALUES (NULL,?,?,?,?,?,?,?,?)
        """,(
            owner_id,
            f.filename,
            request.form["paper"],
            request.form["mode"],
            request.form["orientation"],
            request.form["side"],
            request.form["pages"],
            "PAID"
        ))
        db().commit()

        return f"""
        <h2>Payment Page</h2>
        <p>Pay ₹1 to {owner['upi']}</p>
        <p><b>Demo Mode – Payment Successful</b></p>
        """

    return render_template("upload.html", owner=owner)

# ---------- DASHBOARD ----------
@app.route("/dashboard/<int:oid>")
def dashboard(oid):
    owner = db().execute("SELECT * FROM owners WHERE id=?", (oid,)).fetchone()
    orders = db().execute("SELECT * FROM orders WHERE owner_id=?", (oid,)).fetchall()
    return render_template("dashboard.html", owner=owner, orders=orders)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
