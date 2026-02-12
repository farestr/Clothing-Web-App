from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from datetime import date
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, abort
)
from flask_mysqldb import MySQL
from werkzeug.utils import secure_filename



app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST", "localhost")
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER", "root")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD", "root")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB", "clothing_store_db")
app.config["MYSQL_CURSORCLASS"] = "DictCursor"
app.config["MYSQL_AUTOCOMMIT"] = False

app.config["MYSQL_PORT"] = int(os.environ.get("MYSQL_PORT", "3306"))

# TLS/SSL (works for TiDB Cloud and other managed MySQL)
ssl_ca = os.environ.get("MYSQL_SSL_CA")
if ssl_ca:
    app.config["MYSQL_CUSTOM_OPTIONS"] = {"ssl": {"ca": ssl_ca}}

mysql = MySQL(app)

UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(os.path.join(app.root_path, UPLOAD_FOLDER), exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024



def money(value) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return Decimal("0.00")


def get_cart() -> dict[str, dict]:
    cart = session.get("cart")
    if not isinstance(cart, dict):
        cart = {}
    return cart


def save_cart(cart: dict[str, dict]) -> None:
    session["cart"] = cart
    session.modified = True


def cart_totals(cart: dict[str, dict]) -> tuple[int, Decimal]:
    total_qty = 0
    total_amount = Decimal("0.00")
    for _, row in cart.items():
        qty = int(row.get("qty", 0))
        price = money(row.get("sell_price", "0"))
        total_qty += qty
        total_amount += price * qty
    return total_qty, total_amount


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please login first.", "error")
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def fetch_one(query: str, params: tuple = ()):
    cur = mysql.connection.cursor()
    cur.execute(query, params)
    row = cur.fetchone()
    cur.close()
    return row


def fetch_all(query: str, params: tuple = ()):
    cur = mysql.connection.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def execute(query: str, params: tuple = ()) -> int:
    cur = mysql.connection.cursor()
    cur.execute(query, params)
    last_id = cur.lastrowid
    cur.close()
    return last_id


def get_current_supplier_id() -> int | None:
    """Return Supplier.SupplierID for the currently logged-in supplier user, else None."""
    if not session.get("user_id"):
        return None
    row = fetch_one("SELECT SupplierID FROM Supplier WHERE UserID=%s", (session["user_id"],))
    return int(row["SupplierID"]) if row else None


def invoice_has_status() -> bool:
    """Check if Invoice table has Status column (safe)."""
    try:
        col = fetch_one("SHOW COLUMNS FROM Invoice LIKE 'Status'")
        return col is not None
    except Exception:
        return False


HAS_STATUS = None


def inv_status_sql_select():
    global HAS_STATUS
    if HAS_STATUS is None:
        HAS_STATUS = invoice_has_status()
    return "i.Status" if HAS_STATUS else "'Pending' AS Status"


def inv_status_sql_insert():
    global HAS_STATUS
    if HAS_STATUS is None:
        HAS_STATUS = invoice_has_status()
    return HAS_STATUS



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()
    address = (request.form.get("address") or "").strip()
    phone = (request.form.get("phone") or "").strip()

    if not name or not email or not password:
        flash("Name, Email, Password are required.", "error")
        return redirect(url_for("register"))

    try:
        user_id = execute(
            """
            INSERT INTO User (Password, Name, Address, Email, Phone_Number, Role)
            VALUES (%s,%s,%s,%s,%s,'Customer')
            """,
            (password, name, address, email, phone),
        )
        execute("INSERT INTO Customer (UserID) VALUES (%s)", (user_id,))
        mysql.connection.commit()
        flash("Account created. Please login.", "success")
        return redirect(url_for("login"))

    except Exception as e:
        mysql.connection.rollback()
        msg = str(e)
        if "Duplicate" in msg or "1062" in msg:
            flash("This email already exists. Try login.", "error")
        else:
            flash(f"Register error: {e}", "error")
        return redirect(url_for("register"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()

    user = fetch_one("SELECT * FROM User WHERE Email=%s AND Password=%s", (email, password))
    if not user:
        flash("Wrong email or password.", "error")
        return redirect(url_for("login"))

    session.clear()
    session["user_id"] = user["UserID"]
    session["name"] = user["Name"]
    session["role"] = user.get("Role") or "Customer"

    flash(f"Welcome {user['Name']}!", "success")

    if session["role"] == "Admin":
        return redirect(url_for("admin_models"))
    if session["role"] == "Employee":
        return redirect(url_for("employee_invoices"))
    if session["role"] == "Supplier":
        return redirect(url_for("supplier_supply_orders"))
    return redirect(url_for("home"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))



@app.route("/")
def home():
    q = (request.args.get("q") or "").strip()
    gender = (request.args.get("gender") or "").strip()

    sql = "SELECT * FROM Model WHERE 1=1"
    params = []

    if q:
        sql += " AND (Name LIKE %s OR Description LIKE %s)"
        like = f"%{q}%"
        params.extend([like, like])

    if gender in {"Male", "Female", "Both"}:
        sql += " AND Gender = %s"
        params.append(gender)

    sql += " ORDER BY ModelID DESC"
    models = fetch_all(sql, tuple(params))

    qty, total = cart_totals(get_cart())
    return render_template("home.html", models=models, q=q, gender=gender, cart_qty=qty, cart_total=total)


@app.route("/model/<int:model_id>")
def model_detail(model_id):
    model = fetch_one("SELECT * FROM Model WHERE ModelID=%s", (model_id,))
    if not model:
        abort(404)

    items = fetch_all("""
        SELECT i.ItemID, i.Size, i.Color,
               GREATEST(inv.Quantity - inv.ReservedQuantity, 0) AS Stock
        FROM Item i
        JOIN Inventory inv ON inv.ItemID = i.ItemID AND inv.PlaceID=1
        WHERE i.ModelID=%s
    """, (model_id,))

    return render_template("model_detail.html", model=model, items=items)



@app.route("/cart")
def cart_page():
    cart = get_cart()
    qty, total = cart_totals(cart)

    for key, row in cart.items():
        stock_row = fetch_one("""
            SELECT GREATEST(Quantity - ReservedQuantity, 0) AS AvailableStock
            FROM Inventory
            WHERE PlaceID=1 AND ItemID=%s
        """, (int(key),))
        row["available_stock"] = int(stock_row["AvailableStock"])

    return render_template("cart.html", cart=cart, cart_qty=qty, cart_total=total)


@app.route("/cart/add", methods=["POST"])
def cart_add():
    item_id = request.form.get("item_id", type=int)
    if not item_id:
        abort(400)

    row = fetch_one("""
        SELECT i.ItemID, i.Size, i.Color, i.ModelID,
               m.Name, m.Sell_Price, m.Item_Image
        FROM Item i
        JOIN Model m ON m.ModelID = i.ModelID
        WHERE i.ItemID = %s
    """, (item_id,))
    if not row:
        abort(404)

    stock_row = fetch_one("""
        SELECT GREATEST(Quantity - ReservedQuantity, 0) AS AvailableStock
        FROM Inventory
        WHERE PlaceID=1 AND ItemID=%s
    """, (item_id,))
    available = int(stock_row["AvailableStock"])

    if available == 0:
        flash("Item is out of stock.", "error")
        return redirect(url_for("model_detail", model_id=row["ModelID"]))

    cart = get_cart()
    key = str(item_id)
    current_qty = int(cart.get(key, {}).get("qty", 0))
    new_qty = current_qty + 1

    if new_qty > available:
        flash(f"Not enough stock for that item. Available: {available}", "error")
        return redirect(url_for("model_detail", model_id=row["ModelID"]))

    cart[key] = {
        "qty": new_qty,
        "model_id": int(row["ModelID"]),
        "name": row["Name"],
        "sell_price": str(row["Sell_Price"]),
        "image": row.get("Item_Image") or "default.png",
        "size": row.get("Size") or "",
        "color": row.get("Color") or "",
    }
    save_cart(cart)
    flash("Added to cart.", "success")
    return redirect(url_for("cart_page"))


@app.route("/cart/update", methods=["POST"])
def cart_update():
    cart = get_cart()
    for key in list(cart.keys()):
        qty = request.form.get(f"qty_{key}", type=int)
        if qty is None:
            continue
        if qty <= 0:
            cart.pop(key, None)
            continue

        stock_row = fetch_one("""
            SELECT GREATEST(Quantity - ReservedQuantity, 0) AS AvailableStock
            FROM Inventory
            WHERE PlaceID=1 AND ItemID=%s
        """, (int(key),))
        available = int(stock_row["AvailableStock"])

        if available == 0:
            cart.pop(key, None)
            flash(f"Item #{key} is now out of stock and removed from cart.", "warning")
            continue

        if qty > available:
            qty = available
            flash(f"Quantity adjusted to available stock ({available}).", "warning")

        cart[key]["qty"] = qty

    save_cart(cart)
    flash("Cart updated.", "success")
    return redirect(url_for("cart_page"))


@app.route("/cart/clear", methods=["POST"])
def cart_clear():
    session.pop("cart", None)
    flash("Cart cleared.", "success")
    return redirect(url_for("cart_page"))



@app.route("/checkout", methods=["GET", "POST"])
@role_required("Customer")
def checkout():
    cart = get_cart()
    qty, total = cart_totals(cart)

    if qty == 0:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("home"))

    if request.method == "GET":
        for key, row in cart.items():
            stock_row = fetch_one("""
                SELECT GREATEST(Quantity - ReservedQuantity, 0) AS AvailableStock
                FROM Inventory
                WHERE PlaceID=1 AND ItemID=%s
            """, (int(key),))
            row["available_stock"] = int(stock_row["AvailableStock"])
        return render_template("checkout.html", cart=cart, cart_qty=qty, cart_total=total)

    customer_id = session["user_id"]

    try:
        cur = mysql.connection.cursor()

        for key, row in cart.items():
            item_id = int(key)
            want = int(row["qty"])
            cur.execute("""
                SELECT Quantity - ReservedQuantity AS AvailableStock
                FROM Inventory
                WHERE PlaceID=1 AND ItemID=%s FOR UPDATE
            """, (item_id,))
            available = int(cur.fetchone()["AvailableStock"])
            if available < want:
                mysql.connection.rollback()
                cur.close()
                flash(f"Not enough stock for Item #{item_id}. Available: {available}.", "error")
                return redirect(url_for("cart_page"))

        cur.execute("""
            INSERT INTO Invoice (CustomerID, EmployeeID, TotalAmount, Date)
            VALUES (%s, %s, %s, %s)
        """, (customer_id, None, float(total), date.today().isoformat()))
        invoice_id = cur.lastrowid

        for key, row in cart.items():
            item_id = int(key)
            qty_line = int(row["qty"])
            amount = float(row["sell_price"]) * qty_line

            cur.execute("""
                INSERT INTO Orders (InvoiceID, ItemID, Quantity, Amount)
                VALUES (%s, %s, %s, %s)
            """, (invoice_id, item_id, qty_line, amount))

            cur.execute("""
                UPDATE Inventory
                SET ReservedQuantity = ReservedQuantity + %s
                WHERE PlaceID=1 AND ItemID=%s
            """, (qty_line, item_id))

        mysql.connection.commit()
        cur.close()

        session.pop("cart", None)
        flash(f"Order placed! Invoice #{invoice_id} is Pending. Stock reserved.", "success")
        return redirect(url_for("my_invoices"))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Database error during checkout: {e}", "error")
        return redirect(url_for("checkout"))


@app.route("/my_invoices")
@role_required("Customer")
def my_invoices():
    cid = session["user_id"]
    invoices = fetch_all(
        f"""
        SELECT i.InvoiceID, i.Date, i.TotalAmount, {inv_status_sql_select()}, i.EmployeeID
        FROM Invoice i
        WHERE i.CustomerID=%s
        ORDER BY i.InvoiceID DESC
        """,
        (cid,),
    )
    return render_template("my_invoices.html", invoices=invoices)


@app.route("/my_invoices/<int:invoice_id>")
@role_required("Customer", "Employee", "Admin")
def my_invoice_view(invoice_id: int):
    user_id = session["user_id"]
    role = session.get("role")

    if role == "Customer":
        sql_constraint = "AND i.CustomerID = %s"
        params = (invoice_id, user_id)
    else:
        sql_constraint = ""
        params = (invoice_id,)

    invoice = fetch_one(
        f"""
        SELECT i.*,
               emp.Name AS EmployeeName,
               cust.Name AS CustomerName,
               cust.Email AS CustomerEmail,
               cust.Phone_Number AS CustomerPhone,
               cust.Address AS CustomerAddress
        FROM Invoice i
        LEFT JOIN User emp ON emp.UserID = i.EmployeeID
        LEFT JOIN User cust ON cust.UserID = i.CustomerID
        WHERE i.InvoiceID = %s {sql_constraint}
        """,
        params,
    )
    if not invoice:
        abort(404)

    lines = fetch_all(
        """
        SELECT o.OrderID, o.ItemID, o.Quantity, o.Amount,
               m.Name AS ModelName, it.Size, it.Color
        FROM Orders o
        JOIN Item it ON it.ItemID = o.ItemID
        JOIN Model m ON m.ModelID = it.ModelID
        WHERE o.InvoiceID = %s
        ORDER BY o.OrderID DESC
        """,
        (invoice_id,),
    )

    return render_template("invoice.html", invoice=invoice, lines=lines)



@app.route("/employee/invoices")
@role_required("Employee")
def employee_invoices():
    emp_id = session["user_id"]

    pending_orders = fetch_all("""
        SELECT i.InvoiceID, i.Date, i.TotalAmount, i.Status,
               cu.Name AS CustomerName
        FROM Invoice i
        JOIN User cu ON cu.UserID = i.CustomerID
        WHERE i.Status = 'Pending'
        ORDER BY i.InvoiceID ASC
    """)

    my_orders = fetch_all("""
        SELECT i.InvoiceID, i.Date, i.TotalAmount, i.Status,
               cu.Name AS CustomerName, i.EmployeeID
        FROM Invoice i
        JOIN User cu ON cu.UserID = i.CustomerID
        WHERE i.EmployeeID = %s AND i.Status IN ('Accepted','Prepared')
        ORDER BY i.InvoiceID DESC
    """, (emp_id,))

    completed_orders = fetch_all("""
        SELECT i.InvoiceID, i.Date, i.TotalAmount, i.Status,
               cu.Name AS CustomerName, i.EmployeeID
        FROM Invoice i
        JOIN User cu ON cu.UserID = i.CustomerID
        WHERE i.EmployeeID = %s AND i.Status = 'Completed'
        ORDER BY i.InvoiceID DESC
    """, (emp_id,))

    return render_template(
        "employee_invoices.html",
        pending_orders=pending_orders,
        my_orders=my_orders,
        completed_orders=completed_orders
    )


@app.route("/employee/invoices/<int:invoice_id>/accept", methods=["POST"])
@role_required("Employee")
def employee_accept_invoice(invoice_id: int):
    emp_id = session["user_id"]
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM Invoice WHERE InvoiceID=%s FOR UPDATE", (invoice_id,))
        inv = cur.fetchone()
        if not inv:
            cur.close()
            abort(404)

        if inv["Status"] != "Pending":
            cur.close()
            flash("This invoice is not Pending.", "warning")
            return redirect(url_for("employee_invoices"))

        cur.execute(
            "UPDATE Invoice SET EmployeeID=%s, Status='Accepted' WHERE InvoiceID=%s",
            (emp_id, invoice_id)
        )

        mysql.connection.commit()
        cur.close()
        flash(f"Invoice #{invoice_id} accepted.", "success")
        return redirect(url_for("employee_invoices"))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error accepting invoice: {e}", "error")
        return redirect(url_for("employee_invoices"))


@app.route("/employee/invoices/<int:invoice_id>/prepare", methods=["POST"])
@role_required("Employee")
def employee_prepare_invoice(invoice_id: int):
    emp_id = session["user_id"]
    inv = fetch_one("SELECT * FROM Invoice WHERE InvoiceID=%s", (invoice_id,))
    if not inv:
        abort(404)

    if inv.get("EmployeeID") != emp_id:
        flash("You can only prepare invoices you accepted.", "error")
        return redirect(url_for("employee_invoices"))

    execute("UPDATE Invoice SET Status='Prepared' WHERE InvoiceID=%s", (invoice_id,))
    mysql.connection.commit()
    flash(f"Invoice #{invoice_id} marked Prepared.", "success")
    return redirect(url_for("employee_invoices"))


@app.route("/employee/invoices/<int:invoice_id>/complete", methods=["POST"])
@role_required("Employee")
def employee_complete_invoice(invoice_id: int):
    emp_id = session["user_id"]

    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM Invoice WHERE InvoiceID=%s FOR UPDATE", (invoice_id,))
        inv = cur.fetchone()
        if not inv:
            cur.close()
            abort(404)

        if inv["EmployeeID"] != emp_id:
            cur.close()
            flash("You can only complete invoices you accepted.", "error")
            return redirect(url_for("employee_invoices"))

        if inv["Status"] not in ("Accepted", "Prepared"):
            cur.close()
            flash("Invoice must be Accepted or Prepared first.", "warning")
            return redirect(url_for("employee_invoices"))

        cur.execute("SELECT ItemID, Quantity FROM Orders WHERE InvoiceID=%s", (invoice_id,))
        lines = cur.fetchall()

        for ln in lines:
            cur.execute("""
                UPDATE Inventory
                SET Quantity = Quantity - %s,
                    ReservedQuantity = ReservedQuantity - %s
                WHERE PlaceID=1 AND ItemID=%s
            """, (ln["Quantity"], ln["Quantity"], ln["ItemID"]))

        cur.execute("UPDATE Invoice SET Status='Completed' WHERE InvoiceID=%s", (invoice_id,))
        mysql.connection.commit()
        cur.close()

        flash(f"Invoice #{invoice_id} completed. Stock updated.", "success")
        return redirect(url_for("employee_invoices"))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error completing invoice: {e}", "error")
        return redirect(url_for("employee_invoices"))



@app.route("/admin/models")
@role_required("Admin")
def admin_models():
    search = request.args.get("search", "")
    place_id = request.args.get("place_id", "")
    min_price = request.args.get("min_price", "")
    max_price = request.args.get("max_price", "")
    sort_by = request.args.get("sort_by", "")

    sql = """
        SELECT 
            m.*, 
            COALESCE(SUM(inv.Quantity), 0) as TotalQuantity
        FROM Model m
        LEFT JOIN Item i ON m.ModelID = i.ModelID
        LEFT JOIN Inventory inv ON i.ItemID = inv.ItemID
    """

    params = []
    conditions = []

    if search:
        conditions.append("(m.Name LIKE %s OR m.Description LIKE %s OR m.ModelNumber LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if place_id and place_id != "all":
        conditions.append("inv.PlaceID = %s")
        params.append(place_id)

    if min_price:
        conditions.append("m.Sell_Price >= %s")
        params.append(min_price)

    if max_price:
        conditions.append("m.Sell_Price <= %s")
        params.append(max_price)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " GROUP BY m.ModelID "

    if sort_by == "quantity_desc":
        sql += " ORDER BY TotalQuantity DESC"
    elif sort_by == "quantity_asc":
        sql += " ORDER BY TotalQuantity ASC"
    elif sort_by == "price_high":
        sql += " ORDER BY m.Sell_Price DESC"
    elif sort_by == "price_low":
        sql += " ORDER BY m.Sell_Price ASC"
    else:
        sql += " ORDER BY m.ModelID DESC"

    models = fetch_all(sql, tuple(params))
    places = fetch_all("SELECT * FROM Place")

    return render_template(
        "admin_models.html",
        models=models,
        places=places,
        search=search,
        place_id=place_id,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
    )


@app.route("/admin/models/new", methods=["GET", "POST"])
@role_required("Admin")
def admin_models_new():
    suppliers = fetch_all("SELECT * FROM Supplier ORDER BY Name ASC")

    if request.method == "GET":
        return render_template("admin_model_form.html", model=None, suppliers=suppliers)

    name = request.form.get("Name", "").strip()
    model_number = request.form.get("ModelNumber", "").strip()
    gender = request.form.get("Gender", "").strip()
    description = request.form.get("Description", "").strip()
    price = request.form.get("Price", type=float)
    sell_price = request.form.get("Sell_Price", type=float)
    supplier_id = request.form.get("SupplierID", type=int)

    if not name or price is None or sell_price is None:
        flash("Name, Price, and Sell Price are required.", "error")
        return redirect(url_for("admin_models_new"))

    profit = sell_price - price

    image_file = request.files.get("product_image")
    filename = "default.png"
    if image_file and image_file.filename:
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image_file.save(os.path.join(app.root_path, image_path))

    try:
        execute(
            """
            INSERT INTO Model
            (Name, ModelNumber, Gender, Description, Price, Sell_Price, Profit, Item_Image, SupplierID)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (name, model_number, gender, description, price, sell_price, profit, filename, supplier_id),
        )
        mysql.connection.commit()
        flash("Model created successfully.", "success")
        return redirect(url_for("admin_models"))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Create error: {e}", "error")
        return redirect(url_for("admin_models_new"))


@app.route("/admin/models/<int:model_id>/edit", methods=["GET", "POST"])
@role_required("Admin")
def admin_models_edit(model_id):
    suppliers = fetch_all("SELECT * FROM Supplier ORDER BY Name ASC")
    model = fetch_one("SELECT * FROM Model WHERE ModelID=%s", (model_id,))
    if not model:
        abort(404)

    if request.method == "GET":
        return render_template("admin_model_form.html", model=model, suppliers=suppliers)

    name = request.form.get("Name", "").strip()
    model_number = request.form.get("ModelNumber", "").strip()
    gender = request.form.get("Gender", "").strip()
    description = request.form.get("Description", "").strip()
    price = request.form.get("Price", type=float)
    sell_price = request.form.get("Sell_Price", type=float)
    supplier_id = request.form.get("SupplierID", type=int)

    if not name or price is None or sell_price is None:
        flash("Name, Price, and Sell Price are required.", "error")
        return redirect(url_for("admin_models_edit", model_id=model_id))

    profit = sell_price - price

    image_file = request.files.get("product_image")
    filename = model["Item_Image"] or "default.png"
    if image_file and image_file.filename:
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image_file.save(os.path.join(app.root_path, image_path))

    try:
        execute(
            """
            UPDATE Model
            SET Name=%s, ModelNumber=%s, Gender=%s,
                Description=%s, Price=%s, Sell_Price=%s,
                Profit=%s, Item_Image=%s, SupplierID=%s
            WHERE ModelID=%s
            """,
            (name, model_number, gender, description, price, sell_price, profit, filename, supplier_id, model_id),
        )
        mysql.connection.commit()
        flash("Model updated successfully.", "success")
        return redirect(url_for("admin_models"))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Update error: {e}", "error")
        return redirect(url_for("admin_models_edit", model_id=model_id))


@app.route("/admin/models/<int:model_id>/delete", methods=["POST"])
@role_required("Admin")
def admin_models_delete(model_id):
    count = fetch_one("SELECT COUNT(*) AS c FROM Item WHERE ModelID=%s", (model_id,))
    if count and count["c"] > 0:
        flash("Cannot delete model with existing items.", "error")
        return redirect(url_for("admin_models"))

    try:
        execute("DELETE FROM Model WHERE ModelID=%s", (model_id,))
        mysql.connection.commit()
        flash("Model deleted.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"Delete error: {e}", "error")

    return redirect(url_for("admin_models"))


@app.route("/admin/models/<int:model_id>/items")
@role_required("Admin")
def admin_items(model_id):
    model = fetch_one("SELECT * FROM Model WHERE ModelID=%s", (model_id,))
    if not model:
        abort(404)

    items = fetch_all(
        """
        SELECT i.*, COALESCE(inv.Quantity, 0) AS Stock
        FROM Item i
        LEFT JOIN Inventory inv ON inv.ItemID = i.ItemID AND inv.PlaceID = 1
        WHERE i.ModelID=%s 
        ORDER BY i.ItemID DESC
        """,
        (model_id,),
    )

    return render_template("admin_items.html", model=model, items=items)


@app.route("/admin/models/<int:model_id>/items/add", methods=["POST"])
@role_required("Admin")
def admin_item_add(model_id):
    size = request.form.get("Size", "").strip()
    color = request.form.get("Color", "").strip()
    stock = request.form.get("stock", type=int) or 0

    if not size or not color:
        flash("Size and Color are required.", "error")
        return redirect(request.referrer)

    try:
        item_id = execute("INSERT INTO Item (ModelID, Size, Color) VALUES (%s, %s, %s)", (model_id, size, color))
        execute("INSERT INTO Inventory (ItemID, PlaceID, Quantity) VALUES (%s, 1, %s)", (item_id, stock))
        mysql.connection.commit()
        flash("Variant added successfully.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error: {e}", "error")

    return redirect(url_for("admin_items", model_id=model_id))


@app.route("/admin/item/<int:item_id>/stock", methods=["POST"])
@role_required("Admin")
def admin_item_stock(item_id):
    new_stock = request.form.get("stock")

    if new_stock is not None:
        try:
            execute(
                """
                INSERT INTO Inventory (ItemID, PlaceID, Quantity)
                VALUES (%s, 1, %s)
                ON DUPLICATE KEY UPDATE Quantity = %s
                """,
                (item_id, new_stock, new_stock)
            )
            mysql.connection.commit()
            flash("Stock updated successfully!", "success")
        except Exception as e:
            mysql.connection.rollback()
            flash(f"Error updating stock: {e}", "error")

    return redirect(request.referrer)


@app.route("/admin/item/<int:item_id>/delete", methods=["POST"])
@role_required("Admin")
def admin_item_delete(item_id):
    try:
        execute("DELETE FROM Inventory WHERE ItemID = %s", (item_id,))
        execute("DELETE FROM Item WHERE ItemID = %s", (item_id,))
        mysql.connection.commit()
        flash("Item deleted successfully!", "success")
    except Exception:
        mysql.connection.rollback()
        flash("Cannot delete this item because it has already been ordered by a customer.", "error")

    return redirect(request.referrer)


@app.route("/admin/suppliers")
@role_required("Admin")
def admin_suppliers():
    suppliers = fetch_all("SELECT * FROM Supplier ORDER BY Name ASC")
    return render_template("admin_suppliers.html", suppliers=suppliers)


@app.route("/admin/suppliers/new", methods=["GET", "POST"])
@role_required("Admin")
def admin_suppliers_new():
    if request.method == "GET":
        return render_template("admin_supplier_form.html", supplier=None)

    name = (request.form.get("Name") or "").strip()
    email = (request.form.get("Email") or "").strip()
    phone = (request.form.get("Phone") or "").strip()
    address = (request.form.get("Address") or "").strip()
    password = (request.form.get("Password") or "").strip()

    if not name or not email or not password:
        flash("Name, Email, and Password are required.", "error")
        return redirect(url_for("admin_suppliers_new"))

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO User (Name, Email, Password, Role)
            VALUES (%s, %s, %s, 'Supplier')
        """, (name, email, password))
        user_id = cur.lastrowid

        cur.execute("""
            INSERT INTO Supplier (Name, Email, Phone, Address, UserID)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, email, phone, address, user_id))

        mysql.connection.commit()
        cur.close()

        flash("Supplier account created successfully.", "success")
        return redirect(url_for("admin_suppliers"))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error creating supplier: {e}", "error")
        return redirect(url_for("admin_suppliers_new"))



@app.route("/admin/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@role_required("Admin")
def admin_suppliers_edit(supplier_id: int):
    supplier = fetch_one("SELECT * FROM Supplier WHERE SupplierID=%s", (supplier_id,))
    if not supplier:
        abort(404)

    if request.method == "GET":
        return render_template("admin_supplier_form.html", supplier=supplier)

    name = (request.form.get("Name") or "").strip()
    email = (request.form.get("Email") or "").strip()
    phone = (request.form.get("Phone") or "").strip()
    address = (request.form.get("Address") or "").strip()

    if not name:
        flash("Supplier Name is required.", "error")
        return redirect(url_for("admin_suppliers_edit", supplier_id=supplier_id))

    try:
        execute(
            """
            UPDATE Supplier
            SET Name=%s, Email=%s, Phone=%s, Address=%s
            WHERE SupplierID=%s
            """,
            (name, email, phone, address, supplier_id),
        )
        mysql.connection.commit()
        flash("Supplier updated successfully.", "success")
        return redirect(url_for("admin_suppliers"))
    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error updating supplier: {e}", "error")
        return redirect(url_for("admin_suppliers_edit", supplier_id=supplier_id))


@app.route("/admin/suppliers/<int:supplier_id>/delete", methods=["POST"])
@role_required("Admin")
def admin_suppliers_delete(supplier_id):
    try:
        execute("DELETE FROM Supplier WHERE SupplierID=%s", (supplier_id,))
        mysql.connection.commit()
        flash("Supplier deleted successfully.", "success")
    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error deleting supplier: {e}", "error")
    return redirect(url_for("admin_suppliers"))


@app.route("/admin/invoices")
@role_required("Admin")
def admin_invoices():
    invoices = fetch_all(
        f"""
        SELECT i.InvoiceID, i.Date, i.TotalAmount, {inv_status_sql_select()},
               cu.Name AS CustomerName,
               emp.Name AS EmployeeName
        FROM Invoice i
        JOIN User cu ON cu.UserID = i.CustomerID
        LEFT JOIN User emp ON emp.UserID = i.EmployeeID
        ORDER BY i.InvoiceID DESC
        """
    )
    return render_template("admin_invoices.html", invoices=invoices)


@app.route("/admin/orders")
@role_required("Admin")
def admin_orders():
    orders = fetch_all(
        """
        SELECT o.OrderID, o.InvoiceID, o.Quantity, o.Amount,
               m.Name AS ModelName, it.Size, it.Color
        FROM Orders o
        JOIN Item it ON it.ItemID = o.ItemID
        JOIN Model m ON m.ModelID = it.ModelID
        ORDER BY o.OrderID DESC
        """
    )
    return render_template("admin_orders.html", orders=orders)


@app.route("/admin/stats")
@role_required("Admin")
def admin_stats():
    total_sales_data = fetch_one("SELECT SUM(TotalAmount) AS Total FROM Invoice")
    total_sales = total_sales_data["Total"] if total_sales_data and total_sales_data["Total"] else 0

    invoice_count = fetch_one("SELECT COUNT(*) AS Count FROM Invoice")["Count"]
    order_count = fetch_one("SELECT COUNT(*) AS Count FROM Orders")["Count"]
    model_count = fetch_one("SELECT COUNT(*) AS Count FROM Model")["Count"]

    profit_query = """
        SELECT SUM(o.Amount - (m.Price * o.Quantity)) AS Profit
        FROM Orders o
        JOIN Item i ON o.ItemID = i.ItemID
        JOIN Model m ON i.ModelID = m.ModelID
    """
    result = fetch_one(profit_query)
    total_profit = result["Profit"] if result and result["Profit"] else 0

    return render_template(
        "admin_stats.html",
        total_sales=total_sales,
        total_invoices=invoice_count,
        total_orders=order_count,
        total_models=model_count,
        total_profit=total_profit
    )


@app.route("/admin/selling")
@role_required("Admin")
def admin_selling():
    search = request.args.get("search", "")
    sort_by = request.args.get("sort_by", "quantity_desc")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")

    sql = """
        SELECT 
            m.ModelID, 
            m.Name, 
            m.Item_Image, 
            COALESCE(SUM(o.Quantity), 0) as SoldCount,
            MAX(inv.Date) as LastSoldDate
        FROM Model m
        LEFT JOIN Item i ON m.ModelID = i.ModelID
        LEFT JOIN Orders o ON i.ItemID = o.ItemID
        LEFT JOIN Invoice inv ON o.InvoiceID = inv.InvoiceID
        WHERE 1=1 
    """

    params = []

    if search:
        sql += " AND m.Name LIKE %s"
        params.append(f"%{search}%")

    if start_date:
        sql += " AND (inv.Date >= %s OR inv.Date IS NULL)"
        params.append(start_date)

    if end_date:
        sql += " AND (inv.Date <= %s OR inv.Date IS NULL)"
        params.append(end_date)

    sql += " GROUP BY m.ModelID "

    if sort_by == "quantity_desc":
        sql += " ORDER BY SoldCount DESC"
    elif sort_by == "quantity_asc":
        sql += " ORDER BY SoldCount ASC"
    elif sort_by == "date_desc":
        sql += " ORDER BY LastSoldDate DESC"
    elif sort_by == "date_asc":
        sql += " ORDER BY LastSoldDate ASC"

    models = fetch_all(sql, tuple(params))

    return render_template(
        "admin_selling.html",
        models=models,
        search=search,
        sort_by=sort_by,
        start_date=start_date,
        end_date=end_date
    )


@app.route("/admin/employees")
@role_required("Admin")
def admin_employees():
    positions = fetch_all("SELECT DISTINCT Position FROM Employee WHERE Position IS NOT NULL AND Position != ''")
    places = fetch_all("SELECT PlaceID, Location, Type FROM Place")

    sql = """
        SELECT u.UserID, u.Name, u.Email, e.Position, e.Salary, 
               p.Location AS PlaceName, p.Type AS PlaceType
        FROM Employee e
        JOIN User u ON e.UserID = u.UserID
        LEFT JOIN Place p ON e.PlaceID = p.PlaceID
        WHERE 1=1
    """
    params = []

    name_search = request.args.get("name", "").strip()
    if name_search:
        sql += " AND u.Name LIKE %s"
        params.append(f"%{name_search}%")

    pos_search = request.args.get("position", "").strip()
    if pos_search:
        sql += " AND e.Position = %s"
        params.append(pos_search)

    place_search = request.args.get("place", "").strip()
    if place_search:
        sql += " AND e.PlaceID = %s"
        params.append(place_search)

    min_sal = request.args.get("min_salary", "").strip()
    if min_sal:
        sql += " AND e.Salary >= %s"
        params.append(min_sal)

    max_sal = request.args.get("max_salary", "").strip()
    if max_sal:
        sql += " AND e.Salary <= %s"
        params.append(max_sal)

    sql += " ORDER BY u.UserID DESC"

    employees = fetch_all(sql, tuple(params))

    return render_template(
        "admin_employees.html",
        employees=employees,
        positions=positions,
        places=places
    )


@app.route("/admin/employees/new", methods=["GET", "POST"])
@role_required("Admin")
def admin_create_employee():
    if request.method == "GET":
        return render_template("admin_employee_form.html")

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    position = (request.form.get("position") or "").strip()
    salary = request.form.get("salary", type=float) or 0
    place_id = request.form.get("place_id", type=int) or 1

    if not name or not email or not password:
        flash("Name, email and password are required.", "error")
        return redirect(url_for("admin_create_employee"))

    try:
        user_id = execute(
            """
            INSERT INTO User (Password, Name, Email, Phone_Number, Role)
            VALUES (%s,%s,%s,%s,'Employee')
            """,
            (password, name, email, phone),
        )

        execute(
            "INSERT INTO Employee (UserID, Position, Salary, PlaceID) VALUES (%s,%s,%s,%s)",
            (user_id, position, salary, place_id),
        )

        mysql.connection.commit()
        flash("Employee account created.", "success")
        return redirect(url_for("admin_employees"))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error creating employee: {e}", "error")
        return redirect(url_for("admin_create_employee"))



@app.route("/admin/supply_orders")
@role_required("Admin")
def admin_supply_orders():
    orders = fetch_all("""
        SELECT so.SupplyOrderID, so.Date, so.TotalAmount, so.Status,
               s.Name AS SupplierName,
               p.Location AS PlaceLocation,
               so.PlaceID, so.SupplierID
        FROM SupplyOrder so
        JOIN Supplier s ON s.SupplierID = so.SupplierID
        JOIN Place p ON p.PlaceID = so.PlaceID
        ORDER BY so.SupplyOrderID DESC
    """)
    return render_template("admin_supply_orders.html", orders=orders)


@app.route("/admin/supply_orders/new", methods=["GET", "POST"])
@role_required("Admin")
def admin_supply_orders_new():
    suppliers = fetch_all("SELECT * FROM Supplier ORDER BY Name ASC")
    places = fetch_all("SELECT * FROM Place ORDER BY PlaceID ASC")
    items = fetch_all("""
        SELECT it.ItemID, it.Size, it.Color, m.Name AS ModelName
        FROM Item it
        JOIN Model m ON m.ModelID = it.ModelID
        ORDER BY it.ItemID DESC
    """)

    if request.method == "GET":
        return render_template("admin_supply_order_form.html", suppliers=suppliers, places=places, items=items)

    supplier_id = request.form.get("SupplierID", type=int)
    place_id = request.form.get("PlaceID", type=int)
    date_str = request.form.get("Date") or date.today().isoformat()

    item_ids = request.form.getlist("ItemID")
    qtys = request.form.getlist("Quantity")
    costs = request.form.getlist("UnitCost")

    if not supplier_id or not place_id:
        flash("Supplier and Place are required.", "error")
        return redirect(url_for("admin_supply_orders_new"))

    lines = []
    for i in range(len(item_ids)):
        try:
            item_id = int(item_ids[i])
            q = int(qtys[i])
            c = float(costs[i])
            if q <= 0 or c < 0:
                continue
            lines.append((item_id, q, c))
        except Exception:
            continue

    if not lines:
        flash("Add at least one valid item line.", "error")
        return redirect(url_for("admin_supply_orders_new"))

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO SupplyOrder (
                SupplierID, PlaceID, CreatedByUserID,
                DeliveredBySupplierID,
                TotalAmount, Date, Status
            )
            VALUES (%s, %s, %s, NULL, 0, %s, 'Pending')
        """, (supplier_id, place_id, session["user_id"], date_str))
        so_id = cur.lastrowid

        total = 0.0
        for item_id, q, c in lines:
            amount = q * c
            total += amount
            cur.execute("""
                INSERT INTO SupplyOrderLine (SupplyOrderID, ItemID, Quantity, UnitCost, Amount)
                VALUES (%s, %s, %s, %s, %s)
            """, (so_id, item_id, q, c, amount))

        cur.execute("UPDATE SupplyOrder SET TotalAmount=%s WHERE SupplyOrderID=%s", (total, so_id))

        mysql.connection.commit()
        cur.close()

        flash(f"Supply Order #{so_id} created.", "success")
        return redirect(url_for("admin_supply_order_view", so_id=so_id))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error creating supply order: {e}", "error")
        return redirect(url_for("admin_supply_orders_new"))


@app.route("/admin/supply_orders/<int:so_id>")
@role_required("Admin")
def admin_supply_order_view(so_id: int):
    so = fetch_one("""
        SELECT so.*, s.Name AS SupplierName, p.Location AS PlaceLocation
        FROM SupplyOrder so
        JOIN Supplier s ON s.SupplierID = so.SupplierID
        JOIN Place p ON p.PlaceID = so.PlaceID
        WHERE so.SupplyOrderID=%s
    """, (so_id,))
    if not so:
        abort(404)

    lines = fetch_all("""
        SELECT sol.*, it.Size, it.Color, m.Name AS ModelName
        FROM SupplyOrderLine sol
        JOIN Item it ON it.ItemID = sol.ItemID
        JOIN Model m ON m.ModelID = it.ModelID
        WHERE sol.SupplyOrderID=%s
        ORDER BY sol.SupplyOrderLineID ASC
    """, (so_id,))

    return render_template("admin_supply_order_view.html", so=so, lines=lines)


@app.route("/admin/supply_orders/<int:so_id>/cancel", methods=["POST"])
@role_required("Admin")
def admin_supply_order_cancel(so_id: int):
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM SupplyOrder WHERE SupplyOrderID=%s FOR UPDATE", (so_id,))
        so = cur.fetchone()
        if not so:
            cur.close()
            abort(404)

        if so["Status"] != "Pending":
            cur.close()
            flash("Only Pending supply orders can be cancelled.", "warning")
            return redirect(url_for("admin_supply_order_view", so_id=so_id))

        cur.execute("UPDATE SupplyOrder SET Status='Cancelled' WHERE SupplyOrderID=%s", (so_id,))
        mysql.connection.commit()
        cur.close()

        flash("Supply order cancelled.", "success")
        return redirect(url_for("admin_supply_order_view", so_id=so_id))
    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error cancelling: {e}", "error")
        return redirect(url_for("admin_supply_order_view", so_id=so_id))




@app.route("/supplier/supply_orders")
@role_required("Supplier")
def supplier_supply_orders():
    supplier_user_id = session["user_id"]

    supplier = fetch_one("SELECT SupplierID FROM Supplier WHERE UserID=%s", (supplier_user_id,))
    if not supplier:
        abort(403)

    supplier_id = supplier["SupplierID"]

    orders = fetch_all("""
        SELECT so.SupplyOrderID, so.Date, so.TotalAmount, so.Status,
               p.Location AS PlaceLocation
        FROM SupplyOrder so
        JOIN Place p ON p.PlaceID = so.PlaceID
        WHERE so.SupplierID = %s
        ORDER BY so.SupplyOrderID DESC
    """, (supplier_id,))

    return render_template("supplier_supply_orders.html", orders=orders)


@app.route("/supplier/supply_orders/<int:so_id>")
@role_required("Supplier")
def supplier_supply_order_view(so_id: int):
    supplier_user_id = session["user_id"]

    supplier = fetch_one("SELECT SupplierID FROM Supplier WHERE UserID=%s", (supplier_user_id,))
    if not supplier:
        abort(403)

    supplier_id = supplier["SupplierID"]

    so = fetch_one("""
        SELECT so.*, s.Name AS SupplierName, p.Location AS PlaceLocation
        FROM SupplyOrder so
        JOIN Supplier s ON s.SupplierID = so.SupplierID
        JOIN Place p ON p.PlaceID = so.PlaceID
        WHERE so.SupplyOrderID=%s AND so.SupplierID=%s
    """, (so_id, supplier_id))
    if not so:
        abort(404)

    lines = fetch_all("""
        SELECT sol.*, it.Size, it.Color, m.Name AS ModelName
        FROM SupplyOrderLine sol
        JOIN Item it ON it.ItemID = sol.ItemID
        JOIN Model m ON m.ModelID = it.ModelID
        WHERE sol.SupplyOrderID=%s
        ORDER BY sol.SupplyOrderLineID ASC
    """, (so_id,))

    return render_template("supplier_supply_order_view.html", so=so, lines=lines)


@app.route("/supplier/supply_orders/<int:so_id>/deliver", methods=["POST"])
@role_required("Supplier")
def supplier_supply_order_deliver(so_id: int):
    supplier_id = get_current_supplier_id()
    if not supplier_id:
        abort(403)

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT * FROM SupplyOrder
            WHERE SupplyOrderID=%s AND SupplierID=%s
            FOR UPDATE
        """, (so_id, supplier_id))
        so = cur.fetchone()
        if not so:
            cur.close()
            abort(404)

        if so["Status"] != "Pending":
            cur.close()
            flash("Only Pending supply orders can be delivered.", "warning")
            return redirect(url_for("supplier_supply_order_view", so_id=so_id))

        cur.execute("""
            SELECT ItemID, Quantity
            FROM SupplyOrderLine
            WHERE SupplyOrderID=%s
        """, (so_id,))
        lines = cur.fetchall()

        for ln in lines:
            cur.execute("""
                INSERT INTO Inventory (PlaceID, ItemID, Quantity, ReservedQuantity)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE Quantity = Quantity + VALUES(Quantity)
            """, (so["PlaceID"], ln["ItemID"], ln["Quantity"]))

        cur.execute("""
            UPDATE SupplyOrder
            SET Status='Received',
                DeliveredBySupplierID=%s
            WHERE SupplyOrderID=%s
        """, (supplier_id, so_id))

        mysql.connection.commit()
        cur.close()

        flash("Supply order received. Inventory updated.", "success")
        return redirect(url_for("supplier_supply_order_view", so_id=so_id))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"Error delivering supply order: {e}", "error")
        return redirect(url_for("supplier_supply_order_view", so_id=so_id))



@app.errorhandler(403)
def forbidden(_):
    return render_template("errors/403.html"), 403


@app.errorhandler(404)
def not_found(_):
    return render_template("errors/404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
