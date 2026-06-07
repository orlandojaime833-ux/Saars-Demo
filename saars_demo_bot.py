# saars_demo_bot.py — arquivo único, sem dependências externas além de python-telegram-bot
# Deploy: adiciona ao GitHub → Render Background Worker → Deploy
# Build Command:  pip install python-telegram-bot==21.*
# Start Command:  python saars_demo_bot.py

from __future__ import annotations
import logging
from decimal import Decimal
from urllib.parse import quote
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
TOKEN           = "8904416244:AAGQkn1ktIzhkSqcF3X7PlWBVy5W37qIvjI"
REFERRAL_REWARD = Decimal("1.00")

# ── ESTADO EM MEMÓRIA ─────────────────────────────────────────────────────────
_bal:   dict[int, Decimal]    = {}
_txs:   dict[int, list]       = {}
_refs:  dict[int, int]        = {}   # referred → referrer
_rcnt:  dict[int, int]        = {}
_rearn: dict[int, Decimal]    = {}
_tdone: dict[int, set]        = {}
_twait: dict[int, int]        = {}   # uid aguardando prova → task_id
_purch: dict[int, set]        = {}
_uinfo: dict[int, dict]       = {}

# ── DADOS ─────────────────────────────────────────────────────────────────────
TASKS = [
    {"id":1,"title":"👥 Entrar no canal SAARS News","desc":"Entre no canal e ganhe saldo demo.","reward":Decimal("1.00"),"verif":"auto"},
    {"id":2,"title":"📸 Enviar screenshot do menu","desc":"Tire um screenshot e envie como comprovante.","reward":Decimal("2.50"),"verif":"manual"},
    {"id":3,"title":"🐦 Seguir no Twitter/X","desc":"Segue a conta oficial e confirma aqui.","reward":Decimal("1.50"),"verif":"auto"},
]
PRODUCTS = [
    {"id":1,"title":"📘 Guia: Monetizar no Telegram","desc":"PDF com 50 estratégias para gerar receita com bots.","price":Decimal("5.00"),
     "delivery":"🎉 <b>Desbloqueado!</b>\n\n• Menu Builder\n• Tarefas pagas\n• Infoprodutos\n• Referral viral\n• Pagamentos crypto\n\n📖 https://t.me/saars_news"},
    {"id":2,"title":"🎥 Mini-curso: Bots do Zero","desc":"6 vídeos práticos do BotFather ao primeiro pagamento.","price":Decimal("12.00"),
     "delivery":"🎉 <b>Acesso liberado!</b>\n\n▶️ https://t.me/saars_news\n\n• Aula 1: BotFather\n• Aula 2: Menu Builder\n• Aula 3: Pagamentos\n• Aula 4: Tarefas\n• Aula 5: Referral\n• Aula 6: Deploy"},
    {"id":3,"title":"🤖 Template SAARS Starter","desc":"Código pronto com menus, loja e referral. Deploy em 5 min.","price":Decimal("20.00"),
     "delivery":"✅ <b>Template desbloqueado!</b>\n\n📦 https://github.com/orlandodev/saars-starter\n\n• bot.py\n• menu_builder.py\n• schema.sql\n• render.yaml"},
]
WALLETS = [
    {"label":"TON Wallet",     "addr":"UQBWs0GY1YzNT8e2_DEMO_TON_ADDRESS_xxx"},
    {"label":"BNB Smart Chain","addr":"0xDEMO_BEP20_ADDRESS_xxxxxxxxxxxxxxx"},
    {"label":"TRON (TRC20)",   "addr":"TDEMO_TRC20_ADDRESS_xxxxxxxxxxxxxxxx"},
]
CHANNELS = [
    {"label":"📢 SAARS Oficial",   "url":"https://t.me/saars_news"},
    {"label":"💬 SAARS Community", "url":"https://t.me/saars_community"},
]

# ── HELPERS ───────────────────────────────────────────────────────────────────
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
def kb(*rows): return InlineKeyboardMarkup([[InlineKeyboardButton(t,callback_data=c) for t,c in r] for r in rows])
def tdone(u,tid): return tid in _tdone.get(u,set())
def mtask(u,tid): _tdone.setdefault(u,set()).add(tid)
def bought(u,pid): return pid in _purch.get(u,set())
def mbuy(u,pid):   _purch.setdefault(u,set()).add(pid)

# ── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = u.effective_user
    _uinfo[user.id] = {"username": user.username, "full_name": user.full_name}
    for arg in (c.args or []):
        if arg.startswith("demo_ref_"):
            try: await proc_ref(c, user, int(arg[9:]))
            except: pass
    await u.message.reply_html(
        f"👋 Olá <b>{user.first_name}</b>!\n\n"
        "🚀 <b>SAARS Demo Bot</b>\n\n"
        "Testa todos os módulos em tempo real — loja, tarefas, referral, saldo e muito mais.\n\n"
        "👇 Clica para começar:",
        reply_markup=kb([("🚀 Abrir Demo","demo:main")])
    )

# ── MENU PRINCIPAL ────────────────────────────────────────────────────────────
MKB = kb(
    [("🛍️ Loja","demo:loja"),       ("📋 Tarefas","demo:tarefas")],
    [("👥 Referral","demo:ref"),     ("💰 Meu Saldo","demo:saldo")],
    [("🔒 Canal Guard","demo:guard"),("💳 Carteiras","demo:wallets")],
    [("ℹ️ Sobre o SAARS","demo:sobre"),("❌ Fechar","demo:fechar")],
)
async def main_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    uid = u.effective_user.id
    b = bal(uid)
    txt = "🚀 <b>SAARS — Demo Interativo</b>\n\nTesta todos os módulos em tempo real.\n\n"
    if b > 0: txt += f"💰 Teu saldo: <b>{b:.2f} USDT</b>\n\n"
    txt += "👇 Escolhe uma secção:"
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=MKB)

# ── SOBRE ─────────────────────────────────────────────────────────────────────
async def sobre(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    await u.callback_query.edit_message_text(
        "ℹ️ <b>O que é o SAARS?</b>\n\n"
        "Plataforma SaaS para criar bots Telegram white-label com monetização completa.\n\n"
        "<b>Inclui:</b>\n"
        "• 🎨 Menu Builder\n• 🛍️ Loja com entrega automática\n• 📋 Tarefas pagas\n"
        "• 👥 Referral com ranking\n• 💰 Saldo interno\n• 🔒 Canal Guard\n"
        "• 💳 Crypto: TON · BEP20 · TRC20 · SOL\n\n"
        "<b>Plano Pro:</b> $20/mês · todos os módulos activos.",
        parse_mode="HTML", reply_markup=kb([("🔙 Menu","demo:main")])
    )

async def fechar(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer("Demo fechado.")
    await u.callback_query.edit_message_text(
        "✅ Demo encerrado. Usa /start para voltar.",
        reply_markup=kb([("🚀 Reabrir","demo:main")])
    )

# ── LOJA ──────────────────────────────────────────────────────────────────────
async def loja(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id; b = bal(uid)
    rows = []
    for p in PRODUCTS:
        ok = bought(uid, p["id"])
        rows.append([InlineKeyboardButton(f"{'✅ ' if ok else ''}{p['title']} — {p['price']} USDT", callback_data=f"pd:{p['id']}")])
    rows.append([InlineKeyboardButton("🔙 Menu","demo:main")])
    await u.callback_query.edit_message_text(
        f"🛍️ <b>Loja de Infoprodutos</b>\n\n💰 Teu saldo: <b>{b:.2f} USDT</b>\n\nEscolhe um produto:",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows)
    )

async def prod_detail(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id
    pid = int(u.callback_query.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    b = bal(uid); ok = bought(uid, pid)
    txt = f"🛍️ <b>{p['title']}</b>\n\n{p['desc']}\n\n💲 <b>{p['price']} USDT</b>\n💰 Teu saldo: <b>{b:.2f} USDT</b>"
    if ok:
        txt += "\n\n✅ <b>Já compraste este produto</b>"
        rows = [[InlineKeyboardButton("📦 Ver entrega","demo:redeliver:"+str(pid))],[InlineKeyboardButton("🔙 Loja","demo:loja")]]
    else:
        rows = []
        if b >= p["price"]: rows.append([InlineKeyboardButton(f"💰 Comprar com saldo ({b:.2f} USDT)","demo:buybal:"+str(pid))])
        rows.append([InlineKeyboardButton("💳 Pagar com crypto (demo)","demo:buycrypto:"+str(pid))])
        rows.append([InlineKeyboardButton("🔙 Loja","demo:loja")])
    await u.callback_query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def buybal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id
    pid = int(u.callback_query.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    if bought(uid,pid):
        return await u.callback_query.edit_message_text("✅ Já compraste.", reply_markup=kb([("🔙 Loja","demo:loja")]))
    if not debit(uid, p["price"], "purchase", p["title"]):
        return await u.callback_query.edit_message_text(
            f"❌ <b>Saldo insuficiente.</b>\n\nPrecisas de {p['price']} USDT.", parse_mode="HTML",
            reply_markup=kb([("📋 Ver Tarefas","demo:tarefas")],[("🔙 Loja","demo:loja")])
        )
    mbuy(uid, pid)
    await u.callback_query.edit_message_text(f"✅ <b>Compra realizada!</b>\n\n{p['delivery']}", parse_mode="HTML", reply_markup=kb([("🔙 Loja","demo:loja")]))

async def buycrypto(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    pid = int(u.callback_query.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    wt = "\n".join(f"• <b>{w['label']}</b>:\n  <code>{w['addr']}</code>" for w in WALLETS)
    await u.callback_query.edit_message_text(
        f"💳 <b>Pagamento Crypto</b>\n\nProduto: {p['title']}\nValor: <b>{p['price']} USDT</b>\n\n{wt}\n\n⚠️ <i>Clica 'Já paguei' após enviar.</i>",
        parse_mode="HTML", reply_markup=kb([("✅ Já paguei","demo:confirm:"+str(pid))],[("🔙 Loja","demo:loja")])
    )

async def confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id
    pid = int(u.callback_query.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    mbuy(uid, pid)
    await u.callback_query.edit_message_text(
        f"✅ <b>Confirmado!</b>\n<i>[Demo: aprovação automática]</i>\n\n{p['delivery']}",
        parse_mode="HTML", reply_markup=kb([("🔙 Loja","demo:loja")])
    )

async def redeliver(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    pid = int(u.callback_query.data.split(":")[1])
    p = next(x for x in PRODUCTS if x["id"]==pid)
    await u.callback_query.edit_message_text(f"📦 <b>Entrega</b>\n\n{p['delivery']}", parse_mode="HTML", reply_markup=kb([("🔙 Loja","demo:loja")]))

# ── TAREFAS ───────────────────────────────────────────────────────────────────
async def tarefas(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id; b = bal(uid)
    rows = []
    for t in TASKS:
        done = tdone(uid, t["id"])
        rows.append([InlineKeyboardButton(f"{'✅ ' if done else ''}{t['title']} (+{t['reward']} USDT)", callback_data=f"td:{t['id']}")])
    rows.append([InlineKeyboardButton("🔙 Menu","demo:main")])
    await u.callback_query.edit_message_text(
        f"📋 <b>Tarefas Pagas</b>\n\n💰 Teu saldo: <b>{b:.2f} USDT</b>\n\nCompleta e recebe automaticamente:",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows)
    )

async def task_detail(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id
    tid = int(u.callback_query.data.split(":")[1])
    t = next(x for x in TASKS if x["id"]==tid)
    done = tdone(uid, tid)
    txt = f"📋 <b>{t['title']}</b>\n\n{t['desc']}\n\n🎁 Recompensa: <b>+{t['reward']} USDT</b>"
    if done:
        txt += "\n\n✅ <b>Já concluída!</b>"
        rows = [[InlineKeyboardButton("🔙 Tarefas","demo:tarefas")]]
    else:
        btn = "📤 Enviar comprovante" if t["verif"]=="manual" else "✅ Concluir tarefa"
        cb  = f"demo:tproof:{tid}" if t["verif"]=="manual" else f"demo:tsubmit:{tid}"
        rows = [[InlineKeyboardButton(btn,cb)],[InlineKeyboardButton("🔙 Tarefas","demo:tarefas")]]
    await u.callback_query.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

async def tsubmit(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id
    tid = int(u.callback_query.data.split(":")[1])
    t = next(x for x in TASKS if x["id"]==tid)
    if tdone(uid,tid):
        return await u.callback_query.edit_message_text("✅ Já concluída!", reply_markup=kb([("🔙","demo:tarefas")]))
    mtask(uid,tid); nb = credit(uid, t["reward"], "task", t["title"])
    await u.callback_query.edit_message_text(
        f"✅ <b>Tarefa concluída!</b>\n\n+{t['reward']} USDT\nNovo saldo: <b>{nb:.2f} USDT</b>\n\n<i>[Demo: verificação automática]</i>",
        parse_mode="HTML", reply_markup=kb([("📋 Tarefas","demo:tarefas"),("💰 Saldo","demo:saldo")])
    )

async def tproof(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id
    tid = int(u.callback_query.data.split(":")[1])
    _twait[uid] = tid
    await u.callback_query.edit_message_text(
        "📤 <b>Envio de Comprovante</b>\n\nEnvia agora uma foto ou ficheiro.",
        parse_mode="HTML", reply_markup=kb([("❌ Cancelar","demo:tarefas")])
    )

async def handle_proof(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    tid = _twait.pop(uid, None)
    if tid is None: return
    t = next((x for x in TASKS if x["id"]==tid), None)
    if not t: return
    mtask(uid,tid); nb = credit(uid, t["reward"], "task", t["title"])
    await u.message.reply_html(
        f"✅ <b>Comprovante aprovado!</b>\n\n+{t['reward']} USDT\nNovo saldo: <b>{nb:.2f} USDT</b>",
        reply_markup=kb([("📋 Tarefas","demo:tarefas"),("💰 Saldo","demo:saldo")])
    )

# ── REFERRAL ──────────────────────────────────────────────────────────────────
async def proc_ref(c, user, rid):
    uid = user.id
    if rid==uid or uid in _refs: return
    _uinfo[uid]={"username":user.username,"full_name":user.full_name}
    _refs[uid]=rid; _rcnt[rid]=_rcnt.get(rid,0)+1
    _rearn[rid]=_rearn.get(rid,Decimal("0"))+REFERRAL_REWARD
    credit(rid, REFERRAL_REWARD, "referral", f"Indicação: {user.first_name}")
    try:
        await c.bot.send_message(rid,
            f"🎉 <b>Nova indicação!</b>\n\n{user.first_name} entrou pelo teu link.\n+{REFERRAL_REWARD} USDT creditado!",
            parse_mode="HTML", reply_markup=kb([("💰 Ver saldo","demo:saldo")])
        )
    except: pass

async def ref(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id
    me = await c.bot.get_me()
    lnk = f"https://t.me/{me.username}?start=demo_ref_{uid}"
    cnt = _rcnt.get(uid,0); earn = _rearn.get(uid,Decimal("0"))
    await u.callback_query.edit_message_text(
        f"👥 <b>Referral</b>\n\n🔗 Teu link:\n<code>{lnk}</code>\n\n"
        f"👤 Indicações: <b>{cnt}</b>\n💰 Ganhos: <b>{earn:.2f} USDT</b>\n🎁 Por indicação: <b>{REFERRAL_REWARD} USDT</b>",
        parse_mode="HTML", reply_markup=kb([("🏆 Ranking","demo:ranking")],[("🔙 Menu","demo:main")])
    )

async def ranking(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    top = sorted(_rcnt.items(), key=lambda x:x[1], reverse=True)[:10]
    if not top:
        txt = "🏆 <b>Ranking</b>\n\nAinda sem indicações!"
    else:
        medals = ["🥇","🥈","🥉"]+["🔹"]*7
        lines = ["🏆 <b>Top Indicadores</b>\n"]
        for i,(uid,cnt) in enumerate(top):
            info = _uinfo.get(uid,{})
            name = f"@{info['username']}" if info.get("username") else info.get("full_name",f"User {uid}")
            lines.append(f"{medals[i]} {name} — {cnt} ref · {_rearn.get(uid,Decimal('0')):.2f} USDT")
        txt = "\n".join(lines)
    await u.callback_query.edit_message_text(txt, parse_mode="HTML", reply_markup=kb([("🔙 Referral","demo:ref")]))

# ── SALDO ─────────────────────────────────────────────────────────────────────
async def saldo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    uid = u.effective_user.id; b = bal(uid)
    txs = _txs.get(uid,[])
    bloco = ""
    if txs:
        bloco = "\n\n📜 <b>Últimas transações:</b>\n"
        icons = {"referral":"👥","task":"📋","purchase":"🛍️"}
        for tx in txs[-5:][::-1]:
            s = "+" if tx["a"]>0 else ""
            bloco += f"{icons.get(tx['t'],'💱')} {s}{tx['a']:.2f} USDT — {tx['n'] or tx['t']}\n"
    await u.callback_query.edit_message_text(
        f"💰 <b>Meu Saldo</b>\n\nSaldo actual: <b>{b:.2f} USDT</b>\n\n"
        "Ganhas completando tarefas e indicando amigos."+bloco,
        parse_mode="HTML", reply_markup=kb([("📋 Tarefas","demo:tarefas"),("👥 Referral","demo:ref")],[("🔙 Menu","demo:main")])
    )

# ── CANAL GUARD ───────────────────────────────────────────────────────────────
async def guard(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    ch = "\n".join(f"• {x['label']}: {x['url']}" for x in CHANNELS)
    rows = [[InlineKeyboardButton(x["label"],url=x["url"])] for x in CHANNELS]
    rows += [[InlineKeyboardButton("✅ Verificar adesão (demo)","demo:guard_ok")],[InlineKeyboardButton("🔙 Menu","demo:main")]]
    await u.callback_query.edit_message_text(
        f"🔒 <b>Canal Guard</b>\n\nBloqueia o acesso até o utilizador ser membro.\n\n<b>Canais:</b>\n{ch}\n\n✅ <i>No demo o acesso é sempre permitido.</i>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows), disable_web_page_preview=True
    )

async def guard_ok(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer("✅ Verificado!")
    await u.callback_query.edit_message_text(
        "✅ <b>Verificação concluída!</b>\n\nMenu desbloqueado.",
        parse_mode="HTML", reply_markup=kb([("🏠 Menu Demo","demo:main")])
    )

# ── CARTEIRAS ─────────────────────────────────────────────────────────────────
async def wallets(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    lines = []
    for w in WALLETS:
        qr = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={quote(w['addr'])}"
        lines.append(f"<b>{w['label']}</b>\n<code>{w['addr']}</code>\n🔗 <a href='{qr}'>Ver QR</a>")
    await u.callback_query.edit_message_text(
        "💳 <b>Carteiras de Pagamento</b>\n\n" + "\n\n".join(lines),
        parse_mode="HTML", reply_markup=kb([("🔙 Menu","demo:main")]), disable_web_page_preview=True
    )

# ── ROUTER ────────────────────────────────────────────────────────────────────
EXACT = {
    "demo:main":    main_menu, "demo:sobre":  sobre,    "demo:fechar": fechar,
    "demo:loja":    loja,      "demo:tarefas":tarefas,  "demo:ref":    ref,
    "demo:ranking": ranking,   "demo:saldo":  saldo,    "demo:guard":  guard,
    "demo:guard_ok":guard_ok,  "demo:wallets":wallets,
}
PREFIX = {
    "pd:":          prod_detail,  "demo:buybal:":  buybal,
    "demo:buycrypto:":buycrypto,  "demo:confirm:": confirm,
    "demo:redeliver:":redeliver,  "td:":           task_detail,
    "demo:tsubmit:":tsubmit,      "demo:tproof:":  tproof,
}

async def router(u: Update, c: ContextTypes.DEFAULT_TYPE):
    data = u.callback_query.data or ""
    if data in EXACT:
        return await EXACT[data](u, c)
    for pfx, fn in PREFIX.items():
        if data.startswith(pfx):
            return await fn(u, c)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(router))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_proof))
    log.info("🚀 SAARS Demo Bot online...")
    app.run_polling(drop_pending_updates=True)
