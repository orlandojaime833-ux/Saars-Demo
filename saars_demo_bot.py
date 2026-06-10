# saars_demo_bot.py — arquivo único, sem dependências externas além de python-telegram-bot
# Deploy: Render Web Service
# Build Command:  pip install python-telegram-bot==21.*
# Start Command:  python saars_demo_bot.py

from __future__ import annotations
import asyncio, logging, threading, http.server, os
from decimal import Decimal
from urllib.parse import quote
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN           = os.environ["BOT_TOKEN"]
REFERRAL_REWARD = Decimal("1.00")

_bal:   dict[int, Decimal] = {}
_txs:   dict[int, list]    = {}
_refs:  dict[int, int]     = {}
_rcnt:  dict[int, int]     = {}
_rearn: dict[int, Decimal] = {}
_tdone: dict[int, set]     = {}
_twait: dict[int, int]     = {}
_purch: dict[int, set]     = {}
_uinfo: dict[int, dict]    = {}   # {uid: {username, full_name, negocio}}
_ulang: dict[int, str]     = {}
_onboard: set[int]         = set()  # uids que já completaram onboarding

# Menu Builder — 1 menu custom por user
# _umenu[uid] = {
#   "icon": "🎯", "title": "Meu Menu",
#   "buttons": [ {"id": "0001", "label": "...", "type": "link"|"text"|"submenu", "value": "...", "submenu": [...]} ]
# }
_umenu: dict[int, dict]    = {}

# ─────────────────────────────────────────────
#  Simulador de actividade em tempo real
# ─────────────────────────────────────────────

_FAKE_NAMES = [
    "Carlos Silva","Ana Ferreira","Bruno Costa","Mariana Souza","Pedro Alves",
    "Juliana Lima","Ricardo Gomes","Fernanda Rocha","Thiago Martins","Camila Dias",
    "Lucas Pereira","Beatriz Nunes","Gabriel Carvalho","Larissa Mendes","Rafael Torres",
    "Priya Sharma","Mohammed Al-Rashid","Wei Zhang","Sofia Müller","Amara Diallo",
    "Yuki Tanaka","Isabella Rossi","Alejandro García","Fatima Hassan","Kwame Osei",
]
import random, itertools
_name_cycle: dict[int, itertools.cycle] = {}
_sim_tasks: dict[int, asyncio.Task] = {}

async def _simulador(uid: int, bot):
    """Corre em background: a cada 10s injeta 1 membro + 1 compra."""
    cycle = _name_cycle.setdefault(uid, itertools.cycle(random.sample(_FAKE_NAMES, len(_FAKE_NAMES))))
    while True:
        await asyncio.sleep(10)
        if not PRODUCTS: continue
        prod = min(PRODUCTS, key=lambda p: p["price"])
        nome = next(cycle)
        fake_uid = -(abs(hash(f"{uid}:{nome}")) % 10_000_000)

        _uinfo[fake_uid]  = {"username": None, "full_name": nome, "negocio": ""}
        _rcnt[uid]        = _rcnt.get(uid, 0) + 1
        earn_ref          = REFERRAL_REWARD
        _rearn[uid]       = _rearn.get(uid, Decimal("0")) + earn_ref
        credit(uid, earn_ref, "referral", f"👥 {nome} entrou")

        receita_venda = prod["price"] * Decimal("0.30")
        credit(uid, receita_venda, "purchase", f"🛍️ {nome} comprou {prod['title'][:20]}")

        membros  = 1 + _rcnt.get(uid, 0) * 3 + len(_tdone.get(uid, set())) * 2
        b        = bal(uid)
        negocio  = _uinfo.get(uid, {}).get("negocio", "o teu bot")
        try:
            await bot.send_message(
                uid,
                f"🔔 <b>Nova venda no {negocio} Bot!</b>\n\n"
                f"👤 <b>{nome}</b> entrou pelo teu link\n"
                f"🛍️ Comprou <b>{prod['title'][:30]}</b>\n"
                f"💰 <b>+{earn_ref + receita_venda:.2f} USDT</b> na tua carteira\n\n"
                f"👥 Membros activos: <b>{membros}</b>\n"
                f"💼 Saldo total: <b>{b:.2f} USDT</b>\n\n"
                f"<i>Enquanto lias esta mensagem, o bot trabalhou por ti.</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 Ver o meu painel", callback_data="demo:main")],
                    [InlineKeyboardButton("🚀 Quero o bot real →", url="https://t.me/SAARS_vBOT")],
                ])
            )
        except Exception:
            pass

def _start_sim(uid: int, bot):
    if uid in _sim_tasks and not _sim_tasks[uid].done():
        _sim_tasks[uid].cancel()
    _sim_tasks[uid] = asyncio.create_task(_simulador(uid, bot))

# ─────────────────────────────────────────────
#  N18N — 10 idiomas
# ─────────────────────────────────────────────

STRINGS: dict[str, dict[str, str]] = {

    # ── Portuguese ──────────────────────────────
    "pt": {
        "lang_name": "🇧🇷 Português",
        "welcome": (
            "💸 <b>O teu bot acabou de ganhar dinheiro.</b>\n\n"
            "Enquanto estavas a ler esta frase, <b>3 pessoas</b> entraram no teu canal "
            "e uma comprou o teu produto.\n\n"
            "Bem-vindo ao <b>SAARS Demo</b> — o bot que trabalha enquanto dormes.\n\n"
            "👇 Abre o painel e vê por ti mesmo:"
        ),
        "open_demo": "🚀 Abrir o meu painel",
        "main_title": "🚀 <b>SAARS — Demo Interativo</b>\n\nTesta todos os módulos em tempo real.",
        "balance_line": "💰 Teu saldo: <b>{bal} USDT</b>",
        "choose_section": "👇 Escolhe uma secção:",
        "btn_store": "🛍️ Loja", "btn_tasks": "📋 Tarefas", "btn_ref": "👥 Referral",
        "btn_balance": "💰 Meu Saldo", "btn_guard": "🔒 Canal Guard", "btn_wallets": "💳 Carteiras",
        "btn_about": "ℹ️ Como funciona", "btn_close": "⏸️ Pausar demo", "btn_menu": "🔙 Menu",
        "btn_back_store": "🔙 Loja", "btn_back_tasks": "🔙 Tarefas", "btn_back_ref": "🔙 Referral",
        "btn_ranking": "🏆 Ranking ao vivo", "btn_reopen": "🚀 Reabrir", "btn_home": "🏠 Menu Demo",
        "btn_tasks_go": "📋 Ganhar com Tarefas",
        "btn_buy_bal": "⚡ Comprar agora ({bal} USDT disponível)",
        "btn_buy_crypto": "💳 Pagar com crypto",
        "btn_paid": "✅ Já enviei o pagamento",
        "btn_delivery": "📦 Aceder ao produto", "btn_verify": "✅ Sou membro — verificar",
        "btn_saldo_tasks": "📋 Ganhar mais", "btn_saldo_ref": "👥 Convidar e ganhar",
        "about_text": (
            "🤖 <b>SAARS — o teu negócio digital no automático.</b>\n\n"
            "Enquanto trabalhas, dormes ou estás de férias — o bot vende, entrega e paga.\n\n"
            "<b>O que está incluído:</b>\n"
            "• 🛍️ Loja com entrega automática de produtos digitais\n"
            "• 📋 Tarefas pagas que fazem crescer a tua audiência\n"
            "• 👥 Referral viral — os teus membros trazem mais membros\n"
            "• 💰 Carteira interna em USDT — saques a qualquer hora\n"
            "• 🔒 Canal Guard — só membros pagantes acedem\n"
            "• 💳 Crypto nativa: TON · TRC20 · BEP20 · SOL\n"
            "• 🌐 10 idiomas automáticos — cresce globalmente\n\n"
            "<b>Plano Pro: $20/mês.</b> Sem taxa de activação.\n"
            "<i>Cancelas quando quiseres. A maioria não cancela.</i>"
        ),
        "closed": "⏸️ Demo pausado. /start para voltar.",
        "store_title": (
            "🛍️ <b>Loja — produtos a vender por ti</b>\n\n"
            "💰 Saldo actual: <b>{bal} USDT</b>\n\n"
            "Cada produto abaixo pode ser vendido ilimitadas vezes.\n"
            "Entrega automática. Zero esforço teu."
        ),
        "already_bought": "✅ Já tens acesso a este produto.",
        "insufficient": (
            "❌ <b>Saldo insuficiente para esta compra.</b>\n\n"
            "Precisas de <b>{price} USDT</b>.\n\n"
            "💡 Completa uma tarefa agora e o saldo aparece em segundos."
        ),
        "purchase_ok": "✅ <b>Compra confirmada!</b>\n\n{delivery}",
        "crypto_pay": (
            "💳 <b>Pagamento Crypto</b>\n\n"
            "Produto: <b>{title}</b>\n"
            "Valor: <b>{price} USDT</b>\n\n"
            "{wallets}\n\n"
            "⚡ <i>Após enviar, clica no botão abaixo — a entrega é imediata.</i>"
        ),
        "confirmed": "✅ <b>Pagamento confirmado!</b>\n<i>[Demo: aprovação automática]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>O teu acesso</b>\n\n{delivery}",
        "tasks_title": (
            "📋 <b>Tarefas — ganha USDT agora</b>\n\n"
            "💰 Saldo: <b>{bal} USDT</b>\n\n"
            "Completa qualquer tarefa abaixo e o USDT é creditado na hora.\n"
            "Sem espera. Sem aprovação manual."
        ),
        "task_done_mark": "✅ ",
        "task_done": (
            "⚡ <b>USDT creditado!</b>\n\n"
            "+<b>{reward} USDT</b> na tua carteira\n"
            "Saldo actual: <b>{bal} USDT</b>\n\n"
            "<i>No bot real, cada um dos teus membros faz isto — "
            "e tu ganhas automaticamente.</i>"
        ),
        "task_already": "✅ Tarefa já concluída.",
        "proof_wait": "📤 <b>Envia o comprovante</b>\n\nUma foto ou ficheiro — aprovação em segundos.",
        "proof_cancel": "❌ Cancelar",
        "proof_ok": (
            "✅ <b>Comprovante aprovado!</b>\n\n"
            "+<b>{reward} USDT</b> creditados\n"
            "Saldo: <b>{bal} USDT</b>"
        ),
        "ref_title": (
            "👥 <b>Referral — o teu exército de vendedores</b>\n\n"
            "🔗 Teu link de convite:\n<code>{link}</code>\n\n"
            "👤 Membros convidados: <b>{cnt}</b>\n"
            "💰 Ganhos de referral: <b>{earn} USDT</b>\n"
            "🎁 Por cada convite: <b>{reward} USDT</b>\n\n"
            "<i>Cada pessoa que convidares vai convidar outras.\n"
            "O crescimento torna-se exponencial.</i>"
        ),
        "ranking_empty": (
            "🏆 <b>Ranking ao Vivo</b>\n\n"
            "O ranking fica visível para todos os membros.\n"
            "<i>No bot real, isto cria competição saudável — "
            "os membros indicam mais para subir no ranking.</i>"
        ),
        "ranking_title": "🏆 <b>Top Indicadores</b>\n",
        "ranking_line": "{medal} {name} — {cnt} membros · {earn} USDT",
        "new_ref": (
            "🎉 <b>Novo membro no teu bot!</b>\n\n"
            "<b>{name}</b> acaba de entrar pelo teu link.\n"
            "💰 +<b>{reward} USDT</b> creditados automaticamente."
        ),
        "balance_title": (
            "💰 <b>A tua carteira SAARS</b>\n\n"
            "Saldo disponível: <b>{bal} USDT</b>\n\n"
            "Ganhas cada vez que:\n"
            "• Um membro completa uma tarefa\n"
            "• Alguém compra um produto\n"
            "• Um convidado teu entra no bot"
        ),
        "tx_header": "\n\n📜 <b>Últimas transações:</b>\n",
        "guard_title": (
            "🔒 <b>Canal Guard</b>\n\n"
            "Bloqueia o acesso ao bot até o utilizador entrar nos teus canais.\n"
            "O teu canal cresce automaticamente — sem pedir nada a ninguém.\n\n"
            "<b>Canais activos:</b>\n{channels}\n\n"
            "✅ <i>No demo o acesso é sempre concedido.</i>"
        ),
        "guard_ok": "✅ <b>Verificação concluída!</b>\n\nAcesso ao bot desbloqueado.",
        "wallets_title": "💳 <b>Carteiras de Recebimento</b>\n\n",
        "product_detail": (
            "🛍️ <b>{title}</b>\n\n"
            "{desc}\n\n"
            "💲 <b>{price} USDT</b>\n"
            "💰 Teu saldo: <b>{bal} USDT</b>"
        ),
        "product_owned": "\n\n✅ <b>Já tens acesso</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Recompensa: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Concluída!</b>",
        "btn_submit_task": "⚡ Concluir e receber agora",
        "btn_send_proof": "📤 Enviar comprovante",
        "lang_select": "🌐 <b>Idioma / Language</b>\n\nEscolhe o teu idioma:",
        "lang_set": "✅ Idioma: {lang}",
        "btn_lang": "🌐 Idioma",
        "btn_menubuilder": "🎛️ Menu Builder",
        "mb_intro": (
            "🎛️ <b>Menu Builder</b>\n\n"
            "Cria o menu personalizado do teu bot — com o teu ícone, título e botões.\n\n"
            "<i>É exatamente isto que os teus clientes vão ver quando abrirem o teu bot.</i>"
        ),
        "mb_empty": "Ainda não criaste o teu menu.",
        "mb_preview_title": "👁️ <b>Pré-visualização do teu menu:</b>",
        "mb_btn_create": "✨ Criar o meu menu",
        "mb_btn_edit": "✏️ Editar menu",
        "mb_btn_preview": "👁️ Pré-visualizar",
        "mb_btn_open": "▶️ Abrir o meu menu",
        "mb_btn_delete": "🗑️ Apagar menu",
        "mb_btn_addbtn": "➕ Adicionar botão",
        "mb_btn_editicon": "🎨 Mudar ícone/título",
        "mb_step_icon": "🎨 <b>Passo 1/2 — Identidade do menu</b>\n\nEnvia um <b>emoji</b> para representar o teu menu (ex: 🎯, 🚀, 💼):",
        "mb_step_title": "🎨 <b>Passo 2/2 — Título do menu</b>\n\nEmoji: {icon}\n\nAgora envia o <b>título do menu</b> (ex: <i>Painel Premium</i>):",
        "mb_created": "✅ <b>Menu criado!</b>\n\n{icon} <b>{title}</b>\n\nAgora adiciona botões para o teu menu ganhar vida.",
        "mb_btn_step_label": "🔘 <b>Novo botão — 1/3</b>\n\nEnvia o <b>texto do botão</b> (ex: <i>📦 Os meus produtos</i>):",
        "mb_btn_step_type": "🔘 <b>Novo botão — 2/3</b>\n\nTexto: <i>{label}</i>\n\nQue tipo de ação este botão vai ter?",
        "mb_btn_type_link": "🔗 Abrir link externo",
        "mb_btn_type_text": "💬 Mostrar mensagem",
        "mb_btn_type_submenu": "📂 Abrir submenu",
        "mb_btn_step_link": "🔗 <b>Novo botão — 3/3</b>\n\nEnvia o <b>URL</b> (ex: <i>https://t.me/teucanal</i>):",
        "mb_btn_step_text": "💬 <b>Novo botão — 3/3</b>\n\nEnvia a <b>mensagem</b> que vai aparecer ao clicar:",
        "mb_btn_step_submenu_title": "📂 <b>Novo botão — 3/3</b>\n\nEnvia o <b>título do submenu</b> (ex: <i>Mais opções</i>):",
        "mb_btn_added": "✅ <b>Botão adicionado!</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ Botão removido.",
        "mb_deleted": "🗑️ <b>Menu apagado.</b>\n\nPodes criar um novo a qualquer momento.",
        "mb_max_buttons": "⚠️ Limite de 8 botões atingido neste demo.",
        "mb_no_buttons": "<i>Nenhum botão ainda. Adiciona o primeiro!</i>",
        "mb_open_empty": "🎛️ <b>O teu menu está vazio.</b>\n\nVai a 🎛️ Menu Builder e adiciona botões.",
        "mb_back_to_menu": "🔙 Voltar",
        "mb_psych": (
            "\n\n━━━━━━━━━━━━━━━━\n"
            "💡 <i>Este menu é o que define a primeira impressão do teu bot.\n"
            "Um menu bonito e claro converte mais visitantes em clientes pagantes.</i>"
        ),
    },

    # ── English ──────────────────────────────────
    "en": {
        "lang_name": "🇬🇧 English",
        "welcome": (
            "💸 <b>Your bot just made money.</b>\n\n"
            "While you were reading that sentence, <b>3 people</b> joined your channel "
            "and one bought your product.\n\n"
            "Welcome to <b>SAARS Demo</b> — the bot that works while you sleep.\n\n"
            "👇 Open your dashboard and see it yourself:"
        ),
        "open_demo": "🚀 Open my dashboard",
        "main_title": "🚀 <b>SAARS — Interactive Demo</b>\n\nTest all modules in real time.",
        "balance_line": "💰 Your balance: <b>{bal} USDT</b>",
        "choose_section": "👇 Choose a section:",
        "btn_store": "🛍️ Store", "btn_tasks": "📋 Tasks", "btn_ref": "👥 Referral",
        "btn_balance": "💰 My Balance", "btn_guard": "🔒 Channel Guard", "btn_wallets": "💳 Wallets",
        "btn_about": "ℹ️ How it works", "btn_close": "⏸️ Pause demo", "btn_menu": "🔙 Menu",
        "btn_back_store": "🔙 Store", "btn_back_tasks": "🔙 Tasks", "btn_back_ref": "🔙 Referral",
        "btn_ranking": "🏆 Live Ranking", "btn_reopen": "🚀 Reopen", "btn_home": "🏠 Demo Menu",
        "btn_tasks_go": "📋 Earn with Tasks",
        "btn_buy_bal": "⚡ Buy now ({bal} USDT available)",
        "btn_buy_crypto": "💳 Pay with crypto",
        "btn_paid": "✅ I already sent the payment",
        "btn_delivery": "📦 Access product", "btn_verify": "✅ I'm a member — verify",
        "btn_saldo_tasks": "📋 Earn more", "btn_saldo_ref": "👥 Invite and earn",
        "about_text": (
            "🤖 <b>SAARS — your digital business on autopilot.</b>\n\n"
            "While you work, sleep or take a vacation — the bot sells, delivers and pays.\n\n"
            "<b>What's included:</b>\n"
            "• 🛍️ Store with automatic digital product delivery\n"
            "• 📋 Paid tasks that grow your audience\n"
            "• 👥 Viral referral — your members bring more members\n"
            "• 💰 Internal USDT wallet — withdraw anytime\n"
            "• 🔒 Channel Guard — only paying members get access\n"
            "• 💳 Native crypto: TON · TRC20 · BEP20 · SOL\n"
            "• 🌐 10 automatic languages — grow globally\n\n"
            "<b>Pro Plan: $20/month.</b> No setup fee.\n"
            "<i>Cancel anytime. Most don't.</i>"
        ),
        "closed": "⏸️ Demo paused. /start to return.",
        "store_title": (
            "🛍️ <b>Store — products selling for you</b>\n\n"
            "💰 Current balance: <b>{bal} USDT</b>\n\n"
            "Each product below can be sold unlimited times.\n"
            "Automatic delivery. Zero effort from you."
        ),
        "already_bought": "✅ You already have access to this product.",
        "insufficient": (
            "❌ <b>Insufficient balance for this purchase.</b>\n\n"
            "You need <b>{price} USDT</b>.\n\n"
            "💡 Complete a task now and the balance appears in seconds."
        ),
        "purchase_ok": "✅ <b>Purchase confirmed!</b>\n\n{delivery}",
        "crypto_pay": (
            "💳 <b>Crypto Payment</b>\n\n"
            "Product: <b>{title}</b>\n"
            "Amount: <b>{price} USDT</b>\n\n"
            "{wallets}\n\n"
            "⚡ <i>After sending, click the button below — delivery is instant.</i>"
        ),
        "confirmed": "✅ <b>Payment confirmed!</b>\n<i>[Demo: automatic approval]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Your access</b>\n\n{delivery}",
        "tasks_title": (
            "📋 <b>Tasks — earn USDT right now</b>\n\n"
            "💰 Balance: <b>{bal} USDT</b>\n\n"
            "Complete any task below and USDT is credited instantly.\n"
            "No waiting. No manual approval."
        ),
        "task_done_mark": "✅ ",
        "task_done": (
            "⚡ <b>USDT credited!</b>\n\n"
            "+<b>{reward} USDT</b> in your wallet\n"
            "Current balance: <b>{bal} USDT</b>\n\n"
            "<i>In the real bot, each of your members does this — "
            "and you earn automatically.</i>"
        ),
        "task_already": "✅ Task already completed.",
        "proof_wait": "📤 <b>Send your proof</b>\n\nA photo or file — approved in seconds.",
        "proof_cancel": "❌ Cancel",
        "proof_ok": (
            "✅ <b>Proof approved!</b>\n\n"
            "+<b>{reward} USDT</b> credited\n"
            "Balance: <b>{bal} USDT</b>"
        ),
        "ref_title": (
            "👥 <b>Referral — your army of salespeople</b>\n\n"
            "🔗 Your invite link:\n<code>{link}</code>\n\n"
            "👤 Members invited: <b>{cnt}</b>\n"
            "💰 Referral earnings: <b>{earn} USDT</b>\n"
            "🎁 Per invite: <b>{reward} USDT</b>\n\n"
            "<i>Every person you invite will invite others.\n"
            "Growth becomes exponential.</i>"
        ),
        "ranking_empty": (
            "🏆 <b>Live Ranking</b>\n\n"
            "The ranking is visible to all members.\n"
            "<i>In the real bot, this creates healthy competition — "
            "members refer more to climb the ranking.</i>"
        ),
        "ranking_title": "🏆 <b>Top Referrers</b>\n",
        "ranking_line": "{medal} {name} — {cnt} members · {earn} USDT",
        "new_ref": (
            "🎉 <b>New member in your bot!</b>\n\n"
            "<b>{name}</b> just joined via your link.\n"
            "💰 +<b>{reward} USDT</b> credited automatically."
        ),
        "balance_title": (
            "💰 <b>Your SAARS wallet</b>\n\n"
            "Available balance: <b>{bal} USDT</b>\n\n"
            "You earn every time:\n"
            "• A member completes a task\n"
            "• Someone buys a product\n"
            "• One of your referrals joins the bot"
        ),
        "tx_header": "\n\n📜 <b>Recent transactions:</b>\n",
        "guard_title": (
            "🔒 <b>Channel Guard</b>\n\n"
            "Blocks bot access until the user joins your channels.\n"
            "Your channel grows automatically — without asking anyone.\n\n"
            "<b>Active channels:</b>\n{channels}\n\n"
            "✅ <i>In demo access is always granted.</i>"
        ),
        "guard_ok": "✅ <b>Verification complete!</b>\n\nBot access unlocked.",
        "wallets_title": "💳 <b>Receiving Wallets</b>\n\n",
        "product_detail": (
            "🛍️ <b>{title}</b>\n\n"
            "{desc}\n\n"
            "💲 <b>{price} USDT</b>\n"
            "💰 Your balance: <b>{bal} USDT</b>"
        ),
        "product_owned": "\n\n✅ <b>You already have access</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Reward: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Completed!</b>",
        "btn_submit_task": "⚡ Complete and earn now",
        "btn_send_proof": "📤 Send proof",
        "lang_select": "🌐 <b>Language</b>\n\nChoose your language:",
        "lang_set": "✅ Language: {lang}",
        "btn_lang": "🌐 Language",
        "btn_menubuilder": "🎛️ Menu Builder",
        "mb_intro": (
            "🎛️ <b>Menu Builder</b>\n\n"
            "Create your bot's custom menu — with your own icon, title and buttons.\n\n"
            "<i>This is exactly what your customers will see when they open your bot.</i>"
        ),
        "mb_empty": "You haven't created your menu yet.",
        "mb_preview_title": "👁️ <b>Preview of your menu:</b>",
        "mb_btn_create": "✨ Create my menu",
        "mb_btn_edit": "✏️ Edit menu",
        "mb_btn_preview": "👁️ Preview",
        "mb_btn_open": "▶️ Open my menu",
        "mb_btn_delete": "🗑️ Delete menu",
        "mb_btn_addbtn": "➕ Add button",
        "mb_btn_editicon": "🎨 Change icon/title",
        "mb_step_icon": "🎨 <b>Step 1/2 — Menu identity</b>\n\nSend an <b>emoji</b> to represent your menu (e.g. 🎯, 🚀, 💼):",
        "mb_step_title": "🎨 <b>Step 2/2 — Menu title</b>\n\nEmoji: {icon}\n\nNow send the <b>menu title</b> (e.g. <i>Premium Panel</i>):",
        "mb_created": "✅ <b>Menu created!</b>\n\n{icon} <b>{title}</b>\n\nNow add buttons to bring your menu to life.",
        "mb_btn_step_label": "🔘 <b>New button — 1/3</b>\n\nSend the <b>button text</b> (e.g. <i>📦 My products</i>):",
        "mb_btn_step_type": "🔘 <b>New button — 2/3</b>\n\nText: <i>{label}</i>\n\nWhat action should this button have?",
        "mb_btn_type_link": "🔗 Open external link",
        "mb_btn_type_text": "💬 Show message",
        "mb_btn_type_submenu": "📂 Open submenu",
        "mb_btn_step_link": "🔗 <b>New button — 3/3</b>\n\nSend the <b>URL</b> (e.g. <i>https://t.me/yourchannel</i>):",
        "mb_btn_step_text": "💬 <b>New button — 3/3</b>\n\nSend the <b>message</b> shown when clicked:",
        "mb_btn_step_submenu_title": "📂 <b>New button — 3/3</b>\n\nSend the <b>submenu title</b> (e.g. <i>More options</i>):",
        "mb_btn_added": "✅ <b>Button added!</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ Button removed.",
        "mb_deleted": "🗑️ <b>Menu deleted.</b>\n\nYou can create a new one anytime.",
        "mb_max_buttons": "⚠️ Limit of 8 buttons reached in this demo.",
        "mb_no_buttons": "<i>No buttons yet. Add your first one!</i>",
        "mb_open_empty": "🎛️ <b>Your menu is empty.</b>\n\nGo to 🎛️ Menu Builder and add buttons.",
        "mb_back_to_menu": "🔙 Back",
        "mb_psych": (
            "\n\n━━━━━━━━━━━━━━━━\n"
            "💡 <i>This menu defines your bot's first impression.\n"
            "A clear, beautiful menu converts more visitors into paying customers.</i>"
        ),
    },

    # ── Spanish ──────────────────────────────────
    "es": {
        "lang_name": "🇪🇸 Español",
        "welcome": (
            "💸 <b>Tu bot acaba de ganar dinero.</b>\n\n"
            "Mientras leías esa frase, <b>3 personas</b> entraron a tu canal "
            "y una compró tu producto.\n\n"
            "Bienvenido al <b>SAARS Demo</b> — el bot que trabaja mientras duermes.\n\n"
            "👇 Abre tu panel y compruébalo tú mismo:"
        ),
        "open_demo": "🚀 Abrir mi panel",
        "main_title": "🚀 <b>SAARS — Demo Interactivo</b>\n\nPrueba todos los módulos en tiempo real.",
        "balance_line": "💰 Tu saldo: <b>{bal} USDT</b>",
        "choose_section": "👇 Elige una sección:",
        "btn_store": "🛍️ Tienda", "btn_tasks": "📋 Tareas", "btn_ref": "👥 Referral",
        "btn_balance": "💰 Mi Saldo", "btn_guard": "🔒 Canal Guard", "btn_wallets": "💳 Carteras",
        "btn_about": "ℹ️ Cómo funciona", "btn_close": "⏸️ Pausar demo", "btn_menu": "🔙 Menú",
        "btn_back_store": "🔙 Tienda", "btn_back_tasks": "🔙 Tareas", "btn_back_ref": "🔙 Referral",
        "btn_ranking": "🏆 Ranking en vivo", "btn_reopen": "🚀 Reabrir", "btn_home": "🏠 Menú Demo",
        "btn_tasks_go": "📋 Ganar con Tareas",
        "btn_buy_bal": "⚡ Comprar ahora ({bal} USDT disponible)",
        "btn_buy_crypto": "💳 Pagar con crypto",
        "btn_paid": "✅ Ya envié el pago",
        "btn_delivery": "📦 Acceder al producto", "btn_verify": "✅ Soy miembro — verificar",
        "btn_saldo_tasks": "📋 Ganar más", "btn_saldo_ref": "👥 Invitar y ganar",
        "about_text": (
            "🤖 <b>SAARS — tu negocio digital en automático.</b>\n\n"
            "Mientras trabajas, duermes o estás de vacaciones — el bot vende, entrega y paga.\n\n"
            "<b>Qué incluye:</b>\n"
            "• 🛍️ Tienda con entrega automática de productos digitales\n"
            "• 📋 Tareas pagadas que hacen crecer tu audiencia\n"
            "• 👥 Referral viral — tus miembros traen más miembros\n"
            "• 💰 Cartera interna en USDT — retira cuando quieras\n"
            "• 🔒 Canal Guard — solo miembros pagos tienen acceso\n"
            "• 💳 Crypto nativa: TON · TRC20 · BEP20 · SOL\n"
            "• 🌐 10 idiomas automáticos — crece globalmente\n\n"
            "<b>Plan Pro: $20/mes.</b> Sin tarifa de activación.\n"
            "<i>Cancelas cuando quieras. La mayoría no cancela.</i>"
        ),
        "closed": "⏸️ Demo pausado. /start para volver.",
        "store_title": (
            "🛍️ <b>Tienda — productos vendiéndose por ti</b>\n\n"
            "💰 Saldo actual: <b>{bal} USDT</b>\n\n"
            "Cada producto puede venderse ilimitadas veces.\n"
            "Entrega automática. Cero esfuerzo tuyo."
        ),
        "already_bought": "✅ Ya tienes acceso a este producto.",
        "insufficient": (
            "❌ <b>Saldo insuficiente para esta compra.</b>\n\n"
            "Necesitas <b>{price} USDT</b>.\n\n"
            "💡 Completa una tarea ahora y el saldo aparece en segundos."
        ),
        "purchase_ok": "✅ <b>¡Compra confirmada!</b>\n\n{delivery}",
        "crypto_pay": (
            "💳 <b>Pago Crypto</b>\n\n"
            "Producto: <b>{title}</b>\n"
            "Valor: <b>{price} USDT</b>\n\n"
            "{wallets}\n\n"
            "⚡ <i>Tras enviar, haz clic abajo — la entrega es inmediata.</i>"
        ),
        "confirmed": "✅ <b>¡Pago confirmado!</b>\n<i>[Demo: aprobación automática]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Tu acceso</b>\n\n{delivery}",
        "tasks_title": (
            "📋 <b>Tareas — gana USDT ahora mismo</b>\n\n"
            "💰 Saldo: <b>{bal} USDT</b>\n\n"
            "Completa cualquier tarea y el USDT se acredita al instante.\n"
            "Sin espera. Sin aprobación manual."
        ),
        "task_done_mark": "✅ ",
        "task_done": (
            "⚡ <b>¡USDT acreditado!</b>\n\n"
            "+<b>{reward} USDT</b> en tu cartera\n"
            "Saldo actual: <b>{bal} USDT</b>\n\n"
            "<i>En el bot real, cada uno de tus miembros hace esto — "
            "y tú ganas automáticamente.</i>"
        ),
        "task_already": "✅ Tarea ya completada.",
        "proof_wait": "📤 <b>Envía tu comprobante</b>\n\nUna foto o archivo — aprobado en segundos.",
        "proof_cancel": "❌ Cancelar",
        "proof_ok": (
            "✅ <b>¡Comprobante aprobado!</b>\n\n"
            "+<b>{reward} USDT</b> acreditados\n"
            "Saldo: <b>{bal} USDT</b>"
        ),
        "ref_title": (
            "👥 <b>Referral — tu ejército de vendedores</b>\n\n"
            "🔗 Tu enlace de invitación:\n<code>{link}</code>\n\n"
            "👤 Miembros invitados: <b>{cnt}</b>\n"
            "💰 Ganancias de referral: <b>{earn} USDT</b>\n"
            "🎁 Por cada invitación: <b>{reward} USDT</b>\n\n"
            "<i>Cada persona que invites invitará a otras.\n"
            "El crecimiento se vuelve exponencial.</i>"
        ),
        "ranking_empty": (
            "🏆 <b>Ranking en Vivo</b>\n\n"
            "El ranking es visible para todos los miembros.\n"
            "<i>En el bot real, esto crea competencia sana — "
            "los miembros refieren más para subir en el ranking.</i>"
        ),
        "ranking_title": "🏆 <b>Top Referidores</b>\n",
        "ranking_line": "{medal} {name} — {cnt} miembros · {earn} USDT",
        "new_ref": (
            "🎉 <b>¡Nuevo miembro en tu bot!</b>\n\n"
            "<b>{name}</b> acaba de unirse por tu enlace.\n"
            "💰 +<b>{reward} USDT</b> acreditados automáticamente."
        ),
        "balance_title": (
            "💰 <b>Tu cartera SAARS</b>\n\n"
            "Saldo disponible: <b>{bal} USDT</b>\n\n"
            "Ganas cada vez que:\n"
            "• Un miembro completa una tarea\n"
            "• Alguien compra un producto\n"
            "• Uno de tus referidos entra al bot"
        ),
        "tx_header": "\n\n📜 <b>Últimas transacciones:</b>\n",
        "guard_title": (
            "🔒 <b>Canal Guard</b>\n\n"
            "Bloquea el acceso al bot hasta que el usuario entre en tus canales.\n"
            "Tu canal crece automáticamente — sin pedirle nada a nadie.\n\n"
            "<b>Canales activos:</b>\n{channels}\n\n"
            "✅ <i>En el demo el acceso siempre se concede.</i>"
        ),
        "guard_ok": "✅ <b>¡Verificación completada!</b>\n\nAcceso al bot desbloqueado.",
        "wallets_title": "💳 <b>Carteras de Recepción</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Tu saldo: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Ya tienes acceso</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Recompensa: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>¡Completada!</b>",
        "btn_submit_task": "⚡ Completar y cobrar ahora",
        "btn_send_proof": "📤 Enviar comprobante",
        "lang_select": "🌐 <b>Idioma / Language</b>\n\nElige tu idioma:",
        "lang_set": "✅ Idioma: {lang}",
        "btn_lang": "🌐 Idioma",
        "btn_menubuilder": "🎛️ Constructor de Menú",
        "mb_intro": "🎛️ <b>Constructor de Menú</b>\n\nCrea el menú personalizado de tu bot — con tu propio ícono, título y botones.\n\n<i>Esto es exactamente lo que tus clientes verán al abrir tu bot.</i>",
        "mb_empty": "Aún no has creado tu menú.",
        "mb_preview_title": "👁️ <b>Vista previa de tu menú:</b>",
        "mb_btn_create": "✨ Crear mi menú",
        "mb_btn_edit": "✏️ Editar menú",
        "mb_btn_preview": "👁️ Vista previa",
        "mb_btn_open": "▶️ Abrir mi menú",
        "mb_btn_delete": "🗑️ Borrar menú",
        "mb_btn_addbtn": "➕ Añadir botón",
        "mb_btn_editicon": "🎨 Cambiar ícono/título",
        "mb_step_icon": "🎨 <b>Paso 1/2 — Identidad del menú</b>\n\nEnvía un <b>emoji</b> para representar tu menú (ej: 🎯, 🚀, 💼):",
        "mb_step_title": "🎨 <b>Paso 2/2 — Título del menú</b>\n\nEmoji: {icon}\n\nAhora envía el <b>título del menú</b> (ej: <i>Panel Premium</i>):",
        "mb_created": "✅ <b>¡Menú creado!</b>\n\n{icon} <b>{title}</b>\n\nAhora añade botones para darle vida a tu menú.",
        "mb_btn_step_label": "🔘 <b>Nuevo botón — 1/3</b>\n\nEnvía el <b>texto del botón</b> (ej: <i>📦 Mis productos</i>):",
        "mb_btn_step_type": "🔘 <b>Nuevo botón — 2/3</b>\n\nTexto: <i>{label}</i>\n\n¿Qué acción tendrá este botón?",
        "mb_btn_type_link": "🔗 Abrir enlace externo",
        "mb_btn_type_text": "💬 Mostrar mensaje",
        "mb_btn_type_submenu": "📂 Abrir submenú",
        "mb_btn_step_link": "🔗 <b>Nuevo botón — 3/3</b>\n\nEnvía la <b>URL</b> (ej: <i>https://t.me/tucanal</i>):",
        "mb_btn_step_text": "💬 <b>Nuevo botón — 3/3</b>\n\nEnvía el <b>mensaje</b> que aparecerá al hacer clic:",
        "mb_btn_step_submenu_title": "📂 <b>Nuevo botón — 3/3</b>\n\nEnvía el <b>título del submenú</b> (ej: <i>Más opciones</i>):",
        "mb_btn_added": "✅ <b>¡Botón añadido!</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ Botón eliminado.",
        "mb_deleted": "🗑️ <b>Menú eliminado.</b>\n\nPuedes crear uno nuevo cuando quieras.",
        "mb_max_buttons": "⚠️ Límite de 8 botones alcanzado en este demo.",
        "mb_no_buttons": "<i>Aún no hay botones. ¡Añade el primero!</i>",
        "mb_open_empty": "🎛️ <b>Tu menú está vacío.</b>\n\nVe a 🎛️ Constructor de Menú y añade botones.",
        "mb_back_to_menu": "🔙 Volver",
        "mb_psych": "\n\n━━━━━━━━━━━━━━━━\n💡 <i>Este menú define la primera impresión de tu bot.\nUn menú claro y atractivo convierte más visitantes en clientes pagos.</i>",
    },

    # ── French ───────────────────────────────────
    "fr": {
        "lang_name": "🇫🇷 Français",
        "welcome": (
            "💸 <b>Ton bot vient de gagner de l'argent.</b>\n\n"
            "Pendant que tu lisais cette phrase, <b>3 personnes</b> ont rejoint ton canal "
            "et une a acheté ton produit.\n\n"
            "Bienvenue sur <b>SAARS Demo</b> — le bot qui travaille pendant que tu dors.\n\n"
            "👇 Ouvre ton tableau de bord et vois par toi-même :"
        ),
        "open_demo": "🚀 Ouvrir mon tableau de bord",
        "main_title": "🚀 <b>SAARS — Démo Interactive</b>\n\nTestez tous les modules en temps réel.",
        "balance_line": "💰 Ton solde : <b>{bal} USDT</b>",
        "choose_section": "👇 Choisis une section :",
        "btn_store": "🛍️ Boutique", "btn_tasks": "📋 Tâches", "btn_ref": "👥 Parrainage",
        "btn_balance": "💰 Mon Solde", "btn_guard": "🔒 Garde Canal", "btn_wallets": "💳 Portefeuilles",
        "btn_about": "ℹ️ Comment ça marche", "btn_close": "⏸️ Pause démo", "btn_menu": "🔙 Menu",
        "btn_back_store": "🔙 Boutique", "btn_back_tasks": "🔙 Tâches", "btn_back_ref": "🔙 Parrainage",
        "btn_ranking": "🏆 Classement live", "btn_reopen": "🚀 Rouvrir", "btn_home": "🏠 Menu Démo",
        "btn_tasks_go": "📋 Gagner avec les Tâches",
        "btn_buy_bal": "⚡ Acheter maintenant ({bal} USDT disponible)",
        "btn_buy_crypto": "💳 Payer en crypto",
        "btn_paid": "✅ J'ai déjà envoyé le paiement",
        "btn_delivery": "📦 Accéder au produit", "btn_verify": "✅ Je suis membre — vérifier",
        "btn_saldo_tasks": "📋 Gagner plus", "btn_saldo_ref": "👥 Inviter et gagner",
        "about_text": (
            "🤖 <b>SAARS — ton business digital en automatique.</b>\n\n"
            "Pendant que tu travailles, dors ou es en vacances — le bot vend, livre et paie.\n\n"
            "<b>Ce qui est inclus :</b>\n"
            "• 🛍️ Boutique avec livraison automatique de produits numériques\n"
            "• 📋 Tâches payées qui font croître ton audience\n"
            "• 👥 Parrainage viral — tes membres amènent plus de membres\n"
            "• 💰 Portefeuille interne USDT — retrait à tout moment\n"
            "• 🔒 Garde Canal — seuls les membres payants ont accès\n"
            "• 💳 Crypto native : TON · TRC20 · BEP20 · SOL\n"
            "• 🌐 10 langues automatiques — croissance mondiale\n\n"
            "<b>Plan Pro : 20$/mois.</b> Sans frais d'activation.\n"
            "<i>Résiliation possible à tout moment. La plupart ne résilie pas.</i>"
        ),
        "closed": "⏸️ Démo en pause. /start pour revenir.",
        "store_title": "🛍️ <b>Boutique — produits vendus pour toi</b>\n\n💰 Solde : <b>{bal} USDT</b>\n\nChaque produit peut être vendu à l'infini.\nLivraison automatique. Zéro effort de ta part.",
        "already_bought": "✅ Tu as déjà accès à ce produit.",
        "insufficient": "❌ <b>Solde insuffisant.</b>\n\nTu as besoin de <b>{price} USDT</b>.\n\n💡 Complète une tâche maintenant.",
        "purchase_ok": "✅ <b>Achat confirmé !</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Paiement Crypto</b>\n\nProduit : <b>{title}</b>\nMontant : <b>{price} USDT</b>\n\n{wallets}\n\n⚡ <i>Après l'envoi, clique ci-dessous — livraison immédiate.</i>",
        "confirmed": "✅ <b>Paiement confirmé !</b>\n<i>[Démo : approbation automatique]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Ton accès</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Tâches — gagne des USDT maintenant</b>\n\n💰 Solde : <b>{bal} USDT</b>\n\nComplète n'importe quelle tâche et l'USDT est crédité instantanément.",
        "task_done_mark": "✅ ",
        "task_done": "⚡ <b>USDT crédité !</b>\n\n+<b>{reward} USDT</b> dans ton portefeuille\nSolde : <b>{bal} USDT</b>\n\n<i>Dans le bot réel, chacun de tes membres fait ça — et tu gagnes automatiquement.</i>",
        "task_already": "✅ Tâche déjà accomplie.",
        "proof_wait": "📤 <b>Envoie ta preuve</b>\n\nUne photo ou un fichier — approuvé en secondes.",
        "proof_cancel": "❌ Annuler",
        "proof_ok": "✅ <b>Preuve approuvée !</b>\n\n+<b>{reward} USDT</b> crédités\nSolde : <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Parrainage — ton armée de vendeurs</b>\n\n🔗 Ton lien :\n<code>{link}</code>\n\n👤 Membres invités : <b>{cnt}</b>\n💰 Gains : <b>{earn} USDT</b>\n🎁 Par invitation : <b>{reward} USDT</b>\n\n<i>Chaque personne invitée en invite d'autres.\nLa croissance devient exponentielle.</i>",
        "ranking_empty": "🏆 <b>Classement Live</b>\n\nVisible par tous les membres.\n<i>Dans le bot réel, ça crée une saine compétition.</i>",
        "ranking_title": "🏆 <b>Top Parrains</b>\n",
        "ranking_line": "{medal} {name} — {cnt} membres · {earn} USDT",
        "new_ref": "🎉 <b>Nouveau membre dans ton bot !</b>\n\n<b>{name}</b> vient de rejoindre via ton lien.\n💰 +<b>{reward} USDT</b> crédités automatiquement.",
        "balance_title": "💰 <b>Ton portefeuille SAARS</b>\n\nSolde disponible : <b>{bal} USDT</b>\n\nTu gagnes à chaque fois que :\n• Un membre accomplit une tâche\n• Quelqu'un achète un produit\n• Un de tes filleuls rejoint le bot",
        "tx_header": "\n\n📜 <b>Dernières transactions :</b>\n",
        "guard_title": "🔒 <b>Garde Canal</b>\n\nBloque l'accès jusqu'à ce que l'utilisateur rejoigne tes canaux.\n\n<b>Canaux actifs :</b>\n{channels}\n\n✅ <i>En démo, l'accès est toujours accordé.</i>",
        "guard_ok": "✅ <b>Vérification terminée !</b>\n\nAccès au bot débloqué.",
        "wallets_title": "💳 <b>Portefeuilles de réception</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Ton solde : <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Accès déjà obtenu</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Récompense : <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Accomplie !</b>",
        "btn_submit_task": "⚡ Accomplir et recevoir maintenant",
        "btn_send_proof": "📤 Envoyer la preuve",
        "lang_select": "🌐 <b>Langue / Language</b>\n\nChoisis ta langue :",
        "lang_set": "✅ Langue : {lang}",
        "btn_lang": "🌐 Langue",
        "btn_menubuilder": "🎛️ Constructeur de Menu",
        "mb_intro": "🎛️ <b>Constructeur de Menu</b>\n\nCrée le menu personnalisé de ton bot — avec ton icône, ton titre et tes boutons.\n\n<i>C'est exactement ce que tes clients verront en ouvrant ton bot.</i>",
        "mb_empty": "Tu n'as pas encore créé ton menu.",
        "mb_preview_title": "👁️ <b>Aperçu de ton menu :</b>",
        "mb_btn_create": "✨ Créer mon menu",
        "mb_btn_edit": "✏️ Modifier le menu",
        "mb_btn_preview": "👁️ Aperçu",
        "mb_btn_open": "▶️ Ouvrir mon menu",
        "mb_btn_delete": "🗑️ Supprimer le menu",
        "mb_btn_addbtn": "➕ Ajouter un bouton",
        "mb_btn_editicon": "🎨 Changer icône/titre",
        "mb_step_icon": "🎨 <b>Étape 1/2 — Identité du menu</b>\n\nEnvoie un <b>emoji</b> pour représenter ton menu (ex : 🎯, 🚀, 💼) :",
        "mb_step_title": "🎨 <b>Étape 2/2 — Titre du menu</b>\n\nEmoji : {icon}\n\nEnvoie maintenant le <b>titre du menu</b> (ex : <i>Panneau Premium</i>) :",
        "mb_created": "✅ <b>Menu créé !</b>\n\n{icon} <b>{title}</b>\n\nAjoute des boutons pour donner vie à ton menu.",
        "mb_btn_step_label": "🔘 <b>Nouveau bouton — 1/3</b>\n\nEnvoie le <b>texte du bouton</b> (ex : <i>📦 Mes produits</i>) :",
        "mb_btn_step_type": "🔘 <b>Nouveau bouton — 2/3</b>\n\nTexte : <i>{label}</i>\n\nQuelle action ce bouton aura-t-il ?",
        "mb_btn_type_link": "🔗 Ouvrir un lien externe",
        "mb_btn_type_text": "💬 Afficher un message",
        "mb_btn_type_submenu": "📂 Ouvrir un sous-menu",
        "mb_btn_step_link": "🔗 <b>Nouveau bouton — 3/3</b>\n\nEnvoie l'<b>URL</b> (ex : <i>https://t.me/tonchaine</i>) :",
        "mb_btn_step_text": "💬 <b>Nouveau bouton — 3/3</b>\n\nEnvoie le <b>message</b> qui s'affichera au clic :",
        "mb_btn_step_submenu_title": "📂 <b>Nouveau bouton — 3/3</b>\n\nEnvoie le <b>titre du sous-menu</b> (ex : <i>Plus d'options</i>) :",
        "mb_btn_added": "✅ <b>Bouton ajouté !</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ Bouton supprimé.",
        "mb_deleted": "🗑️ <b>Menu supprimé.</b>\n\nTu peux en créer un nouveau à tout moment.",
        "mb_max_buttons": "⚠️ Limite de 8 boutons atteinte dans cette démo.",
        "mb_no_buttons": "<i>Pas encore de boutons. Ajoute le premier !</i>",
        "mb_open_empty": "🎛️ <b>Ton menu est vide.</b>\n\nVa dans 🎛️ Constructeur de Menu et ajoute des boutons.",
        "mb_back_to_menu": "🔙 Retour",
        "mb_psych": "\n\n━━━━━━━━━━━━━━━━\n💡 <i>Ce menu définit la première impression de ton bot.\nUn menu clair et soigné convertit plus de visiteurs en clients payants.</i>",
    },

    # ── Russian ──────────────────────────────────
    "ru": {
        "lang_name": "🇷🇺 Русский",
        "welcome": (
            "💸 <b>Твой бот только что заработал деньги.</b>\n\n"
            "Пока ты читал это предложение, <b>3 человека</b> вошли в твой канал "
            "и один купил твой продукт.\n\n"
            "Добро пожаловать в <b>SAARS Demo</b> — бот, который работает пока ты спишь.\n\n"
            "👇 Открой панель и убедись сам:"
        ),
        "open_demo": "🚀 Открыть мою панель",
        "main_title": "🚀 <b>SAARS — Интерактивное демо</b>\n\nПроверьте все модули в реальном времени.",
        "balance_line": "💰 Твой баланс: <b>{bal} USDT</b>",
        "choose_section": "👇 Выбери раздел:",
        "btn_store": "🛍️ Магазин", "btn_tasks": "📋 Задания", "btn_ref": "👥 Рефералы",
        "btn_balance": "💰 Мой баланс", "btn_guard": "🔒 Охрана канала", "btn_wallets": "💳 Кошельки",
        "btn_about": "ℹ️ Как это работает", "btn_close": "⏸️ Пауза демо", "btn_menu": "🔙 Меню",
        "btn_back_store": "🔙 Магазин", "btn_back_tasks": "🔙 Задания", "btn_back_ref": "🔙 Рефералы",
        "btn_ranking": "🏆 Рейтинг онлайн", "btn_reopen": "🚀 Открыть снова", "btn_home": "🏠 Демо-меню",
        "btn_tasks_go": "📋 Зарабатывать на заданиях",
        "btn_buy_bal": "⚡ Купить сейчас ({bal} USDT доступно)",
        "btn_buy_crypto": "💳 Оплатить криптой",
        "btn_paid": "✅ Я уже отправил оплату",
        "btn_delivery": "📦 Получить продукт", "btn_verify": "✅ Я участник — проверить",
        "btn_saldo_tasks": "📋 Заработать ещё", "btn_saldo_ref": "👥 Пригласить и заработать",
        "about_text": (
            "🤖 <b>SAARS — твой цифровой бизнес на автопилоте.</b>\n\n"
            "Пока ты работаешь, спишь или отдыхаешь — бот продаёт, доставляет и платит.\n\n"
            "<b>Что включено:</b>\n"
            "• 🛍️ Магазин с автодоставкой цифровых продуктов\n"
            "• 📋 Платные задания, которые развивают аудиторию\n"
            "• 👥 Вирусный реферал — твои участники приводят больше участников\n"
            "• 💰 Внутренний кошелёк USDT — вывод в любое время\n"
            "• 🔒 Охрана канала — доступ только для платящих участников\n"
            "• 💳 Нативная крипта: TON · TRC20 · BEP20 · SOL\n"
            "• 🌐 10 автоматических языков — расти глобально\n\n"
            "<b>Pro-план: $20/мес.</b> Без платы за активацию.\n"
            "<i>Отменяй когда угодно. Большинство не отменяет.</i>"
        ),
        "closed": "⏸️ Демо на паузе. /start чтобы вернуться.",
        "store_title": "🛍️ <b>Магазин — продукты продаются за тебя</b>\n\n💰 Баланс: <b>{bal} USDT</b>\n\nКаждый продукт можно продавать бесконечно.\nАвтодоставка. Ноль усилий с твоей стороны.",
        "already_bought": "✅ У тебя уже есть доступ к этому продукту.",
        "insufficient": "❌ <b>Недостаточно средств.</b>\n\nНужно <b>{price} USDT</b>.\n\n💡 Выполни задание сейчас — баланс появится за секунды.",
        "purchase_ok": "✅ <b>Покупка подтверждена!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Оплата криптой</b>\n\nПродукт: <b>{title}</b>\nСумма: <b>{price} USDT</b>\n\n{wallets}\n\n⚡ <i>После отправки нажми кнопку — доставка мгновенная.</i>",
        "confirmed": "✅ <b>Оплата подтверждена!</b>\n<i>[Демо: автоматическое одобрение]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Твой доступ</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Задания — зарабатывай USDT прямо сейчас</b>\n\n💰 Баланс: <b>{bal} USDT</b>\n\nВыполни любое задание — USDT зачисляется мгновенно.",
        "task_done_mark": "✅ ",
        "task_done": "⚡ <b>USDT зачислен!</b>\n\n+<b>{reward} USDT</b> в кошельке\nБаланс: <b>{bal} USDT</b>\n\n<i>В реальном боте каждый твой участник делает это — и ты зарабатываешь автоматически.</i>",
        "task_already": "✅ Задание уже выполнено.",
        "proof_wait": "📤 <b>Отправь подтверждение</b>\n\nФото или файл — одобрение за секунды.",
        "proof_cancel": "❌ Отмена",
        "proof_ok": "✅ <b>Подтверждение одобрено!</b>\n\n+<b>{reward} USDT</b> зачислено\nБаланс: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Реферальная программа — твоя армия продавцов</b>\n\n🔗 Твоя ссылка:\n<code>{link}</code>\n\n👤 Приглашено участников: <b>{cnt}</b>\n💰 Реферальный заработок: <b>{earn} USDT</b>\n🎁 За приглашение: <b>{reward} USDT</b>\n\n<i>Каждый приглашённый приглашает других.\nРост становится экспоненциальным.</i>",
        "ranking_empty": "🏆 <b>Рейтинг онлайн</b>\n\nВиден всем участникам.\n<i>В реальном боте это создаёт здоровую конкуренцию.</i>",
        "ranking_title": "🏆 <b>Топ рефереров</b>\n",
        "ranking_line": "{medal} {name} — {cnt} участников · {earn} USDT",
        "new_ref": "🎉 <b>Новый участник в твоём боте!</b>\n\n<b>{name}</b> только что вошёл по твоей ссылке.\n💰 +<b>{reward} USDT</b> зачислено автоматически.",
        "balance_title": "💰 <b>Твой кошелёк SAARS</b>\n\nДоступный баланс: <b>{bal} USDT</b>\n\nТы зарабатываешь каждый раз, когда:\n• Участник выполняет задание\n• Кто-то покупает продукт\n• Один из твоих рефералов заходит в бот",
        "tx_header": "\n\n📜 <b>Последние транзакции:</b>\n",
        "guard_title": "🔒 <b>Охрана канала</b>\n\nБлокирует доступ к боту, пока пользователь не вступит в твои каналы.\n\n<b>Активные каналы:</b>\n{channels}\n\n✅ <i>В демо доступ всегда предоставляется.</i>",
        "guard_ok": "✅ <b>Проверка завершена!</b>\n\nДоступ к боту разблокирован.",
        "wallets_title": "💳 <b>Кошельки для получения платежей</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Твой баланс: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Доступ уже получен</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Награда: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Выполнено!</b>",
        "btn_submit_task": "⚡ Выполнить и получить сейчас",
        "btn_send_proof": "📤 Отправить подтверждение",
        "lang_select": "🌐 <b>Язык / Language</b>\n\nВыбери язык:",
        "lang_set": "✅ Язык: {lang}",
        "btn_lang": "🌐 Язык",
        "btn_menubuilder": "🎛️ Конструктор меню",
        "mb_intro": "🎛️ <b>Конструктор меню</b>\n\nСоздай персональное меню своего бота — со своей иконкой, заголовком и кнопками.\n\n<i>Именно это увидят твои клиенты, открыв бота.</i>",
        "mb_empty": "Ты ещё не создал своё меню.",
        "mb_preview_title": "👁️ <b>Предпросмотр твоего меню:</b>",
        "mb_btn_create": "✨ Создать моё меню",
        "mb_btn_edit": "✏️ Редактировать меню",
        "mb_btn_preview": "👁️ Предпросмотр",
        "mb_btn_open": "▶️ Открыть моё меню",
        "mb_btn_delete": "🗑️ Удалить меню",
        "mb_btn_addbtn": "➕ Добавить кнопку",
        "mb_btn_editicon": "🎨 Изменить иконку/заголовок",
        "mb_step_icon": "🎨 <b>Шаг 1/2 — Оформление меню</b>\n\nОтправь <b>эмодзи</b> для своего меню (например: 🎯, 🚀, 💼):",
        "mb_step_title": "🎨 <b>Шаг 2/2 — Заголовок меню</b>\n\nЭмодзи: {icon}\n\nТеперь отправь <b>заголовок меню</b> (например: <i>Премиум-панель</i>):",
        "mb_created": "✅ <b>Меню создано!</b>\n\n{icon} <b>{title}</b>\n\nТеперь добавь кнопки, чтобы оживить меню.",
        "mb_btn_step_label": "🔘 <b>Новая кнопка — 1/3</b>\n\nОтправь <b>текст кнопки</b> (например: <i>📦 Мои товары</i>):",
        "mb_btn_step_type": "🔘 <b>Новая кнопка — 2/3</b>\n\nТекст: <i>{label}</i>\n\nКакое действие будет у этой кнопки?",
        "mb_btn_type_link": "🔗 Открыть внешнюю ссылку",
        "mb_btn_type_text": "💬 Показать сообщение",
        "mb_btn_type_submenu": "📂 Открыть подменю",
        "mb_btn_step_link": "🔗 <b>Новая кнопка — 3/3</b>\n\nОтправь <b>URL</b> (например: <i>https://t.me/твойканал</i>):",
        "mb_btn_step_text": "💬 <b>Новая кнопка — 3/3</b>\n\nОтправь <b>сообщение</b>, которое появится при нажатии:",
        "mb_btn_step_submenu_title": "📂 <b>Новая кнопка — 3/3</b>\n\nОтправь <b>заголовок подменю</b> (например: <i>Больше опций</i>):",
        "mb_btn_added": "✅ <b>Кнопка добавлена!</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ Кнопка удалена.",
        "mb_deleted": "🗑️ <b>Меню удалено.</b>\n\nТы можешь создать новое в любой момент.",
        "mb_max_buttons": "⚠️ В этом демо достигнут лимит в 8 кнопок.",
        "mb_no_buttons": "<i>Кнопок пока нет. Добавь первую!</i>",
        "mb_open_empty": "🎛️ <b>Твоё меню пустое.</b>\n\nПерейди в 🎛️ Конструктор меню и добавь кнопки.",
        "mb_back_to_menu": "🔙 Назад",
        "mb_psych": "\n\n━━━━━━━━━━━━━━━━\n💡 <i>Это меню формирует первое впечатление о твоём боте.\nЧёткое и красивое меню превращает больше посетителей в платящих клиентов.</i>",
    },

    # ── Bengali ──────────────────────────────────
    "bn": {
        "lang_name": "🇧🇩 বাংলা",
        "welcome": "💸 <b>তোমার বট এইমাত্র টাকা উপার্জন করল।</b>\n\n<b>SAARS Demo</b>-তে স্বাগত — যে বট ঘুমের মধ্যে কাজ করে।\n\n👇 তোমার ড্যাশবোর্ড খোলো:",
        "open_demo": "🚀 আমার ড্যাশবোর্ড খুলুন",
        "main_title": "🚀 <b>SAARS — ইন্টারেক্টিভ ডেমো</b>",
        "balance_line": "💰 তোমার ব্যালেন্স: <b>{bal} USDT</b>",
        "choose_section": "👇 একটি বিভাগ বেছে নাও:",
        "btn_store": "🛍️ স্টোর", "btn_tasks": "📋 টাস্ক", "btn_ref": "👥 রেফারেল",
        "btn_balance": "💰 আমার ব্যালেন্স", "btn_guard": "🔒 চ্যানেল গার্ড", "btn_wallets": "💳 ওয়ালেট",
        "btn_about": "ℹ️ কিভাবে কাজ করে", "btn_close": "⏸️ বিরতি", "btn_menu": "🔙 মেনু",
        "btn_back_store": "🔙 স্টোর", "btn_back_tasks": "🔙 টাস্ক", "btn_back_ref": "🔙 রেফারেল",
        "btn_ranking": "🏆 র‍্যাঙ্কিং", "btn_reopen": "🚀 পুনরায় খুলুন", "btn_home": "🏠 ডেমো মেনু",
        "btn_tasks_go": "📋 টাস্কে উপার্জন করো",
        "btn_buy_bal": "⚡ এখনই কিনুন ({bal} USDT)",
        "btn_buy_crypto": "💳 ক্রিপ্টোতে পেমেন্ট",
        "btn_paid": "✅ আমি পেমেন্ট পাঠিয়েছি",
        "btn_delivery": "📦 পণ্য অ্যাক্সেস", "btn_verify": "✅ আমি সদস্য — যাচাই করুন",
        "btn_saldo_tasks": "📋 আরও উপার্জন", "btn_saldo_ref": "👥 আমন্ত্রণ ও উপার্জন",
        "about_text": "🤖 <b>SAARS — তোমার ডিজিটাল ব্যবসা স্বয়ংক্রিয়ভাবে।</b>\n\n<b>Pro Plan: $20/মাস।</b>",
        "closed": "⏸️ ডেমো বিরতিতে। /start ফিরে যেতে।",
        "store_title": "🛍️ <b>স্টোর</b>\n\n💰 ব্যালেন্স: <b>{bal} USDT</b>",
        "already_bought": "✅ তুমি ইতোমধ্যে এই পণ্যে অ্যাক্সেস পেয়েছ।",
        "insufficient": "❌ <b>অপর্যাপ্ত ব্যালেন্স।</b>\n\n<b>{price} USDT</b> প্রয়োজন।",
        "purchase_ok": "✅ <b>ক্রয় নিশ্চিত!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>ক্রিপ্টো পেমেন্ট</b>\n\nপণ্য: <b>{title}</b>\nমূল্য: <b>{price} USDT</b>\n\n{wallets}",
        "confirmed": "✅ <b>নিশ্চিত!</b>\n<i>[ডেমো: স্বয়ংক্রিয়]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>তোমার অ্যাক্সেস</b>\n\n{delivery}",
        "tasks_title": "📋 <b>টাস্ক</b>\n\n💰 ব্যালেন্স: <b>{bal} USDT</b>",
        "task_done_mark": "✅ ",
        "task_done": "⚡ <b>USDT জমা হয়েছে!</b>\n\n+<b>{reward} USDT</b>\nব্যালেন্স: <b>{bal} USDT</b>",
        "task_already": "✅ টাস্ক সম্পন্ন।",
        "proof_wait": "📤 <b>প্রমাণ পাঠাও</b>",
        "proof_cancel": "❌ বাতিল",
        "proof_ok": "✅ <b>অনুমোদিত!</b>\n\n+<b>{reward} USDT</b>\nব্যালেন্স: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>রেফারেল</b>\n\n🔗 তোমার লিংক:\n<code>{link}</code>\n\n👤 আমন্ত্রিত: <b>{cnt}</b>\n💰 উপার্জন: <b>{earn} USDT</b>",
        "ranking_empty": "🏆 <b>র‍্যাঙ্কিং</b>\n\nএখনো কেউ নেই।",
        "ranking_title": "🏆 <b>শীর্ষ রেফারার</b>\n",
        "ranking_line": "{medal} {name} — {cnt} সদস্য · {earn} USDT",
        "new_ref": "🎉 <b>নতুন সদস্য!</b>\n\n<b>{name}</b> যোগ দিয়েছে।\n💰 +<b>{reward} USDT</b>",
        "balance_title": "💰 <b>তোমার SAARS ওয়ালেট</b>\n\nব্যালেন্স: <b>{bal} USDT</b>",
        "tx_header": "\n\n📜 <b>শেষ লেনদেন:</b>\n",
        "guard_title": "🔒 <b>চ্যানেল গার্ড</b>\n\n<b>চ্যানেল:</b>\n{channels}",
        "guard_ok": "✅ <b>যাচাই সম্পন্ন!</b>",
        "wallets_title": "💳 <b>পেমেন্ট ওয়ালেট</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 ব্যালেন্স: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>অ্যাক্সেস আছে</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 পুরস্কার: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>সম্পন্ন!</b>",
        "btn_submit_task": "⚡ সম্পন্ন করো ও পাও",
        "btn_send_proof": "📤 প্রমাণ পাঠাও",
        "lang_select": "🌐 <b>ভাষা</b>\n\nতোমার ভাষা বেছে নাও:",
        "lang_set": "✅ ভাষা: {lang}",
        "btn_lang": "🌐 ভাষা",
        "btn_menubuilder": "🎛️ মেনু বিল্ডার",
        "mb_intro": "🎛️ <b>মেনু বিল্ডার</b>\n\nতোমার বটের কাস্টম মেনু তৈরি করো — নিজের আইকন, শিরোনাম ও বাটন দিয়ে।\n\n<i>তোমার গ্রাহকরা বট খুললে ঠিক এটাই দেখবে।</i>",
        "mb_empty": "তুমি এখনো তোমার মেনু তৈরি করোনি।",
        "mb_preview_title": "👁️ <b>তোমার মেনুর প্রিভিউ:</b>",
        "mb_btn_create": "✨ আমার মেনু তৈরি করো",
        "mb_btn_edit": "✏️ মেনু সম্পাদনা",
        "mb_btn_preview": "👁️ প্রিভিউ",
        "mb_btn_open": "▶️ আমার মেনু খুলুন",
        "mb_btn_delete": "🗑️ মেনু মুছুন",
        "mb_btn_addbtn": "➕ বাটন যোগ করো",
        "mb_btn_editicon": "🎨 আইকন/শিরোনাম পরিবর্তন",
        "mb_step_icon": "🎨 <b>ধাপ ১/২ — মেনুর পরিচয়</b>\n\nতোমার মেনুর জন্য একটি <b>ইমোজি</b> পাঠাও (যেমন: 🎯, 🚀, 💼):",
        "mb_step_title": "🎨 <b>ধাপ ২/২ — মেনুর শিরোনাম</b>\n\nইমোজি: {icon}\n\nএখন <b>মেনুর শিরোনাম</b> পাঠাও (যেমন: <i>প্রিমিয়াম প্যানেল</i>):",
        "mb_created": "✅ <b>মেনু তৈরি হয়েছে!</b>\n\n{icon} <b>{title}</b>\n\nএখন বাটন যোগ করো।",
        "mb_btn_step_label": "🔘 <b>নতুন বাটন — ১/৩</b>\n\n<b>বাটনের লেখা</b> পাঠাও (যেমন: <i>📦 আমার পণ্য</i>):",
        "mb_btn_step_type": "🔘 <b>নতুন বাটন — ২/৩</b>\n\nলেখা: <i>{label}</i>\n\nএই বাটনের অ্যাকশন কী হবে?",
        "mb_btn_type_link": "🔗 বাহ্যিক লিংক খুলুন",
        "mb_btn_type_text": "💬 বার্তা দেখাও",
        "mb_btn_type_submenu": "📂 সাবমেনু খুলুন",
        "mb_btn_step_link": "🔗 <b>নতুন বাটন — ৩/৩</b>\n\n<b>URL</b> পাঠাও (যেমন: <i>https://t.me/তোমারচ্যানেল</i>):",
        "mb_btn_step_text": "💬 <b>নতুন বাটন — ৩/৩</b>\n\nক্লিক করলে যে <b>বার্তা</b> দেখাবে তা পাঠাও:",
        "mb_btn_step_submenu_title": "📂 <b>নতুন বাটন — ৩/৩</b>\n\n<b>সাবমেনুর শিরোনাম</b> পাঠাও (যেমন: <i>আরও অপশন</i>):",
        "mb_btn_added": "✅ <b>বাটন যোগ হয়েছে!</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ বাটন মুছে ফেলা হয়েছে।",
        "mb_deleted": "🗑️ <b>মেনু মুছে ফেলা হয়েছে।</b>\n\nতুমি যেকোনো সময় নতুন তৈরি করতে পারো।",
        "mb_max_buttons": "⚠️ এই ডেমোতে সর্বোচ্চ ৮টি বাটনের সীমা।",
        "mb_no_buttons": "<i>এখনো কোনো বাটন নেই। প্রথমটি যোগ করো!</i>",
        "mb_open_empty": "🎛️ <b>তোমার মেনু খালি।</b>\n\n🎛️ মেনু বিল্ডারে গিয়ে বাটন যোগ করো।",
        "mb_back_to_menu": "🔙 ফিরে যাও",
        "mb_psych": "\n\n━━━━━━━━━━━━━━━━\n💡 <i>এই মেনু তোমার বটের প্রথম ছাপ তৈরি করে।\nএকটি পরিষ্কার, সুন্দর মেনু আরও দর্শককে গ্রাহকে রূপান্তর করে।</i>",
    },

    # ── Hindi ────────────────────────────────────
    "hi": {
        "lang_name": "🇮🇳 हिन्दी",
        "welcome": "💸 <b>तुम्हारे बॉट ने अभी पैसे कमाए।</b>\n\n<b>SAARS Demo</b> में स्वागत है — वो बॉट जो सोते वक्त काम करता है।\n\n👇 अपना डैशबोर्ड खोलो:",
        "open_demo": "🚀 मेरा डैशबोर्ड खोलें",
        "main_title": "🚀 <b>SAARS — इंटरेक्टिव डेमो</b>",
        "balance_line": "💰 तुम्हारा बैलेंस: <b>{bal} USDT</b>",
        "choose_section": "👇 एक सेक्शन चुनो:",
        "btn_store": "🛍️ स्टोर", "btn_tasks": "📋 टास्क", "btn_ref": "👥 रेफरल",
        "btn_balance": "💰 मेरा बैलेंस", "btn_guard": "🔒 चैनल गार्ड", "btn_wallets": "💳 वॉलेट",
        "btn_about": "ℹ️ कैसे काम करता है", "btn_close": "⏸️ डेमो रोकें", "btn_menu": "🔙 मेनू",
        "btn_back_store": "🔙 स्टोर", "btn_back_tasks": "🔙 टास्क", "btn_back_ref": "🔙 रेफरल",
        "btn_ranking": "🏆 लाइव रैंकिंग", "btn_reopen": "🚀 फिर खोलें", "btn_home": "🏠 डेमो मेनू",
        "btn_tasks_go": "📋 टास्क से कमाओ",
        "btn_buy_bal": "⚡ अभी खरीदो ({bal} USDT उपलब्ध)",
        "btn_buy_crypto": "💳 क्रिप्टो से पेमेंट",
        "btn_paid": "✅ मैंने पेमेंट भेज दिया",
        "btn_delivery": "📦 प्रोडक्ट एक्सेस", "btn_verify": "✅ मैं सदस्य हूं — वेरिफाई",
        "btn_saldo_tasks": "📋 और कमाओ", "btn_saldo_ref": "👥 आमंत्रित करो और कमाओ",
        "about_text": "🤖 <b>SAARS — तुम्हारा डिजिटल बिजनेस ऑटोपायलट पर।</b>\n\n<b>Pro Plan: $20/महीना।</b>",
        "closed": "⏸️ डेमो रुका। /start वापस आने के लिए।",
        "store_title": "🛍️ <b>स्टोर</b>\n\n💰 बैलेंस: <b>{bal} USDT</b>",
        "already_bought": "✅ तुम्हारे पास पहले से एक्सेस है।",
        "insufficient": "❌ <b>पर्याप्त बैलेंस नहीं।</b>\n\n<b>{price} USDT</b> चाहिए।",
        "purchase_ok": "✅ <b>खरीदारी पुष्टि!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>क्रिप्टो पेमेंट</b>\n\nप्रोडक्ट: <b>{title}</b>\nराशि: <b>{price} USDT</b>\n\n{wallets}",
        "confirmed": "✅ <b>पुष्टि!</b>\n<i>[डेमो: स्वचालित]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>तुम्हारा एक्सेस</b>\n\n{delivery}",
        "tasks_title": "📋 <b>टास्क</b>\n\n💰 बैलेंस: <b>{bal} USDT</b>",
        "task_done_mark": "✅ ",
        "task_done": "⚡ <b>USDT जमा!</b>\n\n+<b>{reward} USDT</b>\nबैलेंस: <b>{bal} USDT</b>",
        "task_already": "✅ टास्क पहले ही पूरा।",
        "proof_wait": "📤 <b>प्रमाण भेजो</b>",
        "proof_cancel": "❌ रद्द करें",
        "proof_ok": "✅ <b>अनुमोदित!</b>\n\n+<b>{reward} USDT</b>\nबैलेंस: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>रेफरल</b>\n\n🔗 तुम्हारा लिंक:\n<code>{link}</code>\n\n👤 आमंत्रित: <b>{cnt}</b>\n💰 कमाई: <b>{earn} USDT</b>",
        "ranking_empty": "🏆 <b>रैंकिंग</b>\n\nअभी तक कोई नहीं।",
        "ranking_title": "🏆 <b>टॉप रेफरर</b>\n",
        "ranking_line": "{medal} {name} — {cnt} सदस्य · {earn} USDT",
        "new_ref": "🎉 <b>नया सदस्य!</b>\n\n<b>{name}</b> जुड़ा।\n💰 +<b>{reward} USDT</b>",
        "balance_title": "💰 <b>तुम्हारा SAARS वॉलेट</b>\n\nबैलेंस: <b>{bal} USDT</b>",
        "tx_header": "\n\n📜 <b>हालिया लेनदेन:</b>\n",
        "guard_title": "🔒 <b>चैनल गार्ड</b>\n\n<b>चैनल:</b>\n{channels}",
        "guard_ok": "✅ <b>वेरिफिकेशन पूर्ण!</b>",
        "wallets_title": "💳 <b>पेमेंट वॉलेट</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 बैलेंस: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>एक्सेस है</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 पुरस्कार: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>पूर्ण!</b>",
        "btn_submit_task": "⚡ पूरा करो और पाओ",
        "btn_send_proof": "📤 प्रमाण भेजो",
        "lang_select": "🌐 <b>भाषा</b>\n\nअपनी भाषा चुनो:",
        "lang_set": "✅ भाषा: {lang}",
        "btn_lang": "🌐 भाषा",
        "btn_menubuilder": "🎛️ मेनू बिल्डर",
        "mb_intro": "🎛️ <b>मेनू बिल्डर</b>\n\nअपने बॉट का कस्टम मेनू बनाओ — अपने आइकन, टाइटल और बटन के साथ।\n\n<i>तुम्हारे ग्राहक बॉट खोलते ही यही देखेंगे।</i>",
        "mb_empty": "तुमने अभी तक अपना मेनू नहीं बनाया।",
        "mb_preview_title": "👁️ <b>तुम्हारे मेनू का पूर्वावलोकन:</b>",
        "mb_btn_create": "✨ मेरा मेनू बनाओ",
        "mb_btn_edit": "✏️ मेनू संपादित करो",
        "mb_btn_preview": "👁️ पूर्वावलोकन",
        "mb_btn_open": "▶️ मेरा मेनू खोलो",
        "mb_btn_delete": "🗑️ मेनू हटाओ",
        "mb_btn_addbtn": "➕ बटन जोड़ो",
        "mb_btn_editicon": "🎨 आइकन/टाइटल बदलो",
        "mb_step_icon": "🎨 <b>चरण 1/2 — मेनू पहचान</b>\n\nअपने मेनू के लिए एक <b>इमोजी</b> भेजो (जैसे: 🎯, 🚀, 💼):",
        "mb_step_title": "🎨 <b>चरण 2/2 — मेनू टाइटल</b>\n\nइमोजी: {icon}\n\nअब <b>मेनू का टाइटल</b> भेजो (जैसे: <i>प्रीमियम पैनल</i>):",
        "mb_created": "✅ <b>मेनू बन गया!</b>\n\n{icon} <b>{title}</b>\n\nअब बटन जोड़ो।",
        "mb_btn_step_label": "🔘 <b>नया बटन — 1/3</b>\n\n<b>बटन का टेक्स्ट</b> भेजो (जैसे: <i>📦 मेरे प्रोडक्ट्स</i>):",
        "mb_btn_step_type": "🔘 <b>नया बटन — 2/3</b>\n\nटेक्स्ट: <i>{label}</i>\n\nइस बटन का एक्शन क्या होगा?",
        "mb_btn_type_link": "🔗 बाहरी लिंक खोलो",
        "mb_btn_type_text": "💬 संदेश दिखाओ",
        "mb_btn_type_submenu": "📂 सबमेनू खोलो",
        "mb_btn_step_link": "🔗 <b>नया बटन — 3/3</b>\n\n<b>URL</b> भेजो (जैसे: <i>https://t.me/तुम्हाराचैनल</i>):",
        "mb_btn_step_text": "💬 <b>नया बटन — 3/3</b>\n\nक्लिक करने पर दिखने वाला <b>संदेश</b> भेजो:",
        "mb_btn_step_submenu_title": "📂 <b>नया बटन — 3/3</b>\n\n<b>सबमेनू का टाइटल</b> भेजो (जैसे: <i>और विकल्प</i>):",
        "mb_btn_added": "✅ <b>बटन जोड़ा गया!</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ बटन हटाया गया।",
        "mb_deleted": "🗑️ <b>मेनू हटाया गया।</b>\n\nतुम कभी भी नया बना सकते हो।",
        "mb_max_buttons": "⚠️ इस डेमो में अधिकतम 8 बटन की सीमा है।",
        "mb_no_buttons": "<i>अभी कोई बटन नहीं। पहला जोड़ो!</i>",
        "mb_open_empty": "🎛️ <b>तुम्हारा मेनू खाली है।</b>\n\n🎛️ मेनू बिल्डर में जाओ और बटन जोड़ो।",
        "mb_back_to_menu": "🔙 वापस",
        "mb_psych": "\n\n━━━━━━━━━━━━━━━━\n💡 <i>यह मेनू तुम्हारे बॉट का पहला प्रभाव तय करता है।\nएक साफ और सुंदर मेनू ज्यादा विज़िटर्स को ग्राहक बनाता है।</i>",
    },

    # ── Arabic ───────────────────────────────────
    "ar": {
        "lang_name": "🇸🇦 العربية",
        "welcome": "💸 <b>بوتك كسب المال للتو.</b>\n\nمرحباً بك في <b>SAARS Demo</b> — البوت الذي يعمل أثناء نومك.\n\n👇 افتح لوحتك وشاهد بنفسك:",
        "open_demo": "🚀 افتح لوحتي",
        "main_title": "🚀 <b>SAARS — عرض تفاعلي</b>",
        "balance_line": "💰 رصيدك: <b>{bal} USDT</b>",
        "choose_section": "👇 اختر قسماً:",
        "btn_store": "🛍️ المتجر", "btn_tasks": "📋 المهام", "btn_ref": "👥 الإحالة",
        "btn_balance": "💰 رصيدي", "btn_guard": "🔒 حارس القناة", "btn_wallets": "💳 المحافظ",
        "btn_about": "ℹ️ كيف يعمل", "btn_close": "⏸️ إيقاف مؤقت", "btn_menu": "🔙 القائمة",
        "btn_back_store": "🔙 المتجر", "btn_back_tasks": "🔙 المهام", "btn_back_ref": "🔙 الإحالة",
        "btn_ranking": "🏆 الترتيب المباشر", "btn_reopen": "🚀 إعادة فتح", "btn_home": "🏠 قائمة العرض",
        "btn_tasks_go": "📋 اكسب من المهام",
        "btn_buy_bal": "⚡ اشترِ الآن ({bal} USDT متاح)",
        "btn_buy_crypto": "💳 الدفع بالعملة المشفرة",
        "btn_paid": "✅ لقد أرسلت الدفعة",
        "btn_delivery": "📦 الوصول للمنتج", "btn_verify": "✅ أنا عضو — تحقق",
        "btn_saldo_tasks": "📋 اكسب أكثر", "btn_saldo_ref": "👥 ادعُ واكسب",
        "about_text": "🤖 <b>SAARS — عملك الرقمي على الطيار الآلي.</b>\n\n<b>الخطة الاحترافية: 20$/شهر.</b>",
        "closed": "⏸️ العرض متوقف. /start للعودة.",
        "store_title": "🛍️ <b>المتجر</b>\n\n💰 الرصيد: <b>{bal} USDT</b>",
        "already_bought": "✅ لديك بالفعل وصول لهذا المنتج.",
        "insufficient": "❌ <b>رصيد غير كافٍ.</b>\n\nتحتاج <b>{price} USDT</b>.",
        "purchase_ok": "✅ <b>تأكيد الشراء!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>دفع مشفر</b>\n\nالمنتج: <b>{title}</b>\nالمبلغ: <b>{price} USDT</b>\n\n{wallets}",
        "confirmed": "✅ <b>تأكيد!</b>\n<i>[عرض: تلقائي]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>وصولك</b>\n\n{delivery}",
        "tasks_title": "📋 <b>المهام</b>\n\n💰 الرصيد: <b>{bal} USDT</b>",
        "task_done_mark": "✅ ",
        "task_done": "⚡ <b>تم إضافة USDT!</b>\n\n+<b>{reward} USDT</b>\nالرصيد: <b>{bal} USDT</b>",
        "task_already": "✅ المهمة مكتملة مسبقاً.",
        "proof_wait": "📤 <b>أرسل الدليل</b>",
        "proof_cancel": "❌ إلغاء",
        "proof_ok": "✅ <b>تمت الموافقة!</b>\n\n+<b>{reward} USDT</b>\nالرصيد: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>الإحالة</b>\n\n🔗 رابطك:\n<code>{link}</code>\n\n👤 المدعوون: <b>{cnt}</b>\n💰 الأرباح: <b>{earn} USDT</b>",
        "ranking_empty": "🏆 <b>الترتيب</b>\n\nلا أحد بعد.",
        "ranking_title": "🏆 <b>أفضل المُحيلين</b>\n",
        "ranking_line": "{medal} {name} — {cnt} أعضاء · {earn} USDT",
        "new_ref": "🎉 <b>عضو جديد!</b>\n\n<b>{name}</b> انضم.\n💰 +<b>{reward} USDT</b>",
        "balance_title": "💰 <b>محفظة SAARS</b>\n\nالرصيد: <b>{bal} USDT</b>",
        "tx_header": "\n\n📜 <b>آخر المعاملات:</b>\n",
        "guard_title": "🔒 <b>حارس القناة</b>\n\n<b>القنوات:</b>\n{channels}",
        "guard_ok": "✅ <b>التحقق مكتمل!</b>",
        "wallets_title": "💳 <b>محافظ الاستلام</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 الرصيد: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>لديك وصول</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 المكافأة: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>مكتملة!</b>",
        "btn_submit_task": "⚡ أكمل واحصل الآن",
        "btn_send_proof": "📤 أرسل الدليل",
        "lang_select": "🌐 <b>اللغة</b>\n\nاختر لغتك:",
        "lang_set": "✅ اللغة: {lang}",
        "btn_lang": "🌐 اللغة",
        "btn_menubuilder": "🎛️ منشئ القائمة",
        "mb_intro": "🎛️ <b>منشئ القائمة</b>\n\nأنشئ قائمة بوتك المخصصة — برمزك التعبيري وعنوانك وأزرارك.\n\n<i>هذا بالضبط ما سيراه عملاؤك عند فتح بوتك.</i>",
        "mb_empty": "لم تنشئ قائمتك بعد.",
        "mb_preview_title": "👁️ <b>معاينة قائمتك:</b>",
        "mb_btn_create": "✨ إنشاء قائمتي",
        "mb_btn_edit": "✏️ تعديل القائمة",
        "mb_btn_preview": "👁️ معاينة",
        "mb_btn_open": "▶️ افتح قائمتي",
        "mb_btn_delete": "🗑️ حذف القائمة",
        "mb_btn_addbtn": "➕ إضافة زر",
        "mb_btn_editicon": "🎨 تغيير الرمز/العنوان",
        "mb_step_icon": "🎨 <b>الخطوة 1/2 — هوية القائمة</b>\n\nأرسل <b>رمزاً تعبيرياً</b> لتمثيل قائمتك (مثل: 🎯, 🚀, 💼):",
        "mb_step_title": "🎨 <b>الخطوة 2/2 — عنوان القائمة</b>\n\nالرمز: {icon}\n\nالآن أرسل <b>عنوان القائمة</b> (مثل: <i>اللوحة المميزة</i>):",
        "mb_created": "✅ <b>تم إنشاء القائمة!</b>\n\n{icon} <b>{title}</b>\n\nأضف أزراراً الآن لإحياء قائمتك.",
        "mb_btn_step_label": "🔘 <b>زر جديد — 1/3</b>\n\nأرسل <b>نص الزر</b> (مثل: <i>📦 منتجاتي</i>):",
        "mb_btn_step_type": "🔘 <b>زر جديد — 2/3</b>\n\nالنص: <i>{label}</i>\n\nما هو الإجراء الذي سيقوم به هذا الزر؟",
        "mb_btn_type_link": "🔗 فتح رابط خارجي",
        "mb_btn_type_text": "💬 عرض رسالة",
        "mb_btn_type_submenu": "📂 فتح قائمة فرعية",
        "mb_btn_step_link": "🔗 <b>زر جديد — 3/3</b>\n\nأرسل <b>الرابط</b> (مثل: <i>https://t.me/قناتك</i>):",
        "mb_btn_step_text": "💬 <b>زر جديد — 3/3</b>\n\nأرسل <b>الرسالة</b> التي ستظهر عند الضغط:",
        "mb_btn_step_submenu_title": "📂 <b>زر جديد — 3/3</b>\n\nأرسل <b>عنوان القائمة الفرعية</b> (مثل: <i>المزيد من الخيارات</i>):",
        "mb_btn_added": "✅ <b>تمت إضافة الزر!</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ تم حذف الزر.",
        "mb_deleted": "🗑️ <b>تم حذف القائمة.</b>\n\nيمكنك إنشاء واحدة جديدة في أي وقت.",
        "mb_max_buttons": "⚠️ تم بلوغ الحد الأقصى 8 أزرار في هذا العرض.",
        "mb_no_buttons": "<i>لا توجد أزرار بعد. أضف الأول!</i>",
        "mb_open_empty": "🎛️ <b>قائمتك فارغة.</b>\n\nاذهب إلى 🎛️ منشئ القائمة وأضف أزراراً.",
        "mb_back_to_menu": "🔙 رجوع",
        "mb_psych": "\n\n━━━━━━━━━━━━━━━━\n💡 <i>هذه القائمة تحدد الانطباع الأول عن بوتك.\nقائمة واضحة وجذابة تحول المزيد من الزوار إلى عملاء يدفعون.</i>",
    },

    # ── Chinese ──────────────────────────────────
    "zh": {
        "lang_name": "🇨🇳 中文",
        "welcome": "💸 <b>你的机器人刚刚赚到了钱。</b>\n\n欢迎来到 <b>SAARS Demo</b> — 在你睡觉时工作的机器人。\n\n👇 打开你的控制台亲眼见证：",
        "open_demo": "🚀 打开我的控制台",
        "main_title": "🚀 <b>SAARS — 互动演示</b>",
        "balance_line": "💰 你的余额：<b>{bal} USDT</b>",
        "choose_section": "👇 选择一个模块：",
        "btn_store": "🛍️ 商店", "btn_tasks": "📋 任务", "btn_ref": "👥 推荐",
        "btn_balance": "💰 我的余额", "btn_guard": "🔒 频道守卫", "btn_wallets": "💳 钱包",
        "btn_about": "ℹ️ 工作原理", "btn_close": "⏸️ 暂停演示", "btn_menu": "🔙 菜单",
        "btn_back_store": "🔙 商店", "btn_back_tasks": "🔙 任务", "btn_back_ref": "🔙 推荐",
        "btn_ranking": "🏆 实时排名", "btn_reopen": "🚀 重新打开", "btn_home": "🏠 演示菜单",
        "btn_tasks_go": "📋 通过任务赚钱",
        "btn_buy_bal": "⚡ 立即购买（{bal} USDT 可用）",
        "btn_buy_crypto": "💳 加密货币支付",
        "btn_paid": "✅ 我已付款",
        "btn_delivery": "📦 获取产品", "btn_verify": "✅ 我是成员 — 验证",
        "btn_saldo_tasks": "📋 赚更多", "btn_saldo_ref": "👥 邀请并赚取",
        "about_text": "🤖 <b>SAARS — 你的数字业务自动运行。</b>\n\n<b>Pro 计划：每月 $20。</b>",
        "closed": "⏸️ 演示暂停。/start 返回。",
        "store_title": "🛍️ <b>商店</b>\n\n💰 余额：<b>{bal} USDT</b>",
        "already_bought": "✅ 你已经拥有此产品的访问权限。",
        "insufficient": "❌ <b>余额不足。</b>\n\n需要 <b>{price} USDT</b>。",
        "purchase_ok": "✅ <b>购买确认！</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>加密支付</b>\n\n产品：<b>{title}</b>\n金额：<b>{price} USDT</b>\n\n{wallets}",
        "confirmed": "✅ <b>已确认！</b>\n<i>[演示：自动]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>你的访问</b>\n\n{delivery}",
        "tasks_title": "📋 <b>任务</b>\n\n💰 余额：<b>{bal} USDT</b>",
        "task_done_mark": "✅ ",
        "task_done": "⚡ <b>USDT 已到账！</b>\n\n+<b>{reward} USDT</b>\n余额：<b>{bal} USDT</b>",
        "task_already": "✅ 任务已完成。",
        "proof_wait": "📤 <b>发送证明</b>",
        "proof_cancel": "❌ 取消",
        "proof_ok": "✅ <b>已批准！</b>\n\n+<b>{reward} USDT</b>\n余额：<b>{bal} USDT</b>",
        "ref_title": "👥 <b>推荐</b>\n\n🔗 你的链接：\n<code>{link}</code>\n\n👤 已邀请：<b>{cnt}</b>\n💰 收益：<b>{earn} USDT</b>",
        "ranking_empty": "🏆 <b>排名</b>\n\n还没有人。",
        "ranking_title": "🏆 <b>顶级推荐人</b>\n",
        "ranking_line": "{medal} {name} — {cnt} 成员 · {earn} USDT",
        "new_ref": "🎉 <b>新成员！</b>\n\n<b>{name}</b> 已加入。\n💰 +<b>{reward} USDT</b>",
        "balance_title": "💰 <b>你的 SAARS 钱包</b>\n\n余额：<b>{bal} USDT</b>",
        "tx_header": "\n\n📜 <b>最近交易：</b>\n",
        "guard_title": "🔒 <b>频道守卫</b>\n\n<b>频道：</b>\n{channels}",
        "guard_ok": "✅ <b>验证完成！</b>",
        "wallets_title": "💳 <b>收款钱包</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 余额：<b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>已有访问权限</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 奖励：<b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>已完成！</b>",
        "btn_submit_task": "⚡ 完成并立即获取",
        "btn_send_proof": "📤 发送证明",
        "lang_select": "🌐 <b>语言</b>\n\n选择你的语言：",
        "lang_set": "✅ 语言：{lang}",
        "btn_lang": "🌐 语言",
        "btn_menubuilder": "🎛️ 菜单构建器",
        "mb_intro": "🎛️ <b>菜单构建器</b>\n\n创建你机器人的自定义菜单——使用你自己的图标、标题和按钮。\n\n<i>这正是你的客户打开机器人时会看到的内容。</i>",
        "mb_empty": "你还没有创建菜单。",
        "mb_preview_title": "👁️ <b>菜单预览：</b>",
        "mb_btn_create": "✨ 创建我的菜单",
        "mb_btn_edit": "✏️ 编辑菜单",
        "mb_btn_preview": "👁️ 预览",
        "mb_btn_open": "▶️ 打开我的菜单",
        "mb_btn_delete": "🗑️ 删除菜单",
        "mb_btn_addbtn": "➕ 添加按钮",
        "mb_btn_editicon": "🎨 更改图标/标题",
        "mb_step_icon": "🎨 <b>第1/2步 — 菜单标识</b>\n\n发送一个<b>表情符号</b>代表你的菜单（例如：🎯、🚀、💼）：",
        "mb_step_title": "🎨 <b>第2/2步 — 菜单标题</b>\n\n表情：{icon}\n\n现在发送<b>菜单标题</b>（例如：<i>高级面板</i>）：",
        "mb_created": "✅ <b>菜单已创建！</b>\n\n{icon} <b>{title}</b>\n\n现在添加按钮让菜单生动起来。",
        "mb_btn_step_label": "🔘 <b>新按钮 — 1/3</b>\n\n发送<b>按钮文字</b>（例如：<i>📦 我的产品</i>）：",
        "mb_btn_step_type": "🔘 <b>新按钮 — 2/3</b>\n\n文字：<i>{label}</i>\n\n这个按钮的操作是什么？",
        "mb_btn_type_link": "🔗 打开外部链接",
        "mb_btn_type_text": "💬 显示消息",
        "mb_btn_type_submenu": "📂 打开子菜单",
        "mb_btn_step_link": "🔗 <b>新按钮 — 3/3</b>\n\n发送<b>URL</b>（例如：<i>https://t.me/你的频道</i>）：",
        "mb_btn_step_text": "💬 <b>新按钮 — 3/3</b>\n\n发送点击时显示的<b>消息</b>：",
        "mb_btn_step_submenu_title": "📂 <b>新按钮 — 3/3</b>\n\n发送<b>子菜单标题</b>（例如：<i>更多选项</i>）：",
        "mb_btn_added": "✅ <b>按钮已添加！</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ 按钮已删除。",
        "mb_deleted": "🗑️ <b>菜单已删除。</b>\n\n你可以随时创建新菜单。",
        "mb_max_buttons": "⚠️ 此演示最多支持8个按钮。",
        "mb_no_buttons": "<i>还没有按钮。添加第一个吧！</i>",
        "mb_open_empty": "🎛️ <b>你的菜单是空的。</b>\n\n前往🎛️菜单构建器添加按钮。",
        "mb_back_to_menu": "🔙 返回",
        "mb_psych": "\n\n━━━━━━━━━━━━━━━━\n💡 <i>这个菜单决定了你机器人给人的第一印象。\n清晰美观的菜单能将更多访客转化为付费客户。</i>",
    },

    # ── Indonesian ───────────────────────────────
    "id": {
        "lang_name": "🇮🇩 Indonesia",
        "welcome": "💸 <b>Bot kamu baru saja menghasilkan uang.</b>\n\nSelamat datang di <b>SAARS Demo</b> — bot yang bekerja saat kamu tidur.\n\n👇 Buka dashboard-mu dan lihat sendiri:",
        "open_demo": "🚀 Buka dashboard saya",
        "main_title": "🚀 <b>SAARS — Demo Interaktif</b>",
        "balance_line": "💰 Saldo kamu: <b>{bal} USDT</b>",
        "choose_section": "👇 Pilih seksi:",
        "btn_store": "🛍️ Toko", "btn_tasks": "📋 Tugas", "btn_ref": "👥 Referral",
        "btn_balance": "💰 Saldo Saya", "btn_guard": "🔒 Channel Guard", "btn_wallets": "💳 Dompet",
        "btn_about": "ℹ️ Cara kerja", "btn_close": "⏸️ Jeda demo", "btn_menu": "🔙 Menu",
        "btn_back_store": "🔙 Toko", "btn_back_tasks": "🔙 Tugas", "btn_back_ref": "🔙 Referral",
        "btn_ranking": "🏆 Peringkat langsung", "btn_reopen": "🚀 Buka lagi", "btn_home": "🏠 Menu Demo",
        "btn_tasks_go": "📋 Hasilkan dari Tugas",
        "btn_buy_bal": "⚡ Beli sekarang ({bal} USDT tersedia)",
        "btn_buy_crypto": "💳 Bayar dengan crypto",
        "btn_paid": "✅ Saya sudah kirim pembayaran",
        "btn_delivery": "📦 Akses produk", "btn_verify": "✅ Saya anggota — verifikasi",
        "btn_saldo_tasks": "📋 Hasilkan lebih", "btn_saldo_ref": "👥 Undang dan hasilkan",
        "about_text": "🤖 <b>SAARS — bisnis digital kamu di autopilot.</b>\n\n<b>Paket Pro: $20/bulan.</b>",
        "closed": "⏸️ Demo dijeda. /start untuk kembali.",
        "store_title": "🛍️ <b>Toko</b>\n\n💰 Saldo: <b>{bal} USDT</b>",
        "already_bought": "✅ Kamu sudah punya akses ke produk ini.",
        "insufficient": "❌ <b>Saldo tidak cukup.</b>\n\nPerlu <b>{price} USDT</b>.",
        "purchase_ok": "✅ <b>Pembelian dikonfirmasi!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Pembayaran Crypto</b>\n\nProduk: <b>{title}</b>\nJumlah: <b>{price} USDT</b>\n\n{wallets}",
        "confirmed": "✅ <b>Dikonfirmasi!</b>\n<i>[Demo: otomatis]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Akses kamu</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Tugas</b>\n\n💰 Saldo: <b>{bal} USDT</b>",
        "task_done_mark": "✅ ",
        "task_done": "⚡ <b>USDT dikreditkan!</b>\n\n+<b>{reward} USDT</b>\nSaldo: <b>{bal} USDT</b>",
        "task_already": "✅ Tugas sudah selesai.",
        "proof_wait": "📤 <b>Kirim bukti</b>",
        "proof_cancel": "❌ Batal",
        "proof_ok": "✅ <b>Disetujui!</b>\n\n+<b>{reward} USDT</b>\nSaldo: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Referral</b>\n\n🔗 Link kamu:\n<code>{link}</code>\n\n👤 Diundang: <b>{cnt}</b>\n💰 Penghasilan: <b>{earn} USDT</b>",
        "ranking_empty": "🏆 <b>Peringkat</b>\n\nBelum ada.",
        "ranking_title": "🏆 <b>Top Referral</b>\n",
        "ranking_line": "{medal} {name} — {cnt} anggota · {earn} USDT",
        "new_ref": "🎉 <b>Anggota baru!</b>\n\n<b>{name}</b> bergabung.\n💰 +<b>{reward} USDT</b>",
        "balance_title": "💰 <b>Dompet SAARS kamu</b>\n\nSaldo: <b>{bal} USDT</b>",
        "tx_header": "\n\n📜 <b>Transaksi terbaru:</b>\n",
        "guard_title": "🔒 <b>Channel Guard</b>\n\n<b>Channel:</b>\n{channels}",
        "guard_ok": "✅ <b>Verifikasi selesai!</b>",
        "wallets_title": "💳 <b>Dompet Penerima</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Saldo: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Sudah punya akses</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Hadiah: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Selesai!</b>",
        "btn_submit_task": "⚡ Selesaikan dan dapatkan sekarang",
        "btn_send_proof": "📤 Kirim bukti",
        "lang_select": "🌐 <b>Bahasa</b>\n\nPilih bahasamu:",
        "lang_set": "✅ Bahasa: {lang}",
        "btn_lang": "🌐 Bahasa",
        "btn_menubuilder": "🎛️ Pembuat Menu",
        "mb_intro": "🎛️ <b>Pembuat Menu</b>\n\nBuat menu khusus bot kamu — dengan ikon, judul, dan tombol sendiri.\n\n<i>Inilah yang akan dilihat pelanggan saat membuka bot kamu.</i>",
        "mb_empty": "Kamu belum membuat menu.",
        "mb_preview_title": "👁️ <b>Pratinjau menu kamu:</b>",
        "mb_btn_create": "✨ Buat menu saya",
        "mb_btn_edit": "✏️ Edit menu",
        "mb_btn_preview": "👁️ Pratinjau",
        "mb_btn_open": "▶️ Buka menu saya",
        "mb_btn_delete": "🗑️ Hapus menu",
        "mb_btn_addbtn": "➕ Tambah tombol",
        "mb_btn_editicon": "🎨 Ubah ikon/judul",
        "mb_step_icon": "🎨 <b>Langkah 1/2 — Identitas menu</b>\n\nKirim <b>emoji</b> untuk mewakili menu kamu (mis: 🎯, 🚀, 💼):",
        "mb_step_title": "🎨 <b>Langkah 2/2 — Judul menu</b>\n\nEmoji: {icon}\n\nSekarang kirim <b>judul menu</b> (mis: <i>Panel Premium</i>):",
        "mb_created": "✅ <b>Menu dibuat!</b>\n\n{icon} <b>{title}</b>\n\nSekarang tambahkan tombol untuk menghidupkan menu kamu.",
        "mb_btn_step_label": "🔘 <b>Tombol baru — 1/3</b>\n\nKirim <b>teks tombol</b> (mis: <i>📦 Produk saya</i>):",
        "mb_btn_step_type": "🔘 <b>Tombol baru — 2/3</b>\n\nTeks: <i>{label}</i>\n\nAksi apa untuk tombol ini?",
        "mb_btn_type_link": "🔗 Buka tautan eksternal",
        "mb_btn_type_text": "💬 Tampilkan pesan",
        "mb_btn_type_submenu": "📂 Buka submenu",
        "mb_btn_step_link": "🔗 <b>Tombol baru — 3/3</b>\n\nKirim <b>URL</b> (mis: <i>https://t.me/channelmu</i>):",
        "mb_btn_step_text": "💬 <b>Tombol baru — 3/3</b>\n\nKirim <b>pesan</b> yang muncul saat diklik:",
        "mb_btn_step_submenu_title": "📂 <b>Tombol baru — 3/3</b>\n\nKirim <b>judul submenu</b> (mis: <i>Opsi lainnya</i>):",
        "mb_btn_added": "✅ <b>Tombol ditambahkan!</b>\n\n{icon} {label}",
        "mb_btn_deleted": "🗑️ Tombol dihapus.",
        "mb_deleted": "🗑️ <b>Menu dihapus.</b>\n\nKamu bisa membuat yang baru kapan saja.",
        "mb_max_buttons": "⚠️ Batas 8 tombol tercapai di demo ini.",
        "mb_no_buttons": "<i>Belum ada tombol. Tambahkan yang pertama!</i>",
        "mb_open_empty": "🎛️ <b>Menu kamu kosong.</b>\n\nBuka 🎛️ Pembuat Menu dan tambahkan tombol.",
        "mb_back_to_menu": "🔙 Kembali",
        "mb_psych": "\n\n━━━━━━━━━━━━━━━━\n💡 <i>Menu ini menentukan kesan pertama bot kamu.\nMenu yang jelas dan menarik mengubah lebih banyak pengunjung jadi pelanggan berbayar.</i>",
    },
}

LANG_OPTIONS = [(code, d["lang_name"]) for code, d in STRINGS.items()]

def get_lang(uid: int, tg_code: str | None) -> str:
    if uid in _ulang: return _ulang[uid]
    if tg_code:
        base = tg_code.split("-")[0].lower()
        if base in STRINGS: return base
    return "pt"

def t(uid: int, key: str, **kw) -> str:
    lang = _ulang.get(uid, "pt")
    s = STRINGS.get(lang, STRINGS["pt"]).get(key) or STRINGS["pt"].get(key, key)
    return s.format(**kw) if kw else s

# ─────────────────────────────────────────────
#  Balance
# ─────────────────────────────────────────────

def bal(uid: int) -> Decimal:
    return _bal.get(uid, Decimal("0"))

def credit(uid: int, amount: Decimal, kind: str, note: str = "") -> Decimal:
    _bal[uid] = _bal.get(uid, Decimal("0")) + amount
    _txs.setdefault(uid, []).append({"a": amount, "t": kind, "n": note})
    return _bal[uid]

def debit(uid: int, amount: Decimal, kind: str, note: str = "") -> bool:
    if _bal.get(uid, Decimal("0")) < amount: return False
    _bal[uid] -= amount
    _txs.setdefault(uid, []).append({"a": -amount, "t": kind, "n": note})
    return True

# ─────────────────────────────────────────────
#  Keyboard helpers
# ─────────────────────────────────────────────

def kb(*rows): return InlineKeyboardMarkup([[InlineKeyboardButton(tx, callback_data=c) for tx, c in r] for r in rows])
def tdone(u, tid): return tid in _tdone.get(u, set())
def mtask(u, tid): _tdone.setdefault(u, set()).add(tid)
def bought(u, pid): return pid in _purch.get(u, set())
def mbuy(u, pid):   _purch.setdefault(u, set()).add(pid)

# ─────────────────────────────────────────────
#  Data constants
# ─────────────────────────────────────────────

TASKS: list[dict] = [
    {"id": 1, "title": "📢 Entrar no canal VIP", "desc": "Entra no canal exclusivo e recebe acesso antecipado a todos os lançamentos.", "reward": Decimal("2.00"), "verif": "auto"},
    {"id": 2, "title": "🐦 Seguir no Instagram",  "desc": "Segue o perfil oficial e confirma aqui para ganhar o bónus.", "reward": Decimal("1.50"), "verif": "auto"},
    {"id": 3, "title": "📸 Enviar comprovante de partilha", "desc": "Partilha este bot com 3 amigos e envia o screenshot como prova.", "reward": Decimal("5.00"), "verif": "manual"},
    {"id": 4, "title": "🎯 Responder ao quiz de negócios", "desc": "Completa o quiz de 3 perguntas sobre empreendedorismo digital.", "reward": Decimal("3.00"), "verif": "auto"},
]
PRODUCTS: list[dict] = [
    {"id": 1, "title": "⚡ Pack Automação Telegram", "desc": "Templates prontos para bots de vendas, suporte e comunidade. Deploy em 10 minutos.", "price": Decimal("4.99"),
     "delivery": "🎉 <b>Acesso liberado!</b>\n\n📦 Pack completo:\n• 5 templates de bot prontos\n• Guia de deploy no Render\n• Grupo VIP de suporte\n\n🔗 Acesso: https://t.me/saars_news\n\n<i>Válido por 365 dias.</i>"},
    {"id": 2, "title": "🎓 Mentoria: Renda com Bots", "desc": "6 semanas de mentoria ao vivo. Do zero ao primeiro cliente pagante.", "price": Decimal("27.00"),
     "delivery": "✅ <b>Mentoria confirmada!</b>\n\n📅 Próxima turma: segunda-feira\n💬 Grupo privado: https://t.me/saars_news\n\n<i>Guarda este link — é o teu acesso permanente.</i>"},
    {"id": 3, "title": "🤖 Bot Personalizado (feito pra ti)", "desc": "Entregamos o teu bot configurado, com loja, tarefas e referral. Pronto para monetizar.", "price": Decimal("97.00"),
     "delivery": "🚀 <b>Pedido recebido!</b>\n\nA equipa SAARS vai entrar em contacto em até 24h.\n\n📩 Telegram: @saars_suporte\n\n<i>Obrigado pela confiança!</i>"},
]
WALLETS: list[dict] = [
    {"id": 1, "label": "💎 TON Wallet",      "addr": "UQBWs0GY1YzNT8e2xSAARS_TON_DEMO"},
    {"id": 2, "label": "💲 USDT TRC20",      "addr": "TSAARS_DEMO_TRC20_xxxxxxxxxxxxxxxxx"},
    {"id": 3, "label": "🔶 BNB Smart Chain", "addr": "0xSAARS_DEMO_BEP20_xxxxxxxxxxxxxxx"},
]
CHANNELS: list[dict] = [
    {"id": 1, "label": "📢 Canal VIP SAARS",  "url": "https://t.me/saars_news"},
    {"id": 2, "label": "💬 Comunidade SAARS", "url": "https://t.me/saars_community"},
]

_next_id: dict[str, int] = {"task": 5, "product": 4, "wallet": 4, "channel": 3}

def _new_id(kind: str) -> int:
    nid = _next_id[kind]; _next_id[kind] += 1; return nid

# FSM state
_state: dict[int, dict] = {}

def _cancel_state(uid: int): _state.pop(uid, None)

async def _fsm_reply(u: Update, text: str, kb_rows=None):
    markup = InlineKeyboardMarkup(kb_rows) if kb_rows else None
    await u.message.reply_html(text, reply_markup=markup)

# ─────────────────────────────────────────────
#  Menu Gerir (⚙️)
# ─────────────────────────────────────────────

async def gerir(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    await q.edit_message_text(
        "⚙️ <b>Gerir Conteúdo</b>\n\nO que queres adicionar ou remover?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍️ Produtos",     callback_data="gerir:produtos")],
            [InlineKeyboardButton("📋 Tarefas",      callback_data="gerir:tarefas")],
            [InlineKeyboardButton("💳 Wallets",      callback_data="gerir:wallets")],
            [InlineKeyboardButton("🔒 Canais Guard", callback_data="gerir:canais")],
            [InlineKeyboardButton("🔙 Menu",         callback_data="demo:main")],
        ])
    )

async def gerir_produtos(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    linhas = [f"<b>⚙️ Produtos cadastrados ({len(PRODUCTS)})</b>\n"]
    for p in PRODUCTS:
        linhas.append(f"• [{p['id']}] {p['title']} — {p['price']} USDT")
    if not PRODUCTS: linhas.append("(nenhum ainda)")
    rows = [[InlineKeyboardButton("➕ Adicionar produto", callback_data="gerir:add_produto")]]
    for p in PRODUCTS:
        rows.append([InlineKeyboardButton(f"🗑️ [{p['id']}] {p['title'][:25]}", callback_data=f"gerir:del_produto:{p['id']}")])
    rows.append([InlineKeyboardButton("🔙 Gerir", callback_data="gerir:menu")])
    await q.edit_message_text("\n".join(linhas), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def gerir_add_produto(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "prod_titulo"}
    await q.edit_message_text(
        "🛍️ <b>Novo Produto — 1/4</b>\n\nEnvia o <b>título</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]])
    )

async def gerir_del_produto(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    pid = int(q.data.split(":")[2])
    global PRODUCTS; PRODUCTS = [p for p in PRODUCTS if p["id"] != pid]
    await gerir_produtos(u, c)

async def gerir_tarefas(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    linhas = [f"<b>⚙️ Tarefas cadastradas ({len(TASKS)})</b>\n"]
    for tk in TASKS:
        linhas.append(f"• [{tk['id']}] {tk['title']} — +{tk['reward']} USDT ({tk['verif']})")
    if not TASKS: linhas.append("(nenhuma ainda)")
    rows = [[InlineKeyboardButton("➕ Adicionar tarefa", callback_data="gerir:add_tarefa")]]
    for tk in TASKS:
        rows.append([InlineKeyboardButton(f"🗑️ [{tk['id']}] {tk['title'][:25]}", callback_data=f"gerir:del_tarefa:{tk['id']}")])
    rows.append([InlineKeyboardButton("🔙 Gerir", callback_data="gerir:menu")])
    await q.edit_message_text("\n".join(linhas), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def gerir_add_tarefa(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "task_titulo"}
    await q.edit_message_text(
        "📋 <b>Nova Tarefa — 1/3</b>\n\nEnvia o <b>título</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]])
    )

async def gerir_del_tarefa(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    tid = int(q.data.split(":")[2])
    global TASKS; TASKS = [tk for tk in TASKS if tk["id"] != tid]
    await gerir_tarefas(u, c)

async def gerir_wallets(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    linhas = [f"<b>⚙️ Wallets ({len(WALLETS)})</b>\n"]
    for w in WALLETS:
        linhas.append(f"• [{w['id']}] {w['label']}: <code>{w['addr'][:20]}…</code>")
    if not WALLETS: linhas.append("(nenhuma ainda)")
    rows = [[InlineKeyboardButton("➕ Adicionar wallet", callback_data="gerir:add_wallet")]]
    for w in WALLETS:
        rows.append([InlineKeyboardButton(f"🗑️ [{w['id']}] {w['label']}", callback_data=f"gerir:del_wallet:{w['id']}")])
    rows.append([InlineKeyboardButton("🔙 Gerir", callback_data="gerir:menu")])
    await q.edit_message_text("\n".join(linhas), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def gerir_add_wallet(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "wallet_label"}
    await q.edit_message_text(
        "💳 <b>Nova Wallet — 1/2</b>\n\nEnvia o <b>nome/rede</b>\n(ex: <i>TON Wallet</i>, <i>TRON TRC20</i>):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]])
    )

async def gerir_del_wallet(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    wid = int(q.data.split(":")[2])
    global WALLETS; WALLETS = [w for w in WALLETS if w["id"] != wid]
    await gerir_wallets(u, c)

async def gerir_canais(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    linhas = [f"<b>⚙️ Canais Guard ({len(CHANNELS)})</b>\n"]
    for ch in CHANNELS:
        linhas.append(f"• [{ch['id']}] {ch['label']}: {ch['url']}")
    if not CHANNELS: linhas.append("(nenhum ainda)")
    rows = [[InlineKeyboardButton("➕ Adicionar canal", callback_data="gerir:add_canal")]]
    for ch in CHANNELS:
        rows.append([InlineKeyboardButton(f"🗑️ [{ch['id']}] {ch['label']}", callback_data=f"gerir:del_canal:{ch['id']}")])
    rows.append([InlineKeyboardButton("🔙 Gerir", callback_data="gerir:menu")])
    await q.edit_message_text("\n".join(linhas), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def gerir_add_canal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "canal_label"}
    await q.edit_message_text(
        "🔒 <b>Novo Canal Guard — 1/2</b>\n\nEnvia o <b>nome</b> do canal:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]])
    )

async def gerir_del_canal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    cid = int(q.data.split(":")[2])
    global CHANNELS; CHANNELS = [ch for ch in CHANNELS if ch["id"] != cid]
    await gerir_canais(u, c)

async def gerir_cancel(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    uid = u.effective_user.id
    _cancel_state(uid)
    await gerir(u, c)

async def _gerir_task_verif_cb(u: Update, c: ContextTypes.DEFAULT_TYPE):
    """Callback dos botões ⚡auto / 📤manual na criação de tarefa."""
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    verif = q.data.split(":")[2]
    st = _state.get(uid, {})
    if st.get("step") != "task_verif":
        await q.answer("⚠️ Sessão expirada.", show_alert=True); return
    TASKS.append({
        "id":     _new_id("task"),
        "title":  st["titulo"],
        "desc":   st["desc"],
        "reward": st["reward"],
        "verif":  verif,
    })
    _cancel_state(uid)
    await q.edit_message_text(
        f"✅ <b>Tarefa adicionada!</b>\n\n📋 {st['titulo']} — +{st['reward']} USDT ({verif})",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Outra tarefa", callback_data="gerir:add_tarefa")],
            [InlineKeyboardButton("🔙 Gerir",        callback_data="gerir:tarefas")],
            [InlineKeyboardButton("🏠 Menu Demo",    callback_data="demo:main")],
        ])
    )

# ─────────────────────────────────────────────
#  FSM handle_text
# ─────────────────────────────────────────────

async def handle_text(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid  = u.effective_user.id
    text = (u.message.text or "").strip()
    st   = _state.get(uid)
    if not st: return

    step = st["step"]

    # ── Produto ──────────────────────────────
    if step == "prod_titulo":
        st["titulo"] = text; st["step"] = "prod_desc"
        await u.message.reply_html(
            f"🛍️ <b>Novo Produto — 2/4</b>\n\nTítulo: <i>{text}</i>\n\nEnvia a <b>descrição</b>:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "prod_desc":
        st["desc"] = text; st["step"] = "prod_preco"
        await u.message.reply_html(
            "🛍️ <b>Novo Produto — 3/4</b>\n\nEnvia o <b>preço em USDT</b> (ex: <i>5.00</i>):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "prod_preco":
        try:
            preco = Decimal(text.replace(",", "."))
        except Exception:
            await u.message.reply_html("❌ Valor inválido. Ex: <code>9.99</code>"); return
        st["preco"] = preco; st["step"] = "prod_delivery"
        await u.message.reply_html(
            f"🛍️ <b>Novo Produto — 4/4</b>\n\nPreço: <i>{preco} USDT</i>\n\nEnvia o <b>conteúdo de entrega</b>\n(link, texto, código de acesso…):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "prod_delivery":
        PRODUCTS.append({
            "id":       _new_id("product"),
            "title":    st["titulo"],
            "desc":     st["desc"],
            "price":    st["preco"],
            "delivery": text,
        })
        _cancel_state(uid)
        await u.message.reply_html(
            f"✅ <b>Produto adicionado!</b>\n\n🛍️ {st['titulo']} — {st['preco']} USDT",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Outro produto", callback_data="gerir:add_produto")],
                [InlineKeyboardButton("🔙 Gerir",         callback_data="gerir:produtos")],
                [InlineKeyboardButton("🏠 Menu Demo",     callback_data="demo:main")],
            ]))

    # ── Tarefa ───────────────────────────────
    elif step == "task_titulo":
        st["titulo"] = text; st["step"] = "task_desc"
        await u.message.reply_html(
            f"📋 <b>Nova Tarefa — 2/3</b>\n\nTítulo: <i>{text}</i>\n\nEnvia a <b>descrição/instrução</b>:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "task_desc":
        st["desc"] = text; st["step"] = "task_reward"
        await u.message.reply_html(
            "📋 <b>Nova Tarefa — 3/3</b>\n\nEnvia a <b>recompensa em USDT</b> (ex: <i>1.50</i>):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "task_reward":
        try:
            reward = Decimal(text.replace(",", "."))
        except Exception:
            await u.message.reply_html("❌ Valor inválido. Ex: <code>1.50</code>"); return
        st["reward"] = reward; st["step"] = "task_verif"
        await u.message.reply_html(
            "📋 <b>Tipo de verificação:</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ Auto — aprovação imediata", callback_data="gerir:task_verif:auto")],
                [InlineKeyboardButton("📤 Manual — user envia prova", callback_data="gerir:task_verif:manual")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")],
            ]))

    # ── Wallet ───────────────────────────────
    elif step == "wallet_label":
        st["label"] = text; st["step"] = "wallet_addr"
        await u.message.reply_html(
            f"💳 <b>Nova Wallet — 2/2</b>\n\nRede: <i>{text}</i>\n\nEnvia o <b>endereço</b>:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "wallet_addr":
        WALLETS.append({"id": _new_id("wallet"), "label": st["label"], "addr": text})
        _cancel_state(uid)
        await u.message.reply_html(
            f"✅ <b>Wallet adicionada!</b>\n\n💳 {st['label']}\n<code>{text}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Outra wallet", callback_data="gerir:add_wallet")],
                [InlineKeyboardButton("🔙 Gerir",        callback_data="gerir:wallets")],
                [InlineKeyboardButton("🏠 Menu Demo",    callback_data="demo:main")],
            ]))

    # ── Menu Builder ─────────────────────────
    elif step == "mb_icon":
        icon = text.split()[0] if text.split() else text
        st["icon"] = icon[:4]
        if st.get("editing") and uid in _umenu:
            _umenu[uid]["icon"] = st["icon"]
            _cancel_state(uid)
            menu = _umenu[uid]
            await u.message.reply_html(
                f"✅ {menu['icon']} <b>{menu['title']}</b>",
                reply_markup=kb([(t(uid, "mb_back_to_menu"), "mb:menu")]))
            return
        st["step"] = "mb_title"
        await u.message.reply_html(
            t(uid, "mb_step_title", icon=st["icon"]),
            reply_markup=kb([(t(uid, "proof_cancel"), "mb:cancel")]))

    elif step == "mb_title":
        existing = _umenu.get(uid, {"buttons": []})
        _umenu[uid] = {"icon": st["icon"], "title": text, "buttons": existing.get("buttons", [])}
        _cancel_state(uid)
        menu = _umenu[uid]
        await u.message.reply_html(
            t(uid, "mb_created", icon=menu["icon"], title=menu["title"]),
            reply_markup=kb(
                [(t(uid, "mb_btn_addbtn"), "mb:addbtn")],
                [(t(uid, "mb_back_to_menu"), "mb:menu")]
            ))

    elif step == "mb_btn_label":
        st["label"] = text; st["step"] = "mb_btn_type"
        await u.message.reply_html(
            t(uid, "mb_btn_step_type", label=text),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(uid, "mb_btn_type_link"),    callback_data="mb:btype:link")],
                [InlineKeyboardButton(t(uid, "mb_btn_type_text"),    callback_data="mb:btype:text")],
                [InlineKeyboardButton(t(uid, "mb_btn_type_submenu"), callback_data="mb:btype:submenu")],
                [InlineKeyboardButton(t(uid, "proof_cancel"), callback_data="mb:menu")],
            ]))

    elif step in ("mb_btn_value_link", "mb_btn_value_text", "mb_btn_value_submenu"):
        new_btn = {"id": _new_btn_id(), "label": st["label"], "type": st["btype"], "value": text}
        menu = _umenu.setdefault(uid, {"icon": "🎛️", "title": "Menu", "buttons": []})
        menu["buttons"].append(new_btn)
        _cancel_state(uid)
        await u.message.reply_html(
            t(uid, "mb_btn_added", icon=menu["icon"], label=new_btn["label"]),
            reply_markup=kb(
                [(t(uid, "mb_btn_addbtn"), "mb:addbtn")],
                [(t(uid, "mb_btn_open"), "mb:open")],
                [(t(uid, "mb_back_to_menu"), "mb:menu")]
            ))


        st["label"] = text; st["step"] = "canal_url"
        await u.message.reply_html(
            f"🔒 <b>Canal Guard — 2/2</b>\n\nNome: <i>{text}</i>\n\nEnvia o <b>link</b> (ex: <i>https://t.me/meucanal</i>):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "canal_url":
        CHANNELS.append({"id": _new_id("channel"), "label": st["label"], "url": text})
        _cancel_state(uid)
        await u.message.reply_html(
            f"✅ <b>Canal adicionado!</b>\n\n🔒 {st['label']}\n{text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Outro canal", callback_data="gerir:add_canal")],
                [InlineKeyboardButton("🔙 Gerir",       callback_data="gerir:canais")],
                [InlineKeyboardButton("🏠 Menu Demo",   callback_data="demo:main")],
            ]))

# ─────────────────────────────────────────────
#  Handlers principais
# ─────────────────────────────────────────────

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = u.effective_user
    uid  = user.id

    # Registar info do user
    _uinfo.setdefault(uid, {})
    _uinfo[uid].update({
        "username":  user.username,
        "full_name": user.full_name,
        "negocio":   _uinfo[uid].get("negocio") or user.first_name,
    })

    # Processar referral se presente
    for arg in (c.args or []):
        if arg.startswith("demo_ref_"):
            try: await proc_ref(c, user, int(arg[9:]))
            except: pass

    # Definir língua
    lang = get_lang(uid, user.language_code)
    _ulang.setdefault(uid, lang)

    # Se já esteve aqui antes, vai directo ao painel
    if uid in _onboard:
        await u.message.reply_html(
            f"👋 Bem-vindo de volta, <b>{user.first_name}</b>! O teu bot está a trabalhar. 🚀",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📊 Abrir painel", callback_data="demo:main")
            ]])
        )
        return

    # Primeiro acesso — entrada directa sem perguntas
    _onboard.add(uid)
    credit(uid, Decimal("5.00"), "bonus", "🎁 Bónus de boas-vindas")
    _start_sim(uid, c.bot)

    await u.message.reply_html(
        t(uid, "welcome", name=user.first_name),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(t(uid, "open_demo"), callback_data="demo:main")
        ]])
    )

async def cmd_lang(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    rows = [[InlineKeyboardButton(label, callback_data=f"setlang:{code}")] for code, label in LANG_OPTIONS]
    rows.append([InlineKeyboardButton("🔙 Menu", callback_data="demo:main")])
    await u.message.reply_html(t(uid, "lang_select"), reply_markup=InlineKeyboardMarkup(rows))

async def set_lang(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    uid = u.effective_user.id
    code = q.data.split(":")[1]
    if code in STRINGS:
        _ulang[uid] = code
    lang_name = STRINGS.get(code, {}).get("lang_name", code)
    rows = [[InlineKeyboardButton(label, callback_data=f"setlang:{c2}")] for c2, label in LANG_OPTIONS]
    rows.append([InlineKeyboardButton(t(uid, "btn_menu"), callback_data="demo:main")])
    await q.edit_message_text(
        t(uid, "lang_set", lang=lang_name) + "\n\n" + t(uid, "lang_select"),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows)
    )

def _mkb(uid):
    return kb(
        [(t(uid, "btn_store"), "demo:loja"),       (t(uid, "btn_tasks"), "demo:tarefas")],
        [(t(uid, "btn_ref"),   "demo:ref"),         (t(uid, "btn_balance"), "demo:saldo")],
        [(t(uid, "btn_guard"), "demo:guard"),       (t(uid, "btn_wallets"), "demo:wallets")],
        [(t(uid, "btn_menubuilder"), "mb:menu"),    (t(uid, "btn_lang"), "demo:lang")],
        [(t(uid, "btn_about"), "demo:sobre")],
        [("⚙️ Gerir Conteúdo", "gerir:menu")],
        [(t(uid, "btn_close"), "demo:fechar")],
    )

async def main_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    uid = u.effective_user.id; b = bal(uid)
    negocio = _uinfo.get(uid, {}).get("negocio", user_name(uid))

    membros  = 1 + _rcnt.get(uid, 0) * 3 + len(_tdone.get(uid, set())) * 2
    vendas   = len(_purch.get(uid, set())) + _rcnt.get(uid, 0)
    proj_dia = b * Decimal("2")   if b > 0 else Decimal("0")
    proj_mes = b * Decimal("60")  if b > 0 else Decimal("0")

    txt  = f"🤖 <b>{negocio} Bot</b>\n"
    txt += f"<i>powered by SAARS</i>\n"
    txt += f"━━━━━━━━━━━━━━━━\n"
    txt += f"👥 Membros activos: <b>{membros}</b>\n"
    txt += f"🛍️ Vendas processadas: <b>{vendas}</b>\n"
    txt += f"💰 Saldo acumulado: <b>{b:.2f} USDT</b>\n"
    if proj_mes > 0:
        txt += f"━━━━━━━━━━━━━━━━\n"
        txt += f"📈 Projecção diária: <b>~{proj_dia:.0f} USDT</b>\n"
        txt += f"🚀 Projecção mensal: <b>~{proj_mes:.0f} USDT</b>\n"
    txt += f"━━━━━━━━━━━━━━━━\n"
    txt += f"⚡ <i>O bot está a trabalhar agora mesmo.</i>\n"
    txt += f"\n👇 O que queres fazer?"

    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=_mkb(uid))

def user_name(uid: int) -> str:
    info = _uinfo.get(uid, {})
    return info.get("negocio") or info.get("full_name") or f"User {uid}"

async def lang_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    uid = u.effective_user.id
    rows = [[InlineKeyboardButton(label, callback_data=f"setlang:{code}")] for code, label in LANG_OPTIONS]
    rows.append([InlineKeyboardButton(t(uid, "btn_menu"), callback_data="demo:main")])
    await q.edit_message_text(t(uid, "lang_select"), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def sobre(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    await q.edit_message_text(
        t(uid, "about_text"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Quero o meu bot real →", url="https://t.me/SAARS_vBOT")],
            [InlineKeyboardButton("🔙 Voltar ao demo", callback_data="demo:main")],
        ])
    )

async def fechar(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    negocio = _uinfo.get(uid, {}).get("negocio", user_name(uid))
    b = bal(uid)
    vendas  = len(_purch.get(uid, set()))
    membros = 1 + _rcnt.get(uid, 0) * 3 + len(_tdone.get(uid, set())) * 2
    proj_mes = b * Decimal("60") if b > 0 else Decimal("0")
    txt  = f"⏸️ <b>Demo pausado.</b>\n\n"
    txt += f"Em {membros} minutos de demo, o <b>{negocio} Bot</b> gerou:\n\n"
    txt += f"💰 <b>{b:.2f} USDT</b> em saldo\n"
    txt += f"🛍️ <b>{vendas}</b> vendas processadas\n"
    txt += f"👥 <b>{membros}</b> membros activos\n"
    if proj_mes > 0:
        txt += f"\n📈 Ao ritmo actual → <b>~{proj_mes:.0f} USDT/mês</b> no bot real.\n"
    txt += f"\n🔴 <b>Tudo isto foi automático.</b>\n"
    txt += f"No bot real, é dinheiro real. Todos os dias.\n\n"
    txt += f"👇 Activa por <b>$20/mês</b> — menos que um café por dia:"
    await q.edit_message_text(
        txt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Quero o meu bot real →", url="https://t.me/SAARS_vBOT")],
            [InlineKeyboardButton("🔙 Continuar o demo",        callback_data="demo:main")],
        ])
    )

async def loja(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id; b = bal(uid)
    if not PRODUCTS:
        await q.edit_message_text(
            "🛍️ <b>Loja</b>\n\nNenhum produto ainda. Usa ⚙️ Gerir para adicionar.",
            parse_mode="HTML",
            reply_markup=kb([("⚙️ Gerir", "gerir:produtos"), (t(uid, "btn_menu"), "demo:main")])
        ); return
    rows = []
    for p in PRODUCTS:
        ok   = bought(uid, p["id"])
        mark = "✅ " if ok else ""
        rows.append([InlineKeyboardButton(f"{mark}{p['title']} — {p['price']} USDT", callback_data=f"pd:{p['id']}")])
    rows.append([InlineKeyboardButton(t(uid, "btn_menu"), callback_data="demo:main")])
    await q.edit_message_text(t(uid, "store_title", bal=f"{b:.2f}"),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def prod_detail(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[1])
    p   = next(x for x in PRODUCTS if x["id"] == pid)
    b   = bal(uid); ok = bought(uid, pid)
    txt = t(uid, "product_detail", title=p["title"], desc=p["desc"], price=p["price"], bal=f"{b:.2f}")
    if ok:
        txt += t(uid, "product_owned")
        rows = [[InlineKeyboardButton(t(uid, "btn_delivery"), callback_data=f"demo:redeliver:{pid}")],
                [InlineKeyboardButton(t(uid, "btn_back_store"), callback_data="demo:loja")]]
    else:
        rows = []
        if b >= p["price"]:
            rows.append([InlineKeyboardButton(t(uid, "btn_buy_bal", bal=f"{b:.2f}"), callback_data=f"demo:buybal:{pid}")])
        rows.append([InlineKeyboardButton(t(uid, "btn_buy_crypto"), callback_data=f"demo:buycrypto:{pid}")])
        rows.append([InlineKeyboardButton(t(uid, "btn_back_store"), callback_data="demo:loja")])
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def buybal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[2])
    p   = next(x for x in PRODUCTS if x["id"] == pid)
    if bought(uid, pid):
        return await q.edit_message_text(t(uid, "already_bought"),
            reply_markup=kb([(t(uid, "btn_back_store"), "demo:loja")]))
    if not debit(uid, p["price"], "purchase", p["title"]):
        return await q.edit_message_text(
            t(uid, "insufficient", price=p["price"]), parse_mode="HTML",
            reply_markup=kb([(t(uid, "btn_tasks_go"), "demo:tarefas")], [(t(uid, "btn_back_store"), "demo:loja")])
        )
    mbuy(uid, pid)
    negocio  = _uinfo.get(uid, {}).get("negocio", user_name(uid))
    primeira = len(_purch.get(uid, set())) == 1
    txt = t(uid, "purchase_ok", delivery=p["delivery"])
    if primeira:
        txt += (
            f"\n\n━━━━━━━━━━━━━━━━\n"
            f"🤯 <b>Acabaste de fazer a tua primeira venda.</b>\n\n"
            f"No bot real do <b>{negocio}</b>, este dinheiro é teu.\n"
            f"Automático. Sem esforço. 24 horas por dia.\n\n"
            f"<b>$20/mês</b> para ter isto a funcionar a sério:"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Quero o meu bot real →", url="https://t.me/SAARS_vBOT")],
            [InlineKeyboardButton("🔙 Continuar o demo",        callback_data="demo:loja")],
        ])
    else:
        markup = kb([(t(uid, "btn_back_store"), "demo:loja")])
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=markup)

async def buycrypto(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[2])
    p   = next(x for x in PRODUCTS if x["id"] == pid)
    wt  = "\n".join(f"• <b>{w['label']}</b>:\n  <code>{w['addr']}</code>" for w in WALLETS)
    if not wt: wt = "<i>Nenhuma wallet configurada.</i>"
    await q.edit_message_text(
        t(uid, "crypto_pay", title=p["title"], price=p["price"], wallets=wt),
        parse_mode="HTML",
        reply_markup=kb(
            [(t(uid, "btn_paid"), f"demo:confirm:{pid}")],
            [(t(uid, "btn_back_store"), "demo:loja")]
        )
    )

async def confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[2])
    p   = next(x for x in PRODUCTS if x["id"] == pid)
    mbuy(uid, pid)
    negocio  = _uinfo.get(uid, {}).get("negocio", user_name(uid))
    primeira = len(_purch.get(uid, set())) == 1
    txt = t(uid, "confirmed", delivery=p["delivery"])
    if primeira:
        txt += (
            f"\n\n━━━━━━━━━━━━━━━━\n"
            f"🤯 <b>Acabaste de fazer a tua primeira venda.</b>\n\n"
            f"No bot real do <b>{negocio}</b>, este dinheiro é teu.\n"
            f"Automático. Sem esforço. 24 horas por dia.\n\n"
            f"<b>$20/mês</b> para ter isto a funcionar a sério:"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Quero o meu bot real →", url="https://t.me/SAARS_vBOT")],
            [InlineKeyboardButton("🔙 Continuar o demo",        callback_data="demo:loja")],
        ])
    else:
        markup = kb([(t(uid, "btn_back_store"), "demo:loja")])
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=markup)

async def redeliver(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[2])
    p   = next(x for x in PRODUCTS if x["id"] == pid)
    await q.edit_message_text(t(uid, "delivery_title", delivery=p["delivery"]),
        parse_mode="HTML", reply_markup=kb([(t(uid, "btn_back_store"), "demo:loja")]))

async def tarefas(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id; b = bal(uid)
    if not TASKS:
        await q.edit_message_text(
            "📋 <b>Tarefas</b>\n\nNenhuma tarefa ainda. Usa ⚙️ Gerir para adicionar.",
            parse_mode="HTML",
            reply_markup=kb([("⚙️ Gerir", "gerir:tarefas"), (t(uid, "btn_menu"), "demo:main")])
        ); return
    rows = []
    for tk in TASKS:
        done = tdone(uid, tk["id"])
        mark = "✅ " if done else ""
        rows.append([InlineKeyboardButton(f"{mark}{tk['title']} (+{tk['reward']} USDT)", callback_data=f"td:{tk['id']}")])
    rows.append([InlineKeyboardButton(t(uid, "btn_menu"), callback_data="demo:main")])
    await q.edit_message_text(t(uid, "tasks_title", bal=f"{b:.2f}"),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def task_detail(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    tid  = int(q.data.split(":")[1])
    tk   = next(x for x in TASKS if x["id"] == tid)
    done = tdone(uid, tid)
    txt  = t(uid, "task_detail", title=tk["title"], desc=tk["desc"], reward=tk["reward"])
    if done:
        txt  += t(uid, "task_detail_done")
        rows  = [[InlineKeyboardButton(t(uid, "btn_back_tasks"), callback_data="demo:tarefas")]]
    else:
        btn  = t(uid, "btn_send_proof") if tk["verif"] == "manual" else t(uid, "btn_submit_task")
        cb   = f"demo:tproof:{tid}"    if tk["verif"] == "manual" else f"demo:tsubmit:{tid}"
        rows = [
            [InlineKeyboardButton(btn, callback_data=cb)],
            [InlineKeyboardButton(t(uid, "btn_back_tasks"), callback_data="demo:tarefas")],
        ]
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def tsubmit(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    tid = int(q.data.split(":")[2])
    tk  = next(x for x in TASKS if x["id"] == tid)
    if tdone(uid, tid):
        return await q.edit_message_text(t(uid, "task_already"),
            reply_markup=kb([(t(uid, "btn_back_tasks"), "demo:tarefas")]))
    mtask(uid, tid)
    nb = credit(uid, tk["reward"], "task", tk["title"])
    await q.edit_message_text(
        t(uid, "task_done", reward=tk["reward"], bal=f"{nb:.2f}"),
        parse_mode="HTML",
        reply_markup=kb(
            [(t(uid, "btn_back_tasks"), "demo:tarefas"),
             (t(uid, "btn_balance"), "demo:saldo")]
        )
    )

async def tproof(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    tid = int(q.data.split(":")[2])
    _twait[uid] = tid
    await q.edit_message_text(
        t(uid, "proof_wait"), parse_mode="HTML",
        reply_markup=kb([(t(uid, "proof_cancel"), "demo:tarefas")])
    )

async def handle_proof(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    tid = _twait.pop(uid, None)
    if tid is None: return
    tk = next((x for x in TASKS if x["id"] == tid), None)
    if not tk: return
    # BUG FIX: verificar se já foi concluída (evita crédito duplo)
    if tdone(uid, tid):
        await u.message.reply_html(
            t(uid, "task_already"),
            reply_markup=kb([(t(uid, "btn_back_tasks"), "demo:tarefas")])
        ); return
    mtask(uid, tid)
    nb = credit(uid, tk["reward"], "task", tk["title"])
    await u.message.reply_html(
        t(uid, "proof_ok", reward=tk["reward"], bal=f"{nb:.2f}"),
        reply_markup=kb(
            [(t(uid, "btn_back_tasks"), "demo:tarefas"),
             (t(uid, "btn_balance"), "demo:saldo")]
        )
    )

async def proc_ref(c, user, rid):
    uid = user.id
    if rid == uid or uid in _refs: return
    _uinfo[uid] = {"username": user.username, "full_name": user.full_name}
    _refs[uid]  = rid
    _rcnt[rid]  = _rcnt.get(rid, 0) + 1
    _rearn[rid] = _rearn.get(rid, Decimal("0")) + REFERRAL_REWARD
    credit(rid, REFERRAL_REWARD, "referral", f"Ref: {user.first_name}")
    try:
        await c.bot.send_message(
            rid,
            t(rid, "new_ref", name=user.first_name, reward=REFERRAL_REWARD),
            parse_mode="HTML",
            reply_markup=kb([(t(rid, "btn_balance"), "demo:saldo")])
        )
    except: pass

async def ref(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    me      = await c.bot.get_me()
    negocio = _uinfo.get(uid, {}).get("negocio", user_name(uid))
    lnk     = f"https://t.me/{me.username}?start=demo_ref_{uid}"
    cnt     = _rcnt.get(uid, 0)
    earn    = _rearn.get(uid, Decimal("0"))
    proj    = Decimal("100") * REFERRAL_REWARD
    await q.edit_message_text(
        f"👥 <b>Referral — {negocio}</b>\n\n"
        f"🔗 O teu link:\n<code>{lnk}</code>\n\n"
        f"👤 Membros convidados: <b>{cnt}</b>\n"
        f"💰 Ganhos de referral: <b>{earn:.2f} USDT</b>\n"
        f"🎁 Por cada convite: <b>{REFERRAL_REWARD} USDT</b>\n\n"
        f"📈 <i>Com 100 membros → <b>{proj:.0f} USDT</b> garantidos.</i>\n\n"
        f"<i>Partilha o link agora. Cada pessoa que entrar traz outras.</i>",
        parse_mode="HTML",
        reply_markup=kb(
            [(t(uid, "btn_ranking"), "demo:ranking")],
            [(t(uid, "btn_menu"),    "demo:main")]
        )
    )

async def ranking(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    top = sorted(_rcnt.items(), key=lambda x: x[1], reverse=True)[:10]
    if not top:
        txt = (
            "🏆 <b>Ranking de Indicações</b>\n\n"
            "Ainda sem membros no ranking.\n\n"
            "<i>No bot real, este ranking fica público para todos os membros.\n"
            "Cria competição natural — cada um quer estar no topo.\n"
            "O resultado: crescimento viral sem esforço teu.</i>"
        )
    else:
        medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
        lines  = ["🏆 <b>Top Indicadores</b>\n"]
        for i, (ruid, cnt) in enumerate(top):
            info = _uinfo.get(ruid, {})
            name = f"@{info['username']}" if info.get("username") else info.get("full_name", f"User {ruid}")
            lines.append(t(uid, "ranking_line", medal=medals[i], name=name, cnt=cnt,
                           earn=f"{_rearn.get(ruid, Decimal('0')):.2f}"))
        txt = "\n".join(lines)
    await q.edit_message_text(
        txt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Referral",               callback_data="demo:ref")],
            [InlineKeyboardButton("🚀 Quero isto no meu bot →", url="https://t.me/SAARS_vBOT")],
        ])
    )

async def saldo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id; b = bal(uid)
    txs   = _txs.get(uid, [])
    bloco = ""
    if txs:
        bloco = t(uid, "tx_header")
        icons = {"referral": "👥", "task": "📋", "purchase": "🛍️", "bonus": "🎁"}
        for tx in txs[-5:][::-1]:
            s     = "+" if tx["a"] > 0 else ""
            bloco += f"{icons.get(tx['t'], '💱')} {s}{tx['a']:.2f} USDT — {tx['n'] or tx['t']}\n"
    await q.edit_message_text(
        t(uid, "balance_title", bal=f"{b:.2f}") + bloco,
        parse_mode="HTML",
        reply_markup=kb(
            [(t(uid, "btn_saldo_tasks"), "demo:tarefas"),
             (t(uid, "btn_saldo_ref"),   "demo:ref")],
            [(t(uid, "btn_menu"), "demo:main")]
        )
    )

async def guard(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    if not CHANNELS:
        await q.edit_message_text(
            "🔒 <b>Canal Guard</b>\n\nNenhum canal cadastrado. Usa ⚙️ Gerir para adicionar.",
            parse_mode="HTML",
            reply_markup=kb([("⚙️ Gerir", "gerir:canais"), (t(uid, "btn_menu"), "demo:main")])
        ); return
    ch   = "\n".join(f"• {x['label']}: {x['url']}" for x in CHANNELS)
    rows = [[InlineKeyboardButton(x["label"], url=x["url"])] for x in CHANNELS]
    rows += [
        [InlineKeyboardButton(t(uid, "btn_verify"),  callback_data="demo:guard_ok")],
        [InlineKeyboardButton(t(uid, "btn_menu"),    callback_data="demo:main")],
    ]
    await q.edit_message_text(
        t(uid, "guard_title", channels=ch),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows), disable_web_page_preview=True
    )

async def guard_ok(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer("✅"); uid = u.effective_user.id
    await q.edit_message_text(
        t(uid, "guard_ok"), parse_mode="HTML",
        reply_markup=kb([(t(uid, "btn_home"), "demo:main")])
    )

async def wallets(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    if not WALLETS:
        await q.edit_message_text(
            "💳 <b>Carteiras</b>\n\nNenhuma wallet cadastrada. Usa ⚙️ Gerir para adicionar.",
            parse_mode="HTML",
            reply_markup=kb([("⚙️ Gerir", "gerir:wallets"), (t(uid, "btn_menu"), "demo:main")])
        ); return
    lines = []
    for w in WALLETS:
        qr = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={quote(w['addr'])}"
        lines.append(f"<b>{w['label']}</b>\n<code>{w['addr']}</code>\n🔗 <a href='{qr}'>Ver QR</a>")
    await q.edit_message_text(
        t(uid, "wallets_title") + "\n\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb([(t(uid, "btn_menu"), "demo:main")]),
        disable_web_page_preview=True
    )

# ─────────────────────────────────────────────
#  Menu Builder
# ─────────────────────────────────────────────

def _new_btn_id() -> str:
    return f"{random.randint(0, 9999):04d}"

def _mb_render_buttons(uid: int, buttons: list[dict], editing=False):
    rows = []
    for btn in buttons:
        if editing:
            rows.append([InlineKeyboardButton(f"🗑️ {btn['label']}", callback_data=f"mb:delbtn:{btn['id']}")])
        else:
            cb = {
                "link":    None,
                "text":    f"mb:run_text:{btn['id']}",
                "submenu": f"mb:run_sub:{btn['id']}",
            }.get(btn["type"])
            if btn["type"] == "link":
                rows.append([InlineKeyboardButton(btn["label"], url=btn["value"])])
            else:
                rows.append([InlineKeyboardButton(btn["label"], callback_data=cb)])
    return rows

async def mb_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    menu = _umenu.get(uid)
    txt = t(uid, "mb_intro")
    if not menu:
        txt += f"\n\n<i>{t(uid, 'mb_empty')}</i>"
        rows = [
            [InlineKeyboardButton(t(uid, "mb_btn_create"), callback_data="mb:create")],
            [InlineKeyboardButton(t(uid, "btn_menu"), callback_data="demo:main")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(t(uid, "mb_btn_open"),    callback_data="mb:open")],
            [InlineKeyboardButton(t(uid, "mb_btn_addbtn"),  callback_data="mb:addbtn")],
            [InlineKeyboardButton(t(uid, "mb_btn_editicon"),callback_data="mb:editicon")],
            [InlineKeyboardButton(t(uid, "mb_btn_edit"),    callback_data="mb:edit")],
            [InlineKeyboardButton(t(uid, "mb_btn_delete"),  callback_data="mb:delete")],
            [InlineKeyboardButton(t(uid, "btn_menu"), callback_data="demo:main")],
        ]
        n = len(menu["buttons"])
        txt += f"\n\n{menu['icon']} <b>{menu['title']}</b>\n📊 Botões: {n}/8"
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def mb_create(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "mb_icon"}
    await q.edit_message_text(
        t(uid, "mb_step_icon"), parse_mode="HTML",
        reply_markup=kb([(t(uid, "proof_cancel"), "mb:cancel")])
    )

async def mb_editicon(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "mb_icon", "editing": True}
    await q.edit_message_text(
        t(uid, "mb_step_icon"), parse_mode="HTML",
        reply_markup=kb([(t(uid, "proof_cancel"), "mb:menu")])
    )

async def mb_addbtn(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    menu = _umenu.get(uid)
    if menu and len(menu["buttons"]) >= 8:
        await q.answer(t(uid, "mb_max_buttons"), show_alert=True); return
    _state[uid] = {"step": "mb_btn_label"}
    await q.edit_message_text(
        t(uid, "mb_btn_step_label"), parse_mode="HTML",
        reply_markup=kb([(t(uid, "proof_cancel"), "mb:menu")])
    )

async def mb_btn_type(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    btype = q.data.split(":")[2]
    st = _state.get(uid, {})
    if st.get("step") != "mb_btn_type":
        await q.answer("⚠️ Sessão expirada.", show_alert=True); return
    st["btype"] = btype
    if btype == "link":
        st["step"] = "mb_btn_value_link"
        await q.edit_message_text(t(uid, "mb_btn_step_link"), parse_mode="HTML",
            reply_markup=kb([(t(uid, "proof_cancel"), "mb:menu")]))
    elif btype == "text":
        st["step"] = "mb_btn_value_text"
        await q.edit_message_text(t(uid, "mb_btn_step_text"), parse_mode="HTML",
            reply_markup=kb([(t(uid, "proof_cancel"), "mb:menu")]))
    else:
        st["step"] = "mb_btn_value_submenu"
        await q.edit_message_text(t(uid, "mb_btn_step_submenu_title"), parse_mode="HTML",
            reply_markup=kb([(t(uid, "proof_cancel"), "mb:menu")]))

async def mb_delbtn(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    bid = q.data.split(":")[2]
    menu = _umenu.get(uid)
    if menu:
        menu["buttons"] = [b for b in menu["buttons"] if b["id"] != bid]
    await q.answer(t(uid, "mb_btn_deleted"))
    await mb_edit(u, c)

async def mb_edit(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    menu = _umenu.get(uid)
    if not menu:
        return await mb_menu(u, c)
    txt = f"✏️ <b>{t(uid, 'mb_btn_edit')}</b>\n\n{menu['icon']} <b>{menu['title']}</b>\n\nClica para remover:"
    rows = _mb_render_buttons(uid, menu["buttons"], editing=True)
    if not menu["buttons"]:
        txt += f"\n\n{t(uid, 'mb_no_buttons')}"
    rows.append([InlineKeyboardButton(t(uid, "mb_btn_addbtn"), callback_data="mb:addbtn")])
    rows.append([InlineKeyboardButton(t(uid, "mb_back_to_menu"), callback_data="mb:menu")])
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def mb_delete(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _umenu.pop(uid, None)
    await q.edit_message_text(
        t(uid, "mb_deleted"), parse_mode="HTML",
        reply_markup=kb([(t(uid, "btn_menu"), "demo:main")])
    )

async def mb_open(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    menu = _umenu.get(uid)
    if not menu or not menu["buttons"]:
        return await q.edit_message_text(
            t(uid, "mb_open_empty"), parse_mode="HTML",
            reply_markup=kb([(t(uid, "btn_menubuilder"), "mb:menu"), (t(uid, "btn_menu"), "demo:main")])
        )
    rows = _mb_render_buttons(uid, menu["buttons"])
    rows.append([InlineKeyboardButton(t(uid, "btn_menu"), callback_data="demo:main")])
    txt = f"{menu['icon']} <b>{menu['title']}</b>" + t(uid, "mb_psych")
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def mb_run_text(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    bid  = q.data.split(":")[2]
    menu = _umenu.get(uid)
    btn  = next((b for b in menu["buttons"] if b["id"] == bid), None) if menu else None
    if not btn: return
    await q.edit_message_text(
        f"💬 {btn['value']}",
        parse_mode="HTML",
        reply_markup=kb([(t(uid, "mb_back_to_menu"), "mb:open")])
    )

async def mb_run_sub(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    bid  = q.data.split(":")[2]
    menu = _umenu.get(uid)
    btn  = next((b for b in menu["buttons"] if b["id"] == bid), None) if menu else None
    if not btn: return
    await q.edit_message_text(
        f"📂 <b>{btn['value']}</b>\n\n<i>Submenu de demonstração — vazio neste preview.\n"
        f"No bot real, podes adicionar botões dentro deste submenu também.</i>",
        parse_mode="HTML",
        reply_markup=kb([(t(uid, "mb_back_to_menu"), "mb:open")])
    )

async def mb_cancel(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _cancel_state(uid)
    await mb_menu(u, c)



EXACT = {
    "demo:main":     main_menu, "demo:sobre":    sobre,    "demo:fechar":   fechar,
    "demo:loja":     loja,      "demo:tarefas":  tarefas,  "demo:ref":      ref,
    "demo:ranking":  ranking,   "demo:saldo":    saldo,    "demo:guard":    guard,
    "demo:guard_ok": guard_ok,  "demo:wallets":  wallets,  "demo:lang":     lang_menu,
    "gerir:menu":        gerir,
    "gerir:produtos":    gerir_produtos,
    "gerir:tarefas":     gerir_tarefas,
    "gerir:wallets":     gerir_wallets,
    "gerir:canais":      gerir_canais,
    "gerir:add_produto": gerir_add_produto,
    "gerir:add_tarefa":  gerir_add_tarefa,
    "gerir:add_wallet":  gerir_add_wallet,
    "gerir:add_canal":   gerir_add_canal,
    "gerir:cancel":      gerir_cancel,
    "mb:menu":     mb_menu,
    "mb:create":   mb_create,
    "mb:editicon": mb_editicon,
    "mb:addbtn":   mb_addbtn,
    "mb:edit":     mb_edit,
    "mb:delete":   mb_delete,
    "mb:open":     mb_open,
    "mb:cancel":   mb_cancel,
}
PREFIX = {
    "pd:":                prod_detail,
    "demo:buybal:":       buybal,
    "demo:buycrypto:":    buycrypto,
    "demo:confirm:":      confirm,
    "demo:redeliver:":    redeliver,
    "td:":                task_detail,
    "demo:tsubmit:":      tsubmit,
    "demo:tproof:":       tproof,
    "setlang:":           set_lang,
    "gerir:del_produto:": gerir_del_produto,
    "gerir:del_tarefa:":  gerir_del_tarefa,
    "gerir:del_wallet:":  gerir_del_wallet,
    "gerir:del_canal:":   gerir_del_canal,
    "gerir:task_verif:":  _gerir_task_verif_cb,
    "mb:delbtn:":  mb_delbtn,
    "mb:run_text:": mb_run_text,
    "mb:run_sub:":  mb_run_sub,
    "mb:btype:":    mb_btn_type,
}

async def router(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not q: return
    data = q.data or ""
    if data in EXACT:
        return await EXACT[data](u, c)
    for pfx, fn in PREFIX.items():
        if data.startswith(pfx):
            return await fn(u, c)
    log.warning(f"Callback desconhecido: {data}")

# ─────────────────────────────────────────────
#  Boot
# ─────────────────────────────────────────────

async def run():
    port = int(os.environ.get("PORT", 10000))

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a): pass

    threading.Thread(
        target=lambda: http.server.HTTPServer(("0.0.0.0", port), _H).serve_forever(),
        daemon=True
    ).start()
    log.info(f"🌐 HTTP keepalive em :{port}")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("lang",  cmd_lang))
    app.add_handler(CallbackQueryHandler(router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_proof))

    log.info("🚀 SAARS Demo Bot online — marketing psicológico · n18n 10 línguas · zero fricção")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(run())
