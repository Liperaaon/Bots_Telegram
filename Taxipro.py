# -----------------------------------------------------------
# 🚖 Bot Taxi - Sistema de Gestão de Corridas e Rastreamento
# 💻 Desenvolvido por: Prime Studios
# 📅 Versão: 3.3 (Versão de Venda)
# -----------------------------------------------------------

import logging
import sqlite3
import os
from datetime import datetime, timedelta
import pytz
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    TypeHandler,
    PicklePersistence,
)
from telegram.error import BadRequest

# --- ÁREA DE CONFIGURAÇÃO DO COMPRADOR ---
# Instruções:
# 1. Crie um bot no @BotFather e cole o TOKEN abaixo.
# 2. Crie um Grupo no Telegram, adicione o bot como ADMIN.
# 3. Rode o bot e digite /id no grupo para pegar o número (ex: -100...) e cole em ID_GRUPO_ADMIN.

TOKEN = "INSIRA_SEU_TOKEN_AQUI"

# IDs dos Grupos (Deve começar com -100 se for Supergrupo)
ID_GRUPO_ADMIN = "INSIRA_ID_DO_GRUPO_ADMIN_AQUI" 
ID_GRUPO_RASTREAMENTO = "INSIRA_ID_DO_GRUPO_RASTREAMENTO_AQUI" # Pode ser o mesmo do Admin se não tiver um separado

TIMEZONE = "America/Sao_Paulo"
DB_FILE = "taxi_database.db"

# Estados para o Menu de Configuração
CONFIG_MENU, AWAIT_NEW_KM_PRICE, AWAIT_MODE_SELECTION, AWAIT_CAR_MODEL, AWAIT_CAR_PLATE, AWAIT_PIX_KEY = range(6)

# Variável Global
last_driver_location = None

# Configuração de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- TEMPLATES DE TEXTO ---
TEXT_TEMPLATES = {
    'particular': {
        'welcome': "👋 Olá, *{name}*!\n\nSou seu **Motorista Particular Digital**.\nToque nos botões abaixo para começar.",
        'request_btn': "🚗 Chamar Motorista",
        'history_btn': "📜 Meus Pedidos",
        'support_btn': "📞 Falar Comigo",
        'support_msg': "📱 **Contato Direto**\n\nPara falar comigo agora, ligue ou mande WhatsApp:\n📞 **(XX) 99999-9999**",
        'off_duty': "😴 **Motorista em Descanso**\n\nOlá! No momento encerrei meu expediente.\n\nPor favor, tente novamente mais tarde ou agende pelo WhatsApp."
    },
    'empresa': {
        'welcome': "👋 Olá, *{name}*!\n\nBem-vindo à Central do *Táxi VIP*.\nNossa frota está pronta. O que deseja?",
        'request_btn': "🚖 Solicitar Táxi",
        'history_btn': "📜 Histórico",
        'support_btn': "📞 Central de Atendimento",
        'support_msg': "🏢 **Central de Operações**\n\nNossa equipe está disponível 24h:\n📞 **(XX) 3333-3333**",
        'off_duty': "⛔ **Central Fechada**\n\nNosso horário de atendimento encerrou.\nEstamos indisponíveis para novas corridas no momento."
    }
}

# --- BANCO DE DADOS ---
def setup_database():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER UNIQUE, first_name TEXT, username TEXT, joined_at TEXT)")
        
        # Atualizações de Tabela (Schema Migration)
        try:
            cursor.execute("ALTER TABLE rides ADD COLUMN rating INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass
        
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass
            
        cursor.execute("CREATE TABLE IF NOT EXISTS rides (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, details TEXT, driver_name TEXT, price REAL DEFAULT 0, status TEXT, rating INTEGER DEFAULT 0, created_at TEXT, completed_at TEXT, FOREIGN KEY(user_id) REFERENCES users(telegram_id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        # Configurações padrão
        defaults = {
            'price_per_km': '5.00',
            'bot_mode': 'empresa',
            'driver_car': 'Modelo não definido',
            'driver_plate': 'SEM-PLACA',
            'pix_key': 'Chave não configurada',
            'is_on_duty': '1'
        }
        for key, val in defaults.items():
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
        conn.commit()

# --- HELPERS ---
def admin_required(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Validação em chat privado
        if update.effective_chat.type == 'private':
            try:
                # Tenta verificar se o usuário é membro do grupo Admin configurado
                # Nota: Isso falhará se ID_GRUPO_ADMIN não estiver configurado corretamente
                member = await context.bot.get_chat_member(ID_GRUPO_ADMIN, user_id)
                if member.status not in ("creator", "administrator", "member"):
                    await update.message.reply_text("⛔ Acesso negado. Você não faz parte da equipe.")
                    return
            except BadRequest as e:
                logger.error(f"ERRO DE PERMISSÃO: {e}")
                await update.message.reply_text(f"⚠️ Erro ao verificar permissões no grupo ADMIN. Verifique se o ID_GRUPO_ADMIN está correto no código.")
                return
            except Exception:
                return

        # Validação em grupos (deve ser o grupo admin correto)
        elif str(chat_id) != ID_GRUPO_ADMIN:
             print(f"⚠️ AVISO: Comando ignorado. ID do Grupo ({chat_id}) não bate com ID_GRUPO_ADMIN configurado.")
             return

        return await func(update, context, *args, **kwargs)
    return wrapped

def db_register_user(user):
    now = datetime.now(pytz.timezone(TIMEZONE)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO users (telegram_id, first_name, username, joined_at) VALUES (?, ?, ?, ?) ON CONFLICT(telegram_id) DO UPDATE SET first_name=excluded.first_name, username=excluded.username", (user.id, user.first_name, user.username, now))

def db_is_blocked(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        res = conn.execute("SELECT is_blocked FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
        return res and res[0] == 1

def db_set_block_status(user_id, status):
    # status: 1 para bloquear, 0 para desbloquear
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("UPDATE users SET is_blocked = ? WHERE telegram_id = ?", (status, user_id))

def db_create_ride(user_id, details):
    now = datetime.now(pytz.timezone(TIMEZONE)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("INSERT INTO rides (user_id, details, status, created_at) VALUES (?, ?, 'pending', ?)", (user_id, details, now))
        return cursor.lastrowid

def db_update_ride(ride_id, status, price=None, driver=None, rating=None):
    with sqlite3.connect(DB_FILE) as conn:
        query = "UPDATE rides SET status = ?"
        params = [status]
        if price is not None:
            query += ", price = ?"
            params.append(price)
        if driver is not None:
            query += ", driver_name = ?"
            params.append(driver)
        if rating is not None:
            query += ", rating = ?"
            params.append(rating)
        if status == 'completed':
            now = datetime.now(pytz.timezone(TIMEZONE)).isoformat()
            query += ", completed_at = ?"
            params.append(now)
        query += " WHERE id = ?"
        params.append(ride_id)
        conn.execute(query, params)

def db_get_user_history(user_id, limit=5):
    with sqlite3.connect(DB_FILE) as conn:
        return conn.execute("SELECT id, details, price, created_at, status FROM rides WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()

def db_get_stats():
    now = datetime.now(pytz.timezone(TIMEZONE))
    day_str = now.strftime('%Y-%m-%d')
    month_str = now.strftime('%Y-%m')
    with sqlite3.connect(DB_FILE) as conn:
        day_rev = conn.execute("SELECT SUM(price), COUNT(*) FROM rides WHERE status='completed' AND completed_at LIKE ?", (f"{day_str}%",)).fetchone()
        month_rev = conn.execute("SELECT SUM(price), COUNT(*) FROM rides WHERE status='completed' AND completed_at LIKE ?", (f"{month_str}%",)).fetchone()
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        avg_rating = conn.execute("SELECT AVG(rating) FROM rides WHERE rating > 0").fetchone()[0]
    return {'day_val': day_rev[0] or 0, 'day_count': day_rev[1] or 0, 'month_val': month_rev[0] or 0, 'month_count': month_rev[1] or 0, 'users': total_users, 'rating': avg_rating or 5.0}

def db_get_setting(key):
    with sqlite3.connect(DB_FILE) as conn:
        res = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return res[0] if res else None

def db_set_setting(key, value):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

def get_ui_text(key, **kwargs):
    mode = db_get_setting('bot_mode') or 'empresa'
    template = TEXT_TEMPLATES.get(mode, TEXT_TEMPLATES['empresa']).get(key, "")
    return template.format(**kwargs)

def is_driver_on_duty():
    status = db_get_setting('is_on_duty')
    return status == '1' or status is None

# --- MIDDLEWARE ---
async def registrar_usuario_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and not update.effective_user.is_bot:
        try: db_register_user(update.effective_user)
        except: pass
    
    # DEBUGGER DE GRUPO
    if update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
        match_icon = "✅" if str(update.effective_chat.id) == ID_GRUPO_ADMIN else "❌"
        # print(f"ID CHECK: {update.effective_chat.id} | {match_icon}") 

async def get_chat_id_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title or "Privado"
    # Modificado para não expor o ID salvo no código para qualquer um, apenas validação
    is_correct = str(chat_id) == ID_GRUPO_ADMIN
    msg_status = "✅ ID Configurado Corretamente!" if is_correct else "❌ Este ID é diferente do configurado no bot.py"
    
    await update.message.reply_text(
        f"🆔 **Informações do Chat**\n\n"
        f"📝 Nome: {chat_title}\n"
        f"🔢 ID: `{chat_id}`\n\n"
        f"{msg_status}\n\n"
        f"_Copie o ID acima e cole na variável ID_GRUPO_ADMIN do bot.py se este for o grupo principal._", 
        parse_mode='Markdown'
    )

# --- COMANDOS DE ADMIN (BAN/UNBAN) ---
@admin_required
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_to_ban = None
    
    # Caso 1: Respondendo a uma mensagem do bot (pedido)
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        original_msg_id = update.message.reply_to_message.message_id
        dados = context.bot_data.get(original_msg_id)
        if dados:
            user_id_to_ban = dados['user_id']
        else:
            await update.message.reply_text("⚠️ Não encontrei os dados desse pedido na memória para banir.")
            return

    # Caso 2: Passando ID manualmente (/ban 123456)
    elif context.args:
        try:
            user_id_to_ban = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ ID inválido.")
            return
            
    if user_id_to_ban:
        db_set_block_status(user_id_to_ban, 1)
        await update.message.reply_text(f"⛔ **Usuário {user_id_to_ban} BANIDO!**\nEle não poderá mais solicitar corridas.")
    else:
        await update.message.reply_text("⚠️ Use respondendo a um pedido ou digite `/ban ID`.")

@admin_required
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        try:
            user_id = int(context.args[0])
            db_set_block_status(user_id, 0)
            await update.message.reply_text(f"✅ **Usuário {user_id} DESBLOQUEADO!**")
        except ValueError:
            await update.message.reply_text("⚠️ ID inválido.")
    else:
        await update.message.reply_text("⚠️ Digite o ID para desbloquear: `/unban 123456`")


# --- RASTREAMENTO CORE ---
async def capturar_localizacao_motorista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.location: return
    chat_id = update.effective_chat.id
    if str(chat_id) == ID_GRUPO_ADMIN or update.effective_chat.type == 'private':
        global last_driver_location
        last_driver_location = {'lat': message.location.latitude, 'lon': message.location.longitude, 'last_update': datetime.now()}
        if update.message and not context.job_queue.get_jobs_by_name("job_rastreio"):
            context.job_queue.run_repeating(enviar_pulso_rastreio, interval=120, first=10, name="job_rastreio") 
            try: await context.bot.send_message(chat_id=chat_id, text="✅ **Rastreamento Iniciado!**")
            except: pass

async def handle_edited_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.edited_message and update.edited_message.location:
        await capturar_localizacao_motorista(update, context)

async def enviar_pulso_rastreio(context: ContextTypes.DEFAULT_TYPE):
    global last_driver_location
    if not last_driver_location: return
    try:
        if (datetime.now() - last_driver_location['last_update']).seconds > 900:
            return

        await context.bot.send_location(chat_id=ID_GRUPO_RASTREAMENTO, latitude=last_driver_location['lat'], longitude=last_driver_location['lon'])
        hora_atual = datetime.now(pytz.timezone(TIMEZONE)).strftime("%H:%M")
        await context.bot.send_message(chat_id=ID_GRUPO_RASTREAMENTO, text=f"📍 **Status de Segurança**\n🕒 Hora: {hora_atual}\n✅ Motorista em deslocamento.", parse_mode='Markdown')
    except: pass

async def disparar_sos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("🚨 ALERTA ENVIADO!", show_alert=True)
    global last_driver_location
    user_name = update.effective_user.first_name
    msg_sos = (f"🚨🚨🚨 **SOS PÂNICO** 🚨🚨🚨\n\n🆘 **MOTORISTA: {user_name}**\n⚠️ **AÇÃO NECESSÁRIA IMEDIATA!**")
    await context.bot.send_message(chat_id=ID_GRUPO_RASTREAMENTO, text=msg_sos, parse_mode='Markdown')
    if last_driver_location:
        await context.bot.send_location(chat_id=ID_GRUPO_RASTREAMENTO, latitude=last_driver_location['lat'], longitude=last_driver_location['lon'])

# --- PAINEL DE CONTROLE ---
@admin_required
async def painel_central(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_fn = update.message.reply_text if update.message else update.callback_query.edit_message_text
    km_price = db_get_setting('price_per_km') or "0.00"
    mode = db_get_setting('bot_mode') or "empresa"
    mode_icon = "🏢" if mode == 'empresa' else "👤"
    tracking_active = bool(context.job_queue.get_jobs_by_name("job_rastreio"))
    track_icon = "🟢" if tracking_active else "🔴"
    on_duty = is_driver_on_duty()
    duty_status = "🟢 ON" if on_duty else "🔴 OFF"
    duty_btn_text = "🔴 Finalizar Turno" if on_duty else "🟢 Iniciar Turno"

    msg = (f"🎛 **PAINEL CENTRAL**\n\n🕒 Turno: {duty_status}\n📡 Rastreio: {track_icon}\n💰 KM: R$ {km_price} | {mode_icon}\n\nOpções:")
    keyboard = [
        [InlineKeyboardButton(duty_btn_text, callback_data="panel_toggle_duty")],
        [InlineKeyboardButton("📊 Financeiro", callback_data="panel_finance"), InlineKeyboardButton("🛡️ Segurança", callback_data="panel_security")],
        [InlineKeyboardButton("⚙️ Config", callback_data="panel_config"), InlineKeyboardButton("📢 Broadcast", callback_data="start_broadcast")],
        [InlineKeyboardButton("❌ Fechar", callback_data="panel_close")]
    ]
    await reply_fn(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    if update.callback_query: await update.callback_query.answer()

async def painel_nav_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "panel_toggle_duty":
        current = is_driver_on_duty()
        new_status = '0' if current else '1'
        db_set_setting('is_on_duty', new_status)
        await query.answer("Status alterado!", show_alert=True)
        await painel_central(update, context)
    elif data == "panel_finance":
        stats = db_get_stats()
        msg = (f"📊 **FINANCEIRO**\n\n📅 Hoje: {stats['day_count']} corridas | R$ {stats['day_val']:.2f}\n"
               f"🗓 Mês: {stats['month_count']} corridas | R$ {stats['month_val']:.2f}\n"
               f"⭐ Avaliação Média: {stats['rating']:.1f}/5.0")
        keyboard = [[InlineKeyboardButton("🔙 Voltar", callback_data="panel_home")]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    elif data == "panel_security":
        is_tracking = bool(context.job_queue.get_jobs_by_name("job_rastreio"))
        status_txt = "🟢 Monitoramento Ativado" if is_tracking else "🔴 Monitoramento Desligado"
        msg = (f"🛡️ **SEGURANÇA**\n\nStatus: **{status_txt}**\n\nBotão de Pânico abaixo:")
        btn_track = InlineKeyboardButton("🛑 Parar Rastreio", callback_data="panel_stop_track") if is_tracking else InlineKeyboardButton("ℹ️ Como Ativar?", callback_data="panel_track_help")
        keyboard = [[InlineKeyboardButton("🚨 SOS PÂNICO", callback_data="panel_sos_panic")], [btn_track], [InlineKeyboardButton("🔙 Voltar", callback_data="panel_home")]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    elif data == "panel_sos_panic":
        await disparar_sos(update, context)
    elif data == "panel_stop_track":
        for job in context.job_queue.get_jobs_by_name("job_rastreio"): job.schedule_removal()
        global last_driver_location
        last_driver_location = None
        await query.answer("Parado!")
        await painel_central(update, context)
    elif data == "panel_track_help":
        await query.answer("Instruções enviadas!", show_alert=True)
        await context.bot.send_message(chat_id=query.message.chat_id, text="📎 Clique no Clipe > Localização > Enviar em Tempo Real")
    elif data == "panel_home":
        await painel_central(update, context)
    elif data == "panel_close":
        await query.delete_message()

# --- CONFIGURAÇÃO ---
@admin_required
async def config_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_callback = bool(update.callback_query)
    reply_fn = update.callback_query.edit_message_text if is_callback else update.message.reply_text
    if is_callback: await update.callback_query.answer()
    car = db_get_setting('driver_car') or "---"
    pix = db_get_setting('pix_key') or "Não definida"
    
    text = (f"⚙️ **CONFIG**\n\n🚗 Carro: {car}\n💰 KM: R$ {db_get_setting('price_per_km')}\n💸 Pix: `{pix}`")
    
    keyboard = [
        [InlineKeyboardButton("🚗 Alterar Carro", callback_data="cfg_edit_car"), InlineKeyboardButton("💸 Chave Pix", callback_data="cfg_edit_pix")],
        [InlineKeyboardButton("✏️ Editar Preço", callback_data="cfg_edit_km"), InlineKeyboardButton("🔄 Modo Bot", callback_data="cfg_change_mode")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="cfg_back_panel")]
    ]
    await reply_fn(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CONFIG_MENU

async def config_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cfg_edit_km":
        await query.edit_message_text("📝 Digite o novo valor do KM:", parse_mode='Markdown')
        return AWAIT_NEW_KM_PRICE
    elif query.data == "cfg_edit_car":
        await query.edit_message_text("🚗 Digite o Modelo e Cor:", parse_mode='Markdown')
        return AWAIT_CAR_MODEL
    elif query.data == "cfg_edit_pix":
        await query.edit_message_text("💸 Digite sua Chave PIX (CPF, Email, Aleatória...):", parse_mode='Markdown')
        return AWAIT_PIX_KEY
    elif query.data == "cfg_change_mode":
        keyboard = [[InlineKeyboardButton("👤 Particular", callback_data="mode_set_particular")], [InlineKeyboardButton("🏢 Empresa", callback_data="mode_set_empresa")], [InlineKeyboardButton("🔙 Voltar", callback_data="cfg_back_start")]]
        await query.edit_message_text("🎭 Escolha:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return AWAIT_MODE_SELECTION
    elif query.data == "cfg_back_panel":
        await painel_central(update, context)
        return ConversationHandler.END
    elif query.data == "cfg_back_start":
        return await config_start(update, context)

async def config_save_km(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_price = float(update.message.text.replace(',', '.').replace('R$', '').strip())
        db_set_setting('price_per_km', f"{new_price:.2f}")
        await update.message.reply_text(f"✅ Preço: R$ {new_price:.2f}")
        return ConversationHandler.END
    except:
        await update.message.reply_text("⚠️ Valor inválido.")
        return AWAIT_NEW_KM_PRICE

async def config_save_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pix_key = update.message.text.strip()
    db_set_setting('pix_key', pix_key)
    await update.message.reply_text(f"✅ Pix Salvo: `{pix_key}`", parse_mode='Markdown')
    return ConversationHandler.END

async def config_save_car_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_car_model'] = update.message.text
    await update.message.reply_text("🔢 Digite a PLACA:")
    return AWAIT_CAR_PLATE

async def config_save_car_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model = context.user_data.get('temp_car_model', 'Carro')
    plate = update.message.text.upper()
    db_set_setting('driver_car', model)
    db_set_setting('driver_plate', plate)
    await update.message.reply_text(f"✅ Salvo: {model} - {plate}")
    return ConversationHandler.END

async def config_save_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = "particular" if update.callback_query.data == "mode_set_particular" else "empresa"
    db_set_setting('bot_mode', mode)
    await update.callback_query.answer("Salvo!")
    return await config_start(update, context)

async def config_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelado.")
    return ConversationHandler.END

# --- FLUXO CLIENTE ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = False
    
    # Check block
    if db_is_blocked(user.id):
        await update.message.reply_text("⛔ **Conta Suspensa.**\nEntre em contato com o suporte para mais informações.")
        return

    try:
        member = await context.bot.get_chat_member(ID_GRUPO_ADMIN, user.id)
        if member.status in ("creator", "administrator", "member"): 
            is_admin = True
    except: pass

    kb = [
        [KeyboardButton(get_ui_text('request_btn')), KeyboardButton(get_ui_text('history_btn'))], 
        [KeyboardButton(get_ui_text('support_btn'))]
    ]

    msg = get_ui_text('welcome', name=user.first_name)

    if is_admin and update.effective_chat.type == 'private':
        kb.append([KeyboardButton("🎛 ABRIR PAINEL DE CONTROLE")])
        msg += "\n\n👮‍♂️ **Modo Staff Detectado:** Você pode solicitar corridas como cliente ou acessar o Painel abaixo."

    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode='Markdown')

async def cliente_historico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if db_is_blocked(update.effective_user.id): return
    
    rides = db_get_user_history(update.effective_user.id)
    if not rides:
        await update.message.reply_text("📭 Você ainda não tem corridas registradas.")
        return
    
    msg = "📜 **Seu Histórico (Últimas 5):**\n\n"
    for r in rides:
        status_icon = "✅" if r[4] == 'completed' else "❌" if 'cancelled' in r[4] else "⏳"
        data_fmt = datetime.fromisoformat(r[3]).strftime('%d/%m %H:%M')
        price_fmt = f"R$ {r[2]:.2f}" if r[2] else "N/A"
        msg += f"{status_icon} **{data_fmt}** - {price_fmt}\n📍 {r[1]}\n\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def cliente_pedir_taxi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if db_is_blocked(update.effective_user.id):
        await update.message.reply_text("⛔ **Conta Suspensa.**\nVocê não pode solicitar novas corridas.")
        return

    if not is_driver_on_duty():
        await update.message.reply_text(get_ui_text('off_duty'), parse_mode='Markdown')
        return
    
    await update.message.reply_text(
        "📍 **Passo 1: Sua Origem**\n\nToque no botão abaixo para enviar sua localização atual:", 
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📍 Enviar Localização Atual", request_location=True)]], one_time_keyboard=True, resize_keyboard=True), 
        parse_mode='Markdown'
    )
    context.user_data['estado'] = 'aguardando_local'

async def cliente_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_ui_text('support_msg'), parse_mode='Markdown')

async def cancelar_pedido_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ride_id = int(query.data.split('_')[1])
    
    with sqlite3.connect(DB_FILE) as conn:
        status = conn.execute("SELECT status FROM rides WHERE id = ?", (ride_id,)).fetchone()
    
    if status and status[0] == 'pending':
        db_update_ride(ride_id, 'cancelled_by_user')
        await query.edit_message_text("❌ **Pedido Cancelado.**\nSe precisar, solicite novamente.")
        await context.bot.send_message(chat_id=ID_GRUPO_ADMIN, text=f"⚠️ **Pedido #{ride_id}** foi CANCELADO pelo cliente.")
    else:
        await query.answer("Motorista já aceitou! Use o suporte.", show_alert=True)

async def receber_pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private': return
    
    # Check block
    if db_is_blocked(update.effective_user.id):
        return

    estado = context.user_data.get('estado')
    
    if estado == 'aguardando_cotacao' and update.message.text:
        msg_chat = f"💬 **Cliente ({update.effective_user.first_name}) diz:**\n\n{update.message.text}"
        await context.bot.send_message(chat_id=ID_GRUPO_ADMIN, text=msg_chat, parse_mode='Markdown')
        return

    if not estado: return

    if not is_driver_on_duty():
        await update.message.reply_text(get_ui_text('off_duty'), parse_mode='Markdown')
        return

    if estado == 'aguardando_local':
        if update.message.location:
            loc_data = f"GPS: {update.message.location.latitude}, {update.message.location.longitude}"
        elif update.message.text:
            loc_data = update.message.text
        else:
            await update.message.reply_text("⚠️ Por favor, envie a localização ou digite o endereço de onde você está.")
            return

        context.user_data['temp_origem'] = loc_data
        context.user_data['estado'] = 'aguardando_destino'
        
        await update.message.reply_text(
            "📍 **Origem Recebida!**\n\n🏁 **Passo 2: Para onde vamos?**\n\nDigite o nome da rua, bairro ou ponto de referência do destino:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return

    elif estado == 'aguardando_destino':
        if not update.message.text:
            await update.message.reply_text("⚠️ Por favor, digite o destino por escrito.")
            return

        destino = update.message.text
        origem = context.user_data.get('temp_origem', 'Não informada')
        user = update.effective_user
        
        full_details = f"De: {origem} | Para: {destino}"
        ride_id = db_create_ride(user.id, full_details)
        
        context.user_data['ride_id'] = ride_id
        context.user_data['estado'] = 'aguardando_cotacao'

        kb = [
            [KeyboardButton(get_ui_text('request_btn')), KeyboardButton(get_ui_text('history_btn'))], 
            [KeyboardButton(get_ui_text('support_btn'))]
        ]
        await update.message.reply_text("🔎 **Recebido! Aguarde o valor da corrida.**", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode='Markdown')
        
        kb_cancel = [[InlineKeyboardButton("❌ Cancelar Pedido", callback_data=f"cancel_user_{ride_id}")]]
        await update.message.reply_text("Se mudar de ideia:", reply_markup=InlineKeyboardMarkup(kb_cancel))
        
        maps_url = ""
        origem_fmt = f"📍 {origem}"
        if "GPS:" in origem:
            coords = origem.replace("GPS: ", "").replace(" ", "")
            maps_url = f"https://www.google.com/maps/search/?api=1&query={coords}"
            origem_fmt = f"<a href='{maps_url}'>📍 Ver Localização de Embarque (Mapa)</a>"

        msg_admin = (
            f"🚨 <b>NOVO PEDIDO #{ride_id}</b>\n"
            f"👤 {user.first_name}\n\n"
            f"{origem_fmt}\n"
            f"🏁 <b>Destino:</b> {destino}\n\n"
            f"👇 <b>RESPONDA AQUI:</b>\n"
            f"• Digite um valor (ex: 15.00) para cobrar.\n"
            f"• Digite texto para conversar com o cliente.\n"
            f"⚠️ **IMPORTANTE: Use a função RESPONDER (Reply) nesta mensagem!**"
        )

        try:
            sent_msg = await context.bot.send_message(chat_id=ID_GRUPO_ADMIN, text=msg_admin, parse_mode='HTML', disable_web_page_preview=False)
            context.bot_data[sent_msg.message_id] = {'user_id': user.id, 'ride_id': ride_id}
        except Exception as e:
            logger.error(f"Erro ao notificar admin: {e}")

# --- RESPOSTA MOTORISTA (HÍBRIDA) ---
async def resposta_motorista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != ID_GRUPO_ADMIN: 
        print(f"⚠️ Resposta ignorada de grupo desconhecido: {update.effective_chat.id}. Esperado: {ID_GRUPO_ADMIN}")
        return
    
    if update.message.reply_to_message.from_user.id != context.bot.id:
        return

    original_msg_id = update.message.reply_to_message.message_id
    dados = context.bot_data.get(original_msg_id)
    
    if not dados:
        await update.message.reply_text("⚠️ **Erro: Pedido não encontrado na memória.**")
        return

    texto_digitado = update.message.text.strip()
    
    # Se digitar /ban na resposta, ignora (será tratado pelo handler de ban)
    if texto_digitado.startswith('/'):
        return

    try:
        valor = float(texto_digitado.replace(',', '.').replace('R$', '').strip())
        
        db_update_ride(dados['ride_id'], 'quoted', price=valor, driver=update.effective_user.first_name)
        
        teclado = [[InlineKeyboardButton("✅ ACEITAR", callback_data=f"aceitar_{dados['ride_id']}_{valor}")], [InlineKeyboardButton("❌ RECUSAR", callback_data=f"recusar_{dados['ride_id']}")]]
        
        try:
            await context.bot.send_message(chat_id=dados['user_id'], text=f"💰 **Oferta:** R$ {valor:.2f}\nConfirma?", reply_markup=InlineKeyboardMarkup(teclado), parse_mode='Markdown')
            await update.message.reply_text("✅ Preço enviado ao passageiro!")
        except Exception as e:
            await update.message.reply_text(f"❌ Erro ao enviar para o usuário: {e}")
        
    except ValueError:
        try:
            await context.bot.send_message(
                chat_id=dados['user_id'], 
                text=f"💬 **Mensagem do Motorista:**\n\n{texto_digitado}", 
                parse_mode='Markdown'
            )
            await update.message.reply_text("📨 Mensagem de texto enviada ao cliente!")
        except Exception as e:
             await update.message.reply_text(f"❌ Erro ao enviar mensagem: {e}")

async def decisao_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acao, ride_id = query.data.split('_')[0], int(query.data.split('_')[1])
    
    if acao == "recusar":
        db_update_ride(ride_id, 'cancelled')
        await query.edit_message_text("❌ Pedido Cancelado.")
        await context.bot.send_message(chat_id=ID_GRUPO_ADMIN, text=f"⚠️ #{ride_id} recusado pelo cliente.")
    elif acao == "aceitar":
        valor = float(query.data.split('_')[2])
        db_update_ride(ride_id, 'active')
        car = db_get_setting('driver_car') or "Padrão"
        
        msg = f"✅ **Aceito! Motorista a caminho.**\n🚘 {car}\n💵 R$ {valor:.2f}"
        kb = [[InlineKeyboardButton("📤 Enviar p/ Família", callback_data=f"share_ride_{ride_id}")]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        
        kb_adm = [
            [InlineKeyboardButton("🔔 AVISE: CHEGUEI NO LOCAL", callback_data=f"cheguei_{ride_id}")],
            [InlineKeyboardButton("🏁 FINALIZAR CORRIDA", callback_data=f"finalizar_{ride_id}")]
        ]
        await context.bot.send_message(chat_id=ID_GRUPO_ADMIN, text=f"🚀 **ACEITO #{ride_id}**\nR$ {valor:.2f}\n\n📍 Vá buscar o passageiro!", reply_markup=InlineKeyboardMarkup(kb_adm), parse_mode='Markdown')

async def motorista_chegou(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Avisado!")
    ride_id = int(query.data.split('_')[1])
    
    with sqlite3.connect(DB_FILE) as conn:
        user_id = conn.execute("SELECT user_id FROM rides WHERE id = ?", (ride_id,)).fetchone()[0]
    
    await context.bot.send_message(chat_id=user_id, text="🚖 **Seu Motorista Chegou!**\nPor favor, vá ao encontro do veículo.", parse_mode='Markdown')
    
    kb_adm = [[InlineKeyboardButton("🏁 FINALIZAR CORRIDA", callback_data=f"finalizar_{ride_id}")]]
    await query.edit_message_text(f"🔔 **AVISO ENVIADO: MOTORISTA NO LOCAL**\n(Corrida #{ride_id})", reply_markup=InlineKeyboardMarkup(kb_adm))

async def share_ride_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ride_id = update.callback_query.data.split('_')[2]
    car = db_get_setting('driver_car') or "---"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚕 **Corrida #{ride_id}**\nCarro: {car}\nAcompanhe pelo Telegram.", parse_mode='Markdown')
    await update.callback_query.answer("Encaminhe a mensagem abaixo!")

async def finalizar_corrida_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ride_id = int(update.callback_query.data.split('_')[1])
    db_update_ride(ride_id, 'completed')
    
    await update.callback_query.edit_message_text(f"🏁 **#{ride_id} Finalizada!** ✅\nDinheiro no bolso.")
    
    # Busca usuário para enviar Pix e Avaliação
    with sqlite3.connect(DB_FILE) as conn:
        res = conn.execute("SELECT user_id, price FROM rides WHERE id = ?", (ride_id,)).fetchone()
    
    if res:
        user_id, price = res
        pix_key = db_get_setting('pix_key') or "Solicite ao motorista"
        
        msg_user = f"🏁 **Corrida Finalizada!**\n\n💵 Total: R$ {price:.2f}\n\n💸 **Pagar com PIX:**\n`{pix_key}`\n(Toque para copiar)"
        kb_rating = [
            [InlineKeyboardButton("⭐ 1", callback_data=f"rate_{ride_id}_1"), InlineKeyboardButton("⭐ 2", callback_data=f"rate_{ride_id}_2"), InlineKeyboardButton("⭐ 3", callback_data=f"rate_{ride_id}_3")],
            [InlineKeyboardButton("⭐ 4", callback_data=f"rate_{ride_id}_4"), InlineKeyboardButton("⭐ 5", callback_data=f"rate_{ride_id}_5")]
        ]
        try:
            await context.bot.send_message(chat_id=user_id, text=msg_user, reply_markup=InlineKeyboardMarkup(kb_rating), parse_mode='Markdown')
        except: pass

async def processar_avaliacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Obrigado!")
    _, ride_id, stars = query.data.split('_')
    
    db_update_ride(ride_id, 'completed', rating=int(stars))
    await query.edit_message_text(f"🌟 **Avaliação enviada:** {stars} Estrelas.\nObrigado por viajar conosco!")
    
    await context.bot.send_message(chat_id=ID_GRUPO_ADMIN, text=f"⭐ **Nova Avaliação!**\nCorrida #{ride_id}: {stars} Estrelas.")

async def start_broadcast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_fn = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
    await reply_fn("📢 Digite a mensagem do Broadcast:", parse_mode='Markdown')
    context.user_data['esperando_broadcast'] = True

async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('esperando_broadcast') and (str(update.effective_chat.id) == ID_GRUPO_ADMIN or update.effective_chat.type=='private'):
        texto = update.message.text
        context.user_data['esperando_broadcast'] = False
        await update.message.reply_text("🚀 Enviando...")
        with sqlite3.connect(DB_FILE) as conn:
            users = conn.execute("SELECT telegram_id FROM users").fetchall()
        for u in users:
            try: await context.bot.send_message(u[0], f"🔔 **AVISO:**\n{texto}", parse_mode='Markdown')
            except: pass
        await update.message.reply_text("✅ Concluído.")
    
    elif update.message.reply_to_message:
        await resposta_motorista(update, context)
    
    elif str(update.effective_chat.id) == ID_GRUPO_ADMIN:
        # Se for comando, deixa o CommandHandler tratar
        if update.message.text.startswith('/'):
            return
            
        if any(char.isdigit() for char in update.message.text):
            await update.message.reply_text(
                "⚠️ **Atenção:** Você digitou um número mas não respondeu ao pedido!\n\n"
                "👉 **Para enviar o preço:** Você DEVE usar a função **RESPONDER** (Reply) na mensagem do pedido específico.",
                quote=True
            )

# --- MENU DE COMANDOS ---
async def post_init(application: Application):
    """ Define os comandos que aparecem no menu / """
    commands = [
        BotCommand("start", "🏁 Iniciar ou Menu Principal"),
        BotCommand("painel", "🎛 Painel de Controle (Admin)"),
        BotCommand("config", "⚙️ Configurações (Admin)"),
        BotCommand("ban", "⛔ Banir Usuário (Admin)"),
        BotCommand("unban", "✅ Desbanir Usuário (Admin)"),
        BotCommand("id", "🆔 Ver ID do Chat"),
    ]
    await application.bot.set_my_commands(commands)

# --- MAIN ---
if __name__ == '__main__':
    setup_database()
    persistence = PicklePersistence(filepath="bot_data.pickle")
    
    # Atualizado com post_init para o menu
    app = ApplicationBuilder().token(TOKEN).persistence(persistence).post_init(post_init).build()

    app.add_handler(TypeHandler(Update, registrar_usuario_global), group=-1)
    
    app.add_handler(MessageHandler(filters.LOCATION, capturar_localizacao_motorista), group=2)
    app.add_handler(TypeHandler(Update, handle_edited_location), group=2)

    config_conv = ConversationHandler(
        entry_points=[CommandHandler("config", config_start), CallbackQueryHandler(config_start, pattern="^panel_config$")],
        states={
            CONFIG_MENU: [CallbackQueryHandler(config_menu_handler)],
            AWAIT_NEW_KM_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_save_km)],
            AWAIT_CAR_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_save_car_model)],
            AWAIT_CAR_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_save_car_plate)],
            AWAIT_PIX_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_save_pix)],
            AWAIT_MODE_SELECTION: [CallbackQueryHandler(config_save_mode)]
        },
        fallbacks=[CommandHandler("cancelar", config_cancel), CallbackQueryHandler(config_menu_handler, pattern="^cfg_close$")],
        per_message=False
    )
    app.add_handler(config_conv)

    # Comandos Admin
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    
    app.add_handler(CommandHandler("id", get_chat_id_debug))

    app.add_handler(CommandHandler("painel", painel_central))
    app.add_handler(CallbackQueryHandler(painel_central, pattern="^panel_home$"))
    app.add_handler(CallbackQueryHandler(painel_nav_handler, pattern="^panel_"))
    app.add_handler(MessageHandler(filters.Regex("^🎛 ABRIR PAINEL DE CONTROLE$"), painel_central))
    
    app.add_handler(MessageHandler(filters.Regex("^(🚗 Chamar Motorista|🚖 Solicitar Táxi)$"), cliente_pedir_taxi))
    app.add_handler(MessageHandler(filters.Regex("^(📞 Falar Comigo|📞 Central de Atendimento)$"), cliente_suporte))
    app.add_handler(MessageHandler(filters.Regex("^(📜 Meus Pedidos|📜 Histórico)$"), cliente_historico))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_broadcast_msg, pattern="^start_broadcast$"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.LOCATION), receber_pedido))
    
    app.add_handler(CallbackQueryHandler(decisao_cliente, pattern="^(aceitar|recusar)_"))
    app.add_handler(CallbackQueryHandler(share_ride_info, pattern="^share_ride_"))
    app.add_handler(CallbackQueryHandler(finalizar_corrida_admin, pattern="^finalizar_"))
    app.add_handler(CallbackQueryHandler(motorista_chegou, pattern="^cheguei_"))
    app.add_handler(CallbackQueryHandler(cancelar_pedido_cliente, pattern="^cancel_user_"))
    app.add_handler(CallbackQueryHandler(processar_avaliacao, pattern="^rate_"))
    
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT, group_message_handler))

    print("🤖 Bot Taxi 3.3 (Prime Studios) Rodando...")
    app.run_polling()