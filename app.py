
from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-local-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///sanitary_store.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

PAKISTAN_TZ = ZoneInfo("Asia/Karachi")

def pakistan_now():
    return datetime.now(PAKISTAN_TZ).replace(tzinfo=None)

def format_pakistan_datetime(value):
    if value is None:
        return ""
    return value.strftime("%d-%m-%Y, %I:%M %p")

# ==================================================
# 1. DATABASE MODELS
# ==================================================

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    selling_price = db.Column(db.Float, nullable=False, default=0)
    stock_pieces = db.Column(db.Integer, nullable=False, default=0)
    carton_size = db.Column(db.Integer, nullable=False, default=12)



class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    balance = db.Column(db.Float, nullable=False, default=0)



class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(30), unique=True, nullable=False)
    date = db.Column(db.DateTime, default=pakistan_now)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    payment_type = db.Column(db.String(10), nullable=False)
    total = db.Column(db.Float, nullable=False, default=0)
    discount = db.Column(db.Float, nullable=False, default=0)
    paid_amount = db.Column(db.Float, nullable=False, default=0)
    remaining_amount = db.Column(db.Float, nullable=False, default=0)


class BillItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey("bill.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    returned_quantity = db.Column(
    db.Integer, nullable=False, default=0
)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey("bill.id"))
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=pakistan_now)
    note = db.Column(db.String(250))


# ==================================================
# 2. DATABASE SETUP
# ==================================================

with app.app_context():
    db.create_all()

    columns = db.session.execute(
        text("PRAGMA table_info(product)")
    ).fetchall()

    column_names = [column[1] for column in columns]

    if "carton_size" not in column_names:
        db.session.execute(
            text(
                "ALTER TABLE product "
                "ADD COLUMN carton_size INTEGER NOT NULL DEFAULT 12"
            )
        )
        
    # Add return tracking column to existing bills
    bill_item_columns = db.session.execute(
        text("PRAGMA table_info(bill_item)")
    ).fetchall()

    bill_item_column_names = [
        column[1] for column in bill_item_columns
    ]

    if "returned_quantity" not in bill_item_column_names:
        db.session.execute(
            text(
                "ALTER TABLE bill_item "
                "ADD COLUMN returned_quantity "
                "INTEGER NOT NULL DEFAULT 0"
            )
        )
        db.session.commit()

# ==================================================
# 3. DASHBOARD HTML
# ==================================================

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sanitary Store | Dashboard</title>
    <link rel="stylesheet"
          href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<div class="app-layout">

    <aside class="sidebar">
        <h2>✦ SANITARY STORE</h2>
       
<nav>
    <a class="active" href="{{ url_for('home') }}">▦ Dashboard</a>
    <a href="{{ url_for('inventory') }}">▤ Inventory</a>
    <a href="{{ url_for('billing') }}">Billing</a>
    <a href="{{ url_for('khata') }}">Udhaar / Khata</a>
</nav>

    </aside>

    <main class="main-content">
        <header>
            <h1>Dashboard</h1>
            <p>Midnight Black + Gold · Store Overview</p>
        </header>

        {% for message in get_flashed_messages() %}
            <div class="notice">{{ message }}</div>
        {% endfor %}

        
        <div class="stats">
            <div class="stat">
                LOW STOCK PRODUCTS
                <strong>{{ low_stock_count }}</strong>
                <span class="muted">products need restocking</span>
            </div>

            <div class="stat">
                TODAY'S SALES
                <strong>Rs. {{ daily_sales }}</strong>
            </div>

            <div class="stat">
                WEEKLY SALES
                <strong>Rs. {{ weekly_sales }}</strong>
            </div>

            <div class="stat">
                MONTHLY SALES
                <strong>Rs. {{ monthly_sales }}</strong>
            </div>

            <div class="stat">
    YEARLY SALES
    <strong>Rs. {{ yearly_sales }}</strong>
</div>
        </div>

        <section class="panel">
            <h2>Low Stock Products</h2>

            {% if low_stock_products %}
                <table>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>Available Pieces</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for product in low_stock_products %}
                        <tr>
                            <td>{{ product.name }}</td>
                            <td>{{ product.stock_pieces }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <p>Abhi koi low-stock product nahi hai.</p>
            {% endif %}
        </section>

        <section class="panel">
            <h2>Sales Chart</h2>
            <canvas id="salesChart"></canvas>
        </section>


        <footer class="footer">
            Sanitary Store Management · Midnight Gold
        </footer>
    </main>

</div>
</body>
</html>
"""


# ==================================================
# 4. INVENTORY HTML
# ==================================================

INVENTORY_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sanitary Store | Inventory</title>
    <link rel="stylesheet"
          href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<div class="app-layout">

    <aside class="sidebar">
        <h2>✦ SANITARY STORE</h2>
       
<nav>
    <a class="active" href="{{ url_for('home') }}"> Dashboard</a>
    <a href="{{ url_for('inventory') }}"> Inventory</a>
    <a href="{{ url_for('billing') }}"> Billing</a>
    <a href="{{ url_for('khata') }}">Udhaar / Khata</a>
</nav>

    </aside>

    <main class="main-content">
        <header>
            <h1>Product Inventory</h1>
            <p>Manage products, prices and stock</p>
        </header>

        {% for message in get_flashed_messages() %}
            <div class="notice">{{ message }}</div>
        {% endfor %}

        <section class="panel">
            <h2>+ Add New Product</h2>

            <form method="post" action="{{ url_for('add_product') }}">
                <label>Product name</label>
                <input name="name" placeholder="e.g. PVC Pipe"
                       required maxlength="150">

                <label>Selling price per piece (Rs.)</label>
                <input name="selling_price" type="number"
                       min="0" step="0.01" required>

                <label>Pieces in one carton</label>
                <input name="carton_size" type="number"
                       min="1" value="12" required>

                <label>Opening cartons</label>
                <input name="cartons" type="number"
                       min="0" value="0" required>

                <label>Opening loose pieces</label>
                <input name="loose" type="number"
                       min="0" value="0" required>

                <button type="submit">Save Product</button>
            </form>
        </section>

        <section class="panel">
            <h2>All Products</h2>

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Product</th>
                            <th>Price / Piece</th>
                            <th>Carton Size</th>
                            <th>Full Cartons</th>
                            <th>Loose Pieces</th>
                            <th>Total Pieces</th>
                            <th>Action</th>
                        </tr>
                    </thead>

                    <tbody>
                    {% for p in products %}
                        <tr>
                            <td>{{ p.id }}</td>
                            <td>{{ p.name }}</td>
                            <td>Rs. {{ "%.2f"|format(p.selling_price) }}</td>
                            <td>{{ p.carton_size }}</td>
                            <td>{{ p.stock_pieces // p.carton_size }}</td>
                            <td>{{ p.stock_pieces % p.carton_size }}</td>
                            <td>{{ p.stock_pieces }}</td>
                            
<td>
    <a class="update-btn"
       href="{{ url_for('edit_product', product_id=p.id) }}">
        Edit
    </a>

    <a class="update-btn"
       href="{{ url_for('update_stock_page', product_id=p.id) }}">
        Update Stock
    </a>

    <form method="POST"
          action="{{ url_for('delete_product', product_id=p.id) }}"
          onsubmit="return confirm('Kya aap waqai ye product delete karna chahte hain?');"
          style="display:inline;">
        <button type="submit">Delete</button>
    </form>
</td>

                        </tr>
                    {% else %}
                        <tr>
                            <td colspan="8" class="muted">
                                No products added yet.
                            </td>
                        </tr>
                    {% endfor %}
                    </tbody>
                </table>
            </div>
        </section>

        <footer class="footer">
            Sanitary Store Management · Midnight Gold
        </footer>
    </main>

</div>
</body>
</html>
"""
# ==================================================
#  Edit product name HTML
# ==================================

EDIT_PRODUCT_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Edit Product | Sanitary Store</title>
    <link rel="stylesheet"
          href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<div class="app-layout">
    <aside class="sidebar">
        <h2>✦ SANITARY STORE</h2>
        <nav>
            <a href="{{ url_for('home') }}">Dashboard</a>
            <a class="active" href="{{ url_for('inventory') }}">Inventory</a>
            <a href="{{ url_for('billing') }}">Billing</a>
        </nav>
    </aside>

    <main class="main-content">
        <header>
            <h1>Edit Product</h1>
            <p>Update product details without changing its current stock.</p>
        </header>

        {% for message in get_flashed_messages() %}
            <div class="notice">{{ message }}</div>
        {% endfor %}

        <section class="panel">
            <form method="POST"
                  action="{{ url_for('edit_product', product_id=product.id) }}">

                <label>Product name</label>
                <input name="name" maxlength="150"
                       value="{{ product.name }}" required>

                <label>Selling price per piece (Rs.)</label>
                <input name="selling_price" type="number"
                       min="0" step="0.01"
                       value="{{ product.selling_price }}" required>

                <label>Pieces in one carton</label>
                <input name="carton_size" type="number"
                       min="1" step="1"
                       value="{{ product.carton_size }}" required>

                <p>Current stock: {{ product.stock_pieces }} pieces</p>

                <button type="submit">Save Changes</button>
                <a class="update-btn" href="{{ url_for('inventory') }}">
                    Cancel
                </a>
            </form>
        </section>
    </main>
</div>
</body>
</html>
"""


# ==================================================
# 5. UPDATE STOCK HTML
# ==================================================

UPDATE_STOCK_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Update Stock | Sanitary Store</title>
    <link rel="stylesheet"
          href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<div class="app-layout">

    <aside class="sidebar">
        <h2>✦ SANITARY STORE</h2>
        <nav>
            <a href="{{ url_for('home') }}">▦ Dashboard</a>
            <a class="active" href="{{ url_for('inventory') }}">▤ Inventory</a>
        </nav>
    </aside>

    <main class="main-content">
        <header>
            <h1>Update Stock</h1>
            <p>{{ product.name }}</p>
        </header>

        <section class="panel">
            <p>
                Current stock:
                <strong>{{ product.stock_pieces }}</strong> pieces
            </p>

            <p>One carton contains {{ product.carton_size }} pieces.</p>

            <form method="POST">
                <label>Full cartons to add</label>
                <input type="number" name="cartons"
                       min="0" value="0" required>

                <label>Loose pieces to add</label>
                <input type="number" name="loose_pieces"
                       min="0" value="0" required>

                <button type="submit">Save Stock</button>
            </form>

            <p>
                <a href="{{ url_for('inventory') }}">Back to Inventory</a>
            </p>
        </section>
    </main>

</div>
</body>
</html>
"""
# ==================================================
# 5. Billing html
# ==================================================

BILLING_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Billing - Sanitary Store</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="app-layout">

    <aside class="sidebar">
        <h2>Sanitary Store</h2>
        
<nav>
    <a href="{{ url_for('home') }}">Dashboard</a>
    <a href="{{ url_for('inventory') }}">Inventory</a>
    <a href="{{ url_for('billing') }}" class="active">Billing</a>
    <a href="{{ url_for('khata') }}">Udhaar / Khata</a>
</nav>

    </aside>

    <main class="main-content">
        <header>
            <h1>Create New Bill</h1>
            <p>Enter product quantities in pieces.</p>
        </header>

        <section class="panel">

<h2>Select Products</h2>

<input
    type="search"
    id="product-search"
    placeholder="Search product by name..."
    autocomplete="off"
    style="width: 100%; max-width: 400px; margin-bottom: 15px;"
>


{% if products %}
<form id="billing-form" method="POST" action="{{ url_for('billing') }}">
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Product</th>
                    <th>Price / Piece</th>
                    <th>Available Pieces</th>
                    <th>Quantity (Pieces)</th>
                    <th>Line Total</th>
                </tr>
            </thead>
            <tbody>
                {% for p in products %}
                <tr>
                    <td>{{ p.name }}</td>
                    <td>Rs. <span class="price">{{ "%.2f"|format(p.selling_price) }}</span></td>
                    <td>{{ p.stock_pieces }}</td>
                    <td>
                       
<input
    class="quantity"
    type="number"
    name="quantity_{{ p.id }}"
    min="0"
    max="{{ p.stock_pieces }}"
    value="0"
    data-price="{{ p.selling_price }}"
    aria-label="Quantity for {{ p.name }}">

                    </td>
                    <td>Rs. <span class="line-total">0.00</span></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    
<h2>Total Bill: Rs. <span id="subtotal-total">0.00</span></h2>

<label>Discount (Rs.)</label>
<input
    type="number"
    id="discount"
    name="discount"
    min="0"
    step="0.01"
    value="0"
    required
>


<h2>Grand Total: Rs. <span id="grand-total">0.00</span></h2>

<label>Payment Type</label>
<select name="payment_type" id="payment_type" required>
    <option value="Cash">Cash</option>
    <option value="Udhaar">Udhaar (Khata)</option>
</select>

<label>Customer Name (Optional)</label>
<input
    type="text"
    name="customer_name"
    id="customer_name"
    maxlength="150"
    placeholder="Customer ka naam likho"
>

<button type="submit">Save Bill</button>
</form>
```
{% else %}
<p>No products available. Add products in Inventory first.</p>
{% endif %}


<script>
const discountInput = document.getElementById("discount");

function updateTotals() {
    let subtotal = 0;

    document.querySelectorAll(".quantity").forEach(function(input) {
        const max = Number(input.max);
        let qty = Math.floor(Number(input.value) || 0);

        if (qty < 0) qty = 0;
        if (qty > max) qty = max;

        input.value = qty;

        const price = Number(input.dataset.price) || 0;
        const lineTotal = qty * price;

        input.closest("tr").querySelector(".line-total").textContent =
            lineTotal.toFixed(2);

        subtotal += lineTotal;
    });

    let discount = Number(discountInput.value) || 0;
    if (discount < 0) discount = 0;

    document.getElementById("subtotal-total").textContent =
        subtotal.toFixed(2);

    document.getElementById("grand-total").textContent =
        Math.max(0, subtotal - discount).toFixed(2);
}

document.querySelectorAll(".quantity").forEach(function(input) {
    input.addEventListener("input", updateTotals);
});

discountInput.addEventListener("input", updateTotals);

updateTotals();

const productSearch = document.getElementById("product-search");

productSearch.addEventListener("input", function () {
    const searchText = this.value.trim().toLowerCase();

    document.querySelectorAll("#billing-form tbody tr").forEach(function (row) {
        const productName = row.cells[0].textContent.trim().toLowerCase();
        row.style.display = productName.includes(searchText) ? "" : "none";
    });
});

</script>


                <section class="panel">
            <h2>Saved Bills History</h2>
            <p>Saved bills are grouped by date, newest first.</p>

            {% if history_groups %}
                {% for group in history_groups %}
                <div class="panel">
                    <h2>{{ group.date_label }}</h2>

                 {% for entry in group["bills"] %}
                    <details>
                        <summary>
                            Bill #{{ entry.display_number }}
                            | {{ entry.bill.payment_type }}
                            | Rs. {{ "%.2f"|format(entry.bill.total) }}
                        </summary>

                        <p>
                            <strong>Date & Time:</strong>
                            {{ format_pakistan_datetime(entry.bill.date) }}
                        </p>

                        <p>
                            <strong>Payment:</strong>
                            {{ entry.bill.payment_type }}
                        </p>

                        <p>
                            <strong>Discount:</strong>
                            Rs. {{ "%.2f"|format(entry.bill.discount) }}
                        </p>

                        <p>
                            <strong>Total:</strong>
                            Rs. {{ "%.2f"|format(entry.bill.total) }}
                        </p>

                       
                      {% if entry.customer_name %}
<p>
    <strong>Customer:</strong>
    {{ entry.customer_name }}
</p>
{% endif %}

<form
    method="POST"
    action="{{ url_for('delete_bill', bill_id=entry.bill.id) }}"
    onsubmit="return confirm('Kya aap waqai ye bill delete karna chahte hain? Stock aur Khata adjust honge.');"
>
    <button type="submit">Delete Bill</button>
</form>  

                        <h3>Products</h3>
                        <div class="table-wrap">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Product</th>
                                        <th>Quantity</th>
                                        <th>Price / Piece</th>
                                        <th>Subtotal</th>
                                        <th>Return</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for item in entry["items"] %}
                                    <tr>
                                        <td>{{ item.name }}</td>
                                        <td>{{ item.quantity }}</td>
                                        <td>Rs. {{ "%.2f"|format(item.price) }}</td>
                                        <td>Rs. {{ "%.2f"|format(item.subtotal) }}</td>
                                        
<td>
    {% if item.remaining_quantity > 0 %}
    <form method="POST"
          action="{{ url_for('return_bill_item', item_id=item.id) }}"
          onsubmit="return confirm('Kya customer ke return pieces confirm hain?');">
        <input type="number"
               name="return_quantity"
               min="1"
               max="{{ item.remaining_quantity }}"
               step="1"
               required
               placeholder="Pieces"
               style="width: 80px;">
        <button type="submit">Return</button>
    </form>
    {% else %}
        Returned
    {% endif %}
</td>

                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </details>
                    <hr>
                    {% endfor %}
                </div>
                {% endfor %}
            {% else %}
                <p>No saved bills yet. Your bills will appear here after you save them.</p>
            {% endif %}
        </section>
    </main>
</div>
</body>
</html>
"""

#-------------------------
#      khata html
#------------------------



KHATA_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Udhaar / Khata - Sanitary Store</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<div class="app-layout">
    <aside class="sidebar">
        <h2>✦ SANITARY STORE</h2>
        <nav>
            <a href="{{ url_for('home') }}">Dashboard</a>
            <a href="{{ url_for('inventory') }}">Inventory</a>
            <a href="{{ url_for('billing') }}">Billing</a>
            <a class="active" href="{{ url_for('khata') }}">Udhaar / Khata</a>
        </nav>
    </aside>

    <main class="main-content">
        <header>
            <h1>Udhaar / Khata</h1>
            <p>Complete customer bills, discounts and payment history</p>
        </header>

        {% for message in get_flashed_messages() %}
            <div class="notice">{{ message }}</div>
        {% endfor %}

        <section class="panel">
            <label>Search Customer</label>
            <input type="text" id="customerSearch"
                   placeholder="Customer ka naam likho..."
                   oninput="searchCustomers()">
        </section>

        {% for entry in customer_records %}
        <section class="panel customer-record">
            <h2>{{ entry.customer.name }}</h2>

            <h3>
                Outstanding Balance:
                Rs. {{ "%.2f"|format(entry.customer.balance) }}
            </h3>

            <button type="button"
                    onclick="togglePayment({{ entry.customer.id }})">
                Receive Payment
            </button>

            <form id="payment-{{ entry.customer.id }}"
                  action="{{ url_for('receive_khata_payment', customer_id=entry.customer.id) }}"
                  method="POST"
                  style="display:none; margin-top:15px;">

                <label>Cash Received (Rs.)</label>
                <input type="number" name="amount"
                       min="0.01" step="0.01" required>

                <label>Extra Discount (full settlement only)</label>
                <input type="number" name="extra_discount"
                       min="0" step="0.01" value="0" required>

                <label>Note (optional)</label>
                <input type="text" name="note"
                       maxlength="200" placeholder="Payment note">

                <button type="submit">Save Payment</button>
            </form>

            <hr>
            <h3>Udhaar Bills History</h3>

            {% if entry.bills %}
                {% for record in entry["bills"] %}
                <details>
                    <summary>
                        Bill #{{ record.number }}
                        | {{ format_pakistan_datetime(record.bill.date) }}
                        | Rs. {{ "%.2f"|format(record.bill.total) }}
                    </summary>

                    <p><strong>Date & Time:</strong>
                        {{ format_pakistan_datetime(record.bill.date) }}</p>

                    <p><strong>Subtotal:</strong>
                        Rs. {{ "%.2f"|format(record.subtotal) }}</p>

                    <p><strong>Discount:</strong>
                        Rs. {{ "%.2f"|format(record.bill.discount) }}</p>

                    <p><strong>Bill Total:</strong>
                        Rs. {{ "%.2f"|format(record.bill.total) }}</p>

                    <p><strong>Paid:</strong>
                        Rs. {{ "%.2f"|format(record.bill.paid_amount) }}</p>

                    <p><strong>Remaining:</strong>
                        Rs. {{ "%.2f"|format(record.bill.remaining_amount) }}</p>

                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Product</th>
                                    <th>Quantity</th>
                                    <th>Price / Piece</th>
                                    <th>Subtotal</th>
                                    <th>Returned</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for item in record["items"] %}
                                <tr>
                                    <td>{{ item.name }}</td>
                                    <td>{{ item.quantity }}</td>
                                    <td>Rs. {{ "%.2f"|format(item.price) }}</td>
                                    <td>Rs. {{ "%.2f"|format(item.subtotal) }}</td>
                                    <td>{{ item.returned_quantity }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </details>
                <hr>
                {% endfor %}
            {% else %}
                <p>This customer has no  pending khata.</p>
            {% endif %}

            <h3>Payment History</h3>

            {% if entry.payments %}
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>Date & Time</th>
                                <th>Cash Received</th>
                                <th>Note / Discount</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for payment in entry["payments"] %}
                            <tr>
                                <td>{{ format_pakistan_datetime(payment.date) }}</td>
                                <td>Rs. {{ "%.2f"|format(payment.amount) }}</td>
                                <td>{{ payment.note or "-" }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            {% else %}
                <p>Abhi koi payment record nahi hai.</p>
            {% endif %}
        </section>
        {% endfor %}

        {% if not customer_records %}
            <section class="panel">
                <p>Abhi koi customer record nahi hai.</p>
            </section>
        {% endif %}
    </main>
</div>

<script>
function togglePayment(customerId) {
    const form = document.getElementById("payment-" + customerId);
    form.style.display =
        form.style.display === "none" ? "block" : "none";
}

function searchCustomers() {
    const search = document.getElementById("customerSearch")
        .value.toLowerCase();

    document.querySelectorAll(".customer-record").forEach(function(card) {
        card.style.display = card.innerText.toLowerCase().includes(search)
            ? "" : "none";
    });
}
</script>
</body>
</html>
"""

# ==================================================
# 6. DASHBOARD ROUTE
# ==================================================

@app.route("/")
def home():
    products = Product.query.all()

    # Low stock: 10 pieces ya us se kam
    low_stock_products = [
        p for p in products if p.stock_pieces <= 50
    ]
    low_stock_count = len(low_stock_products)

    # Pakistan local date/time
    now = pakistan_now()
    today = now.date()

    # Aaj, is haftay aur is mahine ke start
    from datetime import timedelta

    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    
    # Saved bills
    bills = Bill.query.all()

    daily_sales = 0.0
    weekly_sales = 0.0
    monthly_sales = 0.0
    yearly_sales = 0.0

    for bill in bills:
        bill_date = bill.date.date()

        # Sirf paid amount sales mein count hoga
        paid = bill.paid_amount or 0

        if bill_date == today:
            daily_sales += paid

        if bill_date >= week_start and bill_date <= today:
            weekly_sales += paid

        if bill_date >= month_start and bill_date <= today:
            monthly_sales += paid

        if bill_date >= year_start and bill_date <= today:
            yearly_sales += paid

    return render_template_string(
        PAGE,
        low_stock_products=low_stock_products,
        low_stock_count=low_stock_count,
        daily_sales=f"{daily_sales:,.2f}",
        weekly_sales=f"{weekly_sales:,.2f}",
        monthly_sales=f"{monthly_sales:,.2f}",
        yearly_sales=f"{yearly_sales:,.2f}"
    )


# ==================================================
# 7. INVENTORY ROUTE
# ==================================================


@app.route("/product/edit/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    product = db.session.get(Product, product_id)

    if product is None:
        flash("Product nahi mila.")
        return redirect(url_for("inventory"))

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            selling_price = float(
                request.form.get("selling_price", "")
            )
            carton_size = int(
                request.form.get("carton_size", "")
            )

            if not name:
                raise ValueError("Product name zaroori hai.")

            if len(name) > 150:
                raise ValueError("Product name bohat lamba hai.")

            if selling_price < 0:
                raise ValueError("Price negative nahi ho sakti.")

            if carton_size < 1:
                raise ValueError("Carton size kam az kam 1 hona chahiye.")

            product.name = name
            product.selling_price = selling_price
            product.carton_size = carton_size

            # Stock pieces remain unchanged.
            db.session.commit()
            flash("Product details update ho gayi hain.")
            return redirect(url_for("inventory"))

        except (ValueError, TypeError):
            db.session.rollback()
            flash("Invalid details. Name, price aur carton size check karo.")

        except Exception:
            db.session.rollback()
            app.logger.exception("Product edit error")
            flash("Product update nahi hua. Terminal check karo.")

    return render_template_string(
        EDIT_PRODUCT_PAGE,
        product=product
    )


@app.route("/product/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    product = db.session.get(Product, product_id)

    if product is None:
        flash("Product nahi mila.")
        return redirect(url_for("inventory"))

    # Preserve historical bills: do not delete referenced products.
    used_in_bill = BillItem.query.filter_by(
        product_id=product.id
    ).first()

    if used_in_bill:
        flash(
            "Product is in bill history . "
            "So it can't be deleted, to preserve history. "
            "At that moment you can only edit the product."
        )
        return redirect(url_for("inventory"))

    try:
        db.session.delete(product)
        db.session.commit()
        flash("Product deleted.")

    except Exception:
        db.session.rollback()
        app.logger.exception("Product delete error")
        flash("Product delete nahi hua. Terminal check karo.")

    return redirect(url_for("inventory"))



@app.route("/inventory")
def inventory():
    products = Product.query.order_by(Product.id.desc()).all()

    return render_template_string(
        INVENTORY_PAGE,
        products=products
    )


# ==================================================
# 8. ADD NEW PRODUCT ROUTE
# ==================================================

@app.route("/products/add", methods=["POST"])
def add_product():
    try:
        name = request.form["name"].strip()
        price = float(request.form["selling_price"])
        carton_size = int(request.form["carton_size"])
        cartons = int(request.form["cartons"])
        loose = int(request.form["loose"])

        if (
            not name
            or price < 0
        ):
            raise ValueError

        product = Product(
            name=name,
            selling_price=price,
            carton_size=carton_size,
            stock_pieces=cartons * carton_size + loose
        )

        db.session.add(product)
        db.session.commit()

        flash(f"{name} successfully saved.")

    except (ValueError, KeyError):
        db.session.rollback()
        flash("Please sahi product details enter karo.")

    return redirect(url_for("inventory"))


# ==================================================
# 9. LEGACY ADD STOCK ROUTE
# ==================================================

@app.route("/stock/add", methods=["POST"])
def add_stock():
    try:
        product_id = int(request.form["product_id"])
        cartons = int(request.form["cartons"])
        loose = int(request.form["loose"])

        product = db.session.get(Product, product_id)

        if product is None or cartons < 0 or loose < 0:
            raise ValueError

        product.stock_pieces += (
            cartons * product.carton_size + loose
        )

        db.session.commit()
        flash(f"{product.name} ka stock update ho gaya.")

    except (ValueError, KeyError):
        db.session.rollback()
        flash("Product ID ya stock details check karo.")

    return redirect(url_for("inventory"))


# ==================================================
# 10. UPDATE STOCK ROUTE
# ==================================================


@app.route("/stock/update/<int:product_id>", methods=["GET", "POST"])
def update_stock_page(product_id):
    product = db.session.get(Product, product_id)

    if product is None:
        return "Product not found", 404

    if request.method == "POST":
        try:
            cartons = int(request.form.get("cartons", 0))
            loose_pieces = int(request.form.get("loose_pieces", 0))

            if cartons < 0 or loose_pieces < 0:
                raise ValueError

            added_pieces = (
                cartons * product.carton_size + loose_pieces
            )

            product.stock_pieces += added_pieces
            db.session.commit()

            flash(f"{product.name} ka stock update ho gaya.")
            return redirect(url_for("inventory"))

        except (ValueError, TypeError):
            db.session.rollback()
            flash("Please valid, non-negative quantities enter karo.")

    return render_template_string(
        UPDATE_STOCK_PAGE,
        product=product
    )


# ==================================================
# 11. billing
# ==================================================



def get_billing_history():
    all_bills = Bill.query.order_by(
        Bill.date.desc(), Bill.id.desc()
    ).all()

    grouped = {}

    for bill in all_bills:
        # Unpaid Udhaar bills history mein nahi dikhane
        if bill.payment_type == "Udhaar" and bill.remaining_amount > 0:
            continue

        date_key = bill.date.strftime("%Y-%m-%d")

        if date_key not in grouped:
            grouped[date_key] = {
                "date_label": bill.date.strftime("%d-%m-%Y"),
                "bills": []
            }

        try:
            display_number = int(
                bill.bill_number.rsplit("-", 1)[1]
            )
        except (ValueError, IndexError):
            display_number = bill.bill_number

        customer = None
        if bill.customer_id:
            customer = db.session.get(Customer, bill.customer_id)

        items = []
        saved_items = BillItem.query.filter_by(
            bill_id=bill.id
        ).all()

        for item in saved_items:
            product = db.session.get(Product, item.product_id)

            items.append({
                "id": item.id,
                "product_id": item.product_id,
                "name": product.name if product else "Deleted product",
                "quantity": item.quantity,
                "returned_quantity": item.returned_quantity,
                "remaining_quantity": (
                    item.quantity - item.returned_quantity
                ),
                "price": item.price,
                "subtotal": item.quantity * item.price
            })

        grouped[date_key]["bills"].append({
            "bill": bill,
            "display_number": display_number,
            "customer_name": customer.name if customer else "",
            "items": items
        })

    return [
        grouped[key]
        for key in sorted(grouped.keys(), reverse=True)
    ]


@app.route("/bill/delete/<int:bill_id>", methods=["POST"])
def delete_bill(bill_id):
    bill = db.session.get(Bill, bill_id)

    if bill is None:
        flash("Bill not found.")
        return redirect(url_for("billing"))

    try:
        bill_number = bill.bill_number

        # 1. Restore stock for every product on this bill.
        items = BillItem.query.filter_by(
            bill_id=bill.id
        ).all()

        for item in items:
            product = db.session.get(Product, item.product_id)

            if product is not None:
                product.stock_pieces += item.quantity

        # 2. Remove only this bill's outstanding Udhaar amount.
        if bill.payment_type == "Udhaar" and bill.customer_id:
            customer = db.session.get(Customer, bill.customer_id)

            if customer is not None:
                customer.balance = round(
                    customer.balance - bill.remaining_amount, 2
                )

        # 3. Preserve receipts; detach them from the deleted bill.
        linked_payments = Payment.query.filter_by(
            bill_id=bill.id
        ).all()

        for payment in linked_payments:
            payment.bill_id = None

            marker = (
                f"Receipt retained; bill #{bill_number} deleted"
            )
            old_note = (payment.note or "").strip()

            if old_note:
                keep_length = max(0, 250 - len(marker) - 3)
                payment.note = (
                    old_note[:keep_length] + " | " + marker
                )[:250]
            else:
                payment.note = marker[:250]

        # 4. Delete this bill's line items and bill record.
        for item in items:
            db.session.delete(item)

        db.session.delete(bill)
        db.session.commit()

        flash(
            f"Bill #{bill_number} delete ho gaya aur stock restore ho gaya."
        )

    except Exception:
        db.session.rollback()
        app.logger.exception("Bill delete error")
        flash(
            "Bill delete nahi hua. Terminal mein error check karo."
        )

    return redirect(url_for("billing"))



@app.route("/bill/item/return/<int:item_id>", methods=["POST"])
def return_bill_item(item_id):
    item = db.session.get(BillItem, item_id)

    if item is None:
        flash("Bill item not found.")
        return redirect(url_for("billing"))

    try:
        return_quantity = int(
            request.form.get("return_quantity", 0)
        )

        remaining_quantity = (
            item.quantity - item.returned_quantity
        )

        if return_quantity <= 0:
            flash("Return quantity 1 ya us se zyada honi chahiye.")
            return redirect(url_for("billing"))

        if return_quantity > remaining_quantity:
            flash("Itne pieces return nahi ho sakte.")
            return redirect(url_for("billing"))

        product = db.session.get(Product, item.product_id)

        if product is None:
            flash("Product not found.")
            return redirect(url_for("billing"))

        # Stock mein returned pieces wapas add karo.
        product.stock_pieces += return_quantity

        # Return quantity record karo.
        item.returned_quantity += return_quantity

        db.session.commit()

        flash(
            f"{return_quantity} pieces return ho gaye "
            "aur stock mein wapas add ho gaye."
        )

    except (ValueError, TypeError):
        db.session.rollback()
        flash("Enter return quntity in correct.")
    except Exception:
        db.session.rollback()
        app.logger.exception("Return item error")
        flash("Return save nahi hua. Terminal mein error check karo.")

    return redirect(url_for("billing"))




@app.route("/billing", methods=["GET", "POST"])
def billing():
    products = Product.query.order_by(Product.name).all()

    if request.method == "POST":
        try:
            payment_type = request.form.get("payment_type", "")
            customer_name = request.form.get(
                "customer_name", ""
            ).strip()
            discount = float(request.form.get("discount", 0))

            if payment_type not in ("Cash", "Udhaar"):
                raise ValueError("Cash ya Udhaar select karo.")

            if discount < 0:
                raise ValueError("Discount negative nahi ho sakta.")

            selected_items = []
            subtotal = 0.0

            # Check product quantities and available stock
            for product in products:
                quantity = int(
                    request.form.get(f"quantity_{product.id}", 0)
                )

                if quantity < 0:
                    raise ValueError(
                        "Quantity negative nahi ho sakti."
                    )

                if quantity > product.stock_pieces:
                    raise ValueError(
                        f"{product.name}  stock unavailable."
                    )

                if quantity > 0:
                    price = product.selling_price
                    subtotal += quantity * price
                    selected_items.append(
                        (product, quantity, price)
                    )

            if not selected_items:
                raise ValueError(
                    "Enter atleast 1 quantity."
                )

            subtotal = round(subtotal, 2)

            if discount > subtotal:
                raise ValueError(
                    "Discount can't be more than total bill."
                )

            grand_total = round(subtotal - discount, 2)

            if grand_total <= 0:
                raise ValueError(
                    "Grand Total must be more than 0."
                )

            # Find or create customer if a name was entered
            customer = None
            
            if customer_name:
                customer = Customer.query.filter(
                    db.func.lower(Customer.name) == customer_name.lower()
                ).first()
            
                if customer is None:
                    customer = Customer(
                        name=customer_name,
                        balance=0
                    )
                    db.session.add(customer)
                    db.session.flush()
            
            if payment_type == "Udhaar":
                if customer is None:
                    raise ValueError(
                        "Customer name is compulsory for udhaar."
                    )
            
                paid_amount = 0.0
                remaining_amount = grand_total
            
            else:
                paid_amount = grand_total
                remaining_amount = 0.0
    

            # Generate a daily bill number
            now = pakistan_now()
            date_key = now.strftime("%Y-%m-%d")
            prefix = date_key + "-"

            todays_bills = Bill.query.filter(
                Bill.bill_number.like(prefix + "%")
            ).all()

            numbers = []

            for old_bill in todays_bills:
                try:
                    numbers.append(
                        int(old_bill.bill_number.rsplit("-", 1)[1])
                    )
                except (ValueError, IndexError):
                    continue

            next_number = max(numbers, default=0) + 1

            bill = Bill(
                bill_number=f"{date_key}-{next_number}",
                date=now,
                customer_id=customer.id if customer else None,
                payment_type=payment_type,
                total=grand_total,
                discount=discount,
                paid_amount=paid_amount,
                remaining_amount=remaining_amount
            )

            db.session.add(bill)
            db.session.flush()

            # Save items and deduct stock
            for product, quantity, price in selected_items:
                item = BillItem(
                    bill_id=bill.id,
                    product_id=product.id,
                    quantity=quantity,
                    price=price
                )
                db.session.add(item)
                product.stock_pieces -= quantity

            # Add Udhaar amount to customer Khata
            if payment_type == "Udhaar":
                customer.balance = round(
                    customer.balance + remaining_amount, 2
                )

            db.session.commit()

            flash(
                f"Bill #{next_number} save ho gaya. "
                f"Grand Total: Rs. {grand_total:.2f}"
            )

            return redirect(url_for("billing"))

        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(f"Bill not saved : {error}")

        except Exception:
            db.session.rollback()
            app.logger.exception("Bill save error")
            flash(
                "Bill save nahi hua. Terminal mein error check karo."
            )

    return render_template_string(
        BILLING_PAGE,
        products=products,
        history_groups=get_billing_history(),
        format_pakistan_datetime=format_pakistan_datetime
    )

#------------------------------
#      KHATA ROUTE
#-----------------------------


@app.route("/khata/payment/<int:customer_id>", methods=["POST"])
def receive_khata_payment(customer_id):
    customer = db.session.get(Customer, customer_id)

    if customer is None:
        flash("Customer nahi mila.")
        return redirect(url_for("khata"))

    try:
        amount = round(float(request.form.get("amount", 0)), 2)
        extra_discount = round(
            float(request.form.get("extra_discount", 0)), 2
        )
        note = request.form.get("note", "").strip()

        if amount <= 0:
            raise ValueError("Payment amount zero se zyada hona chahiye.")

        if extra_discount < 0:
            raise ValueError("Discount negative nahi ho sakta.")

        outstanding = round(customer.balance, 2)

        if outstanding <= 0:
            raise ValueError("Is customer ka koi outstanding balance nahi.")

        if amount + extra_discount > outstanding + 0.009:
            raise ValueError(
                "Payment aur discount balance se zyada nahi ho sakte."
            )

        # Extra discount sirf full settlement par allowed hai.
        if extra_discount > 0 and abs(
            amount + extra_discount - outstanding
        ) > 0.009:
            raise ValueError(
                "Extra discount sirf full settlement par mil sakta hai."
            )

        # Outstanding bills oldest-first order mein load karo.
        
        bills = Bill.query.filter_by(
            customer_id=customer.id,
            payment_type="Udhaar"
        ).filter(
            Bill.remaining_amount > 0
        ).order_by(
            Bill.date.asc(), Bill.id.asc()
        ).all()

        bill_outstanding = round(
            sum(b.remaining_amount for b in bills), 2
        )

        # Mismatch ho to records ko ghalat update karne ke bajaye rok do.
        if abs(bill_outstanding - outstanding) > 0.009:
            raise ValueError(
                "Customer balance aur bills ka total match nahi karta. "
                "Payment save nahi hui; pehle balance verify karna hoga."
            )

        # Cash payment ko sab se purane bills par adjust karo.
        cash_left = amount

        for bill in bills:
            if cash_left <= 0:
                break

            applied = min(round(bill.remaining_amount, 2), cash_left)

            bill.remaining_amount = round(
                bill.remaining_amount - applied, 2
            )
            bill.paid_amount = round(bill.paid_amount + applied, 2)
            cash_left = round(cash_left - applied, 2)

        # Full-settlement discount ko remaining bills par adjust karo.
        discount_left = extra_discount

        for bill in bills:
            if discount_left <= 0:
                break

            applied = min(
                round(bill.remaining_amount, 2), discount_left
            )
            bill.remaining_amount = round(
                bill.remaining_amount - applied, 2
            )
            discount_left = round(discount_left - applied, 2)

        if cash_left > 0.009 or discount_left > 0.009:
            raise ValueError("Payment allocation complete nahi ho saki.")

        customer.balance = round(
            outstanding - amount - extra_discount, 2
        )

        # Payment history mein asal cash amount save karo.
        payment_note = note

        if extra_discount > 0:
            discount_text = (
                f"Full settlement discount Rs. {extra_discount:.2f}"
            )
            payment_note = (
                f"{payment_note} | {discount_text}"
                if payment_note else discount_text
            )

        db.session.add(Payment(
            customer_id=customer.id,
            bill_id=None,
            amount=amount,
            date=pakistan_now(),
            note=payment_note[:250] if payment_note else None
        ))

        db.session.commit()

        flash(
            f"Payment Rs. {amount:.2f} save ho gayi. "
            f"Discount Rs. {extra_discount:.2f}. "
            f"Baqi balance Rs. {customer.balance:.2f}."
        )

    except (ValueError, TypeError) as error:
        db.session.rollback()
        flash(f"Payment save nahi hui: {error}")

    except Exception:
        db.session.rollback()
        app.logger.exception("Khata payment error")
        flash("Payment save nahi hui. Terminal mein error check karo.")

    return redirect(url_for("khata"))



@app.route("/khata")
def khata():
    customers = Customer.query.order_by(Customer.name).all()
    customer_records = []

    for customer in customers:
        bills = Bill.query.filter_by(
    customer_id=customer.id,
    payment_type="Udhaar"
).filter(
    Bill.remaining_amount > 0
).order_by(
    Bill.date.desc(), Bill.id.desc()
).all()
        
        bill_records = []

        for bill in bills:
            items = BillItem.query.filter_by(
                bill_id=bill.id
            ).all()

            item_records = []
            subtotal = 0.0

            for item in items:
                product = db.session.get(Product, item.product_id)
                line_total = item.quantity * item.price
                subtotal += line_total

                item_records.append({
                    "name": product.name if product else "Deleted product",
                    "quantity": item.quantity,
                    "price": item.price,
                    "subtotal": line_total,
                    "returned_quantity": item.returned_quantity
                })

            try:
                display_number = int(bill.bill_number.rsplit("-", 1)[1])
            except (ValueError, IndexError):
                display_number = bill.bill_number

            bill_records.append({
                "bill": bill,
                "number": display_number,
                "subtotal": round(subtotal, 2),
                "items": item_records
            })

        payments = Payment.query.filter_by(
            customer_id=customer.id
        ).order_by(Payment.date.desc(), Payment.id.desc()).all()

        # Sirf relevant customers dikhayein.
        if bills or payments or customer.balance > 0:
            customer_records.append({
                "customer": customer,
                "bills": bill_records,
                "payments": payments
            })

    return render_template_string(
        KHATA_PAGE,
        customer_records=customer_records,
        format_pakistan_datetime=format_pakistan_datetime
    )


# ==================================================
# 12. START APPLICATION
# ==================================================

if __name__ == "__main__":
    app.run(debug=True)
