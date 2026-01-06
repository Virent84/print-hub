from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
import qrcode

# -------------------- APP SETUP --------------------

app = Flask(__name__)

DB_NAME = "printhub.db"
UPLOAD_FOLDER = "uploads"
QR_FOLDER = "static/qrcodes"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# -------------------- DATABASE --------------------

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
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

# IMPORTANT: initialize DB for Gunicorn + Render
init_db()

# -------------------- QR GENERATION --------------------

def generate_owner_qr(owner):
    base_url = request.host_url.rstrip("/")
    url = f"{base_url}/upload?owner={owner}"

    qr_path = os.path.join(QR_FOLDER, f"{owner}.png")
    qrcode.make(url).save(qr_path)
    return qr_path

# -------------------- ROUTES --------------------

@app.route("/")
def home():
    return render_template("home.html")

# -------------------- OWNER REGISTER --------------------

@app.route("/register_owner", methods=["GET", "POST"])
def register_owner():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        bw_price = request.form.get("bw_price")
        color_price = request.form.get("color_price")
        upi_id = request.form.get("upi_id")

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO owners VALUES (?, ?, ?, ?, ?)",
                (username, password, bw_price, color_price, upi_id)
            )
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            return "<h3>Owner already exists ❌</h3>"

        qr_path = generate_owner_qr(username)

        return f"""
            <h2>Owner Registered ✅</h2>

            <p><b>Scan this QR for customers:</b></p>
            <img src='/{qr_path}' width='200'><br><br>

            <hr>

            <p><b>Owner actions:</b></p>
            <a href="/login">
                <button style="padding:10px 20px;">Owner Login</button>
            </a>
            """

    return render_template("register_owner.html")

# -------------------- OWNER LOGIN --------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_db_connection()
        owner = conn.execute(
            "SELECT * FROM owners WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if owner:
            return f"""
            <h2>Login Successful ✅</h2>
            <p>Welcome, {username}</p>
            <p>This is where owner dashboard will come.</p>
            """
        else:
            return "<h3>Invalid username or password ❌</h3>"

    return """
    <h2>Owner Login</h2>
    <form method="POST">
        <label>Username:</label><br>
        <input type="text" name="username" required><br><br>

        <label>Password:</label><br>
        <input type="password" name="password" required><br><br>

        <button type="submit">Login</button>
    </form>
    """


# -------------------- CUSTOMER UPLOAD --------------------

@app.route("/upload", methods=["GET", "POST"])
def upload():
    owner = request.args.get("owner")
    if not owner:
        return "<h3>Invalid or missing owner ❌</h3>"

    conn = get_db_connection()
    owner_data = conn.execute(
        "SELECT * FROM owners WHERE username=?",
        (owner,)
    ).fetchone()
    conn.close()

    if not owner_data:
        return "<h3>Owner not found ❌</h3>"

    if request.method == "POST":
        customer_name = request.form.get("name")
        copies = int(request.form.get("copies"))
        print_type = request.form.get("print_type")
        file = request.files.get("file")

        if not file:
            return "<h3>No file uploaded ❌</h3>"

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        price = (
            owner_data["bw_price"]
            if print_type == "bw"
            else owner_data["color_price"]
        )

        total = price * copies

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO orders (owner, customer_name, filename, copies, print_type, amount, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (owner, customer_name, file.filename, copies, print_type, total, "Pending"))
        conn.commit()
        conn.close()

        return f"""
        <h2>Payment Page</h2>
        <p>Amount: ₹{total}</p>
        <p>Pay to UPI: {owner_data['upi_id']}</p>
        <p><b>Demo Mode:</b> Payment assumed successful</p>
        """

    return render_template("upload.html", owner=owner)

# -------------------- RUN --------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
