# -*- coding: utf-8 -*-

import requests
import json
import io
import random
from functools import wraps
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- CORE BOT CONFIGURATION ---
TOKEN = "8499790219:AAFBBCFOswo2b9Aj8y7HT1HiKB2P5od8fHQ"
API_URL = "https://numinfoapi.vercel.app/api/num?number="
CHANNEL_USERNAME = "@ToxicBack2025"
ADMIN_IDS = [7392785352]
SUPPORT_ADMIN = "@CDMAXX"

# --- DATABASE (IN-MEMORY DEMO) ---
# IMPORTANT: This data is lost when the bot restarts.
# For production, use a persistent database like SQLite.
user_data = {}
INITIAL_CREDITS = 2
REFERRAL_CREDIT = 1

# --- CONVERSATION HANDLER STATES ---
BROADCAST_MESSAGE = 0
GET_USER_ID, GET_CREDIT_AMOUNT = 1, 2

# --- DECORATOR: FORCE CHANNEL JOIN ---
def force_join(func):
    """Decorator to ensure a user is in the channel before using a command."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user: return
        user_id = update.effective_user.id
        if user_id in ADMIN_IDS: return await func(update, context, *args, **kwargs)
        try:
            member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                await update.message.reply_text(f"❗️ **Access Denied**\n\nTo use this bot, you must join our official channel.\nPlease join 👉 {CHANNEL_USERNAME} and then press /start.", parse_mode='HTML')
                return
        except Exception as e:
            print(f"Error checking channel membership for user {user_id}: {e}")
            await update.message.reply_text("⛔️ Error verifying channel membership. Please contact support.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- UTILITY: DYNAMIC KEYBOARD ---
def get_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Creates and returns a keyboard layout based on the user's role."""
    keyboard = [[KeyboardButton("Refer & Earn 🎁"), KeyboardButton("Buy Credits 💰")], [KeyboardButton("My Account 📊"), KeyboardButton("Help ❓")]]
    if user_id in ADMIN_IDS:
        admin_keyboard = [[KeyboardButton("Add Credit 👤"), KeyboardButton("Broadcast 📢")], [KeyboardButton("Member Status 👥")]]
        keyboard.extend(admin_keyboard)
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- HELPER FUNCTION: STYLISH REPORT MESSAGE ---
def format_real_record_as_message(record: dict, index: int, total: int) -> str:
    """Formats a REAL database record into a stylish, emoji-rich message."""
    raw_address = record.get('address', 'N/A')
    cleaned_parts = [part.strip() for part in raw_address.replace('!!', '!').split('!') if part.strip()]
    formatted_address = ", ".join(cleaned_parts)
    return (
        f"📊 **Record {index + 1} of {total}**\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 **Name:** `{record.get('name', 'N/A')}`\n"
        f"👨 **Father's Name:** `{record.get('fname', 'N/A')}`\n"
        f"📱 **Mobile:** `{record.get('mobile', 'N/A')}`\n"
        f"🏠 **Address:** `{formatted_address}`\n"
        f"📡 **Circle:** `{record.get('circle', 'N/A')}`"
    )

# --- CORE NUMBER LOOKUP LOGIC ---
@force_join
async def get_number_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all number lookups with robust error handling and credit refunds."""
    user_id = update.effective_user.id
    number = update.message.text.strip()
    
    # Pre-flight checks for user and number format
    if user_id not in user_data: await start(update, context); return
    if user_data[user_id].get('credits', 0) < 1:
        await update.message.reply_text("You have insufficient credits."); return
    if not number.isdigit() or len(number) < 10:
        await update.message.reply_text('Invalid format. Please send a valid 10-digit number.'); return

    processing_message = await update.message.reply_text('🔎 Accessing database... This will consume 1 credit.')
    
    try:
        # Pre-deduct credit for the attempt. It will be refunded on failure.
        user_data[user_id]['credits'] -= 1
        user_data[user_id]['searches'] += 1
        
        response = requests.get(f"{API_URL}{number}", timeout=15)
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)

        # SCENARIO 1: REAL DATA FOUND
        if isinstance(data, list) and data:
            summary_text = f"✅ **Database Report Generated!**\nFound **{len(data)}** record(s) for `{number}`. Details below:"
            await update.message.reply_text(summary_text, parse_mode='Markdown')
            for i, record in enumerate(data):
                await update.message.reply_text(format_real_record_as_message(record, i, len(data)), parse_mode='Markdown')
        else:
            # API returned success but data is empty/invalid. Treat as a failure.
            raise ValueError("No data found")

    except (requests.exceptions.HTTPError, ValueError):
        # SCENARIO 2: NO REAL DATA FOUND (API Error or Empty Data)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, 
            message_id=processing_message.message_id, 
            text="❌ **No Data Found.**\nPlease check the number and try again. Ensure you are entering a correct 10-digit number."
        )
        # Refund the credit since the search was unsuccessful
        user_data[user_id]['credits'] += 1
        user_data[user_id]['searches'] -= 1

    except requests.exceptions.RequestException:
        # SCENARIO 3: NETWORK ERROR
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="🌐 **Network Error.** Could not connect to the information service.")
        # Refund credit as it's a server-side issue
        user_data[user_id]['credits'] += 1
        user_data[user_id]['searches'] -= 1
        
    except Exception as e:
        # SCENARIO 4: UNEXPECTED ERROR
        print(f"Unexpected error in get_number_info: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="⚙️ **An unexpected error occurred.**")
        # Refund credit for fairness
        user_data[user_id]['credits'] += 1
        user_data[user_id]['searches'] -= 1
    
    # Finally, send the updated credit balance
    finally:
        await update.message.reply_text(f"💳 Credits remaining: **{user_data[user_id]['credits']}**", parse_mode='Markdown')

# --- OTHER COMMANDS AND BUTTONS (Unchanged) ---
@force_join
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, user_id = update.effective_user, update.effective_user.id
    if user_id not in user_data:
        try:
            if context.args:
                referrer_id = int(context.args[0])
                if referrer_id in user_data and referrer_id != user_id:
                    user_data[referrer_id]['credits'] += REFERRAL_CREDIT
                    new_balance = user_data[referrer_id]['credits']
                    await context.bot.send_message(chat_id=referrer_id, text=f"🎉 **1 Referral Received!**\nYour new balance is now **{new_balance} credits**.", parse_mode='HTML')
        except Exception as e:
            print(f"Error processing referral: {e}")
        notification_to_admin = f"🎉 New Member Alert!\nName: {user.first_name}\nProfile: [{user_id}](tg://user?id={user_id})"
        if user.username: notification_to_admin += f"\nUsername: @{user.username}"
        for admin_id in ADMIN_IDS:
            try: await context.bot.send_message(chat_id=admin_id, text=notification_to_admin, parse_mode='Markdown', disable_web_page_preview=True)
            except Exception as e: print(f"Failed to send new member notification to admin {admin_id}: {e}")
        user_data[user_id] = {'credits': INITIAL_CREDITS, 'searches': 0, 'join_date': datetime.now().strftime("%Y-%m-%d"), 'first_name': user.first_name, 'username': user.username}
        await update.message.reply_text(f"🎉 Welcome aboard, {user.first_name}!\n\nAs a new member, you've received **{INITIAL_CREDITS} free credits**.", parse_mode='HTML')
    reply_markup = get_reply_keyboard(user_id)
    await my_account_button(update, context, custom_reply_markup=reply_markup)

async def my_account_button(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_reply_markup=None) -> None:
    user, user_id = update.effective_user, update.effective_user.id
    if user_id not in user_data: await update.message.reply_text("Please press /start to register."); return
    reply_markup = custom_reply_markup or get_reply_keyboard(user_id)
    user_info = user_data[user_id]
    await update.message.reply_text(f"🎯 **Welcome, {user.first_name}!**\n\n" f"💳 **Your Credits:** {user_info['credits']}\n" f"📊 **Total Searches:** {user_info['searches']}\n" f"🗓️ **Member Since:** {user_info['join_date']}", reply_markup=reply_markup, parse_mode='HTML')

async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"❓ **Help & Support Center**\n\n" f"🔍 **How to Use:**\n• Send a phone number to get its report.\n• Each search costs 1 credit.\n\n" f"🎁 **Referral Program:**\n• Get {REFERRAL_CREDIT} credit per successful referral.\n\n" f"👤 **Support:** {SUPPORT_ADMIN}", parse_mode='Markdown')

async def refer_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_username = (await context.bot.get_me()).username
    await update.message.reply_text(f"**Invite friends & earn credits!** 🎁\n\n" f"Your link: `https://t.me/{bot_username}?start={update.effective_user.id}`", parse_mode='Markdown')

async def buy_credits_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"💰 **Buy Credits - Price List**\n" f"━━━━━━━━━━━━━━━━━━━━━━━━\n" f"💎 **STARTER** - 25 Credits (₹49)\n" f"🔥 **BASIC** - 100 Credits (₹149)\n" f"⭐ **PRO** - 500 Credits (₹499)\n" f"━━━━━━━━━━━━━━━━━━━━━━━━\n" f"💬 Contact admin to buy: {SUPPORT_ADMIN}", parse_mode='HTML')

async def member_status_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in ADMIN_IDS: return
    all_users_data, total_members = user_data.items(), len(user_data.items())
    bot_info = await context.bot.get_me()
    header = f"📊 **Bot Member Status**\nBot: [@{bot_info.username}](https://t.me/{bot_info.username})\nTotal Members: {total_members}\n➖➖➖➖➖➖➖➖➖➖➖➖\n"
    if total_members == 0: await update.message.reply_text(header + "No members yet.", parse_mode='Markdown', disable_web_page_preview=True); return
    def format_user_line(user_id, data):
        username_str = f"(@{data['username']})" if data.get('username') else ""
        return f"• {data.get('first_name', 'Unknown')} {username_str} - [{user_id}](tg://user?id={user_id})"
    if total_members <= 50:
        await update.message.reply_text(header + "\n".join([format_user_line(uid, udata) for uid, udata in all_users_data]), parse_mode='Markdown', disable_web_page_preview=True)
    else:
        file_content = "\n".join([f"{uid} - {udata.get('first_name', 'N/A')} (@{udata.get('username', 'N/A')}) - tg://user?id={uid}" for uid, udata in all_users_data])
        output_file = io.BytesIO(file_content.encode('utf-8')); output_file.name = 'member_list.txt'
        await context.bot.send_document(chat_id=update.effective_chat.id, document=output_file, caption=header + "\nMember list sent as a file.", parse_mode='Markdown', disable_web_page_preview=True)

async def add_credit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("👤 Send the User ID of the recipient.\n\n/cancel to abort."); return GET_USER_ID

async def get_user_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = int(update.message.text)
        if user_id not in user_data: await update.message.reply_text("⚠️ User not found. Try again or /cancel."); return GET_USER_ID
        context.user_data['target_user_id'] = user_id
        await update.message.reply_text(f"✅ User `{user_id}` found. Send the credit amount.", parse_mode='Markdown'); return GET_CREDIT_AMOUNT
    except ValueError: await update.message.reply_text("❗️Invalid ID. Send numbers only or /cancel."); return GET_USER_ID

async def get_credit_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = int(update.message.text)
        target_user_id = context.user_data.pop('target_user_id')
        user_data[target_user_id]['credits'] += amount
        await update.message.reply_text(f"✅ Success! Added `{amount}` credits to `{target_user_id}`.", parse_mode='Markdown')
        await context.bot.send_message(chat_id=target_user_id, text=f"🎉 Admin added **{amount} credits** to your account!"); return ConversationHandler.END
    except (ValueError, KeyError): await update.message.reply_text("❗️Invalid amount. Send numbers only or /cancel."); return GET_CREDIT_AMOUNT

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📢 Send the message to broadcast.\n\n/cancel to abort."); return BROADCAST_MESSAGE

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg, users, ok, fail = update.message.text, list(user_data.keys()), 0, 0
    await update.message.reply_text(f"⏳ Broadcasting to {len(users)} users...")
    for uid in users:
        try: await context.bot.send_message(chat_id=uid, text=msg); ok += 1
        except Exception: fail += 1
    await update.message.reply_text(f"📢 Broadcast Complete! Sent: {ok}, Failed: {fail}"); return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("🔹 Action has been cancelled.", reply_markup=get_reply_keyboard(update.effective_user.id)); return ConversationHandler.END

# --- MAIN FUNCTION: BOT SETUP ---
def main() -> None:
    app = Application.builder().token(TOKEN).build()
    main_menu_filter = filters.Regex(r'^(My Account 📊|Refer & Earn 🎁|Buy Credits 💰|Help ❓|Member Status 👥|Add Credit 👤|Broadcast 📢)$')
    add_credit_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^Add Credit 👤$'), add_credit_start)],
        states={GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_id_handler)], GET_CREDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_credit_amount_handler)],},
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start), MessageHandler(main_menu_filter, start)], conversation_timeout=120)
    broadcast_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^Broadcast 📢$'), broadcast_start)],
        states={BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]},
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start), MessageHandler(main_menu_filter, start)], conversation_timeout=300)
    app.add_handler(add_credit_handler)
    app.add_handler(broadcast_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r'^My Account 📊$'), my_account_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Refer & Earn 🎁$'), refer_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Buy Credits 💰$'), buy_credits_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Help ❓$'), help_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Member Status 👥$'), member_status_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_number_info))
    print("Zero is online and fully functional.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
