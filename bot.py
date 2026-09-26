import os
import re
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ইন-মেমোরি স্টোরেজ (ইউজারের ভাষা ও লাস্ট অ্যাক্টিভ সময়)
USER_DATA = {}

# যেসব লিংক বা স্প্যাম কি-ওয়ার্ড গ্রুপে ডিলিট হবে
SPAM_PATTERNS = [
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
    r"(?i)(free\s*crypto|earn\s*money|pump|giveaway|100x)"
]

def get_text(user_id, key):
    lang = USER_DATA.get(user_id, {}).get("lang", "en")
    path = f"locales/{lang}.json"
    if not os.path.exists(path):
        path = "locales/en.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get(key, "")

# ১. /start কমান্ড দিলে ভাষা নির্বাচন বাটন দেখাবে
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # ইউজারের অ্যাক্টিভিটি আপডেট
    USER_DATA[user.id] = {
        "lang": USER_DATA.get(user.id, {}).get("lang", "en"),
        "last_seen": datetime.utcnow(),
        "chat_id": chat.id
    }

    keyboard = [
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bn")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose your language / ভাষা নির্বাচন করুন:", reply_markup=reply_markup)

# ২. ভাষা সিলেক্ট করার পর মেনু দেখানো
async def language_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = query.data.split("_")[1]
    user_id = query.from_user.id

    if user_id not in USER_DATA:
        USER_DATA[user_id] = {"chat_id": query.message.chat_id}
    
    USER_DATA[user_id]["lang"] = lang
    USER_DATA[user_id]["last_seen"] = datetime.utcnow()

    welcome = get_text(user_id, "welcome")
    menu = get_text(user_id, "menu")
    await query.edit_message_text(f"{welcome}\n\n{menu}")

# ৩. ডিসকাশন গ্রুপে স্প্যাম মোছা ও অ্যাক্টিভিটি পর্যবেক্ষণ
async def group_moderator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or user.is_bot:
        return

    # ইউজার গ্রুপে মেসেজ দিলে তার লাস্ট অ্যাক্টিভ টাইম আপডেট হবে
    if user.id not in USER_DATA:
        USER_DATA[user.id] = {"lang": "en"}
    USER_DATA[user.id]["last_seen"] = datetime.utcnow()
    USER_DATA[user.id]["chat_id"] = chat.id

    text = message.text or message.caption or ""
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text):
            try:
                await message.delete()
                break
            except Exception as e:
                print(f"মেসেজ ডিলিট করতে সমস্যা: {e}")

# ৪. ১ মাস ইনঅ্যাক্টিভ ইউজারদের অটো-ব্যান করা (প্রতিদিন একবার চেক করবে)
async def auto_ban_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.utcnow()
    threshold = now - timedelta(days=30)
    
    to_remove = []
    for user_id, info in list(USER_DATA.items()):
        if info.get("last_seen") and info["last_seen"] < threshold:
            try:
                await context.bot.ban_chat_member(chat_id=info["chat_id"], user_id=user_id)
                to_remove.append(user_id)
                print(f"ইনঅ্যাক্টিভ ইউজার ব্যান করা হয়েছে: {user_id}")
            except Exception as e:
                print(f"ব্যান করতে সমস্যা হয়েছে ({user_id}): {e}")

    for uid in to_remove:
        del USER_DATA[uid]

def main():
    if not BOT_TOKEN:
        print("ভুল: TELEGRAM_BOT_TOKEN খুঁজে পাওয়া যায়নি!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # হ্যান্ডলার রেজিস্টার
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_select, pattern="^lang_"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, group_moderator))

    # ব্যাকগ্রাউন্ড শিডিউলার (প্রতি ২৪ ঘণ্টায় একবার ইনঅ্যাক্টিভ ইউজার চেক করবে)
    if app.job_queue:
        app.job_queue.run_repeating(auto_ban_inactive_users, interval=86400, first=60)

    print("বট সফলভাবে চালু হয়েছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
