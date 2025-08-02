import os
import json
import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, JobQueue
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "expenses.json"
CHAT_ID_FILE = "chat_id.txt"
DEFAULT_BUDGET = 11000

DAILY_LIMITS = {
    "Mon": 234, "Tue": 234, "Wed": 234, "Thu": 234, "Fri": 234,
    "Sat": 154, "Sun": 654
}

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

# ✅ /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "👋 Welcome to Budget Bot!\n\n"
        "Use /setbudget <amount> to set your monthly budget.\n"
        "Use /bonus to log money you saved (e.g. skipped cigarette).\n"
        "Use /test9am to test tomorrow’s dashboard right now."
    )

# ✅ /setbudget
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

# ✅ /bonus
async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 How much bonus did you save today? (e.g., 40)")
    pending_input[update.effective_user.id] = "bonus"

# ✅ Handle number entry after /bonus
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

# ✅ 9AM Summary — Can be called by test9am or auto job
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
╔═══════════════╗
║  📅 DAILY DASH  ║
╚═══════════════╝

🔙 Yesterday — {yesterday_key}
━━━━━━━━━━━━━━━━━━
💸 Spent       : ₹{sum(yesterday_data.values())}
🎁 Bonus Saved : ₹{yesterday_bonus}
🧾 Breakdown:"""

    for cat, amt in yesterday_data.items():
        icon = {"cigarette": "🚬", "coke": "🥤", "breakfast": "🍽", "fuel": "⛽", "others": "📦"}.get(cat, "•")
        msg += f"\n• {icon} {cat.capitalize():10}: ₹{amt}"

    msg += f"""

🌞 Today — {today_str}
━━━━━━━━━━━━━━━━━━
🎯 Limit       : ₹{limit_today}
💸 Spent So Far: ₹{today_spent}
🟢 Left Today  : ₹{today_left}

💡 Tip: Skip coke today, save ₹20!
""".strip()

    await context.bot.send_message(chat_id=chat_id, text=msg)

# ✅ /test9am — manual trigger of daily dashboard
async def test_daily_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await daily_job(context)

# ✅ Main app setup
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setbudget", setbudget))
    app.add_handler(CommandHandler("bonus", bonus))
    app.add_handler(CommandHandler("test9am", test_daily_message))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_bonus_entry))

    # 9AM daily scheduled job
    app.job_queue.run_daily(daily_job, time=datetime.time(hour=9, minute=0))

    app.run_polling()

if __name__ == "__main__":
    main()
