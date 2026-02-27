"""
Xeo Exchanger Bot — FINAL FIXED
- Uses HTML parse mode everywhere (no Markdown crashes)
- All user input escaped with html.escape() before inserting into messages
- Admin messages sent as plain text (no parse mode at all)
- State persisted to JSON
- Full error logging
"""

import os
import json
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from html import escape

import telebot
from telebot import types

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID       = int(os.environ.get("ADMIN_ID", "6186511950"))
ADMIN_NUMBER   = "7012849145"
XEO_WALLET_URL = "https://xeowallet.vercel.app"

EXCHANGE_TYPES = ["Fxl", "Rdx", "Vsv", "Ultra Pay", "Saathi"]

print(f"[CONFIG] Admin ID: {ADMIN_ID}")
print(f"[CONFIG] Token loaded: {'YES' if BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE' else 'NO - SET BOT_TOKEN'}")

# ─── DATA ─────────────────────────────────────────────────────────────────────
DATA_FILE = "xeo_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception as ex:
            print(f"[ERROR] load_data: {ex}")
    return {
        "total_exchanges": 0,
        "successful_exchanges": 0,
        "declined_exchanges": 0,
        "pending_exchanges": {},
        "requests": [],
        "user_states": {}
    }

def save_data(d):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(d, f, indent=2)
    except Exception as ex:
        print(f"[ERROR] save_data: {ex}")

# ─── STATE ────────────────────────────────────────────────────────────────────
def get_state(uid):
    d = load_data()
    return d.get("user_states", {}).get(str(uid), {})

def set_state(uid, **kwargs):
    d = load_data()
    d.setdefault("user_states", {}).setdefault(str(uid), {}).update(kwargs)
    save_data(d)

def clear_state(uid):
    d = load_data()
    d.setdefault("user_states", {}).pop(str(uid), None)
    save_data(d)

# ─── BOT ──────────────────────────────────────────────────────────────────────
bot = telebot.TeleBot(BOT_TOKEN)

def e(text):
    """Escape any user-provided text for safe HTML insertion."""
    return escape(str(text))

def send_msg(chat_id, text, keyboard=None):
    """Send HTML message. Falls back to plain text if HTML fails."""
    try:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=keyboard)
        return True
    except Exception as err:
        print(f"[ERROR] send_msg HTML to {chat_id}: {err}")
        try:
            import re
            plain = re.sub(r"<[^>]+>", "", text)
            bot.send_message(chat_id, plain, reply_markup=keyboard)
            return True
        except Exception as err2:
            print(f"[ERROR] send_msg plain fallback to {chat_id}: {err2}")
            return False

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────
def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(*[types.KeyboardButton(b) for b in EXCHANGE_TYPES + ["📋 Request", "📊 Stats"]])
    return kb

def cancel_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Cancel"))
    return kb

def admin_kb(exchange_id):
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
    send_msg(
        msg.chat.id,
        "👋 <b>Welcome to Xeo Exchanger!</b>\n\n"
        "Select a fund type below to start exchanging,\n"
        "or use <b>Request</b> to suggest a new fund type.\n\n"
        "Use <b>Stats</b> to view exchanger info.",
        main_keyboard()
    )

# ─── CANCEL ───────────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "❌ Cancel")
def handle_cancel(msg):
    clear_state(msg.from_user.id)
    send_msg(msg.chat.id, "❌ Cancelled. Back to main menu.", main_keyboard())

# ─── STATS ────────────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def handle_stats(msg):
    d = load_data()
    send_msg(
        msg.chat.id,
        "📊 <b>Xeo Exchanger Stats</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏷 <b>Name:</b> Xeo Exchanger\n"
        "🔔 <b>Updates:</b> @Xeo_Wallet\n"
        "💬 <b>Support:</b> @XeoSupportBot\n\n"
        f"💱 <b>Fund Types:</b> {len(EXCHANGE_TYPES)}\n"
        f"<code>Fxl | Rdx | Vsv | Ultra Pay | Saathi</code>\n\n"
        f"📦 <b>Total Exchanges:</b> {d['total_exchanges']}\n"
        f"✅ <b>Successful:</b> {d['successful_exchanges']}\n"
        f"❌ <b>Declined:</b> {d.get('declined_exchanges', 0)}\n"
        f"⏳ <b>Pending:</b> {len(d.get('pending_exchanges', {}))}",
        main_keyboard()
    )

# ─── REQUEST ──────────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📋 Request")
def handle_request(msg):
    clear_state(msg.from_user.id)
    set_state(msg.from_user.id, step="awaiting_request")
    send_msg(
        msg.chat.id,
        "📋 <b>Request a New Fund Type</b>\n\n"
        "Type the name of the fund type you want to add:",
        cancel_keyboard()
    )

# ─── EXCHANGE TYPE ────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text in EXCHANGE_TYPES)
def handle_exchange_type(msg):
    fund = msg.text
    clear_state(msg.from_user.id)
    set_state(msg.from_user.id, step="awaiting_amount", fund=fund)
    send_msg(
        msg.chat.id,
        f"💱 <b>{e(fund)} Exchange</b>\n\n"
        f"💰 How much do you want to exchange?\n<i>(Enter the amount)</i>",
        cancel_keyboard()
    )

# ─── TEXT HANDLER ─────────────────────────────────────────────────────────────
@bot.message_handler(content_types=["text"])
def handle_text(msg):
    uid   = msg.from_user.id
    state = get_state(uid)
    step  = state.get("step")

    print(f"[TEXT] uid={uid} step={step} text={msg.text[:40]!r}")

    if step == "awaiting_request":
        req_text = msg.text.strip()
        d = load_data()
        d["requests"].append({
            "user_id":  uid,
            "username": msg.from_user.username or "none",
            "request":  req_text,
            "time":     datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        save_data(d)

        # Plain text only to admin — zero parse mode, zero risk
        uname = f"@{msg.from_user.username}" if msg.from_user.username else str(uid)
        admin_text = (
            "NEW FUND REQUEST\n"
            "--------------------\n"
            f"From: {msg.from_user.first_name or 'User'} {uname}\n"
            f"User ID: {uid}\n"
            f"Request: {req_text}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        try:
            bot.send_message(ADMIN_ID, admin_text)
            print("[ADMIN] Fund request sent OK")
        except Exception as err:
            print(f"[ERROR] Admin fund request failed: {err}")

        clear_state(uid)
        send_msg(
            msg.chat.id,
            "✅ <b>Request sent!</b>\n\n"
            "Your request has been forwarded to the admin.\n"
            "We'll review and add it if possible. Thank you! 🙏",
            main_keyboard()
        )

    elif step == "awaiting_amount":
        amount = msg.text.strip()
        set_state(uid, step="awaiting_xid", amount=amount)
        send_msg(
            msg.chat.id,
            "📱 <b>Enter your XID or Mobile Number</b>\n\n"
            "Please provide your XID or mobile number linked to your "
            f"<a href='{XEO_WALLET_URL}'>Xeo Wallet</a>:",
            cancel_keyboard()
        )

    elif step == "awaiting_xid":
        xid    = msg.text.strip()
        fund   = state.get("fund", "Unknown")
        amount = state.get("amount", "Unknown")
        set_state(uid, step="awaiting_screenshot", xid=xid)
        send_msg(
            msg.chat.id,
            "📤 <b>Send Payment Now</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💱 Fund Type: <b>{e(fund)}</b>\n"
            f"💰 Amount: <b>{e(amount)}</b>\n\n"
            "Send to this number:\n"
            f"📞 <code>{ADMIN_NUMBER}</code>\n\n"
            "After sending, upload a <b>screenshot</b> of your payment as proof. 📸",
            cancel_keyboard()
        )

    elif step == "awaiting_screenshot":
        send_msg(
            msg.chat.id,
            "📸 Please send a <b>photo/screenshot</b> of your payment, not text.",
            cancel_keyboard()
        )

    else:
        send_msg(msg.chat.id, "Please use the menu below to get started. 👇", main_keyboard())

# ─── PHOTO ────────────────────────────────────────────────────────────────────
@bot.message_handler(content_types=["photo"])
def handle_screenshot(msg):
    uid   = msg.from_user.id
    state = get_state(uid)
    step  = state.get("step")

    print(f"[PHOTO] uid={uid} step={step}")

    if step != "awaiting_screenshot":
        send_msg(msg.chat.id, "Please start an exchange first using the menu below. 👇", main_keyboard())
        return

    fund   = state.get("fund", "Unknown")
    amount = state.get("amount", "Unknown")
    xid    = state.get("xid", "Unknown")
    now    = datetime.now().strftime("%Y-%m-%d %H:%M")

    d = load_data()
    d["total_exchanges"] += 1
    exchange_id = str(d["total_exchanges"])

    # Plain text caption — NO parse_mode at all
    uname = f"@{msg.from_user.username}" if msg.from_user.username else str(uid)
    caption = (
        f"NEW EXCHANGE #{exchange_id}\n"
        f"--------------------\n"
        f"User: {msg.from_user.first_name or 'User'} {uname}\n"
        f"User ID: {uid}\n"
        f"Fund: {fund}\n"
        f"Amount: {amount}\n"
        f"XID/Mobile: {xid}\n"
        f"Time: {now}"
    )

    photo_id = msg.photo[-1].file_id
    print(f"[PHOTO] Sending to admin, exchange_id={exchange_id}")

    try:
        sent = bot.send_photo(ADMIN_ID, photo_id, caption=caption, reply_markup=admin_kb(exchange_id))
        print(f"[ADMIN] Photo sent OK, msg_id={sent.message_id}")
    except Exception as err:
        print(f"[ERROR] send_photo to admin failed: {err}")
        d["total_exchanges"] -= 1
        save_data(d)
        send_msg(
            msg.chat.id,
            "⚠️ Error submitting your request. Please try again or contact @XeoSupportBot.",
            main_keyboard()
        )
        return

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

    send_msg(
        msg.chat.id,
        "✅ <b>Screenshot received!</b>\n\n"
        "Your exchange request has been submitted.\n"
        "You'll be notified once the admin reviews it.\n\n"
        "Thank you for using <b>Xeo Exchanger!</b> 🚀",
        main_keyboard()
    )

# ─── ADMIN APPROVE / DECLINE ──────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data.startswith(("approve_", "decline_")))
def handle_admin_action(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Not authorized.")
        return

    action, exchange_id = call.data.split("_", 1)
    d = load_data()
    exchange = d["pending_exchanges"].get(exchange_id)

    if not exchange:
        bot.answer_callback_query(call.id, "Already processed or not found.")
        return

    user_id = exchange["user_id"]
    fund    = exchange["fund"]
    amount  = exchange["amount"]
    xid     = exchange["xid"]

    if action == "approve":
        d["successful_exchanges"] = d.get("successful_exchanges", 0) + 1
        send_msg(
            user_id,
            "🎉 <b>Exchange Approved!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💱 Fund Type: <b>{e(fund)}</b>\n"
            f"💰 Amount: <b>{e(amount)}</b>\n"
            f"📱 XID/Mobile: <code>{e(xid)}</code>\n\n"
            "Completed successfully! ✅\n"
            "Thank you for using <b>Xeo Exchanger!</b> 🚀"
        )
        status = "\n\n✅ APPROVED"
        bot.answer_callback_query(call.id, "Approved!")
    else:
        d["declined_exchanges"] = d.get("declined_exchanges", 0) + 1
        send_msg(
            user_id,
            "❌ <b>Exchange Declined</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💱 Fund Type: <b>{e(fund)}</b>\n"
            f"💰 Amount: <b>{e(amount)}</b>\n\n"
            "Your request was declined.\n"
            "Contact support: @XeoSupportBot 💬"
        )
        status = "\n\n❌ DECLINED"
        bot.answer_callback_query(call.id, "Declined!")

    # Edit admin photo caption — plain text, no parse_mode
    try:
        bot.edit_message_caption(
            caption=(call.message.caption or "") + status,
            chat_id=ADMIN_ID,
            message_id=call.message.message_id
        )
    except Exception as err:
        print(f"[ERROR] edit_message_caption: {err}")

    del d["pending_exchanges"][exchange_id]
    save_data(d)

# ─── KEEP-ALIVE WEB SERVER ────────────────────────────────────────────────────
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Xeo Exchanger Bot is alive!")
    def log_message(self, *args):
        pass

def run_web():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), PingHandler).serve_forever()

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Xeo Exchanger Bot starting...")
    threading.Thread(target=run_web, daemon=True).start()
    print("Polling...")
    bot.infinity_polling()
