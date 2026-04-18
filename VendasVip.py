# -*- coding: utf-8 -*-
"""
========================================================================
                       VIP LAUNCHER SYSTEM v3.0
========================================================================

    Desenvolvido por: PrimeStudio
    Contato: primestudiosx@gmail.com
    
    Direitos Autorais (c) 2025 PrimeStudio. Todos os direitos reservados.
    
    Este software é proprietário e confidencial. 
    O uso, cópia ou distribuição não autorizada deste código 
    é estritamente proibido sem autorização prévia.

========================================================================
"""

import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
import pytz
import random
import math
import asyncio
import uuid
import json
import shutil
from functools import wraps
import qrcode
import io

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat, User
from telegram.constants import ChatAction
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler, ChatMemberHandler,
    PicklePersistence
)
from telegram.request import HTTPXRequest

# --- CONFIGURAÇÃO INICIAL ---
TOKEN = ""
OWNER_ID = 1
CHAVE_PIX = ""
CIDADE_COBRANCA = ""
NOME_VENDEDOR = ""
TIMEZONE = ""

# --- PLANOS DE ASSINATURA ---
PLANS = {
    "semanal": {"name": "Assinatura Semanal", "price": "9.99", "days": 7},
    "mensal": {"name": "Assinatura Mensal", "price": "14.99", "days": 30},
    "vitalicio": {"name": "Assinatura Vitalícia", "price": "29.99", "days": 9999},
}
# VALOR PADRÃO, PODE SER ALTERADO PELO COMANDO /setdesconto
DEFAULT_DISCOUNT_PRICE_ABANDONED = "12.99"
REENGAGE_DELAY_MINUTES = 20
CONTINUE_CONVO_DELAY_MINUTES = 3
PAYMENT_REMINDER_MINUTES = 10 # Tempo para lembrar o cliente de um pagamento pendente.

# --- Configuração de Caminhos (Paths) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DB_FOLDER, "subscriptions.db")
AD_MEDIA_FOLDER = os.path.join(BASE_DIR, "media_anuncios")
BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")

# --- Configuração dos Grupos ---
# ATENÇÃO: Verifique se os IDs estão nos lugares corretos!
TARGET_GROUP_ID = -  # << GRUPO PÚBLICO
ADMIN_GROUP_ID = -  # << GRUPO DE ADMINS
LOG_GROUP_ID = - # << GRUPO DE LOGS
VIP_GROUP_ID = -      # << GRUPO VIP
STORAGE_CHANNEL_ID = - # << CANAL PRIVADO

# --- Mensagens Automáticas para Anúncios (Carregadas da DB) ---
AD_MESSAGE_TEXTS = []
SEXY_FOLLOW_UPS = []
SEXY_COMPLIMENTS = []

# --- Banco de Frases Variadas (Valores Padrão) ---
DEFAULT_AD_MESSAGE_TEXTS = [
    (
        "🔞 **MILHARES DE VÍDEOS E FOTOS EXCLUSIVAS NO VIP** 🔞\n\n"
        "💥 +50 MIL mídias pra você gozar muito!\n\n"
        "🔥 Putaria, suruba, incesto, novinhas e os melhores vazados\n\n"
        "💎 As mais gostosas do Privacy e OnlyFans, tudo num só lugar\n\n"
        "📲 Acesso imediato e novidades todo dia\n"
        "🚨 **PROMOÇÃO IMPERDÍVEL!**\n\n"
        "De <s>R$ 22,49</s> por apenas **R$ 14,99** — <i>por tempo LIMITADO!</i>"
    ),
]
DEFAULT_SEXY_FOLLOW_UPS = [
    "Ué, cadê você, tesão? Amarelou de repente? kkkk relaxa, eu não mordo... a não ser que você peça.", "Ainda tá aí, gostoso? Pensei que a gente ia se divertir hoje... Vai me deixar esperando?",
]
DEFAULT_SEXY_COMPLIMENTS = [
    "Gostei de ver... adoro homem de atitude que responde rápido 😏", "Hmm, sabia que você não ia resistir. Gosto assim, direto ao ponto. Sem enrolação. 😈", "Assim que eu gosto! Homem que sabe o que quer. Me deixa louca. 🔥",
]

CONVERSATION_TEASER_MESSAGES = [
    "Amor, vou te mostrar uma coisinha pra ver se te anima... 😏", "Gosto de quem tem atitude... Toma um presentinho pra te inspirar. 🔥",
    "Acho que você tá merecendo um mimo... Vê se gosta disso aqui. 😉", "Tô gostando da nossa conversa. Deixa eu te mostrar um segredinho...",
    "Abre aí... É um presente especial, só pra você. 😈"
]
INTERACTION_TRIGGER_COUNT = 3

# --- Textos e Botões ---
BUTTON_TEXTS = {
    "previous_page": "⬅️ Voltar", "next_page": "Avançar ➡️", "back_to_list": "⬅️ Voltar para a Lista",
    "plan_button": "💎 {plan_name} • R${price}", "plan_button_discount": "🔥 {plan_name} • De <s>R${original_price}</s> por R${discounted_price}",
    "talk_private": "😈 Iniciar Conversa", "renew_subscription": "🔥 QUERO RENOVAR AGORA 🔥",
    "renew_with_30_off": "😈 Renovar com 30% OFF", "renew_with_50_off": "😈 Renovar com 50% OFF",
    "approve_payment": "✅ Aprovar", "deny_payment": "❌ Recusar",
    "want_to_be_vip": "😈 ENTRAR NO PARAÍSO AGORA 😈", "see_plans_and_become_vip": "🔞 QUERO ACESSO TOTAL 🔞",
    "go_to_portfolio": "➡️ Ver Portfólio Completo",
}
OFFER_DURATION_MINUTES = 15

# --- Validação das Configurações ---
PLACEHOLDER_TOKEN = "SEU_TOKEN_AQUI"
PLACEHOLDER_OWNER_ID = 
PLACEHOLDER_GROUP_ID = -
PLACEHOLDER_CHANNEL_ID = -

if (PLACEHOLDER_TOKEN in TOKEN or OWNER_ID == PLACEHOLDER_OWNER_ID or TARGET_GROUP_ID == PLACEHOLDER_GROUP_ID or
    VIP_GROUP_ID == PLACEHOLDER_GROUP_ID or LOG_GROUP_ID == PLACEHOLDER_GROUP_ID or STORAGE_CHANNEL_ID == PLACEHOLDER_CHANNEL_ID):
    print("--- ERRO CRÍTICO DE CONFIGURAÇÃO ---")
    if PLACEHOLDER_TOKEN in TOKEN: print("- A variável 'TOKEN' não foi alterada.")
    if OWNER_ID == PLACEHOLDER_OWNER_ID: print("- A variável 'OWNER_ID' não foi alterada.")
    if TARGET_GROUP_ID == PLACEHOLDER_GROUP_ID: print("- A variável 'TARGET_GROUP_ID' não foi alterada.")
    if VIP_GROUP_ID == PLACEHOLDER_GROUP_ID: print("- A variável 'VIP_GROUP_ID' não foi alterada.")
    if LOG_GROUP_ID == PLACEHOLDER_GROUP_ID: print("- A variável 'LOG_GROUP_ID' não foi alterada.")
    if STORAGE_CHANNEL_ID == PLACEHOLDER_CHANNEL_ID: print("- A variável 'STORAGE_CHANNEL_ID' não foi alterada.")
    exit()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

CATALOGO_ATRIZES = []
PORTFOLIO_CACHE = {}

# --- DECORATOR DE ADMIN ---
def admin_required(allowed_chat_ids: list[int] = None, admin_check_chat_id: int = None):
    """
    Decorator para restringir o acesso a comandos a administradores específicos em chats permitidos.
    """
    def decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user = update.effective_user
            chat_id = update.effective_chat.id
            
            if allowed_chat_ids and chat_id not in allowed_chat_ids:
                return

            check_id = admin_check_chat_id or ADMIN_GROUP_ID
            
            try:
                chat_admins = await context.bot.get_chat_administrators(check_id)
                if user.id not in {admin.user.id for admin in chat_admins}:
                    if update.callback_query:
                        await update.callback_query.answer("Acesso negado.", show_alert=False)
                    return
            except Exception as e:
                logger.error(f"Erro ao verificar o estado de admin para o utilizador {user.id} no decorator: {e}")
                return

            return await func(update, context, *args, **kwargs)
        return wrapped
    return decorator

# --- ESTADOS DA CONVERSA ---
SELECT_METHOD, SELECT_ACTION, AWAIT_NAME, AWAIT_TYPED_NAME, RECEIVING_MEDIA = range(5)
AWAIT_VIDEO = range(5, 6)
AWAIT_CONTENT, AWAIT_BUTTON, AWAIT_CONFIRMATION = range(6, 9)
AWAIT_DAYS_TO_ADJUST, AWAIT_USER_ID_TO_SEARCH = range(9, 11)
AWAITING_ANY_REPLY = range(11, 12)
AWAIT_WELCOME_MEDIA = range(12, 13)
AWAIT_TARGET_ID, AWAIT_MESSAGE_TO_SEND = range(13, 15)
MANAGE_PHRASES_MENU, AWAIT_PHRASE_TO_ADD = range(15, 17)

# --- BASE DE DADOS E CONFIGS DINÂMICAS ---
def setup_database():
    os.makedirs(DB_FOLDER, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_id INTEGER PRIMARY KEY, user_name TEXT, start_date TEXT, expiry_date TEXT,
        plan_name TEXT, status TEXT, reminder_sent INTEGER DEFAULT 0,
        discount_offer_sent INTEGER DEFAULT 0
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS media_catalog (
        id INTEGER PRIMARY KEY AUTOINCREMENT, actress_name TEXT NOT NULL,
        file_id TEXT NOT NULL UNIQUE, file_type TEXT NOT NULL, -- 'photo' ou 'video'
        duration INTEGER DEFAULT 0
    )""")
    cursor.execute("CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS click_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, user_name TEXT,
        plan_name TEXT, price REAL, log_type TEXT, timestamp TEXT NOT NULL,
        actress_name TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS welcome_media (
        id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT NOT NULL UNIQUE, file_type TEXT NOT NULL
    )""")

    # Migrações de tabelas
    try: cursor.execute("ALTER TABLE subscriptions ADD COLUMN plan_name TEXT")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE subscriptions ADD COLUMN reminder_sent INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE subscriptions ADD COLUMN discount_offer_sent INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE subscriptions ADD COLUMN renewal_source TEXT")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE subscriptions ADD COLUMN price_paid REAL DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE subscriptions ADD COLUMN dias_ajustados INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE media_catalog ADD COLUMN duration INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE click_logs ADD COLUMN actress_name TEXT")
    except sqlite3.OperationalError: pass
        
    conn.commit()
    conn.close()
    logger.info(f"Base de dados '{DB_PATH}' inicializada com sucesso.")

def load_dynamic_configs():
    """Carrega configurações dinâmicas (frases, etc.) da base de dados."""
    global AD_MESSAGE_TEXTS, SEXY_FOLLOW_UPS, SEXY_COMPLIMENTS
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        configs = {
            "ad_message_texts": {"global_var": "AD_MESSAGE_TEXTS", "default": DEFAULT_AD_MESSAGE_TEXTS},
            "sexy_follow_ups": {"global_var": "SEXY_FOLLOW_UPS", "default": DEFAULT_SEXY_FOLLOW_UPS},
            "sexy_compliments": {"global_var": "SEXY_COMPLIMENTS", "default": DEFAULT_SEXY_COMPLIMENTS},
        }

        for key, config in configs.items():
            cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            if result and result[0]:
                try:
                    globals()[config["global_var"]] = json.loads(result[0])
                except json.JSONDecodeError:
                    globals()[config["global_var"]] = config["default"]
                    logger.warning(f"Erro ao descodificar JSON para '{key}'. A usar o valor padrão.")
            else:
                globals()[config["global_var"]] = config["default"]
                # Guardar o valor padrão na base de dados se não existir
                cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)", (key, json.dumps(config["default"])))
        conn.commit()
    logger.info("Configurações dinâmicas (frases) carregadas.")

def build_catalog_from_db():
    global CATALOGO_ATRIZES
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT actress_name, file_id, file_type, duration FROM media_catalog ORDER BY actress_name, id")
    
    catalog_dict = {}
    for actress_name, file_id, file_type, duration in cursor.fetchall():
        if actress_name not in catalog_dict:
            catalog_dict[actress_name] = {"name": actress_name, "media_files": []}
        catalog_dict[actress_name]["media_files"].append({"id": file_id, "type": file_type, "duration": duration or 0})
    
    CATALOGO_ATRIZES = sorted(list(catalog_dict.values()), key=lambda x: x['name'])
    logger.info(f"{len(CATALOGO_ATRIZES)} atrizes carregadas no catálogo a partir da base de dados.")
    conn.close()

def load_portfolio_cache():
    """Carrega o cache de IDs de mensagens de portfólio da base de dados para a memória."""
    global PORTFOLIO_CACHE
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = 'portfolio_cache'")
            result = cursor.fetchone()
            if result and result[0]:
                PORTFOLIO_CACHE = json.loads(result[0])
                logger.info(f"Cache de portfólio carregado com {len(PORTFOLIO_CACHE)} entradas.")
            else:
                PORTFOLIO_CACHE = {}
                logger.info("Nenhum cache de portfólio persistente encontrado. A iniciar um novo.")
    except Exception as e:
        logger.error(f"Erro ao carregar o cache de portfólio da base de dados: {e}")
        PORTFOLIO_CACHE = {}

def save_portfolio_cache():
    """Guarda o cache de portfólio da memória para a base de dados."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cache_json = json.dumps(PORTFOLIO_CACHE)
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", ('portfolio_cache', cache_json))
            conn.commit()
    except Exception as e:
        logger.error(f"Erro ao guardar o cache de portfólio na base de dados: {e}")

# --- GERAÇÃO DO BR CODE (PIX) ---
def gerar_br_code(chave_pix, preco, nome_vendedor, cidade, txid="***"):
    # O 'txid' para um QR code com valor definido não deve ser '***'.
    # Alguns aplicativos de banco são rigorosos e exigem um ID alfanumérico.
    # Se o txid padrão for usado, geramos um compatível.
    final_txid = txid
    if final_txid == "***":
        final_txid = re.sub(r'[^a-zA-Z0-9]', '', str(uuid.uuid4()))[:25]

    nome_vendedor = re.sub(r'[^a-zA-Z0-9\s]', '', nome_vendedor).upper()[:25]
    cidade = re.sub(r'[^a-zA-Z0-9\s]', '', cidade).upper()[:15]
    payload_format = '000201'
    merchant_account = (f'26{len("0014BR.GOV.BCB.PIX" + "01" + f"{len(chave_pix):02}" + chave_pix):02}0014BR.GOV.BCB.PIX01{len(chave_pix):02}{chave_pix}')
    merchant_category = '52040000'
    transaction_currency = '5303986'
    transaction_amount = f'54{len(preco):02}{preco}'
    country_code = '5802BR'
    merchant_name = f'59{len(nome_vendedor):02}{nome_vendedor}'
    merchant_city = f'60{len(cidade):02}{cidade}'
    additional_data = f'62{len("05" + f"{len(final_txid):02}" + final_txid):02}05{len(final_txid):02}{final_txid}'
    payload_to_crc = (f'{payload_format}{merchant_account}{merchant_category}{transaction_currency}{transaction_amount}{country_code}{merchant_name}{merchant_city}{additional_data}6304')
    polinomio = 0x1021
    resultado = 0xFFFF
    for byte in payload_to_crc.encode('utf-8'):
        resultado ^= (byte << 8)
        for _ in range(8):
            if (resultado & 0x8000):
                resultado = (resultado << 1) ^ polinomio
            else:
                resultado <<= 1
    crc16 = f'{resultado & 0xFFFF:04X}'
    return f'{payload_to_crc}{crc16}'

# --- FUNÇÕES AUXILIARES ---
async def check_admin_permissions(context: ContextTypes.DEFAULT_TYPE, chat_id: int, permissions: list[str]) -> tuple[bool, str]:
    try:
        bot_member = await context.bot.get_chat_member(chat_id=chat_id, user_id=context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            return False, f"O bot não é administrador no grupo <code>{chat_id}</code>."

        missing_perms = [f"<code>{perm}</code>" for perm in permissions if not getattr(bot_member, perm, False)]
        if missing_perms:
            return False, f"O bot é admin no grupo <code>{chat_id}</code>, mas falta(m) a(s) permissão(ões): {', '.join(missing_perms)}."
        return True, "Todas as permissões necessárias estão presentes."
    except Exception as e:
        return False, f"Erro inesperado ao verificar permissões: {e}"

async def simulate_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int, min_delay: float = 1.5, max_delay: float = 3.0):
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(random.uniform(min_delay, max_delay))

async def log_click(context: ContextTypes.DEFAULT_TYPE, user: User, plan: dict, price: str, log_type: str):
    try:
        user_name = f"{user.first_name} {user.last_name or ''}".strip()
        timestamp = datetime.now(pytz.timezone(TIMEZONE)).isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO click_logs (user_id, user_name, plan_name, price, log_type, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (user.id, user_name, plan['name'], float(price), log_type, timestamp)
            )
            conn.commit()
        
        notification_text = (
            f"💡 **Novo Interesse de Compra!** 💡\n\n"
            f"👤 <b>Utilizador:</b> {user_name} (<code>{user.id}</code>)\n"
            f"💎 <b>Plano:</b> {plan['name']}\n💰 <b>Valor:</b> R${price}\n"
            f"ℹ️ <b>Origem:</b> {log_type}"
        )
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=notification_text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Erro ao registar/notificar clique: {e}", exc_info=True)

async def log_engagement(context: ContextTypes.DEFAULT_TYPE, user: User, actress_name: str, log_type: str):
    """Registra cliques de engajamento (visualização de prévia/portfólio)."""
    try:
        user_name = f"{user.first_name} {user.last_name or ''}".strip()
        timestamp = datetime.now(pytz.timezone(TIMEZONE)).isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO click_logs (user_id, user_name, log_type, timestamp, actress_name) VALUES (?, ?, ?, ?, ?)",
                (user.id, user_name, log_type, timestamp, actress_name)
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Erro ao registrar engajamento: {e}", exc_info=True)


def get_plans_markup_and_text(user_first_name: str, discount_percentage: int = 0):
    keyboard = []
    text = f"E aí, {user_first_name}! 😏\n\n"
    if discount_percentage > 0:
        text += f"Você ganhou um presente... 🔥\n\nLiberamos um desconto **EXCLUSIVO** de <b>{discount_percentage}%</b> para você voltar ao jogo!\n\nEscolha o seu plano com o novo valor:"
    else:
        text += "Cansado de prévias? É hora do show principal. 😈\n\nEscolha um dos nossos planos VIP e liberte o acesso a **TUDO**, sem restrições:"

    for plan_id, plan_details in PLANS.items():
        original_price = float(plan_details['price'])
        if discount_percentage > 0:
            discounted_price = original_price * (1 - discount_percentage / 100)
            button_text = BUTTON_TEXTS["plan_button_discount"].format(plan_name=plan_details['name'], original_price=f"{original_price:.2f}", discounted_price=f"{discounted_price:.2f}")
            callback_data = f"select_plan_discount:{plan_id}:{discounted_price:.2f}:{discount_percentage}"
        else:
            button_text = BUTTON_TEXTS["plan_button"].format(plan_name=plan_details['name'], price=plan_details['price'])
            callback_data = f"select_plan:{plan_id}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    return text, InlineKeyboardMarkup(keyboard)

async def show_actress_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    ITEMS_PER_PAGE = 50
    start_index = page * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    page_items = CATALOGO_ATRIZES[start_index:end_index]
    
    if not page_items:
        text_to_send = "O catálogo de atrizes ainda está vazio. Novidades em breve! 🔥"
        if update.callback_query: await update.callback_query.edit_message_text(text_to_send)
        else: await context.bot.send_message(chat_id=update.effective_chat.id, text=text_to_send)
        return

    keyboard = []
    for i in range(0, len(page_items), 2):
        row = [InlineKeyboardButton(page_items[i]['name'], callback_data=f"show_actress_portfolio:{start_index + i}:{page}")]
        if i + 1 < len(page_items):
            row.append(InlineKeyboardButton(page_items[i+1]['name'], callback_data=f"show_actress_portfolio:{start_index + i + 1}:{page}"))
        keyboard.append(row)

    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(BUTTON_TEXTS["previous_page"], callback_data=f"actress_page:{page - 1}"))
    total_pages = math.ceil(len(CATALOGO_ATRIZES) / ITEMS_PER_PAGE) if CATALOGO_ATRIZES else 1
    if end_index < len(CATALOGO_ATRIZES): nav_row.append(InlineKeyboardButton(BUTTON_TEXTS["next_page"], callback_data=f"actress_page:{page + 1}"))
    if nav_row: keyboard.append(nav_row)
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"MENU DE ATRIZES (Página {page + 1}/{total_pages}):"
    
    if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        if update.message: await update.message.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

async def show_previa_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not CATALOGO_ATRIZES:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="O catálogo de prévias ainda está vazio.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'previa_timestamp'")
    timestamp_str = cursor.fetchone()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'previa_indices'")
    indices_str = cursor.fetchone()
    conn.close()

    now = datetime.now(pytz.timezone(TIMEZONE))
    force_refresh = True
    unlocked_indices = []

    if timestamp_str and indices_str:
        try:
            if now - datetime.fromisoformat(timestamp_str[0]) < timedelta(hours=48):
                force_refresh = False
                unlocked_indices = json.loads(indices_str[0])
        except (ValueError, json.JSONDecodeError):
            force_refresh = True

    if force_refresh:
        all_indices = list(range(len(CATALOGO_ATRIZES)))
        num_to_select = min(len(all_indices), 7)
        unlocked_indices = random.sample(all_indices, num_to_select)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", ('previa_timestamp', now.isoformat()))
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", ('previa_indices', json.dumps(unlocked_indices)))
        conn.commit()
        conn.close()

    sorted_for_display = sorted(CATALOGO_ATRIZES, key=lambda actress: CATALOGO_ATRIZES.index(actress) not in unlocked_indices)
    
    keyboard = []
    row = []
    for actress_data in sorted_for_display:
        index = CATALOGO_ATRIZES.index(actress_data)
        if index in unlocked_indices:
            button = InlineKeyboardButton(f"🔓 {actress_data['name']}", callback_data=f"show_teaser_portfolio:{index}")
        else:
            button = InlineKeyboardButton(f"🔒 {actress_data['name']}", callback_data="show_vip_prompt")
        row.append(button)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = ("😈🔥 **DEGUSTAÇÃO LIBERADA!** 🔥😈\n\n"
            "Liberamos uma prévia de algumas das nossas deusas por tempo limitado. As que estão sem cadeado 🔓 vão dar-te um gostinho do paraíso...\n\n"
            "Queres o cardápio completo, sem restrições? 🔞\n"
            "**ACESSE TUDO** e muito mais tornando-te um membro VIP agora mesmo!")
    
    if update.message: await update.message.delete()
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode='HTML')

async def send_actress_portfolio(context: ContextTypes.DEFAULT_TYPE, chat_id: int, actress_index: int, page_for_back_button: int | None = None, reply_to_message_id: int | None = None):
    try:
        actress = CATALOGO_ATRIZES[actress_index]
        actress_name = actress['name']
        if actress_name in PORTFOLIO_CACHE:
            message_id = PORTFOLIO_CACHE[actress_name]
            link_chat_id = str(chat_id).replace("-100", "")
            message_link = f"https://t.me/c/{link_chat_id}/{message_id}"
            keyboard_list = [[InlineKeyboardButton(BUTTON_TEXTS["go_to_portfolio"], url=message_link)]]
            if page_for_back_button is not None:
                keyboard_list.append([InlineKeyboardButton(BUTTON_TEXTS["back_to_list"], callback_data=f"actress_page:{page_for_back_button}")])
            await context.bot.send_message(chat_id=chat_id, text=f"O material completo de <b>{actress['name']}</b> já foi postado aqui.\n\nClique no botão abaixo para ir direto para ele. 🔥", reply_markup=InlineKeyboardMarkup(keyboard_list), parse_mode='HTML', reply_to_message_id=reply_to_message_id)
            return

        chunks = [actress['media_files'][i:i + 10] for i in range(0, len(actress['media_files']), 10)]
        if not chunks:
            await context.bot.send_message(chat_id=chat_id, text=f"Nenhuma mídia encontrada para {actress['name']}.", reply_to_message_id=reply_to_message_id)
            return

        first_message_id_stored = False
        for i, chunk_data in enumerate(chunks):
            media_group = [ (InputMediaPhoto if m['type'] == 'photo' else InputMediaVideo)(media=m['id'], caption=f"<b>{actress['name']}</b>" if i == 0 and j == 0 else None, parse_mode='HTML') for j, m in enumerate(chunk_data) ]
            sent_messages = await context.bot.send_media_group(chat_id=chat_id, media=media_group, protect_content=True)
            if not first_message_id_stored and sent_messages:
                PORTFOLIO_CACHE[actress_name] = sent_messages[0].message_id
                save_portfolio_cache()
                first_message_id_stored = True
            await asyncio.sleep(1)
        
        final_keyboard = []
        if page_for_back_button is not None:
            final_keyboard.append([InlineKeyboardButton(BUTTON_TEXTS["back_to_list"], callback_data=f"actress_page:{page_for_back_button}")])
        if final_keyboard:
            await context.bot.send_message(chat_id=chat_id, text=f"Fim do material de <b>{actress['name']}</b>.", reply_markup=InlineKeyboardMarkup(final_keyboard), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Erro ao enviar portfólio de atriz (índice {actress_index}): {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="Ocorreu um erro ao carregar o portfólio. Tente novamente.", reply_to_message_id=reply_to_message_id)

async def send_actress_teaser(context: ContextTypes.DEFAULT_TYPE, chat_id: int, actress_index: int):
    try:
        actress = CATALOGO_ATRIZES[actress_index]
        eligible_media = [m for m in actress['media_files'] if m['type'] == 'photo' or (m['type'] == 'video' and m.get('duration', 0) <= 30)]
        if not eligible_media:
            await context.bot.send_message(chat_id=chat_id, text=f"Ops! No momento não temos mídias de prévia disponíveis para {actress['name']}.")
            return
        
        selected_media = random.sample(eligible_media, min(len(eligible_media), 2))
        media_group = [(InputMediaPhoto if m['type'] == 'photo' else InputMediaVideo)(media=m['id'], caption=f"🔥 Uma provinha de <b>{actress['name']}</b> 🔥" if i == 0 else None, parse_mode='HTML') for i, m in enumerate(selected_media)]
        await context.bot.send_media_group(chat_id=chat_id, media=media_group)
        await asyncio.sleep(1)

        bot_username = (await context.bot.get_me()).username
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["see_plans_and_become_vip"], url=f"https://t.me/{bot_username}?start=vip")]])
        cta_text = (f"😈🔥 **ISSO É SÓ O COMEÇO!** 🔥😈\n\n"
                    f"A prévia de <b>{actress['name']}</b> deixou-te a querer mais? 😏\n\n"
                    "No <b>Grupo VIP</b>, o ensaio dela é **COMPLETO** e **SEM CENSURA**, junto com o de todas as minhas outras amigas deliciosas. Não percas tempo, o acesso é imediato!\n\n"
                    "👇🏼 **CLIQUE ABAIXO E LIBERTE TUDO AGORA MESMO!** 💦")
        await context.bot.send_message(chat_id=chat_id, text=cta_text, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Erro ao enviar prévia da atriz (índice {actress_index}): {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="Ocorreu um erro ao carregar a prévia.")

async def send_conversation_teaser(context: ContextTypes.DEFAULT_TYPE, chat_id: int, actress_index: int):
    try:
        actress = CATALOGO_ATRIZES[actress_index]
        eligible_photos = [m for m in actress['media_files'] if m['type'] == 'photo']
        if not eligible_photos: return
        selected_photo = random.choice(eligible_photos)
        caption = random.choice(CONVERSATION_TEASER_MESSAGES)
        await context.bot.send_photo(chat_id=chat_id, photo=selected_photo['id'], caption=caption)
    except Exception as e:
        logger.error(f"Erro ao enviar teaser de conversa da atriz (índice {actress_index}): {e}", exc_info=True)

# --- Handlers de Comandos ---
def cancel_all_follow_ups(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    for job in context.job_queue.get_jobs_by_name(f"continue_convo_{user_id}"): job.schedule_removal()
    for job in context.job_queue.get_jobs_by_name(f"reengage_{user_id}"): job.schedule_removal()
    if user_id in context.application.user_data:
        context.application.user_data[user_id]['conversation_active'] = False

async def start_command_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.chat.type != 'private':
        bot_username = (await context.bot.get_me()).username
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["talk_private"], url=f"https://t.me/{bot_username}?start=default")]])
        await update.message.reply_text("Opa, gostoso! Pra gente conversar melhor, me chama no privado clicando no botão aqui embaixo. 😉", reply_markup=reply_markup)
        return ConversationHandler.END

    user = update.effective_user
    try:
        user_name = f"{user.first_name} {user.last_name or ''}".strip()
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=f"▶️ **Novo /start Iniciado**\n\n👤 **Utilizador:** {user_name}\n🆔 **ID:** <code>{user.id}</code>", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Erro ao enviar log de /start: {e}")

    cancel_all_follow_ups(context, user.id)
    context.user_data['interaction_count'] = 0

    if context.args: return ConversationHandler.END

    start_greetings = ["Opa, senta aí... Tava te esperando. Pensei que não vinha mais. 😏", "Finalmente... Achei que tinha amarelado. Gosto de quem tem atitude. 🔥", "Chegou o gostoso que eu tava esperando. Demorou, hein? 😉"]
    phase2_greetings = ["Agora sim, só nós dois aqui no privado... Do jeito que eu gosto. 😈", "Adoro um segredinho... aqui a gente pode fazer o que quiser, sem ninguém pra encher o saco.", "Uhm... só eu e você. O que você quer fazer comigo primeiro? Me conta tudo. 😏"]
    phase3_greetings = ["Você não faz ideia do que eu e minhas amigas preparamos pra você... É putaria sem limites. 🔥", "Se prepara, porque o que eu vou te mostrar vai te deixar de pau duro a semana inteira.", "Tudo que você mais deseja tá aqui. Vou te dar só uma provinha do que te espera no paraíso... 💦"]
    phase4_greetings = ["Chega de papinho furado, né? Gosto de mostrar na prática do que sou capaz de fazer...", "Cansei de falar. Fazer é bem mais gostoso. Se prepara pra gozar muito.", "Acho que já te deixei esperando demais. Tá na hora de se divertir de verdade e bater uma..."]
    final_prompt = ["E aí, gostosão? Curtiu o que eu te mandei? Me fala o que você achou... quero detalhes. 😉", "Isso foi só pra te dar um gostinho... Me diz, te deixei com vontade de ver mais? 🔥", "E aí? O coração bateu mais forte? kkkk A rola já tá pulsando? Conta tudo, não me esconde nada. 😏"]

    await simulate_typing(context, user.id, 1.5, 2.5); await update.message.reply_text(random.choice(start_greetings))
    await simulate_typing(context, user.id, 2.0, 3.5); await context.bot.send_message(chat_id=user.id, text=random.choice(phase2_greetings))
    await simulate_typing(context, user.id, 2.0, 3.0); await context.bot.send_message(chat_id=user.id, text=random.choice(phase3_greetings))
    await simulate_typing(context, user.id, 2.5, 4.0); await context.bot.send_message(chat_id=user.id, text=random.choice(phase4_greetings))

    try:
        with sqlite3.connect(DB_PATH) as conn:
            media = conn.execute("SELECT file_id, file_type FROM welcome_media ORDER BY RANDOM() LIMIT 1").fetchone()
        if media:
            file_id, file_type = media
            action = ChatAction.UPLOAD_PHOTO if file_type == 'photo' else ChatAction.UPLOAD_VIDEO
            await context.bot.send_chat_action(chat_id=user.id, action=action)
            await asyncio.sleep(random.uniform(2.0, 3.0))
            if file_type == 'photo': await context.bot.send_photo(chat_id=user.id, photo=file_id)
            else: await context.bot.send_video(chat_id=user.id, video=file_id)
    except Exception as e:
        logger.error(f"Erro ao enviar mídia de boas-vindas: {e}", exc_info=True)

    await simulate_typing(context, user.id, 1.5, 2.5)
    await context.bot.send_message(chat_id=user.id, text=random.choice(final_prompt))
    
    try:
        chat = await context.bot.get_chat(TARGET_GROUP_ID)
        invite_link = chat.invite_link or (await context.bot.create_chat_invite_link(chat_id=TARGET_GROUP_ID)).invite_link
    except Exception as e:
        logger.error(f"Não foi possível obter/criar o link de convite para o grupo gratuito ({TARGET_GROUP_ID}): {e}")
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=f"🚨 ERRO CRÍTICO: Não consigo obter o link de convite para o grupo gratuito {TARGET_GROUP_ID}. O botão 'Prévias' não será exibido. Verifique as permissões do bot.")
        invite_link = None

    keyboard = [[InlineKeyboardButton(BUTTON_TEXTS["plan_button"].format(plan_name=p['name'], price=p['price']), callback_data=f"select_plan:{pid}")] for pid, p in PLANS.items()]
    if invite_link: keyboard.append([InlineKeyboardButton("🔥 Ver Prévias Grátis 🔥", url=invite_link)])
    
    final_text = "Chega de provinha, né? Tá na hora do show completo. 😈\n\nEscolha um dos nossos planos VIP e libere o acesso a **TODA A PUTARIA**, sem frescura e sem limites:"
    await context.bot.send_message(chat_id=user.id, text=final_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    context.job_queue.run_once(reengage_user, when=timedelta(minutes=REENGAGE_DELAY_MINUTES), chat_id=user.id, name=f"reengage_{user.id}")
    return ConversationHandler.END

async def handle_any_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    try:
        user_name = f"{user.first_name} {user.last_name or ''}".strip()
        log_text = (f"💬 **Utilizador Respondeu ao Bot**\n\n"
                    f"👤 **Utilizador:** {user_name} (<code>{user.id}</code>)\n"
                    f"📝 **Mensagem:** \"{update.message.text}\"")
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=log_text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Erro ao enviar log de resposta: {e}")

    cancel_all_follow_ups(context, user.id)

    await simulate_typing(context, user.id, 1.5, 2.5)
    await update.message.reply_text(random.choice(SEXY_COMPLIMENTS))
    await simulate_typing(context, user.id, 2.0, 3.5)
    
    final_text_options = [
        (f"Agora que você provou que tem pegada, {user.first_name}, tá na hora de subir o nível.\n\n"
         "No VIP o buraco é mais embaixo. Acesso a TUDO: meu conteúdo completo e o de várias vadias que eu chamei, sem cortes e sem limites.\n\n"
         "Tô te esperando lá dentro, gostoso. 😈👇"),
        (f"Adorei nosso papo, {user.first_name}. Mas conversar é só o aquecimento.\n\n"
         "Imagina ter acesso a todos os meus vídeos... e aos de dezenas de amigas minhas... Isso é o VIP. Putaria 24 horas.\n\n"
         "A porta do puteiro tá aberta, só falta você entrar. 🔥"),
    ]
    
    keyboard = [[InlineKeyboardButton(BUTTON_TEXTS["plan_button"].format(plan_name=p['name'], price=p['price']), callback_data=f"select_plan:{pid}")] for pid, p in PLANS.items()]
    await context.bot.send_message(chat_id=user.id, text=random.choice(final_text_options), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    context.job_queue.run_once(reengage_user, when=timedelta(minutes=REENGAGE_DELAY_MINUTES), chat_id=user.id, name=f"reengage_{user.id}")
    return ConversationHandler.END

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.type != 'private':
        bot_username = (await context.bot.get_me()).username
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["talk_private"], url=f"https.t.me/{bot_username}?start=status")]])
        await update.message.reply_text("Para consultar sua assinatura, me chama no privado clicando no botão abaixo.", reply_markup=reply_markup)
        return
        
    user_id = update.effective_user.id
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT expiry_date, status, plan_name, dias_ajustados FROM subscriptions WHERE user_id = ?", (user_id,)).fetchone()

    if result and result[1] == 'active':
        expiry_date_str, _, plan_name, dias_ajustados = result
        expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
        message = f"✅ Sua assinatura **{plan_name}** tá **ATIVA**, gostoso!\n\nPode gozar à vontade até o dia **{expiry_date}**. Aproveita. 😉"
        if dias_ajustados and dias_ajustados > 0: message += f"\n\n🎁 Você tem um bônus de <b>+{dias_ajustados}</b> dias."
        elif dias_ajustados and dias_ajustados < 0: message += f"\n\n⚠️ Sua assinatura teve um ajuste de <b>{dias_ajustados}</b> dias."
        await update.message.reply_html(message)
    else:
        await update.message.reply_html("❌ Ih, você ainda não tá no meu puteiro particular.\n\nUsa o /start pra gente conversar que eu te mostro como entrar no paraíso. 😏")

async def atrizes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.id == VIP_GROUP_ID:
        await show_actress_list(update, context, page=0)

async def previa_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.id == TARGET_GROUP_ID:
        await show_previa_catalog(update, context)
    
async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.id != TARGET_GROUP_ID: return
    bot_username = (await context.bot.get_me()).username
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["see_plans_and_become_vip"], url=f"https://t.me/{bot_username}?start=vip")]])
    try: await update.message.delete()
    except Exception as e: logger.warning(f"Não foi possível apagar o comando /vip: {e}")
    await context.bot.send_message(chat_id=update.effective_chat.id, text="👑 **CHEGA DE SÓ OLHAR. VIRE VIP AGORA!** 👑\n\nCansado de conteúdo limitado? No <b>Grupo VIP</b>, o acesso é **TOTAL** e o prazer é **GARANTIDO**. 😈💦\n\n<b>CLIQUE NO BOTÃO ABAIXO</b> para destravar o seu acesso e entrar no paraíso. 🔥", reply_markup=reply_markup, parse_mode='HTML')

async def lista_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.id != VIP_GROUP_ID: return
    if not CATALOGO_ATRIZES:
        await update.message.reply_text("O catálogo de atrizes ainda está vazio.")
        return

    actress_names = sorted([actress['name'] for actress in CATALOGO_ATRIZES])
    message_header = "📋 **Lista Completa de Atrizes** 📋\n\n"
    message_body = "\n".join([f"<code>{name}</code>" for name in actress_names])
    full_message = message_header + message_body
    if len(full_message) <= 4096:
        await update.message.reply_html(full_message)
    else:
        await update.message.reply_html(message_header)
        for chunk in [actress_names[i:i + 50] for i in range(0, len(actress_names), 50)]:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join([f"<code>{name}</code>" for name in chunk]), parse_mode='HTML')
    await update.message.delete()

async def buscar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.id != VIP_GROUP_ID: return
    if not context.args:
        await update.message.reply_html("<b>Uso:</b> <code>/buscar Nome da Atriz</code>")
        return
        
    search_term = " ".join(context.args).strip().lower()
    
    # Busca por correspondências parciais
    found_actresses = [
        (i, actress) for i, actress in enumerate(CATALOGO_ATRIZES) 
        if search_term in actress['name'].lower()
    ]
    
    if not found_actresses:
        await update.message.reply_html(f"😕 Nenhuma deusa encontrada com o nome '<b>{search_term}</b>'.\n\nConfira a ortografia ou use o comando /lista para ver todos os nomes.")
        return

    # Se encontrar exatamente uma, envia o portfólio
    if len(found_actresses) == 1:
        actress_index, _ = found_actresses[0]
        await update.message.delete()
        await send_actress_portfolio(context, update.effective_chat.id, actress_index)
        await log_engagement(context, update.effective_user, CATALOGO_ATRIZES[actress_index]['name'], 'search_direct_hit')

    # Se encontrar múltiplas, mostra uma lista para o usuário escolher
    else:
        keyboard = []
        text = "🔍 Encontrei várias deusas com esse nome. Qual delas você quer ver?\n\n"
        for actress_index, actress_data in found_actresses:
            keyboard.append([InlineKeyboardButton(actress_data['name'], callback_data=f"select_found_actress:{actress_index}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_html(text, reply_markup=reply_markup)

# --- Comandos de Admin ---
@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def anunciar_tudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inicia o processo de postar todos os portfólios de atrizes no grupo VIP."""
    keyboard = [[
        InlineKeyboardButton("✅ Sim, tenho certeza", callback_data="confirm_anunciar_tudo"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel_anunciar_tudo")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(
        f"🔥 <b>Atenção!</b> Esta ação vai postar o portfólio de TODAS as <b>{len(CATALOGO_ATRIZES)}</b> atrizes no grupo VIP.\n\n"
        "Isso pode levar muito tempo e não pode ser cancelado após o início. Deseja continuar?",
        reply_markup=reply_markup
    )

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID, LOG_GROUP_ID])
async def comandos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        message_text = (
            "📖 **Lista de Comandos de Administração** 📖\n\n"
            "--- **Comunicação e Gestão** ---\n"
            "<b>/falar</b> - Envia uma mensagem privada a um utilizador.\n"
            "<b>/info</b> <code>&lt;ID&gt;</code> ou respondendo - Vê a ficha completa de um utilizador.\n"
            "<b>/painel</b> - Mostra o painel de controlo interativo.\n"
            "<b>/remover</b> <code>&lt;ID&gt;</code> - Remove um utilizador do grupo VIP e da DB.\n"
            "<b>/ajustar_dias</b> <code>&lt;ID&gt; &lt;dias&gt;</code> - Adiciona/remove dias da assinatura.\n"
            "<b>/limpar_expirados</b> <code>&lt;dias&gt;</code> - Apaga da DB utilizadores expirados há mais de X dias.\n\n"
            "--- **Relatórios e Logs** ---\n"
            "<b>/stats</b> - Exibe estatísticas de faturação e assinantes.\n"
            "<b>/relatorio</b> - Relatório diário de interesse de compra.\n"
            "<b>/relatorio_engajamento</b> - Ranking de atrizes mais vistas.\n"
            "<b>/expirados</b> - Lista todos os utilizadores com assinaturas expiradas.\n"
            "<b>/verificar_jobs</b> - Mostra todas as tarefas agendadas.\n\n"
            "--- **Marketing e Conteúdo** ---\n"
            "<b>/anunciar</b> - Envia um anúncio para o grupo público.\n"
            "<b>/anunciaratriz</b> <code>[Nome]</code> - Posta o teaser de uma atriz.\n"
            "<b>/anunciartudo</b> - Posta o portfólio de TODAS as atrizes no grupo VIP.\n"
            "<b>/oferta</b> - Posta um link de acesso VIP temporário.\n"
            "<b>/desconto</b> <code>&lt;valor&gt; &lt;dias&gt;</code> - Envia uma oferta especial personalizada.\n"
            "<b>/setdesconto</b> <code>&lt;valor&gt;</code> - Altera o preço da oferta de carrinho abandonado.\n"
            "<b>/gerenciarfrases</b> - Adiciona/remove frases de marketing.\n"
            "<b>/mensagem</b> - Envia uma mensagem personalizada para o grupo gratuito.\n"
            "<b>/setatrizteaser</b> <code>&lt;Nome&gt;</code> - Define a atriz para teasers de conversa.\n"
            "<b>/setboasvindas</b> - Define as mídias enviadas no /start.\n\n"
            "--- **Gestão de Catálogo (Canal de Armazenamento)** ---\n"
            "<b>/addmedia</b> - Adiciona novas mídias a uma atriz.\n"
            "<b>/remover_atriz</b> <code>&lt;Nome&gt;</code> - Remove uma atriz e todas as suas mídias.\n"
            "<b>/sincronizar</b> - Recarrega o catálogo e limpa o cache.\n\n"
            "--- **Manutenção** ---\n"
            "<b>/backup</b> - Cria uma cópia de segurança da base de dados.\n"
            "<b>/migrarvip</b> <code>&lt;ID do novo grupo&gt;</code> - Re-convida todos os VIPs para um novo grupo.\n"
            "<b>/settutorial</b> - Define/altera o vídeo de tutorial."
        )
        await update.message.reply_html(message_text)
    except Exception as e:
        logger.error(f"Erro ao executar /comandos: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def set_teaser_actress_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_html("<b>Uso:</b> <code>/setatrizteaser Nome da Atriz</code>")
        return

    actress_name = " ".join(context.args)
    found_actress = next((actress for actress in CATALOGO_ATRIZES if actress['name'].lower() == actress_name.lower()), None)
            
    if not found_actress:
        await update.message.reply_html(f"❌ Atriz '<b>{actress_name}</b>' não encontrada no catálogo.")
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", ('conversation_teaser_actress', found_actress['name']))
        conn.commit()

    await update.message.reply_html(f"✅ Sucesso! A atriz <b>{found_actress['name']}</b> foi definida para os teasers de conversa.\n\nA enviar uma prévia para si...")
    try:
        await send_conversation_teaser(context, update.effective_chat.id, CATALOGO_ATRIZES.index(found_actress))
    except Exception:
        await update.message.reply_text("⚠️ Não foi possível enviar a prévia. Verifique se a atriz possui fotos cadastradas.")

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def contar_midia_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            results = conn.execute("""
                SELECT actress_name, SUM(CASE WHEN file_type = 'photo' THEN 1 ELSE 0 END), SUM(CASE WHEN file_type = 'video' THEN 1 ELSE 0 END)
                FROM media_catalog GROUP BY actress_name ORDER BY actress_name;
            """).fetchall()

        if not results:
            await update.message.reply_html("O catálogo de mídias está vazio.")
            return

        message_chunks = []
        current_chunk = "📊 **Contagem de Mídias por Atriz** 📊\n\n"
        for actress_name, photo_count, video_count in results:
            line = f"👱‍♀️ <b>{actress_name}</b>\n   - 📸 Fotos: {photo_count}\n   - 🎥 Vídeos: {video_count}\n   - 🗂️ Total: {photo_count + video_count}\n\n"
            if len(current_chunk) + len(line) > 4096:
                message_chunks.append(current_chunk)
                current_chunk = ""
            current_chunk += line
        if current_chunk: message_chunks.append(current_chunk)
        for chunk in message_chunks:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk, parse_mode='HTML')
            await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Erro ao executar /contarmidia: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[LOG_GROUP_ID])
async def expirados_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            expired_users = conn.execute("SELECT user_name, user_id, expiry_date FROM subscriptions WHERE status = 'expired' ORDER BY expiry_date DESC").fetchall()
        if not expired_users:
            message_text = "✅ Nenhum membro com assinatura expirada no momento."
        else:
            message_text = "📜 **Lista de Assinaturas Expiradas:**\n\n"
            for user_name, user_id, expiry_date_str in expired_users:
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
                message_text += f"👤 <b>{user_name or 'Nome não registado'}</b> (<code>{user_id}</code>)\n   - Expirou em: {expiry_date}\n\n"
        await update.message.reply_html(message_text)
    except Exception as e:
        logger.error(f"Erro ao executar /expirados: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def remover_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        try: user_id_to_remove = int(context.args[0])
        except (IndexError, ValueError):
            await update.message.reply_html("<b>Uso:</b> <code>/remover &lt;ID do utilizador&gt;</code>")
            return
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id_to_remove,))
            db_removed = cursor.rowcount > 0
            conn.commit()

        kick_status = "não foi tentada"
        try:
            await context.bot.ban_chat_member(chat_id=VIP_GROUP_ID, user_id=user_id_to_remove)
            await context.bot.unban_chat_member(chat_id=VIP_GROUP_ID, user_id=user_id_to_remove)
            kick_status = "com sucesso"
        except Exception as e:
            kick_status = f"falhou ({e})."
        
        feedback_message = (f" R E M O Ç Ã O   C O N C L U Í D A \n\n<b>ID do Utilizador:</b> <code>{user_id_to_remove}</code>\n"
                            f"✅ <b>Base de Dados:</b> {'Registo removido.' if db_removed else 'Utilizador não encontrado.'}\n"
                            f"🏃 <b>Grupo VIP:</b> A remoção {kick_status}")
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=feedback_message, parse_mode='HTML')
        await update.message.reply_text("Ação de remoção processada. Relatório enviado para o grupo de logs.")
    except Exception as e:
        logger.error(f"Erro ao executar /remover: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def anunciar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.reply_text("Ok, a enviar o anúncio para o grupo alvo...")
        await send_advertisement(context)
    except Exception as e:
        logger.error(f"Erro ao executar /anunciar: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[STORAGE_CHANNEL_ID], admin_check_chat_id=STORAGE_CHANNEL_ID)
async def remover_atriz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        try: actress_name_to_remove = " ".join(context.args)
        except IndexError:
            await update.message.reply_html("<b>Uso:</b> <code>/remover_atriz Nome da Atriz</code>")
            return
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM media_catalog WHERE actress_name = ?", (actress_name_to_remove,))
            rows_deleted = cursor.rowcount
            conn.commit()

        if rows_deleted > 0:
            await update.message.reply_text(f"✅ {rows_deleted} mídias de '{actress_name_to_remove}' foram removidas do catálogo com sucesso.")
            log_admin_action = (f"🗑️ **Conteúdo Removido**\n\n"
                                f"👤 **Admin:** {update.effective_user.first_name} (<code>{update.effective_user.id}</code>)\n"
                                f"👱‍♀️ **Atriz Removida:** {actress_name_to_remove}\n"
                                f"🔢 **Mídias Apagadas:** {rows_deleted}")
            await context.bot.send_message(chat_id=LOG_GROUP_ID, text=log_admin_action, parse_mode='HTML')
            build_catalog_from_db()
        else:
            await update.message.reply_text(f"Nenhuma atriz encontrada com o nome '{actress_name_to_remove}'.")
    except Exception as e:
        logger.error(f"Erro ao executar /remover_atriz: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[STORAGE_CHANNEL_ID], admin_check_chat_id=STORAGE_CHANNEL_ID)
async def sincronizar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.reply_text("🔄 A sincronizar o catálogo e a limpar o cache...")
        PORTFOLIO_CACHE.clear()
        save_portfolio_cache() # Guarda o cache vazio na base de dados
        build_catalog_from_db()
        load_dynamic_configs()
        await update.message.reply_html(f"✅ Sincronização concluída!\n\n"
                                        f"📚 <b>{len(CATALOGO_ATRIZES)}</b> atrizes carregadas.\n"
                                        f"💬 Frases de marketing recarregadas.\n"
                                        f"🗑️ Cache de portfólios foi limpo.")
        log_admin_action = (f"🔄 **Sincronização Manual**\n\n"
                            f"👤 **Admin:** {update.effective_user.first_name} (<code>{update.effective_user.id}</code>)")
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=log_admin_action, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Erro ao executar /sincronizar: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[LOG_GROUP_ID, ADMIN_GROUP_ID])
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            now = datetime.now(pytz.timezone(TIMEZONE))
            current_month_str, current_year_str = now.strftime('%Y-%m'), now.strftime('%Y')

            monthly_revenue = cursor.execute("SELECT SUM(price_paid) FROM subscriptions WHERE start_date LIKE ?", (f"{current_month_str}%",)).fetchone()[0] or 0
            yearly_revenue = cursor.execute("SELECT SUM(price_paid) FROM subscriptions WHERE start_date LIKE ?", (f"{current_year_str}%",)).fetchone()[0] or 0
            active_count, inactive_count = cursor.execute("SELECT (SELECT COUNT(*) FROM subscriptions WHERE status = 'active'), (SELECT COUNT(*) FROM subscriptions WHERE status = 'expired')").fetchone()
            new_this_month_count = cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE start_date LIKE ?", (f"{current_month_str}%",)).fetchone()[0]
            new_this_year_count = cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE start_date LIKE ?", (f"{current_year_str}%",)).fetchone()[0]
            offers_30_sent_year = cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE discount_offer_sent >= 1 AND expiry_date LIKE ?", (f"{current_year_str}%",)).fetchone()[0]
            converted_30_year = cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE renewal_source = '30%_offer' AND start_date LIKE ?", (f"{current_year_str}%",)).fetchone()[0]
            offers_50_sent_year = cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE discount_offer_sent >= 2 AND expiry_date LIKE ?", (f"{current_year_str}%",)).fetchone()[0]
            converted_50_year = cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE renewal_source = '50%_offer' AND start_date LIKE ?", (f"{current_year_str}%",)).fetchone()[0]

        conversion_rate_30 = (converted_30_year / offers_30_sent_year * 100) if offers_30_sent_year > 0 else 0
        conversion_rate_50 = (converted_50_year / offers_50_sent_year * 100) if offers_50_sent_year > 0 else 0
        message_text = (
            f"📊 <b>Estatísticas Gerais ({current_year_str})</b> 📊\n\n"
            f"💰 <b>Faturação</b>\n   - Este Mês: R$ {monthly_revenue:.2f}\n   - Este Ano: R$ {yearly_revenue:.2f}\n\n"
            f"👥 <b>Assinantes</b>\n   - Ativos: {active_count}\n   - Inativos: {inactive_count}\n"
            f"   - Novos no Mês: {new_this_month_count}\n   - Novos no Ano: {new_this_year_count}\n\n"
            f"🔄 <b>Recuperação (Anual)</b>\n"
            f"   - <u>Oferta 30% OFF:</u> {converted_30_year}/{offers_30_sent_year} ({conversion_rate_30:.2f}%)\n"
            f"   - <u>Oferta 50% OFF:</u> {converted_50_year}/{offers_50_sent_year} ({conversion_rate_50:.2f}%)"
        )
        if update.message: await update.message.reply_html(message_text)
        elif update.callback_query: await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Erro ao executar /stats: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def anunciar_atriz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        eligible_actresses = [actress for actress in CATALOGO_ATRIZES if any(m['type'] == 'photo' for m in actress['media_files']) and any(m['type'] == 'video' and m['duration'] <= 30 for m in actress['media_files'])]
        if not context.args:
            selected_actress = random.choice(eligible_actresses) if eligible_actresses else None
        else:
            search_name = " ".join(context.args).strip().lower()
            selected_actress = next((actress for actress in CATALOGO_ATRIZES if actress['name'].lower() == search_name), None)
        
        if not selected_actress:
            await update.message.reply_html("⚠️ Nenhuma atriz encontrada ou elegível para anúncio.")
            return
        
        await update.message.reply_text(f"Ok, a preparar o anúncio da atriz '{selected_actress['name']}'...")
        success = await _post_actress_teaser(context, selected_actress)
        if success: await update.message.reply_text("✅ Anúncio manual enviado com sucesso!")
        else: await update.message.reply_html(f"⚠️ Não foi possível postar o teaser. A atriz '<b>{selected_actress['name']}</b>' precisa de ter pelo menos <b>uma foto E um vídeo de até 30 segundos</b>.")
    except Exception as e:
        logger.error(f"Erro ao executar /anunciaratriz: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def anunciar_migracao_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        try: new_free_group_id = int(context.args[0])
        except (IndexError, ValueError):
            await update.message.reply_html("<b>Uso:</b> <code>/anunciarmigracao &lt;ID do NOVO grupo gratuito&gt;</code>")
            return
        
        await update.message.reply_text(f"Ok, vou postar o anúncio de migração no grupo gratuito atual ({TARGET_GROUP_ID})...")
        try:
            chat = await context.bot.get_chat(new_free_group_id)
            invite_link = chat.invite_link or (await context.bot.create_chat_invite_link(chat_id=new_free_group_id)).invite_link
        except Exception as e:
            await update.message.reply_html(f"⚠️ <b>Erro ao obter link do novo grupo!</b>\n\nVerifique o ID e se o bot é admin no novo grupo.\n\nErro: {e}")
            return

        message_text = (
            "‼️ **AVISO IMPORTANTE - ESTAMOS DE CASA NOVA!** ‼️\n\n"
            "Para continuar a receber as melhores prévias, estamos a mudar-nos para um novo grupo!\n\n"
            "Este grupo será desativado em breve. Clique no link abaixo para entrar no nosso novo espaço.\n\n"
            f"➡️ **ENTRE NO NOVO GRUPO AQUI:** {invite_link}\n"
            "Esperamos por si lá! 🔥")
        await context.bot.send_message(chat_id=TARGET_GROUP_ID, text=message_text)
        await update.message.reply_html("✅ Anúncio de migração postado com sucesso.\n\n🚨 **LEMBRE-SE:** Atualize a variável `TARGET_GROUP_ID` no código e reinicie o bot.")
    except Exception as e:
        logger.error(f"Erro ao executar /anunciarmigracao: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def migrar_vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        try: new_vip_group_id = int(context.args[0])
        except (IndexError, ValueError):
            await update.message.reply_html("<b>Uso:</b> <code>/migrarvip &lt;ID do NOVO grupo VIP&gt;</code>")
            return

        await update.message.reply_text(f"🚀 **A iniciar migração para o grupo {new_vip_group_id}...**\nIsto pode levar alguns minutos.", parse_mode='HTML')
        with sqlite3.connect(DB_PATH) as conn:
            active_users = conn.execute("SELECT user_id, user_name FROM subscriptions WHERE status = 'active'").fetchall()
        if not active_users:
            await update.message.reply_text("Nenhum assinante ativo encontrado para migrar.")
            return

        success_count, fail_count = 0, 0
        failed_users_details = []
        message_to_user = "Olá! 👋\n\nEstamos de casa nova! Para garantir a melhor experiência, o nosso grupo VIP foi movido.\nUse o seu novo link de convite pessoal e exclusivo abaixo:\n\n➡️ {invite_link}"
        for user_id, user_name in active_users:
            try:
                invite_link = (await context.bot.create_chat_invite_link(chat_id=new_vip_group_id, member_limit=1, name=f"Migração {user_name}")).invite_link
                await context.bot.send_message(chat_id=user_id, text=message_to_user.format(invite_link=invite_link))
                success_count += 1
            except Exception as e:
                fail_count += 1
                failed_users_details.append(f"👤 {user_name} (<code>{user_id}</code>) - Erro: {e}")
            await asyncio.sleep(1)

        report_message = (f"🏁 **Migração Concluída** 🏁\n\n"
                          f"✅ <b>{success_count} membros</b> convidados com sucesso.\n"
                          f"❌ <b>{fail_count} membros</b> falharam ao receber o convite.\n\n")
        if failed_users_details: report_message += "<b>Detalhes das Falhas:</b>\n" + "\n".join(failed_users_details)
        report_message += (f"\n\n🚨 **AÇÃO IMPORTANTE:**\n1. Atualize a variável `VIP_GROUP_ID` no script para `{new_vip_group_id}`\n2. **REINICIE O BOT**.")
        await update.message.reply_html(report_message)
    except Exception as e:
        logger.error(f"Erro crítico durante a execução do /migrarvip: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[LOG_GROUP_ID])
async def relatorio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        today_start = datetime.now(pytz.timezone(TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)
        with sqlite3.connect(DB_PATH) as conn:
            results = conn.execute("SELECT plan_name, log_type, COUNT(*) FROM click_logs WHERE timestamp >= ? GROUP BY plan_name, log_type", (today_start.isoformat(),)).fetchall()

        if not results:
            await update.message.reply_text("📈 Nenhum interesse de compra registado nas últimas 24 horas.")
            return

        report_text = f"📈 **Relatório de Interesse de Compra - {today_start.strftime('%d/%m/%Y')}** 📈\n\n"
        plan_clicks = {}
        for plan_name, log_type, count in results:
            plan_clicks.setdefault(plan_name, {})[log_type] = count
        for plan, clicks in plan_clicks.items():
            total = sum(clicks.values())
            report_text += f"🔹 <b>Plano {plan}:</b>\n"
            for log_type, count in clicks.items():
                report_text += f"   - {log_type}: {count} cliques\n"
            report_text += f"   - <b>Total: {total} cliques</b>\n\n"
        await update.message.reply_html(report_text)
    except Exception as e:
        logger.error(f"Erro ao gerar relatório: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[LOG_GROUP_ID, ADMIN_GROUP_ID])
async def relatorio_engajamento_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Busca os 20 mais vistos
            results = conn.execute("""
                SELECT actress_name, COUNT(*) as view_count 
                FROM click_logs 
                WHERE log_type IN ('portfolio_view', 'teaser_view', 'search_direct_hit', 'search_selection') AND actress_name IS NOT NULL
                GROUP BY actress_name 
                ORDER BY view_count DESC
                LIMIT 20
            """).fetchall()

        if not results:
            await update.message.reply_html("📈 Nenhum dado de engajamento de atrizes foi registrado ainda.")
            return

        report_text = "🏆 **Top 20 Atrizes Mais Vistas** 🏆\n\n"
        rank_emojis = ["🥇", "🥈", "🥉"]
        for i, (actress_name, count) in enumerate(results):
            rank = rank_emojis[i] if i < 3 else f"<b>{i+1}.</b>"
            report_text += f"{rank} {actress_name} - <b>{count}</b> visualizações\n"
            
        await update.message.reply_html(report_text)
    except Exception as e:
        logger.error(f"Erro ao gerar relatório de engajamento: {e}", exc_info=True)
        await update.message.reply_html("Ocorreu um erro ao gerar o relatório.")


@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def postar_tutorial_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            result = conn.execute("SELECT value FROM system_settings WHERE key = ?", ('tutorial_video_id',)).fetchone()
        
        if not result or not result[0]:
            await update.message.reply_html("⚠️ <b>Ação Falhou!</b>\n\nNenhum vídeo tutorial foi configurado. Use <code>/settutorial</code> primeiro.")
            return

        await update.message.reply_text("Ok, a enviar o vídeo tutorial para os grupos VIP e Gratuito...")
        await send_tutorial_video(context)
        await update.message.reply_text("✅ Vídeos enviados com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao executar /postartutorial: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def desconto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if len(context.args) != 2: raise ValueError
        price = f"{float(context.args[0]):.2f}"
        days = int(context.args[1])
        if float(price) <= 0 or days <= 0: raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_html("<b>Uso:</b> <code>/desconto &lt;valor&gt; &lt;dias&gt;</code>\n<b>Exemplo:</b> <code>/desconto 9.99 15</code>")
        return

    await update.message.reply_text(f"Ok, a enviar a oferta especial de R${price} por {days} dias para o grupo gratuito...")
    try:
        bot_username = (await context.bot.get_me()).username
        url_oferta = f"https://t.me/{bot_username}?start=oferta_{price}_{days}"
        texto_oferta = (
            "🤫🔥 **OFERTA SECRETA LIBERADA!** 🔥🤫\n**SÓ PARA QUEM ESTÁ ONLINE AGORA!**\n\n"
            f"🚨 **PREÇO ESPECIAL E ÚNICO: R$ {price} por {days} dias!** 🚨\n\n"
            "Este link é uma oportunidade única e pode expirar a qualquer momento.\n\n"
            "👇🏼😈 **CLIQUE ABAIXO E GARANTA O SEU ACESSO ANTES QUE ALGUÉM PEGUE O SEU LUGAR!** 👇🏼")
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"🔥 QUERO ACESSO VIP POR R${price} AGORA! 🔥", url=url_oferta)]])
        await context.bot.send_message(chat_id=TARGET_GROUP_ID, text=texto_oferta, parse_mode='HTML', reply_markup=reply_markup)
        await update.message.reply_text("✅ Oferta especial enviada com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao enviar a oferta de desconto: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID, LOG_GROUP_ID])
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target_user_id = None
    if update.message.reply_to_message: target_user_id = update.message.reply_to_message.from_user.id
    elif context.args and context.args[0].isdigit(): target_user_id = int(context.args[0])

    if not target_user_id:
        await update.message.reply_html("<b>Uso:</b> Responda a uma mensagem com <code>/info</code> ou use <code>/info &lt;ID&gt;</code>.")
        return

    try:
        await _send_user_info_card(context, update.effective_chat.id, target_user_id)
    except Exception as e:
        logger.error(f"Erro ao executar /info para ID {target_user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"Não foi possível encontrar o utilizador com o ID {target_user_id}.")

async def _send_user_info_card(context: ContextTypes.DEFAULT_TYPE, chat_id: int, target_user_id: int):
    """Envia a ficha de informação de um utilizador."""
    target_user = await context.bot.get_chat(target_user_id)
    user_name = f"{target_user.first_name} {target_user.last_name or ''}".strip()
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT plan_name, expiry_date, status FROM subscriptions WHERE user_id = ?", (target_user_id,)).fetchone()

    message = f"🔍 **Ficha do Utilizador**\n\n👤 **Nome:** {user_name}\n🆔 **ID:** <code>{target_user_id}</code>\n\n"
    if result:
        plan_name, expiry_date_str, status = result
        expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
        status_icon, status_text = ("✅", "ATIVO") if status == 'active' else ("❌", "EXPIRADO")
        message += f"**Estado:** {status_icon} **{status_text}**\n**Plano:** {plan_name}\n**Expira em:** {expiry_date}\n"
    else:
        message += "**Estado:** 🤷‍♂️ **Sem assinatura**\n"

    keyboard = [
        [InlineKeyboardButton("💬 Falar com Utilizador", callback_data=f"falar_com_user:{target_user_id}")],
        [InlineKeyboardButton("➕ Adicionar Dias", callback_data=f"info_adjust_days_start:{target_user_id}"), InlineKeyboardButton("🗑️ Remover do VIP", callback_data=f"info_remove_user_start:{target_user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML', reply_markup=reply_markup)


@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def ajustar_dias_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id_to_adjust = int(context.args[0])
        days_to_add = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_html("<b>Uso:</b> <code>/ajustar_dias &lt;ID&gt; &lt;dias&gt;</code> (ex: 7 ou -3)")
        return

    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT user_name, expiry_date, dias_ajustados FROM subscriptions WHERE user_id = ?", (user_id_to_adjust,)).fetchone()
        if not result:
            await update.message.reply_text(f"❌ Utilizador com ID {user_id_to_adjust} não encontrado.")
            return

        user_name, expiry_date_str, current_adjustment = result
        old_expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        new_expiry_date = old_expiry_date + timedelta(days=days_to_add)
        new_adjustment_total = (current_adjustment or 0) + days_to_add
        conn.execute("UPDATE subscriptions SET expiry_date = ?, dias_ajustados = ? WHERE user_id = ?", (new_expiry_date.strftime('%Y-%m-%d'), new_adjustment_total, user_id_to_adjust))
        conn.commit()

    action_text = f"adicionados {days_to_add}" if days_to_add > 0 else f"removidos {abs(days_to_add)}"
    admin_feedback = (f"✅ **Assinatura Ajustada!**\n\n"
                      f"👤 <b>Cliente:</b> {user_name or 'N/A'} (<code>{user_id_to_adjust}</code>)\n"
                      f"🗓️ <b>Dias:</b> {action_text} dias.\n"
                      f"📅 <b>Expiração Antiga:</b> {old_expiry_date.strftime('%d/%m/%Y')}\n"
                      f"✨ <b>Nova Expiração:</b> {new_expiry_date.strftime('%d/%m/%Y')}")
    await update.message.reply_html(admin_feedback)

    log_admin_action = (f"ℹ️ **Ajuste de Assinatura**\n\n"
                        f"👤 **Admin:** {update.effective_user.first_name} (<code>{update.effective_user.id}</code>)\n"
                        f"👨‍💻 **Cliente:** {user_name or 'N/A'} (<code>{user_id_to_adjust}</code>)\n"
                        f"🗓️ **Ação:** {action_text} dias.")
    await context.bot.send_message(chat_id=LOG_GROUP_ID, text=log_admin_action, parse_mode='HTML')

    try:
        user_notification = (f"ℹ️ **A sua assinatura foi ajustada!**\n\n"
                             f"Foram {action_text} dias.\n"
                             f"A sua nova data de validade é <b>{new_expiry_date.strftime('%d/%m/%Y')}</b>.")
        await context.bot.send_message(chat_id=user_id_to_adjust, text=user_notification, parse_mode='HTML')
    except Forbidden:
        await update.message.reply_html(f"{admin_feedback}\n\n⚠️ Não foi possível notificar o utilizador (bot bloqueado).")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    chat_id = update.effective_chat.id
    if chat_id not in [VIP_GROUP_ID, TARGET_GROUP_ID, ADMIN_GROUP_ID]: return
    try:
        chat_admins = await context.bot.get_chat_administrators(chat_id)
        if user.id not in {admin.user.id for admin in chat_admins}: return
    except Exception as e: logger.error(f"Erro ao verificar admins para /ban: {e}"); return

    if not update.message.reply_to_message:
        await update.message.reply_text("Para banir, responda à mensagem do utilizador com /ban.")
        return

    try:
        user_to_ban_id = update.message.reply_to_message.from_user.id
        await context.bot.ban_chat_member(chat_id, user_to_ban_id)
        await update.message.reply_text(f"✅ Utilizador banido com sucesso!")
    except Exception as e:
        await update.message.reply_text(f"Ocorreu um erro ao tentar banir: {e}")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    chat_id = update.effective_chat.id
    if chat_id not in [VIP_GROUP_ID, TARGET_GROUP_ID, ADMIN_GROUP_ID]: return
    try:
        chat_admins = await context.bot.get_chat_administrators(chat_id)
        if user.id not in {admin.user.id for admin in chat_admins}: return
    except Exception as e: logger.error(f"Erro ao verificar admins para /unban: {e}"); return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Uso: /unban <ID do utilizador>")
        return

    try:
        await context.bot.unban_chat_member(chat_id, int(context.args[0]))
        await update.message.reply_text(f"✅ Utilizador desbanido com sucesso!")
    except Exception as e:
        await update.message.reply_text(f"Ocorreu um erro ao tentar desbanir: {e}")

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID, LOG_GROUP_ID])
async def painel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        now = datetime.now(pytz.timezone(TIMEZONE))
        active_count = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'").fetchone()[0]
        monthly_revenue = conn.execute("SELECT SUM(price_paid) FROM subscriptions WHERE start_date LIKE ?", (f"{now.strftime('%Y-%m')}%",)).fetchone()[0] or 0.0
        daily_sales = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE start_date = ?", (now.strftime('%Y-%m-%d'),)).fetchone()[0]

    text = (f"📊 **PAINEL DE CONTROLO** 📊\n<i>Atualizado em: {now.strftime('%d/%m/%Y %H:%M:%S')}</i>\n\n"
            f"**Membros Ativos:** <code>{active_count}</code>\n"
            f"**Receita do Mês:** <code>R$ {monthly_revenue:.2f}</code>\n"
            f"**Vendas Hoje:** <code>{daily_sales}</code>\n\nSelecione um atalho:")
    keyboard = [
        [InlineKeyboardButton("🔃 Atualizar Painel", callback_data="refresh_panel")],
        [
            InlineKeyboardButton("📢 Anunciar", callback_data="painel_anunciar"),
            InlineKeyboardButton("✨ Anunciar Atriz", callback_data="painel_anunciar_atriz")
        ],
        [
            InlineKeyboardButton("⚡ Oferta Relâmpago", callback_data="painel_oferta"),
            InlineKeyboardButton("📊 Estatísticas", callback_data="painel_stats")
        ],
        [
            InlineKeyboardButton("🔎 Buscar Utilizador", callback_data="painel_buscar_start"),
            InlineKeyboardButton("💬 Falar com Utilizador", callback_data="falar_com_user:start")
        ],
        [
            InlineKeyboardButton("✍️ Nova Mensagem", callback_data="painel_mensagem"),
            InlineKeyboardButton("💾 Backup", callback_data="painel_backup")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
            await query.answer("Painel atualizado!")
        except BadRequest as e:
            if "Message is not modified" in str(e): await query.answer("Nada mudou ainda.")
            else: raise e
    else:
        await update.message.reply_html(text, reply_markup=reply_markup)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def lightning_offer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        vip_ok, vip_msg = await check_admin_permissions(context, VIP_GROUP_ID, ['can_invite_users'])
        if not vip_ok: await update.message.reply_html(f"⚠️ <b>Ação Falhou!</b>\n\n{vip_msg}"); return
        
        await update.message.reply_text("Ok, a gerar e a postar a oferta de acesso único...")
        invite_link_obj = await context.bot.create_chat_invite_link(chat_id=VIP_GROUP_ID, member_limit=1, name=f"Oferta Relampago {uuid.uuid4()}")
        message_text = (f"⚡️😈 **OFERTA RELÂMPAGO!** 😈⚡️\n\n"
                        f"O mais rápido a clicar ganha <b>{OFFER_DURATION_MINUTES} MINUTOS</b> de acesso **GRÁTIS** ao VIP! 🔥\n\n"
                        f"Corra, o link é de **USO ÚNICO**!\n\n➡️ {invite_link_obj.invite_link}")
        sent_message = await context.bot.send_message(chat_id=TARGET_GROUP_ID, text=message_text, parse_mode='HTML')
        context.bot_data[invite_link_obj.invite_link] = {'message_id': sent_message.message_id, 'chat_id': sent_message.chat_id}
    except Exception as e:
        logger.error(f"Erro ao executar /oferta: {e}", exc_info=True)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID, LOG_GROUP_ID])
async def verificar_jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = context.job_queue.jobs()
    if not jobs:
        await update.message.reply_text("✅ Nenhum job agendado no momento.")
        return

    message = "🗓️ **Lista de Jobs Agendados:**\n\n"
    for job in jobs:
        next_run_time = job.next_t.strftime('%d/%m/%Y %H:%M:%S') if job.next_t else "N/A"
        message += f"🔹 <b>Job:</b> <code>{job.name}</code>\n"
        if 'remove_temp' in job.name:
            message += f"   - <b>Ação:</b> Remover utilizador <code>{job.data.get('user_id', 'N/A')}</code>\n"
        message += f"   - <b>Próxima Execução:</b> {next_run_time}\n\n"
    await update.message.reply_html(message)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def limpar_expirados_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Apaga da base de dados os registos de utilizadores expirados há mais de X dias."""
    try:
        days = int(context.args[0])
        if days < 0:
            await update.message.reply_html("O número de dias deve ser positivo.")
            return
    except (IndexError, ValueError):
        await update.message.reply_html("<b>Uso:</b> <code>/limpar_expirados &lt;dias&gt;</code>\nExemplo: <code>/limpar_expirados 30</code> para apagar registos com mais de 30 dias de expiração.")
        return

    limit_date = datetime.now(pytz.timezone(TIMEZONE)) - timedelta(days=days)
    limit_date_str = limit_date.strftime('%Y-%m-%d')

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscriptions WHERE status = 'expired' AND expiry_date < ?", (limit_date_str,))
        rows_deleted = cursor.rowcount
        conn.commit()

    await update.message.reply_html(f"🧹 **Limpeza Concluída**\n\nForam removidos <b>{rows_deleted}</b> registos de utilizadores expirados antes de {limit_date.strftime('%d/%m/%Y')}.")

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def set_desconto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Define o preço da oferta para utilizadores que abandonam a compra."""
    try:
        new_price = f"{float(context.args[0]):.2f}"
    except (IndexError, ValueError):
        await update.message.reply_html("<b>Uso:</b> <code>/setdesconto &lt;valor&gt;</code>\n<b>Exemplo:</b> <code>/setdesconto 12.99</code>")
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", ('abandoned_cart_price', new_price))
        conn.commit()

    global DEFAULT_DISCOUNT_PRICE_ABANDONED
    DEFAULT_DISCOUNT_PRICE_ABANDONED = new_price
    await update.message.reply_html(f"✅ O novo preço para a oferta de carrinho abandonado foi definido para <b>R$ {new_price}</b>.")


# --- Handlers de Conversa Faltantes ---

# /falar
@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID, LOG_GROUP_ID])
async def falar_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Qual o ID do utilizador para quem quer enviar uma mensagem?")
    return AWAIT_TARGET_ID

async def falar_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        target_id = int(update.message.text)
        context.user_data['target_user_id'] = target_id
        await update.message.reply_html(f"Ok, a enviar mensagem para o ID <code>{target_id}</code>. Escreva abaixo o que quer enviar.")
        return AWAIT_MESSAGE_TO_SEND
    except ValueError:
        await update.message.reply_text("ID inválido. Por favor, envie um número.")
        return AWAIT_TARGET_ID

async def falar_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target_id = context.user_data.pop('target_user_id', None)
    if not target_id:
        await update.message.reply_text("Ocorreu um erro, ID de destino não encontrado. A começar de novo.")
        return ConversationHandler.END
    try:
        await context.bot.send_message(chat_id=target_id, text=f"ℹ️ **Mensagem da Administração:**\n\n{update.message.text}")
        await update.message.reply_text("✅ Mensagem enviada com sucesso!")
    except Exception as e:
        await update.message.reply_text(f"❌ Não foi possível enviar a mensagem. Erro: {e}")
    return ConversationHandler.END

# Busca de utilizador pelo painel
async def painel_buscar_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Ok, qual o ID do utilizador que quer procurar?")
    return AWAIT_USER_ID_TO_SEARCH

async def painel_receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = int(update.message.text)
        await _send_user_info_card(context, update.effective_chat.id, user_id)
    except ValueError:
        await update.message.reply_text("Isso não parece ser um ID válido. Tente novamente.")
    except Exception as e:
        await update.message.reply_text(f"Não foi possível encontrar informações para o ID {update.message.text}. Erro: {e}")
    return ConversationHandler.END

# Gerenciar Frases
@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def gerenciar_frases_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("💬 Anúncios", callback_data="phrase_cat_ad_message_texts")],
        [InlineKeyboardButton("🔥 Follow-ups", callback_data="phrase_cat_sexy_follow_ups")],
        [InlineKeyboardButton("😏 Elogios", callback_data="phrase_cat_sexy_compliments")],
        [InlineKeyboardButton("⬅️ Sair", callback_data="phrase_cat_exit")]
    ]
    await update.message.reply_html("💬 **Gerenciador de Frases** 💬\n\nSelecione a categoria que deseja gerenciar:", reply_markup=InlineKeyboardMarkup(keyboard))
    return MANAGE_PHRASES_MENU

async def gerenciar_frases_start_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("💬 Anúncios", callback_data="phrase_cat_ad_message_texts")],
        [InlineKeyboardButton("🔥 Follow-ups", callback_data="phrase_cat_sexy_follow_ups")],
        [InlineKeyboardButton("😏 Elogios", callback_data="phrase_cat_sexy_compliments")],
        [InlineKeyboardButton("⬅️ Sair", callback_data="phrase_cat_exit")]
    ]
    await query.edit_message_text("💬 **Gerenciador de Frases** 💬\n\nSelecione a categoria que deseja gerenciar:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return MANAGE_PHRASES_MENU


async def gerenciar_frases_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "phrase_cat_exit":
        await query.edit_message_text("Operação cancelada.")
        return ConversationHandler.END

    if action.startswith("phrase_act_"):
        if action == "phrase_act_add":
            category_name = context.user_data.get('phrase_category', {}).get('name', 'selecionada')
            await query.message.reply_text(f"Ok, envie a nova frase para a categoria **{category_name}**.", parse_mode='Markdown')
            return AWAIT_PHRASE_TO_ADD
        # Placeholder for other actions like remove
        await query.answer("Função ainda não implementada.", show_alert=True)
        return MANAGE_PHRASES_MENU


    category_key = action.replace("phrase_cat_", "")
    category_map = {
        "ad_message_texts": "Anúncios",
        "sexy_follow_ups": "Follow-ups",
        "sexy_compliments": "Elogios",
    }
    category_name = category_map.get(category_key, "Desconhecida")
    context.user_data['phrase_category'] = {'key': category_key, 'name': category_name}

    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT value FROM system_settings WHERE key = ?", (category_key,)).fetchone()
    
    phrases = json.loads(result[0]) if result and result[0] else []
    
    text = f"**Categoria: {category_name}**\n\n"
    if not phrases:
        text += "Nenhuma frase cadastrada.\n\n"
    else:
        for i, phrase in enumerate(phrases):
            text += f"{i+1}. `{phrase}`\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Adicionar Nova", callback_data=f"phrase_act_add")],
        [InlineKeyboardButton("🗑️ Remover (em breve)", callback_data=f"phrase_act_remove_disabled")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="back_to_phrase_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    return MANAGE_PHRASES_MENU


async def receive_phrase_to_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_phrase = update.message.text
    category_key = context.user_data.get('phrase_category', {}).get('key')

    if not category_key:
        await update.message.reply_text("Erro: Categoria não selecionada. A cancelar.")
        context.user_data.clear()
        return ConversationHandler.END

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = ?", (category_key,))
        result = cursor.fetchone()
        
        phrases = json.loads(result[0]) if result and result[0] else []
        phrases.append(new_phrase)
        
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", (category_key, json.dumps(phrases)))
        conn.commit()

    await update.message.reply_text(f"✅ Frase adicionada com sucesso à categoria **{context.user_data['phrase_category']['name']}**!")
    load_dynamic_configs()
    
    context.user_data.clear()
    await gerenciar_frases_start(update, context)
    return MANAGE_PHRASES_MENU

# --- Construtor de Mensagem ---
@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def mensagem_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("✍️ **Construtor de Mensagem**\n\n**Passo 1/3:** Envie o conteúdo (texto ou imagem com legenda).\n\n/cancelar para sair.")
    return AWAIT_CONTENT

async def mensagem_start_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if query.message.chat_id != ADMIN_GROUP_ID: return ConversationHandler.END
    try:
        chat_admins = await context.bot.get_chat_administrators(ADMIN_GROUP_ID)
        if user.id not in {admin.user.id for admin in chat_admins}: return ConversationHandler.END
    except Exception: return ConversationHandler.END
    await query.message.reply_text("✍️ **Construtor de Mensagem**\n\n**Passo 1/3:** Envie o conteúdo (texto ou imagem com legenda).\n\n/cancelar para sair.")
    return AWAIT_CONTENT

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['message_to_send'] = {'text': None, 'photo': None, 'button_text': None, 'button_url': None}
    if update.message.photo:
        context.user_data['message_to_send']['photo'] = update.message.photo[-1].file_id
        context.user_data['message_to_send']['text'] = update.message.caption
    elif update.message.text:
        context.user_data['message_to_send']['text'] = update.message.text
    else:
        await update.message.reply_text("Formato não suportado. Envie foto com legenda ou texto.")
        return AWAIT_CONTENT
    await update.message.reply_text("**Passo 2/3:** Quer adicionar um botão com link?\n\nEnvie no formato: `Texto do Botão, https://seu-link.com`\nOu digite `não`.")
    return AWAIT_BUTTON

async def receive_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.lower()
    if text not in ['nao', 'não', 'n', 'no']:
        try:
            button_text, button_url = [x.strip() for x in update.message.text.split(',', 1)]
            if not button_url.startswith(('http://', 'https://')): raise ValueError
            context.user_data['message_to_send']['button_text'] = button_text
            context.user_data['message_to_send']['button_url'] = button_url
        except ValueError:
            await update.message.reply_text("Formato inválido. Use: `Texto do Botão, https://link.com` ou digite `não`.")
            return AWAIT_BUTTON

    await update.message.reply_text("**Passo 3/3:** A sua mensagem ficará assim. Enviar para o grupo gratuito?")
    msg_data = context.user_data['message_to_send']
    reply_markup = None
    if msg_data['button_text'] and msg_data['button_url']:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(msg_data['button_text'], url=msg_data['button_url'])]])

    if msg_data['photo']:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=msg_data['photo'], caption=msg_data['text'], parse_mode='HTML', reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_data['text'], parse_mode='HTML', reply_markup=reply_markup)
    
    confirm_keyboard = [[InlineKeyboardButton("✅ Sim, Enviar", callback_data="send_custom_message_confirm"), InlineKeyboardButton("❌ Cancelar", callback_data="send_custom_message_cancel")]]
    await update.message.reply_text("Confirmar o envio?", reply_markup=InlineKeyboardMarkup(confirm_keyboard))
    return AWAIT_CONFIRMATION

async def receive_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "send_custom_message_confirm":
        msg_data = context.user_data.get('message_to_send')
        if not msg_data:
            await query.edit_message_text("❌ Erro: Dados da mensagem não encontrados.")
            return ConversationHandler.END
        try:
            reply_markup = None
            if msg_data['button_text'] and msg_data['button_url']:
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(msg_data['button_text'], url=msg_data['button_url'])]])
            if msg_data['photo']:
                await context.bot.send_photo(chat_id=TARGET_GROUP_ID, photo=msg_data['photo'], caption=msg_data['text'], parse_mode='HTML', reply_markup=reply_markup)
            else:
                await context.bot.send_message(chat_id=TARGET_GROUP_ID, text=msg_data['text'], parse_mode='HTML', reply_markup=reply_markup)
            await query.edit_message_text("✅ Mensagem enviada com sucesso!")
        except Exception as e:
            await query.edit_message_text(f"❌ Falha ao enviar a mensagem. Erro: {e}")
    else:
        await query.edit_message_text("Operação cancelada.")
    context.user_data.clear()
    return ConversationHandler.END

# --- Configurar Mídia de Boas-Vindas ---
@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def set_welcome_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    with sqlite3.connect(DB_PATH) as conn: conn.execute("DELETE FROM welcome_media")
    context.user_data['welcome_media_files'] = []
    await update.message.reply_text("🖼️ **Configurar Mídias de Boas-Vindas**\n\nAs mídias antigas foram removidas. Envie as novas fotos/vídeos. Quando terminar, digite /salvar.\nPara sair sem guardar, use /cancelar.")
    return AWAIT_WELCOME_MEDIA

async def receive_welcome_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_id, media_type = (None, None)
    if update.message.photo: file_id, media_type = update.message.photo[-1].file_id, 'photo'
    elif update.message.video: file_id, media_type = update.message.video.file_id, 'video'
    if file_id:
        context.user_data.setdefault('welcome_media_files', []).append({'id': file_id, 'type': media_type})
        await update.message.reply_text(f"Mídia #{len(context.user_data['welcome_media_files'])} recebida. Envie mais ou digite /salvar.")
    return AWAIT_WELCOME_MEDIA

async def save_welcome_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    media_files = context.user_data.get('welcome_media_files', [])
    if not media_files:
        await update.message.reply_text("Nenhuma mídia foi enviada. Operação cancelada.")
        context.user_data.clear()
        return ConversationHandler.END
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany("INSERT INTO welcome_media (file_id, file_type) VALUES (?, ?)", [(m['id'], m['type']) for m in media_files])
        await update.message.reply_html(f"✅ Sucesso! <b>{len(media_files)}</b> mídias de boas-vindas foram guardadas.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ocorreu um erro ao guardar as mídias: {e}")
    context.user_data.clear()
    return ConversationHandler.END

# --- Funções de Reengajamento ---
async def continue_conversation(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = context.job.chat_id
    if context.application.user_data.get(user_id, {}).get('conversation_active', False):
        try:
            await context.bot.send_message(chat_id=user_id, text=random.choice(SEXY_FOLLOW_UPS))
            context.job_queue.run_once(continue_conversation, when=timedelta(minutes=CONTINUE_CONVO_DELAY_MINUTES), chat_id=user_id, name=f"continue_convo_{user_id}")
        except Exception as e:
            logger.error(f"Erro no job continue_conversation para {user_id}: {e}")
            cancel_all_follow_ups(context, user_id)

async def reengage_user(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = context.job.chat_id
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT status FROM subscriptions WHERE user_id = ?", (user_id,)).fetchone()
    if result and result[0] == 'active': return

    try:
        with sqlite3.connect(DB_PATH) as conn:
            discount_price = conn.execute("SELECT value FROM system_settings WHERE key = 'abandoned_cart_price'").fetchone()
        
        DISCOUNT_PRICE_ABANDONED = discount_price[0] if discount_price else DEFAULT_DISCOUNT_PRICE_ABANDONED

        user_info = await context.bot.get_chat(user_id)
        original_price = PLANS["mensal"]['price']
        callback_data = f"select_plan_discount:mensal:{DISCOUNT_PRICE_ABANDONED}:-1"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"🔥 De R${original_price} por R${DISCOUNT_PRICE_ABANDONED} - PEGAR AGORA! 🔥", callback_data=callback_data)]])
        message_text = (f"🤫 Ei, {user_info.first_name}... sumiu por quê, delícia?\n\n"
                        "Pensei que a gente ia se divertir. 😉\n\n"
                        "Pra te convencer a voltar pra minha cama, liberei um desconto só pra você. Que tal?\n\n"
                        "Mas não demora, essa proposta é só sua e pode sumir a qualquer momento... e aí você perde a chance. 🔥")
        await context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO click_logs (user_id, user_name, plan_name, price, log_type, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                         (user_id, f"{user_info.first_name} {user_info.last_name or ''}".strip(), "Oferta Carrinho Abandonado", float(DISCOUNT_PRICE_ABANDONED), 'oferta_enviada', datetime.now(pytz.timezone(TIMEZONE)).isoformat()))
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem de reengajamento para {user_id}: {e}", exc_info=True)

# --- Handlers ---
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    # Ação de feedback visual imediato
    if query.data not in ["refresh_panel", "copy_pix"]:
        await query.answer("Carregando...")
    else:
        await query.answer()

    user = query.from_user
    parts = query.data.split(":")
    action = parts[0]

    if action not in ["refresh_panel"]: # Evitar cancelar o reengajamento ao atualizar o painel
        cancel_all_follow_ups(context, user.id)
        context.user_data['interaction_count'] = 0

    if action.startswith("select_plan"):
        context.job_queue.run_once(reengage_user, when=timedelta(minutes=REENGAGE_DELAY_MINUTES), chat_id=user.id, name=f"reengage_{user.id}")

    # Handlers do Painel
    if action == "refresh_panel": await painel_command(update, context)
    elif action == "painel_anunciar": await anunciar_command(update, context)
    elif action == "painel_anunciar_atriz": await anunciar_atriz_command(update, context)
    elif action == "painel_oferta": await lightning_offer_command(update, context)
    elif action == "painel_stats": await stats_command(update, context)
    elif action == "painel_buscar_start":
        await query.message.reply_text("Ok, qual o ID do utilizador que quer procurar?")
        return AWAIT_USER_ID_TO_SEARCH
    elif action == "painel_backup":
        success, result = await backup_database(context)
        if success: await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ Backup manual concluído: `{result}`", parse_mode='Markdown')
        else: await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Falha no backup: `{result}`", parse_mode='Markdown')
    elif action.startswith("falar_com_user"):
        target_id = parts[1]
        if target_id == "start":
            await query.message.reply_text("Qual o ID do utilizador para quem quer enviar uma mensagem?")
            return AWAIT_TARGET_ID
        else:
            context.user_data['target_user_id'] = int(target_id)
            await query.message.reply_text(f"Ok, a enviar mensagem para o ID <code>{target_id}</code>. Escreva abaixo o que quer enviar.", parse_mode='HTML')
            return AWAIT_MESSAGE_TO_SEND

    elif action == "info_adjust_days_start":
        context.user_data['adjust_days_target_id'] = int(parts[1])
        await query.message.reply_text(f"Quantos dias quer adicionar/remover para o utilizador <code>{parts[1]}</code>?\n(Use números positivos para adicionar, negativos para remover)", parse_mode='HTML')
        return AWAIT_DAYS_TO_ADJUST

    elif action == "info_remove_user_start":
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Sim, tenho a certeza", callback_data=f"info_confirm_remove:{parts[1]}"), InlineKeyboardButton("❌ Cancelar", callback_data="info_cancel_remove")]]))

    elif action == "info_confirm_remove":
        target_user_id = int(parts[1])
        await query.message.edit_text("A processar remoção...", reply_markup=None)
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (target_user_id,))
            db_removed = cursor.rowcount > 0
        try:
            await context.bot.ban_chat_member(chat_id=VIP_GROUP_ID, user_id=target_user_id)
            await context.bot.unban_chat_member(chat_id=VIP_GROUP_ID, user_id=target_user_id)
            kick_status = "com sucesso"
        except Exception as e: kick_status = f"falhou ({e})"
        feedback = f"Ação de remoção para <code>{target_user_id}</code> concluída.\nDB: {'Removido' if db_removed else 'Não encontrado'}\nGrupo VIP: {kick_status}"
        await query.message.edit_text(feedback, parse_mode='HTML')

    elif action == "info_cancel_remove": await query.message.edit_reply_markup(reply_markup=None)

    elif action == "select_plan" or action == "select_plan_discount":
        payment_reminder_jobs = context.job_queue.get_jobs_by_name(f"payment_reminder_{user.id}")
        for job in payment_reminder_jobs:
            job.schedule_removal()
            logger.info(f"Lembrete de pagamento anterior para {user.id} cancelado.")

        plan_id = parts[1]
        
        price = parts[2] if action == "select_plan_discount" else PLANS[plan_id]['price']
        discount = int(parts[3]) if action == "select_plan_discount" else 0
        
        log_type_map = {30: 'Renovação 30% OFF', 50: 'Renovação 50% OFF', -1: 'Carrinho Abandonado'}
        log_type = log_type_map.get(discount, 'Compra Regular')
        plan = PLANS[plan_id]
        
        await log_click(context, user, plan, price, log_type)
        
        payload = gerar_br_code(CHAVE_PIX, price, NOME_VENDEDOR, CIDADE_COBRANCA)
        context.user_data['pending_payment'] = {'plan_id': plan_id, 'price': price, 'discount': discount}
        context.user_data['pix_code_to_copy'] = payload
        
        # Gerar QR Code
        qr_img = qrcode.make(payload)
        bio = io.BytesIO()
        bio.name = 'pix_qrcode.png'
        qr_img.save(bio, 'PNG')
        bio.seek(0)

        message_text = (
            f"Boa escolha, tesão! Quase lá.\n\n"
            f"<b>Plano:</b> {plan['name']} | <b>Valor:</b> R${price}\n\n"
            "Pra liberar a putaria, faz o seguinte:\n\n"
            "1️⃣ **Escaneie o QR Code acima** com o app do seu banco.\n"
            "2️⃣ Ou **clique no botão abaixo para copiar o código PIX** e use a opção 'PIX Copia e Cola'.\n"
            "3️⃣ **MUITO IMPORTANTE:** Depois de pagar, volta aqui e me manda o comprovante. Pode ser a foto ou o PDF.\n\n"
            "Assim que eu receber, seu acesso é liberado na hora. Tô te esperando de perna aberta... 🔥"
        )
        
        keyboard = [[InlineKeyboardButton("📲 Copiar Código PIX", callback_data="copy_pix")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.delete()
        await context.bot.send_photo(
            chat_id=user.id,
            photo=bio,
            caption=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

        context.job_queue.run_once(
            remind_pending_payment,
            when=timedelta(minutes=PAYMENT_REMINDER_MINUTES),
            chat_id=user.id,
            name=f"payment_reminder_{user.id}",
            data={'user_name': user.first_name}
        )
        logger.info(f"Lembrete de pagamento agendado para {user.id} em {PAYMENT_REMINDER_MINUTES} minutos.")

    elif action == "copy_pix":
        pix_code = context.user_data.get('pix_code_to_copy')
        if pix_code:
            # Em vez de um alerta, enviamos o código como uma mensagem clicável
            await query.answer("Código PIX enviado! Toque nele para copiar.", show_alert=False)
            await context.bot.send_message(
                chat_id=user.id,
                text=f"Seu código PIX Copia e Cola está pronto!\n\n**Toque no código abaixo para copiar** e pague no app do seu banco:\n\n`{pix_code}`",
                parse_mode='Markdown'
            )
        else:
            await query.answer("Código PIX expirado. Por favor, selecione o plano novamente.", show_alert=True)

    elif action == "show_plans_discount":
        text, reply_markup = get_plans_markup_and_text(user.first_name, discount_percentage=int(parts[1]))
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    
    elif action == "show_plans_renewal":
        text, reply_markup = get_plans_markup_and_text(user.first_name)
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)

    elif action == "actress_page":
        await show_actress_list(update, context, page=int(parts[1]))

    elif action == "show_actress_portfolio":
        actress_index = int(parts[1])
        actress_name = CATALOGO_ATRIZES[actress_index]['name']
        await log_engagement(context, user, actress_name, 'portfolio_view')
        await query.message.delete()
        await send_actress_portfolio(context, query.message.chat_id, actress_index, page_for_back_button=int(parts[2]))
    
    elif action == "show_teaser_portfolio":
        actress_index = int(parts[1])
        actress_name = CATALOGO_ATRIZES[actress_index]['name']
        await log_engagement(context, user, actress_name, 'teaser_view')
        await query.message.delete()
        await send_actress_teaser(context, query.message.chat_id, actress_index)
    
    elif action == "show_vip_prompt":
        await query.answer("Para ver o conteúdo completo, torne-se um membro VIP! 🔥", show_alert=True)

    elif action == "select_found_actress":
        actress_index = int(parts[1])
        actress_name = CATALOGO_ATRIZES[actress_index]['name']
        await log_engagement(context, user, actress_name, 'search_selection')
        await query.message.delete()
        await send_actress_portfolio(context, query.message.chat_id, actress_index)

    elif action == "approve":
        _, plan_id, user_id_str, discount_str, price_str, user_name = query.data.split(":", 5)
        user_id, discount, price_paid = int(user_id_str), int(discount_str), float(price_str)
        
        cancel_all_follow_ups(context, user_id)
        chat_admins = await context.bot.get_chat_administrators(ADMIN_GROUP_ID)
        if user.id not in {admin.user.id for admin in chat_admins}:
            await query.answer("Você não tem permissão para aprovar.", show_alert=True); return

        renewal_source_map = {30: '30%_offer', 50: '50%_offer', -1: 'abandoned_cart_offer'}
        renewal_source = renewal_source_map.get(discount, 'regular')

        plan = PLANS.get(plan_id) or {"name": f"Oferta VIP", "days": int(plan_id.split('_')[-1])}
        today = datetime.now(pytz.timezone(TIMEZONE))
        expiry_date = (today + timedelta(days=plan['days'])).strftime('%Y-%m-%d')
        
        try:
            invite_link = (await context.bot.create_chat_invite_link(chat_id=VIP_GROUP_ID, member_limit=1, name=f"Acesso {plan['name']}")).invite_link
            delivery_message = (f"🔥 **ACESSO LIBERADO!** 🔥\n\n"
                                f"Parabéns! A sua assinatura do plano **{plan['name']}** foi ativada.\n\n"
                                "Use o seu link **PESSOAL** e **INTRANSFERÍVEL** para entrar.\n\n"
                                f"👇 **CLIQUE E VENHA DIVERTIR-SE** 👇\n➡️ {invite_link} ⬅️")
            await context.bot.send_message(chat_id=user_id, text=delivery_message, parse_mode='HTML')

            # Mensagem de boas-vindas aprimorada
            welcome_vip_message = (
                "🎉 **Bem-vindo ao nosso Paraíso, gostoso!** 🎉\n\n"
                "Agora que você tá dentro, aqui vão algumas dicas pra aproveitar ao máximo:\n\n"
                "👉 Use o comando /atrizes para ver nosso menu completo de deusas.\n"
                "👉 Use /lista para ver todos os nomes de uma vez.\n"
                "👉 Use /buscar `nome` para ir direto ao que te interessa.\n\n"
                "Qualquer dúvida, é só chamar. Agora vai lá se divertir! 😉"
            )
            await context.bot.send_message(chat_id=user_id, text=welcome_vip_message, parse_mode='HTML')
            
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO subscriptions (user_id, user_name, start_date, expiry_date, plan_name, status, renewal_source, price_paid, dias_ajustados)
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?, 0)
                    ON CONFLICT(user_id) DO UPDATE SET
                    user_name=excluded.user_name, start_date=excluded.start_date, expiry_date=excluded.expiry_date, 
                    plan_name=excluded.plan_name, status='active', renewal_source=excluded.renewal_source, price_paid=excluded.price_paid, dias_ajustados=0
                """, (user_id, user_name, today.strftime('%Y-%m-%d'), expiry_date, plan['name'], renewal_source, price_paid))
            
            log_message = (f"✅ **Nova Assinatura Ativada** ✅\n\n"
                           f"👤 <b>Cliente:</b> {user_name} (<code>{user_id}</code>)\n"
                           f"💎 <b>Plano:</b> {plan['name']}\n💰 <b>Valor Pago:</b> R$ {price_paid:.2f}\n"
                           f"📅 <b>Término:</b> {datetime.strptime(expiry_date, '%Y-%m-%d').strftime('%d/%m/%Y')}\n\n"
                           f"👤 <b>Aprovado por:</b> {user.first_name}")
            await context.bot.send_message(chat_id=LOG_GROUP_ID, text=log_message, parse_mode='HTML')
            await query.edit_message_text(f"✅ Assinatura de <code>{user_id}</code> ({plan['name']}) **APROVADA** por {user.first_name}.", parse_mode='HTML')
        except Exception as e:
            await query.edit_message_text(f"❌ Falha ao aprovar. O utilizador pode ter bloqueado o bot. Erro: {e}")
            logger.error(f"Erro ao aprovar pagamento para {user_id}: {e}", exc_info=True)
            
    elif action == "deny":
        chat_admins = await context.bot.get_chat_administrators(ADMIN_GROUP_ID)
        if user.id not in {admin.user.id for admin in chat_admins}:
            await query.answer("Você não tem permissão para recusar.", show_alert=True); return
            
        user_id_to_deny = int(parts[1])
        try:
            await context.bot.send_message(chat_id=user_id_to_deny, text="😕 Infelizmente, houve um problema com o seu pagamento e não pudemos confirmar.\n\nPor favor, verifique os dados e tente novamente ou contacte o suporte.")
            await query.edit_message_text(f"❌ Pagamento de <code>{user_id_to_deny}</code> **RECUSADO** por {user.first_name}.", parse_mode='HTML')
        except Exception as e:
            await query.edit_message_text(f"❌ Falha ao notificar o utilizador <code>{user_id_to_deny}</code> (pode ter bloqueado o bot). A recusa foi registada.", parse_mode='HTML')
            logger.error(f"Erro ao recusar pagamento: {e}", exc_info=True)

    elif action == "confirm_anunciar_tudo":
        await query.edit_message_text("✅ Confirmação recebida. A postagem em massa foi iniciada em segundo plano. Você será notificado quando terminar.", reply_markup=None)
        context.job_queue.run_once(anunciar_tudo_job, 1, data={'chat_id': query.message.chat_id, 'user_id': query.from_user.id}, name=f"anunciar_tudo_{query.from_user.id}")

    elif action == "cancel_anunciar_tudo":
        await query.edit_message_text("Operação cancelada.", reply_markup=None)

async def comprovante_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recebe o comprovativo de pagamento, encaminha para admins e aguarda aprovação."""
    user = update.effective_user

    payment_reminder_jobs = context.job_queue.get_jobs_by_name(f"payment_reminder_{user.id}")
    if payment_reminder_jobs:
        for job in payment_reminder_jobs:
            job.schedule_removal()
        logger.info(f"Lembrete de pagamento para {user.id} cancelado devido ao envio do comprovativo.")

    cancel_all_follow_ups(context, user.id)
    pending_payment = context.user_data.pop('pending_payment', None)
    if not pending_payment:
        await update.message.reply_text("🤔 Ué, delícia... mandou comprovante antes de escolher o plano? Usa o /start primeiro pra gente se conhecer melhor. 😉")
        return
        
    plan_id, price, discount = pending_payment['plan_id'], pending_payment['price'], pending_payment.get('discount', 0)
    plan = PLANS.get(plan_id) or {"name": "Oferta Especial"}
    await update.message.reply_text(random.choice([
        "Recebido, tesão! 🔥\n\nJá mandei pra conferir. Assim que liberarem, eu mesma volto pra te dar seu acesso. Fica de olho aqui, não vai fazer nada sem mim. 😉",
        "Hmm, gostei da atitude. Pagamento na mão, calcinha no chão! 😈\n\nVou só mostrar aqui pra liberarem e já volto com o seu presente. Aguenta a rola aí...",
        "Opa, chegou! Agora a putaria vai começar de verdade. ✨\n\nSó um minutinho enquanto confirmam. Prepara o pau que seu acesso tá quase saindo do forno."]))
    
    user_name = f"{user.first_name} {user.last_name or ''}".strip()
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Aprovar", callback_data=f"approve:{plan_id}:{user.id}:{discount}:{price}:{user_name}"), InlineKeyboardButton("❌ Recusar", callback_data=f"deny:{user.id}")]])
    await context.bot.forward_message(chat_id=ADMIN_GROUP_ID, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
    await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"🔔 **NOVA NOTIFICAÇÃO DE PAGAMENTO** 🔔\n\n<b>Plano:</b> {plan['name']}\n<b>Utilizador:</b> {user_name}\n<b>ID:</b> <code>{user.id}</code>\n\nVerifique e tome uma ação:", reply_markup=reply_markup, parse_mode='HTML')

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('conversation_active', False): return
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT value FROM system_settings WHERE key = 'conversation_teaser_actress'").fetchone()
    if not result or not result[0]: return
    teaser_actress_name = result[0]
    
    context.user_data['interaction_count'] = context.user_data.get('interaction_count', 0) + 1
    if context.user_data['interaction_count'] >= INTERACTION_TRIGGER_COUNT:
        context.user_data['interaction_count'] = 0
        actress_index = next((i for i, actress in enumerate(CATALOGO_ATRIZES) if actress['name'].lower() == teaser_actress_name.lower()), -1)
        if actress_index != -1:
            await asyncio.sleep(random.uniform(1.5, 3.0))
            await send_conversation_teaser(context, update.effective_chat.id, actress_index)

# --- Funções de Adicionar Mídia ---
async def show_admin_actress_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    ITEMS_PER_PAGE = 20
    with sqlite3.connect(DB_PATH) as conn:
        all_actresses = [row[0] for row in conn.execute("SELECT DISTINCT actress_name FROM media_catalog ORDER BY actress_name").fetchall()]

    start_index, end_index = page * ITEMS_PER_PAGE, (page + 1) * ITEMS_PER_PAGE
    page_items = all_actresses[start_index:end_index]
    keyboard = [[InlineKeyboardButton(name, callback_data=f"actress_{name}")] for name in page_items]
    
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"admin_actress_page:{page - 1}"))
    if end_index < len(all_actresses): nav_row.append(InlineKeyboardButton("Próximo ➡️", callback_data=f"admin_actress_page:{page + 1}"))
    if nav_row: keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Menu", callback_data="add_media_back_to_menu")])
    
    text = f"📖 **Selecione uma Atriz Existente** (Página {page + 1}/{math.ceil(len(all_actresses) / ITEMS_PER_PAGE)})"
    if update.callback_query: await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def select_add_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "add_media_show_list":
        await show_admin_actress_selection(update, context, page=0)
        return SELECT_ACTION
    elif data == "add_media_type_name":
        await query.edit_message_text("Ok. Digite o nome exato da atriz:")
        return AWAIT_TYPED_NAME
    elif data == "add_new_actress":
        await query.edit_message_text("Ok. Qual o nome da nova atriz?")
        return AWAIT_NAME
    elif data == "cancel_add_media":
        await query.edit_message_text("Operação cancelada.")
        return ConversationHandler.END
    return SELECT_METHOD

async def receive_typed_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    actress_name = update.message.text.strip()
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT actress_name FROM media_catalog WHERE LOWER(actress_name) = ? LIMIT 1", (actress_name.lower(),)).fetchone()
    if result:
        context.user_data['actress_name'] = result[0]
        await update.message.reply_html(f"✅ Atriz '<b>{result[0]}</b>' encontrada! Pode começar a enviar as mídias. Quando terminar, digite /salvar.")
        return RECEIVING_MEDIA
    else:
        await update.message.reply_html(f"❌ Nenhuma atriz encontrada com o nome '<b>{actress_name}</b>'. Tente novamente ou use /cancelar.")
        return AWAIT_TYPED_NAME

@admin_required(allowed_chat_ids=[STORAGE_CHANNEL_ID], admin_check_chat_id=STORAGE_CHANNEL_ID)
async def add_media_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton("🔎 Digitar Nome", callback_data="add_media_type_name")],
                [InlineKeyboardButton("📋 Ver Lista", callback_data="add_media_show_list")],
                [InlineKeyboardButton("➕ Nova Atriz", callback_data="add_new_actress")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_add_media")]]
    await update.message.reply_text("📖 **Adicionar Mídia**\n\nComo quer selecionar a atriz?", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_METHOD

async def select_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("admin_actress_page:"):
        await show_admin_actress_selection(update, context, page=int(data.split(":")[1]))
        return SELECT_ACTION
    elif data.startswith("actress_"):
        actress_name = data.split("_", 1)[1]
        context.user_data['actress_name'] = actress_name
        await query.edit_message_text(f"✅ Ok, a receber mídias para <b>{actress_name}</b>.\nEnvie os ficheiros. Quando terminar, digite /salvar.", parse_mode='HTML')
        return RECEIVING_MEDIA
    elif data == "add_media_back_to_menu":
        keyboard = [[InlineKeyboardButton("🔎 Digitar Nome", callback_data="add_media_type_name")], [InlineKeyboardButton("📋 Ver Lista", callback_data="add_media_show_list")], [InlineKeyboardButton("➕ Nova Atriz", callback_data="add_new_actress")], [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_add_media")]]
        await query.edit_message_text("📖 **Adicionar Mídia**\n\nComo quer selecionar a atriz?", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_METHOD
    return SELECT_ACTION

async def receive_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    actress_name = update.message.text.strip()
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute("SELECT actress_name FROM media_catalog WHERE LOWER(actress_name) = ?", (actress_name.lower(),)).fetchone()
    if existing:
        await update.message.reply_html(f"❌ <b>Erro:</b> Uma atriz com o nome '<b>{existing[0]}</b>' já existe. Tente outro nome.")
        return AWAIT_NAME
    context.user_data['actress_name'] = actress_name
    await update.message.reply_html(f"Ok, nova deusa <b>{actress_name}</b> registada.\nAgora, envie as mídias. Quando terminar, digite /salvar.")
    return RECEIVING_MEDIA

async def receive_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    media_info = {}
    if update.message.photo: media_info = {'id': update.message.photo[-1].file_id, 'type': 'photo', 'duration': 0}
    elif update.message.video: media_info = {'id': update.message.video.file_id, 'type': 'video', 'duration': update.message.video.duration}
    if media_info:
        context.user_data.setdefault('media_files', []).append(media_info)
        await update.message.reply_text(f"Mídia #{len(context.user_data['media_files'])} recebida. Envie mais ou digite /salvar.")
    return RECEIVING_MEDIA

async def save_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    actress_name = context.user_data.get('actress_name')
    media_files = context.user_data.get('media_files', [])
    if not actress_name or not media_files:
        await update.message.reply_text("Operação cancelada. Nenhuma mídia enviada."); return ConversationHandler.END

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        is_existing = cursor.execute("SELECT 1 FROM media_catalog WHERE actress_name = ? LIMIT 1", (actress_name,)).fetchone()
        saved_count, skipped_count = 0, 0
        for media in media_files:
            try:
                cursor.execute("INSERT INTO media_catalog (actress_name, file_id, file_type, duration) VALUES (?, ?, ?, ?)", (actress_name, media['id'], media['type'], media.get('duration', 0)))
                saved_count += 1
            except sqlite3.IntegrityError: skipped_count += 1
        conn.commit()

    message = f"✅ Sucesso! {saved_count} novas mídias guardadas para <b>{actress_name}</b>."
    if skipped_count > 0: message += f"\nℹ️ {skipped_count} mídias ignoradas por já existirem."
    await update.message.reply_html(message)

    if saved_count > 0:
        bot_username = (await context.bot.get_me()).username
        vip_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["want_to_be_vip"], url=f"https://t.me/{bot_username}?start=vip")]])
        if not is_existing:
            free_group_message = f"🔞🔥 **CARNE NOVA NO PEDAÇO!** 🔥🔞\n\nAcabámos de adicionar a deliciosa <b>{actress_name}</b> ao nosso cardápio com <b>{saved_count}</b> novas mídias! Os VIPs já estão a deliciar-se... e tu? 😏"
            vip_group_message = f"🔥 **NOVA DEUSA NO CATÁLOGO!** 🔥\n\nA deliciosa <b>{actress_name}</b> chegou com <b>{saved_count}</b> novas mídias! Use /atrizes ou /buscar. 😈"
        else:
            free_group_message = f"🚀🔥 **CONTEÚDO NOVO E QUENTINHO!** 🔥🚀\n\nA insaciável <b>{actress_name}</b> acaba de receber <b>{saved_count}</b> novas mídias no VIP! Queres ver? O **Acesso VIP** é o teu único caminho. 😈"
            vip_group_message = f"🚀 **CATÁLOGO ATUALIZADO!** 🚀\n\n<b>{saved_count}</b> novas mídias adicionadas para <b>{actress_name}</b>. Use /atrizes ou /buscar!"
        
        for group_id, text, markup in [(TARGET_GROUP_ID, free_group_message, vip_keyboard), (VIP_GROUP_ID, vip_group_message, None)]:
            try: await context.bot.send_message(chat_id=group_id, text=text, reply_markup=markup, parse_mode='HTML')
            except Exception as e: await update.message.reply_text(f"⚠️ Aviso: Falha ao notificar o grupo {group_id}. Erro: {e}")
    
    context.user_data.clear()
    build_catalog_from_db()
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancel_all_follow_ups(context, update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text("Ok, operação cancelada. Se mudares de ideia, é só chamar-me. 😉")
    return ConversationHandler.END

# --- Tarefas Agendadas (Jobs) ---
async def anunciar_tudo_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job que executa a postagem de todos os portfólios de atrizes."""
    chat_id = context.job.data['chat_id']
    
    await context.bot.send_message(chat_id=chat_id, text=f"🚀 Iniciando postagem em massa de {len(CATALOGO_ATRIZES)} portfólios...")
    
    count = 0
    errors = 0
    
    for i, actress in enumerate(CATALOGO_ATRIZES):
        try:
            # Envia o portfólio para o grupo VIP, sem o botão de voltar para a lista
            await send_actress_portfolio(context, VIP_GROUP_ID, i, page_for_back_button=None)
            count += 1
            # Delay crucial para não sobrecarregar a API do Telegram
            await asyncio.sleep(5)
        except Exception as e:
            errors += 1
            logger.error(f"Falha ao postar o portfólio de {actress.get('name', 'Desconhecida')}: {e}")
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"⚠️ Falha ao postar o portfólio de <b>{actress.get('name', 'Desconhecida')}</b>. Erro: {e}. Continuando...",
                parse_mode='HTML'
            )
            await asyncio.sleep(2) # Pausa extra em caso de erro

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🏁 **Postagem em Massa Concluída!**\n\n"
             f"✅ Portfólios postados: <b>{count}</b>\n"
             f"❌ Falhas: <b>{errors}</b>",
        parse_mode='HTML'
    )

async def _post_actress_teaser(context: ContextTypes.DEFAULT_TYPE, actress: dict) -> bool:
    all_photos = [m for m in actress['media_files'] if m['type'] == 'photo']
    short_videos = [m for m in actress['media_files'] if m['type'] == 'video' and m['duration'] <= 30]
    if not all_photos or not short_videos: return False
    try:
        selected_media = [random.choice(all_photos), random.choice(short_videos)]
        random.shuffle(selected_media)
        media_group = [(InputMediaPhoto if m['type'] == 'photo' else InputMediaVideo)(media=m['id'], caption=f"🔥 Uma prévia de <b>{actress['name']}</b> para vocês! 🔥" if i == 0 else None, parse_mode='HTML') for i, m in enumerate(selected_media)]
        bot_username = (await context.bot.get_me()).username
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["want_to_be_vip"], url=f"https://t.me/{bot_username}")]])
        call_to_action = (f"Gostaste desta prévia da <b>{actress['name']}</b>? 😏\n\n"
                          "Isso não é nem 1% do que te espera no <b>Grupo VIP</b>.\n\n"
                          "**Clique abaixo e liberte o seu acesso ao paraíso agora!** 🔥")
        await context.bot.send_media_group(chat_id=TARGET_GROUP_ID, media=media_group)
        await context.bot.send_message(chat_id=TARGET_GROUP_ID, text=call_to_action, parse_mode='HTML', reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.error(f"Erro ao postar teaser da atriz '{actress['name']}': {e}", exc_info=True)
        return False

async def send_tutorial_video(context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT value FROM system_settings WHERE key = ?", ('tutorial_video_id',)).fetchone()
    if not result or not result[0]: return

    bot_username = (await context.bot.get_me()).username
    vip_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["want_to_be_vip"], url=f"https://t.me/{bot_username}")]])
    group_configs = {
        VIP_GROUP_ID: {"caption": "📹 <b>TUTORIAL RÁPIDO!</b> 📹\n\nConfira como aproveitar ao máximo o nosso conteúdo.", "keyboard": None},
        TARGET_GROUP_ID: {"caption": "📹😈 **VEJA COMO É FÁCIL PERDER-SE AQUI DENTRO...** 😈📹\n\n**Entre para o Grupo VIP** e tenha tudo na palma da sua mão!", "keyboard": vip_keyboard}
    }
    for group_id, config in group_configs.items():
        try:
            await context.bot.send_video(chat_id=group_id, video=result[0], caption=config["caption"], reply_markup=config["keyboard"], parse_mode='HTML')
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Erro ao enviar vídeo tutorial para o grupo {group_id}: {e}", exc_info=True)

async def send_advertisement(context: ContextTypes.DEFAULT_TYPE):
    os.makedirs(AD_MEDIA_FOLDER, exist_ok=True)
    try:
        valid_media = [f for f in os.listdir(AD_MEDIA_FOLDER) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.m4v'))]
        if not valid_media: return
        
        selected_files = random.sample(valid_media, min(len(valid_media), 2))
        bot_username = (await context.bot.get_me()).username
        keyboard = [[InlineKeyboardButton(BUTTON_TEXTS["plan_button"].format(plan_name=p['name'], price=p['price']), url=f"https://t.me/{bot_username}?start=plan_{pid}")] for pid, p in PLANS.items()]
        reply_markup = InlineKeyboardMarkup(keyboard)

        media_group, opened_files = [], []
        try:
            for i, filename in enumerate(selected_files):
                file_path = os.path.join(AD_MEDIA_FOLDER, filename)
                media_file = open(file_path, 'rb')
                opened_files.append(media_file)
                MediaType = InputMediaPhoto if filename.lower().endswith(('.jpg', '.jpeg', '.png')) else InputMediaVideo
                media_group.append(MediaType(media=media_file, caption=random.choice(AD_MESSAGE_TEXTS) if i == 0 else None, parse_mode='HTML'))
            
            await context.bot.send_media_group(chat_id=TARGET_GROUP_ID, media=media_group)
            await context.bot.send_message(chat_id=TARGET_GROUP_ID, text="<b>Escolha o seu plano e entre para o paraíso!</b> 👇", parse_mode='HTML', reply_markup=reply_markup)
        finally:
            for f in opened_files: f.close()
    except Exception as e:
        logger.error(f"Erro ao enviar o anúncio: {e}", exc_info=True)

async def post_teaser_to_free_group(context: ContextTypes.DEFAULT_TYPE):
    if not CATALOGO_ATRIZES: return
    eligible = [a for a in CATALOGO_ATRIZES if any(m['type'] == 'photo' for m in a['media_files']) and any(m['type'] == 'video' and m['duration'] <= 30 for m in a['media_files'])]
    if eligible: await _post_actress_teaser(context, random.choice(eligible))

async def send_daily_bulletin(context: ContextTypes.DEFAULT_TYPE) -> None:
    yesterday_start = datetime.now(pytz.timezone(TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    yesterday_end = yesterday_start + timedelta(days=1, seconds=-1)
    
    with sqlite3.connect(DB_PATH) as conn:
        new_subs, daily_revenue = conn.execute("SELECT COUNT(*), SUM(price_paid) FROM subscriptions WHERE start_date = ?", (yesterday_start.strftime('%Y-%m-%d'),)).fetchone()
        expired_yesterday = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE expiry_date = ? AND status = 'expired'", (yesterday_start.strftime('%Y-%m-%d'),)).fetchone()[0]
        
        # Novas métricas
        total_clicks = conn.execute("SELECT COUNT(*) FROM click_logs WHERE timestamp >= ? AND timestamp <= ?", (yesterday_start.isoformat(), yesterday_end.isoformat())).fetchone()[0]
        best_selling_plan = conn.execute(
            "SELECT plan_name FROM subscriptions WHERE start_date = ? GROUP BY plan_name ORDER BY COUNT(plan_name) DESC LIMIT 1",
            (yesterday_start.strftime('%Y-%m-%d'),)
        ).fetchone()

    conversion_rate = (new_subs / total_clicks * 100) if total_clicks > 0 else 0
    plan_do_dia = best_selling_plan[0] if best_selling_plan else "N/A"

    bulletin_text = (f"📊 **Boletim Diário - {yesterday_start.strftime('%d/%m/%Y')}** 📊\n\n"
                     f"💰 **Vendas:**\n"
                     f"  • Novas assinaturas: **{new_subs or 0}**\n"
                     f"  • Faturação: **R$ {daily_revenue or 0.0:.2f}**\n\n"
                     f"📈 **Performance:**\n"
                     f"  • Cliques em planos: **{total_clicks}**\n"
                     f"  • Taxa de Conversão: **{conversion_rate:.2f}%**\n"
                     f"  • Plano do Dia: **{plan_do_dia}**\n\n"
                     f"👥 **Membros:**\n"
                     f"  • Assinaturas expiradas: **{expired_yesterday or 0}**\n\n"
                     "✅ **Estado dos Sistemas:** Tudo a operar normalmente.")
    await context.bot.send_message(chat_id=LOG_GROUP_ID, text=bulletin_text, parse_mode='HTML')

async def remove_temp_access(context: ContextTypes.DEFAULT_TYPE) -> None:
    job_data = context.job.data
    user_id, user_name, chat_id = job_data['user_id'], job_data['user_name'], job_data['chat_id']
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ['member', 'restricted']:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.send_message(chat_id=LOG_GROUP_ID, text=f"⏰ **Acesso Expirado** ⏰\nO acesso temporário de <b>{user_name}</b> (<code>{user_id}</code>) foi revogado.", parse_mode='HTML')
            try: await context.bot.send_message(chat_id=user_id, text="👋 O seu tempo de acesso gratuito terminou. Para voltar, use /start e torne-se VIP! 😉")
            except Forbidden: pass
    except Exception as e:
        logger.error(f"Erro ao remover acesso temporário de {user_id}: {e}", exc_info=True)

async def check_renewal_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Verifica e envia múltiplos lembretes de renovação."""
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Lembrete de 3 dias
        three_days_from_now = (now + timedelta(days=3)).strftime('%Y-%m-%d')
        users_3_days = cursor.execute("SELECT user_id, user_name FROM subscriptions WHERE expiry_date = ? AND status = 'active' AND reminder_sent = 0", (three_days_from_now,)).fetchall()
        for user_id, user_name in users_3_days:
            try:
                await context.bot.send_message(chat_id=user_id, text="⏳ **Faltam 3 dias!** ⏳\nSua assinatura está quase no fim. Não fique de fora da putaria, renove usando /start e continue gozando com a gente. 😉")
                conn.execute("UPDATE subscriptions SET reminder_sent = 1 WHERE user_id = ?", (user_id,))
            except Exception as e:
                logger.error(f"Erro ao enviar lembrete de 3 dias para {user_id}: {e}")
        
        # Lembrete de 1 dia
        one_day_from_now = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        users_1_day = cursor.execute("SELECT user_id, user_name FROM subscriptions WHERE expiry_date = ? AND status = 'active' AND reminder_sent = 1", (one_day_from_now,)).fetchall()
        for user_id, user_name in users_1_day:
            try:
                await context.bot.send_message(chat_id=user_id, text="🔥 **É AMANHÃ!** 🔥\nSua assinatura vence em 24 horas. Vai mesmo deixar o paraíso pra trás? Renove agora com /start antes que seja tarde demais!")
                conn.execute("UPDATE subscriptions SET reminder_sent = 2 WHERE user_id = ?", (user_id,))
            except Exception as e:
                logger.error(f"Erro ao enviar lembrete de 1 dia para {user_id}: {e}")

        conn.commit()


async def send_discount_offers(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone(TIMEZONE)
    with sqlite3.connect(DB_PATH) as conn:
        three_days_ago = (datetime.now(tz) - timedelta(days=3)).strftime('%Y-%m-%d')
        users_30_off = conn.execute("SELECT user_id, user_name FROM subscriptions WHERE status = 'expired' AND expiry_date = ? AND discount_offer_sent = 0", (three_days_ago,)).fetchall()
        for user_id, user_name in users_30_off:
            try:
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["renew_with_30_off"], callback_data="show_plans_discount:30")]])
                await context.bot.send_message(chat_id=user_id, text="🤫 Ei, sumido(a)! Sentimos a tua falta... A tua assinatura expirou, mas para voltares, liberamos um presente: 🔥 **30% DE DESCONTO EM QUALQUER PLANO!** 🔥", parse_mode='HTML', reply_markup=reply_markup)
                conn.execute("UPDATE subscriptions SET discount_offer_sent = 1 WHERE user_id = ?", (user_id,))
            except Exception as e: logger.error(f"Erro ao enviar oferta 30% para {user_id}: {e}")

        seven_days_ago = (datetime.now(tz) - timedelta(days=7)).strftime('%Y-%m-%d')
        users_50_off = conn.execute("SELECT user_id, user_name FROM subscriptions WHERE status = 'expired' AND expiry_date = ? AND discount_offer_sent = 1", (seven_days_ago,)).fetchall()
        for user_id, user_name in users_50_off:
            try:
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["renew_with_50_off"], callback_data="show_plans_discount:50")]])
                await context.bot.send_message(chat_id=user_id, text="🔥 **ÚLTIMA CHAMADA!** 🔥\nA tua assinatura expirou há uma semana e esta é a tua oportunidade final de voltar com **50% DE DESCONTO**. É pegar ou largar. 😉", parse_mode='HTML', reply_markup=reply_markup)
                conn.execute("UPDATE subscriptions SET discount_offer_sent = 2 WHERE user_id = ?", (user_id,))
            except Exception as e: logger.error(f"Erro ao enviar oferta 50% para {user_id}: {e}")

async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.now(pytz.timezone(TIMEZONE)).strftime('%Y-%m-%d')
    with sqlite3.connect(DB_PATH) as conn:
        expired_users = conn.execute("SELECT user_id, user_name FROM subscriptions WHERE expiry_date < ? AND status = 'active'", (today_str,)).fetchall()
        if not expired_users: return
        for user_id, user_name in expired_users:
            try:
                await context.bot.ban_chat_member(chat_id=VIP_GROUP_ID, user_id=user_id)
                await context.bot.unban_chat_member(chat_id=VIP_GROUP_ID, user_id=user_id)
                admin_msg = f"e foi **removido(a)** do grupo VIP."
            except Exception as e:
                admin_msg = f"mas **NÃO foi possível removê-lo(a)**. Erro: {e}"
            try:
                reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["renew_subscription"], callback_data="show_plans_renewal")]])
                await context.bot.send_message(chat_id=user_id, text="😢 Sua assinatura expirou e seu acesso foi removido.\n\nMas não fica triste, gostoso. Pra voltar pra putaria, é só clicar no botão e renovar! Te espero de volta. 🔥", reply_markup=reply_markup)
            except Forbidden:
                admin_msg += " O utilizador **bloqueou** o bot."
            
            conn.execute("UPDATE subscriptions SET status = 'expired' WHERE user_id = ?", (user_id,))
            log_msg = (f"⌛️ **Assinatura Expirada** ⌛️\n\n"
                       f"👤 <b>Utilizador:</b> {user_name} (<code>{user_id}</code>)\n"
                       f"ℹ️ A sua assinatura expirou {admin_msg}")
            await context.bot.send_message(chat_id=LOG_GROUP_ID, text=log_msg, parse_mode='HTML')
            
async def sync_catalog_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("A executar a sincronização agendada do catálogo...")
    build_catalog_from_db()

async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    new_member = update.message.new_chat_members[0]
    if update.effective_chat.id == TARGET_GROUP_ID and not new_member.is_bot:
        try: await update.message.delete()
        except Exception as e: logger.warning(f"Não foi possível apagar a mensagem de entrada: {e}")
        try:
            bot_username = (await context.bot.get_me()).username
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXTS["talk_private"], url=f"https://t.me/{bot_username}")]])
            await context.bot.send_message(chat_id=new_member.id, text=f"Oii, {new_member.first_name}! Vi que entraste no meu grupo de prévias... Que bom ter-te por lá! 😏\n\nSe quiseres conversar e ver o que mais tenho para oferecer, clica no botão e chama-me no privado. Estou à tua espera. 🔥", reply_markup=reply_markup)
        except Forbidden:
            logger.warning(f"Não foi possível notificar {new_member.id} sobre o acesso temporário (bot bloqueado).")

async def remind_pending_payment(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem insistente para utilizadores que não enviaram o comprovativo."""
    job = context.job
    user_id = job.chat_id
    user_name = job.data.get('user_name', 'gato(a)')

    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT status FROM subscriptions WHERE user_id = ?", (user_id,)).fetchone()
    
    if result and result[0] == 'active':
        logger.info(f"Lembrete de pagamento para {user_id} cancelado, pois o utilizador já é um assinante.")
        return

    logger.info(f"A enviar lembrete de pagamento pendente para o utilizador {user_id}.")

    reminder_texts = [
        (f"Ei, {user_name}... tô aqui esperando, de calcinha molhada. 🔥\n\nFalta só você pagar pra gente começar a se divertir. Vai me deixar na vontade? Paga logo esse PIX. O paraíso tá te esperando..."),
        (f"Oii, {user_name} 👀\n\nSeu acesso VIP tá quase liberado, só falta o comprovante. Não vai amarelar agora, né? A putaria aqui dentro tá comendo solta e você tá perdendo tudo. Paga logo esse PIX e vem!"),
        (f"Psiu... {user_name}, só pra lembrar que tô te esperando no VIP. 😉\n\nNão demora, senão outro mais rápido pega seu lugar... Paga o PIX e me manda o comprovante. Tô ansiosa pra te ver aqui dentro."),
    ]

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=random.choice(reminder_texts)
        )
    except Forbidden:
        logger.warning(f"Não foi possível enviar o lembrete de pagamento para {user_id}. O bot foi bloqueado.")
    except Exception as e:
        logger.error(f"Erro ao enviar lembrete de pagamento para {user_id}: {e}", exc_info=True)


async def backup_database(context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
    """Cria uma cópia de segurança da base de dados e notifica os admins."""
    try:
        os.makedirs(BACKUP_FOLDER, exist_ok=True)
        timestamp = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"backup_{timestamp}.db"
        shutil.copy(DB_PATH, os.path.join(BACKUP_FOLDER, backup_filename))
        if context.job and context.job.name == "daily_backup_job":
             await context.bot.send_message(chat_id=LOG_GROUP_ID, text=f"✅ Backup automático realizado: `{backup_filename}`", parse_mode='Markdown')
        return True, backup_filename
    except Exception as e:
        logger.error(f"FALHA CRÍTICA NO BACKUP: {e}", exc_info=True)
        admins = await context.bot.get_chat_administrators(ADMIN_GROUP_ID)
        admin_mentions = " ".join([f"@{admin.user.username}" if admin.user.username else f"[{admin.user.first_name}](tg://user?id={admin.user.id})" for admin in admins if not admin.user.is_bot])
        error_message = (
            f"🚨 **ALERTA CRÍTICO: FALHA NO BACKUP!** 🚨\n\n"
            f"O sistema não conseguiu criar uma cópia de segurança da base de dados.\n\n"
            f"**Erro:** `{e}`\n\n"
            f"Atenção, administradores: {admin_mentions}\n\n"
            "É crucial verificar o espaço em disco e as permissões da pasta."
        )
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=error_message, parse_mode='Markdown')
        return False, str(e)

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def settutorial_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Ok. Envie o vídeo que deseja usar como tutorial. Para cancelar, digite /cancelar.")
    return AWAIT_VIDEO

async def receive_tutorial_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.video:
        await update.message.reply_text("Isto não é um vídeo. Envie um vídeo ou /cancelar.")
        return AWAIT_VIDEO
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", ('tutorial_video_id', update.message.video.file_id))
    await update.message.reply_text("✅ Vídeo tutorial guardado com sucesso!")
    return ConversationHandler.END

@admin_required(allowed_chat_ids=[STORAGE_CHANNEL_ID], admin_check_chat_id=STORAGE_CHANNEL_ID)
async def updatedurations_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    replied_message = update.message.reply_to_message
    if not replied_message or not replied_message.video:
        await update.message.reply_text("⚠️ Use este comando respondendo a um vídeo.")
        return

    file_id, duration = replied_message.video.file_id, replied_message.video.duration
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT actress_name, duration FROM media_catalog WHERE file_id = ?", (file_id,)).fetchone()
        if result:
            if result[1] != duration:
                conn.execute("UPDATE media_catalog SET duration = ? WHERE file_id = ?", (duration, file_id))
                await update.message.reply_html(f"✅ Duração do vídeo de <b>{result[0]}</b> atualizada para <b>{duration}</b> segundos.")
            else:
                await update.message.reply_text("ℹ️ A duração já estava correta.")
        else:
            await update.message.reply_text("❌ Este vídeo não foi encontrado no catálogo.")

async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = update.chat_member
    if (result.chat.id == VIP_GROUP_ID and result.old_chat_member.status not in ("member", "administrator", "creator")
        and result.new_chat_member.status in ("member", "administrator", "creator") and result.invite_link):
        invite_link = result.invite_link.invite_link
        if invite_link in context.bot_data:
            offer_data = context.bot_data.pop(invite_link)
            new_member = result.new_chat_member.user
            user_name = f"{new_member.first_name} {new_member.last_name or ''}".strip()

            try: await context.bot.revoke_chat_invite_link(chat_id=result.chat.id, invite_link=invite_link)
            except Exception as e: logger.error(f"Falha ao revogar link da oferta: {e}")
            try: await context.bot.delete_message(chat_id=offer_data['chat_id'], message_id=offer_data['message_id'])
            except Exception as e: logger.error(f"Falha ao apagar mensagem da oferta: {e}")

            job_context = {'user_id': new_member.id, 'user_name': user_name, 'chat_id': result.chat.id}
            context.job_queue.run_once(remove_temp_access, when=timedelta(minutes=OFFER_DURATION_MINUTES), data=job_context, name=f"remove_temp_{new_member.id}")
            
            await context.bot.send_message(chat_id=LOG_GROUP_ID, text=(f"⚡ **Utilizador de Oferta Entrou!** ⚡\n\n"
                                                                        f"👤 <b>Utilizador:</b> {user_name} (<code>{new_member.id}</code>)\n"
                                                                        f"⏰ <b>Acesso:</b> {OFFER_DURATION_MINUTES} minutos.\n\n"
                                                                        f"✅ Remoção agendada."), parse_mode='HTML')
            try:
                await context.bot.send_message(chat_id=new_member.id, text=(f"Parabéns! 🚀\n\nResgataste a oferta e ganhaste <b>{OFFER_DURATION_MINUTES} minutos</b> de acesso ao VIP. Aproveite!"), parse_mode='HTML')
            except Forbidden: pass

@admin_required(allowed_chat_ids=[ADMIN_GROUP_ID])
async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.reply_text("A iniciar backup manual...")
        success, result = await backup_database(context)
        if success: await update.message.reply_text(f"✅ Backup concluído: `{result}`", parse_mode='Markdown')
        else: await update.message.reply_text(f"❌ Falha no backup. Erro: `{result}`", parse_mode='Markdown')
    except Exception as e: logger.error(f"Erro ao executar /backup: {e}", exc_info=True)

async def post_init(application: Application) -> None:
    private_commands = [BotCommand("start", "▶️ Iniciar Conversa"), BotCommand("status", "⭐ Verificar assinatura")]
    await application.bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
    free_group_commands = [BotCommand("previa", "👀 Ver degustação"), BotCommand("vip", "💎 Quero ser VIP")]
    await application.bot.set_my_commands(free_group_commands, scope=BotCommandScopeChat(chat_id=TARGET_GROUP_ID))
    vip_commands = [BotCommand("atrizes", "📚 Ver catálogo"), BotCommand("lista", "📋 Listar nomes"), BotCommand("buscar", "🔎 Procurar atriz")]
    await application.bot.set_my_commands(vip_commands, scope=BotCommandScopeChat(chat_id=VIP_GROUP_ID))
    main_admin_commands = [
        BotCommand("comandos", "📖 Listar comandos"), BotCommand("painel", "📊 Painel de Controlo"),
        BotCommand("falar", "💬 Enviar mensagem a cliente"), BotCommand("info", "🔍 Inspecionar utilizador"),
    ]
    await application.bot.set_my_commands(main_admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_GROUP_ID))
    log_admin_commands = [
        BotCommand("comandos", "📖 Listar comandos"), BotCommand("stats", "📊 Ver estatísticas"),
        BotCommand("relatorio", "📈 Relatório diário"), BotCommand("expirados", "⌛ Listar expirados")
    ]
    await application.bot.set_my_commands(log_admin_commands, scope=BotCommandScopeChat(chat_id=LOG_GROUP_ID))
    storage_commands = [
        BotCommand("addmedia", "➕ Adicionar mídias"), BotCommand("remover_atriz", "🗑️ Remover atriz"),
        BotCommand("sincronizar", "🔄 Recarregar catálogo"), BotCommand("updatedurations", "⏱️ Atualizar duração")
    ]
    await application.bot.set_my_commands(storage_commands, scope=BotCommandScopeChat(chat_id=STORAGE_CHANNEL_ID))

def main() -> None:
    setup_database()
    load_dynamic_configs()
    build_catalog_from_db()
    load_portfolio_cache()
    persistence = PicklePersistence(filepath=os.path.join(DB_FOLDER, "bot_persistence.pickle"))
    request_handler = HTTPXRequest(read_timeout=60.0, write_timeout=60.0, connect_timeout=10.0)
    application = Application.builder().token(TOKEN).request(request_handler).persistence(persistence).post_init(post_init).build()
    
    job_queue = application.job_queue
    # Alterado para não executar na inicialização
    job_queue.run_repeating(send_advertisement, interval=timedelta(hours=6), first=timedelta(seconds=10))
    job_queue.run_daily(check_renewal_reminders, time=datetime.strptime("10:00", "%H:%M").time())
    job_queue.run_daily(check_expirations, time=datetime.strptime("00:01", "%H:%M").time())
    job_queue.run_daily(send_discount_offers, time=datetime.strptime("11:00", "%H:%M").time())
    job_queue.run_repeating(sync_catalog_job, interval=timedelta(days=15))
    job_queue.run_repeating(send_tutorial_video, interval=timedelta(days=1), first=timedelta(seconds=15))
    job_queue.run_repeating(post_teaser_to_free_group, interval=timedelta(hours=5), first=timedelta(seconds=20))
    job_queue.run_daily(backup_database, time=datetime.strptime("03:00", "%H:%M").time(), name="daily_backup_job")
    job_queue.run_daily(send_daily_bulletin, time=datetime.strptime("00:00", "%H:%M").time())

    # --- NOVOS CONVERSATION HANDLERS ---
    falar_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("falar", falar_start),
            CallbackQueryHandler(pattern="^falar_com_user:", callback=callback_handler)
        ],
        states={
            AWAIT_TARGET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, falar_receive_id)],
            AWAIT_MESSAGE_TO_SEND: [MessageHandler(filters.TEXT & ~filters.COMMAND, falar_receive_message)],
        },
        fallbacks=[CommandHandler("cancelar", cancel_conversation)],
    )
    buscar_user_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(pattern="^painel_buscar_start$", callback=painel_buscar_user_start)],
        states={
            AWAIT_USER_ID_TO_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, painel_receive_user_id)],
        },
        fallbacks=[CommandHandler("cancelar", cancel_conversation)],
    )
    gerenciar_frases_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("gerenciarfrases", gerenciar_frases_start)],
        states={
            MANAGE_PHRASES_MENU: [CallbackQueryHandler(gerenciar_frases_menu)],
            AWAIT_PHRASE_TO_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phrase_to_add), CallbackQueryHandler(pattern="^back_to_phrase_menu$", callback=gerenciar_frases_start_from_callback)],
        },
        fallbacks=[CommandHandler("cancelar", cancel_conversation)],
    )

    start_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command_entry)],
        states={AWAITING_ANY_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_any_reply)]},
        fallbacks=[CommandHandler("cancelar", cancel_conversation)],
        conversation_timeout=timedelta(hours=1).total_seconds()
    )
    add_media_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addmedia", add_media_start)],
        states={
            SELECT_METHOD: [CallbackQueryHandler(select_add_method)],
            SELECT_ACTION: [CallbackQueryHandler(select_action)],
            AWAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_name)],
            AWAIT_TYPED_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_typed_name)],
            RECEIVING_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, receive_media), CommandHandler("salvar", save_media)],
        },
        fallbacks=[CommandHandler("cancelar", cancel_conversation)],
    )
    settutorial_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("settutorial", settutorial_start)],
        states={AWAIT_VIDEO: [MessageHandler(filters.VIDEO, receive_tutorial_video)]},
        fallbacks=[CommandHandler("cancelar", cancel_conversation)],
    )
    set_welcome_media_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("setboasvindas", set_welcome_start)],
        states={AWAIT_WELCOME_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, receive_welcome_media), CommandHandler("salvar", save_welcome_media)]},
        fallbacks=[CommandHandler("cancelar", cancel_conversation)],
    )
    send_message_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("mensagem", mensagem_start), CallbackQueryHandler(pattern="^painel_mensagem$", callback=mensagem_start_from_callback)],
        states={
            AWAIT_CONTENT: [MessageHandler(filters.TEXT | filters.PHOTO, receive_content)],
            AWAIT_BUTTON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_button)],
            AWAIT_CONFIRMATION: [CallbackQueryHandler(receive_confirmation)],
        },
        fallbacks=[CommandHandler("cancelar", cancel_conversation)],
    )
    adjust_days_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(pattern=r"^info_adjust_days_start:", callback=callback_handler)],
        states={AWAIT_DAYS_TO_ADJUST: [MessageHandler(filters.TEXT & ~filters.COMMAND, ajustar_dias_command)]},
        fallbacks=[CommandHandler("cancelar", cancel_conversation)], map_to_parent={ConversationHandler.END: -1}
    )

    application.add_handler(start_conv_handler)
    application.add_handler(add_media_conv_handler)
    application.add_handler(settutorial_conv_handler)
    application.add_handler(send_message_conv_handler)
    application.add_handler(adjust_days_conv_handler)
    application.add_handler(set_welcome_media_conv_handler)
    application.add_handler(falar_conv_handler)
    application.add_handler(buscar_user_conv_handler)
    application.add_handler(gerenciar_frases_conv_handler)
    
    command_handlers = {
        "status": status_command, "atrizes": atrizes_command, "previa": previa_command,
        "vip": vip_command, "lista": lista_command, "buscar": buscar_command,
        "comandos": comandos_command, "contarmidia": contar_midia_command, "anunciar": anunciar_command,
        "anunciaratriz": anunciar_atriz_command, "expirados": expirados_command, "remover": remover_command,
        "remover_atriz": remover_atriz_command, "sincronizar": sincronizar_command, "stats": stats_command,
        "setatrizteaser": set_teaser_actress_command, "relatorio": relatorio_command,
        "relatorio_engajamento": relatorio_engajamento_command,
        "postartutorial": postar_tutorial_command, "migrarvip": migrar_vip_command,
        "anunciarmigracao": anunciar_migracao_command, "oferta": lightning_offer_command,
        "updatedurations": updatedurations_command, "backup": backup_command, "desconto": desconto_command,
        "ajustar_dias": ajustar_dias_command, "verificar_jobs": verificar_jobs_command,
        "ban": ban_command, "unban": unban_command, "info": info_command, "painel": painel_command,
        "limpar_expirados": limpar_expirados_command, "setdesconto": set_desconto_command,
        "anunciartudo": anunciar_tudo_command,
    }
    for command, handler_func in command_handlers.items():
        application.add_handler(CommandHandler(command, handler_func))

    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_private_message), group=1)
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.PHOTO | filters.Document.ALL), comprovante_handler))
    application.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.CHAT_MEMBER))

    logger.info("Bot iniciado...")
    application.run_polling()

if __name__ == "__main__":
    main()


