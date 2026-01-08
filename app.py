from flask import Flask, request, redirect, render_template
import sqlite3, os, qrcode
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

DB = "printhub.db"
UPLOADS = "uploads"
QR = "static/qrcodes"

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(QR, exist_ok=True)

# ---------------- DATABASE ----------------
def db():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS owners(
        username TEXT PRIMARY KEY,
        password TEXT,
        bw_price INTEGER,
        color_price INTEGER,
        upi_id TEXT,
        subscription_status TEXT,
        trial_end TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders(
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
    con.commit()
    con.close()

init_db()

# ---------------- QR ----------------
def generate_qr(owner):
    url = f"{request.host_url.rstrip('/')}/upload?owner={owner}"
    path = f"{QR}/{owner}.png"
    qrcode.make(url).save(path)
    return path

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/register_owner", methods=["GET","POST"])
def register_owner():
    if request.method == "POST":
        u = request.form["username"]
        p = generate_password_hash(request.form["password"])
        bw = int(request.form["bw_price"])
        c = int(request.form["color_price"])
        upi = request.form["upi_id"]
        trial = (datetime.now()+timedelta(days=30)).strftime("%Y-%m-%d")

        try:
            con = db()
            con.execute(
                "INSERT INTO owners VALUES (?,?,?,?,?,?,?)",
                (u,p,bw,c,upi,"TRIAL",trial)
            )
            con.commit()
            con.close()
        except:
            return "Owner already exists"

        qr = generate_qr(u)
        return f"<h3>Registered</h3><img src='/{qr}' width='200'><br><a href='/login'>Login</a>"

    return render_template("register_owner.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        con = db()
        o = con.execute("SELECT * FROM owners WHERE username=?", (u,)).fetchone()
        con.close()

        if not o or not check_password_hash(o["password"], p):
            return "Invalid login"

        return redirect(f"/dashboard/{u}")

    return render_template("login.html")

@app.route("/upload", methods=["GET","POST"])
def upload():
    owner = request.args.get("owner")
    if not owner:
        return "Invalid QR"

    con = db()
    shop = con.execute("SELECT * FROM owners WHERE username=?", (owner,)).fetchone()
    con.close()
    if not shop:
        return "Shop not found"

    if request.method == "POST":
        name = request.form["name"]
        copies = int(request.form["copies"])
        ptype = request.form["print_type"]
        f = request.files["file"]

        f.save(os.path.join(UPLOADS, f.filename))
        price = shop["bw_price"] if ptype=="bw" else shop["color_price"]
        total = price * copies

        con = db()
        con.execute("""
        INSERT INTO orders(owner,customer_name,filename,copies,print_type,amount,status,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,(owner,name,f.filename,copies,ptype,total,"CREATED",
             datetime.now().strftime("%Y-%m-%d %H:%M")))
        con.commit()
        con.close()

        return render_template("payment.html", amount=total, upi=shop["upi_id"])

    return render_template("upload.html", owner=owner)

@app.route("/dashboard/<owner>")
def dashboard(owner):
    con = db()
    o = con.execute("SELECT * FROM owners WHERE username=?", (owner,)).fetchone()
    orders = con.execute("SELECT * FROM orders WHERE owner=? ORDER BY id DESC",(owner,)).fetchall()
    con.close()

    today = datetime.now().strftime("%Y-%m-%d")
    if o["subscription_status"]!="ACTIVE" and today>o["trial_end"]:
        return redirect(f"/subscribe/{owner}")

    return render_template("owner_dashboard.html", owner=owner, orders=orders)

@app.route("/subscribe/<owner>")
def subscribe(owner):
    return f"<h3>Pay ₹199</h3><a href='/activate/{owner}'>I have paid</a>"

@app.route("/activate/<owner>")
def activate(owner):
    con = db()
    con.execute("UPDATE owners SET subscription_status='ACTIVE' WHERE username=?", (owner,))
    con.commit()
    con.close()
    return redirect(f"/dashboard/{owner}")

@app.route("/status/<int:i>/<s>")
def status(i,s):
    con = db()
    con.execute("UPDATE orders SET status=? WHERE id=?", (s,i))
    con.commit()
    con.close()
    return redirect(request.referrer)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
