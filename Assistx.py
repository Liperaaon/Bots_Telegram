# ---------------------------------------------------------
# 🤖 BOT FAQ ULTIMATE (PROFISSIONAL & OTIMIZADO V2)
# ---------------------------------------------------------
# INSTRUÇÕES DE CONFIGURAÇÃO PARA O CLIENTE:
# 1. Crie o bot no @BotFather e pegue o TOKEN.
# 2. Crie dois grupos no Telegram (um para Admins, um para Suporte).
# 3. Adicione o bot nesses grupos como ADMIN.
# 4. Use um bot como @userinfobot ou @idbot para pegar o ID dos grupos (começa com -100...).
# ---------------------------------------------------------

import logging
import os
import sqlite3
import shutil
import pytz
import csv
import io
import difflib
import asyncio
from datetime import datetime, time
from functools import wraps

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    InputMediaPhoto, 
    InputMediaVideo
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
    Defaults
)
from telegram.request import HTTPXRequest

# --- ÁREA DE CONFIGURAÇÃO (EDITAR AQUI) ---
TOKEN = "SEU_TOKEN_AQUI"              # Ex: "123456789:ABCdefGHIjkl..."
ADMIN_GROUP_ID = 0000000000           # ID do Grupo de Gestão/Admins (Ex: -100123456789)
SUPPORT_GROUP_ID = 0000000000         # ID do Grupo de Suporte (Ex: -100987654321)

TIMEZONE = "America/Sao_Paulo"        # Fuso horário do Bot

# Configuração de Logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Caminhos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "faq_data")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DB_PATH = os.path.join(DATA_DIR, "faq_bot_v3.db")

# Cache Global de Configurações (Para não ler disco toda hora)
SETTINGS_CACHE = {}

# Estados da Conversa
ADD_CATEGORY, ADD_QUESTION, ADD_ANSWER, ADD_MEDIA = range(4)
BROADCAST_MSG, BROADCAST_MEDIA = range(4, 6)
IN_SUPPORT_CHAT = range(6, 7) 
EDIT_SELECT_FIELD, EDIT_NEW_VALUE = range(7, 9)
CONFIG_NEW_VALUE, CONFIG_NEW_MEDIA = range(9, 11)

# --- BANCO DE DADOS & CACHE ---
def setup_database():
    """Inicializa o banco de dados SQLite, atualiza schema e carrega cache."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    
    # Otimização WAL (Write-Ahead Logging)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        print("🚀 [PERFORMANCE] Modo WAL ativado no SQLite.")
    except Exception as e:
        print(f"⚠️ [PERFORMANCE] Não foi possível ativar WAL: {e}")

    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS faq (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        media_id TEXT,
        media_type TEXT,
        views INTEGER DEFAULT 0
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        joined_date TEXT,
        is_banned INTEGER DEFAULT 0
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_tickets (
        user_id INTEGER PRIMARY KEY,
        admin_id INTEGER,
        admin_name TEXT,
        start_time TEXT
    )
    """)
    
    # Migração: garantir colunas novas se DB antigo
    try: cursor.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
    except: pass 

    defaults = [
        ('welcome_msg', "Olá, {name}! 👋\n\nSou seu assistente virtual. Selecione um tema ou digite sua dúvida:"),
        ('support_msg', "👨‍💻 **Atendimento Humano Iniciado**\n\nVocê está na fila. Aguarde, um atendente irá falar com você em breve.\n\n_Para sair, digite /encerrar_"),
        ('opening_hour', '09:00'),
        ('closing_hour', '18:00'),
        ('closed_msg', "🌙 **Estamos fora do horário comercial.**\nNosso horário é das {open} às {close}. Deixe sua mensagem e responderemos assim que retornarmos!"),
        ('welcome_media_id', ''),
        ('welcome_media_type', '')
    ]
    cursor.executemany("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", defaults)

    conn.commit()
    
    # Carregar Cache Inicial
    print("🔄 [SISTEMA] Carregando configurações para Memória RAM...")
    rows = cursor.execute("SELECT key, value FROM settings").fetchall()
    for key, val in rows:
        SETTINGS_CACHE[key] = val
        
    conn.close()
    print("✅ [SISTEMA] Banco de dados e Cache prontos.")

# --- SISTEMA DE CACHE ---
def get_setting(key):
    """Lê do Cache (RAM) em vez do Disco (DB)."""
    return SETTINGS_CACHE.get(key, "")

def set_setting(key, value):
    """Salva no DB e atualiza o Cache."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    # Atualiza RAM
    SETTINGS_CACHE[key] = value

# --- HELPERS ---
def is_user_banned(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return res and res[0] == 1

def check_operating_hours():
    # Usa cache, muito mais rápido
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).time()
    
    open_str = get_setting('opening_hour')
    close_str = get_setting('closing_hour')
    
    try:
        open_time = datetime.strptime(open_str, "%H:%M").time()
        close_time = datetime.strptime(close_str, "%H:%M").time()
        
        if open_time < close_time:
            return open_time <= now <= close_time
        else: 
            return open_time <= now or now <= close_time
    except:
        return True

# --- EXPORTAÇÃO ---
async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Gerando relatórios...")
    
    users_output = io.StringIO()
    writer = csv.writer(users_output)
    writer.writerow(['User ID', 'Nome', 'Username', 'Data Entrada', 'Banido?'])
    
    with sqlite3.connect(DB_PATH) as conn:
        users = conn.execute("SELECT user_id, first_name, username, joined_date, is_banned FROM users").fetchall()
        writer.writerows(users)
    users_output.seek(0)
    
    faq_output = io.StringIO()
    writer = csv.writer(faq_output)
    writer.writerow(['ID', 'Categoria', 'Pergunta', 'Resposta', 'Views'])
    
    with sqlite3.connect(DB_PATH) as conn:
        faqs = conn.execute("SELECT id, category, question, answer, views FROM faq").fetchall()
        writer.writerows(faqs)
    faq_output.seek(0)
    
    current_date = datetime.now().strftime('%d-%m')
    
    await context.bot.send_document(
        chat_id=ADMIN_GROUP_ID,
        document=io.BytesIO(users_output.getvalue().encode('utf-8')),
        filename=f"usuarios_{current_date}.csv",
        caption="📊 Relatório de Usuários"
    )
    
    await context.bot.send_document(
        chat_id=ADMIN_GROUP_ID,
        document=io.BytesIO(faq_output.getvalue().encode('utf-8')),
        filename=f"faq_conteudo_{current_date}.csv",
        caption="📝 Relatório de Conteúdo FAQ"
    )
    await admin_panel(update, context)

# --- BACKUP ---
async def perform_backup(context: ContextTypes.DEFAULT_TYPE):
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"faq_backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        shutil.copy(DB_PATH, backup_path)
        return True, backup_filename
    except Exception as e:
        return False, str(e)

async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    success, result = await perform_backup(context)
    if success:
        try: await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"💾 **Backup Automático:** `{result}`", parse_mode=ParseMode.MARKDOWN)
        except: pass

async def admin_backup_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Gerando backup...")
    success, result = await perform_backup(context)
    msg = f"✅ Backup: `{result}`" if success else f"❌ Erro: {result}"
    await update.callback_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    await admin_panel(update, context)

# --- COMANDO /SUPORTE (Manual Inteligente) ---
async def global_support_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # 1. Manual para o Grupo de SUPORTE
    if chat_id == SUPPORT_GROUP_ID:
        text = (
            "🚑 **MANUAL DO ATENDENTE (Suporte)**\n\n"
            "Este bot opera no modo **Híbrido**. Você tem duas formas de atender:\n\n"
            "⚡ **1. Modo Rápido (Multitarefa)**\n"
            "• Basta **RESPONDER** (Reply) a qualquer mensagem de um usuário aqui no grupo.\n"
            "• O bot envia sua resposta automaticamente para ele.\n"
            "• _Ideal para tirar dúvidas rápidas sem travar o bot._\n\n"
            "🔒 **2. Modo Foco (Assumir Ticket)**\n"
            "• Clique no botão **[🙋‍♂️ Assumir]** quando chegar um aviso.\n"
            "• O bot foca em você. Tudo que você digitar (sem responder) vai para o usuário.\n"
            "• _Ideal para atendimentos longos e complexos._\n\n"
            "⚙️ **Comandos Úteis:**\n"
            "• `/encerrar` - Fecha o ticket atual (libera o usuário).\n"
            "• `/ban` (respondendo à msg) - Bloqueia usuários tóxicos.\n"
            "• `/suporte` - Mostra esta mensagem."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    # 2. Manual para o Grupo de ADMIN (Gestão)
    elif chat_id == ADMIN_GROUP_ID:
        text = (
            "🛠 **MANUAL DO GESTOR (Admin)**\n\n"
            "Use o comando `/admin` para abrir o Painel Principal.\n\n"
            "📚 **Gerenciando o FAQ**\n"
            "• **Criar:** Cadastre categoria, pergunta, resposta e mídia (foto/vídeo).\n"
            "• **Editar:** Altere textos ou mídias de FAQs existentes.\n"
            "• **Excluir:** Remove FAQs obsoletos.\n\n"
            "📢 **Broadcast (Avisos)**\n"
            "• Envia mensagens para **TODOS** os usuários do bot.\n"
            "• Suporta Texto, Foto e Vídeo.\n"
            "• _Possui sistema Anti-Flood para não bloquear o bot._\n\n"
            "⚙️ **Configurações Gerais**\n"
            "• Defina Horário de Abertura/Fechamento.\n"
            "• Personalize a mensagem de Boas-vindas.\n\n"
            "💾 **Dados e Backup**\n"
            "• **Exportar:** Baixa planilha Excel com todos os usuários e FAQs.\n"
            "• **Backup:** Cria uma cópia de segurança do Banco de Dados."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    else:
        await update.message.reply_text("⚠️ Este comando só funciona nos grupos de Staff.")

# --- DECORATORS ---
def admin_required(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_chat.id != ADMIN_GROUP_ID:
            if update.message and update.message.chat.type == 'private':
                 await update.message.reply_text("⛔ Acesso restrito.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

async def post_init(application: Application):
    msg = "🚀 **Bot FAQ Iniciado!**\n✅ Cache RAM Ativo\n✅ Anti-Flood Ativo\n✅ Suporte Híbrido"
    try: await application.bot.send_message(chat_id=ADMIN_GROUP_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
    except: pass
    
    kb_admin = [
        [InlineKeyboardButton("➕ Criar FAQ", callback_data="admin_add"), InlineKeyboardButton("✏️ Editar FAQ", callback_data="admin_edit_menu")],
        [InlineKeyboardButton("🗑 Excluir FAQ", callback_data="admin_del_menu"), InlineKeyboardButton("⚙️ Configs", callback_data="admin_config_menu")],
        [InlineKeyboardButton("📢 Broadcast (Mídia)", callback_data="admin_broadcast"), InlineKeyboardButton("📊 Exportar Dados", callback_data="admin_export")],
        [InlineKeyboardButton("💾 Backup", callback_data="admin_backup"), InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")]
    ]
    txt_admin = "🛠 **Painel FAQ Ultimate**\nGerencie tudo por aqui."
    try: await application.bot.send_message(chat_id=ADMIN_GROUP_ID, text=txt_admin, reply_markup=InlineKeyboardMarkup(kb_admin), parse_mode=ParseMode.MARKDOWN)
    except: pass

# --- FUNÇÕES DE USUÁRIO ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == ADMIN_GROUP_ID:
        await admin_panel(update, context)
        return
    
    if update.effective_chat.id == SUPPORT_GROUP_ID:
        await update.message.reply_text("👋 Bot de Suporte Ativo!\nUse /ajuda para ver os comandos.")
        return
    
    user = update.effective_user
    if is_user_banned(user.id): return 

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR IGNORE INTO users (user_id, first_name, username, joined_date, is_banned) VALUES (?, ?, ?, ?, 0)",
                (user.id, user.first_name, user.username, datetime.now().isoformat()))
    except: pass
    
    # Verifica ticket aberto
    with sqlite3.connect(DB_PATH) as conn:
        in_ticket = conn.execute("SELECT admin_name FROM active_tickets WHERE user_id = ?", (user.id,)).fetchone()
    
    if in_ticket:
        await update.message.reply_text(f"⚠️ Você já tem um atendimento aberto com **{in_ticket[0]}**.\n\nDigite sua mensagem aqui ou use /encerrar para sair.")
        return IN_SUPPORT_CHAT

    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_PATH) as conn:
        categories = conn.execute("SELECT DISTINCT category FROM faq ORDER BY category").fetchall()
    
    keyboard = []
    row = []
    for cat in categories:
        cat_name = cat[0]
        row.append(InlineKeyboardButton(f"📂 {cat_name}", callback_data=f"cat:{cat_name}"))
        if len(row) == 2: keyboard.append(row); row = []
    if row: keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("💬 Falar com Humano", callback_data="start_support")])
    
    welcome_text = get_setting('welcome_msg').format(name=update.effective_user.first_name)
    welcome_media_id = get_setting('welcome_media_id')
    welcome_media_type = get_setting('welcome_media_type')
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if welcome_media_id:
        if update.callback_query:
            try: await update.callback_query.message.delete()
            except: pass
            if welcome_media_type == 'photo': await context.bot.send_photo(update.effective_chat.id, welcome_media_id, caption=welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            else: await context.bot.send_video(update.effective_chat.id, welcome_media_id, caption=welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:
            if welcome_media_type == 'photo': await update.message.reply_photo(welcome_media_id, caption=welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            else: await update.message.reply_video(welcome_media_id, caption=welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        if update.callback_query:
            try: 
                await update.callback_query.edit_message_text(text=welcome_text, reply_markup=reply_markup)
            except: 
                try: await update.callback_query.message.delete()
                except: pass
                await update.callback_query.message.chat.send_message(welcome_text, reply_markup=reply_markup)
        else: await update.message.reply_text(welcome_text, reply_markup=reply_markup)

# --- BUSCA INTELIGENTE ---
async def handle_fuzzy_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Se estiver em ticket, ignora (deixa o handler de chat pegar)
    with sqlite3.connect(DB_PATH) as conn:
        in_ticket = conn.execute("SELECT 1 FROM active_tickets WHERE user_id = ?", (user_id,)).fetchone()
    if in_ticket: return

    if update.effective_chat.id in [ADMIN_GROUP_ID, SUPPORT_GROUP_ID]: return
    if is_user_banned(user_id): return

    user_text = update.message.text.lower().strip()
    
    with sqlite3.connect(DB_PATH) as conn:
        all_faqs = conn.execute("SELECT id, question FROM faq").fetchall()
    
    questions_text = [q[1].lower() for q in all_faqs]
    
    matches = difflib.get_close_matches(user_text, questions_text, n=3, cutoff=0.4)
    
    if matches:
        keyboard = []
        for match in matches:
            for fid, fquest in all_faqs:
                if fquest.lower() == match:
                    keyboard.append([InlineKeyboardButton(f"❓ {fquest}", callback_data=f"ans:{fid}")])
                    break
        keyboard.append([InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")])
        await update.message.reply_text(f"🤔 Você quis dizer...", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        # Busca simples por contem
        results = []
        for fid, fquest in all_faqs:
            if user_text in fquest.lower(): results.append((fid, fquest))
        
        if results:
            keyboard = [[InlineKeyboardButton(f"❓ {q}", callback_data=f"ans:{i}")] for i, q in results[:3]]
            keyboard.append([InlineKeyboardButton("🏠 Menu Principal", callback_data="main_menu")])
            await update.message.reply_text("🔍 Encontrei estes tópicos:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(
                "😕 Não entendi. Tente usar palavras-chave ou abra o menu.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Abrir Menu", callback_data="main_menu")]])
            )

# --- FLUXO DE SUPORTE ---
async def start_support_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if is_user_banned(user.id):
        await query.edit_message_text("🚫 Você foi bloqueado pelo suporte.")
        return ConversationHandler.END

    with sqlite3.connect(DB_PATH) as conn:
        ticket = conn.execute("SELECT admin_name FROM active_tickets WHERE user_id = ?", (user.id,)).fetchone()
    
    if ticket:
        await query.edit_message_text(f"⚠️ Você já tem um atendimento aberto com **{ticket[0]}**.\n\nEnvie sua mensagem abaixo.")
        return IN_SUPPORT_CHAT

    msg = get_setting('support_msg')
    
    if not check_operating_hours():
        closed_warning = get_setting('closed_msg').format(
            open=get_setting('opening_hour'), 
            close=get_setting('closing_hour')
        )
        msg = f"{closed_warning}\n\n{msg}" 

    try: await query.message.delete()
    except: pass
    
    await query.message.chat.send_message(msg, parse_mode=ParseMode.MARKDOWN)
    
    admin_text = (
        f"🆕 **NOVO CLIENTE NA FILA**\n"
        f"👤 {user.first_name} (ID: `{user.id}`)\n"
        f"🔗 @{user.username or 'SemUser'}\n\n"
        f"👇 Clique para assumir (Foco) ou Responda a mensagem (Rápido)."
    )
    keyboard = [[InlineKeyboardButton("🙋‍♂️ Assumir Atendimento", callback_data=f"claim_usr:{user.id}")]]
    
    await context.bot.send_message(
        chat_id=SUPPORT_GROUP_ID,
        text=admin_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return IN_SUPPORT_CHAT

# --- CHAT: USUÁRIO -> ADMIN (COM MAPA DE REPLY) ---
async def user_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.message.text == '/encerrar':
        await close_ticket_user(update, context)
        return ConversationHandler.END

    with sqlite3.connect(DB_PATH) as conn:
        ticket = conn.execute("SELECT admin_id, admin_name FROM active_tickets WHERE user_id = ?", (user.id,)).fetchone()
    
    admin_name_display = ticket[1] if ticket else "Fila de Espera"
    
    # UX: Avisar usuário que foi enviado
    await context.bot.send_chat_action(chat_id=SUPPORT_GROUP_ID, action=ChatAction.TYPING)
    
    # Enviar para o grupo
    header = f"👤 **{user.first_name}** (Em: {admin_name_display}):"
    
    try:
        sent_msg = None
        if update.message.text:
            sent_msg = await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                text=f"{header}\n{update.message.text}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            sent_msg = await context.bot.copy_message(
                chat_id=SUPPORT_GROUP_ID,
                from_chat_id=user.id,
                message_id=update.message.id,
                caption=f"{header}\n{update.message.caption or ''}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # --- MÁGICA DO REPLY ---
        # Salvamos qual ID de usuário pertence a essa mensagem no grupo
        # Isso permite que o admin responda a essa mensagem específica e o bot saiba pra quem mandar
        if sent_msg:
            # Usamos context.bot_data para persistência em memória durante o runtime
            context.bot_data[f"msg_{sent_msg.message_id}"] = user.id
            
    except Exception as e:
        logger.error(f"Erro ao relay user->admin: {e}")
    
    return IN_SUPPORT_CHAT

# --- ADMIN: ASSUMIR TICKET ---
async def handle_claim_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    admin = update.effective_user
    user_id = int(user_id)
    
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute("SELECT admin_name FROM active_tickets WHERE user_id = ?", (user_id,)).fetchone()
        if existing:
            await update.callback_query.answer(f"⚠️ {existing[0]} já está atendendo!", show_alert=True)
            return

        conn.execute(
            "INSERT OR REPLACE INTO active_tickets (user_id, admin_id, admin_name, start_time) VALUES (?, ?, ?, ?)",
            (user_id, admin.id, admin.first_name, datetime.now().isoformat())
        )
        conn.commit()
    
    new_text = f"{update.callback_query.message.text}\n\n✅ **Assumido por:** {admin.first_name}"
    try: await update.callback_query.edit_message_text(text=new_text, parse_mode=ParseMode.MARKDOWN, reply_markup=None)
    except: pass
    
    await context.bot.send_message(
        chat_id=SUPPORT_GROUP_ID,
        text=f"🔒 **{admin.first_name}** assumiu o chat com {user_id}.\nDigite aqui para responder."
    )
    try: await context.bot.send_message(chat_id=user_id, text=f"👨‍💻 **{admin.first_name}** iniciou seu atendimento.")
    except: pass

# --- ADMIN -> USUÁRIO (LÓGICA HÍBRIDA) ---
async def support_group_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != SUPPORT_GROUP_ID: return
    if update.message.text and update.message.text.startswith('/'): return
    
    admin = update.effective_user
    target_user_id = None
    
    # 1. Verifica se é um REPLY (Prioridade Alta - Permite Multitarefa)
    if update.message.reply_to_message:
        replied_msg_id = update.message.reply_to_message.message_id
        # Tenta recuperar o ID do usuário do mapa salvo
        target_user_id = context.bot_data.get(f"msg_{replied_msg_id}")
        
        if not target_user_id:
            # Se não achou no mapa, tenta ver se foi um aviso de "Novo Cliente" que tem ID no texto
            # Isso é um fallback inteligente
            try:
                txt = update.message.reply_to_message.text or ""
                if "ID:" in txt:
                    # Extrai ID do texto rudimentarmente
                    import re
                    found = re.search(r"ID: `(\d+)`", txt)
                    if found: target_user_id = int(found.group(1))
            except: pass

    # 2. Se não for Reply, usa o modo "Chat Limpo" (Ticket Ativo)
    if not target_user_id:
        with sqlite3.connect(DB_PATH) as conn:
            ticket = conn.execute("SELECT user_id FROM active_tickets WHERE admin_id = ? ORDER BY start_time DESC LIMIT 1", (admin.id,)).fetchone()
        if ticket:
            target_user_id = ticket[0]

    # Envio da mensagem
    if target_user_id:
        try:
            # UX: Mostra digitando pro usuário
            await context.bot.send_chat_action(chat_id=target_user_id, action=ChatAction.TYPING)
            
            if update.message.text:
                await context.bot.send_message(chat_id=target_user_id, text=update.message.text)
            else:
                await context.bot.copy_message(
                    chat_id=target_user_id,
                    from_chat_id=SUPPORT_GROUP_ID,
                    message_id=update.message.id,
                    caption=update.message.caption
                )
            
            # Reação de confirmação pro Admin
            try: await update.message.set_reaction(reaction="👍")
            except: pass
            
        except Exception as e:
            await update.message.reply_text(f"❌ Falha ao enviar para {target_user_id}. (Bloqueou o bot?)")
    else:
        # Só avisa se for um reply explicito que falhou, pra não poluir o grupo
        if update.message.reply_to_message:
            await update.message.reply_text("⚠️ Não consegui identificar o usuário dessa mensagem. Tente usar /encerrar ou aguarde novo contato.")

# --- COMANDO ENCERRAR ---
async def close_ticket_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    is_admin = chat_id == SUPPORT_GROUP_ID
    target_user_id = None
    
    with sqlite3.connect(DB_PATH) as conn:
        if is_admin:
            # Admin fecha o ticket ativo dele
            res = conn.execute("SELECT user_id FROM active_tickets WHERE admin_id = ?", (user_id,)).fetchone()
            if res: target_user_id = res[0]
        else:
            # Usuário fecha o próprio
            res = conn.execute("SELECT user_id FROM active_tickets WHERE user_id = ?", (user_id,)).fetchone()
            if res: target_user_id = user_id

        if target_user_id:
            conn.execute("DELETE FROM active_tickets WHERE user_id = ?", (target_user_id,))
            conn.commit()
            
            try:
                await context.bot.send_message(chat_id=target_user_id, text="✅ **Atendimento Encerrado.**\nObrigado!", parse_mode=ParseMode.MARKDOWN)
                await show_main_menu(update, context)
            except: pass
            
            if is_admin:
                await update.message.reply_text(f"✅ Ticket {target_user_id} fechado.")
            else:
                await context.bot.send_message(chat_id=SUPPORT_GROUP_ID, text=f"ℹ️ Usuário {target_user_id} encerrou o chat.")
            return ConversationHandler.END
        else:
            await update.message.reply_text("⚠️ Nenhum ticket ativo.")

async def close_ticket_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await close_ticket_command(update, context)
    return ConversationHandler.END

# --- BROADCAST OTIMIZADO (ANTI-FLOOD) ---
async def admin_send_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_text'] = update.message.text
    await update.message.reply_text(
        "Texto salvo! Envie MÍDIA ou /enviar.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Enviar só Texto", callback_data="bc_send_text")]])
    )
    return BROADCAST_MEDIA

async def admin_broadcast_media_or_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = context.user_data.get('broadcast_text', '')
    if (update.message and update.message.text == '/enviar') or (update.callback_query and update.callback_query.data == "bc_send_text"):
        if update.callback_query: await update.callback_query.answer()
        return await execute_broadcast(update, context, txt, None, None)

    media_id, media_type = None, None
    if update.message.photo: media_id, media_type = update.message.photo[-1].file_id, 'photo'
    elif update.message.video: media_id, media_type = update.message.video.file_id, 'video'
    
    if media_id:
        return await execute_broadcast(update, context, txt, media_id, media_type)
    
    await update.message.reply_text("❌ Mídia inválida.")
    return BROADCAST_MEDIA

async def execute_broadcast(update, context, text, media_id, media_type):
    with sqlite3.connect(DB_PATH) as conn:
        users = conn.execute("SELECT user_id FROM users").fetchall()
    
    origin = update.message if update.message else update.callback_query.message
    await origin.reply_text(f"🚀 Enviando para {len(users)} usuários (Modo Seguro)...")
    
    count = 0
    # OTIMIZAÇÃO: Intervalo para evitar Flood Wait
    for i, u in enumerate(users):
        try:
            if media_id:
                if media_type == 'photo': await context.bot.send_photo(u[0], media_id, caption=f"🔔 **Aviso:**\n\n{text}", parse_mode=ParseMode.MARKDOWN)
                else: await context.bot.send_video(u[0], media_id, caption=f"🔔 **Aviso:**\n\n{text}", parse_mode=ParseMode.MARKDOWN)
            else:
                await context.bot.send_message(u[0], f"🔔 **Aviso:**\n\n{text}", parse_mode=ParseMode.MARKDOWN)
            count += 1
            
            # Anti-Flood: Pausa a cada 20 mensagens
            if i % 20 == 0: await asyncio.sleep(1.0)
            
        except Exception: pass 
    
    await origin.reply_text(f"✅ Finalizado: {count}/{len(users)}")
    await admin_panel(update, context)
    return ConversationHandler.END

# --- NAVEGAÇÃO E HANDLERS ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("claim_usr:"): return await handle_claim_ticket(update, context, data.split(":")[1])
    if query.data != "bc_send_text": await query.answer()

    if data == "admin_refresh": await admin_panel(update, context)
    elif data == "admin_stats": await show_stats(update, context)
    elif data == "admin_add": 
        await query.message.reply_text("📝 **Adicionar FAQ**\nEnvie a **CATEGORIA**:")
        return ADD_CATEGORY
    elif data == "admin_del_menu": await show_delete_menu(update, context)
    elif data == "admin_edit_menu": await show_edit_menu(update, context)
    elif data == "admin_config_menu": await show_config_menu(update, context)
    elif data == "admin_broadcast":
        await query.message.reply_text("📢 **Broadcast**\nEnvie o TEXTO:")
        return BROADCAST_MSG
    elif data == "admin_backup": await admin_backup_manual(update, context)
    elif data == "admin_export": await export_data(update, context)
    
    elif data.startswith("del_faq:"): await delete_faq(update, context, data.split(":")[1])
    elif data.startswith("edit_faq:"): await show_edit_faq_details(update, context, data.split(":")[1])
    elif data.startswith("conf_edit:"): return await start_config_edit(update, context, data.split(":")[1])
    elif data == "conf_media_welcome": return await start_config_media_edit(update, context)
    elif data.startswith("do_edit:"): return await start_faq_field_edit(update, context, data)

    elif data.startswith("cat:"): await show_questions(query, data.split(":")[1])
    elif data.startswith("ans:"): await show_answer(query, int(data.split(":")[1]))
    elif data == "main_menu": await show_main_menu(update, context)
    elif data == "start_support": return await start_support_flow(update, context)

    return ConversationHandler.END

async def show_questions(query, category):
    with sqlite3.connect(DB_PATH) as conn: questions = conn.execute("SELECT id, question FROM faq WHERE category = ?", (category,)).fetchall()
    keyboard = [[InlineKeyboardButton(f"❓ {q[1]}", callback_data=f"ans:{q[0]}")] for q in questions]
    keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="main_menu")])
    try: await query.message.delete()
    except: pass
    await query.message.chat.send_message(f"📂 **{category}**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def show_answer(query, faq_id):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT question, answer, category, media_id, media_type FROM faq WHERE id = ?", (faq_id,)).fetchone()
        conn.execute("UPDATE faq SET views = views + 1 WHERE id = ?", (faq_id,))
        conn.commit()
    if not res: return
    q, a, c, mid, mtype = res
    kb = [[InlineKeyboardButton("🔙 Voltar", callback_data=f"cat:{c}"), InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]]
    txt = f"❓ **{q}**\n\n✅ {a}"
    try: await query.message.delete()
    except: pass
    if mid:
        if mtype == 'photo': await query.message.chat.send_photo(mid, caption=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
        else: await query.message.chat.send_video(mid, caption=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else: await query.message.chat.send_message(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

@admin_required
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("➕ Criar FAQ", callback_data="admin_add"), InlineKeyboardButton("✏️ Editar FAQ", callback_data="admin_edit_menu")],
        [InlineKeyboardButton("🗑 Excluir FAQ", callback_data="admin_del_menu"), InlineKeyboardButton("⚙️ Configs", callback_data="admin_config_menu")],
        [InlineKeyboardButton("📢 Broadcast (Mídia)", callback_data="admin_broadcast"), InlineKeyboardButton("📊 Exportar Dados", callback_data="admin_export")],
        [InlineKeyboardButton("💾 Backup", callback_data="admin_backup"), InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")]
    ]
    txt = "🛠 **Painel FAQ Ultimate**\nGerencie tudo por aqui."
    if update.callback_query: await update.callback_query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else: await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# --- AUXILIARES ADMIN ---
async def show_config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("👋 Boas-vindas (Txt)", callback_data="conf_edit:welcome_msg"), InlineKeyboardButton("🖼 Boas-vindas (Mídia)", callback_data="conf_media_welcome")],
        [InlineKeyboardButton("👨‍💻 Msg Suporte", callback_data="conf_edit:support_msg"), InlineKeyboardButton("🌙 Msg Fechado", callback_data="conf_edit:closed_msg")],
        [InlineKeyboardButton("⏰ Abre às (HH:MM)", callback_data="conf_edit:opening_hour"), InlineKeyboardButton("⏰ Fecha às (HH:MM)", callback_data="conf_edit:closing_hour")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="admin_refresh")]
    ]
    await update.callback_query.edit_message_text("⚙️ **Configurações**", reply_markup=InlineKeyboardMarkup(kb))

async def show_edit_menu(update, context):
    with sqlite3.connect(DB_PATH) as conn: faqs = conn.execute("SELECT id, category, question FROM faq ORDER BY id DESC LIMIT 20").fetchall()
    kb = [[InlineKeyboardButton(f"✏️ {f[1]}: {f[2][:15]}...", callback_data=f"edit_faq:{f[0]}")] for f in faqs]
    kb.append([InlineKeyboardButton("🔙 Voltar", callback_data="admin_refresh")])
    await update.callback_query.edit_message_text("Selecione para EDITAR:", reply_markup=InlineKeyboardMarkup(kb))

async def show_delete_menu(update, context):
    with sqlite3.connect(DB_PATH) as conn: faqs = conn.execute("SELECT id, category, question FROM faq ORDER BY id DESC LIMIT 10").fetchall()
    kb = [[InlineKeyboardButton(f"🗑 {f[1]}: {f[2][:15]}...", callback_data=f"del_faq:{f[0]}")] for f in faqs]
    kb.append([InlineKeyboardButton("🔙 Voltar", callback_data="admin_refresh")])
    await update.callback_query.edit_message_text("Selecione para EXCLUIR:", reply_markup=InlineKeyboardMarkup(kb))

async def delete_faq(update, context, fid):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("DELETE FROM faq WHERE id = ?", (fid,)); conn.commit()
    await update.callback_query.answer("Deletado!"); await show_delete_menu(update, context)

async def show_edit_faq_details(update, context, fid):
    with sqlite3.connect(DB_PATH) as conn: res = conn.execute("SELECT category, question, answer FROM faq WHERE id = ?", (fid,)).fetchone()
    if not res: return
    c, q, a = res
    kb = [
        [InlineKeyboardButton("📂 Categoria", callback_data=f"do_edit:{fid}:category"), InlineKeyboardButton("❓ Pergunta", callback_data=f"do_edit:{fid}:question")],
        [InlineKeyboardButton("✅ Resposta", callback_data=f"do_edit:{fid}:answer"), InlineKeyboardButton("🖼 Mídia", callback_data=f"do_edit:{fid}:media")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="admin_edit_menu")]
    ]
    await update.callback_query.edit_message_text(f"📝 **Editando FAQ #{fid}**\n\n{q}\n_{a[:50]}..._", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def start_faq_field_edit(update, context, data):
    _, fid, f = data.split(":")
    context.user_data['edit_id'] = fid; context.user_data['edit_field'] = f
    msg = f"Envie novo valor para **{f}**:"
    if f=='media': msg+="\n(Envie foto/vídeo ou /apagar)"
    await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
    return EDIT_NEW_VALUE

async def save_faq_edit(update, context):
    fid, f, val = context.user_data['edit_id'], context.user_data['edit_field'], update.message.text
    with sqlite3.connect(DB_PATH) as conn:
        if f=='media':
            if val=='/apagar': conn.execute("UPDATE faq SET media_id=NULL, media_type=NULL WHERE id=?", (fid,))
            elif update.message.photo: conn.execute("UPDATE faq SET media_id=?, media_type='photo' WHERE id=?", (update.message.photo[-1].file_id, fid))
            elif update.message.video: conn.execute("UPDATE faq SET media_id=?, media_type='video' WHERE id=?", (update.message.video.file_id, fid))
        else: conn.execute(f"UPDATE faq SET {f}=? WHERE id=?", (val, fid))
        conn.commit()
    await update.message.reply_text("✅ Salvo!"); await show_edit_faq_details(update, context, fid)
    return ConversationHandler.END

async def start_config_edit(update, context, key):
    context.user_data['conf_key'] = key
    await update.callback_query.edit_message_text(f"📝 Editando: `{key}`\nValor atual: {get_setting(key)}\n\nEnvie novo valor:", parse_mode=ParseMode.MARKDOWN)
    return CONFIG_NEW_VALUE

async def save_config_edit(update, context):
    set_setting(context.user_data['conf_key'], update.message.text)
    await update.message.reply_text("✅ Config salva!"); await admin_panel(update, context)
    return ConversationHandler.END

async def start_config_media_edit(update, context):
    await update.callback_query.edit_message_text("Envie FOTO/VÍDEO de boas-vindas (ou /apagar):")
    return CONFIG_NEW_MEDIA

async def save_config_media_edit(update, context):
    if update.message.text=='/apagar': set_setting('welcome_media_id',''); set_setting('welcome_media_type','')
    elif update.message.photo: set_setting('welcome_media_id',update.message.photo[-1].file_id); set_setting('welcome_media_type','photo')
    elif update.message.video: set_setting('welcome_media_id',update.message.video.file_id); set_setting('welcome_media_type','video')
    await update.message.reply_text("✅ Mídia salva!"); await admin_panel(update, context)
    return ConversationHandler.END

async def admin_add_cat(update, context): context.user_data['new_cat']=update.message.text; await update.message.reply_text("Envie a PERGUNTA:"); return ADD_QUESTION
async def admin_add_quest(update, context): context.user_data['new_quest']=update.message.text; await update.message.reply_text("Envie a RESPOSTA:"); return ADD_ANSWER
async def admin_add_ans(update, context): context.user_data['new_ans']=update.message.text; await update.message.reply_text("Envie FOTO/VIDEO (ou /pular):"); return ADD_MEDIA
async def admin_add_media(update, context):
    mid, mtype = None, None
    if update.message.photo: mid, mtype = update.message.photo[-1].file_id, 'photo'
    elif update.message.video: mid, mtype = update.message.video.file_id, 'video'
    d = context.user_data
    with sqlite3.connect(DB_PATH) as conn: conn.execute("INSERT INTO faq (category, question, answer, media_id, media_type) VALUES (?,?,?,?,?)", (d['new_cat'], d['new_quest'], d['new_ans'], mid, mtype)); conn.commit()
    await update.message.reply_text("✅ FAQ Criada!"); await admin_panel(update, context); return ConversationHandler.END
async def admin_skip_media(update, context): return await admin_add_media(update, context)

async def cancel(update, context): await update.message.reply_text("Cancelado."); return ConversationHandler.END
async def show_stats(update, context): await admin_panel(update, context) 

# --- MAIN ---
def main():
    setup_database()
    
    # Validação Básica
    if "SEU_TOKEN_AQUI" in TOKEN:
        print("❌ ERRO: Você precisa configurar o TOKEN no arquivo bot.py antes de rodar.")
        return

    request_handler = HTTPXRequest(connection_pool_size=10, read_timeout=20.0, write_timeout=20.0, connect_timeout=10.0)
    
    app = Application.builder().token(TOKEN).request(request_handler).defaults(Defaults(parse_mode=ParseMode.MARKDOWN)).post_init(post_init).build()

    app.job_queue.run_daily(auto_backup_job, time=time(hour=0, minute=0, second=0, tzinfo=pytz.timezone(TIMEZONE)))

    # Handlers Admin
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern="^admin_add$")],
        states={ADD_CATEGORY:[MessageHandler(filters.TEXT, admin_add_cat)], ADD_QUESTION:[MessageHandler(filters.TEXT, admin_add_quest)], ADD_ANSWER:[MessageHandler(filters.TEXT, admin_add_ans)], ADD_MEDIA:[MessageHandler(filters.PHOTO|filters.VIDEO, admin_add_media), CommandHandler("pular", admin_skip_media)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern="^admin_broadcast$")],
        states={
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_send_broadcast_text)],
            BROADCAST_MEDIA: [MessageHandler(filters.ALL & ~filters.COMMAND, admin_broadcast_media_or_send), CallbackQueryHandler(admin_broadcast_media_or_send, pattern="bc_send_text")]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern="^do_edit:")],
        states={EDIT_NEW_VALUE: [MessageHandler(filters.TEXT|filters.PHOTO|filters.VIDEO, save_faq_edit)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern="^conf_edit:"), CallbackQueryHandler(handle_callback, pattern="^conf_media_welcome")],
        states={CONFIG_NEW_VALUE:[MessageHandler(filters.TEXT, save_config_edit)], CONFIG_NEW_MEDIA:[MessageHandler(filters.ALL, save_config_media_edit)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # Handler do Suporte (Usuário)
    support_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern="^start_support$")],
        states={IN_SUPPORT_CHAT: [MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO, user_chat_message)]},
        fallbacks=[CommandHandler("cancelar", close_ticket_user), CommandHandler("encerrar", close_ticket_user)],
    )
    app.add_handler(support_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("ajuda", global_support_guide)) # Alias
    app.add_handler(CommandHandler("suporte", global_support_guide)) # Novo comando principal
    app.add_handler(CommandHandler("encerrar", close_ticket_command))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Handler do GRUPO DE SUPORTE (Otimizado)
    app.add_handler(MessageHandler(filters.Chat(SUPPORT_GROUP_ID), support_group_chat_handler))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_fuzzy_search))

    print("\n" + "="*50)
    print("🚀 BOT FAQ ULTIMATE INICIADO COM SUCESSO!")
    print("⚡ OTIMIZAÇÕES ATIVAS: Cache, Anti-Flood, WAL")
    print("="*50 + "\n")
    
    app.run_polling()

if __name__ == "__main__":
    main()