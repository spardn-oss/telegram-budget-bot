import os
import json
import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler, ContextTypes
)
from keep_alive import keep_alive

# === Configuration ===
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

# === Utils ===
def get_today(): return datetime.datetime.now().strftime("%Y-%m-%d")
def get_yesterday(): return (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
def get_dayname(date): return datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%a")
def get_month(): return datetime.datetime.now().strftime("%Y-%m")

def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r") as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=2)

def save_chat_id(chat_id):
    with open(CHAT_ID_FILE, "w") as f: f.write(str(chat_id))

def load_chat_id():
    if os.path.exists(CHAT_ID_FILE):
        with open(CHAT_ID_FILE, "r") as f: return int(f.read())
    return None

# === Commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "👋 Welcome to Budget Bot!\n\n"
        "💼 /setbudget <amount>\n"
        "💸 /spend – Add spending\n"
        "🎯 /bonus – Calculate bonus from yesterday\n"
        "📊 /summary – Show dashboard\n"
        "📅 /report – Full log\n"
        "🧹 /reset – Manage logs\n"
        "⏰ /test9am – Simulate daily push"
    )

async def setbudget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: amount = int(context.args[0])
    except: return await update.message.reply_text("❌ Usage: /setbudget 11000")
    data = load_data()
    m = get_month()
    data.setdefault(m, {"monthly_budget": amount, "days": {}, "bonus": {}})
    data[m]["monthly_budget"] = amount
    save_data(data)
    await update.message.reply_text(f"✅ Monthly budget set to ₹{amount}")

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    m = get_month()
    y = get_yesterday()
    if y not in data.get(m, {}).get("days", {}):
        return await update.message.reply_text("📭 No spend record for yesterday.")
    spent = sum(data[m]["days"][y].values())
    limit = DAILY_LIMITS.get(get_dayname(y), 234)
    saved = limit - spent
    if saved <= 0:
        return await update.message.reply_text("🛑 No bonus. Full or overspent.")
    data[m]["bonus"][y] = saved
    save_data(data)
    await update.message.reply_text(f"🎉 Saved ₹{saved} yesterday. Bonus logged!")

# === Spend Workflow ===
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
    if cat in ["cigarette", "coke"]:
        price = ITEM_PRICES[cat]
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(4, 7)] if cat == "cigarette" else []]
        if cat == "cigarette":
            keyboard.append([InlineKeyboardButton("Full Packet", callback_data="full")])
        await q.edit_message_text(f"How many {cat}s?")
        await q.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))
        return QUANTITY_SELECT
    else:
        await q.edit_message_text("💰 Enter amount spent:")
        return CUSTOM_AMOUNT

async def quantity_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cat = context.user_data.get("category")
    qty = q.data
    amt = 170 if cat == "cigarette" and qty == "full" else int(qty) * ITEM_PRICES[cat]
    data = load_data()
    m, d = get_month(), get_today()
    data.setdefault(m, {"monthly_budget": DEFAULT_BUDGET, "days": {}, "bonus": {}})
    data[m]["days"].setdefault(d, {})
    data[m]["days"][d][cat] = data[m]["days"][d].get(cat, 0) + amt
    save_data(data)
    await q.edit_message_text(f"✅ Logged ₹{amt} for {cat}")
    return ConversationHandler.END

async def custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: amt = int(update.message.text)
    except: return await update.message.reply_text("❌ Enter a number.")
    cat = context.user_data.get("category")
    data = load_data()
    m, d = get_month(), get_today()
    data.setdefault(m, {"monthly_budget": DEFAULT_BUDGET, "days": {}, "bonus": {}})
    data[m]["days"].setdefault(d, {})
    data[m]["days"][d][cat] = data[m]["days"][d].get(cat, 0) + amt
    save_data(data)
    await update.message.reply_text(f"✅ Logged ₹{amt} for {cat}")
    return ConversationHandler.END

# === Summary Dashboard ===
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    m, d = get_month(), get_today()
    month = data.get(m, {})
    today_data = month.get("days", {}).get(d, {})
    spent_total = sum(sum(day.values()) for day in month.get("days", {}).values())
    spent_today = sum(today_data.values())
    limit = DAILY_LIMITS.get(datetime.datetime.now().strftime("%a"), 234)
    left_today = limit - spent_today
    msg = f"""
📆 {datetime.datetime.now().strftime('%A, %d %B %Y')}

💰 Monthly Budget: ₹{month.get("monthly_budget", DEFAULT_BUDGET)}
💸 Spent So Far: ₹{spent_total}
💵 Remaining: ₹{month.get("monthly_budget", DEFAULT_BUDGET) - spent_total}

📅 Daily Limit: ₹{limit}
💸 Spent Today: ₹{spent_today}
💵 Left Today: ₹{left_today}

🧾 Breakdown:
""" + "\n".join([f"- {k.capitalize()}: ₹{v}" for k, v in today_data.items()])
    await update.message.reply_text(msg.strip())

# === Full Report ===
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    m = get_month()
    msg = f"📆 Report for {m}:\n"
    for day, logs in data.get(m, {}).get("days", {}).items():
        msg += f"\n📅 {day}:\n"
        for cat, amt in logs.items():
            msg += f"• {cat.capitalize()}: ₹{amt}\n"
    await update.message.reply_text(msg or "No data yet.")

# === Reset Command (Simplified) ===
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    m, d = get_month(), get_today()
    if m in data and d in data[m].get("days", {}):
        del data[m]["days"][d]
        save_data(data)
        await update.message.reply_text(f"🧹 Cleared data for {d}")
    else:
        await update.message.reply_text("📭 No data to clear for today.")

# === Scheduled 9AM Push ===
async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = load_chat_id()
    if not chat_id: return
    update = Update(update_id=0, message=None)
    await summary(update, context)

async def test_daily_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await summary(update, context)

# === Main ===
def main():
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("spend", spend)],
        states={
            CATEGORY_SELECT: [CallbackQueryHandler(category_select)],
            QUANTITY_SELECT: [CallbackQueryHandler(quantity_select)],
            CUSTOM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_amount)],
        },
        fallbacks=[]
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setbudget", setbudget))
    app.add_handler(CommandHandler("bonus", bonus))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("test9am", test_daily_message))

    app.job_queue.run_daily(daily_job, time=datetime.time(hour=9, minute=0))
    app.run_polling()

if __name__ == "__main__":
    main()
