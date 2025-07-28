# -*- coding: utf-8 -*-

import requests
import json
import io
from functools import wraps
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- बॉट की मुख्य सेटिंग्स ---
TOKEN = "8499790219:AAFBBCFOswo2b9Aj8y7HT1HiKB2P5od8fHQ"  # अपना बॉट टोकन यहाँ डालें
API_URL = "https://numinfoapi.vercel.app/api/num?number=" # नंबर जानकारी के लिए API
CHANNEL_USERNAME = "@ToxicBack2025"  # आपका चैनल का यूजरनेम
ADMIN_IDS = [7392785352]  # आपकी टेलीग्राम यूजर ID (एडमिन)
SUPPORT_ADMIN = "@CDMAXX" # सपोर्ट के लिए एडमिन का यूजरनेम

# --- डेटाबेस (अभी यह सिर्फ डेमो के लिए है) ---
# महत्वपूर्ण: बॉट रीस्टार्ट होने पर यह डेटा डिलीट हो जाएगा।
# असली इस्तेमाल के लिए SQLite या किसी और डेटाबेस का प्रयोग करें।
user_data = {}
INITIAL_CREDITS = 2
REFERRAL_CREDIT = 1

# --- कन्वर्सेशन के लिए स्टेट्स ---
BROADCAST_MESSAGE = 0
GET_USER_ID, GET_CREDIT_AMOUNT = 1, 2

# --- डेकोरेटर: चैनल जॉइन करवाना ---
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
                    f"❗️ **Access Denied**\n\nइस बॉट का उपयोग करने के लिए, आपको हमारा चैनल जॉइन करना होगा।\nकृपया यहाँ जॉइन करें 👉 {CHANNEL_USERNAME} और फिर /start दबाएँ।",
                    parse_mode='HTML'
                )
                return
        except Exception as e:
            print(f"चैनल मेम्बरशिप चेक करने में त्रुटि: {e}")
            await update.message.reply_text("⛔️ चैनल मेम्बरशिप की पुष्टि करने में एक त्रुटि हुई। कृपया सपोर्ट से संपर्क करें।")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- कीबोर्ड बनाने का फंक्शन ---
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
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


# --- मुख्य कमांड्स ---
@force_join
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    
    # नए यूज़र और रेफेरल की प्रक्रिया
    if user_id not in user_data:
        # रेफेरल को हैंडल करना
        try:
            if context.args:
                referrer_id = int(context.args[0])
                if referrer_id in user_data and referrer_id != user_id:
                    user_data[referrer_id]['credits'] += REFERRAL_CREDIT
                    new_balance = user_data[referrer_id]['credits']
                    notification_text = (
                        f"🎉 **1 Referral Received!**\n\n"
                        f"एक नए यूज़र ने आपके लिंक से जॉइन किया है। +{REFERRAL_CREDIT} क्रेडिट आपके अकाउंट में जोड़ दिया गया है।\n\n"
                        f"आपका नया बैलेंस अब **{new_balance} क्रेडिट** है।"
                    )
                    await context.bot.send_message(chat_id=referrer_id, text=notification_text, parse_mode='HTML')
        except Exception as e:
            print(f"रेफेरल प्रोसेस करने में त्रुटि: {e}")

        # एडमिन को नए सदस्य की सूचना देना
        new_member_notification_text = f"🎉 **New Member Alert!** 🎉\n\n👤 **Name:** {user.first_name}\n🔗 **Profile:** [{user_id}](tg://user?id={user_id})"
        if user.username: new_member_notification_text += f"\n**Username:** @{user.username}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=new_member_notification_text, parse_mode='Markdown', disable_web_page_preview=True)
            except Exception as e:
                print(f"एडमिन को सूचना भेजने में विफल: {e}")

        # नए यूज़र का डेटा सेव करना
        user_data[user_id] = {'credits': INITIAL_CREDITS, 'searches': 0, 'join_date': datetime.now().strftime("%Y-%m-%d"), 'first_name': user.first_name, 'username': user.username}
        welcome_text = f"🎉 आपका स्वागत है, {user.first_name}!\n\nएक नए सदस्य के रूप में, आपको **{INITIAL_CREDITS} फ्री क्रेडिट** मिले हैं।"
        await update.message.reply_text(welcome_text, parse_mode='HTML')

    # सभी यूज़र्स को मेन मेनू दिखाना
    reply_markup = get_reply_keyboard(user_id)
    await my_account_button(update, context, custom_reply_markup=reply_markup)


# --- नंबर की जानकारी निकालना ---
@force_join
async def get_number_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    number = update.message.text.strip()
    if user_id not in user_data: await start(update, context); return
    if user_data[user_id].get('credits', 0) < 1:
        await update.message.reply_text("आपके पास पर्याप्त क्रेडिट नहीं हैं। 'Buy Credits 💰' बटन का उपयोग करें।")
        return
    if not number.isdigit():
        await update.message.reply_text('अमान्य प्रारूप। कृपया बिना स्पेस या सिंबल के एक मान्य नंबर भेजें।')
        return
    processing_message = await update.message.reply_text('🔎 नेटवर्क एक्सेस हो रहा है... इसमें 1 क्रेडिट लगेगा।')
    try:
        response = requests.get(f"{API_URL}{number}", timeout=10)
        response.raise_for_status()
        user_data[user_id]['credits'] -= 1
        user_data[user_id]['searches'] += 1
        data = response.json()
        formatted_response = json.dumps(data, indent=2)
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text=f"<code>{formatted_response}</code>\n\nबचे हुए क्रेडिट: {user_data[user_id]['credits']}", parse_mode='HTML')
    except requests.exceptions.HTTPError:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="❌ **अमान्य नंबर या कोई डेटा नहीं मिला।**\nकृपया एक सही और मान्य नंबर दर्ज करें।")
    except requests.exceptions.RequestException:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="🌐 **नेटवर्क त्रुटि।** सेवा से कनेक्ट नहीं हो सका। कृपया बाद में पुनः प्रयास करें।")
    except Exception as e:
        print(f"अप्रत्याशित त्रुटि: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="⚙️ **एक अप्रत्याशित त्रुटि हुई।** कृपया पुनः प्रयास करें।")


# --- बटन के फंक्शन ---
async def my_account_button(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_reply_markup=None) -> None:
    user, user_id = update.effective_user, update.effective_user.id
    if user_id not in user_data:
        await update.message.reply_text("आपका डेटा नहीं मिला। कृपया /start दबाकर रजिस्टर करें।")
        return
    reply_markup = custom_reply_markup or get_reply_keyboard(user_id)
    user_info = user_data[user_id]
    account_status_message = (
        f"🎯 **Welcome, {user.first_name}!** ➤ Toxic Official 🕊️\n\n"
        "🔎 एडवांस्ड OSINT मल्टी-सर्च बॉट\n\n"
        "➖➖➖➖➖➖➖➖➖➖➖➖\n"
        f"💳 **आपके क्रेडिट:** {user_info['credits']}\n"
        f"📊 **कुल खोजें:** {user_info['searches']}\n"
        f"🗓️ **सदस्यता तिथि:** {user_info['join_date']}"
    )
    await update.message.reply_text(account_status_message, reply_markup=reply_markup, parse_mode='HTML')

async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = ( "❓ **सहायता केंद्र**\n\n" "🔍 **कैसे उपयोग करें:**\n" "• खोजने के लिए एक फ़ोन नंबर भेजें।\n" "• प्रत्येक खोज में 1 क्रेडिट लगता है।\n\n" "🎁 **रेफरल प्रोग्राम:**\n" f"• प्रत्येक रेफरल के लिए {REFERRAL_CREDIT} क्रेडिट प्राप्त करने के लिए अपना लिंक साझा करें।\n\n" f"👤 **सपोर्ट:** {SUPPORT_ADMIN}" )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def refer_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
    await update.message.reply_text(f"**दोस्तों को आमंत्रित करें और क्रेडिट कमाएं!** 🎁\n\n" f"इस लिंक का उपयोग करके जुड़ने वाले प्रत्येक यूज़र के लिए आपको {REFERRAL_CREDIT} क्रेडिट मिलेगा।\n\n" f"आपका लिंक: `{referral_link}`", parse_mode='Markdown')

async def buy_credits_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    buy_text = ( "💰 **क्रेडिट खरीदें - मूल्य सूची**\n" "━━━━━━━━━━━━━━━━━━━━━━━━\n\n" "💎 **STARTER PACK** - 25 Credits (₹49)\n" "🔥 **BASIC PACK** - 100 Credits (₹149)\n" "⭐ **PRO PACK** - 500 Credits (₹499)\n\n" "━━━━━━━━━━━━━━━━━━━━━━━━\n" f"💬 खरीदने के लिए, एडमिन से संपर्क करें: {SUPPORT_ADMIN}" )
    await update.message.reply_text(buy_text, parse_mode='HTML')

# --- एडमिन के फीचर्स ---
async def member_status_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in ADMIN_IDS: return
    all_users_data = user_data.items()
    total_members = len(all_users_data)
    bot_info = await context.bot.get_me()
    header = (f"📊 **बॉट सदस्य स्थिति**\n" f"बॉट: [@{bot_info.username}](https://t.me/{bot_info.username})\n" f"कुल सदस्य: {total_members}\n" "➖➖➖➖➖➖➖➖➖➖➖➖\n")
    if total_members == 0: await update.message.reply_text(header + "अभी तक कोई सदस्य नहीं है।", parse_mode='Markdown', disable_web_page_preview=True); return
    def format_user_line(user_id, data):
        username_str = f"(@{data['username']})" if data.get('username') else ""
        return f"• {data.get('first_name', 'Unknown')} {username_str} - [{user_id}](tg://user?id={user_id})"
    if total_members <= 50:
        message_lines = [header] + [format_user_line(uid, udata) for uid, udata in all_users_data]
        await update.message.reply_text("\n".join(message_lines), parse_mode='Markdown', disable_web_page_preview=True)
    else:
        file_content = "\n".join([f"{uid} - {udata.get('first_name', 'N/A')} (@{udata.get('username', 'N/A')}) - tg://user?id={uid}" for uid, udata in all_users_data])
        output_file = io.BytesIO(file_content.encode('utf-8')); output_file.name = 'member_list.txt'
        caption = header + "\nसदस्य सूची बहुत लंबी होने के कारण फ़ाइल के रूप में भेजी गई है।"
        await context.bot.send_document(chat_id=update.effective_chat.id, document=output_file, caption=caption, parse_mode='Markdown', disable_web_page_preview=True)

async def add_credit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("👤 कृपया उस यूज़र की **User ID** भेजें जिसे क्रेडिट देना है।\n\nरद्द करने के लिए /cancel टाइप करें।")
    return GET_USER_ID

async def get_user_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = int(update.message.text)
        if user_id not in user_data:
            await update.message.reply_text("⚠️ यूज़र नहीं मिला। कृपया दोबारा प्रयास करें या /cancel करें।")
            return GET_USER_ID
        context.user_data['target_user_id'] = user_id
        await update.message.reply_text(f"✅ यूज़र `{user_id}` मिल गया।\n\nअब क्रेडिट की **मात्रा** भेजें।", parse_mode='Markdown')
        return GET_CREDIT_AMOUNT
    except ValueError:
        await update.message.reply_text("❗️अमान्य ID। कृपया केवल नंबर भेजें या /cancel करें।")
        return GET_USER_ID

async def get_credit_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = int(update.message.text)
        target_user_id = context.user_data.pop('target_user_id')
        user_data[target_user_id]['credits'] += amount
        await update.message.reply_text(f"✅ **सफलता!**\n`{amount}` क्रेडिट यूज़र `{target_user_id}` को दे दिए गए हैं।", parse_mode='Markdown')
        await context.bot.send_message(chat_id=target_user_id, text=f"🎉 एडमिन ने आपके अकाउंट में **{amount} क्रेडिट** जोड़े हैं!")
        return ConversationHandler.END
    except (ValueError, KeyError):
        await update.message.reply_text("❗️अमान्य मात्रा। कृपया केवल नंबर भेजें या /cancel करें।")
        return GET_CREDIT_AMOUNT

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📢 कृपया वह संदेश भेजें जिसे आप सभी यूज़र्स को भेजना चाहते हैं।\n\nरद्द करने के लिए /cancel टाइप करें।")
    return BROADCAST_MESSAGE

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg, users, ok, fail = update.message.text, list(user_data.keys()), 0, 0
    await update.message.reply_text(f"⏳ {len(users)} यूज़र्स को संदेश भेजा जा रहा है...")
    for uid in users:
        try: await context.bot.send_message(chat_id=uid, text=msg); ok += 1
        except Exception: fail += 1
    await update.message.reply_text(f"📢 **ब्रॉडकास्ट पूरा हुआ!**\n✅ सफलतापूर्वक भेजा: {ok}\n❌ भेजने में विफल: {fail}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("पिछली कार्रवाई रद्द कर दी गई है।")
    return ConversationHandler.END

# --- मुख्य फंक्शन (जहाँ बॉट शुरू होता है) ---
def main() -> None:
    app = Application.builder().token(TOKEN).build()
    
    # --- कन्वर्सेशन को संभालने के लिए नया और बेहतर तरीका ---
    # यह फ़िल्टर मेन मेनू के सभी बटनों से मेल खाता है
    main_menu_filter = filters.Regex(r'^(Refer & Earn 🎁|Buy Credits 💰|My Account 📊|Help ❓|Member Status 👥|Add Credit 👤|Broadcast 📢)$')

    conv_handler_add_credit = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^Add Credit 👤$'), add_credit_start)],
        states={
            GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_id_handler)],
            GET_CREDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_credit_amount_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start), MessageHandler(main_menu_filter, start)],
        conversation_timeout=120  # 2 मिनट बाद अपने आप कैंसिल हो जाएगा
    )
    conv_handler_broadcast = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^Broadcast 📢$'), broadcast_start)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start), MessageHandler(main_menu_filter, start)],
        conversation_timeout=120
    )
    
    app.add_handler(conv_handler_add_credit)
    app.add_handler(conv_handler_broadcast)
    
    # कमांड और बटन के हैंडलर
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r'^My Account 📊$'), my_account_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Refer & Earn 🎁$'), refer_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Buy Credits 💰$'), buy_credits_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Help ❓$'), help_button))
    app.add_handler(MessageHandler(filters.Regex(r'^Member Status 👥$'), member_status_button))
    
    # यह हैंडलर सबसे आखिर में होना चाहिए
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_number_info))

    print("Zero is online and fully functional.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
