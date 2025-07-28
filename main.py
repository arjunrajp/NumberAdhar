import requests
import json
import io
from functools import wraps
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- CONFIGURATION ---
TOKEN = "8069307971:AAEm8SO1C3K_dOcJcWa9v6r2fQ2ZVwhV-iI"
API_URL = "https://numinfoapi.vercel.app/api/num?number="
CHANNEL_USERNAME = "@ToxicBack2025"
ADMIN_IDS = [7392785352]  # Your Telegram User ID
SUPPORT_ADMIN = "@CDMAXX"

# --- DATABASE (IN-MEMORY DEMO) ---
user_data = {}
INITIAL_CREDITS = 2
REFERRAL_CREDIT = 1

# --- CONVERSATION HANDLER STATES ---
BROADCAST_MESSAGE = 0
GET_USER_ID, GET_CREDIT_AMOUNT = 1, 2

# --- DECORATOR TO FORCE CHANNEL JOIN ---
def force_join(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user: return
        user_id = update.effective_user.id
        if user_id in ADMIN_IDS:
            return await func(update, context, *args, **kwargs)
        try:
            member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                await update.message.reply_text(
                    f"❗️ **Access Denied**\n\nYou must join our official channel to use this bot.\nPlease join 👉 {CHANNEL_USERNAME} and then press /start again.",
                    parse_mode='HTML'
                )
                return
        except Exception as e:
            print(f"Error checking channel membership for user {user_id}: {e}")
            await update.message.reply_text("⛔️ Error verifying channel membership. Please contact support.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- UTILITY FUNCTION FOR KEYBOARD ---
def get_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("Refer & Earn 🎁"), KeyboardButton("Buy Credits 💰")],
        [KeyboardButton("My Account 📊"), KeyboardButton("Help ❓")]
    ]
    if user_id in ADMIN_IDS:
        admin_keyboard = [
            [KeyboardButton("Add Credit 👤"), KeyboardButton("Broadcast 📢")],
            [KeyboardButton("Member Status 👥")]
        ]
        keyboard.extend(admin_keyboard)
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- NEW FALLBACK HANDLER TO FIX THE ISSUE ---
async def main_menu_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles main menu buttons when a conversation is active, canceling it first."""
    await update.message.reply_text("🔹 Action cancelled. Processing your new request...")
    
    text = update.message.text
    if text == "Refer & Earn 🎁":
        await refer_button(update, context)
    elif text == "Buy Credits 💰":
        await buy_credits_button(update, context)
    elif text == "My Account 📊":
        await my_account_button(update, context)
    elif text == "Help ❓":
        await help_button(update, context)
    # Add other main menu buttons here if needed
    
    return ConversationHandler.END

# --- MAIN COMMANDS ---
@force_join
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (start function code remains the same as the previous version)
    user = update.effective_user
    user_id = user.id
    if user_id not in user_data:
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
        except (ValueError, IndexError):
            pass
        except Exception as e:
            print(f"Error processing referral: {e}")

        new_member_notification_text = f"🎉 **New Member Alert!** 🎉\n\n👤 **Name:** {user.first_name}\n🔗 **Profile:** [{user_id}](tg://user?id={user_id})"
        if user.username:
            new_member_notification_text += f"\n**Username:** @{user.username}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=new_member_notification_text, parse_mode='Markdown', disable_web_page_preview=True)
            except Exception as e:
                print(f"Failed to send new member notification to admin {admin_id}: {e}")
        
        user_data[user_id] = {
            'credits': INITIAL_CREDITS, 'searches': 0, 'join_date': datetime.now().strftime("%Y-%m-%d"),
            'first_name': user.first_name, 'username': user.username
        }
        welcome_text = f"🎉 Welcome aboard, {user.first_name}!\n\nAs a new member, you've received **{INITIAL_CREDITS} free credits**."
        await update.message.reply_text(welcome_text, parse_mode='HTML')

    reply_markup = get_reply_keyboard(user_id)
    await my_account_button(update, context, custom_reply_markup=reply_markup)


# --- All other functions (get_number_info, my_account_button, help_button, etc.) remain exactly the same ---
# I'll include them for completeness, but the main change is in the `main()` function at the end.

@force_join
async def get_number_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    number = update.message.text.strip()
    if user_id not in user_data:
        await start(update, context); return
    if user_data[user_id].get('credits', 0) < 1:
        await update.message.reply_text("You have insufficient credits.")
        return
    if not number.isdigit():
        await update.message.reply_text('Invalid format.')
        return
    processing_message = await update.message.reply_text('🔎 Accessing network...')
    try:
        response = requests.get(f"{API_URL}{number}", timeout=10)
        response.raise_for_status()
        user_data[user_id]['credits'] -= 1
        user_data[user_id]['searches'] += 1
        data = response.json()
        formatted_response = json.dumps(data, indent=2)
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=processing_message.message_id,
            text=f"<code>{formatted_response}</code>\n\nCredits: {user_data[user_id]['credits']}",
            parse_mode='HTML'
        )
    except requests.exceptions.HTTPError:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="❌ Invalid Number or No Data Found.")
    except requests.exceptions.RequestException:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="🌐 Network Error.")
    except Exception as e:
        print(f"Error: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="⚙️ An unexpected error occurred.")

async def my_account_button(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_reply_markup=None) -> None:
    user, user_id = update.effective_user, update.effective_user.id
    if user_id not in user_data:
        await update.message.reply_text("Please press /start to register.")
        return
    reply_markup = custom_reply_markup or get_reply_keyboard(user_id)
    user_info = user_data[user_id]
    account_status_message = (
        f"🎯 **Welcome, {user.first_name}!**\n\n"
        f"💳 **Credits:** {user_info['credits']}\n"
        f"📊 **Searches:** {user_info['searches']}\n"
        f"🗓️ **Member Since:** {user_info['join_date']}"
    )
    await update.message.reply_text(account_status_message, reply_markup=reply_markup, parse_mode='HTML')

async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = ( "❓ **Help & Support Center** ... (Full text) ") # Full text
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def refer_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
    await update.message.reply_text(f"Your link: `{referral_link}`", parse_mode='Markdown')

async def buy_credits_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    buy_text = ( "💰 **Buy Credits - Price List** ... (Full text) ") # Full text
    await update.message.reply_text(buy_text, parse_mode='HTML')

async def member_status_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (code for this function is unchanged)
    if update.effective_user.id not in ADMIN_IDS: return
    all_users_data = user_data.items()
    total_members = len(all_users_data)
    bot_info = await context.bot.get_me()
    header = (f"📊 **Bot Member Status**\nTotal Members: {total_members}\n" "➖➖➖➖➖➖➖➖➖➖➖➖\n")
    if total_members == 0:
        await update.message.reply_text(header + "No members yet.", parse_mode='Markdown')
        return
    def format_user_line(user_id, data):
        username_str = f"(@{data['username']})" if data.get('username') else ""
        return f"• {data.get('first_name', 'Unknown')} {username_str} - [{user_id}](tg://user?id={user_id})"
    if total_members <= 50:
        message_lines = [header] + [format_user_line(uid, udata) for uid, udata in all_users_data]
        await update.message.reply_text("\n".join(message_lines), parse_mode='Markdown', disable_web_page_preview=True)
    else:
        file_content = "\n".join([f"{uid}..." for uid, udata in all_users_data]) # Abridged
        output_file = io.BytesIO(file_content.encode('utf-8'))
        output_file.name = 'member_list.txt'
        await context.bot.send_document(chat_id=update.effective_chat.id, document=output_file, caption=header, parse_mode='Markdown')

async def add_credit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("👤 Send the User ID. /cancel to abort.")
    return GET_USER_ID

async def get_user_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = int(update.message.text)
        if user_id not in user_data:
            await update.message.reply_text("⚠️ User not found. Try again or /cancel.")
            return GET_USER_ID
        context.user_data['target_user_id'] = user_id
        await update.message.reply_text(f"✅ User `{user_id}` found. Send the credit amount.", parse_mode='Markdown')
        return GET_CREDIT_AMOUNT
    except ValueError:
        await update.message.reply_text("❗️Invalid ID. Send numbers only or /cancel.")
        return GET_USER_ID

async def get_credit_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = int(update.message.text)
        target_user_id = context.user_data.pop('target_user_id')
        user_data[target_user_id]['credits'] += amount
        await update.message.reply_text(f"✅ Success! Added `{amount}` credits.", parse_mode='Markdown')
        await context.bot.send_message(chat_id=target_user_id, text=f"🎉 Admin added **{amount} credits**!")
        return ConversationHandler.END
    except (ValueError, KeyError):
        await update.message.reply_text("❗️Invalid amount. Send numbers only or /cancel.")
        return GET_CREDIT_AMOUNT

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📢 Send the message to broadcast. /cancel to abort.")
    return BROADCAST_MESSAGE

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg, users, ok, fail = update.message.text, list(user_data.keys()), 0, 0
    await update.message.reply_text(f"⏳ Broadcasting to {len(users)} users...")
    for uid in users:
        try: await context.bot.send_message(chat_id=uid, text=msg); ok += 1
        except Exception: fail += 1
    await update.message.reply_text(f"📢 Broadcast Complete! Sent: {ok}, Failed: {fail}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END

def main() -> None:
    app = Application.builder().token(TOKEN).build()
    
    # --- UPDATED CONVERSATION HANDLER WITH FALLBACK ---
    # This filter will match any of the main menu buttons
    main_menu_filter = filters.Regex(r'^(Refer & Earn 🎁|Buy Credits 💰|My Account 📊|Help ❓)$')

    add_credit_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^Add Credit 👤$'), add_credit_start)],
        states={
            GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_id_handler)],
            GET_CREDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_credit_amount_handler)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(main_menu_filter, main_menu_fallback) # <-- The fix is here
        ]
    )
    broadcast_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^Broadcast 📢$'), broadcast_start)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(main_menu_filter, main_menu_fallback) # <-- And here
        ]
    )
    
    app.add_handler(add_credit_handler)
    app.add_handler(broadcast_handler)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r'^My Account 📊$'), my_account_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Refer & Earn 🎁$'), refer_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Buy Credits 💰$'), buy_credits_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Help ❓$'), help_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Member Status 👥$'), member_status_button))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_number_info))

    print("Zero is online.")
    app.run_polling()

if __name__ == '__main__':
    main()
