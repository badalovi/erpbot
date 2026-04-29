"""
Sales Bot — simple step-by-step flow for the salesperson.
Steps: pick products → set quantities → customer name → payment → confirm → done.
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

TOKEN = os.environ["SALES_BOT_TOKEN"]
SALESPERSON_ID = int(os.environ["SALESPERSON_TELEGRAM_ID"])

# ── States ───────────────────────────────────────────────────────────────────
(
    BROWSING,
    ENTERING_QTY,
    BASKET_ACTION,
    CUSTOMER_NAME,
    PAYMENT,
    CONFIRMING,
    PARTIAL_AMOUNT,
) = range(7)


# ── Auth guard ───────────────────────────────────────────────────────────────

async def guard(update: Update) -> bool:
    if update.effective_user.id != SALESPERSON_ID:
        await update.message.reply_text("⛔ Access denied.")
        return False
    return True


# ── Helpers ──────────────────────────────────────────────────────────────────

def fmt(v):
    return f"{v:,.2f} ₼"

def basket_summary(basket: list) -> str:
    if not basket:
        return "_Empty basket_"
    lines = ["🛒 *Səbət:*\n"]
    total = 0
    for i, item in enumerate(basket, 1):
        subtotal = item["quantity"] * item["unit_price"]
        total += subtotal
        lines.append(f"{i}. {item['name']} × {item['quantity']} = {fmt(subtotal)}")
    lines.append(f"\n💰 *Total: {fmt(total)}*")
    return "\n".join(lines)

def product_buttons(products):
    buttons = []
    row = []
    for p in products:
        label = f"{p['name']} ({p['stock']})"
        row.append(InlineKeyboardButton(label, callback_data=f"pick_{p['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✅ Əlavə edib bitirdim", callback_data="basket_done")])
    return InlineKeyboardMarkup(buttons)

def payment_keyboard():
    return ReplyKeyboardMarkup([["💵 Nağd", "📋 Nisyə"]], resize_keyboard=True, one_time_keyboard=True)

def confirm_keyboard():
    return ReplyKeyboardMarkup([["✅ Satışı Təsdiqlə", "❌ Ləğv et"]], resize_keyboard=True, one_time_keyboard=True)


# ════════════════════════════════════════════════════════════════════════════
# START / MAIN MENU
# ════════════════════════════════════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    #if not await guard(update): return
    await update.message.reply_text(
        "👋 Hello!\n\nUse the buttons below:",
        reply_markup=ReplyKeyboardMarkup(
            [["🛒 Yeni Satış", "💳 Nisyələr"]],
            resize_keyboard=True
        )
    )

async def menu_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "💳 Nisyələr":
        await show_debts(update, ctx)
    elif text == "🛒 Yeni Satış":
        await new_sale_start(update, ctx)


# ════════════════════════════════════════════════════════════════════════════
# STOCK VIEW (read-only)
# ════════════════════════════════════════════════════════════════════════════

async def show_debts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = db.get_debts()
    if not rows:
        await update.message.reply_text("✅ Heç bir nisyə yoxdur.")
        return
    total = sum(r['remaining'] or r['total_revenue'] for r in rows)
    await update.message.reply_text(f"💳 *Nisyələr*\n\n💰 Ümumi qalıq: {round(total)} ₼", parse_mode="Markdown")
    for r in rows:
        remaining = r['remaining'] if r['remaining'] is not None else r['total_revenue']
        await update.message.reply_text(
            f"👤 {r['customer_name']}\n💰 Ümumi: {round(r['total_revenue'])} ₼  |  Qalıq: {round(remaining)} ₼  |  {r['created_at'][:10]}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Tam Ödənildi", callback_data=f"paid_{r['id']}"),
                 InlineKeyboardButton("💸 Qismən Ödədi", callback_data=f"partial_{r['id']}")]
            ])
        )


# ════════════════════════════════════════════════════════════════════════════
# NEW SALE FLOW
# ════════════════════════════════════════════════════════════════════════════

async def new_sale_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    #if not await guard(update): return
    products = [p for p in db.get_products() if p["stock"] > 0]
    if not products:
        await update.message.reply_text("❌ No products in stock. Ask admin to restock.")
        return ConversationHandler.END

    ctx.user_data["basket"] = []
    ctx.user_data["products"] = {p["id"]: dict(p) for p in products}

    await update.message.reply_text(
        "🛒 *Yeni Satış*\n\nƏlavə edəcəyin produkta vur.\nMötərizədəki ədədlər = mövcud stok.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text(
        "Produktları Seç:",
        reply_markup=product_buttons(products)
    )
    return BROWSING


async def product_picked(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """User tapped a product button."""
    query = update.callback_query
    await query.answer()

    if query.data == "basket_done":
        basket = ctx.user_data.get("basket", [])
        if not basket:
            await query.edit_message_text("🛒 Səbət boşdur. Ən azı bir produkt seç")
            await query.message.reply_text("Produktları Seç:", reply_markup=product_buttons(list(ctx.user_data["products"].values())))
            return BROWSING

        await query.edit_message_text(basket_summary(basket), parse_mode="Markdown")
        await query.message.reply_text(
            "Nəsə əlavə edirsən ?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Nəsə əlavə edirsən", callback_data="add_more"),
                 InlineKeyboardButton("➡️ Bitdi, Davam elə", callback_data="proceed")]
            ])
        )
        return BASKET_ACTION

    prod_id = int(query.data.split("_")[1])
    ctx.user_data["current_product_id"] = prod_id
    prod = ctx.user_data["products"][prod_id]
    await query.edit_message_text(
        f"*{prod['name']}*\nQiymət: {fmt(prod['sell_price'])} | Stok: {prod['stock']}\n\nSayı yaz:",
        parse_mode="Markdown"
    )
    return ENTERING_QTY


async def quantity_entered(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """User typed a quantity."""
    try:
        qty = int(update.message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Zəhmət olmasa 0-dan böyük ədəd daxil edin.")
        return ENTERING_QTY

    prod_id = ctx.user_data["current_product_id"]
    prod = ctx.user_data["products"][prod_id]

    if qty > prod["stock"]:
        await update.message.reply_text(f"❌ Only {prod['stock']} in stock. Enter a smaller quantity:")
        return ENTERING_QTY

    # Update basket
    basket = ctx.user_data["basket"]
    existing = next((item for item in basket if item["product_id"] == prod_id), None)
    if existing:
        existing["quantity"] += qty
    else:
        basket.append({
            "product_id": prod_id,
            "name": prod["name"],
            "quantity": qty,
            "unit_cost": prod["cost_price"],
            "unit_price": prod["sell_price"],
        })

    await update.message.reply_text(
        f"✅ Added {qty} × {prod['name']}\n\n{basket_summary(basket)}",
        parse_mode="Markdown"
    )

    # Show products again
    products = list(ctx.user_data["products"].values())
    await update.message.reply_text("Başqa mallar da əlavə et ya da işarəyə bas ✅:", reply_markup=product_buttons(products))
    return BROWSING


async def basket_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Add more or proceed to customer name."""
    query = update.callback_query
    await query.answer()

    if query.data == "add_more":
        products = list(ctx.user_data["products"].values())
        await query.edit_message_text("Choose more products:")
        await query.message.reply_text("Produktlar:", reply_markup=product_buttons(products))
        return BROWSING

    # Proceed → ask customer name
    await query.edit_message_text("Müştəri adı?")
    await query.message.reply_text("Müştəri adını daxil edin:", reply_markup=ReplyKeyboardRemove())
    return CUSTOMER_NAME


async def customer_name_entered(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Zəhmət olmasa ad daxil edin.")
        return CUSTOMER_NAME
    ctx.user_data["customer_name"] = name
    await update.message.reply_text(
        f"*{name}* Ödənişi necə edir?",
        parse_mode="Markdown",
        reply_markup=payment_keyboard()
    )
    return PAYMENT


async def payment_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "💵 Nağd":
        ctx.user_data["payment_type"] = "cash"
    elif text == "📋 Nisyə":
        ctx.user_data["payment_type"] = "debt"
    else:
        await update.message.reply_text("Zəhmət olmasa Nağd və ya Nisyə seçin.", reply_markup=payment_keyboard())
        return PAYMENT

    basket = ctx.user_data["basket"]
    total = sum(i["quantity"] * i["unit_price"] for i in basket)
    payment_label = "💵 Cash" if ctx.user_data["payment_type"] == "cash" else "📋 Will Pay (Debt)"

    summary = basket_summary(basket)
    summary += f"\n\n👤 Müştəri: *{ctx.user_data['customer_name']}*"
    summary += f"\n💳 Ödəniş: *{payment_label}*"

    await update.message.reply_text(
        f"{summary}\n\nSatışı təsdiqləyirsən?",
        parse_mode="Markdown",
        reply_markup=confirm_keyboard()
    )
    return CONFIRMING


async def confirm_sale(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "❌ Ləğv et":
        await update.message.reply_text(
            "❌ Satış ləğv edildi.",
            reply_markup=ReplyKeyboardMarkup([["🛒 Yeni Satış", "💳 Nisyələr"]], resize_keyboard=True)
        )
        return ConversationHandler.END

    if text != "✅ Satışı Təsdiqlə":
        await update.message.reply_text("Təsdiq yaxud Ləğv Et-i bas.", reply_markup=confirm_keyboard())
        return CONFIRMING

    basket = ctx.user_data["basket"]
    customer = ctx.user_data["customer_name"]
    payment = ctx.user_data["payment_type"]

    items = [{
        "product_id": i["product_id"],
        "quantity": i["quantity"],
        "unit_cost": i["unit_cost"],
        "unit_price": i["unit_price"],
    } for i in basket]

    try:
        sale_id, total_cost, total_revenue = db.create_sale(customer, payment, items)
        profit = total_revenue - total_cost
        payment_label = "💵 Nağd" if payment == "cash" else "📋 Nisyə"

        await update.message.reply_text(
            f"✅ *Sale #{sale_id} recorded!*\n\n"
            f"👤 {customer}\n"
            f"💰 Yekun: {fmt(total_revenue)}\n"
            f"💳 {payment_label}",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["🛒 Yeni Satış", "💳 Nisyələr"]], resize_keyboard=True)
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error saving sale: {e}",
            reply_markup=ReplyKeyboardMarkup([["🛒 Yeni Satış", "💳 Nisyələr"]], resize_keyboard=True)
        )

    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
# CANCEL
# ════════════════════════════════════════════════════════════════════════════

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Ləğv edildi.",
        reply_markup=ReplyKeyboardMarkup([["🛒 Yeni Satış", "💳 Nisyələr"]], resize_keyboard=True)
    )
    return ConversationHandler.END



async def debt_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sale_id = int(query.data.split("_")[1])
    db.mark_debt_paid(sale_id)
    await query.edit_message_text(query.message.text + "\n\n✅ Tam ödənildi!")

async def debt_partial_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sale_id = int(query.data.split("_")[1])
    ctx.user_data["partial_sale_id"] = sale_id
    await query.message.reply_text("Nə qədər ödədi? (₼ ilə yaz):")
    return PARTIAL_AMOUNT

async def debt_partial_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Düzgün məbləğ daxil edin:")
        return PARTIAL_AMOUNT

    sale_id = ctx.user_data["partial_sale_id"]
    remaining = db.pay_partial(sale_id, amount)

    if remaining == 0:
        await update.message.reply_text("✅ Borcun hamısı ödənildi!")
    else:
        await update.message.reply_text(f"💸 Ödəniş qeyd edildi.\n💰 Qalan borc: {round(remaining)} ₼")
    return ConversationHandler.END



# ════════════════════════════════════════════════════════════════════════════
# APP SETUP
# ════════════════════════════════════════════════════════════════════════════

def main():
    db.init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nisyeler", show_debts))
    app.add_handler(CommandHandler("cancel", cancel))

    # New sale conversation
    sale_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🛒 Yeni Satış$"), new_sale_start),
            CommandHandler("newsale", new_sale_start),
        ],
        states={
            BROWSING:      [CallbackQueryHandler(product_picked)],
            ENTERING_QTY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_entered)],
            BASKET_ACTION: [CallbackQueryHandler(basket_action)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_name_entered)],
            PAYMENT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_chosen)],
            CONFIRMING:    [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_sale)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(sale_conv)

    # Partial payment conversation
    partial_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(debt_partial_start, pattern=r"^partial_")],
        states={
            PARTIAL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, debt_partial_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(partial_conv)

    # Full debt paid button
    app.add_handler(CallbackQueryHandler(debt_paid, pattern=r"^paid_"))

    # General menu
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router))

    print("✅ Sales Bot running...")
    app.run_polling()




if __name__ == "__main__":
    main()

