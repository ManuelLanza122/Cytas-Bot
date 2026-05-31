import os
import re
import sqlite3
from datetime import datetime
import telebot
from telebot import types
import pytz

# ==========================================
# 🛠️ CONFIGURACIÓN INICIAL, ADMIN Y CANALES
# ==========================================
TOKEN = "TU_TELEGRAM_BOT_TOKEN_AQUÍ"
bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 123456789  # <- Cambia esto por tu ID de Telegram

# 💰 CANAL PRIVADO DE AUDITORÍA DE PAGOS (Debe empezar con -100)
CANAL_PAGOS_ID = -1009876543210 

ZONA_HORARIA = pytz.timezone('America/Bogota')

# ==========================================
# 🎁 CATÁLOGO DE REGALOS (20 OPCIONES)
# ==========================================
CATALOGO_REGALOS = {
    1: ("🌹 Rosa Roja", 10),
    2: ("🍫 Chocolates Finos", 20),
    3: ("☕ Café Caliente", 30),
    4: ("🍦 Helado Dulce", 40),
    5: ("🍕 Rebanada de Pizza", 50),
    6: ("🍔 Combo Hamburguesa", 80),
    7: ("🍿 Cine & Palomitas", 100),
    8: ("🧸 Peluche Lindo", 150),
    9: ("💐 Ramo de Flores", 200),
    10: ("🎵 Serenata Virtual", 250),
    11: ("🍾 Botella de Champaña", 350),
    12: ("🎟️ Entrada a Concierto", 450),
    13: ("👟 Zapatillas Deportivas", 600),
    14: ("👜 Bolso Elegante", 800),
    15: ("⌚ Reloj de Lujo", 1000),
    16: ("📱 Teléfono Inteligente", 2000),
    17: ("✈️ Boleto de Avión", 3500),
    18: ("💍 Anillo de Compromiso", 5000),
    19: ("🏎️ Auto Deportivo", 10000),
    20: ("🏰 Castillo de Fantasía", 25000)
}

# ==========================================
# 💾 CONEXIÓN Y CREACIÓN DE BASE DE DATOS
# ==========================================
def conectar_db():
    conn = sqlite3.connect('cytas_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id_telegram INTEGER PRIMARY KEY,
            nombre TEXT,
            edad INTEGER,
            descripcion TEXT,
            ciudad TEXT,
            monedas INTEGER DEFAULT 50,
            monedas_regalo INTEGER DEFAULT 0,
            foto_id TEXT,
            estado TEXT DEFAULT 'normal'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS solicitudes_match_link (
            id_solicitud INTEGER PRIMARY KEY AUTOINCREMENT,
            id_recibe INTEGER,
            id_envia INTEGER,
            estado TEXT DEFAULT 'pendiente',
            UNIQUE(id_recibe, id_envia)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats_activos (
            user1_id INTEGER PRIMARY KEY,
            user2_id INTEGER,
            fecha_inicio TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS solicitudes_recarga (
            id_solicitud INTEGER PRIMARY KEY AUTOINCREMENT,
            id_telegram INTEGER,
            monto INTEGER,
            comprobante_foto_id TEXT,
            fecha_pago TEXT,
            estado TEXT DEFAULT 'pendiente'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_regalos (
            id_regalo_envio INTEGER PRIMARY KEY AUTOINCREMENT,
            id_envia INTEGER,
            id_recibe INTEGER,
            regalo_id INTEGER,
            costo_total INTEGER,
            ganancia_recibida INTEGER,
            fecha TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referidos_pendientes (
            id_invitado INTEGER PRIMARY KEY,
            id_invitador INTEGER,
            fecha_click TEXT,
            estado_registro TEXT DEFAULT 'pendiente'
        )
    ''')
    
    conn.commit()
    return conn, cursor

# Inicializar DB al arrancar el script
conectar_db()[0].close()

# ==========================================
# ⚙️ FUNCIONES AUXILIARES DE ESTADO Y NEGOCIO
# ==========================================
def obtener_estado(chat_id):
    conn, cursor = conectar_db()
    cursor.execute("SELECT estado FROM usuarios WHERE id_telegram = ?", (chat_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else "normal"

def actualizar_estado(chat_id, nuevo_estado):
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET estado = ? WHERE id_telegram = ?", (nuevo_estado, chat_id))
    conn.commit()
    conn.close()

def obtener_pareja_chat(chat_id):
    conn, cursor = conectar_db()
    cursor.execute("SELECT user2_id FROM chats_activos WHERE user1_id = ?", (chat_id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("SELECT user1_id FROM chats_activos WHERE user2_id = ?", (chat_id,))
        res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def calcular_rango_vip(total_recargas):
    if total_recargas == 0: return "Unranked ⚪"
    elif 1 <= total_recargas <= 3: return "VIP Bronce 🟫"
    elif 4 <= total_recargas <= 8: return "VIP Plata ⬜"
    else: return "VIP Oro 🟨"

def filtrar_contacto(texto):
    patron_enlaces = r"(io|com|net|org|me|co|t\.me|instagram\.com|facebook\.com|wa\.me|tiktok\.com)"
    patron_usuario = r"@\w+"
    if re.search(patron_enlaces, texto, re.IGNORECASE) or re.search(patron_usuario, texto):
        return True
    return False

# ==========================================
# 📱 TECLADOS Y MENÚS DE NAVEGACIÓN
# ==========================================
def menu_principal():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🔍 Buscar Citas"), types.KeyboardButton("👤 Mi Perfil"))
    markup.add(types.KeyboardButton("📥 Solicitudes"), types.KeyboardButton("🔗 Mi Link de Match"))
    markup.add(types.KeyboardButton("🪙 Recargar Monedas"), types.KeyboardButton("💰 Retirar Fondos"))
    markup.add(types.KeyboardButton("🏆 Top Compradores"), types.KeyboardButton("🔊 Invitar Amigos"))
    return markup

def menu_chat_activo():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🎁 Enviar Regalo"), types.KeyboardButton("👤 Ver Perfil de mi Cita"))
    markup.add(types.KeyboardButton("❌ Terminar Chat"))
    return markup

# ==========================================
# 👑 PANEL DE ADMINISTRACIÓN (EXCLUSIVO ADMIN)
# ==========================================
@bot.message_handler(commands=['panel'], func=lambda m: m.chat.id == ADMIN_ID)
def panel_admin(message):
    conn, cursor = conectar_db()
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM solicitudes_recarga WHERE estado = 'pendiente'")
    pendientes_pago = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(monto) FROM solicitudes_recarga WHERE estado = 'aprobada'")
    total_recaudado = cursor.fetchone()[0] or 0
    conn.close()
    
    txt_admin = (
        "👑 **PANEL DE CONTROL - ADMINISTRADOR** 👑\n\n"
        f"👥 **Usuarios Totales:** `{total_users}`\n"
        f"⏳ **Pagos pendientes en Canal:** `{pendientes_pago}`\n"
        f"💰 **Total Recaudado:** `{total_recaudado} Monedas`.\n\n"
        "🛠️ **Comandos Globales:**\n"
        "• `/difundir Mensaje` - Envía un anuncio masivo a todos los registrados."
    )
    bot.send_message(ADMIN_ID, txt_admin, parse_mode="Markdown")

@bot.message_handler(commands=['difundir'], func=lambda m: m.chat.id == ADMIN_ID)
def admin_difundir_mensaje(message):
    texto_masivo = message.text.replace("/difundir", "").strip()
    if not texto_masivo:
        bot.send_message(ADMIN_ID, "❌ Debes escribir un mensaje. Ejemplo: `/difundir Hola`")
        return
        
    conn, cursor = conectar_db()
    cursor.execute("SELECT id_telegram FROM usuarios")
    usuarios = cursor.fetchall()
    conn.close()
    
    enviados = 0
    for u in usuarios:
        try:
            bot.send_message(u[0], f"📢 **ANUNCIO OFICIAL:**\n\n{texto_masivo}", parse_mode="Markdown")
            enviados += 1
        except: continue
    bot.send_message(ADMIN_ID, f"✅ Difusión completada. Entregados: `{enviados}/{len(usuarios)}`.", parse_mode="Markdown")

# ==========================================
# 🚀 COMANDO DE ENTRADA /START
# ==========================================
@bot.message_handler(commands=['start'])
def inicio(message):
    chat_id = message.chat.id
    texto = message.text.split()
    
    conn, cursor = conectar_db()
    cursor.execute("SELECT estado FROM usuarios WHERE id_telegram = ?", (chat_id,))
    user = cursor.fetchone()
    
    id_objetivo_match = None
    id_invitador = None
    
    if len(texto) > 1:
        parametro = texto[1]
        if parametro.startswith("match_"):
            try:
                id_objetivo_match = int(parametro.split("_")[1])
                if id_objetivo_match == chat_id: id_objetivo_match = None
            except ValueError: pass
        elif parametro.isdigit():
            id_invitador = int(parametro)
            if id_invitador == chat_id: id_invitador = None

    if not user:
        ref_txt = ""
        if id_objetivo_match: ref_txt = f"MATCH_LINK:{id_objetivo_match}"
        elif id_invitador:
            ref_txt = f"INVITE_ID:{id_invitador}"
            fecha_actual = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M")
            cursor.execute("INSERT OR IGNORE INTO referidos_pendientes (id_invitado, id_invitador, fecha_click) VALUES (?, ?, ?)", (chat_id, id_invitador, fecha_actual))
            conn.commit()
            try: bot.send_message(id_invitador, "🔔 **¡Alguien tocó tu link de invitación!**", parse_mode="Markdown")
            except: pass

        cursor.execute("INSERT INTO usuarios (id_telegram, estado, descripcion) VALUES (?, 'reg_nombre', ?)", (chat_id, ref_txt))
        conn.commit()
        bot.send_message(chat_id, "¡Bienvenido al Bot de Citas! 👋\nConfiguremos tu tarjeta de perfil.\n\n¿Cómo te llamas?")
    else:
        actualizar_estado(chat_id, "normal")
        if id_objetivo_match:
            try:
                cursor.execute("INSERT OR IGNORE INTO solicitudes_match_link (id_recibe, id_envia) VALUES (?, ?)", (id_objetivo_match, chat_id))
                conn.commit()
                bot.send_message(chat_id, "✨ **¡Solicitud de Match enviada!**", reply_markup=menu_principal(), parse_mode="Markdown")
                bot.send_message(id_objetivo_match, "🔔 **¡Tienes una nueva solicitud por link directo!** Revisa tu sección '📥 Solicitudes'.")
            except:
                bot.send_message(chat_id, "¡Hola de nuevo!", reply_markup=menu_principal())
        else:
            bot.send_message(chat_id, "¡Hola de nuevo!", reply_markup=menu_principal())
    conn.close()

# ==========================================
# 📥 FLUJO DE REGISTRO PASO A PASO
# ==========================================
@bot.message_handler(func=lambda m: obtener_estado(m.chat.id).startswith('reg_'))
def flujo_registro(message):
    chat_id = message.chat.id
    estado = obtener_estado(chat_id)
    texto = message.text
    conn, cursor = conectar_db()
    
    if estado == "reg_nombre":
        cursor.execute("UPDATE usuarios SET nombre = ?, estado = 'reg_edad' WHERE id_telegram = ?", (texto, chat_id))
        conn.commit()
        bot.send_message(chat_id, f"Mucho gusto {texto}. ¿Cuántos años tienes?")
    elif estado == "reg_edad":
        if not texto.isdigit():
            bot.send_message(chat_id, "❌ Envía un número válido:")
            conn.close()
            return
        cursor.execute("UPDATE usuarios SET edad = ?, estado = 'reg_ciudad' WHERE id_telegram = ?", (int(texto), chat_id))
        conn.commit()
        bot.send_message(chat_id, "📍 ¿De qué ciudad eres?")
    elif estado == "reg_ciudad":
        cursor.execute("UPDATE usuarios SET ciudad = ?, estado = 'reg_desc' WHERE id_telegram = ?", (texto, chat_id))
        conn.commit()
        bot.send_message(chat_id, "✍️ Escribe una breve descripción para tu perfil:")
    elif estado == "reg_desc":
        cursor.execute("UPDATE usuarios SET descripcion = ?, estado = 'reg_foto' WHERE id_telegram = ?", (texto, chat_id))
        conn.commit()
        bot.send_message(chat_id, "📸 Por último, envía tu foto de perfil:")
    conn.close()

@bot.message_handler(content_types=['photo'], func=lambda m: obtener_estado(m.chat.id) == 'reg_foto')
def registro_foto(message):
    chat_id = message.chat.id
    foto_id = message.photo[-1].file_id
    
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET foto_id = ?, estado = 'normal' WHERE id_telegram = ?", (foto_id, chat_id))
    conn.commit()
    conn.close()
    
    bot.send_message(chat_id, "🎉 **¡Tu perfil ha sido creado con éxito!** Te regalamos 50 monedas iniciales.", reply_markup=menu_principal())

# ==========================================
# 🎮 CONTROLADOR DEL PANEL PRINCIPAL (BOTONES TEXTO)
# ==========================================
@bot.message_handler(func=lambda m: obtener_estado(m.chat.id) == 'normal')
def controlador_menu_principal(message):
    chat_id = message.chat.id
    texto = message.text

    if texto == "👤 Mi Perfil":
        conn, cursor = conectar_db()
        cursor.execute("SELECT nombre, edad, descripcion, ciudad, monedas, monedas_regalo, foto_id FROM usuarios WHERE id_telegram = ?", (chat_id,))
        n, e, d, c, m, mr, f = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM solicitudes_recarga WHERE id_telegram = ? AND estado = 'aprobada'", (chat_id,))
        total_recargas = cursor.fetchone()[0]
        conn.close()
        
        rango_vip = calcular_rango_vip(total_recargas)
        txt = (
            f"👤 **Tu Tarjeta de Perfil:**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🎖️ **Rango:** {rango_vip}\n"
            f"ID: `{chat_id}`\n"
            f"📛 **Nombre:** {n}\n🎂 **Edad:** {e} años\n📍 **Ubicación:** `{c if c else 'No def.'}`\n"
            f"📝 **Biografía:** _{d}_\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 **Saldo:** `{m}` monedas.\n💰 **Regalos Ganados:** `{mr}` monedas."
        )
        markup_editar = types.InlineKeyboardMarkup()
        markup_editar.add(types.InlineKeyboardButton("⚙️ Editar mis datos", callback_data="perf_menu_editar"))
        bot.send_photo(chat_id, f, caption=txt, reply_markup=markup_editar, parse_mode="Markdown")

    elif texto == "🔍 Buscar Citas":
        conn, cursor = conectar_db()
        cursor.execute("SELECT id_telegram, nombre, edad, descripcion, city = ciudad, foto_id FROM usuarios WHERE id_telegram != ? AND foto_id IS NOT NULL ORDER BY RANDOM() LIMIT 1", (chat_id,))
        target = cursor.fetchone()
        conn.close()
        
        if not target:
            bot.send_message(chat_id, "😔 No hay perfiles disponibles por ahora.")
            return
            
        tid, n, e, d, c, f = target
        txt_target = f"🔥 **Descubre a esta persona:**\n\n👤 **Nombre:** {n}\n🎂 **Edad:** {e} años\n📍 **Ubicación:** `{c}`\n📝 **Bio:** _{d}_"
        
        markup_voto = types.InlineKeyboardMarkup(row_width=2)
        markup_voto.add(types.InlineKeyboardButton("❌ Pasar", callback_data="skip_next"), types.InlineKeyboardButton("💚 Me Gusta", callback_data=f"like_{tid}"))
        bot.send_photo(chat_id, f, caption=txt_target, reply_markup=markup_voto, parse_mode="Markdown")

    elif texto == "🔗 Mi Link de Match":
        bot_info = bot.get_me()
        bot.send_message(chat_id, f"🔗 **TU ENLACE DE MATCH DIRECTO**\n\n`https://t.me/{bot_info.username}?start=match_{chat_id}`", parse_mode="Markdown")

    elif texto == "📥 Solicitudes":
        conn, cursor = conectar_db()
        cursor.execute("""
            SELECT s.id_solicitud, u.id_telegram, u.nombre, u.edad, u.descripcion, u.foto_id 
            FROM solicitudes_match_link s
            JOIN usuarios u ON s.id_envia = u.id_telegram
            WHERE s.id_recibe = ? AND s.estado = 'pendiente' LIMIT 1
        """, (chat_id,))
        solicitud = cursor.fetchone()
        conn.close()
        
        if not solicitud:
            bot.send_message(chat_id, "📥 No tienes solicitudes pendientes.")
            return
            
        id_sol, id_envia, nombre, edad, descripcion, foto_id = solicitud
        markup_sol = types.InlineKeyboardMarkup(row_width=2)
        markup_sol.add(types.InlineKeyboardButton("❌ Rechazar", callback_data=f"lnk_rech_{id_sol}"), types.InlineKeyboardButton("✅ Conectar", callback_data=f"lnk_aprob_{id_sol}"))
        
        bot.send_photo(chat_id, foto_id, caption=f"✨ **¡QUIEREN CONECTAR CONTIGO!**\n\n👤 **Nombre:** {nombre}\n🎂 **Edad:** {edad}\n📝 **Bio:** {descripcion}", reply_markup=markup_sol, parse_mode="Markdown")

    elif texto == "🪙 Recargar Monedas":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🪙 100 Monedas ($1 USD)", callback_data="buy_100"),
            types.InlineKeyboardButton("🪙 500 Monedas ($5 USD)", callback_data="buy_500"),
            types.InlineKeyboardButton("🪙 1000 Monedas ($10 USD)", callback_data="buy_1000")
        )
        txt_info = (
            "🪙 **CENTRAL DE RECARGAS** 🪙\n\n"
            "📌 *Medios de Pago:* Nequi / Daviplata al número: `3001234567`\n"
            "👇 Elige el paquete que deseas adquirir e infórmalo al sistema:"
        )
        bot.send_message(chat_id, txt_info, reply_markup=markup, parse_mode="Markdown")

    elif texto == "💰 Retirar Fondos":
        bot.send_message(chat_id, "💰 **SISTEMA DE RETIROS**\nMínimo de retiro: 1.000 monedas de regalos ($10 USD).\nEscríbele a @Administrador para procesar por Nequi.")

    elif texto == "🏆 Top Compradores":
        conn, cursor = conectar_db()
        cursor.execute("SELECT nombre, monedas FROM usuarios ORDER BY monedas DESC LIMIT 5")
        tops = cursor.fetchall()
        conn.close()
        txt_top = "🏆 **TOP 5 COMPRADORES**\n\n"
        for i, u in enumerate(tops): txt_top += f"{i+1}. **{u[0]}** — `{u[1]}` monedas.\n"
        bot.send_message(chat_id, txt_top, parse_mode="Markdown")

    elif texto == "🔊 Invitar Amigos":
        bot_info = bot.get_me()
        bot.send_message(chat_id, f"📢 **INVITA Y GANA 50 MONEDAS**\n\n`https://t.me/{bot_info.username}?start={chat_id}`", parse_mode="Markdown")

# ==========================================
# ⚙️ EDICIÓN INLINE DE PERFIL (CALLBACKS)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('perf_'))
def editar_perfil_callback(call):
    chat_id = call.message.chat.id
    data = call.data
    if data == "perf_menu_editar":
        bot.delete_message(chat_id, call.message.message_id)
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📝 Nombre", callback_data="perf_edit_nombre"),
            types.InlineKeyboardButton("🎂 Edad", callback_data="perf_edit_edad"),
            types.InlineKeyboardButton("📍 Ciudad", callback_data="perf_edit_ciudad"),
            types.InlineKeyboardButton("✍️ Bio", callback_data="perf_edit_desc"),
            types.InlineKeyboardButton("📸 Foto", callback_data="perf_edit_foto"),
            types.InlineKeyboardButton("🔙 Volver", callback_data="perf_cancelar")
        )
        bot.send_message(chat_id, "🛠️ **¿Qué dato deseas modificar?**", reply_markup=markup, parse_mode="Markdown")
    elif data.startswith("perf_edit_"):
        campo = data.split("_")[2]
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, f"Introduce el nuevo valor para tu {campo}:")
        actualizar_estado(chat_id, f"edit_wait_{campo}")
    elif data == "perf_cancelar":
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, "✅ Operación cancelada.", reply_markup=menu_principal())

@bot.message_handler(func=lambda m: obtener_estado(m.chat.id).startswith('edit_wait_'))
def procesar_cambio_perfil(message):
    chat_id = message.chat.id
    estado = obtener_estado(chat_id)
    campo = estado.split('_')[2]
    texto = message.text
    conn, cursor = conectar_db()
    if campo == "nombre": cursor.execute("UPDATE usuarios SET nombre = ? WHERE id_telegram = ?", (texto, chat_id))
    elif campo == "edad": cursor.execute("UPDATE usuarios SET edad = ? WHERE id_telegram = ?", (int(texto), chat_id))
    elif campo == "ciudad": cursor.execute("UPDATE usuarios SET ciudad = ? WHERE id_telegram = ?", (texto, chat_id))
    elif campo == "desc": cursor.execute("UPDATE usuarios SET descripcion = ? WHERE id_telegram = ?", (texto, chat_id))
    conn.commit()
    conn.close()
    actualizar_estado(chat_id, "normal")
    bot.send_message(chat_id, f"✅ Tu {campo} ha sido actualizado con éxito.", reply_markup=menu_principal())

@bot.message_handler(content_types=['photo'], func=lambda m: obtener_estado(m.chat.id) == 'edit_wait_foto')
def procesar_cambio_foto_perfil(message):
    chat_id = message.chat.id
    foto_id = message.photo[-1].file_id
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET foto_id = ? WHERE id_telegram = ?", (foto_id, chat_id))
    conn.commit()
    conn.close()
    actualizar_estado(chat_id, "normal")
    bot.send_message(chat_id, "✅ Nueva foto de perfil establecida.", reply_markup=menu_principal())

# ==========================================
# 🗳️ PROCESAMIENTO DE VOTOS (ME GUSTA / PASAR)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('like_') or call.data == "skip_next")
def v_likes_buscador(call):
    chat_id = call.message.chat.id
    if call.data == "skip_next":
        bot.delete_message(chat_id, call.message.message_id)
        message = call.message
        message.text = "🔍 Buscar Citas"
        controlador_menu_principal(message)
        return
        
    id_votado = int(call.data.split('_')[1])
    bot.delete_message(chat_id, call.message.message_id)
    
    conn, cursor = conectar_db()
    cursor.execute("INSERT OR IGNORE INTO solicitudes_match_link (id_recibe, id_envia) VALUES (?, ?)", (id_votado, chat_id))
    conn.commit()
    conn.close()
    
    bot.send_message(chat_id, "💚 ¡Le diste Me Gusta! Te avisaremos si te acepta.")
    try: bot.send_message(id_votado, "🔔 ¡Tienes un nuevo Me Gusta esperando en la sección '📥 Solicitudes'!")
    except: pass

# ==========================================
# 📥 CONTROLADOR DE SOLICITUDES RECIBIDAS
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('lnk_'))
def procesar_gestion_solicitudes(call):
    chat_id = call.message.chat.id
    accion = call.data.split('_')[1]
    id_sol = int(call.data.split('_')[2])
    bot.delete_message(chat_id, call.message.message_id)
    
    conn, cursor = conectar_db()
    cursor.execute("SELECT id_recibe, id_envia, estado FROM solicitudes_match_link WHERE id_solicitud = ?", (id_sol,))
    res_sol = cursor.fetchone()
    
    if not res_sol or res_sol[2] != 'pendiente':
        conn.close()
        return
        
    id_recibe, id_envia, _ = res_sol
    
    if accion == "rech":
        cursor.execute("UPDATE solicitudes_match_link SET estado = 'rechazado' WHERE id_solicitud = ?", (id_sol,))
        conn.commit()
        bot.send_message(chat_id, "❌ Solicitud rechazada correctamente.")
    elif accion == "aprob":
        cursor.execute("UPDATE solicitudes_match_link SET estado = 'aprobado' WHERE id_solicitud = ?", (id_sol,))
        fecha_actual = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M")
        cursor.execute("INSERT OR REPLACE INTO chats_activos (user1_id, user2_id, fecha_inicio) VALUES (?, ?, ?)", (chat_id, id_envia, fecha_actual))
        cursor.execute("UPDATE usuarios SET estado = 'chateando' WHERE id_telegram IN (?, ?)", (chat_id, id_envia))
        conn.commit()
        
        bot.send_message(chat_id, "🥳 **¡CONEXIÓN ESTABLECIDA!** 🎉\nYa pueden hablar de manera directa y segura.", reply_markup=menu_chat_activo(), parse_mode="Markdown")
        bot.send_message(id_envia, "🥳 **¡CONEXIÓN ESTABLECIDA!** 🎉\nYa pueden hablar de manera directa y segura.", reply_markup=menu_chat_activo(), parse_mode="Markdown")
    conn.close()

# ==========================================
# 🪙 SISTEMA DE VERIFICACIÓN DE PAGOS POR CANAL 
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def procesar_seleccion_paquete(call):
    chat_id = call.message.chat.id
    monedas = int(call.data.split('_')[1])
    bot.delete_message(chat_id, call.message.message_id)
    
    actualizar_estado(chat_id, f"pay_wait_{monedas}")
    bot.send_message(chat_id, f"📸 **Elegiste el paquete de {monedas} Monedas.**\nPor favor envía la captura o foto nítida de tu comprobante de pago por aquí:")

@bot.message_handler(content_types=['photo'], func=lambda m: obtener_estado(m.chat.id).startswith('pay_wait_'))
def recibir_comprobante_pago(message):
    chat_id = message.chat.id
    estado = obtener_estado(chat_id)
    monedas_solicitadas = int(estado.split('_')[2])
    foto_comprobante = message.photo[-1].file_id
    fecha_actual = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M")
    
    conn, cursor = conectar_db()
    cursor.execute("INSERT INTO solicitudes_recarga (id_telegram, monto, comprobante_foto_id, fecha_pago, estado) VALUES (?, ?, ?, ?, 'pendiente')", (chat_id, monedas_solicitadas, foto_comprobante, fecha_actual))
    id_solicitud = cursor.lastrowid
    cursor.execute("SELECT nombre FROM usuarios WHERE id_telegram = ?", (chat_id,))
    nombre_usuario = cursor.fetchone()[0]
    conn.close()
    
    actualizar_estado(chat_id, "normal")
    
    markup_canal = types.InlineKeyboardMarkup(row_width=2)
    markup_canal.add(
        types.InlineKeyboardButton("✅ Aprobar Saldo", callback_data=f"pay_aprob_{id_solicitud}"),
        types.InlineKeyboardButton("❌ Rechazar Recibo", callback_data=f"pay_rech_{id_solicitud}")
    )
    
    texto_canal = (
        "💰 **SOLICITUD DE RECARGA RECIBIDA** 💰\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 **ID Recarga:** #{id_solicitud}\n"
        f"👤 **Usuario:** {nombre_usuario} (`{chat_id}`)\n"
        f"🪙 **Monto Prometido:** `{monedas_solicitadas}` Monedas\n"
        f"🕒 **Fecha:** {fecha_actual}\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )
    
    try:
        bot.send_photo(CANAL_PAGOS_ID, foto_comprobante, caption=texto_canal, reply_markup=markup_canal, parse_mode="Markdown")
        bot.send_message(chat_id, "✅ **Comprobante en revisión.** Validaremos el depósito en el canal de administración en minutos.", reply_markup=menu_principal())
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Error en despacho a canal: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_aprob_') or call.data.startswith('pay_rech_'))
def procesar_clicks_canal_pagos(call):
    if call.message.chat.id != CANAL_PAGOS_ID and call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Sin permisos de administrador.")
        return
        
    partes = call.data.split('_')
    accion = partes[1]
    id_solicitud = int(partes[2])
    
    conn, cursor = conectar_db()
    cursor.execute("SELECT id_telegram, monto, estado FROM solicitudes_recarga WHERE id_solicitud = ?", (id_solicitud,))
    recarga = cursor.fetchone()
    
    if not recarga or recarga[2] != 'pendiente':
        bot.answer_callback_query(call.id, "Operación expirada o ya resuelta.")
        conn.close()
        return
        
    user_id, monto_monedas, _ = recarga
    
    if accion == "aprob":
        cursor.execute("UPDATE solicitudes_recarga SET estado = 'aprobada' WHERE id_solicitud = ?", (id_solicitud,))
        cursor.execute("UPDATE usuarios SET monedas = monedas + ? WHERE id_telegram = ?", (monto_monedas, user_id))
        conn.commit()
        
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=call.message.caption + f"\n\n🟢 **APROBADA por @{call.from_user.username or call.from_user.id}**", reply_markup=None)
        try: bot.send_message(user_id, f"🎉 **¡Recarga Aprobada!** Se han inyectado `{monto_monedas}` monedas a tu billetera virtual.")
        except: pass
        
    elif accion == "rech":
        cursor.execute("UPDATE solicitudes_recarga SET estado = 'rechazada' WHERE id_solicitud = ?", (id_solicitud,))
        conn.commit()
        
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=call.message.caption + f"\n\n🔴 **RECHAZADA por @{call.from_user.username or call.from_user.id}**", reply_markup=None)
        try: bot.send_message(user_id, "❌ **Tu comprobante fue declinado.** Si crees que es un error comunícate con soporte.")
        except: pass
        
    conn.close()

# ==========================================
# 🎁 TIENDA INTERACTIVA (20 REGALOS - COMISIÓN 50%)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('gift_send_'))
def procesar_envio_regalo(call):
    chat_id = call.message.chat.id
    regalo_id = int(call.data.split('_')[2])
    pareja_id = obtener_pareja_chat(chat_id)
    
    if not pareja_id:
        bot.answer_callback_query(call.id, "⚠️ La sesión de chat ya expiró.", show_alert=True)
        bot.delete_message(chat_id, call.message.message_id)
        return
        
    nombre_regalo, costo = CATALOGO_REGALOS[regalo_id]
    conn, cursor = conectar_db()
    
    cursor.execute("SELECT monedas, nombre FROM usuarios WHERE id_telegram = ?", (chat_id,))
    remitente = cursor.fetchone()
    monedas_actuales = remitente[0] if remitente else 0
    nombre_remitente = remitente[1] if remitente else "Tu cita"
    
    if monedas_actuales < costo:
        bot.answer_callback_query(call.id, f"❌ Saldo insuficiente. Cuesta {costo} monedas.", show_alert=True)
        conn.close()
        return
        
    # El receptor gana exactamente la mitad (50%)
    ganancia_receptor = costo // 2
    
    cursor.execute("UPDATE usuarios SET monedas = monedas - ? WHERE id_telegram = ?", (costo, chat_id))
    cursor.execute("UPDATE usuarios SET monedas = monedas + ?, monedas_regalo = monedas_regalo + ? WHERE id_telegram = ?", (ganancia_receptor, ganancia_receptor, pareja_id))
    
    fecha_envio = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M")
    cursor.execute("INSERT INTO historial_regalos (id_envia, id_recibe, regalo_id, costo_total, ganancia_recibida, fecha) VALUES (?, ?, ?, ?, ?, ?)", (chat_id, pareja_id, regalo_id, costo, ganancia_receptor, fecha_envio))
    conn.commit()
    conn.close()
    
    bot.delete_message(chat_id, call.message.message_id)
    bot.answer_callback_query(call.id, f"¡{nombre_regalo} enviado!")
    
    bot.send_message(chat_id, f"💝 **¡Regalo enviado!** Descontadas `{costo}` monedas de tu saldo.")
    bot.send_message(pareja_id, f"🎁 ✨ **¡{nombre_remitente} te envió un {nombre_regalo}!**\nHas ganado **+{ganancia_receptor} monedas** añadidas a tu cuenta.")

# ==========================================
# 💬 INTERMEDIARIO DE CHAT EN VIVO ANÓNIMO
# ==========================================
@bot.message_handler(func=lambda m: obtener_estado(m.chat.id) == 'chateando', content_types=['text', 'photo', 'sticker', 'video', 'voice'])
def retransmision_chat_anonimo(message):
    chat_id = message.chat.id
    texto = message.text if message.text else ""
    id_pareja = obtener_pareja_chat(chat_id)
    
    if not id_pareja:
        actualizar_estado(chat_id, "normal")
        bot.send_message(chat_id, "La conversación finalizó.", reply_markup=menu_principal())
        return
    
    if texto == "❌ Terminar Chat":
        conn, cursor = conectar_db()
        cursor.execute("DELETE FROM chats_activos WHERE user1_id = ? OR user2_id = ?", (chat_id, chat_id))
        cursor.execute("UPDATE usuarios SET estado = 'normal' WHERE id_telegram IN (?, ?)", (chat_id, id_pareja))
        conn.commit()
        conn.close()
        bot.send_message(chat_id, "❌ Has cerrado la conversación.", reply_markup=menu_principal())
        bot.send_message(id_pareja, "❌ Tu cita ha cerrado la conversación.", reply_markup=menu_principal())
        return
        
    elif texto == "👤 Ver Perfil de mi Cita":
        conn, cursor = conectar_db()
        cursor.execute("SELECT nombre, edad, descripcion, ciudad, foto_id FROM usuarios WHERE id_telegram = ?", (id_pareja,))
        n, e, d, c, f = cursor.fetchone()
        conn.close()
        bot.send_photo(chat_id, f, caption=f"👤 **Perfil:** {n}, {e} años.\n📍 `{c}`\n📝 _{d}_", parse_mode="Markdown")
        return
        
    elif texto == "🎁 Enviar Regalo":
        markup = types.InlineKeyboardMarkup(row_width=2)
        botones = [types.InlineKeyboardButton(f"{nom} ({cos} 🪙)", callback_data=f"gift_send_{id_r}") for id_r, (nom, cos) in CATALOGO_REGALOS.items()]
        markup.add(*botones)
        bot.send_message(chat_id, "🎁 **TIENDA DE REGALOS**\nElige el obsequio. Tu pareja recibe el 50% de su valor en saldo:", reply_markup=markup, parse_mode="Markdown")
        return

    if message.content_type == 'text' and filtrar_contacto(texto):
        bot.send_message(chat_id, "🚫 No se permite compartir redes sociales o enlaces aquí.")
        return

    # Validar cobro de 1 moneda por mensaje enviado
    conn, cursor = conectar_db()
    cursor.execute("SELECT monedas FROM usuarios WHERE id_telegram = ?", (chat_id,))
    saldo = cursor.fetchone()[0]
    
    if saldo < 1:
        bot.send_message(chat_id, "🚨 Te quedaste sin monedas. Por favor ve a '🪙 Recargar Monedas' en el menú principal.")
        conn.close()
        return
        
    cursor.execute("UPDATE usuarios SET monedas = monedas - 1 WHERE id_telegram = ?", (chat_id,))
    conn.commit()
    conn.close()

    try:
        if message.content_type == 'text': bot.send_message(id_pareja, f"💬 **Tu cita:** {texto}")
        elif message.content_type == 'photo': bot.send_photo(id_pareja, message.photo[-1].file_id, caption="💬 **Tu cita te envió una foto**")
        elif message.content_type == 'sticker': bot.send_sticker(id_pareja, message.sticker.file_id)
        elif message.content_type == 'video': bot.send_video(id_pareja, message.video.file_id)
        elif message.content_type == 'voice': bot.send_voice(id_pareja, message.voice.file_id)
    except: pass

# ==========================================
# 🔄 INICIO DE POLLING PERPETUO
# ==========================================
if __name__ == '__main__':
    print("🚀 Cytas-Bot Completado al 100%. Desplegado y listo para producción...")
    bot.infinity_polling(skip_pending=True)