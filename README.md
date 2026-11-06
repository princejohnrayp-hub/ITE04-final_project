# Group 6 — Sales and Order Management System

Flask + SQLite web app for products, customers, orders, inventory and sales reports.

## Run it
```
pip install -r requirements.txt
python app.py seed      # first run: creates sales.db and adds sample data
python app.py           # later runs
```
Open http://127.0.0.1:5000

## Design
Styling lives in `static/style.css` (loaded by `templates/base.html`) on top of Bootstrap 5 and Bootstrap Icons. Fonts come from Google Fonts, so the pages need an internet connection to look their best.

## Pages (7)
Dashboard `/` · Products `/products` · Customers `/customers` · Order History `/orders`
· New Order `/orders/new` · Order Detail `/orders/<id>` · Sales Summary `/sales`
(plus add/edit forms for products and customers)

## Database (4 related tables, see schema.sql)
products ← order_items → orders → customers
- order_items.order_id → orders (ON DELETE CASCADE)
- order_items.product_id → products (RESTRICT)
- orders.customer_id → customers (RESTRICT)
- CHECK constraints: price >= 0, stock >= 0, quantity > 0, valid status values
- order_items.unit_price stores the price at the time of sale, so later price changes don't alter old orders

## How HTML → Flask → Python → SQL/SQLite work together
Example: user clicks **Confirm Order** on order #5
1. HTML: `order_detail.html` has a form that POSTs `status=Confirmed` to `/orders/5/status`
2. Flask: `@app.route("/orders/<int:order_id>/status")` receives the request
3. Python: `order_status()` validates the transition and checks stock for every item
4. SQL: `BEGIN IMMEDIATE` → `SELECT` stock → `UPDATE products SET stock = stock - ?` → `UPDATE orders SET status = ?` → `COMMIT`
   (any problem → `ROLLBACK`, so stock and status never get out of sync)
5. SQLite stores the change; Python flashes a success/error message
6. Flask redirects, Jinja2 renders `order_detail.html` with fresh data → HTML back to the browser

## Business rules
- Order totals are calculated on the server (sum of quantity × unit_price)
- Confirming is blocked if any item's quantity exceeds stock; the message lists which products are short
- Confirming deducts inventory; cancelling a confirmed order restores it
- Status flow: Pending → Confirmed → Completed; Pending/Confirmed → Cancelled
- Products with orders and customers with orders cannot be deleted
- Confirmed/Completed orders cannot be deleted (cancel instead)

## Requirement checklist
| Requirement | Where |
|---|---|
| Products with price & stock | `/products`, `product_form.html` |
| Customers, multi-item orders | `/customers`, `/orders/new` |
| Automatic totals | `order_new()` (server), JS preview in `order_new.html` |
| Status update & history | `order_status()`, `/orders` |
| Inventory deduction & sales summary | `order_status()`, `/sales` |
| CRUD on main records | products, customers (full), orders (create/read/update status/delete) |
| Search / filter | product name, customer name/contact, order status + customer |
| Complete transactions | `order_new()` (order + items + total), `order_status()` (confirm/cancel) |
| Validation, parameterized SQL, error handling | `read_product_form()`, `parse_int()`, all queries use `?` |
