import os
import json
import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackContext, ConversationHandler
)
from keep_alive import keep_alive  # for keeping port open on Render

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "expenses.json"
CHAT_ID_FILE = "chat_id.txt"
DEFAULT_BUDGET = 11000

DAILY_LIMITS = {
    "Mon": 234, "Tue": 234, "Wed": 234, "Thu": 234, "Fri": 234,
    "Sat": 154, "Sun": 654
}

pending_input = {}

CATEGORIES = ["cigarette", "coke", "breakfast", "fuel", "others"]
SPEND, AMOUNT = range(2)

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

# Command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "👋 Welcome to Budget Bot!\n"
        "Commands:\n"
        "/setbudget <amount> - Set your monthly budget\n"
        "/bonus - Log money saved\n"
        "/spend - Add expense by category\n"
        "/summary - Show budget summary\n"
        "/report - Full month report\n"
        "/reset - Delete or adjust log\n"
        "/test9am - Simulate daily summary\n"
        "/help - List all commands"
    )

# Command: /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# Command: /setbudget
async def setbudget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Use: /setbudget 11000")
        return
    data = load_data()
    month = get_month_key()
    data.setdefault(month, {"monthly_budget": amount, "days": {}, "bonus": {}})
    data[month]["monthly_budget"] = amount
    save_data(data)
    await update.message.reply_text(f"✅ Monthly budget set to ₹{amount}")

# Command: /bonus
async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 How much bonus did you save today? (e.g., 40)")
    pending_input[update.effective_user.id] = "bonus"

# Handle bonus reply
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
        day = get_today_key()
        data.setdefault(month, {"monthly_budget": DEFAULT_BUDGET, "days": {}, "bonus": {}})
        data[month]["bonus"][day] = data[month]["bonus"].get(day, 0) + amount
        save_data(data)
        del pending_input[user_id]
        await update.message.reply_text(f"✅ Bonus of ₹{amount} saved for today!")
        return True
    return False

# Command: /spend
async def spend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[KeyboardButton(cat.capitalize())] for cat in CATEGORIES]
    await update.message.reply_text(
        "🧾 Choose a category:",
        reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
    )
    return SPEND

# Handle category selected
async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["category"] = update.message.text.lower()
    await update.message.reply_text("💸 Enter amount spent:")
    return AMOUNT

# Handle amount input
async def amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Please enter a number.")
        return AMOUNT

    cat = context.user_data.get("category", "others").lower()
    data = load_data()
    month = get_month_key()
    today = get_today_key()
    data.setdefault(month, {"monthly_budget": DEFAULT_BUDGET, "days": {}, "bonus": {}})
    data[month]["days"].setdefault(today, {})
    data[month]["days"][today][cat] = data[month]["days"][today].get(cat, 0) + amount
    save_data(data)
    await update.message.reply_text(f"✅ Logged ₹{amount} under {cat.capitalize()}.")
    return ConversationHandler.END

# Command: /summary
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    month = get_month_key()
    today = get_today_key()
    mdata = data.get(month, {})
    spent = sum([sum(day.values()) for day in mdata.get("days", {}).values()])
    spent_today = sum(mdata.get("days", {}).get(today, {}).values())
    limit_today = DAILY_LIMITS.get(datetime.datetime.now().strftime("%a"), 234)
    rem_today = limit_today - spent_today
    rem_month = mdata.get("monthly_budget", DEFAULT_BUDGET) - spent
    await update.message.reply_text(
        f"📊 Summary:\n"
        f"💰 Monthly Budget: ₹{mdata.get('monthly_budget', DEFAULT_BUDGET)}\n"
        f"💸 Spent this month: ₹{spent}\n"
        f"💵 Remaining this month: ₹{rem_month}\n\n"
        f"🎯 Today Limit: ₹{limit_today}\n"
        f"💸 Spent Today: ₹{spent_today}\n"
        f"💵 Left Today: ₹{rem_today}"
    )

# Command: /report
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    month = get_month_key()
    mdata = data.get(month, {})
    days = mdata.get("days", {})
    summary = "📅 Monthly Report:\n"
    for day, cats in days.items():
        summary += f"\n📆 {day}:\n"
        for c, a in cats.items():
            summary += f"• {c.capitalize()}: ₹{a}\n"
    await update.message.reply_text(summary or "No data yet.")

# Command: /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    month = get_month_key()
    today = get_today_key()
    data.get(month, {}).get("days", {}).pop(today, None)
    save_data(data)
    await update.message.reply_text("🧹 Today's records have been reset.")

# /test9am
async def test_daily_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await daily_job(context)

# 9AM auto dashboard
async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = load_chat_id()
    if not chat_id:
        return

    data = load_data()
    month = get_month_key()
    today = datetime.datetime.now()
    today_str = today.strftime("%A, %d %B %Y")
    weekday = today.strftime("%a")
    yesterday_key = get_yesterday_key()
    today_key = get_today_key()
    limit_today = DAILY_LIMITS.get(weekday, 234)

    days = data.get(month, {}).get("days", {})
    bonus = data.get(month, {}).get("bonus", {})
    yesterday_data = days.get(yesterday_key, {})
    yesterday_bonus = bonus.get(yesterday_key, 0)
    today_spent = sum(days.get(today_key, {}).values())
    today_left = limit_today - today_spent

    msg = f"""
📆 {today_str}
💰 Monthly Budget: ₹{data[month]["monthly_budget"]}
💸 Spent So Far: ₹{sum([sum(day.values()) for day in days.values()])}
💵 Remaining: ₹{data[month]["monthly_budget"] - sum([sum(day.values()) for day in days.values()])}

📅 Today’s Limit: ₹{limit_today}
💸 Spent Today: ₹{today_spent}
💵 Left Today: ₹{today_left}

🧾 By Category Today:"""

    for cat, val in days.get(today_key, {}).items():
        msg += f"\n- {cat.capitalize()}: ₹{val}"

    await context.bot.send_message(chat_id=chat_id, text=msg.strip())

# Cancel handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# Main entry
def main():
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation handler for /spend
    spend_conv = ConversationHandler(
        entry_points=[CommandHandler("spend", spend)],
        states={
            SPEND: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_chosen)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_entered)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
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
