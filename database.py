import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "retail.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS categories (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS products (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                code          TEXT UNIQUE,
                name          TEXT NOT NULL,
                category_id   INTEGER REFERENCES categories(id),
                unit          TEXT NOT NULL DEFAULT 'pcs',
                cost_price    REAL NOT NULL DEFAULT 0,
                sell_price    REAL NOT NULL DEFAULT 0,
                stock         INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sales (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                payment_type  TEXT NOT NULL CHECK(payment_type IN ('cash','debt')),
                total_cost    REAL NOT NULL,
                total_revenue REAL NOT NULL,
                remaining     REAL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS sale_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id     INTEGER NOT NULL REFERENCES sales(id),
                product_id  INTEGER NOT NULL REFERENCES products(id),
                quantity    INTEGER NOT NULL,
                unit_cost   REAL NOT NULL,
                unit_price  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS restocks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id  INTEGER NOT NULL REFERENCES products(id),
                quantity    INTEGER NOT NULL,
                unit_cost   REAL NOT NULL,
                note        TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
        """)


# ── Categories ─────────────────────────────────────────────────────────────

def add_category(name: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO categories(name) VALUES(?)", (name.strip(),))

def get_categories():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM categories ORDER BY name").fetchall()

def delete_category(cat_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM categories WHERE id=?", (cat_id,))


# ── Products ────────────────────────────────────────────────────────────────

def add_product(code, name, category_id, unit, cost_price, sell_price):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO products(code,name,category_id,unit,cost_price,sell_price,stock) VALUES(?,?,?,?,?,?,0)",
            (code, name, category_id, unit, cost_price, sell_price)
        )

def get_products(category_id=None):
    with get_conn() as conn:
        if category_id:
            return conn.execute(
                "SELECT p.*, c.name as category_name FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.category_id=? ORDER BY p.name",
                (category_id,)
            ).fetchall()
        return conn.execute(
            "SELECT p.*, c.name as category_name FROM products p LEFT JOIN categories c ON p.category_id=c.id ORDER BY p.name"
        ).fetchall()

def get_product(product_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT p.*, c.name as category_name FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.id=?",
            (product_id,)
        ).fetchone()

def update_product(product_id, code, name, category_id, unit, cost_price, sell_price):
    with get_conn() as conn:
        conn.execute(
            "UPDATE products SET code=?,name=?,category_id=?,unit=?,cost_price=?,sell_price=? WHERE id=?",
            (code, name, category_id, unit, cost_price, sell_price, product_id)
        )

def delete_product(product_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))


# ── Restock ─────────────────────────────────────────────────────────────────

def restock_product(product_id, quantity, unit_cost, note=""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO restocks(product_id,quantity,unit_cost,note) VALUES(?,?,?,?)",
            (product_id, quantity, unit_cost, note)
        )
        conn.execute(
            "UPDATE products SET cost_price=?, stock=stock+? WHERE id=?",
            (unit_cost, quantity, product_id)
        )


# ── Sales ───────────────────────────────────────────────────────────────────

def create_sale(customer_name, payment_type, items: list):
    """
    items = [{"product_id": int, "quantity": int, "unit_cost": float, "unit_price": float}, ...]
    """
    total_cost = sum(i["quantity"] * i["unit_cost"] for i in items)
    total_revenue = sum(i["quantity"] * i["unit_price"] for i in items)
    remaining = total_revenue if payment_type == 'debt' else None

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sales(customer_name,payment_type,total_cost,total_revenue,remaining) VALUES(?,?,?,?,?)",
            (customer_name, payment_type, total_cost, total_revenue, remaining)
        )
        sale_id = cur.lastrowid
        for item in items:
            conn.execute(
                "INSERT INTO sale_items(sale_id,product_id,quantity,unit_cost,unit_price) VALUES(?,?,?,?,?)",
                (sale_id, item["product_id"], item["quantity"], item["unit_cost"], item["unit_price"])
            )
            conn.execute(
                "UPDATE products SET stock=stock-? WHERE id=?",
                (item["quantity"], item["product_id"])
            )
    return sale_id, total_cost, total_revenue


# ── Reports ─────────────────────────────────────────────────────────────────

def report_summary(period: str = "today"):
    """period: today | week | month | all"""
    filters = {
        "today": "DATE(created_at)=DATE('now','localtime')",
        "week":  "created_at >= DATE('now','localtime','-6 days')",
        "month": "strftime('%Y-%m',created_at)=strftime('%Y-%m',DATE('now','localtime'))",
        "all":   "1=1",
    }
    f = filters.get(period, filters["today"])
    with get_conn() as conn:
        row = conn.execute(f"""
            SELECT
                COUNT(*)            AS total_sales,
                SUM(total_revenue)  AS revenue,
                SUM(total_cost)     AS cost,
                SUM(CASE WHEN payment_type='debt' THEN total_revenue ELSE 0 END) AS debt_amount,
                COUNT(CASE WHEN payment_type='debt' THEN 1 END) AS debt_count
            FROM sales WHERE {f}
        """).fetchone()
    return row

def report_by_category(period: str = "today"):
    filters = {
        "today": "DATE(s.created_at)=DATE('now','localtime')",
        "week":  "s.created_at >= DATE('now','localtime','-6 days')",
        "month": "strftime('%Y-%m',s.created_at)=strftime('%Y-%m',DATE('now','localtime'))",
        "all":   "1=1",
    }
    f = filters.get(period, filters["today"])
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT
                COALESCE(c.name,'Uncategorized') AS category,
                SUM(si.quantity * si.unit_price)  AS revenue,
                SUM(si.quantity * si.unit_cost)   AS cost
            FROM sale_items si
            JOIN sales s ON si.sale_id=s.id
            JOIN products p ON si.product_id=p.id
            LEFT JOIN categories c ON p.category_id=c.id
            WHERE {f}
            GROUP BY c.id
            ORDER BY revenue DESC
        """).fetchall()
    return rows

def report_top_products(period: str = "today", limit: int = 5):
    filters = {
        "today": "DATE(s.created_at)=DATE('now','localtime')",
        "week":  "s.created_at >= DATE('now','localtime','-6 days')",
        "month": "strftime('%Y-%m',s.created_at)=strftime('%Y-%m',DATE('now','localtime'))",
        "all":   "1=1",
    }
    f = filters.get(period, filters["today"])
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT
                p.name,
                SUM(si.quantity)                  AS qty_sold,
                SUM(si.quantity * si.unit_price)  AS revenue
            FROM sale_items si
            JOIN sales s ON si.sale_id=s.id
            JOIN products p ON si.product_id=p.id
            WHERE {f}
            GROUP BY p.id
            ORDER BY qty_sold DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return rows

def get_stock_report():
    with get_conn() as conn:
        return conn.execute("""
            SELECT p.code, p.name, c.name as category, p.unit, p.stock, p.cost_price, p.sell_price
            FROM products p
            LEFT JOIN categories c ON p.category_id=c.id
            ORDER BY c.name, p.name
        """).fetchall()


def get_debts():
    with get_conn() as conn:
        return conn.execute("""
            SELECT id, customer_name, total_revenue, remaining, created_at
            FROM sales
            WHERE payment_type = 'debt'
            ORDER BY created_at DESC
        """).fetchall()
    

def mark_debt_paid(sale_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE sales SET payment_type='cash', remaining=0 WHERE id=?", (sale_id,))

def pay_partial(sale_id: int, amount: float):
    with get_conn() as conn:
        row = conn.execute("SELECT remaining FROM sales WHERE id=?", (sale_id,)).fetchone()
        new_remaining = max(0, row['remaining'] - amount)
        if new_remaining == 0:
            conn.execute("UPDATE sales SET remaining=0, payment_type='cash' WHERE id=?", (sale_id,))
        else:
            conn.execute("UPDATE sales SET remaining=? WHERE id=?", (new_remaining, sale_id))
        return new_remaining