# founderspace_demo_bot.py — single file, no external deps besides python-telegram-bot
# Deploy: Render Web Service
# Build Command:  pip install python-telegram-bot==21.*
# Start Command:  python founderspace_demo_bot.py
#
# English-only demo bot. Simulates the 9 real SAARS/FounderSpace child-bot modules
# (digital_store, affiliates, community, channel_guard, subscribers, tasks,
# referral, wallet, balance) using the real labels/texts from menus/*.py,
# wrapped in a live-activity simulator so a prospect feels the product working.

from __future__ import annotations
import asyncio, logging, itertools, random, os
from decimal import Decimal
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN           = os.environ["BOT_TOKEN"]
REAL_BOT_LINK   = "https://t.me/Founder_SpaceBot"
REFERRAL_REWARD = Decimal("1.00")

# ─────────────────────────────────────────────
#  In-memory demo state (per user)
# ─────────────────────────────────────────────

_bal:   dict[int, Decimal] = {}
_txs:   dict[int, list]    = {}
_rcnt:  dict[int, int]     = {}
_rearn: dict[int, Decimal] = {}
_sim_tasks: dict[int, asyncio.Task] = {}

_FAKE_NAMES = [
    "Carlos Silva", "Ana Ferreira", "Bruno Costa", "Mariana Souza", "Pedro Alves",
    "Juliana Lima", "Ricardo Gomes", "Fernanda Rocha", "Thiago Martins", "Camila Dias",
    "Priya Sharma", "Mohammed Al-Rashid", "Wei Zhang", "Sofia Müller", "Amara Diallo",
    "Yuki Tanaka", "Isabella Rossi", "Alejandro García", "Fatima Hassan", "Kwame Osei",
]
_name_cycle: dict[int, "itertools.cycle"] = {}


def bal(uid: int) -> Decimal:
    return _bal.get(uid, Decimal("0"))


def credit(uid: int, amount: Decimal, kind: str, note: str):
    _bal[uid] = bal(uid) + amount
    _txs.setdefault(uid, []).insert(0, (kind, note, amount))
    _txs[uid] = _txs[uid][:10]


# ─────────────────────────────────────────────
#  Live activity simulator
# ─────────────────────────────────────────────

async def _simulador(uid: int, bot):
    """Runs in background: every 12s injects 1 fake member + 1 fake sale."""
    cycle = _name_cycle.setdefault(uid, itertools.cycle(random.sample(_FAKE_NAMES, len(_FAKE_NAMES))))
    while True:
        await asyncio.sleep(12)
        nome = next(cycle)

        _rcnt[uid]  = _rcnt.get(uid, 0) + 1
        earn_ref    = REFERRAL_REWARD
        _rearn[uid] = _rearn.get(uid, Decimal("0")) + earn_ref
        credit(uid, earn_ref, "referral", f"👥 {nome} joined")

        sale_amount = Decimal("9.00")
        credit(uid, sale_amount, "purchase", f"🛍️ {nome} bought a product")

        members = 1 + _rcnt.get(uid, 0) * 3
        b = bal(uid)
        try:
            await bot.send_message(
                uid,
                f"🔔 <b>New sale on your FounderSpace bot!</b>\n\n"
                f"👤 <b>{nome}</b> joined through your link\n"
                f"🛍️ Bought a product\n"
                f"💰 <b>+{earn_ref + sale_amount:.2f} USDT</b> in your wallet\n\n"
                f"👥 Active members: <b>{members}</b>\n"
                f"💼 Total balance: <b>{b:.2f} USDT</b>\n\n"
                f"<i>While you were reading this, your bot was working for you.</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 Open my dashboard", callback_data="demo:main")],
                    [InlineKeyboardButton("🚀 I want the real bot →", url=REAL_BOT_LINK)],
                ])
            )
        except Exception:
            pass


def _start_sim(uid: int, bot):
    if uid in _sim_tasks and not _sim_tasks[uid].done():
        _sim_tasks[uid].cancel()
    _sim_tasks[uid] = asyncio.create_task(_simulador(uid, bot))


# ─────────────────────────────────────────────
#  Module registry — mirrors the real menus/*.py exactly
#  (MENU_LABEL, intro text, and keyboard taken verbatim
#  from the actual repository, prefix kept identical so behaviour
#  matches the production child bots)
# ─────────────────────────────────────────────

MODULES: dict[str, dict] = {
    "ld": {
        "label": "🛍️ Digital Store",
        "text": (
            "<b>🛍️ Welcome to our Store!</b>\n\n"
            "Find the best digital products and info-products here.\n\n"
            "👇 Choose an option below:"
        ),
        "buttons": [
            ("🛒 Browse Products", "products"),
            ("💳 Buy Now", "buy"),
            ("📦 My Orders", "orders"),
            ("🎁 Special Offers", "offers"),
            ("💬 Support", "support"),
        ],
    },
    "af": {
        "label": "🔗 Affiliate Channel",
        "text": (
            "<b>🔗 Affiliate Program</b>\n\n"
            "Share your link and earn automatic commissions on every sale.\n\n"
            "💡 The more you share, the more you earn.\n\n"
            "👇 What would you like to do?"
        ),
        "buttons": [
            ("🔗 My Affiliate Link", "link"),
            ("📊 My Commissions", "commissions"),
            ("👥 My Network", "network"),
            ("💸 Withdraw", "withdraw"),
            ("📖 How It Works", "info"),
        ],
    },
    "cm": {
        "label": "👥 Community",
        "text": (
            "<b>👥 Exclusive Community</b>\n\n"
            "Premium access to exclusive content, networking and direct support.\n\n"
            "🔒 Closed group • Instant access after payment\n\n"
            "👇 What would you like to do?"
        ),
        "buttons": [
            ("🔓 Join Community", "join"),
            ("📅 My Subscription", "subscription"),
            ("🔄 Renew Access", "renew"),
            ("🎁 Invite Friends", "invite"),
            ("❓ What's included?", "info"),
        ],
    },
    "cg": {
        "label": "🛡️ Channel Guard",
        "text": (
            "<b>🛡️ Channel Guard</b>\n\n"
            "Access exclusive paid channels with a single subscription.\n\n"
            "🔒 Access verified automatically • Removed on expiry\n\n"
            "👇 What would you like to do?"
        ),
        "buttons": [
            ("🔓 Get Access", "access"),
            ("📅 My Subscription", "subscription"),
            ("🔄 Renew Access", "renew"),
            ("📋 Channels List", "channels"),
            ("❓ How It Works", "info"),
        ],
    },
    "sb": {
        "label": "📋 Subscribers",
        "text": (
            "<b>📋 Subscription Plans</b>\n\n"
            "Subscribe and unlock exclusive benefits and content.\n\n"
            "⚡ Instant activation • Crypto payment\n\n"
            "👇 What would you like to do?"
        ),
        "buttons": [
            ("📋 View Plans", "plans"),
            ("✅ Subscribe", "subscribe"),
            ("📅 My Subscription", "subscription"),
            ("🔄 Renew", "renew"),
            ("🎁 Refer a Friend", "refer"),
        ],
    },
    "tk": {
        "label": "✅ Paid Tasks",
        "text": (
            "<b>✅ Paid Tasks</b>\n\n"
            "Complete tasks and earn crypto rewards instantly.\n\n"
            "🎯 Simple tasks • Fast payment • No limits\n\n"
            "👇 What would you like to do?"
        ),
        "buttons": [
            ("📋 Available Tasks", "list"),
            ("✅ My Completions", "completions"),
            ("💰 My Earnings", "earnings"),
            ("💸 Withdraw", "withdraw"),
            ("❓ How It Works", "info"),
        ],
    },
    "rf": {
        "label": "🎯 Referral System",
        "text": (
            "<b>🎯 Referral System</b>\n\n"
            "Invite friends and earn commissions on every purchase they make.\n\n"
            "💡 No limits — the more you refer, the more you earn.\n\n"
            "👇 What would you like to do?"
        ),
        "buttons": [
            ("🔗 My Referral Link", "link"),
            ("👥 My Referrals", "referrals"),
            ("💰 My Earnings", "earnings"),
            ("💸 Withdraw", "withdraw"),
            ("📖 How It Works", "info"),
        ],
    },
    "wl": {
        "label": "👛 Wallet",
        "text": (
            "<b>👛 Your Wallet</b>\n\n"
            "Manage your crypto balance directly from Telegram.\n\n"
            "🔒 Secure • Instant • Non-custodial payments via NowPayments\n\n"
            "👇 What would you like to do?"
        ),
        "buttons": [
            ("💰 My Balance", "balance"),
            ("➕ Top Up", "topup"),
            ("➖ Withdraw", "withdraw"),
            ("📊 Transactions", "history"),
            ("📤 Send", "send"),
        ],
    },
    "bl": {
        "label": "💳 Balance",
        "text": (
            "<b>💳 Internal Balance</b>\n\n"
            "Your internal account — track earnings, spending and withdrawals.\n\n"
            "🔒 Isolated per bot • Managed via NowPayments\n\n"
            "👇 What would you like to do?"
        ),
        "buttons": [
            ("💳 My Balance", "balance"),
            ("➕ Add Funds", "add"),
            ("📊 History", "history"),
            ("💸 Withdraw", "withdraw"),
            ("📈 Summary", "summary"),
        ],
    },
}

MODULE_ORDER = ["ld", "af", "cm", "cg", "sb", "tk", "rf", "wl", "bl"]


# ─────────────────────────────────────────────
#  Main demo menu
# ─────────────────────────────────────────────

def main_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(MODULES[p]["label"], callback_data=f"demo:open:{p}")]
            for p in MODULE_ORDER]
    rows.append([InlineKeyboardButton("💰 My Balance", callback_data="demo:balance")])
    rows.append([InlineKeyboardButton("ℹ️ How it works", callback_data="demo:about")])
    rows.append([InlineKeyboardButton("🚀 I want the real bot →", url=REAL_BOT_LINK)])
    return InlineKeyboardMarkup(rows)


def main_text(uid: int) -> str:
    return (
        "🚀 <b>FounderSpace — Interactive Demo</b>\n\n"
        f"💰 Your balance: <b>{bal(uid):.2f} USDT</b>\n\n"
        "Test all 9 monetization modules in real time.\n\n"
        "👇 Choose a module:"
    )


def module_keyboard(prefix: str) -> InlineKeyboardMarkup:
    mod = MODULES[prefix]
    rows = [[InlineKeyboardButton(label, callback_data=f"{prefix}:{action}")]
            for label, action in mod["buttons"]]
    rows.append([InlineKeyboardButton("⬅️ Back to menu", callback_data="demo:main")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────
#  Handlers
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    welcome = (
        "💸 <b>Your bot just made money.</b>\n\n"
        "While you were reading that sentence, <b>3 people</b> joined your channel "
        "and one bought your product.\n\n"
        "Welcome to <b>FounderSpace Demo</b> — the bot that works while you sleep.\n\n"
        "👇 Open your dashboard and see it for yourself:"
    )
    await update.message.reply_text(
        welcome, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Open my dashboard", callback_data="demo:main")]
        ])
    )
    _start_sim(uid, context.bot)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()

    if data == "demo:main":
        await query.edit_message_text(main_text(uid), parse_mode="HTML", reply_markup=main_keyboard())
        return

    if data == "demo:balance":
        tx_lines = "\n".join(
            f"• {note} — <b>+{amt:.2f} USDT</b>" for _, note, amt in _txs.get(uid, [])[:5]
        ) or "<i>No transactions yet.</i>"
        await query.edit_message_text(
            f"💰 <b>Your FounderSpace wallet</b>\n\n"
            f"Available balance: <b>{bal(uid):.2f} USDT</b>\n\n"
            f"📜 <b>Recent transactions:</b>\n{tx_lines}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to menu", callback_data="demo:main")]
            ])
        )
        return

    if data == "demo:about":
        await query.edit_message_text(
            "🤖 <b>FounderSpace — your digital business, on autopilot.</b>\n\n"
            "While you work, sleep, or take a vacation — the bot sells, delivers, and pays.\n\n"
            "<b>What's included:</b>\n"
            "• 🛍️ Digital Store with automatic product delivery\n"
            "• 🔗 Affiliate Channel — automatic commissions\n"
            "• 👥 Community — paid exclusive access\n"
            "• 🛡️ Channel Guard — verified paid access\n"
            "• 📋 Subscribers — recurring subscription plans\n"
            "• ✅ Paid Tasks — instant crypto rewards\n"
            "• 🎯 Referral System — viral growth, automatic commissions\n"
            "• 👛 Wallet & 💳 Balance — built-in, non-custodial via NowPayments\n\n"
            "<b>Pro Plan: $199/month.</b> No setup fee.\n"
            "<i>From menu to money — in minutes.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to menu", callback_data="demo:main")],
                [InlineKeyboardButton("🚀 I want the real bot →", url=REAL_BOT_LINK)],
            ])
        )
        return

    if data.startswith("demo:open:"):
        prefix = data.split(":")[2]
        mod = MODULES[prefix]
        await query.edit_message_text(mod["text"], parse_mode="HTML", reply_markup=module_keyboard(prefix))
        return

    # Module-internal actions: "<prefix>:<action>"
    if ":" in data:
        prefix, action = data.split(":", 1)
        if prefix in MODULES:
            await _handle_module_action(query, uid, prefix, action)
            return

    await query.answer("Unknown action.", show_alert=True)


async def _handle_module_action(query, uid: int, prefix: str, action: str):
    mod = MODULES[prefix]

    if action == "withdraw":
        text = (
            f"💸 <b>Withdraw</b>\n\n"
            f"Available balance: <b>{bal(uid):.2f} USDT</b>\n\n"
            f"<i>In the real bot, withdrawals are processed automatically via "
            f"NowPayments — no manual approval needed.</i>"
        )
    elif action == "balance":
        text = f"{mod['text']}\n\n💰 Current balance: <b>{bal(uid):.2f} USDT</b>"
    elif action == "info":
        text = (
            f"<b>{mod['label']} — How It Works</b>\n\n"
            f"This module runs fully automated inside your bot — no manual work, "
            f"no extra setup. Every action your members take here credits your "
            f"FounderSpace wallet instantly."
        )
    else:
        text = f"{mod['text']}\n\n<i>Loading {action.replace('_', ' ')}...</i>"

    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data=f"demo:open:{prefix}")]
        ])
    )


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_callback))
    log.info("[FounderSpace Demo] Bot starting (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
