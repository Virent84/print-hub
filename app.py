from flask import Flask, render_template, request, redirect, url_for
import os
import qrcode

# -------------------------------------------------
# APP SETUP
# -------------------------------------------------
app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# -------------------------------------------------
# TEMP STORAGE (NO DATABASE YET)
# -------------------------------------------------
owners = {}   # stores owner details
orders = []   # stores all orders

# -------------------------------------------------
# HOME PAGE
# -------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html")

# -------------------------------------------------
# OWNER REGISTRATION
# -------------------------------------------------
@app.route("/register_owner", methods=["GET", "POST"])
def register_owner():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        bw_price = int(request.form.get("bw_price"))
        color_price = int(request.form.get("color_price"))

        owners[username] = {
            "password": password,
            "bw_price": bw_price,
            "color_price": color_price
        }

        qr_path = generate_owner_qr(username)

        return f"""
        <h2>Owner Registered ✅</h2>
        <p><b>Shop Name:</b> {username}</p>
        <p>Give this QR code to customers:</p>
        <img src='/{qr_path}' width='200'><br><br>
        <a href="/owner/{username}">Go to Owner Dashboard</a>
        """

    return render_template("register_owner.html")

# -------------------------------------------------
# CUSTOMER UPLOAD (OWNER-SPECIFIC)
# -------------------------------------------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    # 🔥 READ OWNER FROM FORM FIRST, THEN QUERY
    owner = request.form.get("owner") or request.args.get("owner")

    if not owner or owner not in owners:
        return "<h3>Invalid or missing owner ❌<br>Please scan the shop QR.</h3>"

    if request.method == "POST":
        customer_name = request.form.get("customer_name")
        copies = int(request.form.get("copies"))
        print_type = request.form.get("print_type")
        file = request.files.get("document")

        price_per_page = (
            owners[owner]["bw_price"]
            if print_type == "bw"
            else owners[owner]["color_price"]
        )

        total_price = copies * price_per_page

        if file:
            filename = f"{owner}_{file.filename}"
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)

            orders.append({
                "owner": owner,
                "customer": customer_name,
                "file": filename,
                "copies": copies,
                "print_type": print_type,
                "price": total_price
            })

            return redirect(url_for("owner_dashboard", owner_name=owner))

    # 🔥 PASS OWNER TO TEMPLATE
    return render_template("upload.html", owner=owner)

# -------------------------------------------------
# OWNER DASHBOARD (ORDER QUEUE)
# -------------------------------------------------
@app.route("/owner/<owner_name>")
def owner_dashboard(owner_name):
    if owner_name not in owners:
        return "<h3>Owner not found ❌</h3>"

    owner_orders = [o for o in orders if o["owner"] == owner_name]

    return render_template(
        "owner_dashboard.html",
        owner=owner_name,
        orders=owner_orders
    )

# -------------------------------------------------
# QR CODE GENERATION (PER OWNER)
# -------------------------------------------------
def generate_owner_qr(owner):
    url = f"http://10.103.204.13:5000/upload?owner={owner}"

    qr_folder = os.path.join("static", "qrcodes")
    os.makedirs(qr_folder, exist_ok=True)

    qr_path = os.path.join(qr_folder, f"{owner}_qr.png")
    qrcode.make(url).save(qr_path)

    return qr_path

# -------------------------------------------------
# RUN SERVER (PHONE + LAPTOP)
# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
