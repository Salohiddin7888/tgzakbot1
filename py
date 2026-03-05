import logging
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# States for conversation
PHOTO, TYPE, QUANTITY, CONFIRM, ADDITIONAL = range(5)

# Admin username to send orders
ADMIN_USERNAME = '@c_a_r_o_l_0_8'

# In-memory storage for orders (user_id -> list of orders)
# For production, use a database like SQLite
user_orders = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    logger.info(f"User {user.first_name} started the bot")
    keyboard = [
        ["Zakaz berish"],
        ["Zakazlar tarixi"],
        ["Zakaz ma'lumoti"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Xush kelibsiz! Quyidagi tugmalardan birini tanlang.",
        reply_markup=reply_markup
    )

async def order_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id not in user_orders or not user_orders[user_id]:
        await update.message.reply_text("Sizda hali zakazlar yo'q.")
        return
    history = "\n".join([f"Zakaz {i+1}: {order['type']} kishilik, {order['quantity']} dona, Rasm mavjud" for i, order in enumerate(user_orders[user_id])])
    await update.message.reply_text(f"Zakazlar tarixi:\n{history}")

async def order_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Bu joyda zakaz haqida umumiy ma'lumot berish mumkin
    await update.message.reply_text("Zakaz berish jarayoni: Rasm yuboring, turini tanlang, sonini kiriting va tasdiqlang.")

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Zakaz berishni boshlash uchun rasm yuboring.",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data['current_order'] = {}
    return PHOTO

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    photo_file = await update.message.photo[-1].get_file()
    context.user_data['current_order']['photo'] = photo_file
    logger.info(f"Photo received from {user.first_name}")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 kishilik", callback_data='1')],
        [InlineKeyboardButton("2 kishilik", callback_data='2')]
    ])
    await update.message.reply_text("Nechta kishilik?", reply_markup=keyboard)
    return TYPE

async def type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    type_choice = query.data
    context.user_data['current_order']['type'] = type_choice
    await query.edit_message_text(text=f"Tanlangan: {type_choice} kishilik. Endi nechta dona kerak ekanligini kiriting (faqat raqam):")
    return QUANTITY

async def quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        quantity = int(update.message.text)
        if quantity <= 0:
            raise ValueError
        context.user_data['current_order']['quantity'] = quantity
        
        order = context.user_data['current_order']
        photo_file = order['photo']
        caption = f"{order['type']} kishilik, {order['quantity']} dona"
        
        await update.message.reply_photo(photo=await photo_file.download_as_bytearray(), caption=caption)
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Tasdiqlash", callback_data='confirm')]])
        await update.message.reply_text("Tasdiqlaysizmi?", reply_markup=keyboard)
        return CONFIRM
    except ValueError:
        await update.message.reply_text("Iltimos, faqat musbat raqam kiriting.")
        return QUANTITY

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == 'confirm':
        user_id = query.from_user.id
        order = context.user_data['current_order']
        if user_id not in user_orders:
            user_orders[user_id] = []
        user_orders[user_id].append(order.copy())
        
        await query.edit_message_text(text="Zakaz tasdiqlandi!")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yana zakaz", callback_data='another')],
            [InlineKeyboardButton("Yuborish", callback_data='send')]
        ])
        await query.message.reply_text("Keyingi harakat?", reply_markup=keyboard)
        return ADDITIONAL
    return ConversationHandler.END

async def additional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == 'another':
        await query.edit_message_text(text="Yana zakaz berish.")
        return await start_order(query, context)  # Restart order process
    elif query.data == 'send':
        user_id = query.from_user.id
        if user_id in user_orders and user_orders[user_id]:
            for order in user_orders[user_id]:
                photo_file = order['photo']
                caption = f"{order['type']} kishilik, {order['quantity']} dona"
                await context.bot.send_photo(chat_id=ADMIN_USERNAME, photo=await photo_file.download_as_bytearray(), caption=caption)
            user_orders[user_id] = []  # Clear after sending
            await query.edit_message_text(text="Zakazlar yuborildi!")
        else:
            await query.edit_message_text(text="Yuborish uchun zakazlar yo'q.")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Zakaz bekor qilindi.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main() -> None:
    # Replace 'YOUR_TOKEN' with your bot's token
    application = Application.builder().token("YOUR_TOKEN").build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(Zakaz berish)$"), start_order)],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, photo)],
            TYPE: [CallbackQueryHandler(type_handler)],
            QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity)],
            CONFIRM: [CallbackQueryHandler(confirm)],
            ADDITIONAL: [CallbackQueryHandler(additional)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^(Zakazlar tarixi)$"), order_history))
    application.add_handler(MessageHandler(filters.Regex("^(Zakaz ma'lumoti)$"), order_info))
    application.add_handler(conv_handler)

    # For 24/7 running, deploy to a server like Heroku, AWS, or use a VPS.
    # Locally: application.run_polling()
    # For production, use webhook or long polling in a loop.

    application.run_polling()

if __name__ == "__main__":
    main()
