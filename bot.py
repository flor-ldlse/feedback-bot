
# @ldlse / @sswager
# @ldlse / @sswager
# @ldlse / @sswager

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes
)
import logging
import json
import os
import random
from datetime import datetime, timedelta
from config import BOT_TOKEN, ADMINS

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

FEEDBACK_FILE = 'feedback.json'
TICKET_FILE = 'tickets.json'
STATS_FILE = 'stats.json'

banned_users = {}
muted_users = {}

def load_json(file_path, default):
    if not os.path.exists(file_path):
        return default
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return default
            return json.loads(content)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Ошибка при чтении {file_path}: {e}")
        return default

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_tickets():
    return load_json(TICKET_FILE, [])

def save_tickets(data):
    save_json(TICKET_FILE, data)

def load_stats():
    return load_json(STATS_FILE, {})

def save_stats(data):
    save_json(STATS_FILE, data)

def update_stats(topic):
    stats = load_stats()
    stats[topic] = stats.get(topic, 0) + 1
    save_stats(stats)

def is_user_banned(user_id):
    ban_end = banned_users.get(user_id)
    if ban_end is None:
        return False
    if ban_end == 'perm':
        return True
    if datetime.utcnow() > datetime.fromisoformat(ban_end):
        banned_users.pop(user_id)
        return False
    return True

def is_user_muted(user_id):
    mute_end = muted_users.get(user_id)
    if mute_end is None:
        return False
    if mute_end == 'perm':
        return True
    if datetime.utcnow() > datetime.fromisoformat(mute_end):
        muted_users.pop(user_id)
        return False
    return True

def get_priority_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Важно", callback_data='priority_high')],
        [InlineKeyboardButton("⚪ Обычное", callback_data='priority_normal')]
    ])

def get_file_choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 Отправить файл/фото", callback_data='file_yes')],
        [InlineKeyboardButton("🚫 Без файла", callback_data='file_no')]
    ])

def get_message_choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Написать сообщение", callback_data='msg_yes')],
        [InlineKeyboardButton("🚫 Без сообщения", callback_data='msg_no')]
    ])

def get_ticket_status_keyboard(ticket_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("В работе", callback_data=f'status_{ticket_id}_in_progress')],
        [InlineKeyboardButton("Закрыто", callback_data=f'status_{ticket_id}_closed')],
        [InlineKeyboardButton("Отмена", callback_data='admin_cancel')]
    ])

def get_admin_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Баны", callback_data='admin_ban')],
        [InlineKeyboardButton("Мюты", callback_data='admin_mute')],
        [InlineKeyboardButton("Разбанить/Размьютить", callback_data='admin_unban')],
        [InlineKeyboardButton("Просмотреть тикеты", callback_data='admin_tickets')],
    ])

PROCESSING_EMOJIS = ["⌛", "🔄", "🛠️", "⏳", "⚙️"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMINS:
        await update.message.reply_text("Привет, админ! Выберите действие:", reply_markup=get_admin_panel())
    else:
        keyboard = [[InlineKeyboardButton("Отправить обращение", callback_data='send_ticket')]]
        await update.message.reply_text("Привет! Нажмите кнопку для отправки обращения.", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == 'send_ticket':
        if is_user_banned(user_id):
            await query.edit_message_text("Вы забанены и не можете отправлять обращения.")
            return
        if is_user_muted(user_id):
            await query.edit_message_text("Вы замьючены и не можете отправлять обращения.")
            return
        await query.edit_message_text("Пожалуйста, введите тему вашего обращения (коротко).")
        context.user_data['awaiting_topic'] = True

    elif query.data.startswith('priority_') and context.user_data.get('awaiting_priority'):
        priority = 'Высокий' if query.data == 'priority_high' else 'Низкий'
        context.user_data['priority'] = priority
        context.user_data.pop('awaiting_priority', None)
        await query.edit_message_text(f"Выбрана важность: {priority}.\nХотите прикрепить файл или фото?", reply_markup=get_file_choice_keyboard())

    elif query.data == 'file_yes' and context.user_data.get('priority'):
        context.user_data['awaiting_file'] = True
        context.user_data.pop('awaiting_message', None)
        await query.edit_message_text("Отправьте файл или фото.")

    elif query.data == 'file_no' and context.user_data.get('priority'):
        context.user_data.pop('awaiting_file', None)
        await query.edit_message_text("Хотите добавить текстовое сообщение к обращению?", reply_markup=get_message_choice_keyboard())

    elif query.data == 'msg_yes' and context.user_data.get('priority'):
        context.user_data['awaiting_message'] = True
        await query.edit_message_text("Пожалуйста, напишите сообщение к обращению.")

    elif query.data == 'msg_no' and context.user_data.get('priority'):
        context.user_data.pop('awaiting_message', None)
        await process_ticket_full(update, context, "")

    elif user_id in ADMINS:
        if query.data == 'admin_ban':
            await query.edit_message_text("Введите user_id и время бана в минутах через пробел, или perm.\n/cancel для отмены")
            context.user_data['admin_action'] = 'ban'

        elif query.data == 'admin_mute':
            await query.edit_message_text("Введите user_id и время мута в минутах через пробел или perm.\n/cancel для отмены")
            context.user_data['admin_action'] = 'mute'

        elif query.data == 'admin_unban':
            await query.edit_message_text("Введите user_id для снятия бана/мьюта.\n/cancel для отмены")
            context.user_data['admin_action'] = 'unban'

        elif query.data == 'admin_tickets':
            tickets = load_tickets()
            if not tickets:
                await query.edit_message_text("Нет активных тикетов.")
                return
            keyboard = []
            for t in tickets:
                label = f"#{t['id']} {t['topic']} ({t['priority']}) [{t['status']}]"
                keyboard.append([InlineKeyboardButton(label, callback_data=f'admin_answer_{t["id"]}')])
            keyboard.append([InlineKeyboardButton("Отмена", callback_data='admin_cancel')])
            await query.edit_message_text("Выберите тикет для ответа:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data.startswith('admin_answer_'):
            ticket_id = int(query.data.split('_')[-1])
            tickets = load_tickets()
            ticket = next((t for t in tickets if t['id'] == ticket_id), None)
            if not ticket:
                await query.answer("Тикет не найден")
                return
            context.user_data['answer_ticket_id'] = ticket_id
            await query.edit_message_text(f'Введите ответ для тикета #{ticket_id} (тема: {ticket["topic"]}):\n"{ticket["message"][:100]}"' if ticket["message"] else "(без текста)")

        elif query.data.startswith('status_'):
            parts = query.data.split('_')
            if len(parts) < 3:
                await query.answer("Неверные данные")
                return
            ticket_id = int(parts[1])
            new_status = parts[2]
            tickets = load_tickets()
            for t in tickets:
                if t['id'] == ticket_id:
                    display_status = "В обработке" if new_status == "in_progress" else ("Закрыто" if new_status == "closed" else new_status)
                    t['status'] = display_status
                    save_tickets(tickets)
                    await query.edit_message_text(f"Тикет {ticket_id} сменил статус на: {display_status}")
                    try:
                        if new_status == "in_progress":
                            emoji = random.choice(["⌛", "🔄", "🛠️", "⏳", "⚙️"])
                            await context.bot.send_message(chat_id=t['user_id'], text=f"Ваш тикет в обработке {emoji}")
                        else:
                            await context.bot.send_message(chat_id=t['user_id'], text=f"Ваш тикет #{ticket_id} изменил статус на: {display_status}.")
                    except Exception as e:
                        logger.error(f"Ошибка уведомления пользователя: {e}")
                    return
            await query.answer("Тикет не найден")

        elif query.data == 'admin_cancel':
            await query.edit_message_text("Действие отменено.")
            context.user_data.clear()

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Действие отменено.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.user_data.get('awaiting_topic'):
        topic_text = update.message.text
        if not topic_text or len(topic_text.strip()) < 3:
            await update.message.reply_text("Тема слишком короткая, попробуйте заново.")
            return
        context.user_data['topic'] = topic_text.strip()
        del context.user_data['awaiting_topic']
        context.user_data['awaiting_priority'] = True
        await update.message.reply_text("Выберите приоритет:", reply_markup=get_priority_keyboard())
        return

    if context.user_data.get('awaiting_file'):
        if is_user_banned(user_id) or is_user_muted(user_id):
            await update.message.reply_text("Вы не можете отправлять обращения.")
            context.user_data.clear()
            return
        file_id = None
        file_type = None
        if update.message.document:
            file_id = update.message.document.file_id
            file_type = 'document'
        elif update.message.photo:
            file_id = update.message.photo[-1].file_id
            file_type = 'photo'
        else:
            await update.message.reply_text("Пожалуйста, отправьте файл или фото.")
            return
        context.user_data['file_id'] = file_id
        context.user_data['file_type'] = file_type
        del context.user_data['awaiting_file']
        await update.message.reply_text("Хотите добавить текстовое сообщение к обращению?", reply_markup=get_message_choice_keyboard())
        return

    if user_id in ADMINS and 'answer_ticket_id' in context.user_data:
        ticket_id = context.user_data['answer_ticket_id']
        tickets = load_tickets()
        ticket = next((t for t in tickets if t['id'] == ticket_id), None)
        if not ticket:
            await update.message.reply_text("Тикет не найден.")
            context.user_data.pop('answer_ticket_id')
            return
        try:
            await context.bot.send_message(chat_id=ticket['user_id'], text=f"Ответ на твой тикет #{ticket_id}:\n{update.message.text}")
            await update.message.reply_text("Ответ отправлен пользователю.")
        except Exception as e:
            logger.error(f"Ошибка отправки ответа: {e}")
            await update.message.reply_text("Ошибка при отправке ответа.")
        context.user_data.pop('answer_ticket_id')
        return

    if context.user_data.get('awaiting_message') is not None:
        if is_user_banned(user_id) or is_user_muted(user_id):
            await update.message.reply_text("Вы не можете отправлять обращения.")
            context.user_data.clear()
            return
        msg_text = update.message.text or ''
        await process_ticket_full(update, context, msg_text)
        context.user_data.clear()

async def process_ticket_full(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await update.message.reply_text("Ошибка определения пользователя.")
        return
    file_id = context.user_data.get('file_id')
    file_type = context.user_data.get('file_type')
    priority = context.user_data.get('priority', 'Низкий')
    topic = context.user_data.get('topic', 'Общее')

    tickets = load_tickets()
    ticket_id = (tickets[-1]['id'] + 1) if tickets else 1

    ticket = {
        "id": ticket_id,
        "user_id": user_id,
        "user_name": update.effective_user.full_name if update.effective_user else "Неизвестный",
        "message": message_text,
        "file_id": file_id,
        "file_type": file_type,
        "priority": priority,
        "topic": topic,
        "status": "Получено",
        "created_at": datetime.utcnow().isoformat()
    }

    tickets.append(ticket)
    save_tickets(tickets)
    update_stats(topic)

    if update.message:
        await update.message.reply_text(f"Спасибо! Ваш тикет #{ticket_id} принят с приоритетом: {priority}.")
    elif update.callback_query:
        await update.callback_query.message.reply_text(f"Спасибо! Ваш тикет #{ticket_id} принят с приоритетом: {priority}.")

    for admin_id in ADMINS:
        try:
            msg = (
                f"📩 Новый тикет #{ticket_id}\n"
                f"Пользователь: {ticket['user_name']} (ID: {user_id})\n"
                f"Приоритет: {priority}\n"
                f"Тема: {topic}\n"
                f"Статус: {ticket['status']}\n\n"
                f"Сообщение:\n{ticket['message'].strip() or '(прикреплен файл)'}"
            )
            if file_id:
                if file_type == "document":
                    await context.bot.send_document(chat_id=admin_id, document=file_id, caption=msg)
                elif file_type == "photo":
                    await context.bot.send_photo(chat_id=admin_id, photo=file_id, caption=msg)
            else:
                await context.bot.send_message(chat_id=admin_id, text=msg)

            await context.bot.send_message(chat_id=admin_id, text="Управление тикетом:", reply_markup=get_ticket_status_keyboard(ticket_id))
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админам: {e}")

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL | filters.PHOTO, message_handler))

    application.run_polling()

if __name__ == "__main__":
    main()

# @ldlse / @sswager