import os
import json
import datetime
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "expenses.json"
DEFAULT_BUDGET = 11000

DAILY_LIMITS = {
    "Mon": 234, "Tue": 234, "Wed": 234, "Thu": 234, "Fri": 234,
    "Sat": 154, "Sun": 654
}

CATEGORY_PRICES = {
    "cigarette": 18,
    "cigarette_full": 170,
    "coke": 20
}

pending_input = {}  # Tracks what category user is inputting manually

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Budget Bot!\n"
        "Use /setbudget <amount> to set your monthly budget.\n"
        "Use /spend to log an expense.\n"
        "Use /summary to see your spending summary."
    )

async def setbudget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Use: /setbudget 11000")
        return

    data = load_data()
    month_key = get_month_key()
    if month_key not in data:
        data[month_key] = {"monthly_budget": amount, "days": {}}
    else:
        data[month_key]["monthly_budget"] = amount
    save_data(data)
    await update.message.reply_text(f"✅ Monthly budget set to ₹{amount}")

async def spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("Cigarette", callback_data="spend_cigarette")],
        [InlineKeyboardButton("Coke", callback_data="spend_coke")],
        [InlineKeyboardButton("Breakfast", callback_data="spend_breakfast")],
        [InlineKeyboardButton("Fuel", callback_data="spend_fuel")],
        [InlineKeyboardButton("Others", callback_data="spend_others")]
    ]
    await update.message.reply_text(
        "What did you buy?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("spend_cigarette"):
        buttons = [
            [InlineKeyboardButton(str(i), callback_data=f"cig_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=f"cig_{i}") for i in range(4, 7)],
            [InlineKeyboardButton("Full Packet", callback_data="cig_full")]
        ]
        await query.edit_message_text("How many cigarettes?", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("spend_coke"):
        buttons = [
            [InlineKeyboardButton(str(i), callback_data=f"coke_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=f"coke_{i}") for i in range(4, 7)],
        ]
        await query.edit_message_text("How many cokes?", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("spend_"):
        category = data.split("_")[1]
        pending_input[query.from_user.id] = category
        await query.edit_message_text(f"Enter amount for {category} (e.g., 60):")

async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user_id = update.effective_user.id
    text = update.message.text
    month = get_month_key()
    day = get_today_key()
    data.setdefault(month, {"monthly_budget": DEFAULT_BUDGET, "days": {}})
    data[month]["days"].setdefault(day, {})

    if user_id in pending_input:
        category = pending_input.pop(user_id)
        try:
            amount = int(text)
        except ValueError:
            await update.message.reply_text("❌ Please enter a number.")
            return
        data[month]["days"][day][category] = data[month]["days"][day].get(category, 0) + amount
        save_data(data)
        await update.message.reply_text("✅ Added.", reply_markup=ReplyKeyboardRemove())
        await send_summary(update, context)
        return

async def handle_button_quantities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    month = get_month_key()
    day = get_today_key()
    data.setdefault(month, {"monthly_budget": DEFAULT_BUDGET, "days": {}})
    data[month]["days"].setdefault(day, {})

    if query.data.startswith("cig_"):
        qty = query.data.split("_")[1]
        if qty == "full":
            amount = CATEGORY_PRICES["cigarette_full"]
        else:
            amount = int(qty) * CATEGORY_PRICES["cigarette"]
        data[month]["days"][day]["cigarette"] = data[month]["days"][day].get("cigarette", 0) + amount
        save_data(data)
        await query.edit_message_text("✅ Cigarette added.")
        await send_summary(query, context, is_query=True)

    elif query.data.startswith("coke_"):
        qty = int(query.data.split("_")[1])
        amount = qty * CATEGORY_PRICES["coke"]
        data[month]["days"][day]["coke"] = data[month]["days"][day].get("coke", 0) + amount
        save_data(data)
        await query.edit_message_text("✅ Coke added.")
        await send_summary(query, context, is_query=True)

async def send_summary(source, context, is_query=False):
    today = datetime.datetime.now()
    weekday = today.strftime("%a")
    month = get_month_key()
    day = get_today_key()
    data = load_data()
    monthly = data.get(month, {})
    budget = monthly.get("monthly_budget", DEFAULT_BUDGET)
    all_days = monthly.get("days", {})
    today_data = all_days.get(day, {})

    daily_total = sum(today_data.values())
    monthly_total = sum(sum(d.values()) for d in all_days.values())
    remaining = budget - monthly_total
    daily_limit = DAILY_LIMITS.get(weekday, 234)
    daily_left = daily_limit - daily_total

    categories = ["cigarette", "coke", "breakfast", "fuel", "others"]
    lines = []
    for cat in categories:
        amt = today_data.get(cat, 0)
        if amt > 0:
            lines.append(f"{cat.capitalize()}: ₹{amt}")

    msg = f"""
📆 {today.strftime("%A, %d %B %Y")}
💰 Budget: ₹{budget} | Spent: ₹{monthly_total} | Left: ₹{remaining}
📅 Daily Limit: ₹{daily_limit} | Spent Today: ₹{daily_total} | Left Today: ₹{daily_left}

🧾 Category-wise:
""" + "\n".join(lines)

    if is_query:
        await source.message.reply_text(msg)
    else:
        await source.message.reply_text(msg)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setbudget", setbudget))
    app.add_handler(CommandHandler("spend", spend))
    app.add_handler(CommandHandler("summary", send_summary))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern="^spend_.*"))
    app.add_handler(CallbackQueryHandler(handle_button_quantities, pattern="^(cig_|coke_).*"))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_quantity))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
