# menu_builder.py — MenuBuilder para SAARS Demo Bot
# Adiciona ao saars_demo_bot.py: import menu_builder e registra os handlers

from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# ── ESTRUTURA DE MENUS ────────────────────────────────────────────────────────
# Cada menu tem: title, text, rows de botões (label, callback_data ou url)
MENUS: dict[str, dict] = {
    "demo:main": {
        "title": "🚀 SAARS — Demo Interativo",
        "text": (
            "🚀 <b>SAARS — Demo Interativo</b>\n\n"
            "Testa todos os módulos em tempo real.\n\n"
            "👇 Escolhe uma secção:"
        ),
        "rows": [
            [("🛍️ Loja",       "demo:loja"),   ("📋 Tarefas",  "demo:tarefas")],
            [("👥 Referral",   "demo:ref"),    ("💰 Meu Saldo","demo:saldo")],
            [("🔒 Canal Guard","demo:guard"),  ("💳 Carteiras","demo:wallets")],
            [("ℹ️ Sobre",      "demo:sobre"),  ("❌ Fechar",   "demo:fechar")],
        ],
    },
    "demo:sobre": {
        "title": "ℹ️ Sobre o SAARS",
        "text": (
            "ℹ️ <b>O que é o SAARS?</b>\n\n"
            "Plataforma SaaS para criar bots Telegram white-label com monetização completa.\n\n"
            "<b>Inclui:</b>\n"
            "• 🎨 Menu Builder\n"
            "• 🛍️ Loja com entrega automática\n"
            "• 📋 Tarefas pagas\n"
            "• 👥 Referral com ranking\n"
            "• 💰 Saldo interno\n"
            "• 🔒 Canal Guard\n"
            "• 💳 Crypto: TON · BEP20 · TRC20\n\n"
            "<b>Plano Pro:</b> $20/mês · todos os módulos activos."
        ),
        "rows": [
            [("🔙 Menu", "demo:main")],
        ],
    },
    "demo:fechar": {
        "title": "Demo Fechado",
        "text": "✅ Demo encerrado. Usa /start para voltar.",
        "rows": [
            [("🚀 Reabrir", "demo:main")],
        ],
    },
}

# ── BUILDER DE TECLADO ────────────────────────────────────────────────────────
def build_keyboard(rows: list[list[tuple]]) -> InlineKeyboardMarkup:
    """
    rows: lista de linhas, cada linha é lista de (label, value).
    Se value começa com 'http', usa url=; caso contrário, callback_data=.
    """
    kb_rows = []
    for row in rows:
        line = []
        for label, value in row:
            if value.startswith("http"):
                line.append(InlineKeyboardButton(label, url=value))
            else:
                line.append(InlineKeyboardButton(label, callback_data=value))
        kb_rows.append(line)
    return InlineKeyboardMarkup(kb_rows)


def get_menu_markup(menu_key: str, extra_rows: list | None = None) -> InlineKeyboardMarkup:
    """Retorna o InlineKeyboardMarkup de um menu pelo key."""
    menu = MENUS.get(menu_key)
    if not menu:
        return build_keyboard([[("🔙 Voltar", "demo:main")]])
    rows = list(menu["rows"])
    if extra_rows:
        rows = extra_rows + rows
    return build_keyboard(rows)


def get_menu_text(menu_key: str) -> str:
    menu = MENUS.get(menu_key)
    if not menu:
        return "Menu não encontrado."
    return menu["text"]


# ── HANDLERS DE MENUS ESTÁTICOS ───────────────────────────────────────────────
async def handle_static_menu(u: Update, c: ContextTypes.DEFAULT_TYPE, menu_key: str):
    """Handler genérico para menus estáticos definidos em MENUS."""
    q = u.callback_query
    await q.answer()
    await q.edit_message_text(
        get_menu_text(menu_key),
        parse_mode="HTML",
        reply_markup=get_menu_markup(menu_key),
        disable_web_page_preview=True,
    )


async def main_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    from decimal import Decimal
    q = u.callback_query
    await q.answer()
    uid = u.effective_user.id
    # Importa bal do bot principal se disponível, senão usa 0
    try:
        from saars_demo_bot import bal
        b = bal(uid)
    except ImportError:
        b = Decimal("0")

    text = get_menu_text("demo:main")
    if b > 0:
        # Injeta saldo no texto
        text = text.replace(
            "👇 Escolhe uma secção:",
            f"💰 Teu saldo: <b>{b:.2f} USDT</b>\n\n👇 Escolhe uma secção:"
        )
    await q.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=get_menu_markup("demo:main"),
    )


async def sobre(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await handle_static_menu(u, c, "demo:sobre")


async def fechar(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer("Demo fechado.")
    await u.callback_query.edit_message_text(
        get_menu_text("demo:fechar"),
        reply_markup=get_menu_markup("demo:fechar"),
    )


# ── REGISTRO DE HANDLERS ──────────────────────────────────────────────────────
# Dicionário pronto para merge com EXACT no router do bot principal
MENU_EXACT: dict[str, any] = {
    "demo:main":  main_menu,
    "demo:sobre": sobre,
    "demo:fechar": fechar,
}

# ── UTILITÁRIOS ───────────────────────────────────────────────────────────────
def register_menu(key: str, title: str, text: str, rows: list[list[tuple]]):
    """
    Registra um novo menu em runtime.

    Exemplo:
        register_menu(
            key="demo:promo",
            title="🎁 Promoção",
            text="<b>Promoção especial!</b>\\n\\nGanha 5 USDT agora.",
            rows=[
                [("✅ Resgatar", "demo:resgate")],
                [("🔙 Menu", "demo:main")],
            ]
        )
    """
    MENUS[key] = {"title": title, "text": text, "rows": rows}


def add_button_to_menu(menu_key: str, label: str, value: str, row: int = -1):
    """
    Adiciona um botão a um menu existente.
    row=-1 adiciona numa nova linha no final (antes do botão 🔙).
    """
    if menu_key not in MENUS:
        raise KeyError(f"Menu '{menu_key}' não existe.")
    rows = MENUS[menu_key]["rows"]
    back_row = None
    # Preserva botão 🔙 sempre no final
    if rows and any(v.startswith("demo:") for _, v in rows[-1]):
        last = rows[-1]
        if any("🔙" in lbl for lbl, _ in last):
            back_row = rows.pop()
    if row == -1 or row >= len(rows):
        rows.append([(label, value)])
    else:
        rows[row].append((label, value))
    if back_row:
        rows.append(back_row)


def list_menus() -> list[str]:
    """Retorna todos os keys de menus registrados."""
    return list(MENUS.keys())
