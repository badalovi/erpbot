# 🏪 Retail ERP — Telegram Bots

Two Telegram bots sharing one SQLite database:
- **Admin Bot** — manage products, categories, restock, view reports
- **Sales Bot** — simple sale flow for the salesperson

---

## 📁 Project Structure

```
retail_erp/
├── database.py          ← shared database logic (both bots use this)
├── requirements.txt
├── Procfile             ← for Railway deployment
├── .env.example         ← copy to .env and fill in
├── admin_bot/
│   └── admin_bot.py
└── sales_bot/
    └── sales_bot.py
```

---

## ⚙️ Setup

### Step 1 — Create two Telegram bots

1. Open Telegram and message **@BotFather**
2. Send `/newbot` → follow instructions → you'll get a **token**
3. Do this **twice** — once for the Admin Bot, once for the Sales Bot
4. Save both tokens

### Step 2 — Get your Telegram User IDs

1. Message **@userinfobot** on Telegram
2. It replies with your numeric ID (e.g. `123456789`)
3. Have the salesperson do the same

### Step 3 — Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
```
ADMIN_BOT_TOKEN=<token from Admin Bot>
SALES_BOT_TOKEN=<token from Sales Bot>
ADMIN_TELEGRAM_ID=<your numeric Telegram ID>
SALESPERSON_TELEGRAM_ID=<salesperson's numeric Telegram ID>
DB_PATH=/data/retail.db
```

### Step 4 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 5 — Run locally (for testing)

Open two terminals:

```bash
# Terminal 1
python admin_bot/admin_bot.py

# Terminal 2
python sales_bot/sales_bot.py
```

---

## 🚀 Deploy to Railway

1. Create a free account at [railway.app](https://railway.app)
2. Create a new project → **Deploy from GitHub repo**
3. Push your code to GitHub first (make sure `.env` is in `.gitignore`)
4. In Railway, go to **Variables** and add all 5 variables from `.env.example`
5. Add a **Volume** (persistent storage):
   - Mount path: `/data`
   - This is where `retail.db` will live permanently
6. Railway reads the `Procfile` and starts both bots automatically

---

## 🤖 Admin Bot — Commands

| Command | What it does |
|---|---|
| `/start` | Show main menu |
| `/addcat` | Add a new category |
| `/delcat` | Delete a category |
| `/addproduct` | Add a new product |
| `/editproduct` | Edit an existing product |
| `/delproduct` | Delete a product |
| `/restock` | Add stock to a product |
| `/stock` | View current stock levels |
| Menu: 📊 Reports | Sales reports with profit metrics |
| `/cancel` | Cancel current action |

### Reports include:
- Total sales, revenue, cost, gross profit
- **Markup %** = profit ÷ cost × 100
- **Margin %** = profit ÷ revenue × 100
- Debt amount + debt % of revenue
- Breakdown by category (markup & margin per category)
- Top 5 products by quantity sold

Periods: Today / This Week / This Month / All Time

---

## 🛒 Sales Bot — How it works

1. Tap **🛒 New Sale**
2. Tap products to add them (stock shown in brackets)
3. Enter quantity for each
4. Tap **✅ Done adding**
5. Type customer name
6. Choose **💵 Cash** or **📋 Will Pay**
7. Review summary → tap **✅ Confirm Sale**

Done! Stock is automatically deducted.

The salesperson can also tap **📋 Check Stock** anytime to see what's available.

---

## 📝 Notes

- Both bots connect to the **same `retail.db` file** — set `DB_PATH` to the same path for both
- On Railway with a Volume mounted at `/data`, use `DB_PATH=/data/retail.db`
- Debt sales are logged but not tracked — handle debt collection manually
- To add more salespersons in the future, the access control in `sales_bot.py` can be extended
