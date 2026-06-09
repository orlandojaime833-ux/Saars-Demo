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

TOKEN           = "8898427762:AAH-ieOsrQ4Y-Hwi8IvPXxe4fnKAyjVa0qs"
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
_onboard: set[int]         = {}   # uids que já completaram onboarding

# ─────────────────────────────────────────────
#  Simulador de actividade em tempo real
#  A cada 10s: +1 membro fictício entra pelo
#  referral do prospect E compra o produto mais
#  barato — o saldo acumula no balance real.
# ─────────────────────────────────────────────

_FAKE_NAMES = [
    "Carlos Silva","Ana Ferreira","Bruno Costa","Mariana Souza","Pedro Alves",
    "Juliana Lima","Ricardo Gomes","Fernanda Rocha","Thiago Martins","Camila Dias",
    "Lucas Pereira","Beatriz Nunes","Gabriel Carvalho","Larissa Mendes","Rafael Torres",
    "Priya Sharma","Mohammed Al-Rashid","Wei Zhang","Sofia Müller","Amara Diallo",
    "Yuki Tanaka","Isabella Rossi","Alejandro García","Fatima Hassan","Kwame Osei",
]
import random, itertools
_name_cycle: dict[int, itertools.cycle] = {}   # uid → ciclo de nomes

# uid → asyncio.Task do simulador
_sim_tasks: dict[int, asyncio.Task] = {}

async def _simulador(uid: int, bot):
    """Corre em background: a cada 10s injeta 1 membro + 1 compra."""
    global _rcnt, _rearn
    cycle = _name_cycle.setdefault(uid, itertools.cycle(random.sample(_FAKE_NAMES, len(_FAKE_NAMES))))
    # produto mais barato disponível
    while True:
        await asyncio.sleep(10)
        # escolhe produto mais barato
        if not PRODUCTS: continue
        prod = min(PRODUCTS, key=lambda p: p["price"])
        nome = next(cycle)
        fake_uid = -(abs(hash(f"{uid}:{nome}")) % 10_000_000)  # uid fictício negativo

        # registar como referral do prospect
        _uinfo[fake_uid]  = {"username": None, "full_name": nome, "negocio": ""}
        _rcnt[uid]        = _rcnt.get(uid, 0) + 1
        earn_ref          = REFERRAL_REWARD
        _rearn[uid]       = _rearn.get(uid, Decimal("0")) + earn_ref
        credit(uid, earn_ref, "referral", f"👥 {nome} entrou")

        # fake compra o produto — receita vai para o prospect
        receita_venda = prod["price"] * Decimal("0.30")   # 30% de comissão demo
        credit(uid, receita_venda, "purchase", f"🛍️ {nome} comprou {prod['title'][:20]}")

        # notificação push ao prospect
        membros  = 1 + _rcnt.get(uid, 0) * 3 + len(_tdone.get(uid, set())) * 2
        b        = bal(uid)
        negocio  = _uinfo.get(uid, {}).get("negocio", "o teu bot")
        try:
            await bot.send_message(
                uid,
                f"🔔 <b>Actividade no {negocio} Bot!</b>\n\n"
                f"👤 <b>{nome}</b> entrou pelo teu link\n"
                f"🛍️ Comprou <b>{prod['title'][:30]}</b>\n"
                f"💰 <b>+{earn_ref + receita_venda:.2f} USDT</b> creditados\n\n"
                f"📊 Total de membros: <b>{membros}</b> · Saldo: <b>{b:.2f} USDT</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 Ver painel", callback_data="demo:main")],
                    [InlineKeyboardButton("🚀 Quero o bot real →", url="https://t.me/SAARS_vBOT")],
                ])
            )
        except Exception:
            pass   # user bloqueou o bot ou saiu

def _start_sim(uid: int, bot):
    """Inicia o simulador para um uid, cancelando qualquer um anterior."""
    if uid in _sim_tasks and not _sim_tasks[uid].done():
        _sim_tasks[uid].cancel()
    _sim_tasks[uid] = asyncio.create_task(_simulador(uid, bot))

# ─────────────────────────────────────────────
#  N18N — 10 most spoken languages
# ─────────────────────────────────────────────

STRINGS: dict[str, dict[str, str]] = {

    # ── Portuguese ──────────────────────────────
    "pt": {
        "lang_name": "🇧🇷 Português",
        "welcome": "👋 Olá <b>{name}</b>!\n\n🚀 <b>SAARS Demo Bot</b>\n\nTesta todos os módulos em tempo real — loja, tarefas, referral, saldo e muito mais.\n\n👇 Clica para começar:",
        "open_demo": "🚀 Abrir Demo",
        "main_title": "🚀 <b>SAARS — Demo Interativo</b>\n\nTesta todos os módulos em tempo real.",
        "balance_line": "💰 Teu saldo: <b>{bal} USDT</b>",
        "choose_section": "👇 Escolhe uma secção:",
        "btn_store": "🛍️ Loja", "btn_tasks": "📋 Tarefas", "btn_ref": "👥 Referral",
        "btn_balance": "💰 Meu Saldo", "btn_guard": "🔒 Canal Guard", "btn_wallets": "💳 Carteiras",
        "btn_about": "ℹ️ Sobre o SAARS", "btn_close": "❌ Fechar", "btn_menu": "🔙 Menu",
        "btn_back_store": "🔙 Loja", "btn_back_tasks": "🔙 Tarefas", "btn_back_ref": "🔙 Referral",
        "btn_ranking": "🏆 Ranking", "btn_reopen": "🚀 Reabrir", "btn_home": "🏠 Menu Demo",
        "btn_tasks_go": "📋 Ver Tarefas", "btn_buy_bal": "💰 Comprar com saldo ({bal} USDT)",
        "btn_buy_crypto": "💳 Pagar com crypto (demo)", "btn_paid": "✅ Já paguei",
        "btn_delivery": "📦 Ver entrega", "btn_verify": "✅ Verificar adesão (demo)",
        "btn_saldo_tasks": "📋 Tarefas", "btn_saldo_ref": "👥 Referral",
        "about_text": (
            "ℹ️ <b>O que é o SAARS?</b>\n\n"
            "Plataforma SaaS para criar bots Telegram white-label com monetização completa.\n\n"
            "<b>Inclui:</b>\n• 🎨 Menu Builder\n• 🛍️ Loja com entrega automática\n• 📋 Tarefas pagas\n"
            "• 👥 Referral com ranking\n• 💰 Saldo interno\n• 🔒 Canal Guard\n"
            "• 💳 Crypto: TON · BEP20 · TRC20 · SOL\n\n"
            "<b>Plano Pro:</b> $20/mês · todos os módulos activos."
        ),
        "closed": "✅ Demo encerrado. Usa /start para voltar.",
        "store_title": "🛍️ <b>Loja de Infoprodutos</b>\n\n💰 Teu saldo: <b>{bal} USDT</b>\n\nEscolhe um produto:",
        "already_bought": "✅ Já compraste.",
        "insufficient": "❌ <b>Saldo insuficiente.</b>\n\nPrecisas de {price} USDT.",
        "purchase_ok": "✅ <b>Compra realizada!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Pagamento Crypto</b>\n\nProduto: {title}\nValor: <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>Clica 'Já paguei' após enviar.</i>",
        "confirmed": "✅ <b>Confirmado!</b>\n<i>[Demo: aprovação automática]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Entrega</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Tarefas Pagas</b>\n\n💰 Teu saldo: <b>{bal} USDT</b>\n\nCompleta e recebe automaticamente:",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>Tarefa concluída!</b>\n\n+{reward} USDT\nNovo saldo: <b>{bal} USDT</b>\n\n<i>[Demo: verificação automática]</i>",
        "task_already": "✅ Já concluída!",
        "proof_wait": "📤 <b>Envio de Comprovante</b>\n\nEnvia agora uma foto ou ficheiro.",
        "proof_cancel": "❌ Cancelar",
        "proof_ok": "✅ <b>Comprovante aprovado!</b>\n\n+{reward} USDT\nNovo saldo: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Referral</b>\n\n🔗 Teu link:\n<code>{link}</code>\n\n👤 Indicações: <b>{cnt}</b>\n💰 Ganhos: <b>{earn} USDT</b>\n🎁 Por indicação: <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>Ranking</b>\n\nAinda sem indicações!",
        "ranking_title": "🏆 <b>Top Indicadores</b>\n",
        "ranking_line": "{medal} {name} — {cnt} ref · {earn} USDT",
        "new_ref": "🎉 <b>Nova indicação!</b>\n\n{name} entrou pelo teu link.\n+{reward} USDT creditado!",
        "balance_title": "💰 <b>Meu Saldo</b>\n\nSaldo actual: <b>{bal} USDT</b>\n\nGanhas completando tarefas e indicando amigos.",
        "tx_header": "\n\n📜 <b>Últimas transações:</b>\n",
        "guard_title": "🔒 <b>Canal Guard</b>\n\nBloqueia o acesso até o utilizador ser membro.\n\n<b>Canais:</b>\n{channels}\n\n✅ <i>No demo o acesso é sempre permitido.</i>",
        "guard_ok": "✅ <b>Verificação concluída!</b>\n\nMenu desbloqueado.",
        "wallets_title": "💳 <b>Carteiras de Pagamento</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Teu saldo: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Já compraste este produto</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Recompensa: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Já concluída!</b>",
        "btn_submit_task": "✅ Concluir tarefa",
        "btn_send_proof": "📤 Enviar comprovante",
        "lang_select": "🌐 <b>Idioma / Language</b>\n\nEscolhe o teu idioma:",
        "lang_set": "✅ Idioma definido: {lang}",
        "btn_lang": "🌐 Idioma",
    },

    # ── English ──────────────────────────────────
    "en": {
        "lang_name": "🇬🇧 English",
        "welcome": "👋 Hello <b>{name}</b>!\n\n🚀 <b>SAARS Demo Bot</b>\n\nTest all modules in real time — store, tasks, referral, balance and more.\n\n👇 Click to begin:",
        "open_demo": "🚀 Open Demo",
        "main_title": "🚀 <b>SAARS — Interactive Demo</b>\n\nTest all modules in real time.",
        "balance_line": "💰 Your balance: <b>{bal} USDT</b>",
        "choose_section": "👇 Choose a section:",
        "btn_store": "🛍️ Store", "btn_tasks": "📋 Tasks", "btn_ref": "👥 Referral",
        "btn_balance": "💰 My Balance", "btn_guard": "🔒 Channel Guard", "btn_wallets": "💳 Wallets",
        "btn_about": "ℹ️ About SAARS", "btn_close": "❌ Close", "btn_menu": "🔙 Menu",
        "btn_back_store": "🔙 Store", "btn_back_tasks": "🔙 Tasks", "btn_back_ref": "🔙 Referral",
        "btn_ranking": "🏆 Ranking", "btn_reopen": "🚀 Reopen", "btn_home": "🏠 Demo Menu",
        "btn_tasks_go": "📋 See Tasks", "btn_buy_bal": "💰 Buy with balance ({bal} USDT)",
        "btn_buy_crypto": "💳 Pay with crypto (demo)", "btn_paid": "✅ I already paid",
        "btn_delivery": "📦 View delivery", "btn_verify": "✅ Verify membership (demo)",
        "btn_saldo_tasks": "📋 Tasks", "btn_saldo_ref": "👥 Referral",
        "about_text": (
            "ℹ️ <b>What is SAARS?</b>\n\n"
            "SaaS platform to create white-label Telegram bots with full monetization.\n\n"
            "<b>Includes:</b>\n• 🎨 Menu Builder\n• 🛍️ Store with automatic delivery\n• 📋 Paid Tasks\n"
            "• 👥 Referral with ranking\n• 💰 Internal balance\n• 🔒 Channel Guard\n"
            "• 💳 Crypto: TON · BEP20 · TRC20 · SOL\n\n"
            "<b>Pro Plan:</b> $20/month · all modules active."
        ),
        "closed": "✅ Demo closed. Use /start to return.",
        "store_title": "🛍️ <b>Digital Products Store</b>\n\n💰 Your balance: <b>{bal} USDT</b>\n\nChoose a product:",
        "already_bought": "✅ Already purchased.",
        "insufficient": "❌ <b>Insufficient balance.</b>\n\nYou need {price} USDT.",
        "purchase_ok": "✅ <b>Purchase successful!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Crypto Payment</b>\n\nProduct: {title}\nAmount: <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>Click 'I already paid' after sending.</i>",
        "confirmed": "✅ <b>Confirmed!</b>\n<i>[Demo: automatic approval]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Delivery</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Paid Tasks</b>\n\n💰 Your balance: <b>{bal} USDT</b>\n\nComplete and earn automatically:",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>Task completed!</b>\n\n+{reward} USDT\nNew balance: <b>{bal} USDT</b>\n\n<i>[Demo: automatic verification]</i>",
        "task_already": "✅ Already completed!",
        "proof_wait": "📤 <b>Submit Proof</b>\n\nSend a photo or file now.",
        "proof_cancel": "❌ Cancel",
        "proof_ok": "✅ <b>Proof approved!</b>\n\n+{reward} USDT\nNew balance: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Referral</b>\n\n🔗 Your link:\n<code>{link}</code>\n\n👤 Referrals: <b>{cnt}</b>\n💰 Earnings: <b>{earn} USDT</b>\n🎁 Per referral: <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>Ranking</b>\n\nNo referrals yet!",
        "ranking_title": "🏆 <b>Top Referrers</b>\n",
        "ranking_line": "{medal} {name} — {cnt} ref · {earn} USDT",
        "new_ref": "🎉 <b>New referral!</b>\n\n{name} joined via your link.\n+{reward} USDT credited!",
        "balance_title": "💰 <b>My Balance</b>\n\nCurrent balance: <b>{bal} USDT</b>\n\nEarn by completing tasks and referring friends.",
        "tx_header": "\n\n📜 <b>Recent transactions:</b>\n",
        "guard_title": "🔒 <b>Channel Guard</b>\n\nBlocks access until the user is a member.\n\n<b>Channels:</b>\n{channels}\n\n✅ <i>In demo access is always granted.</i>",
        "guard_ok": "✅ <b>Verification complete!</b>\n\nMenu unlocked.",
        "wallets_title": "💳 <b>Payment Wallets</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Your balance: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Already purchased</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Reward: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Already completed!</b>",
        "btn_submit_task": "✅ Complete task",
        "btn_send_proof": "📤 Send proof",
        "lang_select": "🌐 <b>Language</b>\n\nChoose your language:",
        "lang_set": "✅ Language set: {lang}",
        "btn_lang": "🌐 Language",
    },

    # ── Spanish ──────────────────────────────────
    "es": {
        "lang_name": "🇪🇸 Español",
        "welcome": "👋 ¡Hola <b>{name}</b>!\n\n🚀 <b>SAARS Demo Bot</b>\n\nPrueba todos los módulos en tiempo real — tienda, tareas, referral, saldo y más.\n\n👇 Haz clic para empezar:",
        "open_demo": "🚀 Abrir Demo",
        "main_title": "🚀 <b>SAARS — Demo Interactivo</b>\n\nPrueba todos los módulos en tiempo real.",
        "balance_line": "💰 Tu saldo: <b>{bal} USDT</b>",
        "choose_section": "👇 Elige una sección:",
        "btn_store": "🛍️ Tienda", "btn_tasks": "📋 Tareas", "btn_ref": "👥 Referral",
        "btn_balance": "💰 Mi Saldo", "btn_guard": "🔒 Canal Guard", "btn_wallets": "💳 Carteras",
        "btn_about": "ℹ️ Sobre SAARS", "btn_close": "❌ Cerrar", "btn_menu": "🔙 Menú",
        "btn_back_store": "🔙 Tienda", "btn_back_tasks": "🔙 Tareas", "btn_back_ref": "🔙 Referral",
        "btn_ranking": "🏆 Ranking", "btn_reopen": "🚀 Reabrir", "btn_home": "🏠 Menú Demo",
        "btn_tasks_go": "📋 Ver Tareas", "btn_buy_bal": "💰 Comprar con saldo ({bal} USDT)",
        "btn_buy_crypto": "💳 Pagar con crypto (demo)", "btn_paid": "✅ Ya pagué",
        "btn_delivery": "📦 Ver entrega", "btn_verify": "✅ Verificar membresía (demo)",
        "btn_saldo_tasks": "📋 Tareas", "btn_saldo_ref": "👥 Referral",
        "about_text": (
            "ℹ️ <b>¿Qué es SAARS?</b>\n\n"
            "Plataforma SaaS para crear bots de Telegram white-label con monetización completa.\n\n"
            "<b>Incluye:</b>\n• 🎨 Menu Builder\n• 🛍️ Tienda con entrega automática\n• 📋 Tareas pagas\n"
            "• 👥 Referral con ranking\n• 💰 Saldo interno\n• 🔒 Canal Guard\n"
            "• 💳 Crypto: TON · BEP20 · TRC20 · SOL\n\n"
            "<b>Plan Pro:</b> $20/mes · todos los módulos activos."
        ),
        "closed": "✅ Demo cerrado. Usa /start para volver.",
        "store_title": "🛍️ <b>Tienda de Infoproductos</b>\n\n💰 Tu saldo: <b>{bal} USDT</b>\n\nElige un producto:",
        "already_bought": "✅ Ya compraste esto.",
        "insufficient": "❌ <b>Saldo insuficiente.</b>\n\nNecesitas {price} USDT.",
        "purchase_ok": "✅ <b>¡Compra realizada!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Pago Crypto</b>\n\nProducto: {title}\nValor: <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>Haz clic en 'Ya pagué' después de enviar.</i>",
        "confirmed": "✅ <b>¡Confirmado!</b>\n<i>[Demo: aprobación automática]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Entrega</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Tareas Pagas</b>\n\n💰 Tu saldo: <b>{bal} USDT</b>\n\nCompleta y recibe automáticamente:",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>¡Tarea completada!</b>\n\n+{reward} USDT\nNuevo saldo: <b>{bal} USDT</b>\n\n<i>[Demo: verificación automática]</i>",
        "task_already": "✅ ¡Ya completada!",
        "proof_wait": "📤 <b>Envío de Comprobante</b>\n\nEnvía ahora una foto o archivo.",
        "proof_cancel": "❌ Cancelar",
        "proof_ok": "✅ <b>¡Comprobante aprobado!</b>\n\n+{reward} USDT\nNuevo saldo: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Referral</b>\n\n🔗 Tu enlace:\n<code>{link}</code>\n\n👤 Referidos: <b>{cnt}</b>\n💰 Ganancias: <b>{earn} USDT</b>\n🎁 Por referido: <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>Ranking</b>\n\n¡Aún sin referidos!",
        "ranking_title": "🏆 <b>Top Referidores</b>\n",
        "ranking_line": "{medal} {name} — {cnt} ref · {earn} USDT",
        "new_ref": "🎉 <b>¡Nuevo referido!</b>\n\n{name} entró por tu enlace.\n+{reward} USDT acreditado!",
        "balance_title": "💰 <b>Mi Saldo</b>\n\nSaldo actual: <b>{bal} USDT</b>\n\nGanas completando tareas y refiriendo amigos.",
        "tx_header": "\n\n📜 <b>Últimas transacciones:</b>\n",
        "guard_title": "🔒 <b>Canal Guard</b>\n\nBloquea el acceso hasta que el usuario sea miembro.\n\n<b>Canales:</b>\n{channels}\n\n✅ <i>En el demo el acceso siempre está permitido.</i>",
        "guard_ok": "✅ <b>¡Verificación completa!</b>\n\nMenú desbloqueado.",
        "wallets_title": "💳 <b>Carteras de Pago</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Tu saldo: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Ya compraste este producto</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Recompensa: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>¡Ya completada!</b>",
        "btn_submit_task": "✅ Completar tarea",
        "btn_send_proof": "📤 Enviar comprobante",
        "lang_select": "🌐 <b>Idioma / Language</b>\n\nElige tu idioma:",
        "lang_set": "✅ Idioma establecido: {lang}",
        "btn_lang": "🌐 Idioma",
    },

    # ── Mandarin Chinese ─────────────────────────
    "zh": {
        "lang_name": "🇨🇳 中文",
        "welcome": "👋 你好 <b>{name}</b>！\n\n🚀 <b>SAARS 演示机器人</b>\n\n实时测试所有模块——商店、任务、推荐、余额等。\n\n👇 点击开始：",
        "open_demo": "🚀 打开演示",
        "main_title": "🚀 <b>SAARS — 交互演示</b>\n\n实时测试所有模块。",
        "balance_line": "💰 您的余额：<b>{bal} USDT</b>",
        "choose_section": "👇 选择一个板块：",
        "btn_store": "🛍️ 商店", "btn_tasks": "📋 任务", "btn_ref": "👥 推荐",
        "btn_balance": "💰 我的余额", "btn_guard": "🔒 频道守卫", "btn_wallets": "💳 钱包",
        "btn_about": "ℹ️ 关于 SAARS", "btn_close": "❌ 关闭", "btn_menu": "🔙 菜单",
        "btn_back_store": "🔙 商店", "btn_back_tasks": "🔙 任务", "btn_back_ref": "🔙 推荐",
        "btn_ranking": "🏆 排行榜", "btn_reopen": "🚀 重新打开", "btn_home": "🏠 演示菜单",
        "btn_tasks_go": "📋 查看任务", "btn_buy_bal": "💰 用余额购买（{bal} USDT）",
        "btn_buy_crypto": "💳 用加密货币支付（演示）", "btn_paid": "✅ 我已支付",
        "btn_delivery": "📦 查看交付", "btn_verify": "✅ 验证会员（演示）",
        "btn_saldo_tasks": "📋 任务", "btn_saldo_ref": "👥 推荐",
        "about_text": (
            "ℹ️ <b>什么是 SAARS？</b>\n\n"
            "用于创建具有完整货币化功能的白标 Telegram 机器人的 SaaS 平台。\n\n"
            "<b>包含：</b>\n• 🎨 菜单构建器\n• 🛍️ 自动交付商店\n• 📋 付费任务\n"
            "• 👥 推荐排行榜\n• 💰 内部余额\n• 🔒 频道守卫\n"
            "• 💳 加密货币：TON · BEP20 · TRC20 · SOL\n\n"
            "<b>专业版：</b> $20/月 · 所有模块激活。"
        ),
        "closed": "✅ 演示已关闭。使用 /start 返回。",
        "store_title": "🛍️ <b>数字产品商店</b>\n\n💰 您的余额：<b>{bal} USDT</b>\n\n选择产品：",
        "already_bought": "✅ 已购买。",
        "insufficient": "❌ <b>余额不足。</b>\n\n您需要 {price} USDT。",
        "purchase_ok": "✅ <b>购买成功！</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>加密货币支付</b>\n\n产品：{title}\n金额：<b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>发送后点击「我已支付」。</i>",
        "confirmed": "✅ <b>已确认！</b>\n<i>[演示：自动批准]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>交付</b>\n\n{delivery}",
        "tasks_title": "📋 <b>付费任务</b>\n\n💰 您的余额：<b>{bal} USDT</b>\n\n完成任务自动获得奖励：",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>任务完成！</b>\n\n+{reward} USDT\n新余额：<b>{bal} USDT</b>\n\n<i>[演示：自动验证]</i>",
        "task_already": "✅ 已完成！",
        "proof_wait": "📤 <b>提交证明</b>\n\n现在发送照片或文件。",
        "proof_cancel": "❌ 取消",
        "proof_ok": "✅ <b>证明已批准！</b>\n\n+{reward} USDT\n新余额：<b>{bal} USDT</b>",
        "ref_title": "👥 <b>推荐</b>\n\n🔗 您的链接：\n<code>{link}</code>\n\n👤 推荐数：<b>{cnt}</b>\n💰 收益：<b>{earn} USDT</b>\n🎁 每次推荐：<b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>排行榜</b>\n\n暂无推荐！",
        "ranking_title": "🏆 <b>推荐排行榜</b>\n",
        "ranking_line": "{medal} {name} — {cnt} 推荐 · {earn} USDT",
        "new_ref": "🎉 <b>新推荐！</b>\n\n{name} 通过您的链接加入。\n+{reward} USDT 已到账！",
        "balance_title": "💰 <b>我的余额</b>\n\n当前余额：<b>{bal} USDT</b>\n\n通过完成任务和推荐好友赚取收益。",
        "tx_header": "\n\n📜 <b>最近交易：</b>\n",
        "guard_title": "🔒 <b>频道守卫</b>\n\n在用户成为成员之前阻止访问。\n\n<b>频道：</b>\n{channels}\n\n✅ <i>在演示中访问始终被允许。</i>",
        "guard_ok": "✅ <b>验证完成！</b>\n\n菜单已解锁。",
        "wallets_title": "💳 <b>支付钱包</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 您的余额：<b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>已购买此产品</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 奖励：<b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>已完成！</b>",
        "btn_submit_task": "✅ 完成任务",
        "btn_send_proof": "📤 发送证明",
        "lang_select": "🌐 <b>语言 / Language</b>\n\n选择您的语言：",
        "lang_set": "✅ 语言已设置：{lang}",
        "btn_lang": "🌐 语言",
    },

    # ── Hindi ────────────────────────────────────
    "hi": {
        "lang_name": "🇮🇳 हिंदी",
        "welcome": "👋 नमस्ते <b>{name}</b>!\n\n🚀 <b>SAARS Demo Bot</b>\n\nसभी मॉड्यूल रियल टाइम में टेस्ट करें — स्टोर, टास्क, रेफरल, बैलेंस और बहुत कुछ।\n\n👇 शुरू करने के लिए क्लिक करें:",
        "open_demo": "🚀 डेमो खोलें",
        "main_title": "🚀 <b>SAARS — इंटरैक्टिव डेमो</b>\n\nसभी मॉड्यूल रियल टाइम में टेस्ट करें।",
        "balance_line": "💰 आपका बैलेंस: <b>{bal} USDT</b>",
        "choose_section": "👇 एक सेक्शन चुनें:",
        "btn_store": "🛍️ स्टोर", "btn_tasks": "📋 टास्क", "btn_ref": "👥 रेफरल",
        "btn_balance": "💰 मेरा बैलेंस", "btn_guard": "🔒 चैनल गार्ड", "btn_wallets": "💳 वॉलेट",
        "btn_about": "ℹ️ SAARS के बारे में", "btn_close": "❌ बंद करें", "btn_menu": "🔙 मेनू",
        "btn_back_store": "🔙 स्टोर", "btn_back_tasks": "🔙 टास्क", "btn_back_ref": "🔙 रेफरल",
        "btn_ranking": "🏆 रैंकिंग", "btn_reopen": "🚀 फिर खोलें", "btn_home": "🏠 डेमो मेनू",
        "btn_tasks_go": "📋 टास्क देखें", "btn_buy_bal": "💰 बैलेंस से खरीदें ({bal} USDT)",
        "btn_buy_crypto": "💳 क्रिप्टो से भुगतान करें (डेमो)", "btn_paid": "✅ मैंने भुगतान कर दिया",
        "btn_delivery": "📦 डिलीवरी देखें", "btn_verify": "✅ सदस्यता जांचें (डेमो)",
        "btn_saldo_tasks": "📋 टास्क", "btn_saldo_ref": "👥 रेफरल",
        "about_text": (
            "ℹ️ <b>SAARS क्या है?</b>\n\n"
            "पूर्ण मुद्रीकरण के साथ white-label Telegram बॉट बनाने का SaaS प्लेटफॉर्म।\n\n"
            "<b>शामिल है:</b>\n• 🎨 Menu Builder\n• 🛍️ ऑटो डिलीवरी स्टोर\n• 📋 पेड टास्क\n"
            "• 👥 रेफरल रैंकिंग\n• 💰 इंटरनल बैलेंस\n• 🔒 चैनल गार्ड\n"
            "• 💳 Crypto: TON · BEP20 · TRC20 · SOL\n\n"
            "<b>Pro Plan:</b> $20/माह · सभी मॉड्यूल सक्रिय।"
        ),
        "closed": "✅ डेमो बंद। वापस जाने के लिए /start उपयोग करें।",
        "store_title": "🛍️ <b>डिजिटल प्रोडक्ट स्टोर</b>\n\n💰 आपका बैलेंस: <b>{bal} USDT</b>\n\nएक प्रोडक्ट चुनें:",
        "already_bought": "✅ पहले से खरीदा जा चुका है।",
        "insufficient": "❌ <b>बैलेंस कम है।</b>\n\nआपको {price} USDT चाहिए।",
        "purchase_ok": "✅ <b>खरीद सफल!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>क्रिप्टो भुगतान</b>\n\nप्रोडक्ट: {title}\nराशि: <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>भेजने के बाद 'मैंने भुगतान कर दिया' क्लिक करें।</i>",
        "confirmed": "✅ <b>पुष्टि हो गई!</b>\n<i>[डेमो: स्वचालित अनुमोदन]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>डिलीवरी</b>\n\n{delivery}",
        "tasks_title": "📋 <b>पेड टास्क</b>\n\n💰 आपका बैलेंस: <b>{bal} USDT</b>\n\nपूरा करें और तुरंत पाएं:",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>टास्क पूरा हुआ!</b>\n\n+{reward} USDT\nनया बैलेंस: <b>{bal} USDT</b>\n\n<i>[डेमो: स्वचालित सत्यापन]</i>",
        "task_already": "✅ पहले से पूरा हो चुका है!",
        "proof_wait": "📤 <b>प्रमाण भेजें</b>\n\nअभी एक फोटो या फाइल भेजें।",
        "proof_cancel": "❌ रद्द करें",
        "proof_ok": "✅ <b>प्रमाण स्वीकृत!</b>\n\n+{reward} USDT\nनया बैलेंस: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>रेफरल</b>\n\n🔗 आपका लिंक:\n<code>{link}</code>\n\n👤 रेफरल: <b>{cnt}</b>\n💰 कमाई: <b>{earn} USDT</b>\n🎁 प्रति रेफरल: <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>रैंकिंग</b>\n\nअभी कोई रेफरल नहीं!",
        "ranking_title": "🏆 <b>टॉप रेफरर्स</b>\n",
        "ranking_line": "{medal} {name} — {cnt} रेफरल · {earn} USDT",
        "new_ref": "🎉 <b>नया रेफरल!</b>\n\n{name} आपके लिंक से जुड़ा।\n+{reward} USDT क्रेडिट हुआ!",
        "balance_title": "💰 <b>मेरा बैलेंस</b>\n\nवर्तमान बैलेंस: <b>{bal} USDT</b>\n\nटास्क पूरा करके और दोस्तों को रेफर करके कमाएं।",
        "tx_header": "\n\n📜 <b>हाल के लेनदेन:</b>\n",
        "guard_title": "🔒 <b>चैनल गार्ड</b>\n\nसदस्य बनने तक पहुंच ब्लॉक।\n\n<b>चैनल:</b>\n{channels}\n\n✅ <i>डेमो में एक्सेस हमेशा दी जाती है।</i>",
        "guard_ok": "✅ <b>सत्यापन पूर्ण!</b>\n\nमेनू अनलॉक हो गया।",
        "wallets_title": "💳 <b>भुगतान वॉलेट</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 आपका बैलेंस: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>यह प्रोडक्ट पहले से खरीदा गया है</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 पुरस्कार: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>पहले से पूरा!</b>",
        "btn_submit_task": "✅ टास्क पूरा करें",
        "btn_send_proof": "📤 प्रमाण भेजें",
        "lang_select": "🌐 <b>भाषा / Language</b>\n\nअपनी भाषा चुनें:",
        "lang_set": "✅ भाषा सेट हुई: {lang}",
        "btn_lang": "🌐 भाषा",
    },

    # ── Arabic ───────────────────────────────────
    "ar": {
        "lang_name": "🇸🇦 العربية",
        "welcome": "👋 مرحباً <b>{name}</b>!\n\n🚀 <b>SAARS Demo Bot</b>\n\nاختبر جميع الوحدات في الوقت الفعلي — المتجر والمهام والإحالة والرصيد والمزيد.\n\n👇 انقر للبدء:",
        "open_demo": "🚀 فتح العرض",
        "main_title": "🚀 <b>SAARS — العرض التفاعلي</b>\n\nاختبر جميع الوحدات في الوقت الفعلي.",
        "balance_line": "💰 رصيدك: <b>{bal} USDT</b>",
        "choose_section": "👇 اختر قسماً:",
        "btn_store": "🛍️ المتجر", "btn_tasks": "📋 المهام", "btn_ref": "👥 الإحالة",
        "btn_balance": "💰 رصيدي", "btn_guard": "🔒 حارس القناة", "btn_wallets": "💳 المحافظ",
        "btn_about": "ℹ️ عن SAARS", "btn_close": "❌ إغلاق", "btn_menu": "🔙 القائمة",
        "btn_back_store": "🔙 المتجر", "btn_back_tasks": "🔙 المهام", "btn_back_ref": "🔙 الإحالة",
        "btn_ranking": "🏆 التصنيف", "btn_reopen": "🚀 إعادة فتح", "btn_home": "🏠 قائمة العرض",
        "btn_tasks_go": "📋 عرض المهام", "btn_buy_bal": "💰 شراء بالرصيد ({bal} USDT)",
        "btn_buy_crypto": "💳 الدفع بالعملة المشفرة (عرض)", "btn_paid": "✅ لقد دفعت",
        "btn_delivery": "📦 عرض التسليم", "btn_verify": "✅ التحقق من العضوية (عرض)",
        "btn_saldo_tasks": "📋 المهام", "btn_saldo_ref": "👥 الإحالة",
        "about_text": (
            "ℹ️ <b>ما هو SAARS؟</b>\n\n"
            "منصة SaaS لإنشاء روبوتات Telegram white-label مع تحقيق دخل كامل.\n\n"
            "<b>يشمل:</b>\n• 🎨 منشئ القوائم\n• 🛍️ متجر تسليم تلقائي\n• 📋 مهام مدفوعة\n"
            "• 👥 إحالة مع تصنيف\n• 💰 رصيد داخلي\n• 🔒 حارس القناة\n"
            "• 💳 العملات المشفرة: TON · BEP20 · TRC20 · SOL\n\n"
            "<b>الخطة الاحترافية:</b> 20$/شهر · جميع الوحدات نشطة."
        ),
        "closed": "✅ تم إغلاق العرض. استخدم /start للعودة.",
        "store_title": "🛍️ <b>متجر المنتجات الرقمية</b>\n\n💰 رصيدك: <b>{bal} USDT</b>\n\nاختر منتجاً:",
        "already_bought": "✅ تم الشراء مسبقاً.",
        "insufficient": "❌ <b>الرصيد غير كافٍ.</b>\n\nتحتاج {price} USDT.",
        "purchase_ok": "✅ <b>تمت عملية الشراء!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>الدفع بالعملة المشفرة</b>\n\nالمنتج: {title}\nالمبلغ: <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>انقر 'لقد دفعت' بعد الإرسال.</i>",
        "confirmed": "✅ <b>تم التأكيد!</b>\n<i>[عرض: موافقة تلقائية]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>التسليم</b>\n\n{delivery}",
        "tasks_title": "📋 <b>المهام المدفوعة</b>\n\n💰 رصيدك: <b>{bal} USDT</b>\n\nأكمل واحصل تلقائياً:",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>تمت المهمة!</b>\n\n+{reward} USDT\nالرصيد الجديد: <b>{bal} USDT</b>\n\n<i>[عرض: تحقق تلقائي]</i>",
        "task_already": "✅ تم إنجازها مسبقاً!",
        "proof_wait": "📤 <b>إرسال الدليل</b>\n\nأرسل صورة أو ملفاً الآن.",
        "proof_cancel": "❌ إلغاء",
        "proof_ok": "✅ <b>تمت الموافقة على الدليل!</b>\n\n+{reward} USDT\nالرصيد الجديد: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>الإحالة</b>\n\n🔗 رابطك:\n<code>{link}</code>\n\n👤 الإحالات: <b>{cnt}</b>\n💰 الأرباح: <b>{earn} USDT</b>\n🎁 لكل إحالة: <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>التصنيف</b>\n\nلا توجد إحالات بعد!",
        "ranking_title": "🏆 <b>أفضل المُحيلين</b>\n",
        "ranking_line": "{medal} {name} — {cnt} إحالة · {earn} USDT",
        "new_ref": "🎉 <b>إحالة جديدة!</b>\n\n{name} انضم عبر رابطك.\n+{reward} USDT تم إضافته!",
        "balance_title": "💰 <b>رصيدي</b>\n\nالرصيد الحالي: <b>{bal} USDT</b>\n\nاكسب بإتمام المهام وإحالة الأصدقاء.",
        "tx_header": "\n\n📜 <b>آخر المعاملات:</b>\n",
        "guard_title": "🔒 <b>حارس القناة</b>\n\nيحجب الوصول حتى يصبح المستخدم عضواً.\n\n<b>القنوات:</b>\n{channels}\n\n✅ <i>في العرض الوصول مسموح دائماً.</i>",
        "guard_ok": "✅ <b>اكتمل التحقق!</b>\n\nتم فتح القائمة.",
        "wallets_title": "💳 <b>محافظ الدفع</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 رصيدك: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>تم شراء هذا المنتج مسبقاً</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 المكافأة: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>تم إنجازها مسبقاً!</b>",
        "btn_submit_task": "✅ إتمام المهمة",
        "btn_send_proof": "📤 إرسال الدليل",
        "lang_select": "🌐 <b>اللغة / Language</b>\n\nاختر لغتك:",
        "lang_set": "✅ تم ضبط اللغة: {lang}",
        "btn_lang": "🌐 اللغة",
    },

    # ── French ───────────────────────────────────
    "fr": {
        "lang_name": "🇫🇷 Français",
        "welcome": "👋 Bonjour <b>{name}</b> !\n\n🚀 <b>SAARS Demo Bot</b>\n\nTestez tous les modules en temps réel — boutique, tâches, parrainage, solde et plus.\n\n👇 Cliquez pour commencer :",
        "open_demo": "🚀 Ouvrir la Démo",
        "main_title": "🚀 <b>SAARS — Démo Interactive</b>\n\nTestez tous les modules en temps réel.",
        "balance_line": "💰 Votre solde : <b>{bal} USDT</b>",
        "choose_section": "👇 Choisissez une section :",
        "btn_store": "🛍️ Boutique", "btn_tasks": "📋 Tâches", "btn_ref": "👥 Parrainage",
        "btn_balance": "💰 Mon Solde", "btn_guard": "🔒 Garde Canal", "btn_wallets": "💳 Portefeuilles",
        "btn_about": "ℹ️ À propos de SAARS", "btn_close": "❌ Fermer", "btn_menu": "🔙 Menu",
        "btn_back_store": "🔙 Boutique", "btn_back_tasks": "🔙 Tâches", "btn_back_ref": "🔙 Parrainage",
        "btn_ranking": "🏆 Classement", "btn_reopen": "🚀 Rouvrir", "btn_home": "🏠 Menu Démo",
        "btn_tasks_go": "📋 Voir les Tâches", "btn_buy_bal": "💰 Acheter avec le solde ({bal} USDT)",
        "btn_buy_crypto": "💳 Payer en crypto (démo)", "btn_paid": "✅ J'ai déjà payé",
        "btn_delivery": "📦 Voir la livraison", "btn_verify": "✅ Vérifier l'adhésion (démo)",
        "btn_saldo_tasks": "📋 Tâches", "btn_saldo_ref": "👥 Parrainage",
        "about_text": (
            "ℹ️ <b>Qu'est-ce que SAARS ?</b>\n\n"
            "Plateforme SaaS pour créer des bots Telegram white-label avec monétisation complète.\n\n"
            "<b>Comprend :</b>\n• 🎨 Menu Builder\n• 🛍️ Boutique avec livraison automatique\n• 📋 Tâches payantes\n"
            "• 👥 Parrainage avec classement\n• 💰 Solde interne\n• 🔒 Garde Canal\n"
            "• 💳 Crypto : TON · BEP20 · TRC20 · SOL\n\n"
            "<b>Plan Pro :</b> 20$/mois · tous les modules actifs."
        ),
        "closed": "✅ Démo fermée. Utilisez /start pour revenir.",
        "store_title": "🛍️ <b>Boutique de Produits Numériques</b>\n\n💰 Votre solde : <b>{bal} USDT</b>\n\nChoisissez un produit :",
        "already_bought": "✅ Déjà acheté.",
        "insufficient": "❌ <b>Solde insuffisant.</b>\n\nVous avez besoin de {price} USDT.",
        "purchase_ok": "✅ <b>Achat réussi !</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Paiement Crypto</b>\n\nProduit : {title}\nMontant : <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>Cliquez 'J'ai déjà payé' après l'envoi.</i>",
        "confirmed": "✅ <b>Confirmé !</b>\n<i>[Démo : approbation automatique]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Livraison</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Tâches Payantes</b>\n\n💰 Votre solde : <b>{bal} USDT</b>\n\nComplétez et recevez automatiquement :",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>Tâche accomplie !</b>\n\n+{reward} USDT\nNouveau solde : <b>{bal} USDT</b>\n\n<i>[Démo : vérification automatique]</i>",
        "task_already": "✅ Déjà accomplie !",
        "proof_wait": "📤 <b>Envoi de Preuve</b>\n\nEnvoyez maintenant une photo ou un fichier.",
        "proof_cancel": "❌ Annuler",
        "proof_ok": "✅ <b>Preuve approuvée !</b>\n\n+{reward} USDT\nNouveau solde : <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Parrainage</b>\n\n🔗 Votre lien :\n<code>{link}</code>\n\n👤 Parrainages : <b>{cnt}</b>\n💰 Gains : <b>{earn} USDT</b>\n🎁 Par parrainage : <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>Classement</b>\n\nAucun parrainage pour l'instant !",
        "ranking_title": "🏆 <b>Top Parrains</b>\n",
        "ranking_line": "{medal} {name} — {cnt} parr. · {earn} USDT",
        "new_ref": "🎉 <b>Nouveau parrainage !</b>\n\n{name} a rejoint via votre lien.\n+{reward} USDT crédité !",
        "balance_title": "💰 <b>Mon Solde</b>\n\nSolde actuel : <b>{bal} USDT</b>\n\nGagnez en accomplissant des tâches et en parrainant des amis.",
        "tx_header": "\n\n📜 <b>Dernières transactions :</b>\n",
        "guard_title": "🔒 <b>Garde Canal</b>\n\nBloque l'accès jusqu'à ce que l'utilisateur soit membre.\n\n<b>Canaux :</b>\n{channels}\n\n✅ <i>En démo l'accès est toujours autorisé.</i>",
        "guard_ok": "✅ <b>Vérification terminée !</b>\n\nMenu débloqué.",
        "wallets_title": "💳 <b>Portefeuilles de Paiement</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Votre solde : <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Déjà acheté</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Récompense : <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Déjà accomplie !</b>",
        "btn_submit_task": "✅ Accomplir la tâche",
        "btn_send_proof": "📤 Envoyer la preuve",
        "lang_select": "🌐 <b>Langue / Language</b>\n\nChoisissez votre langue :",
        "lang_set": "✅ Langue définie : {lang}",
        "btn_lang": "🌐 Langue",
    },

    # ── Russian ──────────────────────────────────
    "ru": {
        "lang_name": "🇷🇺 Русский",
        "welcome": "👋 Привет <b>{name}</b>!\n\n🚀 <b>SAARS Demo Bot</b>\n\nПроверьте все модули в реальном времени — магазин, задания, рефералы, баланс и многое другое.\n\n👇 Нажмите, чтобы начать:",
        "open_demo": "🚀 Открыть демо",
        "main_title": "🚀 <b>SAARS — Интерактивное демо</b>\n\nПроверьте все модули в реальном времени.",
        "balance_line": "💰 Ваш баланс: <b>{bal} USDT</b>",
        "choose_section": "👇 Выберите раздел:",
        "btn_store": "🛍️ Магазин", "btn_tasks": "📋 Задания", "btn_ref": "👥 Рефералы",
        "btn_balance": "💰 Мой баланс", "btn_guard": "🔒 Охрана канала", "btn_wallets": "💳 Кошельки",
        "btn_about": "ℹ️ О SAARS", "btn_close": "❌ Закрыть", "btn_menu": "🔙 Меню",
        "btn_back_store": "🔙 Магазин", "btn_back_tasks": "🔙 Задания", "btn_back_ref": "🔙 Рефералы",
        "btn_ranking": "🏆 Рейтинг", "btn_reopen": "🚀 Открыть снова", "btn_home": "🏠 Демо-меню",
        "btn_tasks_go": "📋 Посмотреть задания", "btn_buy_bal": "💰 Купить с баланса ({bal} USDT)",
        "btn_buy_crypto": "💳 Оплатить криптой (демо)", "btn_paid": "✅ Я уже оплатил",
        "btn_delivery": "📦 Посмотреть доставку", "btn_verify": "✅ Проверить членство (демо)",
        "btn_saldo_tasks": "📋 Задания", "btn_saldo_ref": "👥 Рефералы",
        "about_text": (
            "ℹ️ <b>Что такое SAARS?</b>\n\n"
            "SaaS-платформа для создания white-label Telegram-ботов с полной монетизацией.\n\n"
            "<b>Включает:</b>\n• 🎨 Конструктор меню\n• 🛍️ Магазин с автодоставкой\n• 📋 Платные задания\n"
            "• 👥 Реферальная программа с рейтингом\n• 💰 Внутренний баланс\n• 🔒 Охрана канала\n"
            "• 💳 Крипта: TON · BEP20 · TRC20 · SOL\n\n"
            "<b>Pro-план:</b> $20/мес · все модули активны."
        ),
        "closed": "✅ Демо закрыто. Используйте /start для возврата.",
        "store_title": "🛍️ <b>Магазин цифровых продуктов</b>\n\n💰 Ваш баланс: <b>{bal} USDT</b>\n\nВыберите продукт:",
        "already_bought": "✅ Уже куплено.",
        "insufficient": "❌ <b>Недостаточно средств.</b>\n\nВам нужно {price} USDT.",
        "purchase_ok": "✅ <b>Покупка успешна!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Оплата криптой</b>\n\nПродукт: {title}\nСумма: <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>Нажмите 'Я уже оплатил' после отправки.</i>",
        "confirmed": "✅ <b>Подтверждено!</b>\n<i>[Демо: автоматическое одобрение]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Доставка</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Платные задания</b>\n\n💰 Ваш баланс: <b>{bal} USDT</b>\n\nВыполняйте и получайте автоматически:",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>Задание выполнено!</b>\n\n+{reward} USDT\nНовый баланс: <b>{bal} USDT</b>\n\n<i>[Демо: автоматическая проверка]</i>",
        "task_already": "✅ Уже выполнено!",
        "proof_wait": "📤 <b>Отправка доказательства</b>\n\nОтправьте фото или файл сейчас.",
        "proof_cancel": "❌ Отмена",
        "proof_ok": "✅ <b>Доказательство одобрено!</b>\n\n+{reward} USDT\nНовый баланс: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Рефералы</b>\n\n🔗 Ваша ссылка:\n<code>{link}</code>\n\n👤 Рефералов: <b>{cnt}</b>\n💰 Заработок: <b>{earn} USDT</b>\n🎁 За реферала: <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>Рейтинг</b>\n\nПока нет рефералов!",
        "ranking_title": "🏆 <b>Топ рефереров</b>\n",
        "ranking_line": "{medal} {name} — {cnt} реф. · {earn} USDT",
        "new_ref": "🎉 <b>Новый реферал!</b>\n\n{name} присоединился по вашей ссылке.\n+{reward} USDT зачислено!",
        "balance_title": "💰 <b>Мой баланс</b>\n\nТекущий баланс: <b>{bal} USDT</b>\n\nЗарабатывайте, выполняя задания и приглашая друзей.",
        "tx_header": "\n\n📜 <b>Последние транзакции:</b>\n",
        "guard_title": "🔒 <b>Охрана канала</b>\n\nБлокирует доступ, пока пользователь не станет членом.\n\n<b>Каналы:</b>\n{channels}\n\n✅ <i>В демо доступ всегда разрешён.</i>",
        "guard_ok": "✅ <b>Проверка завершена!</b>\n\nМеню разблокировано.",
        "wallets_title": "💳 <b>Платёжные кошельки</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Ваш баланс: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Уже куплено</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Награда: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Уже выполнено!</b>",
        "btn_submit_task": "✅ Выполнить задание",
        "btn_send_proof": "📤 Отправить доказательство",
        "lang_select": "🌐 <b>Язык / Language</b>\n\nВыберите язык:",
        "lang_set": "✅ Язык установлен: {lang}",
        "btn_lang": "🌐 Язык",
    },

    # ── Bengali ──────────────────────────────────
    "bn": {
        "lang_name": "🇧🇩 বাংলা",
        "welcome": "👋 হ্যালো <b>{name}</b>!\n\n🚀 <b>SAARS Demo Bot</b>\n\nসমস্ত মডিউল রিয়েল টাইমে পরীক্ষা করুন — স্টোর, টাস্ক, রেফারেল, ব্যালেন্স এবং আরও।\n\n👇 শুরু করতে ক্লিক করুন:",
        "open_demo": "🚀 ডেমো খুলুন",
        "main_title": "🚀 <b>SAARS — ইন্টারেক্টিভ ডেমো</b>\n\nসমস্ত মডিউল রিয়েল টাইমে পরীক্ষা করুন।",
        "balance_line": "💰 আপনার ব্যালেন্স: <b>{bal} USDT</b>",
        "choose_section": "👇 একটি বিভাগ বেছে নিন:",
        "btn_store": "🛍️ স্টোর", "btn_tasks": "📋 টাস্ক", "btn_ref": "👥 রেফারেল",
        "btn_balance": "💰 আমার ব্যালেন্স", "btn_guard": "🔒 চ্যানেল গার্ড", "btn_wallets": "💳 ওয়ালেট",
        "btn_about": "ℹ️ SAARS সম্পর্কে", "btn_close": "❌ বন্ধ", "btn_menu": "🔙 মেনু",
        "btn_back_store": "🔙 স্টোর", "btn_back_tasks": "🔙 টাস্ক", "btn_back_ref": "🔙 রেফারেল",
        "btn_ranking": "🏆 র‍্যাংকিং", "btn_reopen": "🚀 পুনরায় খুলুন", "btn_home": "🏠 ডেমো মেনু",
        "btn_tasks_go": "📋 টাস্ক দেখুন", "btn_buy_bal": "💰 ব্যালেন্স দিয়ে কিনুন ({bal} USDT)",
        "btn_buy_crypto": "💳 ক্রিপ্টো দিয়ে পেমেন্ট (ডেমো)", "btn_paid": "✅ আমি পেমেন্ট করেছি",
        "btn_delivery": "📦 ডেলিভারি দেখুন", "btn_verify": "✅ সদস্যতা যাচাই (ডেমো)",
        "btn_saldo_tasks": "📋 টাস্ক", "btn_saldo_ref": "👥 রেফারেল",
        "about_text": (
            "ℹ️ <b>SAARS কী?</b>\n\n"
            "সম্পূর্ণ মনিটাইজেশনসহ white-label Telegram বট তৈরির SaaS প্ল্যাটফর্ম।\n\n"
            "<b>অন্তর্ভুক্ত:</b>\n• 🎨 মেনু বিল্ডার\n• 🛍️ অটো ডেলিভারি স্টোর\n• 📋 পেইড টাস্ক\n"
            "• 👥 র‍্যাংকিং সহ রেফারেল\n• 💰 অভ্যন্তরীণ ব্যালেন্স\n• 🔒 চ্যানেল গার্ড\n"
            "• 💳 Crypto: TON · BEP20 · TRC20 · SOL\n\n"
            "<b>Pro Plan:</b> $20/মাস · সব মডিউল সক্রিয়।"
        ),
        "closed": "✅ ডেমো বন্ধ। ফিরতে /start ব্যবহার করুন।",
        "store_title": "🛍️ <b>ডিজিটাল পণ্য স্টোর</b>\n\n💰 আপনার ব্যালেন্স: <b>{bal} USDT</b>\n\nপণ্য বেছে নিন:",
        "already_bought": "✅ ইতিমধ্যে কেনা হয়েছে।",
        "insufficient": "❌ <b>ব্যালেন্স যথেষ্ট নেই।</b>\n\nআপনার {price} USDT দরকার।",
        "purchase_ok": "✅ <b>ক্রয় সফল!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>ক্রিপ্টো পেমেন্ট</b>\n\nপণ্য: {title}\nমূল্য: <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>পাঠানোর পরে 'আমি পেমেন্ট করেছি' ক্লিক করুন।</i>",
        "confirmed": "✅ <b>নিশ্চিত!</b>\n<i>[ডেমো: স্বয়ংক্রিয় অনুমোদন]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>ডেলিভারি</b>\n\n{delivery}",
        "tasks_title": "📋 <b>পেইড টাস্ক</b>\n\n💰 আপনার ব্যালেন্স: <b>{bal} USDT</b>\n\nসম্পন্ন করুন এবং স্বয়ংক্রিয়ভাবে পান:",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>টাস্ক সম্পন্ন!</b>\n\n+{reward} USDT\nনতুন ব্যালেন্স: <b>{bal} USDT</b>\n\n<i>[ডেমো: স্বয়ংক্রিয় যাচাই]</i>",
        "task_already": "✅ ইতিমধ্যে সম্পন্ন!",
        "proof_wait": "📤 <b>প্রমাণ পাঠান</b>\n\nএখন একটি ফটো বা ফাইল পাঠান।",
        "proof_cancel": "❌ বাতিল",
        "proof_ok": "✅ <b>প্রমাণ অনুমোদিত!</b>\n\n+{reward} USDT\nনতুন ব্যালেন্স: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>রেফারেল</b>\n\n🔗 আপনার লিংক:\n<code>{link}</code>\n\n👤 রেফারেল: <b>{cnt}</b>\n💰 আয়: <b>{earn} USDT</b>\n🎁 প্রতি রেফারেলে: <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>র‍্যাংকিং</b>\n\nএখনো কোনো রেফারেল নেই!",
        "ranking_title": "🏆 <b>শীর্ষ রেফারকারী</b>\n",
        "ranking_line": "{medal} {name} — {cnt} রেফ. · {earn} USDT",
        "new_ref": "🎉 <b>নতুন রেফারেল!</b>\n\n{name} আপনার লিংক থেকে যোগ দিয়েছে।\n+{reward} USDT জমা হয়েছে!",
        "balance_title": "💰 <b>আমার ব্যালেন্স</b>\n\nবর্তমান ব্যালেন্স: <b>{bal} USDT</b>\n\nটাস্ক সম্পন্ন করে এবং বন্ধু রেফার করে উপার্জন করুন।",
        "tx_header": "\n\n📜 <b>সাম্প্রতিক লেনদেন:</b>\n",
        "guard_title": "🔒 <b>চ্যানেল গার্ড</b>\n\nব্যবহারকারী সদস্য না হওয়া পর্যন্ত অ্যাক্সেস ব্লক।\n\n<b>চ্যানেল:</b>\n{channels}\n\n✅ <i>ডেমোতে অ্যাক্সেস সবসময় অনুমোদিত।</i>",
        "guard_ok": "✅ <b>যাচাই সম্পন্ন!</b>\n\nমেনু আনলক হয়েছে।",
        "wallets_title": "💳 <b>পেমেন্ট ওয়ালেট</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 আপনার ব্যালেন্স: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>এই পণ্যটি ইতিমধ্যে কেনা হয়েছে</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 পুরস্কার: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>ইতিমধ্যে সম্পন্ন!</b>",
        "btn_submit_task": "✅ টাস্ক সম্পন্ন করুন",
        "btn_send_proof": "📤 প্রমাণ পাঠান",
        "lang_select": "🌐 <b>ভাষা / Language</b>\n\nআপনার ভাষা বেছে নিন:",
        "lang_set": "✅ ভাষা সেট হয়েছে: {lang}",
        "btn_lang": "🌐 ভাষা",
    },

    # ── Indonesian ───────────────────────────────
    "id": {
        "lang_name": "🇮🇩 Bahasa Indonesia",
        "welcome": "👋 Halo <b>{name}</b>!\n\n🚀 <b>SAARS Demo Bot</b>\n\nUji semua modul secara real time — toko, tugas, referral, saldo dan lainnya.\n\n👇 Klik untuk mulai:",
        "open_demo": "🚀 Buka Demo",
        "main_title": "🚀 <b>SAARS — Demo Interaktif</b>\n\nUji semua modul secara real time.",
        "balance_line": "💰 Saldo kamu: <b>{bal} USDT</b>",
        "choose_section": "👇 Pilih sebuah bagian:",
        "btn_store": "🛍️ Toko", "btn_tasks": "📋 Tugas", "btn_ref": "👥 Referral",
        "btn_balance": "💰 Saldo Saya", "btn_guard": "🔒 Channel Guard", "btn_wallets": "💳 Dompet",
        "btn_about": "ℹ️ Tentang SAARS", "btn_close": "❌ Tutup", "btn_menu": "🔙 Menu",
        "btn_back_store": "🔙 Toko", "btn_back_tasks": "🔙 Tugas", "btn_back_ref": "🔙 Referral",
        "btn_ranking": "🏆 Peringkat", "btn_reopen": "🚀 Buka Kembali", "btn_home": "🏠 Menu Demo",
        "btn_tasks_go": "📋 Lihat Tugas", "btn_buy_bal": "💰 Beli dengan saldo ({bal} USDT)",
        "btn_buy_crypto": "💳 Bayar dengan crypto (demo)", "btn_paid": "✅ Saya sudah bayar",
        "btn_delivery": "📦 Lihat pengiriman", "btn_verify": "✅ Verifikasi keanggotaan (demo)",
        "btn_saldo_tasks": "📋 Tugas", "btn_saldo_ref": "👥 Referral",
        "about_text": (
            "ℹ️ <b>Apa itu SAARS?</b>\n\n"
            "Platform SaaS untuk membuat bot Telegram white-label dengan monetisasi lengkap.\n\n"
            "<b>Termasuk:</b>\n• 🎨 Menu Builder\n• 🛍️ Toko dengan pengiriman otomatis\n• 📋 Tugas berbayar\n"
            "• 👥 Referral dengan peringkat\n• 💰 Saldo internal\n• 🔒 Channel Guard\n"
            "• 💳 Crypto: TON · BEP20 · TRC20 · SOL\n\n"
            "<b>Paket Pro:</b> $20/bulan · semua modul aktif."
        ),
        "closed": "✅ Demo ditutup. Gunakan /start untuk kembali.",
        "store_title": "🛍️ <b>Toko Produk Digital</b>\n\n💰 Saldo kamu: <b>{bal} USDT</b>\n\nPilih produk:",
        "already_bought": "✅ Sudah dibeli.",
        "insufficient": "❌ <b>Saldo tidak cukup.</b>\n\nKamu butuh {price} USDT.",
        "purchase_ok": "✅ <b>Pembelian berhasil!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Pembayaran Crypto</b>\n\nProduk: {title}\nJumlah: <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>Klik 'Saya sudah bayar' setelah mengirim.</i>",
        "confirmed": "✅ <b>Dikonfirmasi!</b>\n<i>[Demo: persetujuan otomatis]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Pengiriman</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Tugas Berbayar</b>\n\n💰 Saldo kamu: <b>{bal} USDT</b>\n\nSelesaikan dan terima otomatis:",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>Tugas selesai!</b>\n\n+{reward} USDT\nSaldo baru: <b>{bal} USDT</b>\n\n<i>[Demo: verifikasi otomatis]</i>",
        "task_already": "✅ Sudah selesai!",
        "proof_wait": "📤 <b>Kirim Bukti</b>\n\nKirim foto atau file sekarang.",
        "proof_cancel": "❌ Batal",
        "proof_ok": "✅ <b>Bukti disetujui!</b>\n\n+{reward} USDT\nSaldo baru: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Referral</b>\n\n🔗 Link kamu:\n<code>{link}</code>\n\n👤 Referral: <b>{cnt}</b>\n💰 Penghasilan: <b>{earn} USDT</b>\n🎁 Per referral: <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>Peringkat</b>\n\nBelum ada referral!",
        "ranking_title": "🏆 <b>Top Referrer</b>\n",
        "ranking_line": "{medal} {name} — {cnt} ref · {earn} USDT",
        "new_ref": "🎉 <b>Referral baru!</b>\n\n{name} bergabung melalui link kamu.\n+{reward} USDT dikreditkan!",
        "balance_title": "💰 <b>Saldo Saya</b>\n\nSaldo saat ini: <b>{bal} USDT</b>\n\nDapatkan dengan menyelesaikan tugas dan mereferensikan teman.",
        "tx_header": "\n\n📜 <b>Transaksi terakhir:</b>\n",
        "guard_title": "🔒 <b>Channel Guard</b>\n\nMemblokir akses hingga pengguna menjadi anggota.\n\n<b>Channel:</b>\n{channels}\n\n✅ <i>Di demo akses selalu diizinkan.</i>",
        "guard_ok": "✅ <b>Verifikasi selesai!</b>\n\nMenu dibuka.",
        "wallets_title": "💳 <b>Dompet Pembayaran</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Saldo kamu: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Sudah dibeli</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Hadiah: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Sudah selesai!</b>",
        "btn_submit_task": "✅ Selesaikan tugas",
        "btn_send_proof": "📤 Kirim bukti",
        "lang_select": "🌐 <b>Bahasa / Language</b>\n\nPilih bahasa kamu:",
        "lang_set": "✅ Bahasa diatur: {lang}",
        "btn_lang": "🌐 Bahasa",
    },

    # ── Swahili ──────────────────────────────────
    "sw": {
        "lang_name": "🌍 Kiswahili",
        "welcome": "👋 Habari <b>{name}</b>!\n\n🚀 <b>SAARS Demo Bot</b>\n\nJaribu moduli zote kwa wakati halisi — duka, kazi, rufaa, salio na zaidi.\n\n👇 Bonyeza kuanza:",
        "open_demo": "🚀 Fungua Demo",
        "main_title": "🚀 <b>SAARS — Demo ya Maingiliano</b>\n\nJaribu moduli zote kwa wakati halisi.",
        "balance_line": "💰 Salio lako: <b>{bal} USDT</b>",
        "choose_section": "👇 Chagua sehemu:",
        "btn_store": "🛍️ Duka", "btn_tasks": "📋 Kazi", "btn_ref": "👥 Rufaa",
        "btn_balance": "💰 Salio Langu", "btn_guard": "🔒 Ulinzi wa Chaneli", "btn_wallets": "💳 Pochi",
        "btn_about": "ℹ️ Kuhusu SAARS", "btn_close": "❌ Funga", "btn_menu": "🔙 Menyu",
        "btn_back_store": "🔙 Duka", "btn_back_tasks": "🔙 Kazi", "btn_back_ref": "🔙 Rufaa",
        "btn_ranking": "🏆 Orodha", "btn_reopen": "🚀 Fungua Tena", "btn_home": "🏠 Menyu ya Demo",
        "btn_tasks_go": "📋 Tazama Kazi", "btn_buy_bal": "💰 Nunua kwa salio ({bal} USDT)",
        "btn_buy_crypto": "💳 Lipa kwa crypto (demo)", "btn_paid": "✅ Nimelipa",
        "btn_delivery": "📦 Tazama uwasilishaji", "btn_verify": "✅ Thibitisha uanachama (demo)",
        "btn_saldo_tasks": "📋 Kazi", "btn_saldo_ref": "👥 Rufaa",
        "about_text": (
            "ℹ️ <b>SAARS ni nini?</b>\n\n"
            "Jukwaa la SaaS la kuunda boti za Telegram white-label na ukusanyaji mapato kamili.\n\n"
            "<b>Inajumuisha:</b>\n• 🎨 Mjenzi wa Menyu\n• 🛍️ Duka na uwasilishaji otomatiki\n• 📋 Kazi za kulipwa\n"
            "• 👥 Rufaa na orodha\n• 💰 Salio la ndani\n• 🔒 Ulinzi wa Chaneli\n"
            "• 💳 Crypto: TON · BEP20 · TRC20 · SOL\n\n"
            "<b>Mpango wa Pro:</b> $20/mwezi · moduli zote zinafanya kazi."
        ),
        "closed": "✅ Demo imefungwa. Tumia /start kurudi.",
        "store_title": "🛍️ <b>Duka la Bidhaa za Kidijitali</b>\n\n💰 Salio lako: <b>{bal} USDT</b>\n\nChagua bidhaa:",
        "already_bought": "✅ Tayari umenunua.",
        "insufficient": "❌ <b>Salio haitoshi.</b>\n\nUnahitaji {price} USDT.",
        "purchase_ok": "✅ <b>Ununuzi umefanikiwa!</b>\n\n{delivery}",
        "crypto_pay": "💳 <b>Malipo ya Crypto</b>\n\nBidhaa: {title}\nKiasi: <b>{price} USDT</b>\n\n{wallets}\n\n⚠️ <i>Bonyeza 'Nimelipa' baada ya kutuma.</i>",
        "confirmed": "✅ <b>Imethibitishwa!</b>\n<i>[Demo: idhini otomatiki]</i>\n\n{delivery}",
        "delivery_title": "📦 <b>Uwasilishaji</b>\n\n{delivery}",
        "tasks_title": "📋 <b>Kazi za Kulipwa</b>\n\n💰 Salio lako: <b>{bal} USDT</b>\n\nKamilisha na upokee moja kwa moja:",
        "task_done_mark": "✅ ",
        "task_done": "✅ <b>Kazi imekamilika!</b>\n\n+{reward} USDT\nSalio jipya: <b>{bal} USDT</b>\n\n<i>[Demo: uthibitisho otomatiki]</i>",
        "task_already": "✅ Tayari imekamilika!",
        "proof_wait": "📤 <b>Tuma Uthibitisho</b>\n\nTuma picha au faili sasa.",
        "proof_cancel": "❌ Ghairi",
        "proof_ok": "✅ <b>Uthibitisho umeidhinishwa!</b>\n\n+{reward} USDT\nSalio jipya: <b>{bal} USDT</b>",
        "ref_title": "👥 <b>Rufaa</b>\n\n🔗 Kiungo chako:\n<code>{link}</code>\n\n👤 Rufaa: <b>{cnt}</b>\n💰 Mapato: <b>{earn} USDT</b>\n🎁 Kwa kila rufaa: <b>{reward} USDT</b>",
        "ranking_empty": "🏆 <b>Orodha</b>\n\nHaijana rufaa bado!",
        "ranking_title": "🏆 <b>Wakurugenzi Bora</b>\n",
        "ranking_line": "{medal} {name} — {cnt} rufaa · {earn} USDT",
        "new_ref": "🎉 <b>Rufaa mpya!</b>\n\n{name} amejiunga kupitia kiungo chako.\n+{reward} USDT imeongezwa!",
        "balance_title": "💰 <b>Salio Langu</b>\n\nSalio la sasa: <b>{bal} USDT</b>\n\nPata kwa kukamilisha kazi na kuwasilisha marafiki.",
        "tx_header": "\n\n📜 <b>Miamala ya hivi karibuni:</b>\n",
        "guard_title": "🔒 <b>Ulinzi wa Chaneli</b>\n\nInazuia ufikiaji hadi mtumiaji awe mwanachama.\n\n<b>Chaneli:</b>\n{channels}\n\n✅ <i>Katika demo ufikiaji daima unaruhusiwa.</i>",
        "guard_ok": "✅ <b>Uthibitisho umekamilika!</b>\n\nMenuyu imefunguliwa.",
        "wallets_title": "💳 <b>Pochi za Malipo</b>\n\n",
        "product_detail": "🛍️ <b>{title}</b>\n\n{desc}\n\n💲 <b>{price} USDT</b>\n💰 Salio lako: <b>{bal} USDT</b>",
        "product_owned": "\n\n✅ <b>Tayari umenunua bidhaa hii</b>",
        "task_detail": "📋 <b>{title}</b>\n\n{desc}\n\n🎁 Tuzo: <b>+{reward} USDT</b>",
        "task_detail_done": "\n\n✅ <b>Tayari imekamilika!</b>",
        "btn_submit_task": "✅ Kamilisha kazi",
        "btn_send_proof": "📤 Tuma uthibitisho",
        "lang_select": "🌐 <b>Lugha / Language</b>\n\nChagua lugha yako:",
        "lang_set": "✅ Lugha imewekwa: {lang}",
        "btn_lang": "🌐 Lugha",
    },
}

# fallback
STRINGS["zh-hans"] = STRINGS["zh"]
STRINGS["zh-hant"] = STRINGS["zh"]

DEFAULT_LANG = "pt"

# Telegram language_code → STRINGS key
LANG_MAP = {
    "pt": "pt", "pt-br": "pt", "pt-pt": "pt",
    "en": "en", "en-us": "en", "en-gb": "en",
    "es": "es", "es-419": "es",
    "zh": "zh", "zh-hans": "zh", "zh-hant": "zh",
    "hi": "hi",
    "ar": "ar",
    "fr": "fr", "fr-be": "fr", "fr-ca": "fr",
    "ru": "ru",
    "bn": "bn",
    "id": "id",
    "sw": "sw",
}

# Selector buttons displayed in /lang menu
LANG_OPTIONS = [
    ("pt", "🇧🇷 Português"),
    ("en", "🇬🇧 English"),
    ("es", "🇪🇸 Español"),
    ("zh", "🇨🇳 中文"),
    ("hi", "🇮🇳 हिंदी"),
    ("ar", "🇸🇦 العربية"),
    ("fr", "🇫🇷 Français"),
    ("ru", "🇷🇺 Русский"),
    ("bn", "🇧🇩 বাংলা"),
    ("id", "🇮🇩 Indonesia"),
    ("sw", "🌍 Kiswahili"),
]

def get_lang(uid: int, tg_lang: str | None = None) -> str:
    """Return resolved language code for user."""
    if uid in _ulang:
        return _ulang[uid]
    if tg_lang:
        code = tg_lang.lower()
        if code in LANG_MAP:
            return LANG_MAP[code]
        prefix = code.split("-")[0]
        if prefix in LANG_MAP:
            return LANG_MAP[prefix]
    return DEFAULT_LANG

def t(uid: int, key: str, tg_lang: str | None = None, **kwargs) -> str:
    """Translate key for user, with optional format kwargs."""
    lang = get_lang(uid, tg_lang)
    s = STRINGS.get(lang, STRINGS[DEFAULT_LANG])
    text = s.get(key, STRINGS[DEFAULT_LANG].get(key, key))
    return text.format(**kwargs) if kwargs else text

# ─────────────────────────────────────────────
#  Data helpers
# ─────────────────────────────────────────────

def bal(u):  return _bal.get(u, Decimal("0"))
def credit(u, amt, tp, note=""):
    _bal[u] = _bal.get(u, Decimal("0")) + amt
    _txs.setdefault(u,[]).append({"a":amt,"t":tp,"n":note})
    return _bal[u]
def debit(u, amt, tp, note=""):
    if _bal.get(u, Decimal("0")) < amt: return False
    _bal[u] -= amt
    _txs.setdefault(u,[]).append({"a":-amt,"t":tp,"n":note})
    return True
def kb(*rows): return InlineKeyboardMarkup([[InlineKeyboardButton(tx,callback_data=c) for tx,c in r] for r in rows])
def tdone(u,tid): return tid in _tdone.get(u,set())
def mtask(u,tid): _tdone.setdefault(u,set()).add(tid)
def bought(u,pid): return pid in _purch.get(u,set())
def mbuy(u,pid):   _purch.setdefault(u,set()).add(pid)

# ─────────────────────────────────────────────
#  Data constants
# ─────────────────────────────────────────────

# ── Dados demo pré-carregados ────────────────────────────────────────────
# Simulam um negócio digital real — o prospect vê o bot "funcionando"
TASKS: list[dict] = [
    {"id":1,"title":"📢 Entrar no canal VIP","desc":"Entra no canal exclusivo e recebe acesso antecipado a todos os lançamentos.","reward":Decimal("2.00"),"verif":"auto"},
    {"id":2,"title":"🐦 Seguir no Instagram","desc":"Segue o perfil oficial e confirma aqui para ganhar o bónus.","reward":Decimal("1.50"),"verif":"auto"},
    {"id":3,"title":"📸 Enviar comprovante de partilha","desc":"Partilha este bot com 3 amigos e envia o screenshot como prova.","reward":Decimal("5.00"),"verif":"manual"},
    {"id":4,"title":"🎯 Responder ao quiz de negócios","desc":"Completa o quiz de 3 perguntas sobre empreendedorismo digital.","reward":Decimal("3.00"),"verif":"auto"},
]
PRODUCTS: list[dict] = [
    {"id":1,"title":"⚡ Pack Automação Telegram","desc":"Templates prontos para bots de vendas, suporte e comunidade. Deploy em 10 minutos.","price":Decimal("4.99"),
     "delivery":"🎉 <b>Acesso liberado!</b>\n\n📦 Pack completo:\n• 5 templates de bot prontos\n• Guia de deploy no Render\n• Grupo VIP de suporte\n\n🔗 Acesso: https://t.me/saars_news\n\n<i>Válido por 365 dias.</i>"},
    {"id":2,"title":"🎓 Mentoria: Renda com Bots","desc":"6 semanas de mentoria ao vivo. Do zero ao primeiro cliente pagante.","price":Decimal("27.00"),
     "delivery":"✅ <b>Mentoria confirmada!</b>\n\n📅 Próxima turma: segunda-feira\n💬 Grupo privado: https://t.me/saars_news\n\n<i>Guarda este link — é o teu acesso permanente.</i>"},
    {"id":3,"title":"🤖 Bot Personalizado (feito pra ti)","desc":"Entregamos o teu bot configurado, com loja, tarefas e referral. Pronto para monetizar.","price":Decimal("97.00"),
     "delivery":"🚀 <b>Pedido recebido!</b>\n\nA equipa SAARS vai entrar em contacto em até 24h.\n\n📩 Telegram: @saars_suporte\n\n<i>Obrigado pela confiança!</i>"},
]
WALLETS: list[dict] = [
    {"id":1,"label":"💎 TON Wallet",      "addr":"UQBWs0GY1YzNT8e2xSAARS_TON_DEMO"},
    {"id":2,"label":"💲 USDT TRC20",      "addr":"TSAARS_DEMO_TRC20_xxxxxxxxxxxxxxxxx"},
    {"id":3,"label":"🔶 BNB Smart Chain", "addr":"0xSAARS_DEMO_BEP20_xxxxxxxxxxxxxxx"},
]
CHANNELS: list[dict] = [
    {"id":1,"label":"📢 Canal VIP SAARS",    "url":"https://t.me/saars_news"},
    {"id":2,"label":"💬 Comunidade SAARS",   "url":"https://t.me/saars_community"},
]

_next_id: dict[str, int] = {"task": 5, "product": 4, "wallet": 4, "channel": 3}

def _new_id(kind: str) -> int:
    nid = _next_id[kind]; _next_id[kind] += 1; return nid

# ── FSM: estado de cadastro por usuário ──────────────────────────────────
# _state[uid] = {"step": str, ...dados parciais...}
_state: dict[int, dict] = {}

# ─────────────────────────────────────────────
#  Helpers FSM
# ─────────────────────────────────────────────

def _cancel_state(uid: int): _state.pop(uid, None)

async def _fsm_reply(u: Update, text: str, kb_rows=None):
    markup = InlineKeyboardMarkup(kb_rows) if kb_rows else None
    await u.message.reply_html(text, reply_markup=markup)

# ─────────────────────────────────────────────
#  Menu Gerir (⚙️) — aberto a todos
# ─────────────────────────────────────────────

async def gerir(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    await q.edit_message_text(
        "⚙️ <b>Gerir Conteúdo</b>\n\nO que queres adicionar ou remover?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍️ Produtos",    callback_data="gerir:produtos")],
            [InlineKeyboardButton("📋 Tarefas",     callback_data="gerir:tarefas")],
            [InlineKeyboardButton("💳 Wallets",     callback_data="gerir:wallets")],
            [InlineKeyboardButton("🔒 Canais Guard",callback_data="gerir:canais")],
            [InlineKeyboardButton("🔙 Menu",        callback_data="demo:main")],
        ])
    )

# ── Produtos ─────────────────────────────────

async def gerir_produtos(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    linhas = [f"<b>⚙️ Produtos cadastrados ({len(PRODUCTS)})</b>\n"]
    for p in PRODUCTS:
        linhas.append(f"• [{p['id']}] {p['title']} — {p['price']} USDT")
    if not PRODUCTS: linhas.append("(nenhum ainda)")
    rows = [
        [InlineKeyboardButton("➕ Adicionar produto", callback_data="gerir:add_produto")],
    ]
    for p in PRODUCTS:
        rows.append([InlineKeyboardButton(f"🗑️ Remover [{p['id']}] {p['title'][:25]}", callback_data=f"gerir:del_produto:{p['id']}")])
    rows.append([InlineKeyboardButton("🔙 Gerir", callback_data="gerir:menu")])
    await q.edit_message_text("\n".join(linhas), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def gerir_add_produto(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "prod_titulo"}
    await q.edit_message_text(
        "🛍️ <b>Novo Produto — Passo 1/4</b>\n\nEnvia o <b>título</b> do produto:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]])
    )

async def gerir_del_produto(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[2])
    global PRODUCTS; PRODUCTS = [p for p in PRODUCTS if p["id"] != pid]
    await gerir_produtos(u, c)

# ── Tarefas ───────────────────────────────────

async def gerir_tarefas(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    linhas = [f"<b>⚙️ Tarefas cadastradas ({len(TASKS)})</b>\n"]
    for tk in TASKS:
        linhas.append(f"• [{tk['id']}] {tk['title']} — +{tk['reward']} USDT ({tk['verif']})")
    if not TASKS: linhas.append("(nenhuma ainda)")
    rows = [
        [InlineKeyboardButton("➕ Adicionar tarefa", callback_data="gerir:add_tarefa")],
    ]
    for tk in TASKS:
        rows.append([InlineKeyboardButton(f"🗑️ Remover [{tk['id']}] {tk['title'][:25]}", callback_data=f"gerir:del_tarefa:{tk['id']}")])
    rows.append([InlineKeyboardButton("🔙 Gerir", callback_data="gerir:menu")])
    await q.edit_message_text("\n".join(linhas), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def gerir_add_tarefa(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "task_titulo"}
    await q.edit_message_text(
        "📋 <b>Nova Tarefa — Passo 1/4</b>\n\nEnvia o <b>título</b> da tarefa:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]])
    )

async def gerir_del_tarefa(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    tid = int(q.data.split(":")[2])
    global TASKS; TASKS = [t for t in TASKS if t["id"] != tid]
    await gerir_tarefas(u, c)

# ── Wallets ───────────────────────────────────

async def gerir_wallets(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    linhas = [f"<b>⚙️ Wallets cadastradas ({len(WALLETS)})</b>\n"]
    for w in WALLETS:
        linhas.append(f"• [{w['id']}] {w['label']}: <code>{w['addr'][:20]}…</code>")
    if not WALLETS: linhas.append("(nenhuma ainda)")
    rows = [
        [InlineKeyboardButton("➕ Adicionar wallet", callback_data="gerir:add_wallet")],
    ]
    for w in WALLETS:
        rows.append([InlineKeyboardButton(f"🗑️ Remover [{w['id']}] {w['label']}", callback_data=f"gerir:del_wallet:{w['id']}")])
    rows.append([InlineKeyboardButton("🔙 Gerir", callback_data="gerir:menu")])
    await q.edit_message_text("\n".join(linhas), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def gerir_add_wallet(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "wallet_label"}
    await q.edit_message_text(
        "💳 <b>Nova Wallet — Passo 1/2</b>\n\nEnvia o <b>nome/rede</b> da wallet\n(ex: <i>TON Wallet</i>, <i>TRON TRC20</i>):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]])
    )

async def gerir_del_wallet(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    wid = int(q.data.split(":")[2])
    global WALLETS; WALLETS = [w for w in WALLETS if w["id"] != wid]
    await gerir_wallets(u, c)

# ── Canais Guard ──────────────────────────────

async def gerir_canais(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    linhas = [f"<b>⚙️ Canais Guard cadastrados ({len(CHANNELS)})</b>\n"]
    for ch in CHANNELS:
        linhas.append(f"• [{ch['id']}] {ch['label']}: {ch['url']}")
    if not CHANNELS: linhas.append("(nenhum ainda)")
    rows = [
        [InlineKeyboardButton("➕ Adicionar canal", callback_data="gerir:add_canal")],
    ]
    for ch in CHANNELS:
        rows.append([InlineKeyboardButton(f"🗑️ Remover [{ch['id']}] {ch['label']}", callback_data=f"gerir:del_canal:{ch['id']}")])
    rows.append([InlineKeyboardButton("🔙 Gerir", callback_data="gerir:menu")])
    await q.edit_message_text("\n".join(linhas), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def gerir_add_canal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _state[uid] = {"step": "canal_label"}
    await q.edit_message_text(
        "🔒 <b>Novo Canal Guard — Passo 1/2</b>\n\nEnvia o <b>nome</b> do canal\n(ex: <i>📢 SAARS News</i>):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]])
    )

async def gerir_del_canal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    cid = int(q.data.split(":")[2])
    global CHANNELS; CHANNELS = [ch for ch in CHANNELS if ch["id"] != cid]
    await gerir_canais(u, c)

# ── Cancel ────────────────────────────────────

async def gerir_cancel(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    _cancel_state(uid)
    await gerir(u, c)

# ─────────────────────────────────────────────
#  FSM — handle_text: intercepta respostas de cadastro
# ─────────────────────────────────────────────

async def handle_text(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid  = u.effective_user.id
    text = (u.message.text or "").strip()
    st   = _state.get(uid)
    if not st:
        return  # mensagem fora de contexto, ignora

    step = st["step"]

    # ── Onboarding ────────────────────────────
    if step == "onboard_negocio":
        negocio = text[:40]  # limita tamanho
        _uinfo[uid]["negocio"] = negocio
        _onboard.add(uid)
        _cancel_state(uid)
        # Crédito de boas-vindas para activar o ciclo de ganância
        credit(uid, Decimal("5.00"), "bonus", "🎁 Bónus de boas-vindas")
        # Arranca o simulador de actividade em tempo real
        _start_sim(uid, c.bot)
        await u.message.reply_html(
            f"🚀 <b>Bot criado com sucesso!</b>\n\n"
            f"✅ Nome: <b>{negocio}</b>\n"
            f"✅ Loja de produtos: <b>activa</b>\n"
            f"✅ Sistema de tarefas: <b>activo</b>\n"
            f"✅ Referral viral: <b>activo</b>\n"
            f"✅ Pagamentos crypto: <b>activo</b>\n\n"
            f"🎁 <b>+5.00 USDT</b> de bónus de boas-vindas creditados!\n\n"
            f"👇 Explora o teu painel:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🚀 Abrir painel", callback_data="demo:main")
            ]])
        )
        return

    # ── Produto ──────────────────────────────
    if step == "prod_titulo":
        st["titulo"] = text; st["step"] = "prod_desc"
        await u.message.reply_html(
            f"🛍️ <b>Novo Produto — Passo 2/4</b>\n\nTítulo: <i>{text}</i>\n\nAgora envia a <b>descrição</b>:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "prod_desc":
        st["desc"] = text; st["step"] = "prod_preco"
        await u.message.reply_html(
            f"🛍️ <b>Novo Produto — Passo 3/4</b>\n\nAgora envia o <b>preço em USDT</b>\n(ex: <i>5.00</i>):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "prod_preco":
        try:
            preco = Decimal(text.replace(",", "."))
        except Exception:
            await u.message.reply_html("❌ Valor inválido. Envia um número, ex: <code>9.99</code>"); return
        st["preco"] = preco; st["step"] = "prod_delivery"
        await u.message.reply_html(
            f"🛍️ <b>Novo Produto — Passo 4/4</b>\n\nPreço: <i>{preco} USDT</i>\n\nAgora envia o <b>conteúdo de entrega</b>\n(link, texto, código de acesso…):",
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
            f"📋 <b>Nova Tarefa — Passo 2/4</b>\n\nTítulo: <i>{text}</i>\n\nAgora envia a <b>descrição/instrução</b>:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "task_desc":
        st["desc"] = text; st["step"] = "task_reward"
        await u.message.reply_html(
            "📋 <b>Nova Tarefa — Passo 3/4</b>\n\nAgora envia a <b>recompensa em USDT</b>\n(ex: <i>1.50</i>):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")]]))

    elif step == "task_reward":
        try:
            reward = Decimal(text.replace(",", "."))
        except Exception:
            await u.message.reply_html("❌ Valor inválido. Envia um número, ex: <code>1.50</code>"); return
        st["reward"] = reward; st["step"] = "task_verif"
        await u.message.reply_html(
            "📋 <b>Nova Tarefa — Passo 4/4</b>\n\nTipo de verificação:\n• Envia <b>auto</b> — aprovação instantânea\n• Envia <b>manual</b> — user envia comprovante",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ auto",   callback_data="gerir:task_verif:auto"),
                 InlineKeyboardButton("📤 manual", callback_data="gerir:task_verif:manual")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="gerir:cancel")],
            ]))

    # ── Wallet ───────────────────────────────
    elif step == "wallet_label":
        st["label"] = text; st["step"] = "wallet_addr"
        await u.message.reply_html(
            f"💳 <b>Nova Wallet — Passo 2/2</b>\n\nRede: <i>{text}</i>\n\nAgora envia o <b>endereço</b> da wallet:",
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

    # ── Canal Guard ──────────────────────────
    elif step == "canal_label":
        st["label"] = text; st["step"] = "canal_url"
        await u.message.reply_html(
            f"🔒 <b>Novo Canal Guard — Passo 2/2</b>\n\nNome: <i>{text}</i>\n\nAgora envia o <b>link</b> do canal\n(ex: <i>https://t.me/meucanal</i>):",
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
#  Handlers
# ─────────────────────────────────────────────

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = u.effective_user
    uid  = user.id
    _uinfo.setdefault(uid, {})
    _uinfo[uid].update({"username": user.username, "full_name": user.full_name})
    for arg in (c.args or []):
        if arg.startswith("demo_ref_"):
            try: await proc_ref(c, user, int(arg[9:]))
            except: pass
    lang = get_lang(uid, user.language_code)
    _ulang.setdefault(uid, lang)

    # Se já fez onboarding, vai directo ao menu
    if uid in _onboard:
        negocio = _uinfo[uid].get("negocio", "o teu negócio")
        await u.message.reply_html(
            f"👋 Bem-vindo de volta, <b>{user.first_name}</b>!\n\n"
            f"O teu bot <b>{negocio}</b> está pronto. 🚀",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🚀 Abrir painel", callback_data="demo:main")
            ]])
        )
        return

    # Primeiro acesso — pede o nome do negócio
    _state[uid] = {"step": "onboard_negocio"}
    await u.message.reply_html(
        f"👋 Olá, <b>{user.first_name}</b>!\n\n"
        "Vou criar um <b>bot de demonstração</b> personalizado para ti agora mesmo.\n\n"
        "⚡ Leva 10 segundos.\n\n"
        "👇 <b>Qual é o nome do teu negócio ou projecto?</b>\n"
        "<i>(ex: Minha Loja Digital, Curso do João, CriptoClub...)</i>"
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
        [(t(uid,"btn_store"),"demo:loja"),        (t(uid,"btn_tasks"),"demo:tarefas")],
        [(t(uid,"btn_ref"),"demo:ref"),            (t(uid,"btn_balance"),"demo:saldo")],
        [(t(uid,"btn_guard"),"demo:guard"),        (t(uid,"btn_wallets"),"demo:wallets")],
        [(t(uid,"btn_about"),"demo:sobre"),        (t(uid,"btn_lang"),"demo:lang")],
        [("⚙️ Gerir Conteúdo","gerir:menu")],
        [(t(uid,"btn_close"),"demo:fechar")],
    )

async def main_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    uid = u.effective_user.id; b = bal(uid)
    negocio = _uinfo.get(uid, {}).get("negocio", "O teu negócio")

    membros  = 1 + _rcnt.get(uid, 0) * 3 + len(_tdone.get(uid, set())) * 2
    vendas   = len(_purch.get(uid, set())) + _rcnt.get(uid, 0)  # próprias + fictícias
    proj_dia = b * Decimal("2") if b > 0 else Decimal("0")
    proj_mes = b * Decimal("60") if b > 0 else Decimal("0")

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
    txt += f"⚡ <i>O bot está a trabalhar em tempo real.</i>\n"
    txt += f"\n👇 O que queres fazer?"

    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=_mkb(uid))

async def lang_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    uid = u.effective_user.id
    rows = [[InlineKeyboardButton(label, callback_data=f"setlang:{code}")] for code, label in LANG_OPTIONS]
    rows.append([InlineKeyboardButton(t(uid,"btn_menu"), callback_data="demo:main")])
    await q.edit_message_text(t(uid, "lang_select"), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def sobre(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    negocio = _uinfo.get(uid, {}).get("negocio", "o teu negócio")
    await q.edit_message_text(
        f"💡 <b>O que acabaste de ver é o teu bot.</b>\n\n"
        f"<b>{negocio} Bot</b> com loja, tarefas pagas, referral viral e pagamentos crypto — "
        f"tudo configurado, tudo automático.\n\n"
        f"<b>O SAARS entrega isto em menos de 5 minutos.</b>\n\n"
        f"<b>Inclui:</b>\n"
        f"• 🛍️ Loja com entrega automática\n"
        f"• 📋 Tarefas pagas com verificação\n"
        f"• 👥 Referral viral com ranking\n"
        f"• 💰 Carteira interna USDT\n"
        f"• 🔒 Canal Guard\n"
        f"• 💳 Crypto: TON · TRC20 · BEP20 · SOL\n"
        f"• 🌐 10 idiomas automáticos\n\n"
        f"<b>Plano Pro: $20/mês.</b> Sem taxa de setup.\n\n"
        f"👇 O teu bot está à espera:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Activar o meu bot →", url="https://t.me/SAARS_vBOT")],
            [InlineKeyboardButton("🔙 Voltar ao demo",       callback_data="demo:main")],
        ])
    )

async def fechar(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    negocio = _uinfo.get(uid, {}).get("negocio", "o teu negócio")
    b = bal(uid)
    vendas  = len(_purch.get(uid, set()))
    membros = 1 + _rcnt.get(uid, 0) * 3 + len(_tdone.get(uid, set())) * 2
    await q.edit_message_text(
        f"⏸️ <b>Demo pausado.</b>\n\n"
        f"O teu bot <b>{negocio}</b> gerou:\n"
        f"💰 <b>{b:.2f} USDT</b> em saldo\n"
        f"🛍️ <b>{vendas}</b> vendas\n"
        f"👥 <b>{membros}</b> membros\n\n"
        f"🔴 <b>Isto foi só o demo.</b>\n"
        f"No bot real, estes números são dinheiro real.\n\n"
        f"👇 Activa o teu bot agora por <b>$20/mês</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Quero o meu bot real →", url="https://t.me/SAARS_vBOT")],
            [InlineKeyboardButton("🔙 Continuar o demo",        callback_data="demo:main")],
        ])
    )

async def loja(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id; b = bal(uid)
    if not PRODUCTS:
        await q.edit_message_text(
            "🛍️ <b>Loja</b>\n\nNenhum produto cadastrado ainda.\nUsa ⚙️ Gerir para adicionar produtos.",
            parse_mode="HTML",
            reply_markup=kb([("⚙️ Gerir","gerir:produtos"),(t(uid,"btn_menu"),"demo:main")])
        ); return
    rows = []
    for p in PRODUCTS:
        ok = bought(uid, p["id"])
        mark = t(uid,"task_done_mark") if ok else ""
        rows.append([InlineKeyboardButton(f"{mark}{p['title']} — {p['price']} USDT", callback_data=f"pd:{p['id']}")])
    rows.append([InlineKeyboardButton(t(uid,"btn_menu"), callback_data="demo:main")])
    await q.edit_message_text(t(uid,"store_title", bal=f"{b:.2f}"),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def prod_detail(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    b = bal(uid); ok = bought(uid, pid)
    txt = t(uid,"product_detail", title=p["title"], desc=p["desc"], price=p["price"], bal=f"{b:.2f}")
    if ok:
        txt += t(uid,"product_owned")
        rows = [
            [InlineKeyboardButton(t(uid,"btn_delivery"), callback_data="demo:redeliver:"+str(pid))],
            [InlineKeyboardButton(t(uid,"btn_back_store"), callback_data="demo:loja")],
        ]
    else:
        rows = []
        if b >= p["price"]:
            rows.append([InlineKeyboardButton(t(uid,"btn_buy_bal",bal=f"{b:.2f}"), callback_data="demo:buybal:"+str(pid))])
        rows.append([InlineKeyboardButton(t(uid,"btn_buy_crypto"), callback_data="demo:buycrypto:"+str(pid))])
        rows.append([InlineKeyboardButton(t(uid,"btn_back_store"), callback_data="demo:loja")])
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def buybal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    if bought(uid,pid):
        return await q.edit_message_text(t(uid,"already_bought"), reply_markup=kb([(t(uid,"btn_back_store"),"demo:loja")]))
    if not debit(uid, p["price"], "purchase", p["title"]):
        return await q.edit_message_text(
            t(uid,"insufficient",price=p["price"]), parse_mode="HTML",
            reply_markup=kb([(t(uid,"btn_tasks_go"),"demo:tarefas")],[(t(uid,"btn_back_store"),"demo:loja")])
        )
    mbuy(uid, pid)
    negocio = _uinfo.get(uid, {}).get("negocio", "o teu bot")
    primeira = len(_purch.get(uid, set())) == 1
    txt = t(uid,"purchase_ok",delivery=p["delivery"])
    if primeira:
        txt += (
            f"\n\n━━━━━━━━━━━━━━━━\n"
            f"🤯 <b>Acabaste de fazer a tua primeira venda.</b>\n\n"
            f"No bot real do <b>{negocio}</b>, este dinheiro é teu.\n"
            f"Automático. Sem esforço. 24/7.\n\n"
            f"👇 Activa por <b>$20/mês</b>:"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Quero o meu bot real →", url="https://t.me/SAARS_vBOT")],
            [InlineKeyboardButton("🔙 Continuar o demo",        callback_data="demo:loja")],
        ])
    else:
        markup = kb([(t(uid,"btn_back_store"),"demo:loja")])
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=markup)

async def buycrypto(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    wt = "\n".join(f"• <b>{w['label']}</b>:\n  <code>{w['addr']}</code>" for w in WALLETS)
    if not wt: wt = "<i>Nenhuma wallet configurada ainda.</i>"
    await q.edit_message_text(
        t(uid,"crypto_pay", title=p["title"], price=p["price"], wallets=wt),
        parse_mode="HTML",
        reply_markup=kb([(t(uid,"btn_paid"),"demo:confirm:"+str(pid))],[(t(uid,"btn_back_store"),"demo:loja")])
    )

async def confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    mbuy(uid, pid)
    negocio = _uinfo.get(uid, {}).get("negocio", "o teu bot")
    primeira = len(_purch.get(uid, set())) == 1
    txt = t(uid,"confirmed",delivery=p["delivery"])
    if primeira:
        txt += (
            f"\n\n━━━━━━━━━━━━━━━━\n"
            f"🤯 <b>Acabaste de fazer a tua primeira venda.</b>\n\n"
            f"No bot real do <b>{negocio}</b>, este dinheiro é teu.\n"
            f"Automático. Sem esforço. 24/7.\n\n"
            f"👇 Activa por <b>$20/mês</b>:"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Quero o meu bot real →", url="https://t.me/SAARS_vBOT")],
            [InlineKeyboardButton("🔙 Continuar o demo",        callback_data="demo:loja")],
        ])
    else:
        markup = kb([(t(uid,"btn_back_store"),"demo:loja")])
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=markup)

async def redeliver(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    pid = int(q.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    await q.edit_message_text(t(uid,"delivery_title",delivery=p["delivery"]), parse_mode="HTML",
        reply_markup=kb([(t(uid,"btn_back_store"),"demo:loja")]))

async def tarefas(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id; b = bal(uid)
    if not TASKS:
        await q.edit_message_text(
            "📋 <b>Tarefas</b>\n\nNenhuma tarefa cadastrada ainda.\nUsa ⚙️ Gerir para adicionar tarefas.",
            parse_mode="HTML",
            reply_markup=kb([("⚙️ Gerir","gerir:tarefas"),(t(uid,"btn_menu"),"demo:main")])
        ); return
    rows = []
    for tk in TASKS:
        done = tdone(uid, tk["id"])
        mark = t(uid,"task_done_mark") if done else ""
        rows.append([InlineKeyboardButton(f"{mark}{tk['title']} (+{tk['reward']} USDT)", callback_data=f"td:{tk['id']}")])
    rows.append([InlineKeyboardButton(t(uid,"btn_menu"), callback_data="demo:main")])
    await q.edit_message_text(t(uid,"tasks_title",bal=f"{b:.2f}"),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def task_detail(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    tid = int(q.data.split(":")[1])
    tk = next(x for x in TASKS if x["id"]==tid)
    done = tdone(uid, tid)
    txt = t(uid,"task_detail", title=tk["title"], desc=tk["desc"], reward=tk["reward"])
    if done:
        txt += t(uid,"task_detail_done")
        rows = [[InlineKeyboardButton(t(uid,"btn_back_tasks"), callback_data="demo:tarefas")]]
    else:
        btn  = t(uid,"btn_send_proof") if tk["verif"]=="manual" else t(uid,"btn_submit_task")
        cb   = f"demo:tproof:{tid}" if tk["verif"]=="manual" else f"demo:tsubmit:{tid}"
        rows = [
            [InlineKeyboardButton(btn, callback_data=cb)],
            [InlineKeyboardButton(t(uid,"btn_back_tasks"), callback_data="demo:tarefas")],
        ]
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def tsubmit(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    tid = int(q.data.split(":")[1])
    tk = next(x for x in TASKS if x["id"]==tid)
    if tdone(uid,tid):
        return await q.edit_message_text(t(uid,"task_already"),
            reply_markup=kb([(t(uid,"btn_back_tasks"),"demo:tarefas")]))
    mtask(uid,tid); nb = credit(uid, tk["reward"], "task", tk["title"])
    await q.edit_message_text(t(uid,"task_done",reward=tk["reward"],bal=f"{nb:.2f}"),
        parse_mode="HTML",
        reply_markup=kb([(t(uid,"btn_back_tasks"),"demo:tarefas"),(t(uid,"btn_balance"),"demo:saldo")]))

async def tproof(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    tid = int(q.data.split(":")[1])
    _twait[uid] = tid
    await q.edit_message_text(t(uid,"proof_wait"), parse_mode="HTML",
        reply_markup=kb([(t(uid,"proof_cancel"),"demo:tarefas")]))

async def handle_proof(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    tid = _twait.pop(uid, None)
    if tid is None: return
    tk = next((x for x in TASKS if x["id"]==tid), None)
    if not tk: return
    mtask(uid,tid); nb = credit(uid, tk["reward"], "task", tk["title"])
    await u.message.reply_html(
        t(uid,"proof_ok",reward=tk["reward"],bal=f"{nb:.2f}"),
        reply_markup=kb([(t(uid,"btn_back_tasks"),"demo:tarefas"),(t(uid,"btn_balance"),"demo:saldo")])
    )

async def proc_ref(c, user, rid):
    uid = user.id
    if rid==uid or uid in _refs: return
    _uinfo[uid]={"username":user.username,"full_name":user.full_name}
    _refs[uid]=rid; _rcnt[rid]=_rcnt.get(rid,0)+1
    _rearn[rid]=_rearn.get(rid,Decimal("0"))+REFERRAL_REWARD
    credit(rid, REFERRAL_REWARD, "referral", f"Ref: {user.first_name}")
    try:
        await c.bot.send_message(rid,
            t(rid,"new_ref",name=user.first_name,reward=REFERRAL_REWARD),
            parse_mode="HTML", reply_markup=kb([(t(rid,"btn_balance"),"demo:saldo")])
        )
    except: pass

async def ref(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    me = await c.bot.get_me()
    negocio = _uinfo.get(uid, {}).get("negocio", "o teu bot")
    lnk = f"https://t.me/{me.username}?start=demo_ref_{uid}"
    cnt = _rcnt.get(uid, 0); earn = _rearn.get(uid, Decimal("0"))
    # Projecção: se tiver 100 refs ao preço real
    proj = Decimal("100") * REFERRAL_REWARD
    await q.edit_message_text(
        f"👥 <b>Referral — {negocio}</b>\n\n"
        f"🔗 Teu link:\n<code>{lnk}</code>\n\n"
        f"👤 Indicações feitas: <b>{cnt}</b>\n"
        f"💰 Ganho total: <b>{earn:.2f} USDT</b>\n"
        f"🎁 Por indicação: <b>{REFERRAL_REWARD} USDT</b>\n\n"
        f"📈 <i>Com 100 membros indicados → <b>{proj:.0f} USDT</b></i>",
        parse_mode="HTML",
        reply_markup=kb(
            [(t(uid,"btn_ranking"),"demo:ranking")],
            [(t(uid,"btn_menu"),"demo:main")]
        )
    )

async def ranking(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    top = sorted(_rcnt.items(), key=lambda x:x[1], reverse=True)[:10]
    if not top:
        txt = (
            "🏆 <b>Ranking de Indicações</b>\n\n"
            "Ainda ninguém indicou membros.\n\n"
            "<i>No bot real, este ranking é público — "
            "cria competição e faz os membros indicarem mais.</i>"
        )
    else:
        medals = ["🥇","🥈","🥉"]+["🔹"]*7
        lines = ["🏆 <b>Top Indicadores</b>\n"]
        for i,(ruid,cnt) in enumerate(top):
            info = _uinfo.get(ruid,{})
            name = f"@{info['username']}" if info.get("username") else info.get("full_name",f"User {ruid}")
            lines.append(t(uid,"ranking_line",medal=medals[i],name=name,cnt=cnt,earn=f"{_rearn.get(ruid,Decimal('0')):.2f}"))
        txt = "\n".join(lines)
    await q.edit_message_text(
        txt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Referral",              callback_data="demo:ref")],
            [InlineKeyboardButton("🚀 Quero isto no meu bot →", url="https://t.me/SAARS_vBOT")],
        ])
    )

async def saldo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id; b = bal(uid)
    txs = _txs.get(uid,[])
    bloco = ""
    if txs:
        bloco = t(uid,"tx_header")
        icons = {"referral":"👥","task":"📋","purchase":"🛍️"}
        for tx in txs[-5:][::-1]:
            s = "+" if tx["a"]>0 else ""
            bloco += f"{icons.get(tx['t'],'💱')} {s}{tx['a']:.2f} USDT — {tx['n'] or tx['t']}\n"
    await q.edit_message_text(
        t(uid,"balance_title",bal=f"{b:.2f}") + bloco,
        parse_mode="HTML",
        reply_markup=kb([(t(uid,"btn_saldo_tasks"),"demo:tarefas"),(t(uid,"btn_saldo_ref"),"demo:ref")],
                        [(t(uid,"btn_menu"),"demo:main")])
    )

async def guard(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    if not CHANNELS:
        await q.edit_message_text(
            "🔒 <b>Canal Guard</b>\n\nNenhum canal cadastrado ainda.\nUsa ⚙️ Gerir para adicionar.",
            parse_mode="HTML",
            reply_markup=kb([("⚙️ Gerir","gerir:canais"),(t(uid,"btn_menu"),"demo:main")])
        ); return
    ch = "\n".join(f"• {x['label']}: {x['url']}" for x in CHANNELS)
    rows = [[InlineKeyboardButton(x["label"], url=x["url"])] for x in CHANNELS]
    rows += [
        [InlineKeyboardButton(t(uid,"btn_verify"), callback_data="demo:guard_ok")],
        [InlineKeyboardButton(t(uid,"btn_menu"),   callback_data="demo:main")],
    ]
    await q.edit_message_text(t(uid,"guard_title",channels=ch),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows), disable_web_page_preview=True)

async def guard_ok(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer("✅"); uid = u.effective_user.id
    await q.edit_message_text(t(uid,"guard_ok"), parse_mode="HTML",
        reply_markup=kb([(t(uid,"btn_home"),"demo:main")]))

async def wallets(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    if not WALLETS:
        await q.edit_message_text(
            "💳 <b>Carteiras</b>\n\nNenhuma wallet cadastrada ainda.\nUsa ⚙️ Gerir para adicionar.",
            parse_mode="HTML",
            reply_markup=kb([("⚙️ Gerir","gerir:wallets"),(t(uid,"btn_menu"),"demo:main")])
        ); return
    lines = []
    for w in WALLETS:
        qr = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={quote(w['addr'])}"
        lines.append(f"<b>{w['label']}</b>\n<code>{w['addr']}</code>\n🔗 <a href='{qr}'>Ver QR</a>")
    await q.edit_message_text(t(uid,"wallets_title") + "\n\n".join(lines),
        parse_mode="HTML", reply_markup=kb([(t(uid,"btn_menu"),"demo:main")]), disable_web_page_preview=True)

async def _gerir_task_verif_cb(u: Update, c: ContextTypes.DEFAULT_TYPE):
    """Callback dos botões ⚡auto / 📤manual na criação de tarefa."""
    q = u.callback_query; await q.answer(); uid = u.effective_user.id
    verif = q.data.split(":")[2]   # "auto" ou "manual"
    st = _state.get(uid, {})
    if st.get("step") != "task_verif":
        await q.answer("⚠️ Sessão expirada. Começa de novo.", show_alert=True); return
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
#  Router
# ─────────────────────────────────────────────

EXACT = {
    "demo:main":    main_menu, "demo:sobre":   sobre,    "demo:fechar":  fechar,
    "demo:loja":    loja,      "demo:tarefas": tarefas,  "demo:ref":     ref,
    "demo:ranking": ranking,   "demo:saldo":   saldo,    "demo:guard":   guard,
    "demo:guard_ok":guard_ok,  "demo:wallets": wallets,  "demo:lang":    lang_menu,
    # ── Gerir ──
    "gerir:menu":       gerir,
    "gerir:produtos":   gerir_produtos,
    "gerir:tarefas":    gerir_tarefas,
    "gerir:wallets":    gerir_wallets,
    "gerir:canais":     gerir_canais,
    "gerir:add_produto":gerir_add_produto,
    "gerir:add_tarefa": gerir_add_tarefa,
    "gerir:add_wallet": gerir_add_wallet,
    "gerir:add_canal":  gerir_add_canal,
    "gerir:cancel":     gerir_cancel,
}
PREFIX = {
    "pd:":                prod_detail,    "demo:buybal:":    buybal,
    "demo:buycrypto:":    buycrypto,      "demo:confirm:":   confirm,
    "demo:redeliver:":    redeliver,      "td:":             task_detail,
    "demo:tsubmit:":      tsubmit,        "demo:tproof:":    tproof,
    "setlang:":           set_lang,
    # ── Gerir prefix ──
    "gerir:del_produto:": gerir_del_produto,
    "gerir:del_tarefa:":  gerir_del_tarefa,
    "gerir:del_wallet:":  gerir_del_wallet,
    "gerir:del_canal:":   gerir_del_canal,
    "gerir:task_verif:":  _gerir_task_verif_cb,
}

async def router(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not q: return
    await q.answer()
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
    threading.Thread(target=lambda: http.server.HTTPServer(("0.0.0.0", port), _H).serve_forever(), daemon=True).start()
    log.info(f"🌐 HTTP keepalive em :{port}")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("lang",  cmd_lang))
    app.add_handler(CallbackQueryHandler(router))
    # Texto: FSM de cadastro tem prioridade; proof é fallback
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_proof))
    log.info("🚀 SAARS Demo Bot online — n18n 10 línguas ativas")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(run())
