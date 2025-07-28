# -*- coding: utf-8 -*-

import requests
import json
import io
from functools import wraps
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- CORE BOT CONFIGURATION ---
TOKEN = "8499790219:AAFBBCFOswo2b9Aj8y7HT1HiKB2P5od8fHQ"  # Your bot token here
API_URL = "https://numinfoapi.vercel.app/api/num?number=" # API for number lookups
CHANNEL_USERNAME = "@ToxicBack2025"  # Your required channel username
ADMIN_IDS = [7392785352]  # Your Telegram User ID for admin privileges
SUPPORT_ADMIN = "@CDMAXX" # Username for support contact

# --- DATABASE (IN-MEMORY DEMO) ---
# IMPORTANT: This data is lost when the bot restarts.
# For production, use a persistent database like SQLite.
user_data = {}
INITIAL_CREDITS = 2
REFERRAL_CREDIT = 1

# --- CONVERSATION HANDLER STATES ---
# These are used to track the steps in a multi-step command
BROADCAST_MESSAGE = 0
GET_USER_ID, GET_CREDIT_AMOUNT = 1, 2

# --- DECORATOR: FORCE CHANNEL JOIN ---
def force_join(func):
    """Decorator to ensure a user is in the channel before using a command."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user: return
        user_id = update.effective_user.id
        # Admins are exempt from this check
        if user_id in ADMIN_IDS:
            return await func(update, context, *args, **kwargs)
        try:
            member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                await update.message.reply_text(
                    f"❗️ **Access Denied**\n\nTo use this bot, you must join our official channel.\nPlease join 👉 {CHANNEL_USERNAME} and then press /start.",
                    parse_mode='HTML'
                )
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
    keyboard = [
        [KeyboardButton("Refer & Earn 🎁"), KeyboardButton("Buy Credits 💰")],
        [KeyboardButton("My Account 📊"), KeyboardButton("Help ❓")]
    ]
    # Add an extra row of buttons for admins
    if user_id in ADMIN_IDS:
        admin_keyboard = [
            [KeyboardButton("Add Credit 👤"), KeyboardButton("Broadcast 📢")],
            [KeyboardButton("Member Status 👥")]
        ]
        keyboard.extend(admin_keyboard)
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- CORE COMMANDS & BUTTON HANDLERS ---
@force_join
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command, registers new users, and processes referrals."""
    user = update.effective_user
    user_id = user.id
    
    # This block runs only ONCE for a brand new user.
    if user_id not in user_data:
        # 1. Process referral if applicable
        try:
            if context.args:
                referrer_id = int(context.args[0])
                if referrer_id in user_data and referrer_id != user_id:
                    user_data[referrer_id]['credits'] += REFERRAL_CREDIT
                    new_balance = user_data[referrer_id]['credits']
                    notification_text = (
                        f"🎉 **1 Referral Received!**\n\n"
                        f"A new user joined using your link. +{REFERRAL_CREDIT} credit has been added.\n\n"
                        f"Your new balance is now **{new_balance} credits**."
                    )
                    await context.bot.send_message(chat_id=referrer_id, text=notification_text, parse_mode='HTML')
        except Exception as e:
            print(f"Error processing referral: {e}")

        # 2. Notify admins about the new member
        notification_to_admin = f"🎉 New Member Alert!\n\nName: {user.first_name}\nProfile: [{user_id}](tg://user?id={user_id})"
        if user.username: notification_to_admin += f"\nUsername: @{user.username}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=notification_to_admin, parse_mode='Markdown', disable_web_page_preview=True)
            except Exception as e:
                print(f"Failed to send new member notification to admin {admin_id}: {e}")

        # 3. Create the account for the new user
        user_data[user_id] = {'credits': INITIAL_CREDITS, 'searches': 0, 'join_date': datetime.now().strftime("%Y-%m-%d"), 'first_name': user.first_name, 'username': user.username}
        welcome_text = f"🎉 Welcome aboard, {user.first_name}!\n\nAs a new member, you've received **{INITIAL_CREDITS} free credits**."
        await update.message.reply_text(welcome_text, parse_mode='HTML')

    # 4. For all users (new and old), show the main account status screen
    reply_markup = get_reply_keyboard(user_id)
    await my_account_button(update, context, custom_reply_markup=reply_markup)


@force_join
async def get_number_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """The main function to look up a phone number."""
    user_id = update.effective_user.id
    number = update.message.text.strip()
    if user_id not in user_data: await start(update, context); return
    if user_data[user_id].get('credits', 0) < 1:
        await update.message.reply_text("You have insufficient credits. Use the 'Buy Credits 💰' button.")
        return
    if not number.isdigit():
        await update.message.reply_text('Invalid format. Please send a valid number without spaces or symbols.')
        return
    processing_message = await update.message.reply_text('🔎 Accessing network... This will consume 1 credit.')
    try:
        response = requests.get(f"{API_URL}{number}", timeout=10)
        response.raise_for_status()
        user_data[user_id]['credits'] -= 1
        user_data[user_id]['searches'] += 1
        data = response.json()
        formatted_response = json.dumps(data, indent=2)
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text=f"<code>{formatted_response}</code>\n\nCredits remaining: {user_data[user_id]['credits']}", parse_mode='HTML')
    except requests.exceptions.HTTPError:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="❌ **Invalid Number or No Data Found.**\nPlease enter a correct and valid number.")
    except requests.exceptions.RequestException:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="🌐 **Network Error.** Could not connect to the service. Please try again later.")
    except Exception as e:
        print(f"Unexpected error in get_number_info: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="⚙️ **An unexpected error occurred.** Please try again.")

async def my_account_button(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_reply_markup=None) -> None:
    """Displays the user's account status."""
    user, user_id = update.effective_user, update.effective_user.id
    if user_id not in user_data:
        await update.message.reply_text("Could not find your data. Please press /start to register.")
        return
    reply_markup = custom_reply_markup or get_reply_keyboard(user_id)
    user_info = user_data[user_id]
    account_status_message = (f"🎯 **Welcome, {user.first_name}!** ➤ Toxic Official 🕊️\n\n" f"🔎 Advanced OSINT Multi-Search Bot\n\n" f"➖➖➖➖➖➖➖➖➖➖➖➖\n" f"💳 **Your Credits:** {user_info['credits']}\n" f"📊 **Total Searches:** {user_info['searches']}\n" f"🗓️ **Member Since:** {user_info['join_date']}")
    await update.message.reply_text(account_status_message, reply_markup=reply_markup, parse_mode='HTML')

async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the help message."""
    help_text = ( "❓ **Help & Support Center**\n\n" "🔍 **How to Use:**\n" "• Send a phone number to search.\n" "• Each search costs 1 credit.\n\n" "🎁 **Referral Program:**\n" f"• Share your link to get {REFERRAL_CREDIT} credit per referral.\n\n" f"👤 **Support:** {SUPPORT_ADMIN}" )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def refer_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generates and sends the user's referral link."""
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
    await update.message.reply_text(f"**Invite friends and earn credits!** 🎁\n\n" f"You get {REFERRAL_CREDIT} credit for every new user who starts the bot through your link.\n\n" f"Your link: `{referral_link}`", parse_mode='Markdown')

async def buy_credits_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the credit purchase information."""
    buy_text = ( "💰 **Buy Credits - Price List**\n" "━━━━━━━━━━━━━━━━━━━━━━━━\n\n" "💎 **STARTER PACK** - 25 Credits (₹49)\n" "🔥 **BASIC PACK** - 100 Credits (₹149)\n" "⭐ **PRO PACK** - 500 Credits (₹499)\n\n" "━━━━━━━━━━━━━━━━━━━━━━━━\n" f"💬 To purchase credits, contact the admin: {SUPPORT_ADMIN}" )
    await update.message.reply_text(buy_text, parse_mode='HTML')


# --- ADMIN-ONLY FEATURES ---
async def member_status_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows admins a list of all bot members."""
    if update.effective_user.id not in ADMIN_IDS: return
    all_users_data, total_members = user_data.items(), len(user_data.items())
    bot_info = await context.bot.get_me()
    header = (f"📊 **Bot Member Status**\n" f"Bot: [@{bot_info.username}](https://t.me/{bot_info.username})\n" f"Total Members: {total_members}\n" "➖➖➖➖➖➖➖➖➖➖➖➖\n")
    if total_members == 0: await update.message.reply_text(header + "No members have started the bot yet.", parse_mode='Markdown', disable_web_page_preview=True); return
    def format_user_line(user_id, data):
        username_str = f"(@{data['username']})" if data.get('username') else ""
        return f"• {data.get('first_name', 'Unknown')} {username_str} - [{user_id}](tg://user?id={user_id})"
    if total_members <= 50:
        message_lines = [header] + [format_user_line(uid, udata) for uid, udata in all_users_data]
        await update.message.reply_text("\n".join(message_lines), parse_mode='Markdown', disable_web_page_preview=True)
    else:
        file_content = "\n".join([f"{uid} - {udata.get('first_name', 'N/A')} (@{udata.get('username', 'N/A')}) - tg://user?id={uid}" for uid, udata in all_users_data])
        output_file = io.BytesIO(file_content.encode('utf-8')); output_file.name = 'member_list.txt'
        caption = header + "\nThe member list was too long to display and has been sent as a file."
        await context.bot.send_document(chat_id=update.effective_chat.id, document=output_file, caption=caption, parse_mode='Markdown', disable_web_page_preview=True)

# --- CONVERSATION HANDLERS (for multi-step admin commands) ---
async def add_credit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the 'add credit' conversation."""
    await update.message.reply_text("👤 Please send the User ID of the recipient.\n\nType /cancel to abort.")
    return GET_USER_ID

async def get_user_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the User ID and asks for the amount."""
    try:
        user_id = int(update.message.text)
        if user_id not in user_data:
            await update.message.reply_text("⚠️ User not found in database. Please try again or type /cancel.")
            return GET_USER_ID
        context.user_data['target_user_id'] = user_id
        await update.message.reply_text(f"✅ User `{user_id}` found.\n\nNow, please send the amount of credits to add.", parse_mode='Markdown')
        return GET_CREDIT_AMOUNT
    except ValueError:
        await update.message.reply_text("❗️Invalid ID. Please send numbers only or type /cancel.")
        return GET_USER_ID

async def get_credit_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the amount, adds credit, and ends the conversation."""
    try:
        amount = int(update.message.text)
        target_user_id = context.user_data.pop('target_user_id')
        user_data[target_user_id]['credits'] += amount
        await update.message.reply_text(f"✅ **Success!**\nAdded `{amount}` credits to user `{target_user_id}`.", parse_mode='Markdown')
        await context.bot.send_message(chat_id=target_user_id, text=f"🎉 An administrator has added **{amount} credits** to your account!")
        return ConversationHandler.END
    except (ValueError, KeyError):
        await update.message.reply_text("❗️Invalid amount. Please send numbers only or type /cancel.")
        return GET_CREDIT_AMOUNT

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the 'broadcast' conversation."""
    await update.message.reply_text("📢 Please send the message you want to broadcast to all users.\n\nType /cancel to abort.")
    return BROADCAST_MESSAGE

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the broadcast message, sends it, and ends the conversation."""
    msg, users, ok, fail = update.message.text, list(user_data.keys()), 0, 0
    await update.message.reply_text(f"⏳ Broadcasting your message to {len(users)} users...")
    for uid in users:
        try: await context.bot.send_message(chat_id=uid, text=msg); ok += 1
        except Exception: fail += 1
    await update.message.reply_text(f"📢 **Broadcast Complete!**\n✅ Sent successfully: {ok}\n❌ Failed to send: {fail}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """A universal command to cancel any active conversation."""
    context.user_data.clear()
    await update.message.reply_text("🔹 Action has been cancelled.", reply_markup=get_reply_keyboard(update.effective_user.id))
    return ConversationHandler.END


# --- MAIN FUNCTION: BOT SETUP ---
def main() -> None:
    """Initializes the bot and sets up all handlers."""
    app = Application.builder().token(TOKEN).build()
    
    # --- CONVERSATION HANDLERS SETUP (WITH THE FIX) ---
    # This filter will match any of the main menu buttons, to be used as a smart fallback.
    main_menu_filter = filters.Regex(r'^(My Account 📊|Refer & Earn 🎁|Buy Credits 💰|Help ❓|Member Status 👥|Add Credit 👤|Broadcast 📢)$')

    add_credit_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^Add Credit 👤$'), add_credit_start)],
        states={
            GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_id_handler)],
            GET_CREDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_credit_amount_handler)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            MessageHandler(main_menu_filter, start) # If any main button is pressed, cancel and restart
        ],
        conversation_timeout=120  # 2 minutes
    )
    broadcast_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^Broadcast 📢$'), broadcast_start)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            MessageHandler(main_menu_filter, start) # If any main button is pressed, cancel and restart
        ],
        conversation_timeout=300 # 5 minutes
    )
    
    # Add conversation handlers first, as they are more specific.
    app.add_handler(add_credit_handler)
    app.add_handler(broadcast_handler)
    
    # Add regular command and button handlers.
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r'^My Account 📊$'), my_account_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Refer & Earn 🎁$'), refer_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Buy Credits 💰$'), buy_credits_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Help ❓$'), help_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Member Status 👥$'), member_status_button))
    
    # This handler must be last, to catch any text that isn't a known command or button.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_number_info))

    print("Zero is online and fully functional.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
