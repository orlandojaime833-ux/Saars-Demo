# founderspace_demo_bot.py — single file, no external deps besides python-telegram-bot
# Deploy: Render Web Service
# Build Command:  pip install python-telegram-bot==21.*
# Start Command:  python founderspace_demo_bot.py

from __future__ import annotations
import asyncio, logging, itertools, random, os
from datetime import datetime, timedelta
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
_sim_count: dict[int, int] = {}   # tracks how many sim cycles ran (for spacing)

_FAKE_NAMES = [
    "Carlos Silva", "Ana Ferreira", "Bruno Costa", "Mariana Souza", "Pedro Alves",
    "Juliana Lima", "Ricardo Gomes", "Fernanda Rocha", "Thiago Martins", "Camila Dias",
    "Priya Sharma", "Mohammed Al-Rashid", "Wei Zhang", "Sofia Müller", "Amara Diallo",
    "Yuki Tanaka", "Isabella Rossi", "Alejandro García", "Fatima Hassan", "Kwame Osei",
]
_name_cycle: dict[int, "itertools.cycle"] = {}

# ─────────────────────────────────────────────
#  Realistic demo data sets
# ─────────────────────────────────────────────

_PRODUCTS = [
    ("📘 Copywriting Master Course", "97.00", "Digital course • 47 lessons"),
    ("🎯 Paid Traffic Blueprint", "67.00", "PDF + video • 12 modules"),
    ("🤖 AI Automation Toolkit", "47.00", "Templates + scripts bundle"),
    ("📊 Sales Funnel Masterclass", "127.00", "Video course • 8h content"),
    ("🎤 Podcast Monetization Guide", "37.00", "eBook + worksheets"),
]

_TASKS = [
    ("📢 Follow our Instagram", "0.50", "completed"),
    ("▶️ Watch intro video (3 min)", "1.00", "completed"),
    ("⭐ Leave a 5-star review", "2.00", "available"),
    ("🔗 Share referral link", "1.50", "available"),
    ("💬 Send feedback form", "0.75", "available"),
]

_CHANNELS = [
    ("📈 Trading Signals VIP", "Monthly", "29.90"),
    ("🤖 AI Tools Weekly", "Monthly", "19.90"),
    ("💼 Business Insiders Club", "Quarterly", "49.90"),
]

_SUBS_PLANS = [
    ("🥉 Starter", "9.90/mo", "Basic content + community"),
    ("🥈 Pro", "29.90/mo", "All content + weekly calls"),
    ("🥇 Elite", "79.90/mo", "1-on-1 coaching + all access"),
]

_REFERRALS_SAMPLE = [
    ("Carlos Silva", "2025-06-01", "1.00"),
    ("Ana Ferreira",  "2025-06-03", "1.00"),
    ("Bruno Costa",   "2025-06-07", "1.00"),
    ("Mariana Souza", "2025-06-10", "1.00"),
    ("Pedro Alves",   "2025-06-14", "1.00"),
]

_AFFILIATE_SALES = [
    ("📘 Copywriting Course", "2025-06-02", "9.70"),
    ("🎯 Traffic Blueprint",  "2025-06-05", "6.70"),
    ("🤖 AI Toolkit",         "2025-06-09", "4.70"),
    ("📘 Copywriting Course", "2025-06-13", "9.70"),
]


def bal(uid: int) -> Decimal:
    return _bal.get(uid, Decimal("0"))


def credit(uid: int, amount: Decimal, kind: str, note: str):
    _bal[uid] = bal(uid) + amount
    _txs.setdefault(uid, []).insert(0, (kind, note, amount))
    _txs[uid] = _txs[uid][:10]


# ─────────────────────────────────────────────
#  Live activity simulator — fires every 10 MINUTES
#  (600 s) so the prospect never sees a jarring
#  second-by-second flood and the timing feels organic.
# ─────────────────────────────────────────────

async def _simulador(uid: int, bot):
    """Background task: every 10 min injects 1 fake member + 1 fake sale notification."""
    cycle = _name_cycle.setdefault(uid, itertools.cycle(random.sample(_FAKE_NAMES, len(_FAKE_NAMES))))
    _sim_count[uid] = _sim_count.get(uid, 0)

    while True:
        await asyncio.sleep(600)          # ← 10 minutes between notifications
        _sim_count[uid] += 1
        nome = next(cycle)

        _rcnt[uid]  = _rcnt.get(uid, 0) + 1
        earn_ref    = REFERRAL_REWARD
        _rearn[uid] = _rearn.get(uid, Decimal("0")) + earn_ref
        credit(uid, earn_ref, "referral", f"👥 {nome} joined")

        # Pick a random product for this cycle
        prod_name, prod_price, _ = random.choice(_PRODUCTS)
        sale_amount = Decimal(prod_price)
        commission  = (sale_amount * Decimal("0.10")).quantize(Decimal("0.01"))
        credit(uid, commission, "purchase", f"🛍️ {nome} bought {prod_name}")

        members = 18 + _rcnt.get(uid, 0) * 3   # starts at 18 so it feels established
        b = bal(uid)

        # Timestamp shows the REAL clock time so the gap between messages
        # looks natural (10-min intervals = believable background activity)
        now_str = datetime.now().strftime("%H:%M")

        try:
            await bot.send_message(
                uid,
                f"🔔 <b>New activity on your FounderSpace bot!</b>  <i>{now_str}</i>\n\n"
                f"👤 <b>{nome}</b> joined through your referral link\n"
                f"🛍️ Purchased: <b>{prod_name}</b>\n"
                f"💰 Your commission: <b>+{earn_ref + commission:.2f} USDT</b>\n\n"
                f"👥 Active members: <b>{members}</b>\n"
                f"💼 Total balance: <b>{b:.2f} USDT</b>\n\n"
                f"<i>While you were doing other things, your bot kept working.</i>",
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
#  Module registry
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
            ("💳 Buy Now",         "buy"),
            ("📦 My Orders",       "orders"),
            ("🎁 Special Offers",  "offers"),
            ("💬 Support",         "support"),
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
            ("🔗 My Affiliate Link",  "link"),
            ("📊 My Commissions",     "commissions"),
            ("👥 My Network",         "network"),
            ("💸 Withdraw",           "withdraw"),
            ("📖 How It Works",       "info"),
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
            ("🔓 Join Community",  "join"),
            ("📅 My Subscription", "subscription"),
            ("🔄 Renew Access",    "renew"),
            ("🎁 Invite Friends",  "invite"),
            ("❓ What's included?","info"),
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
            ("🔓 Get Access",      "access"),
            ("📅 My Subscription", "subscription"),
            ("🔄 Renew Access",    "renew"),
            ("📋 Channels List",   "channels"),
            ("❓ How It Works",    "info"),
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
            ("📋 View Plans",      "plans"),
            ("✅ Subscribe",       "subscribe"),
            ("📅 My Subscription", "subscription"),
            ("🔄 Renew",           "renew"),
            ("🎁 Refer a Friend",  "refer"),
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
            ("📋 Available Tasks",  "list"),
            ("✅ My Completions",   "completions"),
            ("💰 My Earnings",      "earnings"),
            ("💸 Withdraw",         "withdraw"),
            ("❓ How It Works",     "info"),
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
            ("👥 My Referrals",     "referrals"),
            ("💰 My Earnings",      "earnings"),
            ("💸 Withdraw",         "withdraw"),
            ("📖 How It Works",     "info"),
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
            ("💰 My Balance",    "balance"),
            ("➕ Top Up",         "topup"),
            ("➖ Withdraw",       "withdraw"),
            ("📊 Transactions",  "history"),
            ("📤 Send",          "send"),
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
            ("➕ Add Funds",   "add"),
            ("📊 History",    "history"),
            ("💸 Withdraw",   "withdraw"),
            ("📈 Summary",    "summary"),
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
    rows.append([InlineKeyboardButton("💰 My Balance",      callback_data="demo:balance")])
    rows.append([InlineKeyboardButton("ℹ️ How it works",    callback_data="demo:about")])
    rows.append([InlineKeyboardButton("🚀 I want the real bot →", url=REAL_BOT_LINK)])
    return InlineKeyboardMarkup(rows)


def main_text(uid: int) -> str:
    members = 18 + _rcnt.get(uid, 0) * 3
    return (
        "🚀 <b>FounderSpace — Interactive Demo</b>\n\n"
        f"💰 Your balance: <b>{bal(uid):.2f} USDT</b>\n"
        f"👥 Active members: <b>{members}</b>\n\n"
        "Test all 9 monetization modules in real time.\n\n"
        "👇 Choose a module:"
    )


def module_keyboard(prefix: str) -> InlineKeyboardMarkup:
    mod = MODULES[prefix]
    rows = [[InlineKeyboardButton(label, callback_data=f"{prefix}:{action}")]
            for label, action in mod["buttons"]]
    rows.append([InlineKeyboardButton("⬅️ Back to menu", callback_data="demo:main")])
    return InlineKeyboardMarkup(rows)


def _back_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data=f"demo:open:{prefix}")],
    ])


# ─────────────────────────────────────────────
#  Handlers
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # Seed a realistic starting balance so the dashboard looks live from the first click
    if uid not in _bal:
        credit(uid, Decimal("12.50"), "welcome",  "🎁 Welcome bonus")
        credit(uid, Decimal("9.00"),  "purchase",  "🛍️ Carlos Silva bought Copywriting Course")
        credit(uid, Decimal("1.00"),  "referral",  "👥 Ana Ferreira joined")
        credit(uid, Decimal("4.70"),  "affiliate", "🔗 Affiliate commission — AI Toolkit")
        _rcnt[uid]  = 3
        _rearn[uid] = Decimal("3.00")

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
    uid   = query.from_user.id
    data  = query.data
    await query.answer()

    if data == "demo:main":
        await query.edit_message_text(main_text(uid), parse_mode="HTML", reply_markup=main_keyboard())
        return

    if data == "demo:balance":
        tx_lines = "\n".join(
            f"• {note} — <b>+{amt:.2f} USDT</b>" for _, note, amt in _txs.get(uid, [])[:6]
        ) or "<i>No transactions yet.</i>"
        await query.edit_message_text(
            f"💰 <b>Your FounderSpace Wallet</b>\n\n"
            f"Available balance: <b>{bal(uid):.2f} USDT</b>\n"
            f"Pending withdrawal: <b>0.00 USDT</b>\n\n"
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
                [InlineKeyboardButton("⬅️ Back to menu",         callback_data="demo:main")],
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


# ─────────────────────────────────────────────
#  Rich per-action handlers — all actions show
#  fully populated, realistic data (no "Coming
#  soon" or blank states).
# ─────────────────────────────────────────────

async def _handle_module_action(query, uid: int, prefix: str, action: str):

    # ── DIGITAL STORE ──────────────────────────────────────────────────────
    if prefix == "ld":
        if action == "products":
            lines = "\n".join(
                f"• {name}  —  <b>${price}</b>  <i>{desc}</i>"
                for name, price, desc in _PRODUCTS
            )
            text = f"🛒 <b>Product Catalog</b>\n\n{lines}\n\n<i>Tap any product to buy instantly via crypto.</i>"

        elif action == "buy":
            p = _PRODUCTS[0]
            text = (
                f"💳 <b>Quick Buy</b>\n\n"
                f"Product: <b>{p[0]}</b>\n"
                f"Price: <b>${p[1]} USDT</b>\n\n"
                f"Payment: USDT (TRC-20 / ERC-20)\n"
                f"Delivery: instant after confirmation\n\n"
                f"<i>In the real bot, a NowPayments invoice is generated automatically.</i>"
            )

        elif action == "orders":
            text = (
                "📦 <b>My Orders</b>\n\n"
                "✅ <b>Copywriting Master Course</b> — Jun 14 — $97.00\n"
                "   🔗 <i>Access link delivered automatically</i>\n\n"
                "✅ <b>AI Automation Toolkit</b> — Jun 02 — $47.00\n"
                "   🔗 <i>Access link delivered automatically</i>\n\n"
                "<i>2 orders • $144.00 total</i>"
            )

        elif action == "offers":
            text = (
                "🎁 <b>Special Offers — This Week</b>\n\n"
                "🔥 <b>Traffic Blueprint</b>  ~~$67~~ → <b>$39.00</b>  (42% off)\n"
                "⏳ Ends in 2 days\n\n"
                "🔥 <b>Sales Funnel Masterclass</b>  ~~$127~~ → <b>$79.00</b>  (38% off)\n"
                "⏳ Ends in 5 days"
            )

        elif action == "support":
            text = (
                "💬 <b>Support</b>\n\n"
                "Average response time: <b>under 2 hours</b>\n\n"
                "📧 Email: support@founderspace.io\n"
                "💬 Telegram: @FounderSpaceSupport\n\n"
                "<i>In the real bot, this button opens a direct support thread.</i>"
            )
        else:
            text = MODULES[prefix]["text"]

    # ── AFFILIATE ──────────────────────────────────────────────────────────
    elif prefix == "af":
        if action == "link":
            text = (
                "🔗 <b>Your Affiliate Link</b>\n\n"
                "<code>https://t.me/FounderSpaceBot?start=aff_demo123</code>\n\n"
                "Share this link on social media, WhatsApp, or groups.\n"
                "Every sale earns you <b>10% commission</b> automatically."
            )

        elif action == "commissions":
            total = sum(Decimal(s[2]) for s in _AFFILIATE_SALES)
            lines = "\n".join(
                f"• {prod}  {date}  <b>+${amt} USDT</b>"
                for prod, date, amt in _AFFILIATE_SALES
            )
            text = f"📊 <b>My Commissions</b>\n\n{lines}\n\n💰 Total earned: <b>${total:.2f} USDT</b>"

        elif action == "network":
            text = (
                "👥 <b>My Affiliate Network</b>\n\n"
                "Direct referrals: <b>12 people</b>\n"
                "Tier-2 referrals: <b>5 people</b>\n"
                "Total network:    <b>17 people</b>\n\n"
                "🏆 Top performer: <b>Mariana Souza</b>  (3 sales this week)"
            )

        elif action == "withdraw":
            text = (
                f"💸 <b>Withdraw Commissions</b>\n\n"
                f"Available: <b>{bal(uid):.2f} USDT</b>\n"
                f"Minimum withdrawal: <b>5.00 USDT</b>\n\n"
                f"Network: TRC-20 (Tron) or ERC-20\n\n"
                f"<i>In the real bot, withdrawal is processed via NowPayments — no manual approval.</i>"
            )

        elif action == "info":
            text = (
                "📖 <b>How the Affiliate Program Works</b>\n\n"
                "1. Share your unique link\n"
                "2. Someone buys through your link\n"
                "3. <b>10% commission</b> is credited instantly\n"
                "4. Withdraw anytime above 5 USDT\n\n"
                "✅ Tracked automatically • No manual work required"
            )
        else:
            text = MODULES[prefix]["text"]

    # ── COMMUNITY ──────────────────────────────────────────────────────────
    elif prefix == "cm":
        if action == "join":
            text = (
                "🔓 <b>Join the Community</b>\n\n"
                "Monthly plan: <b>$29.90 USDT</b>\n"
                "Quarterly plan: <b>$69.90 USDT</b>  (save 22%)\n\n"
                "✅ Instant access after payment\n"
                "✅ Removed automatically when subscription expires\n\n"
                "<i>In the real bot, an invoice is generated via NowPayments.</i>"
            )

        elif action == "subscription":
            expire = (datetime.now() + timedelta(days=18)).strftime("%b %d, %Y")
            text = (
                "📅 <b>My Subscription</b>\n\n"
                "Plan: <b>Pro — $29.90/month</b>\n"
                f"Expires: <b>{expire}</b>\n"
                "Status: <b>✅ Active</b>\n\n"
                "Community members: <b>847</b>\n"
                "Your join date: <b>Jun 01, 2025</b>"
            )

        elif action == "renew":
            text = (
                "🔄 <b>Renew Access</b>\n\n"
                "Current plan expires in <b>18 days</b>.\n\n"
                "Renew now and keep uninterrupted access:\n"
                "• Monthly: $29.90\n"
                "• Quarterly: $69.90 (best value)\n\n"
                "<i>Renewing early extends from current expiry date.</i>"
            )

        elif action == "invite":
            text = (
                "🎁 <b>Invite Friends</b>\n\n"
                "Your invite link:\n"
                "<code>https://t.me/FounderSpaceBot?start=cm_demo123</code>\n\n"
                "For every friend who subscribes, you earn <b>1 month free</b>.\n"
                "You've referred <b>2 friends</b> so far — keep going!"
            )

        elif action == "info":
            text = (
                "❓ <b>What's Included in the Community</b>\n\n"
                "✅ Private Telegram group (847 members)\n"
                "✅ Weekly live Q&A sessions\n"
                "✅ Exclusive PDF resources library\n"
                "✅ Direct access to the creator\n"
                "✅ Job board & collaboration channel\n\n"
                "🔒 Access managed automatically by Channel Guard."
            )
        else:
            text = MODULES[prefix]["text"]

    # ── CHANNEL GUARD ──────────────────────────────────────────────────────
    elif prefix == "cg":
        if action == "access":
            text = (
                "🔓 <b>Get Channel Access</b>\n\n"
                + "\n".join(
                    f"• {name}  ({freq})  <b>${price}/mo USDT</b>"
                    for name, freq, price in _CHANNELS
                )
                + "\n\n<i>Choose a channel and pay once — access is granted instantly.</i>"
            )

        elif action == "subscription":
            expire = (datetime.now() + timedelta(days=22)).strftime("%b %d, %Y")
            text = (
                "📅 <b>My Active Channels</b>\n\n"
                f"📈 Trading Signals VIP  — expires <b>{expire}</b>  ✅\n"
                "🤖 AI Tools Weekly      — <b>not subscribed</b>\n"
                "💼 Business Insiders    — <b>not subscribed</b>\n\n"
                "You are a member of <b>1 channel</b>."
            )

        elif action == "renew":
            expire = (datetime.now() + timedelta(days=22)).strftime("%b %d, %Y")
            text = (
                f"🔄 <b>Renew Channel Access</b>\n\n"
                f"📈 Trading Signals VIP — expires <b>{expire}</b>\n\n"
                "Renew for <b>$29.90/month</b> to maintain access.\n\n"
                "<i>If not renewed, you will be removed automatically on expiry.</i>"
            )

        elif action == "channels":
            text = (
                "📋 <b>Available Channels</b>\n\n"
                + "\n".join(
                    f"• <b>{name}</b>  |  {freq}  |  ${price} USDT"
                    for name, freq, price in _CHANNELS
                )
                + "\n\n👥 Combined subscriber base: <b>2,340 members</b>"
            )

        elif action == "info":
            text = (
                "❓ <b>How Channel Guard Works</b>\n\n"
                "1. Choose a channel and subscribe\n"
                "2. Pay via USDT (TRC-20)\n"
                "3. Bot adds you to the channel instantly\n"
                "4. On expiry, you're removed automatically\n"
                "5. Renew anytime from this menu\n\n"
                "✅ Zero manual work for the channel owner."
            )
        else:
            text = MODULES[prefix]["text"]

    # ── SUBSCRIBERS ────────────────────────────────────────────────────────
    elif prefix == "sb":
        if action == "plans":
            text = (
                "📋 <b>Subscription Plans</b>\n\n"
                + "\n".join(
                    f"• <b>{tier}</b>  {price}\n  {desc}"
                    for tier, price, desc in _SUBS_PLANS
                )
                + "\n\n<i>All plans billed in USDT. Cancel anytime.</i>"
            )

        elif action == "subscribe":
            text = (
                "✅ <b>Subscribe Now</b>\n\n"
                "Selected: <b>Pro Plan — $29.90/month</b>\n\n"
                "Payment: USDT (TRC-20)\n"
                "Activation: instant after confirmation\n\n"
                "<i>In the real bot, a NowPayments invoice is generated here.</i>"
            )

        elif action == "subscription":
            expire = (datetime.now() + timedelta(days=15)).strftime("%b %d, %Y")
            text = (
                "📅 <b>My Subscription</b>\n\n"
                "Plan: <b>🥈 Pro — $29.90/month</b>\n"
                f"Renews: <b>{expire}</b>\n"
                "Status: <b>✅ Active</b>\n\n"
                "Member since: <b>May 15, 2025</b>"
            )

        elif action == "renew":
            text = (
                "🔄 <b>Renew Subscription</b>\n\n"
                "Your Pro plan renews in <b>15 days</b>.\n\n"
                "Renewing early extends from current expiry date — no days lost.\n\n"
                "• Pro: $29.90/month\n"
                "• Elite: $79.90/month\n"
            )

        elif action == "refer":
            text = (
                "🎁 <b>Refer a Friend</b>\n\n"
                "Share your link and earn <b>$5 USDT</b> for each friend who subscribes.\n\n"
                "<code>https://t.me/FounderSpaceBot?start=sb_demo123</code>\n\n"
                "You've referred <b>3 friends</b> and earned <b>$15.00 USDT</b> in referral bonuses."
            )
        else:
            text = MODULES[prefix]["text"]

    # ── TASKS ──────────────────────────────────────────────────────────────
    elif prefix == "tk":
        if action == "list":
            available = [t for t in _TASKS if t[2] == "available"]
            lines = "\n".join(
                f"• {name}  → <b>+${reward} USDT</b>"
                for name, reward, _ in available
            )
            text = f"📋 <b>Available Tasks</b>\n\n{lines}\n\n<i>Tap a task in the real bot to complete and earn instantly.</i>"

        elif action == "completions":
            done = [t for t in _TASKS if t[2] == "completed"]
            lines = "\n".join(
                f"✅ {name}  <b>+${reward} USDT</b>  earned"
                for name, reward, _ in done
            )
            text = f"✅ <b>Completed Tasks</b>\n\n{lines}\n\n<i>{len(done)} tasks completed so far.</i>"

        elif action == "earnings":
            total = sum(Decimal(t[1]) for t in _TASKS if t[2] == "completed")
            text = (
                f"💰 <b>Task Earnings</b>\n\n"
                f"Tasks completed: <b>{sum(1 for t in _TASKS if t[2] == 'completed')}</b>\n"
                f"Total earned: <b>${total:.2f} USDT</b>\n\n"
                f"Available to withdraw: <b>${total:.2f} USDT</b>"
            )

        elif action == "withdraw":
            total_tasks = sum(Decimal(t[1]) for t in _TASKS if t[2] == "completed")
            text = (
                f"💸 <b>Withdraw Task Earnings</b>\n\n"
                f"Available: <b>${total_tasks:.2f} USDT</b>\n"
                f"Min. withdrawal: <b>2.00 USDT</b>\n\n"
                f"Network: TRC-20 or ERC-20\n\n"
                f"<i>In the real bot, processed via NowPayments automatically.</i>"
            )

        elif action == "info":
            text = (
                "❓ <b>How Paid Tasks Work</b>\n\n"
                "1. Browse available tasks\n"
                "2. Complete the task (follow, watch, share…)\n"
                "3. Submit proof inside the bot\n"
                "4. Reward is credited instantly after verification\n"
                "5. Withdraw to any USDT wallet\n\n"
                "✅ New tasks added every week."
            )
        else:
            text = MODULES[prefix]["text"]

    # ── REFERRAL ───────────────────────────────────────────────────────────
    elif prefix == "rf":
        if action == "link":
            text = (
                "🔗 <b>Your Referral Link</b>\n\n"
                "<code>https://t.me/FounderSpaceBot?start=ref_demo123</code>\n\n"
                f"Referrals so far: <b>{_rcnt.get(uid, 3)}</b>\n"
                f"Total earned: <b>${_rearn.get(uid, Decimal('3.00')):.2f} USDT</b>\n\n"
                "Every friend who joins earns you <b>$1.00 USDT</b> automatically."
            )

        elif action == "referrals":
            lines = "\n".join(
                f"• {name}  {date}  <b>+${earn} USDT</b>"
                for name, date, earn in _REFERRALS_SAMPLE[:_rcnt.get(uid, 3) + 2]
            )
            text = f"👥 <b>My Referrals</b>\n\n{lines}\n\n<i>{_rcnt.get(uid, 3)} referrals total.</i>"

        elif action == "earnings":
            earned = _rearn.get(uid, Decimal("3.00"))
            text = (
                f"💰 <b>Referral Earnings</b>\n\n"
                f"Total referrals:  <b>{_rcnt.get(uid, 3)}</b>\n"
                f"Total earned:     <b>${earned:.2f} USDT</b>\n"
                f"This month:       <b>${earned:.2f} USDT</b>\n\n"
                f"Rate: <b>$1.00 USDT</b> per referral who joins"
            )

        elif action == "withdraw":
            earned = _rearn.get(uid, Decimal("3.00"))
            text = (
                f"💸 <b>Withdraw Referral Earnings</b>\n\n"
                f"Available: <b>${earned:.2f} USDT</b>\n"
                f"Minimum: <b>5.00 USDT</b>\n\n"
                f"{'✅ Ready to withdraw!' if earned >= 5 else f'⏳ Need ${5 - float(earned):.2f} more to reach minimum.'}\n\n"
                f"<i>In the real bot, processed via NowPayments automatically.</i>"
            )

        elif action == "info":
            text = (
                "📖 <b>How the Referral System Works</b>\n\n"
                "1. Copy your unique referral link\n"
                "2. Share it anywhere (Telegram, WhatsApp, Instagram…)\n"
                "3. When someone starts the bot through your link, you earn <b>$1.00 USDT</b>\n"
                "4. When they buy something, you earn an extra commission\n"
                "5. Withdraw anytime above $5 USDT\n\n"
                "✅ Fully automated — no manual tracking needed."
            )
        else:
            text = MODULES[prefix]["text"]

    # ── WALLET ─────────────────────────────────────────────────────────────
    elif prefix == "wl":
        if action == "balance":
            tx_lines = "\n".join(
                f"• {note} — <b>+{amt:.2f} USDT</b>"
                for _, note, amt in _txs.get(uid, [])[:5]
            ) or "<i>No transactions yet.</i>"
            text = (
                f"💰 <b>Wallet Balance</b>\n\n"
                f"Available: <b>{bal(uid):.2f} USDT</b>\n"
                f"Locked:    <b>0.00 USDT</b>\n\n"
                f"📜 <b>Recent:</b>\n{tx_lines}"
            )

        elif action == "topup":
            text = (
                "➕ <b>Top Up Wallet</b>\n\n"
                "Send USDT to your deposit address:\n\n"
                "<code>TQn4vDemo1234xyzABCD5678ExampleAddr</code>\n"
                "<i>(TRC-20 network)</i>\n\n"
                "Min. deposit: <b>5.00 USDT</b>\n"
                "Confirmed in: <b>~2 minutes</b>\n\n"
                "<i>Address is unique to your account and generated via NowPayments.</i>"
            )

        elif action == "withdraw":
            text = (
                f"➖ <b>Withdraw from Wallet</b>\n\n"
                f"Available: <b>{bal(uid):.2f} USDT</b>\n"
                f"Fee: <b>1.00 USDT</b>  (network fee)\n\n"
                f"Enter your USDT address and amount in the real bot — sent within minutes.\n\n"
                f"<i>Processed via NowPayments. No manual approval needed.</i>"
            )

        elif action == "history":
            tx_lines = "\n".join(
                f"• {note}  <b>+{amt:.2f} USDT</b>"
                for _, note, amt in _txs.get(uid, [])
            ) or "<i>No transactions yet.</i>"
            text = f"📊 <b>Transaction History</b>\n\n{tx_lines}"

        elif action == "send":
            text = (
                "📤 <b>Send USDT</b>\n\n"
                f"Your balance: <b>{bal(uid):.2f} USDT</b>\n\n"
                "In the real bot, enter a recipient's Telegram username or USDT address "
                "and the amount — transferred instantly from wallet to wallet.\n\n"
                "<i>Internal transfers are instant and fee-free.</i>"
            )
        else:
            text = MODULES[prefix]["text"]

    # ── BALANCE ────────────────────────────────────────────────────────────
    elif prefix == "bl":
        if action == "balance":
            text = (
                f"💳 <b>Internal Balance</b>\n\n"
                f"Current balance: <b>{bal(uid):.2f} USDT</b>\n"
                f"Total earned:    <b>{bal(uid) + Decimal('5.20'):.2f} USDT</b>\n"
                f"Total withdrawn: <b>5.20 USDT</b>"
            )

        elif action == "add":
            text = (
                "➕ <b>Add Funds</b>\n\n"
                "Top up your internal balance with USDT.\n\n"
                "Min. amount: <b>5.00 USDT</b>\n"
                "Network: TRC-20 (Tron)\n\n"
                "<i>Funds appear instantly after blockchain confirmation.</i>"
            )

        elif action == "history":
            tx_lines = "\n".join(
                f"• {note}  <b>+{amt:.2f} USDT</b>"
                for _, note, amt in _txs.get(uid, [])
            ) or "<i>No transactions yet.</i>"
            text = f"📊 <b>Balance History</b>\n\n{tx_lines}"

        elif action == "withdraw":
            text = (
                f"💸 <b>Withdraw Balance</b>\n\n"
                f"Available: <b>{bal(uid):.2f} USDT</b>\n"
                f"Minimum: <b>5.00 USDT</b>\n\n"
                f"<i>Processed via NowPayments. Arrives in ~5 minutes.</i>"
            )

        elif action == "summary":
            total_in  = sum(amt for _, _, amt in _txs.get(uid, []))
            n_txs = len(_txs.get(uid, []))
            text = (
                f"📈 <b>Balance Summary</b>\n\n"
                f"Total credited: <b>{total_in:.2f} USDT</b>\n"
                f"Transactions:   <b>{n_txs}</b>\n"
                f"Withdrawals:    <b>1</b>  (5.20 USDT)\n"
                f"Net balance:    <b>{bal(uid):.2f} USDT</b>\n\n"
                f"<i>All figures are live demo values that grow with each referral.</i>"
            )
        else:
            text = MODULES[prefix]["text"]

    else:
        text = MODULES[prefix]["text"]

    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=_back_kb(prefix)
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
