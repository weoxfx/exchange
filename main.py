import os
import json
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import telebot
from telebot import types

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID       = 6186511950
ADMIN_NUMBER   = "7012849145"
XEO_WALLET_URL = "https://xeowallet.vercel.app"

EXCHANGE_TYPES = ["Fxl", "Rdx", "Vsv", "Ultra Pay", "Saathi"]

# ─── DATA ─────────────────────────────────────────────────────────────────────
DATA_FILE = "xeo_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "total_exchanges": 0,
        "successful_exchanges": 0,
        "declined_exchanges": 0,
        "pending_exchanges": {},
        "requests": []
    }

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=2)

# ─── BOT ──────────────────────────────────────────────────────────────────────
bot = telebot.TeleBot(BOT_TOKEN)

# In-memory user state
user_states = {}

def get_state(uid):
    return user_states.get(uid, {})

def set_state(uid, **kwargs):
    if uid not in user_states:
        user_states[uid] = {}
    user_states[uid].update(kwargs)

def clear_state(uid):
    user_states.pop(uid, None)

def user_mention(user):
    name = user.first_name or "User"
    if user.last_name:
        name += f" {user.last_name}"
    if user.username:
        return f"@{user.username} ({name})"
    return f"{name} [ID: {user.id}]"

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────
def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = EXCHANGE_TYPES + ["📋 Request", "📊 Stats"]
    kb.add(*[types.KeyboardButton(b) for b in buttons])
    return kb

def cancel_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Cancel"))
    return kb

def admin_approval_keyboard(exchange_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{exchange_id}"),
        types.InlineKeyboardButton("❌ Decline", callback_data=f"decline_{exchange_id}")
    )
    return kb

# ─── /start ───────────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    clear_state(msg.from_user.id)
    bot.send_message(
        msg.chat.id,
        "👋 *Welcome to Xeo Exchanger!*\n\n"
        "Select a fund type below to start exchanging, "
        "or use *Request* to suggest a new fund type.\n\n"
        "Use *Stats* to view exchanger info.",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

# ─── CANCEL ───────────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "❌ Cancel")
def handle_cancel(msg):
    clear_state(msg.from_user.id)
    bot.send_message(
        msg.chat.id,
        "❌ Cancelled. Back to main menu.",
        reply_markup=main_keyboard()
    )

# ─── STATS ────────────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def handle_stats(msg):
    d = load_data()
    text = (
        "📊 *Xeo Exchanger — Stats*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷 *Name:* Xeo Exchanger\n"
        f"🔔 *Updates:* @Xeo\\_Wallet\n"
        f"💬 *Support:* @XeoSupportBot\n\n"
        f"💱 *Fund Types Available:* {len(EXCHANGE_TYPES)}\n"
        f"   `{' | '.join(EXCHANGE_TYPES)}`\n\n"
        f"📦 *Total Exchanges:* {d['total_exchanges']}\n"
        f"✅ *Successful:* {d['successful_exchanges']}\n"
        f"❌ *Declined:* {d.get('declined_exchanges', 0)}\n"
        f"⏳ *Pending:* {len(d.get('pending_exchanges', {}))}"
    )
    bot.send_message(
        msg.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

# ─── REQUEST ──────────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📋 Request")
def handle_request(msg):
    set_state(msg.from_user.id, step="awaiting_request")
    bot.send_message(
        msg.chat.id,
        "📋 *Request a New Fund Type*\n\n"
        "Type the name of the fund type you'd like us to add:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )

# ─── EXCHANGE TYPE SELECTED ───────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text in EXCHANGE_TYPES)
def handle_exchange_type(msg):
    fund = msg.text
    set_state(msg.from_user.id, step="awaiting_amount", fund=fund)
    bot.send_message(
        msg.chat.id,
        f"💱 *{fund} Exchange*\n\n"
        f"💰 How much do you want to exchange?\n"
        f"_(Enter the amount)_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )

# ─── TEXT MESSAGES (State Machine) ────────────────────────────────────────────
@bot.message_handler(content_types=["text"])
def handle_text(msg):
    uid   = msg.from_user.id
    state = get_state(uid)
    step  = state.get("step")

    # ── Awaiting fund request ──
    if step == "awaiting_request":
        req_text = msg.text.strip()
        d = load_data()
        d["requests"].append({
            "user_id":  uid,
            "username": msg.from_user.username,
            "request":  req_text,
            "time":     datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        save_data(d)
        bot.send_message(
            ADMIN_ID,
            f"📋 *New Fund Request*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 From: {user_mention(msg.from_user)}\n"
            f"🆔 User ID: `{uid}`\n"
            f"📝 Request: *{req_text}*\n"
            f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            parse_mode="Markdown"
        )
        clear_state(uid)
        bot.send_message(
            msg.chat.id,
            "✅ *Request sent!*\n\n"
            "Your request has been forwarded to the admin. "
            "We'll review it and add it if possible. Thank you! 🙏",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )

    # ── Awaiting amount ──
    elif step == "awaiting_amount":
        amount = msg.text.strip()
        set_state(uid, step="awaiting_xid", amount=amount)
        bot.send_message(
            msg.chat.id,
            f"📱 *Enter your XID or Mobile Number*\n\n"
            f"Please provide your XID or the mobile number "
            f"linked to your [Xeo Wallet]({XEO_WALLET_URL}):",
            parse_mode="Markdown",
            disable_web_page_preview=False,
            reply_markup=cancel_keyboard()
        )

    # ── Awaiting XID / mobile ──
    elif step == "awaiting_xid":
        xid    = msg.text.strip()
        fund   = state.get("fund")
        amount = state.get("amount")
        set_state(uid, step="awaiting_screenshot", xid=xid)
        bot.send_message(
            msg.chat.id,
            f"📤 *Send Payment Now*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💱 Fund Type: *{fund}*\n"
            f"💰 Amount: *{amount}*\n\n"
            f"Please send the amount to this number:\n"
            f"📞 `{ADMIN_NUMBER}`\n\n"
            f"After sending, upload a *screenshot* of your payment here as proof. 📸",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )

    # ── Unknown / no state ──
    else:
        bot.send_message(
            msg.chat.id,
            "Please use the menu below to get started. 👇",
            reply_markup=main_keyboard()
        )

# ─── SCREENSHOT ───────────────────────────────────────────────────────────────
@bot.message_handler(content_types=["photo"])
def handle_screenshot(msg):
    uid   = msg.from_user.id
    state = get_state(uid)

    if state.get("step") != "awaiting_screenshot":
        bot.send_message(
            msg.chat.id,
            "Please start an exchange first using the menu below. 👇",
            reply_markup=main_keyboard()
        )
        return

    fund   = state.get("fund")
    amount = state.get("amount")
    xid    = state.get("xid")
    now    = datetime.now().strftime("%Y-%m-%d %H:%M")

    d = load_data()
    d["total_exchanges"] += 1
    exchange_id = str(d["total_exchanges"])

    caption = (
        f"📥 *New Exchange Request #{exchange_id}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: {user_mention(msg.from_user)}\n"
        f"🆔 User ID: `{uid}`\n"
        f"💱 Fund Type: *{fund}*\n"
        f"💰 Amount: *{amount}*\n"
        f"📱 XID/Mobile: `{xid}`\n"
        f"🕐 Time: {now}"
    )

    photo_id = msg.photo[-1].file_id

    sent = bot.send_photo(
        ADMIN_ID,
        photo_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=admin_approval_keyboard(exchange_id)
    )

    d["pending_exchanges"][exchange_id] = {
        "user_id":      uid,
        "fund":         fund,
        "amount":       amount,
        "xid":          xid,
        "admin_msg_id": sent.message_id,
        "time":         now
    }
    save_data(d)
    clear_state(uid)

    bot.send_message(
        msg.chat.id,
        "✅ *Screenshot received!*\n\n"
        "Your exchange request has been submitted.\n"
        "You'll be notified once the admin reviews it.\n\n"
        "Thank you for using *Xeo Exchanger!* 🚀",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

# ─── ADMIN: Approve / Decline ─────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data.startswith(("approve_", "decline_")))
def handle_admin_action(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ You are not authorized.")
        return

    action, exchange_id = call.data.split("_", 1)
    d = load_data()
    exchange = d["pending_exchanges"].get(exchange_id)

    if not exchange:
        bot.answer_callback_query(call.id, "⚠️ Already processed or not found.")
        return

    user_id = exchange["user_id"]
    fund    = exchange["fund"]
    amount  = exchange["amount"]
    xid     = exchange["xid"]

    if action == "approve":
        d["successful_exchanges"] = d.get("successful_exchanges", 0) + 1
        bot.send_message(
            user_id,
            f"🎉 *Exchange Approved!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💱 Fund Type: *{fund}*\n"
            f"💰 Amount: *{amount}*\n"
            f"📱 XID/Mobile: `{xid}`\n\n"
            f"Your exchange has been completed successfully! ✅\n"
            f"Thank you for using *Xeo Exchanger!* 🚀",
            parse_mode="Markdown"
        )
        new_caption = call.message.caption + "\n\n━━━━━━━━━━━━━━━━━━━━\n✅ *APPROVED*"
        bot.answer_callback_query(call.id, "✅ Approved and user notified!")

    else:
        d["declined_exchanges"] = d.get("declined_exchanges", 0) + 1
        bot.send_message(
            user_id,
            f"❌ *Exchange Declined*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💱 Fund Type: *{fund}*\n"
            f"💰 Amount: *{amount}*\n\n"
            f"Unfortunately your exchange request was declined.\n"
            f"For help, contact support: @XeoSupportBot 💬",
            parse_mode="Markdown"
        )
        new_caption = call.message.caption + "\n\n━━━━━━━━━━━━━━━━━━━━\n❌ *DECLINED*"
        bot.answer_callback_query(call.id, "❌ Declined and user notified!")

    try:
        bot.edit_message_caption(
            caption=new_caption,
            chat_id=ADMIN_ID,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
    except Exception:
        pass

    del d["pending_exchanges"][exchange_id]
    save_data(d)

# ─── KEEP-ALIVE WEB SERVER (for Render + UptimeRobot) ─────────────────────────
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Xeo Exchanger Bot is alive!")

    def log_message(self, format, *args):
        pass  # Suppress access logs

def run_web():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    print(f"🌐 Web server running on port {port}")
    server.serve_forever()

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Xeo Exchanger Bot is starting...")
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()
    print("🤖 Bot polling started...")
    bot.infinity_polling()
