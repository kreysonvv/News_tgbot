#!/usr/bin/env python3

import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton 
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import vk_api
import time

# Введите ваши токены
TELEGRAM_TOKEN =  'ВАШ_ТОКЕН'
VK_ACCESS_TOKEN = 'ВАШ_ОТКРЫТЫЙ_ТОКЕН'
GROUP_IDS = [
    ('ID 1', 'Название группы 1'),
    ('ID 2', 'Название группы 2')
]  # Список ID групп ВКонтакте

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Функция для получения новостей из конкретной группы ВКонтакте
def get_vk_news(group_id, group_name):
    vk_session = vk_api.VkApi(token=VK_ACCESS_TOKEN)
    vk = vk_session.get_api()
    news = []

    try:
        if group_id.isdigit():
            response = vk.wall.get(owner_id=f'-{group_id}', count=5)  # Используем owner_id
        else:
            response = vk.wall.get(domain=group_id, count=5)  # Используем domain
        for item in response['items']:
            post = {
                'text': item['text'],
                'group_name': group_name,
                'owner_id': item['owner_id'],
                'post_id': item['id'],
                'date': item['date'],  # Добавляем дату публикации
                'photos': []
            }

            # Проверяем наличие фотографий в посте
            if 'attachments' in item:
                for attachment in item['attachments']:
                    if attachment['type'] == 'photo':
                        max_size_photo = max(attachment['photo']['sizes'], key=lambda size: size['width'] * size['height'])
                        post['photos'].append(max_size_photo['url'])

            news.append(post)
    except vk_api.exceptions.ApiError as e:
        logger.error(f"Ошибка при получении новостей для группы {group_id}: {e}")

    return news

# Функция для получения комментариев поста из ВКонтакте
def get_vk_comments(owner_id, post_id):
    vk_session = vk_api.VkApi(token=VK_ACCESS_TOKEN)
    vk = vk_session.get_api()
    comments = []

    try:
        response = vk.wall.getComments(owner_id=owner_id, post_id=post_id, count=10, extended=1)
        for comment in response['items']:
            # Получаем информацию о пользователе
            user_info = vk.users.get(user_ids=comment['from_id'])[0]
            comments.append({
                'text': comment['text'],
                'from_id': comment['from_id'],
                'from_name': f"{user_info['first_name']} {user_info['last_name']}",
                'date': comment['date']
            })
    except vk_api.exceptions.ApiError as e:
        logger.error(f"Ошибка при получении комментариев для поста {owner_id}_{post_id}: {e}")

    return comments

# Функция разбивки длинного сообщения на несколько частей
def split_message(message, max_length=4096):
    return [message[i:i+max_length] for i in range(0, len(message), max_length)]

# Функция форматирования даты
def format_date(timestamp):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))

# Функция обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        try:
            await update.message.reply_text('Привет! Я бот, который собирает новости из ВКонтакте.')
            await menu(update, context)  # Сразу вызываем функцию menu
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")

# Функция обработки команды /menu
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[group[1]] for group in GROUP_IDS]  # Кнопки с названиями групп
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    if update.message:
        try:
            await update.message.reply_text('Выберите группу:', reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")

# Функция для формирования инлайн-кнопок под каждым сообщением новости
def generate_inline_keyboard(post_id, owner_id):
    keyboard = [[InlineKeyboardButton("Показать комментарии", callback_data=f"comments_{owner_id}_{post_id}")]]
    return InlineKeyboardMarkup(keyboard)

# Функция обработки нажатий кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    for group_id, group_name in GROUP_IDS:
        if text == group_name:
            news_items = get_vk_news(group_id, group_name)
            if news_items:
                for item in news_items:
                    post_link = f"https://vk.com/wall{item['owner_id']}_{item['post_id']}"
                    post_date = format_date(item['date'])
                    message = f"{post_link}\nДата: {post_date}\nГруппа: {item['group_name']}\n\n{item['text']}"
                    
                    # Добавляем кнопки под каждым сообщением новости
                    inline_keyboard = generate_inline_keyboard(item['post_id'], item['owner_id'])
                    
                    if item['photos']:
                        for photo in item['photos']:
                            await update.message.reply_photo(photo, caption=message, reply_markup=inline_keyboard)
                    else:
                        await update.message.reply_text(message, reply_markup=inline_keyboard)

            else:
                await update.message.reply_text(f'Новостей нет для группы {group_name} или произошла ошибка при получении новостей.')
            break
    else:
        await update.message.reply_text('Неверная команда. Используйте меню для выбора группы.')

# Функция обработки нажатий на инлайн-кнопки
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    query_data = query.data.split('_')
    if query_data[0] == 'comments':
        owner_id = query_data[1]
        post_id = query_data[2]
        comments = get_vk_comments(owner_id, post_id)
        if comments:
            comment_text = '\n\n'.join([f"{comment['text']}\n\nКомментарий от: {comment['from_name']}\nВремя: {format_date(comment['date'])}" for comment in comments])
            if len(comment_text) > 4096:
                parts = split_message(comment_text)
                for part in parts:
                    await query.message.reply_text(part)
            else:
                await query.message.reply_text(comment_text)
        else:
            await query.message.reply_text('Комментариев нет.')

    # Удаляем кнопку "Назад в меню"
    await query.message.delete_reply_markup()

# Основная функция для запуска бота
def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    application.run_polling()

if __name__ == '__main__':
    main()
