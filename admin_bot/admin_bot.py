"""
Admin Bot — full control: categories, products, restock, reports.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)
import database as db

TOKEN = os.environ["ADMIN_BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_TELEGRAM_ID"])

# ── Conversation states ──────────────────────────────────────────────────────
(
    # Category
    CAT_NAME,
    # Product
    PROD_CAT, PROD_CODE, PROD_NAME, PROD_UNIT, PROD_COST, PROD_SELL,
    # Restock
    RS_PRODUCT, RS_QTY, RS_COST, RS_NOTE,
    # Edit product
    EDIT_PICK, EDIT_FIELD, EDIT_VALUE,
    # Delete
    DEL_CONFIRM,
    # Report period
    RPT_PERIOD,
) = range(16)


# ── Auth guard ───────────────────────────────────────────────────────────────

async def guard(update: Update) -> bool:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Access denied.")
        return False
    return True


# ── Helpers ──────────────────────────────────────────────────────────────────

def main_menu():
    keyboard = [
        ["📦 Products", "🗂 Categories"],
        ["🔄 Restock", "📊 Reports"],
        ["📋 Stock Levels"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def period_keyboard():
    return ReplyKeyboardMarkup(
        [["Today", "This Week"], ["This Month", "All Time"], ["🏠 Menu"]],
        resize_keyboard=True
    )

def fmt_money(v):
    return f"{v:,.2f} ₼" if v is not None else "0.00 ₼"

def pct(part, whole):
    if not whole:
        return 0.0
    return (part / whole) * 100


# ── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    await update.message.reply_text(
        "👋 Welcome, Admin!\nChoose an option below.",
        reply_markup=main_menu()
    )


# ── Menu router ──────────────────────────────────────────────────────────────

async def menu_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    text = update.message.text

    if text == "🗂 Categories":
        return await categories_menu(update, ctx)
    if text == "📦 Products":
        return await products_menu(update, ctx)
    if text == "🔄 Restock":
        return await restock_start(update, ctx)
    if text == "📊 Reports":
        return await reports_menu(update, ctx)
    if text == "📋 Stock Levels":
        return await stock_levels(update, ctx)
    if text == "🏠 Menu":
        await update.message.reply_text("Main menu:", reply_markup=main_menu())


# ════════════════════════════════════════════════════════════════════════════
# CATEGORIES
# ════════════════════════════════════════════════════════════════════════════

async def categories_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cats = db.get_categories()
    lines = ["🗂 *Categories*\n"]
    for c in cats:
        lines.append(f"• {c['name']} (ID: {c['id']})")
    if not cats:
        lines.append("_No categories yet._")
    lines.append("\n/addcat — Add new category")
    lines.append("/delcat — Delete a category")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=main_menu())


async def addcat_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    await update.message.reply_text("Enter new category name:", reply_markup=ReplyKeyboardRemove())
    return CAT_NAME

async def addcat_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    try:
        db.add_category(name)
        await update.message.reply_text(f"✅ Category *{name}* added!", parse_mode="Markdown", reply_markup=main_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", reply_markup=main_menu())
    return ConversationHandler.END


async def delcat_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    cats = db.get_categories()
    if not cats:
        await update.message.reply_text("No categories to delete.")
        return ConversationHandler.END
    buttons = [[InlineKeyboardButton(c["name"], callback_data=f"delcat_{c['id']}")] for c in cats]
    await update.message.reply_text("Select category to delete:", reply_markup=InlineKeyboardMarkup(buttons))
    return DEL_CONFIRM

async def delcat_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split("_")[1])
    db.delete_category(cat_id)
    await query.edit_message_text("✅ Category deleted.")
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ════════════════════════════════════════════════════════════════════════════

async def products_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    products = db.get_products()
    lines = ["📦 *Products*\n"]
    current_cat = None
    for p in products:
        cat = p["category_name"] or "Uncategorized"
        if cat != current_cat:
            lines.append(f"\n*{cat}*")
            current_cat = cat
        lines.append(f"  [{p['code'] or '—'}] {p['name']} | Stock: {p['stock']} {p['unit']} | Sell: {fmt_money(p['sell_price'])}")
    if not products:
        lines.append("_No products yet._")
    lines.append("\n/addproduct — Add product")
    lines.append("/editproduct — Edit product")
    lines.append("/delproduct — Delete product")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=main_menu())


# ── Add product ──────────────────────────────────────────────────────────────

async def addprod_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    cats = db.get_categories()
    if not cats:
        await update.message.reply_text("❌ Add at least one category first (/addcat).")
        return ConversationHandler.END
    buttons = [[InlineKeyboardButton(c["name"], callback_data=f"pc_{c['id']}")] for c in cats]
    await update.message.reply_text("Select category for new product:", reply_markup=InlineKeyboardMarkup(buttons))
    return PROD_CAT

async def addprod_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["new_prod"] = {"category_id": int(query.data.split("_")[1])}
    await query.edit_message_text("Enter product *code* (or type `skip` for none):", parse_mode="Markdown")
    return PROD_CODE

async def addprod_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["new_prod"]["code"] = None if val.lower() == "skip" else val
    await update.message.reply_text("Enter product *name*:", parse_mode="Markdown")
    return PROD_NAME

async def addprod_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_prod"]["name"] = update.message.text.strip()
    await update.message.reply_text("Enter *unit* (e.g. pcs, box, pack):", parse_mode="Markdown")
    return PROD_UNIT

async def addprod_unit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_prod"]["unit"] = update.message.text.strip()
    await update.message.reply_text("Enter *cost price* (what you paid per unit, in ₼):", parse_mode="Markdown")
    return PROD_COST

async def addprod_cost(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["new_prod"]["cost_price"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Invalid number. Enter cost price:")
        return PROD_COST
    await update.message.reply_text("Enter *selling price* (per unit, in ₼):", parse_mode="Markdown")
    return PROD_SELL

async def addprod_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["new_prod"]["sell_price"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Invalid number. Enter selling price:")
        return PROD_SELL
    p = ctx.user_data["new_prod"]
    try:
        db.add_product(p["code"], p["name"], p["category_id"], p["unit"], p["cost_price"], p["sell_price"])
        await update.message.reply_text(f"✅ Product *{p['name']}* added!", parse_mode="Markdown", reply_markup=main_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", reply_markup=main_menu())
    return ConversationHandler.END


# ── Delete product ───────────────────────────────────────────────────────────

async def delprod_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    products = db.get_products()
    if not products:
        await update.message.reply_text("No products to delete.")
        return ConversationHandler.END
    buttons = [[InlineKeyboardButton(f"[{p['code'] or '—'}] {p['name']}", callback_data=f"delprod_{p['id']}")] for p in products]
    await update.message.reply_text("Select product to delete:", reply_markup=InlineKeyboardMarkup(buttons))
    return DEL_CONFIRM

async def delprod_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = int(query.data.split("_")[1])
    db.delete_product(prod_id)
    await query.edit_message_text("✅ Product deleted.")
    return ConversationHandler.END


# ── Edit product ─────────────────────────────────────────────────────────────

async def editprod_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    products = db.get_products()
    if not products:
        await update.message.reply_text("No products to edit.")
        return ConversationHandler.END
    buttons = [[InlineKeyboardButton(f"[{p['code'] or '—'}] {p['name']}", callback_data=f"editpick_{p['id']}")] for p in products]
    await update.message.reply_text("Select product to edit:", reply_markup=InlineKeyboardMarkup(buttons))
    return EDIT_PICK

async def editprod_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = int(query.data.split("_")[1])
    p = db.get_product(prod_id)
    ctx.user_data["edit_prod"] = dict(p)
    fields = [
        [InlineKeyboardButton("Code", callback_data="ef_code"), InlineKeyboardButton("Name", callback_data="ef_name")],
        [InlineKeyboardButton("Unit", callback_data="ef_unit"), InlineKeyboardButton("Cost Price", callback_data="ef_cost_price")],
        [InlineKeyboardButton("Sell Price", callback_data="ef_sell_price")],
    ]
    await query.edit_message_text(
        f"Editing: *{p['name']}*\nWhat do you want to change?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(fields)
    )
    return EDIT_FIELD

async def editprod_field(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.split("_", 1)[1]
    ctx.user_data["edit_field"] = field
    labels = {"code": "code", "name": "name", "unit": "unit", "cost_price": "cost price (₼)", "sell_price": "selling price (₼)"}
    await query.edit_message_text(f"Enter new {labels.get(field, field)}:")
    return EDIT_VALUE

async def editprod_value(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    field = ctx.user_data["edit_field"]
    val = update.message.text.strip()
    p = ctx.user_data["edit_prod"]
    try:
        if field in ("cost_price", "sell_price"):
            p[field] = float(val.replace(",", "."))
        else:
            p[field] = val
        db.update_product(p["id"], p["code"], p["name"], p["category_id"], p["unit"], p["cost_price"], p["sell_price"])
        await update.message.reply_text(f"✅ Product updated!", reply_markup=main_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", reply_markup=main_menu())
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# RESTOCK
# ════════════════════════════════════════════════════════════════════════════

async def restock_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    products = db.get_products()
    if not products:
        await update.message.reply_text("No products found. Add products first.")
        return ConversationHandler.END
    buttons = [[InlineKeyboardButton(f"[{p['code'] or '—'}] {p['name']} (stock: {p['stock']})", callback_data=f"rs_{p['id']}")] for p in products]
    await update.message.reply_text("Select product to restock:", reply_markup=InlineKeyboardMarkup(buttons))
    return RS_PRODUCT

async def restock_product(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = int(query.data.split("_")[1])
    ctx.user_data["restock"] = {"product_id": prod_id}
    p = db.get_product(prod_id)
    await query.edit_message_text(f"Restocking *{p['name']}*\nEnter quantity received:", parse_mode="Markdown")
    return RS_QTY

async def restock_qty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["restock"]["quantity"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a whole number.")
        return RS_QTY
    await update.message.reply_text("Enter unit cost paid (₼ per unit):")
    return RS_COST

async def restock_cost(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["restock"]["unit_cost"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Invalid number.")
        return RS_COST
    await update.message.reply_text("Any note? (supplier name, invoice, etc.) — or type `skip`:")
    return RS_NOTE

async def restock_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    r = ctx.user_data["restock"]
    r["note"] = "" if note.lower() == "skip" else note
    try:
        db.restock_product(r["product_id"], r["quantity"], r["unit_cost"], r["note"])
        p = db.get_product(r["product_id"])
        await update.message.reply_text(
            f"✅ Restocked *{p['name']}*\n+{r['quantity']} units @ {fmt_money(r['unit_cost'])}\nNew stock: {p['stock']}",
            parse_mode="Markdown", reply_markup=main_menu()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", reply_markup=main_menu())
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# REPORTS
# ════════════════════════════════════════════════════════════════════════════

PERIOD_MAP = {"Today": "today", "This Week": "week", "This Month": "month", "All Time": "all"}

async def reports_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Select report period:", reply_markup=period_keyboard())
    return RPT_PERIOD

async def show_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    label = update.message.text
    if label == "🏠 Menu":
        await update.message.reply_text("Main menu:", reply_markup=main_menu())
        return ConversationHandler.END

    period = PERIOD_MAP.get(label)
    if not period:
        await update.message.reply_text("Please choose a period from the buttons.")
        return RPT_PERIOD

    s = db.report_summary(period)
    rev = s["revenue"] or 0
    cost = s["cost"] or 0
    profit = rev - cost
    debt = s["debt_amount"] or 0

    markup = pct(profit, cost)        # (profit/cost)*100 — markup %
    margin = pct(profit, rev)         # (profit/revenue)*100 — margin %
    debt_pct = pct(debt, rev)         # debt as % of revenue

    lines = [
        f"📊 *Report — {label}*\n",
        f"🧾 Total Sales: {s['total_sales']}",
        f"💰 Revenue: {fmt_money(rev)}",
        f"📦 Total Cost: {fmt_money(cost)}",
        f"✅ Gross Profit: {fmt_money(profit)}",
        f"📈 Markup: {markup:.1f}%  (profit / cost)",
        f"📉 Margin: {margin:.1f}%  (profit / revenue)",
        f"",
        f"💳 Debt Sales: {s['debt_count']} orders",
        f"💳 Debt Amount: {fmt_money(debt)}  ({debt_pct:.1f}% of revenue)",
    ]

    cats = db.report_by_category(period)
    if cats:
        lines.append("\n*By Category:*")
        for c in cats:
            c_rev = c["revenue"] or 0
            c_cost = c["cost"] or 0
            c_profit = c_rev - c_cost
            c_margin = pct(c_profit, c_rev)
            c_markup = pct(c_profit, c_cost)
            lines.append(
                f"  • {c['category']}: Rev {fmt_money(c_rev)} | Profit {fmt_money(c_profit)} | "
                f"Markup {c_markup:.1f}% | Margin {c_margin:.1f}%"
            )

    tops = db.report_top_products(period)
    if tops:
        lines.append("\n*Top Products:*")
        for i, t in enumerate(tops, 1):
            lines.append(f"  {i}. {t['name']} — {t['qty_sold']} sold | {fmt_money(t['revenue'])}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=main_menu())
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# STOCK LEVELS
# ════════════════════════════════════════════════════════════════════════════

async def stock_levels(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = db.get_stock_report()
    if not rows:
        await update.message.reply_text("No products found.", reply_markup=main_menu())
        return
    lines = ["📋 *Current Stock Levels*\n"]
    current_cat = None
    for r in rows:
        cat = r["category"] or "Uncategorized"
        if cat != current_cat:
            lines.append(f"\n*{cat}*")
            current_cat = cat
        lines.append(f"  [{r['code'] or '—'}] {r['name']}: {r['stock']} {r['unit']} | Cost: {fmt_money(r['cost_price'])} | Sell: {fmt_money(r['sell_price'])}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=main_menu())


# ════════════════════════════════════════════════════════════════════════════
# CANCEL
# ════════════════════════════════════════════════════════════════════════════

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=main_menu())
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# APP SETUP
# ════════════════════════════════════════════════════════════════════════════

def main():
    db.init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stock", stock_levels))

    # Add category
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("addcat", addcat_start)],
        states={CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, addcat_save)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Delete category
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delcat", delcat_start)],
        states={DEL_CONFIRM: [CallbackQueryHandler(delcat_confirm, pattern=r"^delcat_")]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Add product
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("addproduct", addprod_start)],
        states={
            PROD_CAT:  [CallbackQueryHandler(addprod_cat, pattern=r"^pc_")],
            PROD_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, addprod_code)],
            PROD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, addprod_name)],
            PROD_UNIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, addprod_unit)],
            PROD_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, addprod_cost)],
            PROD_SELL: [MessageHandler(filters.TEXT & ~filters.COMMAND, addprod_sell)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Delete product
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delproduct", delprod_start)],
        states={DEL_CONFIRM: [CallbackQueryHandler(delprod_confirm, pattern=r"^delprod_")]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Edit product
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("editproduct", editprod_start)],
        states={
            EDIT_PICK:  [CallbackQueryHandler(editprod_pick, pattern=r"^editpick_")],
            EDIT_FIELD: [CallbackQueryHandler(editprod_field, pattern=r"^ef_")],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, editprod_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Restock
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("restock", restock_start), MessageHandler(filters.Regex("^🔄 Restock$"), restock_start)],
        states={
            RS_PRODUCT: [CallbackQueryHandler(restock_product, pattern=r"^rs_")],
            RS_QTY:     [MessageHandler(filters.TEXT & ~filters.COMMAND, restock_qty)],
            RS_COST:    [MessageHandler(filters.TEXT & ~filters.COMMAND, restock_cost)],
            RS_NOTE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, restock_note)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Reports
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📊 Reports$"), reports_menu)],
        states={RPT_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, show_report)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # General menu handler
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        menu_router
    ))

    print("✅ Admin Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
