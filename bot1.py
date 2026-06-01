import telebot
from telebot import types
import sqlite3
from datetime import datetime
import pytz
import re

# ==========================================
# ⚙️ CONFIGURACIÓN PRINCIPAL Y ECONOMÍA
# ==========================================
TOKEN = "TU_TELEGRAM_BOT_TOKEN"          # 👈 Cambia por el token de tu BotFather
ID_ADMIN = 123456789                     # 👈 Cambia por tu ID real de Telegram (numérico)
ID_CANAL_SOLICITUDES = -1002345678901    # 👈 Cambia por el ID de tu canal de Telegram (debe empezar con -100)

bot = telebot.TeleBot(TOKEN)

# Reglas del negocio (Precios Suaves y Filtros)
COSTO_LIKE = 2        
COSTO_MENSAJE = 1     
MINIMO_RETIRABLE_MONEDAS = 2500          # Equivalente exacto a $25 USD (100 monedas = $1 USD)

CATALOGO_REGALOS = {
    "rosa": {"nombre": "🌹 Rosa", "precio": 10},
    "chocolate": {"nombre": "🍫 Chocolates", "precio": 30},
    "oso": {"nombre": "🧸 Oso de Peluche", "precio": 100},
    "corona": {"nombre": "👑 Corona VIP", "precio": 500}
}

PAQUETES_MONEDAS = {
    "pack_100": {"monedas": 100, "precio": "$2.000 COP / $0.50 USD"},  
    "pack_300": {"monedas": 300, "precio": "$5.000 COP / $1.20 USD"},
    "pack_1000": {"monedas": 1000, "precio": "$15.000 COP / $3.50 USD"}
}

# ==========================================
# 🗄️ MANEJO DE BASE DE DATOS (SQLite)
# ==========================================
def conectar_db():
    conn = sqlite3.connect('dating_bot.db')
    cursor = conn.cursor()
    
    # Usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id_telegram INTEGER PRIMARY KEY,
            nombre TEXT,
            edad INTEGER,
            genero TEXT,
            busca TEXT,
            descripcion TEXT,
            ciudad TEXT,
            foto_id TEXT,
            monedas INTEGER DEFAULT 50,
            monedas_regalo INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'registro'
        )
    ''')
    
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN ciudad TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Likes / Dislikes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interacciones (
            de_id INTEGER,
            para_id INTEGER,
            tipo TEXT,
            PRIMARY KEY (de_id, para_id)
        )
    ''')
    
    # Matches Activos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats_activos (
            user1_id INTEGER,
            user2_id INTEGER,
            PRIMARY KEY (user1_id, user2_id)
        )
    ''')
    
    # Solicitudes de Recarga (Nequi/PayPal)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS solicitudes_recarga (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_telegram INTEGER,
            cantidad_monedas INTEGER,
            comprobante_foto_id TEXT,
            estado TEXT DEFAULT 'pendiente'
        )
    ''')
    
    # Solicitudes de Retiro ($25 USD)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS solicitudes_retiro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_telegram INTEGER,
            cantidad_monedas INTEGER,
            datos_pago TEXT,
            estado TEXT DEFAULT 'pendiente'
        )
    ''')

    # Historial de Regalos (Nueva tabla para controlar la lista más larga de regalos recibidos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS regalos_enviados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            de_id INTEGER,
            para_id INTEGER,
            tipo_regalo TEXT,
            valor_monedas INTEGER,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    return conn, cursor

# Inicializar Base de Datos al arrancar
conectar_db()

# Funciones Auxiliares de Estado y Transacciones
def obtener_estado(chat_id):
    conn, cursor = conectar_db()
    cursor.execute("SELECT estado FROM usuarios WHERE id_telegram = ?", (chat_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

def actualizar_estado(chat_id, nuevo_estado):
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET estado = ? WHERE id_telegram = ?", (nuevo_estado, chat_id))
    conn.commit()
    conn.close()

def cobrar_monedas(chat_id, costo):
    conn, cursor = conectar_db()
    cursor.execute("SELECT monedas FROM usuarios WHERE id_telegram = ?", (chat_id,))
    res = cursor.fetchone()
    if res and res[0] >= costo:
        nuevo_saldo = res[0] - costo
        cursor.execute("UPDATE usuarios SET monedas = ? WHERE id_telegram = ?", (nuevo_saldo, chat_id))
        conn.commit()
        conn.close()
        return True, nuevo_saldo
    conn.close()
    return False, 0

def calcular_rango_vip(total_recargas):
    if total_recargas == 0:
        return "👤 Usuario Regular"
    elif 1 <= total_recargas <= 2:
        return "✨ VIP Bronce 🥉"
    elif 3 <= total_recargas <= 5:
        return "🔥 VIP Plata 🥈"
    else:
        return "👑 VIP Oro Rey 👑"

# ==========================================
# 🕒 CONTROL HORARIO (COLOMBIA)
# ==========================================
def obtener_aviso_horario():
    zona_co = pytz.timezone('America/Bogota')
    hora_actual = datetime.now(zona_co).hour
    if hora_actual >= 23 or hora_actual < 7:
        return "\n\n⚠️ **AVISO DE HORARIO:** Actualmente estamos fuera de jornada (11:00 PM - 7:00 AM). Puedes hacer el pago y subir tu comprobante ya mismo, pero procesaremos la carga a primera hora de la mañana. 🌅"
    return ""

# ==========================================
# 🛡️ FILTRO DE PRIVACIDAD (ANTI @USUARIO)
# ==========================================
def filtrar_contacto(texto):
    if not texto:
        return False
    patron_usuario = r"@[a-zA-Z0-9_]+"
    patron_enlace = r"(t\.me|telegram\.me)"
    if re.search(patron_usuario, texto) or re.search(patron_enlace, texto):
        return True
    return False

# ==========================================
# 📱 TECLADOS Y MENÚS INTERACTIVOS
# ==========================================
def menu_principal():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🔍 Buscar Citas"), types.KeyboardButton("👤 Mi Perfil"))
    markup.add(types.KeyboardButton("🪙 Recargar Monedas"), types.KeyboardButton("💰 Retirar Fondos"))
    markup.add(types.KeyboardButton("🔊 Invitar Amigos"), types.KeyboardButton("🏆 Top Compradores"))
    markup.add(types.KeyboardButton("🎁 Top Regalos"))
    return markup

def menu_chat_activo():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🎁 Enviar Regalo"), types.KeyboardButton("👤 Ver Perfil de mi Cita"))
    markup.add(types.KeyboardButton("❌ Terminar Chat"))
    return markup

# ==========================================
# 🚀 COMANDO DE INICIO Y FLUJO DE REGISTRO
# ==========================================
@bot.message_handler(commands=['start'])
def inicio(message):
    chat_id = message.chat.id
    texto = message.text.split()
    
    conn, cursor = conectar_db()
    cursor.execute("SELECT estado FROM usuarios WHERE id_telegram = ?", (chat_id,))
    user = cursor.fetchone()
    
    if not user:
        id_invitador = None
        if len(texto) > 1 and texto[1].isdigit():
            id_invitador = int(texto[1])
            if id_invitador == chat_id:
                id_invitador = None

        cursor.execute("INSERT INTO usuarios (id_telegram, estado, descripcion) VALUES (?, 'reg_nombre', ?)", (chat_id, f"REF:{id_invitador}" if id_invitador else ""))
        conn.commit()
        bot.send_message(chat_id, "¡Bienvenido al Bot de Citas! 👋\nVamos a armar tu perfil para que empieces a conocer gente.\n\n¿Cómo te llamas?")
    else:
        actualizar_estado(chat_id, "normal")
        bot.send_message(chat_id, "¡Hola de nuevo! Usa el panel inferior para navegar.", reply_markup=menu_principal())
    conn.close()

@bot.message_handler(func=lambda m: obtener_estado(m.chat.id) == 'reg_nombre')
def reg_nombre(message):
    chat_id = message.chat.id
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET nombre = ?, estado = 'reg_edad' WHERE id_telegram = ?", (message.text, chat_id))
    conn.commit()
    conn.close()
    bot.send_message(chat_id, f"Encantado, {message.text}. ¿Qué edad tienes? (Envía solo números)")

@bot.message_handler(func=lambda m: obtener_estado(m.chat.id) == 'reg_edad')
def reg_edad(message):
    chat_id = message.chat.id
    if not message.text.isdigit():
        bot.send_message(chat_id, "Por favor, introduce una edad válida en números.")
        return
    
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET edad = ?, estado = 'reg_genero' WHERE id_telegram = ?", (int(message.text), chat_id))
    conn.commit()
    conn.close()
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Hombre 👱‍♂️", callback_data="gen_Hombre"),
               types.InlineKeyboardButton("Mujer 👩‍🦰", callback_data="gen_Mujer"))
    bot.send_message(chat_id, "Selecciona tu género:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('gen_'))
def reg_genero(call):
    chat_id = call.message.chat.id
    genero = call.data.split('_')[1]
    
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET genero = ?, estado = 'reg_busca' WHERE id_telegram = ?", (genero, chat_id))
    conn.commit()
    conn.close()
    
    bot.delete_message(chat_id, call.message.message_id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Hombres 👱‍♂️", callback_data="busca_Hombre"),
               types.InlineKeyboardButton("Mujeres 👩‍🦰", callback_data="busca_Mujer"),
               types.InlineKeyboardButton("Ambos 🧑‍🤝‍🧑", callback_data="busca_Ambos"))
    bot.send_message(chat_id, "¿A quién te interesa conocer?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('busca_'))
def reg_busca(call):
    chat_id = call.message.chat.id
    busca = call.data.split('_')[1]
    
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET busca = ?, estado = 'reg_desc' WHERE id_telegram = ?", (busca, chat_id))
    conn.commit()
    conn.close()
    
    bot.delete_message(chat_id, call.message.message_id)
    bot.send_message(chat_id, "Escribe una descripción breve sobre ti (tus gustos, pasatiempos, qué buscas):")

@bot.message_handler(func=lambda m: obtener_estado(m.chat.id) == 'reg_desc')
def reg_desc(message):
    chat_id = message.chat.id
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET descripcion = ?, estado = 'reg_ciudad' WHERE id_telegram = ?", (message.text, chat_id))
    conn.commit()
    conn.close()
    bot.send_message(chat_id, "📍 ¿En qué ciudad o municipio te encuentras? (Ej: Arboletes, Antioquia)")

@bot.message_handler(func=lambda m: obtener_estado(m.chat.id) == 'reg_ciudad')
def reg_ciudad(message):
    chat_id = message.chat.id
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET ciudad = ?, estado = 'reg_foto' WHERE id_telegram = ?", (message.text, chat_id))
    conn.commit()
    conn.close()
    bot.send_message(chat_id, "Por último, envía una foto tuya para mostrar en tu tarjeta de perfil 📸")

@bot.message_handler(content_types=['photo'], func=lambda m: obtener_estado(m.chat.id) == 'reg_foto')
def reg_foto(message):
    chat_id = message.chat.id
    foto_id = message.photo[-1].file_id
    
    conn, cursor = conectar_db()
    cursor.execute("SELECT descripcion FROM usuarios WHERE id_telegram = ?", (chat_id,))
    res_ref = cursor.fetchone()
    
    id_invitador = None
    if res_ref and res_ref[0] and res_ref[0].startswith("REF:"):
        partes = res_ref[0].split(":")
        if len(partes) > 1 and partes[1] != "None":
            id_invitador = int(partes[1])

    cursor.execute("UPDATE usuarios SET foto_id = ?, estado = 'normal' WHERE id_telegram = ?", (foto_id, chat_id))
    conn.commit()
    
    if id_invitador:
        try:
            cursor.execute("UPDATE usuarios SET monedas = monedas + 50 WHERE id_telegram = ?", (id_invitador,))
            conn.commit()
            bot.send_message(id_invitador, "🔔 **¡Un nuevo amigo se registró con tu enlace!**\nSe han sumado `50 monedas` 🪙 de regalo a tu balance para usar dentro del bot.", parse_mode="Markdown")
        except Exception as e:
            print(f"Error al otorgar referido: {e}")

    conn.close()
    bot.send_message(chat_id, "🎉 ¡Perfil creado con éxito! Te regalamos **50 monedas** iniciales para interactuar.", reply_markup=menu_principal())

# ==========================================
# 🔍 ENGINE DE MATCH Y SWIPE (CITAS ALEATORIAS)
# ==========================================
def obtener_siguiente_perfil(chat_id):
    conn, cursor = conectar_db()
    cursor.execute("SELECT busca FROM usuarios WHERE id_telegram = ?", (chat_id,))
    res = cursor.fetchone()
    if not res:
        conn.close()
        return None
    
    que_busca = res[0]
    query = """
        SELECT id_telegram, nombre, edad, descripcion, ciudad, foto_id 
        FROM usuarios 
        WHERE id_telegram != ? AND estado != 'registro'
        AND id_telegram NOT IN (SELECT para_id FROM interacciones WHERE de_id = ?)
    """
    parametros = [chat_id, chat_id]
    if que_busca != "Ambos":
        query += " AND genero = ?"
        parametros.append(que_busca)
        
    query += " ORDER BY RANDOM() LIMIT 1"
    cursor.execute(query, parametros)
    perfil = cursor.fetchone()
    conn.close()
    return perfil

def mostrar_perfil_a_votar(chat_id):
    perfil = obtener_siguiente_perfil(chat_id)
    if not perfil:
        bot.send_message(chat_id, "✨ No hay perfiles nuevos por el momento. ¡Vuelve a intentar más tarde!")
        return
        
    id_perfil, nombre, edad, descripcion, ciudad, foto_id = perfil
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("❌ Pasar", callback_data=f"sw_dislike_{id_perfil}"),
               types.InlineKeyboardButton(f"💚 Like ({COSTO_LIKE} 🪙)", callback_data=f"sw_like_{id_perfil}"))
    
    ciudad_txt = ciudad if ciudad else "No especificada"
    texto = f"🔥 **{nombre}**, {edad} años\n📍 Ubicación: `{ciudad_txt}`\n\n📝 _{descripcion}_"
    if foto_id:
        bot.send_photo(chat_id, foto_id, caption=texto, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('sw_'))
def procesar_swipe(call):
    chat_id = call.message.chat.id
    accion = call.data.split('_')[1]
    id_votado = int(call.data.split('_')[2])
    
    bot.delete_message(chat_id, call.message.message_id)
    conn, cursor = conectar_db()
    
    if accion == "dislike":
        cursor.execute("INSERT OR REPLACE INTO interacciones (de_id, para_id, tipo) VALUES (?, ?, 'dislike')", (chat_id, id_votado))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Pasado ❌")
        mostrar_perfil_a_votar(chat_id)
        return
        
    elif accion == "like":
        pago, saldo = cobrar_monedas(chat_id, COSTO_LIKE)
        if not pago:
            conn.close()
            bot.answer_callback_query(call.id, "❌ Saldo insuficiente")
            bot.send_message(chat_id, "⚠️ No posees monedas suficientes para dar Like. ¡Usa el menú para recargar saldo!")
            return
            
        cursor.execute("INSERT OR REPLACE INTO interacciones (de_id, para_id, tipo) VALUES (?, ?, 'like')", (chat_id, id_votado))
        conn.commit()
        bot.answer_callback_query(call.id, f"¡Like! Saldo: {saldo} 🪙")
        
        cursor.execute("SELECT tipo FROM interacciones WHERE de_id = ? AND para_id = ?", (id_votado, chat_id))
        inverso = cursor.fetchone()
        
        if inverso and inverso[0] == 'like':
            cursor.execute("INSERT OR REPLACE INTO chats_activos (user1_id, user2_id) VALUES (?, ?)", (chat_id, id_votado))
            cursor.execute("UPDATE usuarios SET estado = 'chateando' WHERE id_telegram IN (?, ?)", (chat_id, id_votado))
            conn.commit()
            conn.close()
            
            bot.send_message(chat_id, "🥳 **¡ES UN MATCH MUTUO!** 🎉\nSe abrió el chat privado intermediado. ¡Cada acción o multimedia enviado costará 1 moneda!", reply_markup=menu_chat_activo(), parse_mode="Markdown")
            bot.send_message(id_votado, "🥳 **¡ALGUIEN TE CORRESPONDIÓ EL LIKE!** 🎉\nSe habilitó el canal privado de chat. ¡Comiencen a hablar!", reply_markup=menu_chat_activo(), parse_mode="Markdown")
            return
            
        conn.close()
        mostrar_perfil_a_votar(chat_id)

# ==========================================
# 💬 CHAT PRIVADO MULTIMEDIA CON NOMBRE ADAPTATIVO
# ==========================================
def obtener_nombre_usuario(chat_id):
    """Auxiliar para extraer el nombre personalizado de la base de datos"""
    conn, cursor = conectar_db()
    cursor.execute("SELECT nombre FROM usuarios WHERE id_telegram = ?", (chat_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else "Cita"

def enviar_multimedia_con_cobro(message, tipo_contenido, enviar_func, *args, **kwargs):
    chat_id = message.chat.id
    conn, cursor = conectar_db()
    cursor.execute("SELECT user1_id, user2_id FROM chats_activos WHERE user1_id = ? OR user2_id = ?", (chat_id, chat_id))
    pareja = cursor.fetchone()
    
    if not pareja:
        conn.close()
        actualizar_estado(chat_id, "normal")
        bot.send_message(chat_id, "El chat ha finalizado.", reply_markup=menu_principal())
        return
        
    receptor = pareja[1] if pareja[0] == chat_id else pareja[0]
    conn.close()

    pago_exitoso, _ = cobrar_monedas(chat_id, COSTO_MENSAJE)
    if pago_exitoso:
        enviar_func(receptor, *args, **kwargs)
    else:
        bot.send_message(chat_id, f"⚠️ **¡Te has quedado sin monedas!**\n\nEnviar cualquier elemento cuesta `{COSTO_MENSAJE} moneda` 🪙.\nUsa el menú principal para recargar.")

# 1. Mensajes de Texto Normales y Botones
@bot.message_handler(content_types=['text'], func=lambda m: obtener_estado(m.chat.id) == 'chateando')
def manejar_chat_texto(message):
    chat_id = message.chat.id
    texto = message.text

    if texto == "🎁 Enviar Regalo":
        markup = types.InlineKeyboardMarkup(row_width=2)
        btns = [types.InlineKeyboardButton(f"{inf['nombre']} ({inf['precio']}🪙)", callback_data=f"reg_{k}") for k, inf in CATALOGO_REGALOS.items()]
        markup.add(*btns)
        bot.send_message(chat_id, "💎 **Tienda de Regalos**\nElige un detalle para tu cita:", reply_markup=markup, parse_mode="Markdown")
        return
    elif texto == "👤 Ver Perfil de mi Cita":
        conn, cursor = conectar_db()
        cursor.execute("SELECT user1_id, user2_id FROM chats_activos WHERE user1_id = ? OR user2_id = ?", (chat_id, chat_id))
        pareja = cursor.fetchone()
        if pareja:
            receptor = pareja[1] if pareja[0] == chat_id else pareja[0]
            
            cursor.execute("SELECT nombre, edad, descripcion, ciudad, foto_id FROM usuarios WHERE id_telegram = ?", (receptor,))
            n, e, d, c, f = cursor.fetchone()
            
            cursor.execute("SELECT COUNT(*) FROM solicitudes_recarga WHERE id_telegram = ? AND estado = 'aprobada'", (receptor,))
            total_recargas_cita = cursor.fetchone()[0]
            rango_cita = calcular_rango_vip(total_recargas_cita)
            
            c_txt = c if c else "No especificada"
            txt = (
                f"👤 **Perfil de tu cita:**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🎖️ **Rango:** {rango_cita}\n"
                f"🔥 **Nombre:** {n}\n"
                f"🎂 **Edad:** {e} años\n"
                f"📍 **Ubicación:** `{c_txt}`\n"
                f"📝 **Biografía:** _{d}_"
            )
            if f: bot.send_photo(chat_id, f, caption=txt, parse_mode="Markdown")
            else: bot.send_message(chat_id, txt, parse_mode="Markdown")
        conn.close()
        return
    elif texto == "❌ Terminar Chat":
        conn, cursor = conectar_db()
        cursor.execute("SELECT user1_id, user2_id FROM chats_activos WHERE user1_id = ? OR user2_id = ?", (chat_id, chat_id))
        pareja = cursor.fetchone()
        if pareja:
            receptor = pareja[1] if pareja[0] == chat_id else pareja[0]
            cursor.execute("DELETE FROM chats_activos WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)", (chat_id, receptor, receptor, chat_id))
            cursor.execute("UPDATE usuarios SET estado = 'normal' WHERE id_telegram IN (?, ?)", (chat_id, receptor))
            conn.commit()
            bot.send_message(chat_id, "❌ Has cerrado la conversación.", reply_markup=menu_principal())
            bot.send_message(receptor, "❌ Tu cita ha cerrado la conversación.", reply_markup=menu_principal())
        conn.close()
        return

    if filtrar_contacto(texto):
        bot.send_message(chat_id, "🚫 **Acción bloqueada:** Por motivos de seguridad no está permitido enviar nombres de usuario (@) ni enlaces de contacto.")
        return

    # Extrae el nombre configurado del emisor para mostrarlo dinámicamente en el chat del receptor
    nombre_emisor = obtener_nombre_usuario(chat_id)
    enviar_multimedia_con_cobro(message, "text", bot.send_message, text=f"💬 **{nombre_emisor}:** {texto}", parse_mode="Markdown")

# 2. Envío de Fotos
@bot.message_handler(content_types=['photo'], func=lambda m: obtener_estado(m.chat.id) == 'chateando')
def manejar_chat_foto(message):
    chat_id = message.chat.id
    caption = message.caption
    if filtrar_contacto(caption):
        bot.send_message(chat_id, "🚫 **Acción bloqueada:** No puedes incluir un @usuario en la descripción de la foto.")
        return
    foto_id = message.photo[-1].file_id
    nombre_emisor = obtener_nombre_usuario(chat_id)
    texto_final = f"📸 **Foto de {nombre_emisor}**" + (f": {caption}" if caption else "")
    enviar_multimedia_con_cobro(message, "photo", bot.send_photo, photo=foto_id, caption=texto_final, parse_mode="Markdown")

# 3. Envío de Videos y Video Notas
@bot.message_handler(content_types=['video', 'video_note'], func=lambda m: obtener_estado(m.chat.id) == 'chateando')
def manejar_chat_video(message):
    chat_id = message.chat.id
    caption = message.caption
    if filtrar_contacto(caption):
        bot.send_message(chat_id, "🚫 **Acción bloqueada:** No puedes incluir un @usuario en la descripción de este video.")
        return
    video_id = message.video.file_id if message.video else message.video_note.file_id
    nombre_emisor = obtener_nombre_usuario(chat_id)
    if message.video:
        texto_final = f"🎥 **Video de {nombre_emisor}**" + (f": {caption}" if caption else "")
        enviar_multimedia_con_cobro(message, "video", bot.send_video, video=video_id, caption=texto_final, parse_mode="Markdown")
    else:
        enviar_multimedia_con_cobro(message, "video_note", bot.send_video_note, video_note=video_id)

# 4. Envío de Stickers
@bot.message_handler(content_types=['sticker'], func=lambda m: obtener_estado(m.chat.id) == 'chateando')
def manejar_chat_sticker(message):
    sticker_id = message.sticker.file_id
    enviar_multimedia_con_cobro(message, "sticker", bot.send_sticker, sticker=sticker_id)

# ==========================================
# 💎 TRANSFERENCIA Y LÓGICA DE REGALOS
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('reg_'))
def procesar_envio_regalo(call):
    chat_id = call.message.chat.id
    tipo_regalo = call.data.split('_')[1]
    
    conn, cursor = conectar_db()
    cursor.execute("SELECT user1_id, user2_id FROM chats_activos WHERE user1_id = ? OR user2_id = ?", (chat_id, chat_id))
    pareja = cursor.fetchone()
    if not pareja:
        bot.answer_callback_query(call.id, "Chat inactivo.")
        conn.close()
        return
    receptor = pareja[1] if pareja[0] == chat_id else pareja[0]
    
    costo = CATALOGO_REGALOS[tipo_regalo]["precio"]
    cursor.execute("SELECT monedas FROM usuarios WHERE id_telegram = ?", (chat_id,))
    saldo_emisor = cursor.fetchone()[0]
    
    if saldo_emisor < costo:
        conn.close()
        bot.answer_callback_query(call.id, "❌ No tienes monedas suficientes.")
        return
        
    cursor.execute("UPDATE usuarios SET monedas = monedas - ? WHERE id_telegram = ?", (costo, chat_id))
    cursor.execute("UPDATE usuarios SET monedas_regalo = monedas_regalo + ? WHERE id_telegram = ?", (costo, receptor))
    
    # Insertar el registro en el historial para controlar el Top de Regalos
    cursor.execute("INSERT INTO regalos_enviados (de_id, para_id, tipo_regalo, valor_monedas) VALUES (?, ?, ?, ?)", 
                   (chat_id, receptor, tipo_regalo, costo))
    
    conn.commit()
    conn.close()
    
    bot.answer_callback_query(call.id, "¡Enviado! 🎁")
    bot.send_message(chat_id, f"✅ Le regalaste un {CATALOGO_REGALOS[tipo_regalo]['nombre']} a tu cita.")
    bot.send_message(receptor, f"🎁 **¡Felicidades!** Te enviaron un **{CATALOGO_REGALOS[tipo_regalo]['nombre']}**. Sumaste **{costo} monedas retirables** a tu balance.")

# ==========================================
# 💵 RECARGAS MANUALES PROTEGIDAS
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def procesar_solicitud_compra(call):
    chat_id = call.message.chat.id
    pack = call.data.split('_')[1] + "_" + call.data.split('_')[2]
    monedas = PAQUETES_MONEDAS[pack]["monedas"]
    
    aviso_noche = obtener_aviso_horario()
    
    txt = (
        f"💳 **Datos de Pago para adquirir {monedas} Monedas:**\n\n"
        f"📱 **Nequi (Colombia):** Envía por la app al número `3187861907`\n"
        f"👤 **Nombre del Comercio:** `CitasBot CO`\n"
        f"🅿️ **PayPal Business:** Transfiere vía: `paypal.me/jonaikerRivas205`\n\n"
        f"⚠️ **IMPORTANTE:** Una vez finalizada la transferencia, tómale un pantallazo al comprobante de pago y **envía la foto directamente aquí en este chat**."
        f"{aviso_noche}"
    )
    bot.send_message(chat_id, txt, parse_mode="Markdown")
    actualizar_estado(chat_id, f"wait_comprobante_{monedas}")

@bot.message_handler(content_types=['photo'], func=lambda m: obtener_estado(m.chat.id).startswith('wait_comprobante_'))
def recibir_comprobante(message):
    chat_id = message.chat.id
    monedas = int(obtener_estado(chat_id).split('_')[2])
    foto_id = message.photo[-1].file_id
    
    conn, cursor = conectar_db()
    cursor.execute("INSERT INTO solicitudes_recarga (id_telegram, cantidad_monedas, comprobante_foto_id) VALUES (?, ?, ?)", (chat_id, monedas, foto_id))
    sol_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    actualizar_estado(chat_id, "normal")
    bot.send_message(chat_id, "✅ **Comprobante recibido.** Tu saldo se actualizará en cuanto se valide el pago.")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Aprobar", callback_data=f"adm_aprob_rec_{sol_id}"),
               types.InlineKeyboardButton("❌ Rechazar", callback_data=f"adm_rech_rec_{sol_id}"))
    
    texto_canal = (
        f"🚨 **NUEVA RECARGA DE MONEDAS** 🚨\n\n"
        f"👤 **Usuario ID:** `{chat_id}`\n"
        f"🪙 **Monto:** {monedas} Monedas\n"
        f"🆔 **Fila ID:** #{sol_id}\n\n"
        f"📌 _Revisa tu Nequi o PayPal antes de aprobar._"
    )
    bot.send_photo(ID_CANAL_SOLICITUDES, foto_id, caption=texto_canal, reply_markup=markup, parse_mode="Markdown")

# ==========================================
# 💰 RETIROS MÍNIMOS
# ==========================================
def panel_retiros(chat_id):
    conn, cursor = conectar_db()
    cursor.execute("SELECT monedas_regalo FROM usuarios WHERE id_telegram = ?", (chat_id,))
    saldo_retirable = cursor.fetchone()[0]
    conn.close()
    
    saldo_en_dolares = saldo_retirable / 100.0
    
    if saldo_retirable < MINIMO_RETIRABLE_MONEDAS:
        bot.send_message(
            chat_id, 
            f"⚠️ **Retiro mínimo no alcanzado.**\n\n"
            f"El monto mínimo para retirar es de **$25 USD** ({MINIMO_RETIRABLE_MONEDAS} monedas ganadas en regalos).\n"
            f"Tu saldo retirable actual es de: **{saldo_retirable} 🪙** (Equivale a **${saldo_en_dolares:.2f} USD**).\n\n"
            f"📌 _Nota: Las monedas iniciales o por referidos son para interactuar dentro del bot; solo se retira lo acumulado por regalos enviados de otros usuarios._ 🎁"
        )
        return
        
    bot.send_message(
        chat_id, 
        f"💰 **¡Felicidades! Tienes saldo disponible para retirar.**\n"
        f"Balance Retirable: `{saldo_retirable} monedas` (Equivale a **${saldo_en_dolares:.2f} USD**).\n\n"
        f"⚠️ **Nota sobre comisiones:**\n"
        f"• 📱 **Nequi:** Cobro 100% gratis sin costos extras.\n"
        f"• 🅿️ **PayPal:** Se restará la tasa de envío de la plataforma de tus fondos.\n\n"
        f"Escribe tu método de pago preferido para recibir tu dinero real (Ej: Correo de PayPal o número Nequi con nombre y cédula):"
    )
    actualizar_estado(chat_id, "wait_retiro_datos")

@bot.message_handler(func=lambda m: obtener_estado(m.chat.id) == 'wait_retiro_datos')
def procesar_datos_retiro(message):
    chat_id = message.chat.id
    datos = message.text
    
    conn, cursor = conectar_db()
    cursor.execute("SELECT monedas_regalo FROM usuarios WHERE id_telegram = ?", (chat_id,))
    saldo = cursor.fetchone()[0]
    
    cursor.execute("UPDATE usuarios SET monedas_regalo = 0 WHERE id_telegram = ?", (chat_id,))
    cursor.execute("INSERT INTO solicitudes_retiro (id_telegram, cantidad_monedas, datos_pago) VALUES (?, ?, ?)", (chat_id, saldo, datos))
    sol_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    actualizar_estado(chat_id, "normal")
    bot.send_message(chat_id, "✅ **Retiro registrado.** Tu saldo ha sido congelado y será transferido en un lapso de 24 a 48 horas.")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Confirmar Pago", callback_data=f"adm_aprob_ret_{sol_id}"),
               types.InlineKeyboardButton("❌ Rechazar / Reversar", callback_data=f"adm_rech_ret_{sol_id}"))
    
    texto_canal = (
        f"💸 **SOLICITUD DE RETIRO DE EFECTIVO** 💸\n\n"
        f"👤 **Usuario ID:** `{chat_id}`\n"
        f"🪙 **Monedas a cambiar:** {saldo}\n"
        f"💵 **Valor Neto a Pagar:** **${saldo/100.0:.2f} USD**\n"
        f"🏦 **Datos de Envío:**\n`{datos}`\n\n"
        f"📌 _Haz la transferencia manual y luego confirma aquí abajo._"
    )
    bot.send_message(ID_CANAL_SOLICITUDES, texto_canal, reply_markup=markup, parse_mode="Markdown")

# ==========================================
# 🛠️ PANEL DE ACCIONES DIRECTAS EN EL CANAL
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def controlador_admin(call):
    partes = call.data.split('_')
    accion, tipo, sol_id = partes[1], partes[2], int(partes[3])
    
    conn, cursor = conectar_db()
    
    if tipo == "rec":
        cursor.execute("SELECT id_telegram, cantidad_monedas, estado FROM solicitudes_recarga WHERE id = ?", (sol_id,))
        sol = cursor.fetchone()
        if not sol or sol[2] != 'pendiente':
            bot.answer_callback_query(call.id, "Ya gestionada.")
            conn.close()
            return
            
        u_id, mon, _ = sol
        if accion == "aprob":
            cursor.execute("UPDATE solicitudes_recarga SET estado = 'aprobada' WHERE id = ?", (sol_id,))
            cursor.execute("UPDATE usuarios SET monedas = monedas + ? WHERE id_telegram = ?", (mon, u_id))
            conn.commit()
            bot.edit_message_caption(chat_id=ID_CANAL_SOLICITUDES, message_id=call.message.message_id, caption=call.message.caption + "\n\n🟢 **APROBADA**")
            bot.send_message(u_id, f"🎉 ¡Pago verificado! Adquiriste **{mon} monedas** con éxito.")
        else:
            cursor.execute("UPDATE solicitudes_recarga SET estado = 'rechazada' WHERE id = ?", (sol_id,))
            conn.commit()
            bot.edit_message_caption(chat_id=ID_CANAL_SOLICITUDES, message_id=call.message.message_id, caption=call.message.caption + "\n\n🔴 **RECHAZADA**")
            bot.send_message(u_id, "❌ Tu comprobante de recarga fue rechazado por la administración.")
            
    elif tipo == "ret":
        cursor.execute("SELECT id_telegram, cantidad_monedas, estado FROM solicitudes_retiro WHERE id = ?", (sol_id,))
        sol = cursor.fetchone()
        if not sol or sol[2] != 'pendiente':
            bot.answer_callback_query(call.id, "Ya gestionada.")
            conn.close()
            return
            
        u_id, mon, _ = sol
        if accion == "aprob":
            cursor.execute("UPDATE solicitudes_retiro SET estado = 'pagado' WHERE id = ?", (sol_id,))
            conn.commit()
            bot.edit_message_text(call.message.text + "\n\n🟢 **PAGADO Y CERRADO**", chat_id=ID_CANAL_SOLICITUDES, message_id=call.message.message_id)
            bot.send_message(u_id, f"💰 **¡Tu dinero ha sido enviado!** Tus {mon} monedas fueron procesadas hacia tus cuentas.")
        else:
            cursor.execute("UPDATE solicitudes_retiro SET estado = 'rechazado' WHERE id = ?", (sol_id,))
            cursor.execute("UPDATE usuarios SET monedas_regalo = monedas_regalo + ? WHERE id_telegram = ?", (mon, u_id))
            conn.commit()
            bot.edit_message_text(call.message.text + "\n\n🔴 **RECHAZADO / SALDO REVERSADO**", chat_id=ID_CANAL_SOLICITUDES, message_id=call.message.message_id)
            bot.send_message(u_id, "⚠️ Tu solicitud de retiro fue rechazada. Las monedas retornaron a tu balance retirable.")
            
    conn.close()
    bot.answer_callback_query(call.id, "Acción procesada.")

# ==========================================
# ⚙️ NUEVO FLUJO INTERACTIVO: EDITAR PERFIL
# ==========================================
def menu_editar_perfil():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📝 Nombre", callback_data="edit_nombre"),
        types.InlineKeyboardButton("🎂 Edad", callback_data="edit_edad"),
        types.InlineKeyboardButton("✍️ Descripción", callback_data="edit_desc"),
        types.InlineKeyboardButton("📍 Ciudad", callback_data="edit_ciudad"),
        types.InlineKeyboardButton("📸 Cambiar Foto", callback_data="edit_foto")
    )
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_'))
def procesar_seleccion_edicion(call):
    chat_id = call.message.chat.id
    campo = call.data.split('_')[1]
    
    bot.delete_message(chat_id, call.message.message_id)
    
    if campo == "nombre":
        bot.send_message(chat_id, "✏️ Escribe tu nuevo nombre para el perfil:")
        actualizar_estado(chat_id, "wait_edit_nombre")
    elif campo == "edad":
        bot.send_message(chat_id, "✏️ Envía tu edad real en números:")
        actualizar_estado(chat_id, "wait_edit_edad")
    elif campo == "desc":
        bot.send_message(chat_id, "✏️ Escribe una nueva descripción para tu biografía:")
        actualizar_estado(chat_id, "wait_edit_desc")
    elif campo == "ciudad":
        bot.send_message(chat_id, "✏️ Escribe tu ciudad o ubicación actual (Ej: Arboletes, Antioquia):")
        actualizar_estado(chat_id, "wait_edit_ciudad")
    elif campo == "foto":
        bot.send_message(chat_id, "📸 Envía una nueva fotografía nítida para tu tarjeta:")
        actualizar_estado(chat_id, "wait_edit_foto")
    bot.answer_callback_query(call.id)

# Controladores de captura de datos de edición
@bot.message_handler(func=lambda m: obtener_estado(m.chat.id).startswith('wait_edit_'))
def capturar_edicion_perfil(message):
    chat_id = message.chat.id
    estado_actual = obtener_estado(chat_id)
    campo = estado_actual.split('_')[2]
    valor = message.text
    
    conn, cursor = conectar_db()
    
    if campo == "nombre":
        cursor.execute("UPDATE usuarios SET nombre = ? WHERE id_telegram = ?", (valor, chat_id))
    elif campo == "edad":
        if not valor.isdigit():
            conn.close()
            bot.send_message(chat_id, "❌ Por favor introduce solo números enteros para la edad.")
            return
        cursor.execute("UPDATE usuarios SET edad = ? WHERE id_telegram = ?", (int(valor), chat_id))
    elif campo == "desc":
        cursor.execute("UPDATE usuarios SET descripcion = ? WHERE id_telegram = ?", (valor, chat_id))
    elif campo == "ciudad":
        cursor.execute("UPDATE usuarios SET ciudad = ? WHERE id_telegram = ?", (valor, chat_id))
        
    conn.commit()
    conn.close()
    
    actualizar_estado(chat_id, "normal")
    bot.send_message(chat_id, f"✅ El campo **{campo.capitalize()}** ha sido actualizado correctamente.", reply_markup=menu_principal())

@bot.message_handler(content_types=['photo'], func=lambda m: obtener_estado(m.chat.id) == 'wait_edit_foto')
def capturar_foto_edicion(message):
    chat_id = message.chat.id
    foto_id = message.photo[-1].file_id
    
    conn, cursor = conectar_db()
    cursor.execute("UPDATE usuarios SET foto_id = ? WHERE id_telegram = ?", (foto_id, chat_id))
    conn.commit()
    conn.close()
    
    actualizar_estado(chat_id, "normal")
    bot.send_message(chat_id, "✅ Tu foto de perfil ha sido reemplazada con éxito.", reply_markup=menu_principal())

# ==========================================
# 🗺️ CONTROLADOR INTERNO DE BOTONES DE TEXTO
# ==========================================
@bot.message_handler(func=lambda m: obtener_estado(m.chat.id) == 'normal')
def controlador_menu_principal(message):
    chat_id = message.chat.id
    texto = message.text
    
    if texto == "🔍 Buscar Citas":
        mostrar_perfil_a_votar(chat_id)
    elif texto == "👤 Mi Perfil":
        conn, cursor = conectar_db()
        cursor.execute("SELECT nombre, edad, descripcion, ciudad, monedas, monedas_regalo, foto_id FROM usuarios WHERE id_telegram = ?", (chat_id,))
        n, e, d, c, m, mr, f = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) FROM solicitudes_recarga WHERE id_telegram = ? AND estado = 'aprobada'", (chat_id,))
        total_recargas = cursor.fetchone()[0]
        conn.close()
        
        rango_vip = calcular_rango_vip(total_recargas)
        
        c_txt = c if c else "No especificada"
        txt = (
            f"👤 **Tu Tarjeta de Perfil:**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎖️ **Rango:** {rango_vip}\n"
            f"📛 **Nombre:** {n}\n"
            f"🎂 **Edad:** {e} años\n"
            f"📍 **Ubicación:** `{c_txt}`\n"
            f"📝 **Biografía:** _{d}_\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 **Saldo para usar:** `{m}` monedas.\n"
            f"💰 **Saldo de regalos (Retirable):** `{mr}` monedas (Equivale a **${mr/100.0:.2f} USD**).\n"
            f"📊 **Recargas verificadas:** `{total_recargas}`\n\n"
            f"⚙️ ¿Deseas modificar algún dato? Presiona el botón correspondiente abajo:"
        )
        if f: 
            bot.send_photo(chat_id, f, caption=txt, reply_markup=menu_editar_perfil(), parse_mode="Markdown")
        else: 
            bot.send_message(chat_id, txt, reply_markup=menu_editar_perfil(), parse_mode="Markdown")
        
    elif texto == "🪙 Recargar Monedas":
        markup = types.InlineKeyboardMarkup(row_width=1)
        for k, v in PAQUETES_MONEDAS.items():
            markup.add(types.InlineKeyboardButton(f"🪙 {v['monedas']} Monedas por {v['precio']}", callback_data=f"buy_{k}"))
        bot.send_message(chat_id, "💎 **Elige el pack de monedas que deseas adquirir:**", reply_markup=markup, parse_mode="Markdown")
        
    elif texto == "💰 Retirar Fondos":
        panel_retiros(chat_id)

    elif texto == "🏆 Top Compradores":
        # Se corrigió la query sumando las cantidades históricas para armar la lista más larga de recargas efectivas
        conn, cursor = conectar_db()
        query_top = """
            SELECT u.nombre, SUM(s.cantidad_monedas) as total_historico
            FROM solicitudes_recarga s
            JOIN usuarios u ON s.id_telegram = u.id_telegram
            WHERE s.estado = 'aprobada' 
            GROUP BY s.id_telegram
            ORDER BY total_historico DESC
            LIMIT 10
        """
        cursor.execute(query_top)
        top_usuarios = cursor.fetchall()
        conn.close()
        
        txt_top = "🏆 **TOP 10 COMPRADORES (Lista más larga)** 🏆\n"
        txt_top += "⚡ _Los usuarios que más monedas han recargado_ ⚡\n"
        txt_top += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if not top_usuarios:
            txt_top += "✨ ¡La competencia está abierta! Sin recargas registradas."
        else:
            medallas = ["🥇", "🥈", "🥉", "👑", "✨", "⚡", "💎", "⭐", "🔥", "📌"]
            for i, (nombre, total) in enumerate(top_usuarios):
                medalla = medallas[i] if i < len(medallas) else "🔹"
                nombre_corto = nombre[:15] + "..." if len(nombre) > 15 else nombre
                txt_top += f"{medalla} **Puesto #{i+1}:** {nombre_corto}\n"
                txt_top += f"└ 🪙 Total Recargado: `{total}` monedas\n\n"
                
        txt_top += "━━━━━━━━━━━━━━━━━━━━\n"
        bot.send_message(chat_id, txt_top, parse_mode="Markdown")

    elif texto == "🎁 Top Regalos":
        # Nueva función de consulta para extraer la lista más larga de regalos recibidos (Monedas acumuladas por regalos)
        conn, cursor = conectar_db()
        query_regalos = """
            SELECT u.nombre, SUM(r.valor_monedas) as total_regalos
            FROM regalos_enviados r
            JOIN usuarios u ON r.para_id = u.id_telegram
            GROUP BY r.para_id
            ORDER BY total_regalos DESC
            LIMIT 10
        """
        cursor.execute(query_regalos)
        top_regalos = cursor.fetchall()
        conn.close()

        txt_regalos = "🎁 **TOP 10 REGALOS RECIBIDOS** 🎁\n"
        txt_regalos += "👑 _Los perfiles más populares y queridos del bot_ 👑\n"
        txt_regalos += "━━━━━━━━━━━━━━━━━━━━\n\n"

        if not top_regalos:
            txt_regalos += "✨ Aún no se han enviado regalos en el bot. ¡Sé el primero en consentir a tu cita!"
        else:
            medallas_r = ["👑", "❤️", "💖", "🌹", "💎", "✨", "🎈", "🌸", "⭐", "🔹"]
            for i, (nombre, total) in enumerate(top_regalos):
                medalla = medallas_r[i] if i < len(medallas_r) else "🔹"
                nombre_corto = nombre[:15] + "..." if len(nombre) > 15 else nombre
                txt_regalos += f"{medalla} **Puesto #{i+1}:** {nombre_corto}\n"
                txt_regalos += f"└ 🪙 Monedas en regalos: `{total}`\n\n"

        txt_regalos += "━━━━━━━━━━━━━━━━━━━━\n"
        bot.send_message(chat_id, txt_regalos, parse_mode="Markdown")
        
    elif texto == "🔊 Invitar Amigos":
        bot_info = bot.get_me()
        link_invitacion = f"https://t.me/{bot_info.username}?start={chat_id}"
        
        mensaje_ref = (
            f"📢 **¡GANA MONEDAS GRATIS INVITANDO AMIGOS!** 📢\n\n"
            f"Por cada amigo que invites al bot usando tu enlace, recibirás **50 monedas de regalo** 🪙 automáticas en tu saldo cuando terminen de configurar su tarjeta de perfil.\n\n"
            f"🔗 **Tu enlace único de invitación:**\n`{link_invitacion}`\n\n"
            f"📌 _Nota: Estas monedas son para usar exclusivamente dentro del bot (likes, mensajes, regalos). No suman saldo retirable directo a dólares._"
        )
        bot.send_message(chat_id, mensaje_ref, parse_mode="Markdown")

# Encendido definitivo del Bot
print("🚀 El Bot de Citas de Jonaiker está en línea...")
bot.infinity_polling()