import os
import json
import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)
from keep_alive import keep_alive

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "expenses.json"
CHAT_ID_FILE = "chat_id.txt"
DEFAULT_BUDGET = 11000

DAILY_LIMITS = {
    "Mon": 234, "Tue": 234, "Wed": 234, "Thu": 234, "Fri": 234,
    "Sat": 154, "Sun": 654
}
ITEM_PRICES = {"cigarette": 18, "coke": 20, "breakfast": 0, "fuel": 0, "others": 0}
CATEGORY_SELECT, QUANTITY_SELECT, CUSTOM_AMOUNT = range(3)
RESET_SELECT_DATE, RESET_CHOOSE_ACTION, RESET_EDIT_AMOUNT = range(3, 6)

pending_input = {}

def get_today_key():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def get_yesterday_key():
    return (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

def get_month_key():
    return datetime.datetime.now().strftime("%Y-%m")

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_chat_id(chat_id):
    with open(CHAT_ID_FILE, "w") as f:
        f.write(str(chat_id))

def load_chat_id():
    if os.path.exists(CHAT_ID_FILE):
        with open(CHAT_ID_FILE, "r") as f:
            return int(f.read())
    return None

# ---------------- START & HELP ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "👋 Welcome to Budget Bot!\n\n"
        "Commands:\n"
        "/setbudget <amount>\n"
        "/bonus\n/spend\n/summary\n/report\n/reset\n/test9am\n/help"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def setbudget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = int(context.args[0])
    except:
        await update.message.reply_text("❌ Usage: /setbudget 11000")
        return
    data = load_data()
    m = get_month_key()
    data.setdefault(m, {"monthly_budget": amt, "days": {}, "bonus": {}})
    data[m]["monthly_budget"] = amt
    save_data(data)
    await update.message.reply_text(f"✅ Budget set to ₹{amt}")

# ---------------- BONUS (AUTO) ----------------

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    m, y = get_month_key(), get_yesterday_key()
    yesterday = datetime.datetime.strptime(y, "%Y-%m-%d").strftime("%a")
    limit = DAILY_LIMITS.get(yesterday, 234)
    spent = sum(data.get(m, {}).get("days", {}).get(y, {}).values())
    saved = limit - spent
    if saved <= 0:
        await update.message.reply_text("🛑 No bonus. You spent full or over.")
        return
    data[m]["bonus"][y] = data[m]["bonus"].get(y, 0) + saved
    save_data(data)
    await update.message.reply_text(f"🎉 Bonus ₹{saved} added from yesterday!")

# ---------------- SPEND TRACKING ----------------

async def spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("🚬 Cigarette", callback_data="cigarette")],
          [InlineKeyboardButton("🥤 Coke", callback_data="coke")],
          [InlineKeyboardButton("🍽 Breakfast", callback_data="breakfast")],
          [InlineKeyboardButton("⛽ Fuel", callback_data="fuel")],
          [InlineKeyboardButton("📦 Others", callback_data="others")]]
    await update.message.reply_text("🧾 Choose category:", reply_markup=InlineKeyboardMarkup(kb))
    return CATEGORY_SELECT

async def category_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cat = q.data
    context.user_data["category"] = cat
    if cat == "cigarette":
        kb = [[InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 4)],
              [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(4, 7)],
              [InlineKeyboardButton("Full Packet", callback_data="full")]]
        await q.edit_message_text("🚬 How many cigarettes?")
        await q.edit_message_reply_markup(InlineKeyboardMarkup(kb))
        return QUANTITY_SELECT
    elif cat == "coke":
        kb = [[InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 4)],
              [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(4, 6)]]
        await q.edit_message_text("🥤 How many cokes?")
        await q.edit_message_reply_markup(InlineKeyboardMarkup(kb))
        return QUANTITY_SELECT
    else:
        await q.edit_message_text("💸 Enter amount:")
        return CUSTOM_AMOUNT

async def quantity_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    qty = q.data
    cat = context.user_data.get("category")
    amount = 170 if qty == "full" and cat == "cigarette" else int(qty) * ITEM_PRICES[cat]
    data = load_data()
    m, d = get_month_key(), get_today_key()
    data.setdefault(m, {"monthly_budget": DEFAULT_BUDGET, "days": {}, "bonus": {}})
    data[m]["days"].setdefault(d, {})
    data[m]["days"][d][cat] = data[m]["days"][d].get(cat, 0) + amount
    save_data(data)
    await q.edit_message_text(f"✅ Logged ₹{amount} for {cat.capitalize()}")
    return ConversationHandler.END

async def custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = int(update.message.text)
    except:
        await update.message.reply_text("❌ Enter number.")
        return CUSTOM_AMOUNT
    cat = context.user_data.get("category")
    data = load_data()
    m, d = get_month_key(), get_today_key()
    data.setdefault(m, {"monthly_budget": DEFAULT_BUDGET, "days": {}, "bonus": {}})
    data[m]["days"].setdefault(d, {})
    data[m]["days"][d][cat] = data[m]["days"][d].get(cat, 0) + amt
    save_data(data)
    await update.message.reply_text(f"✅ Logged ₹{amt} for {cat.capitalize()}")
    return ConversationHandler.END

# ---------------- DASHBOARD / REPORT ----------------

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    m, d = get_month_key(), get_today_key()
    month_data = data.get(m, {})
    today_data = month_data.get("days", {}).get(d, {})
    today = datetime.datetime.now().strftime("%A, %d %B %Y")
    spent_total = sum(sum(day.values()) for day in month_data.get("days", {}).values())
    daily_limit = DAILY_LIMITS.get(datetime.datetime.now().strftime("%a"), 234)
    spent_today = sum(today_data.values())
    msg = f"""
📆 {today}
💰 Monthly Budget: ₹{month_data.get('monthly_budget', DEFAULT_BUDGET)}
💸 Spent So Far: ₹{spent_total}
💵 Remaining: ₹{month_data.get('monthly_budget', DEFAULT_BUDGET) - spent_total}

📅 Today's Limit: ₹{daily_limit}
💸 Spent Today: ₹{spent_today}
💵 Left Today: ₹{daily_limit - spent_today}

🧾 Breakdown:
""" + "\n".join([f"- {k.capitalize()}: ₹{v}" for k, v in today_data.items()])
    await update.message.reply_text(msg.strip())

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    m = get_month_key()
    msg = f"📆 Report for {m}:\n"
    for day, cats in data.get(m, {}).get("days", {}).items():
        msg += f"\n📅 {day}\n"
        for c, v in cats.items():
            msg += f"• {c}: ₹{v}\n"
    await update.message.reply_text(msg or "No data yet.")

# ---------------- RESET MENU ----------------

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("🗓 Daily", callback_data="daily")]]
    await update.message.reply_text("🔄 Choose reset type:", reply_markup=InlineKeyboardMarkup(kb))
    return RESET_SELECT_DATE

async def reset_select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    m = get_month_key()
    data = load_data()
    dates = list(data.get(m, {}).get("days", {}).keys())
    if not dates:
        await q.edit_message_text("📭 No data to reset.")
        return ConversationHandler.END
    buttons = [[InlineKeyboardButton(date, callback_data=date)] for date in dates]
    await q.edit_message_text("📅 Choose a date to manage:", reply_markup=InlineKeyboardMarkup(buttons))
    return RESET_CHOOSE_ACTION

async def reset_choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["reset_day"] = q.data
    data = load_data()
    m = get_month_key()
    categories = data.get(m, {}).get("days", {}).get(q.data, {})
    buttons = [[InlineKeyboardButton(f"{k}: ₹{v}", callback_data=k)] for k, v in categories.items()]
    await q.edit_message_text(f"📂 Edit {q.data}", reply_markup=InlineKeyboardMarkup(buttons))
    return RESET_EDIT_AMOUNT

async def reset_edit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cat = q.data
    context.user_data["reset_cat"] = cat
    await q.edit_message_text(f"❓ What to do with {cat}?\n[Edit] or [Delete]")
    return ConversationHandler.END  # You can extend here to support actual edit/delete logic

# ---------------- DAILY MESSAGE ----------------

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = load_chat_id()
    if not chat_id: return
    fake_update = Update(update_id=0, message=None)
    await summary(fake_update, context)

async def test_daily_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await summary(update, context)

# ---------------- MAIN ----------------

def main():
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    spend_conv = ConversationHandler(
        entry_points=[CommandHandler("spend", spend)],
        states={
            CATEGORY_SELECT: [CallbackQueryHandler(category_select)],
            QUANTITY_SELECT: [CallbackQueryHandler(quantity_select)],
            CUSTOM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_amount)]
        },
        fallbacks=[]
    )

    reset_conv = ConversationHandler(
        entry_points=[CommandHandler("reset", reset)],
        states={
            RESET_SELECT_DATE: [CallbackQueryHandler(reset_select_date)],
            RESET_CHOOSE_ACTION: [CallbackQueryHandler(reset_choose_action)],
            RESET_EDIT_AMOUNT: [CallbackQueryHandler(reset_edit_amount)],
        },
        fallbacks=[]
    )

    app.add_handler(spend_conv)
    app.add_handler(reset_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setbudget", setbudget))
    app.add_handler(CommandHandler("bonus", bonus))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("test9am", test_daily_message))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_bonus_entry))

    app.job_queue.run_daily(daily_job, time=datetime.time(hour=9, minute=0))
    app.run_polling()

if __name__ == "__main__":
    main()
