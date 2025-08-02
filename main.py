import os
import json
import datetime
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler, CallbackQueryHandler
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

ITEM_PRICES = {
    "cigarette": 18,
    "coke": 20,
    "breakfast": 0,
    "fuel": 0,
    "others": 0
}

CATEGORY_SELECT, QUANTITY_SELECT, CUSTOM_AMOUNT = range(3)
pending_input = {}

def get_today_key():
    return datetime.datetime.now().strftime("%Y-%m-%d")

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

# ------------------------- Bot Commands -------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "👋 Welcome to Budget Bot!\n\n"
        "📘 Commands:\n"
        "/setbudget <amount> - Set your monthly budget\n"
        "/bonus - Log bonus saved\n"
        "/spend - Log spending (smart categories)\n"
        "/summary - See daily & monthly status\n"
        "/report - Show full month log\n"
        "/reset - Clear today’s data\n"
        "/test9am - Simulate daily dashboard\n"
        "/help - Show this menu"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def setbudget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Use like this: /setbudget 11000")
        return
    data = load_data()
    month = get_month_key()
    data.setdefault(month, {"monthly_budget": amount, "days": {}, "bonus": {}})
    data[month]["monthly_budget"] = amount
    save_data(data)
    await update.message.reply_text(f"✅ Budget set to ₹{amount}")

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 How much bonus did you save today?")
    pending_input[update.effective_user.id] = "bonus"

async def handle_bonus_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in pending_input and pending_input[user_id] == "bonus":
        try:
            amount = int(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ Please enter a number.")
            return
        data = load_data()
        month = get_month_key()
        today = get_today_key()
        data.setdefault(month, {"monthly_budget": DEFAULT_BUDGET, "days": {}, "bonus": {}})
        data[month]["bonus"][today] = data[month]["bonus"].get(today, 0) + amount
        save_data(data)
        del pending_input[user_id]
        await update.message.reply_text(f"✅ Bonus ₹{amount} logged.")
        return True
    return False

# ---------------------- Spend Conversation ----------------------

async def spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🚬 Cigarette", callback_data="cigarette")],
        [InlineKeyboardButton("🥤 Coke", callback_data="coke")],
        [InlineKeyboardButton("🍽 Breakfast", callback_data="breakfast")],
        [InlineKeyboardButton("⛽ Fuel", callback_data="fuel")],
        [InlineKeyboardButton("📦 Others", callback_data="others")]
    ]
    await update.message.reply_text("🧾 Choose category:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY_SELECT

async def category_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data
    context.user_data["category"] = cat

    if cat == "cigarette":
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(4, 7)],
            [InlineKeyboardButton("Full Packet", callback_data="full")]
        ]
        await query.edit_message_text("🚬 How many cigarettes?")
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        return QUANTITY_SELECT

    elif cat == "coke":
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(4, 6)],
        ]
        await query.edit_message_text("🥤 How many cokes?")
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        return QUANTITY_SELECT

    else:
        await query.edit_message_text("💸 Enter the amount:")
        return CUSTOM_AMOUNT

async def quantity_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    qty = query.data
    cat = context.user_data.get("category")

    if cat == "cigarette":
        amount = 170 if qty == "full" else int(qty) * ITEM_PRICES["cigarette"]
    else:
        amount = int(qty) * ITEM_PRICES[cat]

    data = load_data()
    month = get_month_key()
    today = get_today_key()
    data.setdefault(month, {"monthly_budget": DEFAULT_BUDGET, "days": {}, "bonus": {}})
    data[month]["days"].setdefault(today, {})
    data[month]["days"][today][cat] = data[month]["days"][today].get(cat, 0) + amount
    save_data(data)

    await query.edit_message_text(f"✅ Logged ₹{amount} for {cat.capitalize()}")
    return ConversationHandler.END

async def custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Enter a number.")
        return CUSTOM_AMOUNT

    cat = context.user_data.get("category")
    data = load_data()
    month = get_month_key()
    today = get_today_key()
    data.setdefault(month, {"monthly_budget": DEFAULT_BUDGET, "days": {}, "bonus": {}})
    data[month]["days"].setdefault(today, {})
    data[month]["days"][today][cat] = data[month]["days"][today].get(cat, 0) + amount
    save_data(data)

    await update.message.reply_text(f"✅ Logged ₹{amount} for {cat.capitalize()}")
    return ConversationHandler.END

# ---------------------- Reporting & Daily ----------------------

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    month = get_month_key()
    today = get_today_key()
    mdata = data.get(month, {})
    spent = sum([sum(day.values()) for day in mdata.get("days", {}).values()])
    today_spent = sum(mdata.get("days", {}).get(today, {}).values())
    limit = DAILY_LIMITS.get(datetime.datetime.now().strftime("%a"), 234)
    await update.message.reply_text(
        f"📊 Summary:\n"
        f"💰 Budget: ₹{mdata.get('monthly_budget', DEFAULT_BUDGET)}\n"
        f"💸 Spent: ₹{spent}\n"
        f"🟢 Left: ₹{mdata.get('monthly_budget', DEFAULT_BUDGET) - spent}\n\n"
        f"🎯 Today’s Limit: ₹{limit}\n"
        f"💸 Spent Today: ₹{today_spent}\n"
        f"💵 Left Today: ₹{limit - today_spent}"
    )

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    month = get_month_key()
    days = data.get(month, {}).get("days", {})
    msg = "📆 Monthly Report:\n"
    for day, logs in days.items():
        msg += f"\n📅 {day}:\n"
        for cat, amt in logs.items():
            msg += f"• {cat.capitalize()}: ₹{amt}\n"
    await update.message.reply_text(msg or "No data yet.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    month = get_month_key()
    today = get_today_key()
    data.get(month, {}).get("days", {}).pop(today, None)
    save_data(data)
    await update.message.reply_text("🧹 Cleared today’s log.")

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = load_chat_id()
    if not chat_id: return
    fake_update = Update(update_id=0, message=None)
    await summary(fake_update, context)

async def test_daily_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await summary(update, context)

# ------------------------- Main Setup -------------------------

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

    app.add_handler(spend_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setbudget", setbudget))
    app.add_handler(CommandHandler("bonus", bonus))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("test9am", test_daily_message))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_bonus_entry))

    app.job_queue.run_daily(daily_job, time=datetime.time(hour=9, minute=0))
    app.run_polling()

if __name__ == "__main__":
    main()
