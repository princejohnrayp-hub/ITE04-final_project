"""
Sales and Order Management System
Flow: HTML form -> Flask route -> Python logic -> parameterized SQL -> SQLite
      -> result back to Python -> Jinja2 template -> HTML page
"""
import os
import sys
import sqlite3
from datetime import datetime

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, g)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "sales.db")

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

STATUSES = ["Pending", "Confirmed", "Completed", "Cancelled"]
# Allowed status transitions (order workflow)
TRANSITIONS = {
    "Pending":   ["Confirmed", "Cancelled"],
    "Confirmed": ["Completed", "Cancelled"],
    "Completed": [],
    "Cancelled": [],
}
SOLD_STATUSES = ("Confirmed", "Completed")   # counted as sales


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        # isolation_level=None -> we control transactions manually (BEGIN/COMMIT)
        g.db = sqlite3.connect(DATABASE, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    with open(os.path.join(BASE_DIR, "schema.sql")) as f:
        db.executescript(f.read())
    db.commit()
    db.close()


def seed_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executemany("INSERT OR IGNORE INTO products (name, price, stock) VALUES (?,?,?)",
                   [("Notebook", 45.00, 100), ("Ballpen (Blue)", 12.50, 250),
                    ("Backpack", 899.00, 15), ("Calculator", 350.00, 30)])
    if db.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
        db.executemany("INSERT INTO customers (name, contact) VALUES (?,?)",
                       [("Juan Dela Cruz", "0917-123-4567"),
                        ("Maria Santos", "maria@example.com")])
    db.commit()
    db.close()


# --------------------------------------------------------------- validation
def clean_text(value, max_len=100):
    return (value or "").strip()[:max_len]


def parse_price(value):
    try:
        price = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    return price if price >= 0 else None


def parse_int(value, minimum=0):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= minimum else None


@app.template_filter("peso")
def peso(value):
    return "₱{:,.2f}".format(value or 0)


@app.errorhandler(404)
def not_found(e):
    flash("The page or record you requested was not found.", "danger")
    return redirect(url_for("dashboard"))


@app.errorhandler(sqlite3.Error)
def db_error(e):
    flash(f"Database error: {e}", "danger")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------- dashboard
@app.route("/")
def dashboard():
    db = get_db()
    stats = {
        "products":  db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "customers": db.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "pending":   db.execute("SELECT COUNT(*) FROM orders WHERE status='Pending'").fetchone()[0],
        "revenue":   db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status IN (?,?)",
                                SOLD_STATUSES).fetchone()[0],
    }
    low_stock = db.execute("SELECT * FROM products WHERE stock <= 10 ORDER BY stock").fetchall()
    recent = db.execute("""SELECT o.*, c.name AS customer FROM orders o
                           JOIN customers c ON c.customer_id = o.customer_id
                           ORDER BY o.order_id DESC LIMIT 5""").fetchall()
    return render_template("index.html", stats=stats, low_stock=low_stock, recent=recent)


# ----------------------------------------------------------------- products
@app.route("/products")
def products():
    q = clean_text(request.args.get("q"))
    rows = get_db().execute(
        "SELECT * FROM products WHERE name LIKE ? ORDER BY name", (f"%{q}%",)).fetchall()
    return render_template("products.html", products=rows, q=q)


def read_product_form():
    name = clean_text(request.form.get("name"))
    price = parse_price(request.form.get("price"))
    stock = parse_int(request.form.get("stock"), 0)
    errors = []
    if not name:
        errors.append("Product name is required.")
    if price is None:
        errors.append("Price must be a number that is 0 or higher.")
    if stock is None:
        errors.append("Stock must be a whole number that is 0 or higher.")
    return name, price, stock, errors


@app.route("/products/new", methods=["GET", "POST"])
def product_new():
    if request.method == "POST":
        name, price, stock, errors = read_product_form()
        if not errors:
            try:
                get_db().execute("INSERT INTO products (name, price, stock) VALUES (?,?,?)",
                                 (name, price, stock))
                flash(f"Product '{name}' was added.", "success")
                return redirect(url_for("products"))
            except sqlite3.IntegrityError:
                errors.append("A product with that name already exists.")
        for e in errors:
            flash(e, "danger")
        return render_template("product_form.html", product=request.form, editing=False)
    return render_template("product_form.html", product={}, editing=False)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def product_edit(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE product_id=?", (product_id,)).fetchone()
    if product is None:
        flash("Product not found.", "danger")
        return redirect(url_for("products"))
    if request.method == "POST":
        name, price, stock, errors = read_product_form()
        if not errors:
            try:
                db.execute("UPDATE products SET name=?, price=?, stock=? WHERE product_id=?",
                           (name, price, stock, product_id))
                flash("Product updated.", "success")
                return redirect(url_for("products"))
            except sqlite3.IntegrityError:
                errors.append("A product with that name already exists.")
        for e in errors:
            flash(e, "danger")
        return render_template("product_form.html", product=request.form, editing=True,
                               product_id=product_id)
    return render_template("product_form.html", product=product, editing=True,
                           product_id=product_id)


@app.route("/products/<int:product_id>/delete", methods=["POST"])
def product_delete(product_id):
    try:
        get_db().execute("DELETE FROM products WHERE product_id=?", (product_id,))
        flash("Product deleted.", "success")
    except sqlite3.IntegrityError:
        flash("Cannot delete this product because it appears in existing orders.", "danger")
    return redirect(url_for("products"))


# ---------------------------------------------------------------- customers
@app.route("/customers")
def customers():
    q = clean_text(request.args.get("q"))
    rows = get_db().execute(
        "SELECT * FROM customers WHERE name LIKE ? OR contact LIKE ? ORDER BY name",
        (f"%{q}%", f"%{q}%")).fetchall()
    return render_template("customers.html", customers=rows, q=q)


def read_customer_form():
    name = clean_text(request.form.get("name"))
    contact = clean_text(request.form.get("contact"))
    errors = []
    if not name:
        errors.append("Customer name is required.")
    if not contact:
        errors.append("Contact information is required.")
    return name, contact, errors


@app.route("/customers/new", methods=["GET", "POST"])
def customer_new():
    if request.method == "POST":
        name, contact, errors = read_customer_form()
        if not errors:
            get_db().execute("INSERT INTO customers (name, contact) VALUES (?,?)", (name, contact))
            flash(f"Customer '{name}' was added.", "success")
            return redirect(url_for("customers"))
        for e in errors:
            flash(e, "danger")
        return render_template("customer_form.html", customer=request.form, editing=False)
    return render_template("customer_form.html", customer={}, editing=False)


@app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
def customer_edit(customer_id):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
    if customer is None:
        flash("Customer not found.", "danger")
        return redirect(url_for("customers"))
    if request.method == "POST":
        name, contact, errors = read_customer_form()
        if not errors:
            db.execute("UPDATE customers SET name=?, contact=? WHERE customer_id=?",
                       (name, contact, customer_id))
            flash("Customer updated.", "success")
            return redirect(url_for("customers"))
        for e in errors:
            flash(e, "danger")
        return render_template("customer_form.html", customer=request.form, editing=True,
                               customer_id=customer_id)
    return render_template("customer_form.html", customer=customer, editing=True,
                           customer_id=customer_id)


@app.route("/customers/<int:customer_id>/delete", methods=["POST"])
def customer_delete(customer_id):
    try:
        get_db().execute("DELETE FROM customers WHERE customer_id=?", (customer_id,))
        flash("Customer deleted.", "success")
    except sqlite3.IntegrityError:
        flash("Cannot delete this customer because they have order history.", "danger")
    return redirect(url_for("customers"))


# ------------------------------------------------------------------- orders
@app.route("/orders")
def orders():
    status = clean_text(request.args.get("status"))
    q = clean_text(request.args.get("q"))
    sql = """SELECT o.*, c.name AS customer,
                    (SELECT COALESCE(SUM(quantity),0) FROM order_items WHERE order_id=o.order_id) AS units
             FROM orders o JOIN customers c ON c.customer_id = o.customer_id
             WHERE c.name LIKE ?"""
    params = [f"%{q}%"]
    if status in STATUSES:
        sql += " AND o.status = ?"
        params.append(status)
    sql += " ORDER BY o.order_id DESC"
    rows = get_db().execute(sql, params).fetchall()
    return render_template("orders.html", orders=rows, statuses=STATUSES, status=status, q=q)


@app.route("/orders/new", methods=["GET", "POST"])
def order_new():
    db = get_db()
    customers_ = db.execute("SELECT * FROM customers ORDER BY name").fetchall()
    products_ = db.execute("SELECT * FROM products ORDER BY name").fetchall()

    if request.method == "POST":
        customer_id = parse_int(request.form.get("customer_id"), 1)
        errors = []
        if customer_id is None or not db.execute(
                "SELECT 1 FROM customers WHERE customer_id=?", (customer_id,)).fetchone():
            errors.append("Please select a valid customer.")

        # Collect items; merge duplicate products into one line
        items = {}
        for pid, qty in zip(request.form.getlist("product_id"), request.form.getlist("quantity")):
            if not pid:
                continue
            pid_i, qty_i = parse_int(pid, 1), parse_int(qty, 1)
            if pid_i is None or qty_i is None:
                errors.append("Each item needs a product and a quantity of at least 1.")
                break
            items[pid_i] = items.get(pid_i, 0) + qty_i
        if not items and not errors:
            errors.append("Add at least one product to the order.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("order_new.html", customers=customers_, products=products_,
                                   selected=customer_id)

        # ---- TRANSACTION: order + all items + total are saved together or not at all
        try:
            db.execute("BEGIN")
            cur = db.execute(
                "INSERT INTO orders (customer_id, order_date, status, total) VALUES (?,?,?,0)",
                (customer_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Pending"))
            order_id = cur.lastrowid
            total = 0.0
            for pid, qty in items.items():
                prod = db.execute("SELECT price FROM products WHERE product_id=?", (pid,)).fetchone()
                if prod is None:
                    raise ValueError("One of the selected products no longer exists.")
                db.execute("""INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                              VALUES (?,?,?,?)""", (order_id, pid, qty, prod["price"]))
                total += prod["price"] * qty
            db.execute("UPDATE orders SET total=? WHERE order_id=?", (round(total, 2), order_id))
            db.execute("COMMIT")
        except Exception as exc:
            if db.in_transaction:
                db.execute("ROLLBACK")
            flash(f"Order could not be created: {exc}", "danger")
            return render_template("order_new.html", customers=customers_, products=products_,
                                   selected=customer_id)

        flash(f"Order #{order_id} created (Pending). Total: {peso(total)}.", "success")
        return redirect(url_for("order_detail", order_id=order_id))

    return render_template("order_new.html", customers=customers_, products=products_,
                           selected=None)


@app.route("/orders/<int:order_id>")
def order_detail(order_id):
    db = get_db()
    order = db.execute("""SELECT o.*, c.name AS customer, c.contact
                          FROM orders o JOIN customers c ON c.customer_id=o.customer_id
                          WHERE o.order_id=?""", (order_id,)).fetchone()
    if order is None:
        flash("Order not found.", "danger")
        return redirect(url_for("orders"))
    items = db.execute("""SELECT oi.*, p.name, p.stock, oi.quantity*oi.unit_price AS subtotal
                          FROM order_items oi JOIN products p ON p.product_id=oi.product_id
                          WHERE oi.order_id=?""", (order_id,)).fetchall()
    return render_template("order_detail.html", order=order, items=items,
                           next_statuses=TRANSITIONS[order["status"]])


@app.route("/orders/<int:order_id>/status", methods=["POST"])
def order_status(order_id):
    new_status = clean_text(request.form.get("status"))
    db = get_db()
    try:
        # BEGIN IMMEDIATE locks the DB for writing so two users can't oversell stock
        db.execute("BEGIN IMMEDIATE")
        order = db.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if order is None:
            raise ValueError("Order not found.")
        if new_status not in TRANSITIONS[order["status"]]:
            raise ValueError(f"An order that is {order['status']} cannot become {new_status}.")

        items = db.execute("SELECT product_id, quantity FROM order_items WHERE order_id=?",
                           (order_id,)).fetchall()

        if new_status == "Confirmed":
            # Business rule: cannot confirm more than the stock on hand
            shortages = []
            for it in items:
                p = db.execute("SELECT name, stock FROM products WHERE product_id=?",
                               (it["product_id"],)).fetchone()
                if it["quantity"] > p["stock"]:
                    shortages.append(f"{p['name']} (ordered {it['quantity']}, in stock {p['stock']})")
            if shortages:
                raise ValueError("Not enough stock: " + "; ".join(shortages))
            for it in items:
                db.execute("UPDATE products SET stock = stock - ? WHERE product_id=?",
                           (it["quantity"], it["product_id"]))

        elif new_status == "Cancelled" and order["status"] == "Confirmed":
            # Stock was already deducted, so give it back
            for it in items:
                db.execute("UPDATE products SET stock = stock + ? WHERE product_id=?",
                           (it["quantity"], it["product_id"]))

        db.execute("UPDATE orders SET status=? WHERE order_id=?", (new_status, order_id))
        db.execute("COMMIT")
        msg = f"Order #{order_id} is now {new_status}."
        if new_status == "Confirmed":
            msg += " Inventory has been updated."
        flash(msg, "success")
    except Exception as exc:
        if db.in_transaction:
            db.execute("ROLLBACK")
        flash(str(exc), "danger")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/orders/<int:order_id>/delete", methods=["POST"])
def order_delete(order_id):
    db = get_db()
    order = db.execute("SELECT status FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if order is None:
        flash("Order not found.", "danger")
    elif order["status"] in ("Confirmed", "Completed"):
        flash("Confirmed or completed orders cannot be deleted. Cancel the order instead.", "danger")
    else:
        db.execute("DELETE FROM orders WHERE order_id=?", (order_id,))  # items cascade
        flash(f"Order #{order_id} deleted.", "success")
        return redirect(url_for("orders"))
    return redirect(url_for("order_detail", order_id=order_id))


# ------------------------------------------------------------ sales summary
@app.route("/sales")
def sales():
    db = get_db()
    totals = db.execute("""SELECT COUNT(*) AS orders, COALESCE(SUM(total),0) AS revenue
                           FROM orders WHERE status IN (?,?)""", SOLD_STATUSES).fetchone()
    units = db.execute("""SELECT COALESCE(SUM(oi.quantity),0) FROM order_items oi
                          JOIN orders o ON o.order_id=oi.order_id
                          WHERE o.status IN (?,?)""", SOLD_STATUSES).fetchone()[0]
    by_product = db.execute("""SELECT p.name, SUM(oi.quantity) AS units,
                                      SUM(oi.quantity*oi.unit_price) AS revenue
                               FROM order_items oi
                               JOIN orders o   ON o.order_id=oi.order_id
                               JOIN products p ON p.product_id=oi.product_id
                               WHERE o.status IN (?,?)
                               GROUP BY p.product_id ORDER BY revenue DESC""",
                            SOLD_STATUSES).fetchall()
    by_day = db.execute("""SELECT substr(order_date,1,10) AS day, COUNT(*) AS orders,
                                  SUM(total) AS revenue
                           FROM orders WHERE status IN (?,?)
                           GROUP BY day ORDER BY day DESC""", SOLD_STATUSES).fetchall()
    by_status = db.execute("SELECT status, COUNT(*) AS n FROM orders GROUP BY status").fetchall()
    return render_template("sales.html", totals=totals, units=units, by_product=by_product,
                           by_day=by_day, by_status=by_status)


if __name__ == "__main__":
    init_db()
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed_db()
        print("Sample data added.")
    app.run(debug=True)
