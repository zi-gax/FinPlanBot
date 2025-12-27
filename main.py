import asyncio
import logging
import signal
import os
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest
from config import API_token, ADMIN_IDS
from database import Database
from ai_parser import AIParser
from translations import get_text
from dollarprice import get_usd_price
from decimal import Decimal

usdprice = get_usd_price()


def format_amount(val):
    """Format a numeric value for display with thousands separator and 2 decimals."""
    try:
        if val is None:
            return "0.00"
        v = Decimal(str(val))
        return f"{v:,.2f}"
    except Exception:
        try:
            return format(float(val), ",.2f")
        except Exception:
            return str(val)

# Helper to get user language from callback or message
def get_user_lang(event):
    """Get user language from callback query or message."""
    # Both Message and CallbackQuery expose `from_user`.
    user = getattr(event, 'from_user', None)
    if not user:
        return 'fa'
    return db.get_user_language(user.id)

# Helper to check if user is admin
def is_admin(user_id):
    """Check if user is an admin."""
    return user_id in ADMIN_IDS

# Setup logging
logging.basicConfig(level=logging.INFO)

# Suppress AFC (Automatic Function Calling) messages from google-genai
logging.getLogger('google_genai.models').setLevel(logging.WARNING)

# Initialize bot and dispatcher
bot = Bot(token=API_token)
dp = Dispatcher(storage=MemoryStorage())
db = Database()
ai_parser = AIParser()

# States
class TransactionStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_card_source = State()
    waiting_for_date = State()
    waiting_for_description = State()
    waiting_for_type = State()
    waiting_for_category = State()
    waiting_for_custom_category = State()
    waiting_for_note = State()  # Keep for backward compatibility

class PlanStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()

class CategoryStates(StatesGroup):
    waiting_for_category_name = State()
    waiting_for_category_edit = State()

class CardSourceStates(StatesGroup):
    waiting_for_source_name = State()
    waiting_for_card_number = State()
    waiting_for_edit_name = State()
    waiting_for_edit_card_number = State()

class CustomReportStates(StatesGroup):
    waiting_for_start_date = State()
    waiting_for_end_date = State()
    viewing_paginated_report = State()

# Keyboards
def main_menu_kb(lang='fa', is_admin=False):
    """Generate main menu keyboard based on language and admin status."""
    if lang == 'en':
        buttons = [
            [InlineKeyboardButton(text="💰 Financial Management", callback_data="finance_main")],
            [InlineKeyboardButton(text="📅 Planning", callback_data="plan_main")],
            [InlineKeyboardButton(text="ℹ️ Help", callback_data="help")],
            [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings")]
        ]
        if is_admin:
            buttons.append([InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_panel")])
    else:  # Persian (fa)
        buttons = [
            [InlineKeyboardButton(text="💰 مدیریت مالی", callback_data="finance_main")],
            [InlineKeyboardButton(text="📅 برنامه‌ریزی", callback_data="plan_main")],
            [InlineKeyboardButton(text="💡 راهنما", callback_data="help")],
            [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="settings")]
        ]
        if is_admin:
            buttons.append([InlineKeyboardButton(text="👑 پنل مدیریت", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def finance_menu_kb(lang='fa'):
    """Generate finance menu keyboard based on language."""
    if lang == 'en':
        buttons = [
            [InlineKeyboardButton(text="➕ Add Transaction", callback_data="add_transaction")],
            [InlineKeyboardButton(text="📊 Reporting", callback_data="reporting")],
            [InlineKeyboardButton(text="⚙️ Settings", callback_data="financial_settings")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="➕ افزودن تراکنش", callback_data="add_transaction")],
            [InlineKeyboardButton(text="📊 گزارش‌گیری", callback_data="reporting")],
            [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="financial_settings")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def planning_menu_kb(lang='fa'):
    """Generate planning menu keyboard based on language."""
    if lang == 'en':
        buttons = [
            [InlineKeyboardButton(text="➕ Add Plan", callback_data="add_plan")],
            [InlineKeyboardButton(text="📆 Today's Plans", callback_data="plans_today")],
            [InlineKeyboardButton(text="📅 This Week's Plans", callback_data="plans_week")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="➕ افزودن برنامه", callback_data="add_plan")],
            [InlineKeyboardButton(text="📆 برنامه‌های امروز", callback_data="plans_today")],
            [InlineKeyboardButton(text="📅 برنامه‌های این هفته", callback_data="plans_week")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_menu_kb(lang='fa'):
    """Generate admin panel menu keyboard based on language."""
    if lang == 'en':
        buttons = [
            [InlineKeyboardButton(text="👥 User List", callback_data="admin_users")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="👥 لیست کاربران", callback_data="admin_users")],
            [InlineKeyboardButton(text="📊 آمار", callback_data="admin_stats")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Translation helper is now imported from translations.py

# Handlers
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    db.add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    lang = db.get_user_language(message.from_user.id)
    admin_status = is_admin(message.from_user.id)
    await send_menu_message(
        message.from_user.id,
        get_text('welcome', lang),
        reply_markup=main_menu_kb(lang, admin_status)
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    lang = db.get_user_language(callback.from_user.id)
    admin_status = is_admin(callback.from_user.id)
    text = get_text('welcome', lang).split('\n')[1] if '\n' in get_text('welcome', lang) else "بخش مورد نظر را انتخاب کنید:"
    await send_menu_message(callback.from_user.id, text, reply_markup=main_menu_kb(lang, admin_status))
    await callback.answer()

@dp.callback_query(F.data == "settings")
async def settings_menu(callback: types.CallbackQuery):
    """Show settings menu."""
    await show_settings_menu(callback.from_user.id)
    await callback.answer()

@dp.callback_query(F.data == "financial_settings")
async def financial_settings_menu(callback: types.CallbackQuery):
    """Show financial settings menu."""
    lang = db.get_user_language(callback.from_user.id)
    settings = db.get_user_settings(callback.from_user.id)

    currency_text = get_text('currency_toman', lang) if settings['currency'] == 'toman' else get_text('currency_dollar', lang)
    calendar_text = get_text('calendar_jalali', lang) if settings['calendar_format'] == 'jalali' else get_text('calendar_gregorian', lang)

    if lang == 'en':
        text = f"⚙️ Financial Settings\n\nCurrent Settings:\n💵 Currency: {currency_text}\n📅 Calendar: {calendar_text}\n\nSelect an option:"
        buttons = [
            [InlineKeyboardButton(text="💵 Change Currency", callback_data="change_currency")],
            [InlineKeyboardButton(text="📅 Change Calendar", callback_data="change_calendar")],
            [InlineKeyboardButton(text="💳 Manage Cards/Sources", callback_data="manage_cards_sources")],
            [InlineKeyboardButton(text="📂 Manage Categories", callback_data="categories")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="settings")]
        ]
    else:  # Persian
        text = f"⚙️ تنظیمات مالی\n\nتنظیمات فعلی:\n💵 واحد پول: {currency_text}\n📅 تقویم: {calendar_text}\n\nگزینه مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text="💵 تغییر واحد پول", callback_data="change_currency")],
            [InlineKeyboardButton(text="📅 تغییر تقویم", callback_data="change_calendar")],
            [InlineKeyboardButton(text="💳 مدیریت کارت‌ها/منابع", callback_data="manage_cards_sources")],
            [InlineKeyboardButton(text="📂 مدیریت دسته‌بندی‌ها", callback_data="categories")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="settings")]
        ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# Card/Source Management Handlers
@dp.callback_query(F.data == "manage_cards_sources")
async def manage_cards_sources_menu(callback: types.CallbackQuery, state: FSMContext):
    """Show card/source management menu."""
    # Clear any leftover transaction state and messages when entering manage cards
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=callback.from_user.id, message_id=message_id)
        except Exception as e:
            # Ignore errors if message doesn't exist or can't be deleted
            logging.debug(f"Could not delete leftover transaction message {message_id}: {e}")
    await state.clear()
    lang = db.get_user_language(callback.from_user.id)
    cards_sources = db.get_cards_sources(callback.from_user.id)

    if lang == 'en':
        text = "💳 Card/Source Management\n\nYour Cards/Sources:"
    else:
        text = "💳 مدیریت کارت‌ها و منابع\n\nکارت‌ها/منابع شما:"

    buttons = []

    if cards_sources:
        for card_source in cards_sources:
            card_id, name, card_number, balance = card_source
            settings = db.get_user_settings(callback.from_user.id)
            currency = get_text('toman', lang) if settings['currency'] == 'toman' else get_text('dollar', lang)

            # Mask card number if it exists
            display_name = name
            if card_number:
                masked_card = f"****{card_number[-4:]}" if len(card_number) >= 4 else card_number
                display_name = f"{name} ({masked_card})"

            balance_text = get_text('card_source_balance', lang, balance=format_amount(balance), currency=currency)
            button_text = f"{display_name}\n{balance_text}"

            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"edit_card_{card_id}")])
    else:
        if lang == 'en':
            text += "\n\nNo cards/sources registered yet."
        else:
            text += "\n\nهنوز هیچ کارت/منبعی ثبت نشده است."

    # Add management buttons
    if lang == 'en':
        buttons.extend([
            [InlineKeyboardButton(text="➕ Add Card/Source", callback_data="add_card_source")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="financial_settings")]
        ])
    else:
        buttons.extend([
            [InlineKeyboardButton(text="➕ افزودن کارت/منبع", callback_data="add_card_source")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="financial_settings")]
        ])

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "add_card_source")
async def start_add_card_source(callback: types.CallbackQuery, state: FSMContext):
    """Start adding a new card/source."""
    lang = db.get_user_language(callback.from_user.id)

    await state.update_data(edit_mode=False)
    text = get_text('enter_source_name', lang)
    buttons = [[InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="manage_cards_sources")]]

    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(CardSourceStates.waiting_for_source_name)
    await callback.answer()

@dp.message(CardSourceStates.waiting_for_source_name)
async def process_source_name(message: types.Message, state: FSMContext):
    """Process the card/source name."""
    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    edit_mode = data.get('edit_mode', False)

    name = message.text.strip()
    if not name:
        await message.answer(get_text('source_name_empty', lang))
        return

    await state.update_data(source_name=name)

    text = get_text('enter_card_number', lang)
    buttons = [
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="manage_cards_sources")],
        [InlineKeyboardButton(text="رد کردن" if lang == 'fa' else "Skip", callback_data="skip_card_number")]
    ]

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(CardSourceStates.waiting_for_card_number)

@dp.callback_query(F.data == "skip_card_number", StateFilter(CardSourceStates.waiting_for_card_number))
async def skip_card_number(callback: types.CallbackQuery, state: FSMContext):
    """Skip entering card number."""
    # Delete the card number input message
    await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
    await process_card_number_finish(callback, state, None)

@dp.message(CardSourceStates.waiting_for_card_number)
async def process_card_number(message: types.Message, state: FSMContext):
    """Process the card number."""
    await process_card_number_finish(message, state, message.text.strip())

async def process_card_number_finish(event, state: FSMContext, card_number):
    """Finish processing card/source creation."""
    # Determine user and event type
    is_callback = hasattr(event, 'data')
    user_id = event.from_user.id
    lang = db.get_user_language(user_id)

    data = await state.get_data()
    name = data['source_name']
    edit_mode = data.get('edit_mode', False)

    # Validate card number if provided
    if card_number:
        # Remove spaces and non-digits
        card_number = ''.join(filter(str.isdigit, card_number))
        if len(card_number) != 16:
            error_msg = get_text('card_number_invalid', lang)
            if is_callback:
                await event.answer(error_msg, show_alert=True)
            else:
                await event.answer(error_msg)
            return

        # Check if card number already exists
        cards_sources = db.get_cards_sources(user_id)
        for card_source in cards_sources:
            if card_source[2] == card_number:  # card_number is at index 2
                error_msg = get_text('card_source_exists', lang)
                if is_callback:
                    await event.answer(error_msg, show_alert=True)
                else:
                    await event.answer(error_msg)
                return

    if edit_mode:
        card_id = data['edit_card_id']
        db.update_card_source(card_id, name=name, card_number=card_number)
        text = get_text('card_source_updated', lang, name=name)
    else:
        db.add_card_source(user_id, name, card_number)
        text = get_text('card_source_added', lang, name=name)

    await state.clear()

    # Return to card/source management menu
    if is_callback:
        await manage_cards_sources_menu(event, state)
    else:
        # For message events, create a fake callback query
        fake_callback = types.CallbackQuery(
            id="fake",
            from_user=event.from_user,
            message=event,
            data="manage_cards_sources",
            chat_instance="fake"
        )
        await manage_cards_sources_menu(fake_callback, state)

@dp.callback_query(F.data.startswith("edit_card_"))
async def edit_card_source_menu(callback: types.CallbackQuery):
    """Show edit menu for a specific card/source."""
    lang = db.get_user_language(callback.from_user.id)
    card_id = int(callback.data.replace("edit_card_", ""))

    card_source = db.get_card_source(card_id)
    if not card_source:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    card_id, name, card_number, balance = card_source
    settings = db.get_user_settings(callback.from_user.id)
    currency = get_text('toman', lang) if settings['currency'] == 'toman' else get_text('dollar', lang)

    card_display = f"****{card_number[-4:]}" if card_number and len(card_number) >= 4 else (card_number or "بدون شماره کارت" if lang == 'fa' else "No card number")

    if lang == 'en':
        text = f"💳 Edit Card/Source\n\nName: {name}\nCard: {card_display}\nBalance: {format_amount(balance)} {currency}\n\nSelect action:"
        buttons = [
            [InlineKeyboardButton(text="✏️ Edit Name", callback_data=f"edit_name_{card_id}")],
            [InlineKeyboardButton(text="💳 Edit Card Number", callback_data=f"edit_card_number_{card_id}")],
            [InlineKeyboardButton(text="🗑 Delete", callback_data=f"delete_card_{card_id}")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="manage_cards_sources")]
        ]
    else:
        text = f"💳 ویرایش کارت/منبع\n\nنام: {name}\nکارت: {card_display}\nموجودی: {format_amount(balance)} {currency}\n\nاقدام مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text="✏️ ویرایش نام", callback_data=f"edit_name_{card_id}")],
            [InlineKeyboardButton(text="💳 ویرایش شماره کارت", callback_data=f"edit_card_number_{card_id}")],
            [InlineKeyboardButton(text="🗑 حذف", callback_data=f"delete_card_{card_id}")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="manage_cards_sources")]
        ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_card_"))
async def confirm_delete_card(callback: types.CallbackQuery):
    """Confirm deletion of a card/source."""
    lang = db.get_user_language(callback.from_user.id)
    card_id = int(callback.data.replace("delete_card_", ""))

    card_source = db.get_card_source(card_id)
    if not card_source:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    name = card_source[1]  # name is at index 1

    text = get_text('confirm_delete_card', lang, name=name)
    buttons = [
        [InlineKeyboardButton(text="✅ تایید" if lang == 'fa' else "✅ Confirm", callback_data=f"execute_delete_card_{card_id}")],
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="manage_cards_sources")]
    ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("execute_delete_card_"))
async def execute_delete_card(callback: types.CallbackQuery):
    """Execute deletion of a card/source."""
    lang = db.get_user_language(callback.from_user.id)
    card_id = int(callback.data.replace("execute_delete_card_", ""))

    card_source = db.get_card_source(card_id)
    if not card_source:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    name = card_source[1]  # name is at index 1
    db.delete_card_source(card_id)

    text = get_text('card_source_deleted', lang, name=name)
    buttons = [[InlineKeyboardButton(text=get_text('back', lang), callback_data="manage_cards_sources")]]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    """Show admin panel menu."""
    # Check if user is admin
    if not is_admin(callback.from_user.id):
        lang = db.get_user_language(callback.from_user.id)
        await callback.answer(get_text('access_denied', lang) if lang == 'en' else "دسترسی غیرمجاز", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)

    if lang == 'en':
        text = "👑 Admin Panel\n\nWelcome to the admin panel. Choose an option:"
    else:
        text = "👑 پنل مدیریت\n\nبه پنل مدیریت خوش آمدید. گزینه مورد نظر را انتخاب کنید:"

    await send_menu_message(callback.from_user.id, text, reply_markup=admin_menu_kb(lang))
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    """Show list of all users."""
    # Check if user is admin
    if not is_admin(callback.from_user.id):
        lang = db.get_user_language(callback.from_user.id)
        await callback.answer(get_text('access_denied', lang) if lang == 'en' else "دسترسی غیرمجاز", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    users = db.get_all_users()

    if not users:
        text = "👥 لیست کاربران\n\nهیچ کاربری یافت نشد." if lang == 'fa' else "👥 User List\n\nNo users found."
        await send_menu_message(callback.from_user.id, text, reply_markup=admin_menu_kb(lang))
        await callback.answer()
        return

    # Show first 10 users with pagination
    page = 0
    users_per_page = 10
    start_idx = page * users_per_page
    end_idx = start_idx + users_per_page
    current_users = users[start_idx:end_idx]

    text = "👥 لیست کاربران:\n\n" if lang == 'fa' else "👥 User List:\n\n"

    for i, user in enumerate(current_users, start_idx + 1):
        user_id, username, full_name, language, created_at = user
        username_display = f"@{username}" if username else "بدون نام کاربری" if lang == 'fa' else "No username"
        lang_flag = "🇮🇷" if language == 'fa' else "🇬🇧"
        text += f"{i}. {full_name} ({username_display}) {lang_flag}\n"

    # Add pagination buttons if needed
    buttons = []
    if len(users) > users_per_page:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ قبلی" if lang == 'fa' else "⬅️ Previous",
                                                   callback_data=f"admin_users_page_{page-1}"))
        if end_idx < len(users):
            nav_buttons.append(InlineKeyboardButton(text="بعدی ➡️" if lang == 'fa' else "Next ➡️",
                                                   callback_data=f"admin_users_page_{page+1}"))
        if nav_buttons:
            buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text=get_text('back', lang), callback_data="admin_panel")])

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users_page(callback: types.CallbackQuery):
    """Handle pagination for user list."""
    # Check if user is admin
    if not is_admin(callback.from_user.id):
        lang = db.get_user_language(callback.from_user.id)
        await callback.answer(get_text('access_denied', lang) if lang == 'fa' else "Access denied", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    page = int(callback.data.replace("admin_users_page_", ""))

    users = db.get_all_users()
    users_per_page = 10
    start_idx = page * users_per_page
    end_idx = start_idx + users_per_page
    current_users = users[start_idx:end_idx]

    text = "👥 لیست کاربران:\n\n" if lang == 'fa' else "👥 User List:\n\n"

    for i, user in enumerate(current_users, start_idx + 1):
        user_id, username, full_name, language, created_at = user
        username_display = f"@{username}" if username else "بدون نام کاربری" if lang == 'fa' else "No username"
        lang_flag = "🇮🇷" if language == 'fa' else "🇬🇧"
        text += f"{i}. {full_name} ({username_display}) {lang_flag}\n"

    # Add pagination buttons
    buttons = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ قبلی" if lang == 'fa' else "⬅️ Previous",
                                               callback_data=f"admin_users_page_{page-1}"))
    if end_idx < len(users):
        nav_buttons.append(InlineKeyboardButton(text="بعدی ➡️" if lang == 'fa' else "Next ➡️",
                                               callback_data=f"admin_users_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text=get_text('back', lang), callback_data="admin_panel")])

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    """Show bot statistics."""
    # Check if user is admin
    if not is_admin(callback.from_user.id):
        lang = db.get_user_language(callback.from_user.id)
        await callback.answer(get_text('access_denied', lang) if lang == 'fa' else "Access denied", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    stats = db.get_user_stats()

    if lang == 'en':
        text = "📊 Bot Statistics\n\n"
        text += f"👥 Total Users: {stats['total_users']:,}\n"
        text += f"🔥 Active Users (30 days): {stats['active_users']:,}\n\n"

        text += "🌐 Language Distribution:\n"
        for lang_code, count in stats['language_stats'].items():
            flag = "🇮🇷 Persian" if lang_code == 'fa' else "🇬🇧 English"
            text += f"  {flag}: {count:,}\n"

        text += "\n📈 Activity Stats:\n"
        text += f"💰 Total Transactions: {stats['total_transactions']:,}\n"
        text += f"📅 Total Plans: {stats['total_plans']:,}\n"
        text += f"📂 Total Categories: {stats['total_categories']:,}\n"
    else:
        text = "📊 آمار ربات\n\n"
        text += f"👥 تعداد کل کاربران: {stats['total_users']:,}\n"
        text += f"🔥 کاربران فعال (۳۰ روز): {stats['active_users']:,}\n\n"

        text += "🌐 توزیع زبان‌ها:\n"
        for lang_code, count in stats['language_stats'].items():
            flag = "🇮🇷 فارسی" if lang_code == 'fa' else "🇬🇧 انگلیسی"
            text += f"  {flag}: {count:,}\n"

        text += "\n📈 آمار فعالیت:\n"
        text += f"💰 تعداد کل تراکنش‌ها: {stats['total_transactions']:,}\n"
        text += f"📅 تعداد کل برنامه‌ها: {stats['total_plans']:,}\n"
        text += f"📂 تعداد کل دسته‌بندی‌ها: {stats['total_categories']:,}\n"

    buttons = [[InlineKeyboardButton(text=get_text('back', lang), callback_data="admin_panel")]]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "change_currency")
async def change_currency_menu(callback: types.CallbackQuery):
    """Show currency selection menu."""
    lang = db.get_user_language(callback.from_user.id)

    text = get_text('select_currency', lang)
    buttons = [
        [InlineKeyboardButton(text=get_text('currency_toman', lang), callback_data="set_currency_toman")],
        [InlineKeyboardButton(text=get_text('currency_dollar', lang), callback_data="set_currency_dollar")],
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="financial_settings")]
    ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("set_currency_"))
async def set_currency(callback: types.CallbackQuery):
    """Set user's currency preference."""
    lang = db.get_user_language(callback.from_user.id)
    currency = callback.data.replace("set_currency_", "")
    
    # Get current user currency before change
    current_settings = db.get_user_settings(callback.from_user.id)
    old_currency = current_settings['currency']
    
    # Only convert if currency is actually changing
    if old_currency != currency:
        try:
            # Ensure we check for an updated USD price now (hourly cache handled inside)
            current_usd_price = get_usd_price()
            
            if current_usd_price is None or current_usd_price <= 0:
                raise ValueError('Invalid USD price')
            
            # Convert all transactions from old currency to new currency
            db.convert_user_currency(callback.from_user.id, old_currency, currency, current_usd_price)
            # Update currency setting AFTER successful conversion
            db.set_user_currency(callback.from_user.id, currency)
        except Exception as e:
            logging.error(f"Currency conversion error for user {callback.from_user.id}: {e}")
            # Still update currency preference even if conversion fails
            db.set_user_currency(callback.from_user.id, currency)
            currency_name = get_text('currency_toman', lang) if currency == 'toman' else get_text('currency_dollar', lang)
            text = f"⚠️ {get_text('currency_changed', lang, currency=currency_name)}\n\n{get_text('conversion_error', lang)}"
            buttons = [[InlineKeyboardButton(text=get_text('back', lang), callback_data="financial_settings")]]
            await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
            await callback.answer()
            return
    else:
        # Currency didn't change, just update preference
        db.set_user_currency(callback.from_user.id, currency)

    currency_name = get_text('currency_toman', lang) if currency == 'toman' else get_text('currency_dollar', lang)
    text = get_text('currency_changed', lang, currency=currency_name)

    buttons = [[InlineKeyboardButton(text=get_text('back', lang), callback_data="financial_settings")]]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "change_calendar")
async def change_calendar_menu(callback: types.CallbackQuery):
    """Show calendar format selection menu."""
    lang = db.get_user_language(callback.from_user.id)

    text = get_text('select_calendar', lang)
    buttons = [
        [InlineKeyboardButton(text=get_text('calendar_jalali', lang), callback_data="set_calendar_jalali")],
        [InlineKeyboardButton(text=get_text('calendar_gregorian', lang), callback_data="set_calendar_gregorian")],
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="financial_settings")]
    ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("set_calendar_"))
async def set_calendar_format(callback: types.CallbackQuery):
    """Set user's calendar format preference."""
    lang = db.get_user_language(callback.from_user.id)
    calendar_format = callback.data.replace("set_calendar_", "")

    db.set_user_calendar_format(callback.from_user.id, calendar_format)

    calendar_name = get_text('calendar_jalali', lang) if calendar_format == 'jalali' else get_text('calendar_gregorian', lang)
    text = get_text('calendar_changed', lang, calendar=calendar_name)

    buttons = [[InlineKeyboardButton(text=get_text('back', lang), callback_data="financial_settings")]]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "change_language")
async def change_language_menu(callback: types.CallbackQuery):
    """Show language selection menu."""
    current_lang = db.get_user_language(callback.from_user.id)
    
    if current_lang == 'en':
        text = "🌐 Change Language\n\nCurrent language: English\n\nPlease select your preferred language:"
        buttons = [
            [InlineKeyboardButton(text="🇮🇷 فارسی (Persian)", callback_data="set_lang_fa")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
            [InlineKeyboardButton(text=get_text('back', current_lang), callback_data="settings")]
        ]
    else:  # Persian
        text = "🌐 تغییر زبان\n\nزبان فعلی: فارسی\n\nلطفاً زبان مورد نظر خود را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text="🇮🇷 فارسی", callback_data="set_lang_fa")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
            [InlineKeyboardButton(text=get_text('back', current_lang), callback_data="settings")]
        ]
    
    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("set_lang_"))
async def set_language(callback: types.CallbackQuery):
    """Set user's language preference."""
    lang_code = callback.data.replace("set_lang_", "")
    db.set_user_language(callback.from_user.id, lang_code)
    
    # Get updated language
    lang = db.get_user_language(callback.from_user.id)
    
    if lang == 'en':
        text = "✅ Language changed successfully.\n\nCurrent language: English"
        buttons = [
            [InlineKeyboardButton(text="🔙 Back to Settings", callback_data="settings")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
        ]
    else:  # Persian
        text = "✅ زبان با موفقیت تغییر کرد.\n\nزبان فعلی: فارسی"
        buttons = [
            [InlineKeyboardButton(text="🔙 بازگشت به تنظیمات", callback_data="settings")],
            [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="main_menu")]
        ]
    
    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer(get_text('lang_changed', lang))

@dp.callback_query(F.data == "finance_main")
async def finance_main(callback: types.CallbackQuery, state: FSMContext):
    # Clear any existing transaction state
    await state.clear()

    lang = db.get_user_language(callback.from_user.id)

    # Show single button for transaction registration
    text = get_text('select_transaction_type', lang)

    buttons = [
        [InlineKeyboardButton(text=get_text('add_transaction', lang), callback_data="add_transaction")],
        [InlineKeyboardButton(text="📊 " + ("Reporting" if lang == 'en' else "گزارش‌گیری"), callback_data="reporting")],
        [InlineKeyboardButton(text="⚙️ " + ("Settings" if lang == 'en' else "تنظیمات"), callback_data="financial_settings")],
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
    ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "plan_main")
async def plan_main(callback: types.CallbackQuery):
    lang = get_user_lang(callback)
    text = f"{get_text('planning_main', lang)}\n{get_text('planning_desc', lang)}"
    await send_menu_message(callback.from_user.id, text, reply_markup=planning_menu_kb(lang))
    await callback.answer()

@dp.callback_query(F.data == "help")
@dp.message(Command("help"))
async def help_cmd(event: types.CallbackQuery | types.Message):
    lang = get_user_lang(event)
    help_text = f"{get_text('help_title', lang)}\n\n{get_text('help_text', lang)}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]])
    await send_menu_message(event.from_user.id, help_text, reply_markup=kb)
    if isinstance(event, types.CallbackQuery):
        await event.answer()


# Data Management Handlers
@dp.callback_query(F.data == "confirm_clear_data")
async def ask_confirm_clear(callback: types.CallbackQuery):
    lang = get_user_lang(callback)
    text = get_text('select_clear_option', lang)
    buttons = [
        [InlineKeyboardButton(text=get_text('clear_everything', lang), callback_data="execute_clear_everything")],
        [InlineKeyboardButton(text=get_text('clear_financial', lang), callback_data="execute_clear_financial")],
        [InlineKeyboardButton(text=get_text('clear_planning', lang), callback_data="execute_clear_planning")],
        [InlineKeyboardButton(text=get_text('clear_cards', lang), callback_data="execute_clear_cards")],
        [InlineKeyboardButton(text=get_text('cancel', lang), callback_data="settings")]
    ]
    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "execute_clear_everything")
async def execute_clear_everything(callback: types.CallbackQuery):
    lang = get_user_lang(callback)
    db.clear_user_data(callback.from_user.id)

    # Show success message briefly
    success_text = get_text('data_cleared', lang)
    await send_menu_message(callback.from_user.id, success_text)

    # Wait 2 seconds then show settings menu
    await asyncio.sleep(2)
    await show_settings_menu(callback.from_user.id)

@dp.callback_query(F.data == "execute_clear_cards")
async def execute_clear_cards(callback: types.CallbackQuery):
    lang = get_user_lang(callback)
    db.clear_cards(callback.from_user.id)

    # Show success message briefly
    success_text = "✅ کارت‌ها با موفقیت پاکسازی شد." if lang == 'fa' else "✅ Cards cleared successfully."
    await send_menu_message(callback.from_user.id, success_text)

    # Wait 2 seconds then show settings menu
    await asyncio.sleep(2)
    await show_settings_menu(callback.from_user.id)

@dp.callback_query(F.data == "execute_clear_financial")
async def execute_clear_financial(callback: types.CallbackQuery):
    lang = get_user_lang(callback)
    db.clear_financial_data(callback.from_user.id)

    # Show success message briefly
    success_text = get_text('financial_data_cleared', lang)
    await send_menu_message(callback.from_user.id, success_text)

    # Wait 2 seconds then show settings menu
    await asyncio.sleep(2)
    await show_settings_menu(callback.from_user.id)

@dp.callback_query(F.data == "execute_clear_planning")
async def execute_clear_planning(callback: types.CallbackQuery):
    lang = get_user_lang(callback)
    db.clear_planning_data(callback.from_user.id)

    # Show success message briefly
    success_text = get_text('planning_data_cleared', lang)
    await send_menu_message(callback.from_user.id, success_text)

    # Wait 2 seconds then show settings menu
    await asyncio.sleep(2)
    await show_settings_menu(callback.from_user.id)

# Restart functionality removed

# Helper: Persian numbers to English
def fa_to_en(text):
    fa_nums = "۰۱۲۳۴۵۶۷۸۹"
    en_nums = "0123456789"
    table = str.maketrans(fa_nums, en_nums)
    return text.translate(table)

# Calendar conversion utilities
def gregorian_to_jalali(gy, gm, gd):
    """Convert Gregorian date to Jalali date."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gm > 2:
        gy2 = gy + 1
    else:
        gy2 = gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd

def jalali_to_gregorian(jy, jm, jd):
    """Convert Jalali date to Gregorian date."""
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        gm = 1 + (days // 31)
        gd = 1 + (days % 31)
    else:
        gm = 7 + ((days - 186) // 30)
        gd = 1 + ((days - 186) % 30)
    return gy, gm, gd

def format_date_for_display(date_str, calendar_format, lang='fa'):
    """Format date string for display based on calendar format."""
    try:
        year, month, day = map(int, date_str.split('-'))
        if calendar_format == 'jalali':
            jy, jm, jd = gregorian_to_jalali(year, month, day)
            return f"{jy:04d}-{jm:02d}-{jd:02d}"
        else:
            return date_str
    except:
        return date_str

def parse_date_input(date_input, calendar_format):
    """Parse date input and convert to Gregorian format for storage."""
    try:
        # Handle both dash and slash separators
        if '-' in date_input:
            year, month, day = map(int, date_input.split('-'))
        elif '/' in date_input:
            year, month, day = map(int, date_input.split('/'))
        else:
            raise ValueError("Invalid date format")

        if calendar_format == 'jalali':
            gy, gm, gd = jalali_to_gregorian(year, month, day)
            return f"{gy:04d}-{gm:02d}-{gd:02d}"
        else:
            return f"{year:04d}-{month:02d}-{day:02d}"
    except:
        # Return today's date if parsing fails
        from datetime import date
        return date.today().strftime("%Y-%m-%d")

# Helper: Safely edit message text (handles "message not modified" error)
async def safe_edit_text(message_or_callback, text: str, reply_markup=None):
    """Safely edit message text, catching TelegramBadRequest for identical content."""
    try:
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(text, reply_markup=reply_markup)
        else:
            await message_or_callback.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        # Ignore "message is not modified" error
        if "message is not modified" in str(e).lower():
            logging.debug(f"Message not modified (expected): {e}")
        else:
            # Re-raise if it's a different TelegramBadRequest
            raise

# Helper: Generate settings menu keyboard
def settings_menu_kb(lang='fa'):
    """Generate settings menu keyboard based on language."""
    if lang == 'en':
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]
    else:  # Persian
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Helper: Show full settings menu for a user
async def show_settings_menu(user_id: int):
    """Show the full settings menu for a user."""
    lang = db.get_user_language(user_id)

    if lang == 'en':
        text = "⚙️ Settings\n\nSelect an option:"
        buttons = [
            [InlineKeyboardButton(text="💰 Financial Settings", callback_data="financial_settings")],
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]
    else:  # Persian
        text = "⚙️ تنظیمات\n\nگزینه مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text="💰 تنظیمات مالی", callback_data="financial_settings")],
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
        ]

    await send_menu_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# Helper: Send menu message and manage previous menu deletion
async def send_menu_message(user_id: int, text: str, reply_markup=None):
    """Send a menu message, deleting the previous menu message if it exists."""
    # Get the last menu message ID
    last_message_id = db.get_last_menu_message_id(user_id)

    # Try to delete the previous menu message if it exists
    if last_message_id:
        try:
            await bot.delete_message(chat_id=user_id, message_id=last_message_id)
        except TelegramBadRequest as e:
            # Ignore if message was already deleted or doesn't exist
            if "message to delete not found" not in str(e).lower():
                logging.debug(f"Could not delete previous menu message: {e}")

    # Send the new menu message
        sent_message = await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, disable_notification=True)

    # Store the new message ID
    db.set_last_menu_message_id(user_id, sent_message.message_id)

    return sent_message

# Transaction FSM Handlers
@dp.callback_query(F.data == "add_transaction")
async def start_add_transaction(callback: types.CallbackQuery, state: FSMContext):
    lang = get_user_lang(callback)
    settings = db.get_user_settings(callback.from_user.id)
    currency = get_text('toman', lang) if settings['currency'] == 'toman' else get_text('dollar', lang)

    text = f"{get_text('enter_amount_with_currency', lang, currency=currency)}\n\n{get_text('cancel_hint', lang)}"
    buttons = [
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
    ]
    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(TransactionStates.waiting_for_amount)
    await callback.answer()

@dp.message(TransactionStates.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    lang = get_user_lang(message)
    settings = db.get_user_settings(message.from_user.id)
    currency = settings['currency']
    currency_display = get_text('toman', lang) if currency == 'toman' else get_text('dollar', lang)

    amount_str = fa_to_en(message.text).replace(",", "").replace(" ", "")
    # Try to extract number
    import re
    nums = re.findall(r'\d+', amount_str)
    if not nums:
        await message.answer(f"{get_text('invalid_amount', lang)}\n\n{get_text('cancel_hint', lang)}")
        return

    amount = float(nums[0])
    await state.update_data(amount=amount, currency=currency)

    # Check if user has any cards/sources
    cards_sources = db.get_cards_sources(message.from_user.id)
    if not cards_sources:
        # Show guide to add card/source
        text = f"{get_text('no_card_source', lang)}\n\n{get_text('add_card_source_guide', lang)}"
        buttons = [
            [InlineKeyboardButton(text="💳 " + ("مدیریت کارت‌ها/منابع" if lang == 'fa' else "Manage Cards/Sources"), callback_data="manage_cards_sources")],
            [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
        ]
        sent_message = await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        # Track message ID for cleanup
        data = await state.get_data()
        message_ids = data.get('message_ids', [])
        message_ids.append(sent_message.message_id)
        await state.update_data(message_ids=message_ids)
        return

    text = f"{get_text('amount_label', lang)}: {format_amount(amount)} {currency_display}\n\n{get_text('select_card_source', lang)}"
    buttons = []
    for card_source in cards_sources:
        card_id, name, card_number, balance = card_source
        # Mask card number if it exists
        display_name = name
        if card_number:
            masked_card = f"****{card_number[-4:]}" if len(card_number) >= 4 else card_number
            display_name = f"{name} ({masked_card})"

        balance_text = get_text('card_source_balance', lang, balance=format_amount(balance), currency=currency_display)
        button_text = f"{display_name}\n{balance_text}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"card_{card_id}")])

    buttons.append([InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")])
    sent_message = await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    # Track message ID for cleanup
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(sent_message.message_id)
    await state.update_data(message_ids=message_ids)
    await state.set_state(TransactionStates.waiting_for_card_source)

@dp.callback_query(TransactionStates.waiting_for_card_source)
async def process_card_source(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "cancel_transaction":
        await cancel_transaction(callback, state)
        return

    lang = db.get_user_language(callback.from_user.id)
    card_id = int(callback.data.replace("card_", ""))

    # Verify card/source belongs to user
    card_source = db.get_card_source(card_id)
    if not card_source or card_source[0] != card_id:  # Check if card exists and belongs to user
        await callback.answer(get_text('error', lang), show_alert=True)
        # Clear transaction state and clean up messages when card is not found
        data = await state.get_data()
        message_ids = data.get('message_ids', [])
        for message_id in message_ids:
            try:
                await bot.delete_message(chat_id=callback.from_user.id, message_id=message_id)
            except Exception as e:
                # Ignore errors if message doesn't exist or can't be deleted
                logging.debug(f"Could not delete transaction message {message_id}: {e}")
        await state.clear()
        return

    await state.update_data(card_source_id=card_id)

    # Move to date input
    settings = db.get_user_settings(callback.from_user.id)
    calendar_format = settings['calendar_format']
    calendar_display = "شمسی" if calendar_format == 'jalali' and lang == 'fa' else ("Jalali" if calendar_format == 'jalali' else "Gregorian")

    data = await state.get_data()
    amount = data['amount']
    currency_display = get_text('toman', lang) if data['currency'] == 'toman' else get_text('dollar', lang)

    text = f"{get_text('amount_label', lang)}: {format_amount(amount)} {currency_display}\n"
    text += f"{get_text('card_source_label', lang)}: {card_source[1]}\n\n"  # card_source[1] is name
    if calendar_format == 'jalali':
        text += f"{get_text('enter_date', lang, calendar_format=calendar_display)}\n\n"
        text += "📅 مثال: ۱۴۰۳-۰۶-۱۵ یا ۱۴۰۳/۰۶/۱۵ (شمسی) یا 2024-12-25 (میلادی)" if lang == 'fa' else "📅 Example: 1403-06-15 or 1403/06/15 (Jalali) or 2024-12-25 (Gregorian)"
    else:
        text += f"{get_text('enter_date', lang, calendar_format=calendar_display)}\n\n"
        text += "📅 مثال: ۱۴۰۳-۰۶-۱۵ (شمسی) یا 2024-12-25 (میلادی)" if lang == 'fa' else "📅 Example: 1403-06-15 (Jalali) or 2024-12-25 (Gregorian)"

    buttons = [
        [InlineKeyboardButton(text="📅 امروز" if lang == 'fa' else "📅 Today", callback_data="date_today")],
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
    ]

    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(TransactionStates.waiting_for_date)

@dp.callback_query(TransactionStates.waiting_for_date)
@dp.message(TransactionStates.waiting_for_date)
async def process_date(event, state: FSMContext):
    user_id = event.from_user.id
    lang = db.get_user_language(user_id)

    settings = db.get_user_settings(user_id)
    calendar_format = settings['calendar_format']

    if isinstance(event, types.CallbackQuery):
        if event.data == "cancel_transaction":
            await cancel_transaction(event, state)
            return
        elif event.data == "date_today":
            from datetime import date
            selected_date = date.today().strftime("%Y-%m-%d")
        else:
            await event.answer(get_text('error', lang), show_alert=True)
            return
    else:
        # Manual date input
        date_input = event.text.strip()
        # Basic date validation
        import re
        if calendar_format == 'jalali':
            # For Jalali calendar, accept both YYYY-MM-DD and YYYY/MM/DD formats
            if not re.match(r'^\d{4}[-/]\d{2}[-/]\d{2}$', date_input):
                await event.answer(f"❌ Invalid date format. Please try again:\n\nJalali format:\n• YYYY-MM-DD or YYYY/MM/DD (e.g., 1403-06-15 or 1403/06/15)" if lang == 'en' else f"❌ فرمت تاریخ نامعتبر. لطفا از فرمت‌های زیر استفاده کنید:\n\nفرمت شمسی:\n• YYYY-MM-DD یا YYYY/MM/DD (مثال: ۱۴۰۳-۰۶-۱۵ یا ۱۴۰۳/۰۶/۱۵)")
                return
        else:
            # For Gregorian calendar, accept YYYY-MM-DD format
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_input):
                await event.answer(f"❌ Invalid date format. Please use YYYY-MM-DD format." if lang == 'en' else f"❌ فرمت تاریخ نامعتبر. لطفا از فرمت YYYY-MM-DD استفاده کنید.")
                return
        # Convert input date to Gregorian for storage
        selected_date = parse_date_input(date_input, calendar_format)

    await state.update_data(date=selected_date)

    # Move to description input (optional)
    data = await state.get_data()
    currency_display = get_text('toman', lang) if data['currency'] == 'toman' else get_text('dollar', lang)
    card_source = db.get_card_source(data['card_source_id'])

    text = f"{get_text('transaction_details', lang)}\n\n"
    text += f"{get_text('amount_label', lang)}: {format_amount(data['amount'])} {currency_display}\n"
    text += f"{get_text('card_source_label', lang)}: {card_source[1]}\n"
    text += f"{get_text('date_label', lang)}: {selected_date}\n\n"
    text += f"{get_text('enter_description', lang)}"

    buttons = [
        [InlineKeyboardButton(text="رد کردن" if lang == 'fa' else "Skip", callback_data="skip_description")],
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
    ]

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await event.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    await state.set_state(TransactionStates.waiting_for_description)

@dp.callback_query(F.data == "skip_description", StateFilter(TransactionStates.waiting_for_description))
async def skip_description(callback: types.CallbackQuery, state: FSMContext):
    """Skip description input."""
    await process_description_finish(callback, state, None)

@dp.message(TransactionStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    """Process description input."""
    await process_description_finish(message, state, message.text.strip())

async def process_description_finish(event, state: FSMContext, description):
    """Finish processing description and move to type selection."""
    user_id = event.from_user.id
    lang = db.get_user_language(user_id)

    await state.update_data(description=description or "")

    # Move to transaction type selection
    data = await state.get_data()
    currency_display = get_text('toman', lang) if data['currency'] == 'toman' else get_text('dollar', lang)
    card_source = db.get_card_source(data['card_source_id'])

    text = f"{get_text('transaction_details', lang)}\n\n"
    text += f"{get_text('amount_label', lang)}: {format_amount(data['amount'])} {currency_display}\n"
    text += f"{get_text('card_source_label', lang)}: {card_source[1]}\n"
    text += f"{get_text('date_label', lang)}: {data['date']}\n"
    if data.get('description'):
        text += f"{get_text('description_label', lang)}: {data['description']}\n\n"
    else:
        text += "\n"
    text += f"{get_text('select_type', lang)}"

    buttons = [
        [InlineKeyboardButton(text=get_text('expense_type', lang), callback_data="type_expense")],
        [InlineKeyboardButton(text=get_text('income_type', lang), callback_data="type_income")],
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
    ]

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        sent_message = await event.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        # Track message ID for cleanup
        data = await state.get_data()
        message_ids = data.get('message_ids', [])
        message_ids.append(sent_message.message_id)
        await state.update_data(message_ids=message_ids)

    await state.set_state(TransactionStates.waiting_for_type)

@dp.callback_query(TransactionStates.waiting_for_type)
async def process_type(callback: types.CallbackQuery, state: FSMContext):
    lang = get_user_lang(callback)
    if callback.data == "cancel_transaction":
        await cancel_transaction(callback, state)
        return
    
    t_type = "expense" if callback.data == "type_expense" else "income"
    await state.update_data(type=t_type)
    
    data = await state.get_data()
    amount = data.get('amount', 0)
    currency_display = get_text('toman', lang) if data['currency'] == 'toman' else get_text('dollar', lang)
    type_text = get_text('expense_type', lang) if t_type == "expense" else get_text('income_type', lang)
    card_source = db.get_card_source(data['card_source_id'])

    categories = db.get_categories(callback.from_user.id, t_type)
    if not categories:
        # Default categories based on type
        if t_type == "expense":
            categories = [
                get_text('cat_food', lang),
                get_text('cat_transport', lang),
                get_text('cat_rent', lang),
                get_text('cat_entertainment', lang),
                get_text('cat_other', lang)
            ]
        else:
            categories = [
                get_text('cat_salary', lang),
                get_text('cat_bonus', lang),
                get_text('cat_investment', lang),
                get_text('cat_other', lang)
            ]
        for cat in categories:
            db.add_category(callback.from_user.id, cat, t_type)

    text = f"{get_text('transaction_details', lang)}\n\n"
    text += f"{get_text('amount_label', lang)}: {format_amount(amount)} {currency_display}\n"
    text += f"{get_text('card_source_label', lang)}: {card_source[1]}\n"
    text += f"{get_text('currency_label', lang)}: {currency_display}\n"
    text += f"{get_text('date_label', lang)}: {data['date']}\n"
    if data.get('description'):
        text += f"{get_text('description_label', lang)}: {data['description']}\n"
    text += f"{get_text('type_label', lang)}: {type_text}\n\n"
    text += f"{get_text('select_category', lang)}"

    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}")] for cat in categories]
    buttons.append([InlineKeyboardButton(text=get_text('type_custom_category', lang), callback_data="type_custom_category")])
    buttons.append([InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")])
    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(TransactionStates.waiting_for_category)
    await callback.answer()

@dp.callback_query(TransactionStates.waiting_for_category)
async def process_category(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "cancel_transaction":
        await cancel_transaction(callback, state)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    # Only process if it's a category selection (starts with "cat_")
    if not callback.data.startswith("cat_"):
        await callback.answer(get_text('error', lang), show_alert=True)
        return
    
    category = callback.data.replace("cat_", "")
    await state.update_data(category=category)

    data = await state.get_data()
    currency_display = get_text('toman', lang) if data['currency'] == 'toman' else get_text('dollar', lang)
    type_text = get_text('expense_type', lang) if data['type'] == 'expense' else get_text('income_type', lang)
    card_source = db.get_card_source(data['card_source_id'])

    summary = f"{get_text('confirm_transaction', lang)}\n\n"
    # Format date for display
    settings = db.get_user_settings(callback.from_user.id)
    display_date = format_date_for_display(data['date'], settings['calendar_format'], lang)

    summary += f"{get_text('amount_label', lang)}: {format_amount(data['amount'])} {currency_display}\n"
    summary += f"{get_text('card_source_label', lang)}: {card_source[1]}\n"
    summary += f"{get_text('currency_label', lang)}: {currency_display}\n"
    summary += f"{get_text('type_label', lang)}: {type_text}\n"
    summary += f"{get_text('category_label', lang)}: {data['category']}\n"
    summary += f"{get_text('date_label', lang)}: {display_date}\n"
    if data.get('description'):
        summary += f"{get_text('description_label', lang)}: {data['description']}\n"
    summary += f"\n{get_text('confirm_question', lang)}"
    buttons = [
        [InlineKeyboardButton(text=get_text('confirm_btn', lang), callback_data="confirm_transaction")],
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
    ]
    await safe_edit_text(callback, summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    # Change state to None so process_category won't catch confirm_transaction callback
    # But keep the data in state for confirm_transaction handler
    await state.set_state(None)
    await callback.answer()

# Cancel transaction handler
@dp.callback_query(F.data == "cancel_transaction")
async def cancel_transaction(callback: types.CallbackQuery, state: FSMContext):
    # Delete all tracked messages from the transaction flow
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=callback.from_user.id, message_id=message_id)
        except Exception as e:
            # Ignore errors if message doesn't exist or can't be deleted
            logging.debug(f"Could not delete transaction message {message_id}: {e}")

    # Clear any existing transaction state
    await state.clear()

    lang = get_user_lang(callback)

    # Show full finance main menu (same as finance_main function)
    text = get_text('select_transaction_type', lang)

    buttons = [
        [InlineKeyboardButton(text=get_text('add_transaction', lang), callback_data="add_transaction")],
        [InlineKeyboardButton(text="📊 " + ("Reporting" if lang == 'en' else "گزارش‌گیری"), callback_data="reporting")],
        [InlineKeyboardButton(text="⚙️ " + ("Settings" if lang == 'en' else "تنظیمات"), callback_data="financial_settings")],
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
    ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer(get_text('cancel', lang))

@dp.callback_query(F.data.in_(["quick_expense", "quick_income"]))
async def quick_transaction_start(callback: types.CallbackQuery, state: FSMContext):
    """Start quick transaction (expense or income)."""
    lang = get_user_lang(callback)
    transaction_type = "expense" if callback.data == "quick_expense" else "income"
    await state.update_data(type=transaction_type)

    # Start the enhanced transaction flow from amount input
    settings = db.get_user_settings(callback.from_user.id)
    currency = settings['currency']
    currency_display = get_text('toman', lang) if currency == 'toman' else get_text('dollar', lang)

    type_text = get_text('expense_type', lang) if transaction_type == "expense" else get_text('income_type', lang)

    text = f"💰 {type_text}\n\n{get_text('enter_amount_with_currency', lang, currency=currency_display)}\n\n{get_text('cancel_hint', lang)}"
    buttons = [[InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]]

    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(TransactionStates.waiting_for_amount)
    await callback.answer()

@dp.callback_query(F.data == "type_custom_category")
async def start_custom_category_input(callback: types.CallbackQuery, state: FSMContext):
    """Allow user to type a custom category name."""
    lang = get_user_lang(callback)

    data = await state.get_data()
    t_type = data.get('type', 'expense')
    type_text = get_text('expense_type', lang) if t_type == 'expense' else get_text('income_type', lang)

    text = f"{get_text('select_category', lang)}\n\n{type_text}\n\n{get_text('enter_custom_category_name', lang)}"

    buttons = [
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
    ]

    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(TransactionStates.waiting_for_custom_category)
    await callback.answer()

@dp.message(TransactionStates.waiting_for_custom_category)
async def process_custom_category(message: types.Message, state: FSMContext):
    """Process the custom category name and create it if needed."""
    lang = db.get_user_language(message.from_user.id)
    category_name = message.text.strip()

    if not category_name:
        await message.answer(get_text('category_empty', lang))
        return

    data = await state.get_data()
    t_type = data.get('type', 'expense')

    # Check if category already exists, if not, create it
    existing_cats = db.get_categories(message.from_user.id, t_type)
    if category_name not in existing_cats:
        db.add_category(message.from_user.id, category_name, t_type)

    # Now proceed with this category
    await state.update_data(category=category_name)

    currency_display = get_text('toman', lang) if data['currency'] == 'toman' else get_text('dollar', lang)
    type_text = get_text('expense_type', lang) if t_type == 'expense' else get_text('income_type', lang)
    card_source = db.get_card_source(data['card_source_id'])

    summary = f"{get_text('confirm_transaction', lang)}\n\n"
    # Format date for display
    settings = db.get_user_settings(message.from_user.id)
    display_date = format_date_for_display(data['date'], settings['calendar_format'], lang)

    summary += f"{get_text('amount_label', lang)}: {format_amount(data['amount'])} {currency_display}\n"
    summary += f"{get_text('card_source_label', lang)}: {card_source[1]}\n"
    summary += f"{get_text('currency_label', lang)}: {currency_display}\n"
    summary += f"{get_text('type_label', lang)}: {type_text}\n"
    summary += f"{get_text('category_label', lang)}: {category_name}\n"
    summary += f"{get_text('date_label', lang)}: {display_date}\n"
    if data.get('description'):
        summary += f"{get_text('description_label', lang)}: {data['description']}\n"
    summary += f"\n{get_text('confirm_question', lang)}"

    buttons = [
        [InlineKeyboardButton(text=get_text('confirm_btn', lang), callback_data="confirm_transaction")],
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
    ]

    await message.answer(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    # Change state to None so process_category won't catch confirm_transaction callback
    await state.set_state(None)

@dp.callback_query(F.data == "confirm_transaction")
async def confirm_transaction(callback: types.CallbackQuery, state: FSMContext):
    lang = get_user_lang(callback)
    data = await state.get_data()
    if not data or 'amount' not in data:
        await callback.answer(get_text('error', lang), show_alert=True)
        await cancel_transaction(callback, state)
        return
    
    # Add transaction with enhanced parameters
    db.add_transaction(
        callback.from_user.id,
        data['amount'],
        data['currency'],
        data['type'],
        data['category'],
        data['card_source_id'],
        data['date'],
        data.get('description')
    )

    # Delete the confirmation message
    try:
        await bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
    except Exception:
        # Ignore if message was already deleted or doesn't exist
        pass

    # Get updated card/source balance
    card_source = db.get_card_source(data['card_source_id'])
    currency_display = get_text('toman', lang) if data['currency'] == 'toman' else get_text('dollar', lang)

    if lang == 'en':
        text = (
            f"{get_text('transaction_saved', lang)}\n\n"
            f"{get_text('balance_updated', lang, balance=card_source[3], currency=currency_display)}\n\n"
            f"💰 {card_source[1]} balance: {format_amount(card_source[3])} {currency_display}"
        )
    else:
        text = (
            f"{get_text('transaction_saved', lang)}\n\n"
            f"{get_text('balance_updated', lang, balance=card_source[3], currency=currency_display)}\n\n"
            f"💰 موجودی {card_source[1]}: {format_amount(card_source[3])} {currency_display}"
        )
    await send_menu_message(callback.from_user.id, text, reply_markup=finance_menu_kb(lang))

    # Delete all tracked messages from the transaction flow
    message_ids = data.get('message_ids', [])
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=callback.from_user.id, message_id=message_id)
        except Exception as e:
            # Ignore errors if message doesn't exist or can't be deleted
            logging.debug(f"Could not delete transaction message {message_id}: {e}")

    await state.clear()
    await callback.answer(get_text('done', lang))

# Categories Management
@dp.callback_query(F.data == "categories")
async def show_categories(callback: types.CallbackQuery):
    """Show user's expense and income categories."""
    lang = get_user_lang(callback)

    # Get categories with IDs
    expense_cats = db.cursor.execute("""
        SELECT id, name FROM categories
        WHERE user_id = ? AND type = 'expense'
        ORDER BY name
    """, (callback.from_user.id,)).fetchall()

    income_cats = db.cursor.execute("""
        SELECT id, name FROM categories
        WHERE user_id = ? AND type = 'income'
        ORDER BY name
    """, (callback.from_user.id,)).fetchall()

    text = f"{get_text('your_categories', lang)}\n\n"

    buttons = []

    # Expense categories section
    if expense_cats:
        text += f"{get_text('expenses', lang)}\n"
        for cat_id, cat_name in expense_cats:
            text += f"• {cat_name}\n"
            # Add edit and delete buttons for each category
            buttons.append([
                InlineKeyboardButton(text=f"✏️ {cat_name}", callback_data=f"edit_cat_{cat_id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"delete_cat_{cat_id}")
            ])
        text += "\n"
    else:
        text += f"{get_text('expenses', lang)} {get_text('no_category', lang)}\n\n"

    # Add visual separator between expense and income categories if both exist
    if expense_cats and income_cats:
        buttons.append([InlineKeyboardButton(text="━━━━━━━━━━━━━━━━━━━━━━━━━━━", callback_data="separator")])

    # Income categories section
    if income_cats:
        text += f"{get_text('incomes', lang)}\n"
        for cat_id, cat_name in income_cats:
            text += f"• {cat_name}\n"
            # Add edit and delete buttons for each category
            buttons.append([
                InlineKeyboardButton(text=f"✏️ {cat_name}", callback_data=f"edit_cat_{cat_id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"delete_cat_{cat_id}")
            ])
    else:
        text += f"{get_text('incomes', lang)} {get_text('no_category', lang)}"

    # Add buttons for creating new categories and going back
    buttons.extend([
        [InlineKeyboardButton(text=get_text('add_expense_cat', lang), callback_data="add_category_expense")],
        [InlineKeyboardButton(text=get_text('add_income_cat', lang), callback_data="add_category_income")],
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="finance_main")]
    ])

    # Delete the current message and send new categories menu
    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    except Exception:
        pass  # Ignore if message was already deleted

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.in_(["add_category_expense", "add_category_income"]))
async def start_add_category(callback: types.CallbackQuery, state: FSMContext):
    """Start adding a new category."""
    lang = get_user_lang(callback)
    cat_type = "expense" if callback.data == "add_category_expense" else "income"
    type_text = get_text('expense_type', lang) if cat_type == "expense" else get_text('income_type', lang)

    await state.update_data(category_type=cat_type)
    text = f"➕ {get_text('add_expense_cat', lang) if cat_type == 'expense' else get_text('add_income_cat', lang)}\n\n{get_text('enter_category_name', lang)}"
    buttons = [
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="categories")]
    ]

    # Delete the original categories menu message
    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    except Exception:
        pass  # Ignore if message was already deleted

    # Send new message instead of editing
    sent_message = await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    # Store the message ID to delete it later
    await state.update_data(prompt_message_id=sent_message.message_id)
    await state.set_state(CategoryStates.waiting_for_category_name)
    await callback.answer()

@dp.message(CategoryStates.waiting_for_category_name)
async def process_category_name(message: types.Message, state: FSMContext):
    """Process the new category name."""
    lang = get_user_lang(message)
    data = await state.get_data()
    cat_type = data.get('category_type', 'expense')
    category_name = message.text.strip()
    
    if not category_name:
        await message.answer(get_text('category_empty', lang))
        return
    
    # Check if category already exists
    existing_cats = db.get_categories(message.from_user.id, cat_type)
    if category_name in existing_cats:
        await message.answer(get_text('category_exists', lang, name=category_name))
        return
    
    # Add the category
    db.add_category(message.from_user.id, category_name, cat_type)

    # Delete the prompt message
    data = await state.get_data()
    prompt_message_id = data.get('prompt_message_id')
    if prompt_message_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception:
            pass  # Ignore if message was already deleted

    type_text = get_text('expense_type', lang) if cat_type == "expense" else get_text('income_type', lang)
    await message.answer(
        get_text('category_added', lang, name=category_name, type=type_text),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="categories")]
        ])
    )
    await state.clear()

@dp.callback_query(F.data.startswith("edit_cat_"))
async def start_edit_category(callback: types.CallbackQuery, state: FSMContext):
    """Start editing a category."""
    lang = get_user_lang(callback)
    data_parts = callback.data.split("_", 2)  # edit_cat_{id}

    if len(data_parts) < 2:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    cat_id = int(data_parts[2])

    # Get category info from database
    category = db.cursor.execute("""
        SELECT name, type FROM categories WHERE id = ? AND user_id = ?
    """, (cat_id, callback.from_user.id)).fetchone()

    if not category:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    cat_name, cat_type = category

    # Store the old category info
    await state.update_data(edit_category_id=cat_id, edit_category_old_name=cat_name, edit_category_type=cat_type)

    type_text = get_text('expense_type', lang) if cat_type == "expense" else get_text('income_type', lang)
    text = f"✏️ {get_text('edit_category', lang, name=cat_name, type=type_text)}\n\n{get_text('enter_new_category_name', lang)}"

    buttons = [[InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="categories")]]

    # Delete the original categories menu message
    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    except Exception:
        pass  # Ignore if message was already deleted

    # Send new message instead of editing
    sent_message = await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    # Store the message ID to delete it later
    await state.update_data(prompt_message_id=sent_message.message_id)
    await state.set_state(CategoryStates.waiting_for_category_edit)
    await callback.answer()

@dp.message(CategoryStates.waiting_for_category_edit)
async def process_edit_category_name(message: types.Message, state: FSMContext):
    """Process the edited category name."""
    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    cat_id = data.get('edit_category_id')
    cat_type = data.get('edit_category_type')
    old_name = data.get('edit_category_old_name')
    new_name = message.text.strip()

    if not new_name:
        await message.answer(get_text('category_empty', lang))
        return

    # Check if the new name already exists (but allow if it's the same as old name)
    if new_name != old_name:
        existing_cats = db.get_categories(message.from_user.id, cat_type)
        if new_name in existing_cats:
            await message.answer(get_text('category_exists', lang, name=new_name))
            return

    # Update the category
    if db.update_category(message.from_user.id, old_name, new_name, cat_type):
        # Delete the prompt message
        prompt_message_id = data.get('prompt_message_id')
        if prompt_message_id:
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
            except Exception:
                pass  # Ignore if message was already deleted

        type_text = get_text('expense_type', lang) if cat_type == "expense" else get_text('income_type', lang)
        await message.answer(
            get_text('category_updated', lang, old_name=old_name, new_name=new_name, type=type_text),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text('back', lang), callback_data="categories")]
            ])
        )
    else:
        await message.answer(get_text('error', lang))

    await state.clear()

@dp.callback_query(F.data.startswith("delete_cat_"))
async def confirm_delete_category(callback: types.CallbackQuery):
    """Confirm deletion of a category."""
    lang = get_user_lang(callback)
    data_parts = callback.data.split("_", 2)  # delete_cat_{id}

    if len(data_parts) < 2:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    cat_id = int(data_parts[2])

    # Get category info from database
    category = db.cursor.execute("""
        SELECT name, type FROM categories WHERE id = ? AND user_id = ?
    """, (cat_id, callback.from_user.id)).fetchone()

    if not category:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    cat_name, cat_type = category

    type_text = get_text('expense_type', lang) if cat_type == "expense" else get_text('income_type', lang)
    text = get_text('confirm_delete_category', lang, name=cat_name, type=type_text)

    buttons = [
        [InlineKeyboardButton(text=get_text('confirm_btn', lang), callback_data=f"confirm_delete_cat_{cat_id}")],
        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="categories")]
    ]

    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_delete_cat_"))
async def process_delete_category(callback: types.CallbackQuery):
    """Process category deletion."""
    lang = get_user_lang(callback)
    data_parts = callback.data.split("_", 3)  # confirm_delete_cat_{id}

    if len(data_parts) < 3:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    cat_id = int(data_parts[3])

    # Get category info from database
    category = db.cursor.execute("""
        SELECT name, type FROM categories WHERE id = ? AND user_id = ?
    """, (cat_id, callback.from_user.id)).fetchone()

    if not category:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    cat_name, cat_type = category

    # Check if category is used in transactions
    db.cursor.execute("""
        SELECT COUNT(*) FROM transactions
        WHERE user_id = ? AND category = ?
    """, (callback.from_user.id, cat_name))
    transaction_count = db.cursor.fetchone()[0]

    if transaction_count > 0:
        # Category is used in transactions, show warning
        type_text = get_text('expense_type', lang) if cat_type == "expense" else get_text('income_type', lang)
        text = get_text('category_in_use', lang, name=cat_name, count=transaction_count, type=type_text)
        buttons = [
            [InlineKeyboardButton(text=get_text('force_delete', lang), callback_data=f"force_delete_cat_{cat_id}")],
            [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="categories")]
        ]
        await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        # Safe to delete
        if db.delete_category(callback.from_user.id, cat_name, cat_type):
            type_text = get_text('expense_type', lang) if cat_type == "expense" else get_text('income_type', lang)
            text = get_text('category_deleted', lang, name=cat_name, type=type_text)
            buttons = [[InlineKeyboardButton(text=get_text('back', lang), callback_data="categories")]]
            await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await callback.answer(get_text('error', lang), show_alert=True)

    await callback.answer()

@dp.callback_query(F.data.startswith("force_delete_cat_"))
async def force_delete_category(callback: types.CallbackQuery):
    """Force delete a category even if it's used in transactions."""
    lang = get_user_lang(callback)
    data_parts = callback.data.split("_", 3)  # force_delete_cat_{id}

    if len(data_parts) < 3:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    cat_id = int(data_parts[3])

    # Get category info from database
    category = db.cursor.execute("""
        SELECT name, type FROM categories WHERE id = ? AND user_id = ?
    """, (cat_id, callback.from_user.id)).fetchone()

    if not category:
        await callback.answer(get_text('error', lang), show_alert=True)
        return

    cat_name, cat_type = category

    if db.delete_category(callback.from_user.id, cat_name, cat_type):
        type_text = get_text('expense_type', lang) if cat_type == "expense" else get_text('income_type', lang)
        text = get_text('category_deleted', lang, name=cat_name, type=type_text)
        buttons = [[InlineKeyboardButton(text=get_text('back', lang), callback_data="categories")]]
        await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await callback.answer(get_text('error', lang), show_alert=True)

    await callback.answer()

# Report Helper Functions
def format_transactions_page(transactions, page, per_page, lang, currency, settings, start_idx=None):
    """Format transactions for a specific page with pagination info."""
    total_transactions = len(transactions)
    total_pages = (total_transactions + per_page - 1) // per_page  # Ceiling division

    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total_transactions)
    page_transactions = transactions[start_idx:end_idx]

    text = ""
    for i, transaction in enumerate(page_transactions, start=start_idx + 1):
        trans_id, amount, trans_currency, trans_type, category, trans_date, note, card_name, card_number = transaction

        # Handle potential None values
        amount = amount or 0
        category = category or ("نامشخص" if lang == 'fa' else "Unknown")
        trans_type = trans_type or "expense"

        type_emoji = "🔼" if trans_type == "income" else "🔻"
        card_display = card_name or ("نامشخص" if lang == 'fa' else "Unknown")
        if card_number and len(card_number) >= 4:
            card_display += f" (****{card_number[-4:]})"

        # Format date for display
        display_date = format_date_for_display(trans_date, settings['calendar_format'], lang)

        text += f"{type_emoji} {format_amount(amount)} {currency} - {category} - {card_display} - {display_date}\n"
        if note:
            text += f"   💬 {note}\n"

    # Add pagination info
    if total_pages > 1:
        page_info = get_text('page_info', lang, current=page, total=total_pages)
        text += f"\n{page_info}"

    return text, total_pages, start_idx, end_idx, total_transactions

def create_pagination_buttons(page, total_pages, range_type, lang, extra_data=""):
    """Create pagination buttons for reports."""
    buttons = []

    # Navigation row
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text=get_text('previous_page', lang),
            callback_data=f"report_page_{page-1}_{range_type}{extra_data}"
        ))

    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(
            text=get_text('next_page', lang),
            callback_data=f"report_page_{page+1}_{range_type}{extra_data}"
        ))

    if nav_buttons:
        buttons.append(nav_buttons)

    # Back button
    buttons.append([InlineKeyboardButton(text=get_text('back', lang), callback_data="reporting")])

    return buttons

# Export Functions
async def generate_export_file(user_id: int, range_type: str, export_format: str, lang: str,
                              start_date_str: str = None, end_date_str: str = None,
                              start_date_display: str = None, end_date_display: str = None) -> str:
    """Generate export file in the specified format and return file path."""
    import tempfile
    import os
    from datetime import date, timedelta, datetime

    # Get date range
    today = date.today()
    if range_type == "custom":
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        range_text = f"Custom Range ({start_date_display} to {end_date_display})"
    else:
        if range_type == "overall":
            start_date = date(2000, 1, 1)
            end_date = today
            range_text = "Overall Report"
        elif range_type == "day":
            start_date = today
            end_date = today
            range_text = "Today"
        elif range_type == "week":
            start_date = today - timedelta(days=6)
            end_date = today
            range_text = "This Week"
        elif range_type == "month":
            start_date = today.replace(day=1)
            end_date = today
            range_text = "This Month"
        elif range_type == "year":
            start_date = today.replace(month=1, day=1)
            end_date = today
            range_text = "This Year"

    # Get data from database
    balance_report = db.get_balance_report(user_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    card_balances = db.get_card_source_balances_in_range(user_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    transactions = db.get_transactions_in_range(user_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    settings = db.get_user_settings(user_id)

    # Create temporary file with correct extension
    if export_format == 'excel':
        suffix = '.xlsx'
    elif export_format == 'pdf':
        suffix = '.pdf'
    elif export_format == 'csv':
        suffix = '.csv'
    else:
        suffix = f'.{export_format}'

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        file_path = temp_file.name

    try:
        if export_format == 'csv':
            generate_csv_export(file_path, balance_report, card_balances, transactions, range_text, settings, lang)
        elif export_format == 'excel':
            generate_excel_export(file_path, balance_report, card_balances, transactions, range_text, settings, lang)
        elif export_format == 'pdf':
            generate_pdf_export(file_path, balance_report, card_balances, transactions, range_text, settings, lang)
        return file_path
    except Exception as e:
        # Clean up on error
        if os.path.exists(file_path):
            os.remove(file_path)
        raise e

def generate_csv_export(file_path: str, balance_report: dict, card_balances: list,
                             transactions: list, range_text: str, settings: dict, lang: str):
    """Generate CSV export file."""
    import csv

    with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)

        # Write report header
        writer.writerow([get_text('reporting_title', lang) + f" - {range_text}"])
        writer.writerow([])

        # Write financial summary section
        writer.writerow(["FINANCIAL SUMMARY"])
        currency = get_text('toman', lang) if settings['currency'] == 'toman' else get_text('dollar', lang)
        writer.writerow(['Metric' if lang == 'en' else 'متریک', 'Value' if lang == 'en' else 'مقدار'])
        writer.writerow([get_text('amount_earned', lang), f"{format_amount(balance_report['income'] or 0)} {currency}"])
        writer.writerow([get_text('amount_spent', lang), f"{format_amount(balance_report['expense'] or 0)} {currency}"])
        writer.writerow([get_text('current_balance', lang), f"{format_amount(balance_report['balance'] or 0)} {currency}"])
        writer.writerow([])

        # Write card/source balances section
        if card_balances:
            writer.writerow(["CARD/SOURCE BALANCES"])
            headers = ['Card/Source' if lang == 'en' else 'کارت/منبع',
                      'Start Balance' if lang == 'en' else 'موجودی اولیه',
                      'Net Change' if lang == 'en' else 'تغییر خالص',
                      'End Balance' if lang == 'en' else 'موجودی نهایی']
            writer.writerow(headers)

            for card in card_balances:
                card_display = card['name'] or ("نامشخص" if lang == 'fa' else "Unknown")
                if card['card_number'] and len(card['card_number']) >= 4:
                    card_display += f" (****{card['card_number'][-4:]})"
                writer.writerow([
                    card_display,
                    card['start_balance'] or 0,
                    card['net_change'] or 0,
                    card['end_balance'] or 0
                ])
            writer.writerow([])

        # Write transactions section
        if transactions:
            writer.writerow(["TRANSACTIONS"])
            headers = ['Date' if lang == 'en' else 'تاریخ',
                      'Type' if lang == 'en' else 'نوع',
                      'Category' if lang == 'en' else 'دسته',
                      'Amount' if lang == 'en' else 'مبلغ',
                      'Currency' if lang == 'en' else 'ارز',
                      'Card/Source' if lang == 'en' else 'کارت/منبع',
                      'Note' if lang == 'en' else 'توضیحات']
            writer.writerow(headers)

            for transaction in transactions:
                trans_id, amount, trans_currency, trans_type, category, trans_date, note, card_name, card_number = transaction

                type_text = "درآمد" if trans_type == "income" and lang == 'fa' else ("هزینه" if trans_type == "expense" and lang == 'fa' else ("Income" if trans_type == "income" else "Expense"))
                category = category or ("نامشخص" if lang == 'fa' else "Unknown")
                card_display = card_name or ("نامشخص" if lang == 'fa' else "Unknown")
                if card_number and len(card_number) >= 4:
                    card_display += f" (****{card_number[-4:]})"

                writer.writerow([
                    trans_date,
                    type_text,
                    category,
                    amount or 0,
                    trans_currency or settings['currency'],
                    card_display,
                    note or ""
                ])

def generate_excel_export(file_path: str, balance_report: dict, card_balances: list,
                               transactions: list, range_text: str, settings: dict, lang: str):
    """Generate Excel export file."""
    import pandas as pd

    # Create Excel writer
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        # Summary sheet - clean financial overview
        currency = get_text('toman', lang) if settings['currency'] == 'toman' else get_text('dollar', lang)
        summary_data = [
            {'Metric' if lang == 'en' else 'متریک': get_text('amount_earned', lang),
             'Value' if lang == 'en' else 'مقدار': f"{format_amount(balance_report['income'] or 0)} {currency}"},
            {'Metric' if lang == 'en' else 'متریک': get_text('amount_spent', lang),
             'Value' if lang == 'en' else 'مقدار': f"{format_amount(balance_report['expense'] or 0)} {currency}"},
            {'Metric' if lang == 'en' else 'متریک': get_text('current_balance', lang),
             'Value' if lang == 'en' else 'مقدار': f"{format_amount(balance_report['balance'] or 0)} {currency}"}
        ]
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary' if lang == 'en' else 'خلاصه', index=False)

        # Card balances sheet
        if card_balances:
            card_data = []
            for card in card_balances:
                card_display = card['name'] or ("نامشخص" if lang == 'fa' else "Unknown")
                if card['card_number'] and len(card['card_number']) >= 4:
                    card_display += f" (****{card['card_number'][-4:]})"
                card_data.append({
                    'Card/Source' if lang == 'en' else 'کارت/منبع': card_display,
                    'Start Balance' if lang == 'en' else 'موجودی اولیه': card['start_balance'] or 0,
                    'Net Change' if lang == 'en' else 'تغییر خالص': card['net_change'] or 0,
                    'End Balance' if lang == 'en' else 'موجودی نهایی': card['end_balance'] or 0
                })
            card_df = pd.DataFrame(card_data)
            card_df.to_excel(writer, sheet_name='Cards' if lang == 'en' else 'کارت‌ها', index=False)

        # Transactions sheet
        if transactions:
            transaction_data = []
            for transaction in transactions:
                trans_id, amount, trans_currency, trans_type, category, trans_date, note, card_name, card_number = transaction

                type_text = "درآمد" if trans_type == "income" and lang == 'fa' else ("هزینه" if trans_type == "expense" and lang == 'fa' else ("Income" if trans_type == "income" else "Expense"))
                category = category or ("نامشخص" if lang == 'fa' else "Unknown")
                card_display = card_name or ("نامشخص" if lang == 'fa' else "Unknown")
                if card_number and len(card_number) >= 4:
                    card_display += f" (****{card_number[-4:]})"

                transaction_data.append({
                    'Date' if lang == 'en' else 'تاریخ': trans_date,
                    'Type' if lang == 'en' else 'نوع': type_text,
                    'Category' if lang == 'en' else 'دسته': category,
                    'Amount' if lang == 'en' else 'مبلغ': amount or 0,
                    'Currency' if lang == 'en' else 'ارز': trans_currency or settings['currency'],
                    'Card/Source' if lang == 'en' else 'کارت/منبع': card_display,
                    'Note' if lang == 'en' else 'توضیحات': note or ""
                })
            trans_df = pd.DataFrame(transaction_data)
            trans_df.to_excel(writer, sheet_name='Transactions' if lang == 'en' else 'تراکنش‌ها', index=False)

def generate_pdf_export(file_path: str, balance_report: dict, card_balances: list,
                             transactions: list, range_text: str, settings: dict, lang: str):
    """Generate PDF export file in a report-style format (no tables)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Create PDF document with proper Unicode support for Persian
    from reportlab.lib.pagesizes import A4

    # Set up document with explicit Unicode support
    doc = SimpleDocTemplate(file_path,
                           pagesize=A4,
                           rightMargin=40,
                           leftMargin=40,
                           topMargin=40,
                           bottomMargin=40,
                           encoding='utf-8')

    styles = getSampleStyleSheet()

    # Enable full Unicode support for Persian characters
    from reportlab.pdfbase import pdfdoc
    from reportlab.pdfbase import pdfmetrics

    # Set Unicode encoding for proper Persian character support
    pdfdoc.unicode = True

    # Configure PDF for Unicode text rendering
    try:
        # Ensure proper encoding setup
        import locale
        try:
            # Try Persian locale if available
            locale.setlocale(locale.LC_ALL, 'fa_IR.UTF-8')
        except:
            try:
                # Fallback to general UTF-8 locale
                locale.setlocale(locale.LC_ALL, 'C.UTF-8')
            except:
                # If locale setting fails, continue without it
                pass
    except:
        pass

    # Force English for PDF export regardless of user language
    pdf_lang = 'en'
    is_persian = False  # Always use LTR layout for English PDF

    # Try to use a font that definitely supports Persian characters
    persian_font = 'Helvetica'  # Default fallback

    if is_persian:
        try:
            # Try to register fonts that support Persian/Arabic characters
            # First try to use system fonts that are known to support Persian
            persian_font_names = [
                'Arial Unicode MS',  # Best Persian support
                'Tahoma',            # Good Persian support
                'DejaVu Sans',       # Good Unicode support
                'Times New Roman',   # Decent Unicode support
                'Arial',             # Common system font
            ]

            font_loaded = False
            for font_name in persian_font_names:
                try:
                    # Try to register the font
                    from reportlab.pdfbase.ttfonts import TTFont
                    pdfmetrics.registerFont(TTFont(font_name, font_name))
                    persian_font = font_name
                    font_loaded = True
                    print(f"Successfully loaded Persian font: {font_name}")
                    break
                except Exception as e:
                    # Font not available, try next one
                    continue

            if not font_loaded:
                # If no Persian fonts work, try built-in fonts that might have Unicode support
                persian_font = 'Times-Roman'  # Often has better Unicode than Helvetica
                print("Using Times-Roman as Persian fallback")

        except Exception as e:
            print(f"Persian font setup error: {e}")
            persian_font = 'Helvetica'

    # Custom styles for report-style layout with proper font handling
    # Use fonts that ReportLab knows about and can map properly
    base_font = persian_font if is_persian else 'Helvetica'
    bold_font = persian_font + '-Bold' if is_persian else 'Helvetica-Bold'
    italic_font = persian_font + '-Oblique' if is_persian else 'Helvetica-Oblique'

    # Configure font encoding for Persian/Unicode support
    if is_persian:
        try:
            # Ensure proper Unicode handling for Persian text
            from reportlab.lib.enums import TA_RIGHT
            # Test font loading to ensure it works
            pdfmetrics.setFont(base_font, 10)

            # Additional Unicode configuration for Persian
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.enums import TA_JUSTIFY

            # For Persian, we might want right alignment for better RTL appearance
            # But let's keep left alignment for consistency with LTR languages

        except Exception as e:
            print(f"Persian font configuration issue: {e}")
            # If Persian font fails, fall back to standard Helvetica
            base_font = 'Helvetica'
            bold_font = 'Helvetica-Bold'
            italic_font = 'Helvetica-Oblique'

    # Ensure fonts are available, fallback to standard fonts if needed
    try:
        title_style = ParagraphStyle('Title',
                                   parent=styles['Heading1'],
                                   alignment=TA_CENTER,
                                   fontSize=20,
                                   spaceAfter=25,
                                   textColor=colors.darkblue,
                                   fontName=bold_font)
    except:
        title_style = ParagraphStyle('Title',
                                   parent=styles['Heading1'],
                                   alignment=TA_CENTER,
                                   fontSize=20,
                                   spaceAfter=25,
                                   textColor=colors.darkblue,
                                   fontName='Helvetica-Bold')

    try:
        section_style = ParagraphStyle('Section',
                                     parent=styles['Heading2'],
                                     alignment=TA_LEFT,
                                     fontSize=16,
                                     spaceAfter=15,
                                     textColor=colors.darkgreen,
                                     fontName=bold_font)
    except:
        section_style = ParagraphStyle('Section',
                                     parent=styles['Heading2'],
                                     alignment=TA_LEFT,
                                     fontSize=16,
                                     spaceAfter=15,
                                     textColor=colors.darkgreen,
                                     fontName='Helvetica-Bold')

    try:
        summary_style = ParagraphStyle('Summary',
                                     parent=styles['Normal'],
                                     fontSize=12,
                                     alignment=TA_LEFT,
                                     spaceAfter=8,
                                     fontName=base_font)
    except:
        summary_style = ParagraphStyle('Summary',
                                     parent=styles['Normal'],
                                     fontSize=12,
                                     alignment=TA_LEFT,
                                     spaceAfter=8,
                                     fontName='Helvetica')

    try:
        transaction_style = ParagraphStyle('Transaction',
                                         parent=styles['Normal'],
                                         fontSize=10,
                                         alignment=TA_LEFT,
                                         spaceAfter=5,
                                         fontName=base_font,
                                         leftIndent=20)
    except:
        transaction_style = ParagraphStyle('Transaction',
                                         parent=styles['Normal'],
                                         fontSize=10,
                                         alignment=TA_LEFT,
                                         spaceAfter=5,
                                         fontName='Helvetica',
                                         leftIndent=20)

    try:
        note_style = ParagraphStyle('Note',
                                  parent=styles['Normal'],
                                  fontSize=9,
                                  alignment=TA_LEFT,
                                  spaceAfter=3,
                                  fontName=italic_font,
                                  leftIndent=40)
    except:
        note_style = ParagraphStyle('Note',
                                  parent=styles['Normal'],
                                  fontSize=9,
                                  alignment=TA_LEFT,
                                  spaceAfter=3,
                                  fontName='Helvetica-Oblique',
                                  leftIndent=40)

    elements = []
    currency = get_text('toman', pdf_lang) if settings['currency'] == 'toman' else get_text('dollar', pdf_lang)

    # Title
    title_text = f"{get_text('reporting_title', pdf_lang)} - {range_text}"
    title_text = str(title_text)
    elements.append(Paragraph(title_text, title_style))

    # Financial Summary Section - Report Style
    summary_title = "💰 Financial Summary"
    elements.append(Paragraph(summary_title, section_style))

    summary_lines = [
        f"💵 {get_text('amount_earned', pdf_lang)}: <b>{format_amount(balance_report['income'] or 0)} {currency}</b>",
        f"💸 {get_text('amount_spent', pdf_lang)}: <b>{format_amount(balance_report['expense'] or 0)} {currency}</b>",
        f"⚖️ {get_text('current_balance', pdf_lang)}: <b>{format_amount(balance_report['balance'] or 0)} {currency}</b>"
    ]

    for line in summary_lines:
        elements.append(Paragraph(line, summary_style))

    elements.append(Spacer(1, 20))

    # Card Balances Section - Report Style
    if card_balances:
        card_title = "💳 " + get_text('card_source_balances', pdf_lang)
        elements.append(Paragraph(card_title, section_style))

        for card in card_balances:
            card_display = card['name'] or "Unknown"
            if card['card_number'] and len(card['card_number']) >= 4:
                card_display += f" (****{card['card_number'][-4:]})"

            start_balance_text = 'Start Balance'
            net_change_text = 'Net Change'
            end_balance_text = 'End Balance'

            card_line = f"• <b>{card_display}</b><br/>"
            card_line += f"  📊 {start_balance_text}: {format_amount(card['start_balance'] or 0)} {currency}<br/>"
            card_line += f"  📈 {net_change_text}: {format_amount(card['net_change'] or 0)} {currency}<br/>"
            card_line += f"  💰 {end_balance_text}: {format_amount(card['end_balance'] or 0)} {currency}"

            card_line = str(card_line)  # Ensure Unicode string
            elements.append(Paragraph(card_line, summary_style))
            elements.append(Spacer(1, 10))

    # Transactions Section - Report Style
    if transactions:
        trans_title = "📋 " + get_text('transactions_in_range', pdf_lang)
        elements.append(Paragraph(trans_title, section_style))

        # Group transactions by date for better organization
        from collections import defaultdict
        transactions_by_date = defaultdict(list)

        for transaction in transactions:
            trans_id, amount, trans_currency, trans_type, category, trans_date, note, card_name, card_number = transaction
            transactions_by_date[trans_date].append(transaction)

        # Sort dates
        sorted_dates = sorted(transactions_by_date.keys(), reverse=True)

        for trans_date in sorted_dates:
            # Date header
            date_header = f"📅 {trans_date}"
            date_header = str(date_header)  # Ensure Unicode string
            elements.append(Paragraph(date_header, section_style))
            elements.append(Spacer(1, 5))

            # Transactions for this date
            for transaction in transactions_by_date[trans_date]:
                trans_id, amount, trans_currency, trans_type, category, trans_date, note, card_name, card_number = transaction

                type_emoji = "💰" if trans_type == "income" else "💸"
                type_text = "Income" if trans_type == "income" else "Expense"
                category = category or "Unknown"
                card_display = card_name or "Unknown"
                if card_number and len(card_number) >= 4:
                    card_display += f" (****{card_number[-4:]})"

                # Transaction line
                trans_line = f"{type_emoji} <b>{format_amount(amount or 0)} {trans_currency or currency}</b> - {category} - {card_display}"
                elements.append(Paragraph(trans_line, transaction_style))

                # Note if exists
                if note:
                    note_line = f"💬 {note}"
                    elements.append(Paragraph(note_line, note_style))

            elements.append(Spacer(1, 10))

            # Check if we need a page break (roughly every 20 transactions to prevent overflow)
            total_so_far = sum(len(transactions_by_date[d]) for d in sorted_dates[:sorted_dates.index(trans_date) + 1])
            if total_so_far % 20 == 0 and trans_date != sorted_dates[-1]:
                elements.append(PageBreak())

    # Build PDF
    doc.build(elements)

# Reports
@dp.callback_query(F.data == "reporting")
async def reporting(callback: types.CallbackQuery):
    """Show time range selection for reporting."""
    lang = get_user_lang(callback)

    text = get_text('reporting_title', lang) + "\n\n" + get_text('select_time_range', lang)

    buttons = [
        [InlineKeyboardButton(text=get_text('time_range_overall', lang), callback_data="report_range_overall")],
        [InlineKeyboardButton(text=get_text('time_range_day', lang), callback_data="report_range_day")],
        [InlineKeyboardButton(text=get_text('time_range_week', lang), callback_data="report_range_week")],
        [InlineKeyboardButton(text=get_text('time_range_month', lang), callback_data="report_range_month")],
        [InlineKeyboardButton(text=get_text('time_range_year', lang), callback_data="report_range_year")],
        [InlineKeyboardButton(text=get_text('time_range_custom', lang), callback_data="report_range_custom")],
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="finance_main")]
    ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "report_range_custom")
async def custom_report_range(callback: types.CallbackQuery, state: FSMContext):
    """Handle custom time range selection."""
    lang = get_user_lang(callback)
    settings = db.get_user_settings(callback.from_user.id)
    calendar_format = "Jalali (YYYY/MM/DD)" if settings['calendar_format'] == 'jalali' else "Gregorian (YYYY-MM-DD)"

    if settings['calendar_format'] == 'jalali':
        calendar_format = "Jalali (YYYY/MM/DD or MM/DD/YYYY)"
    else:
        calendar_format = "Gregorian (YYYY-MM-DD)"
    text = get_text('enter_start_date', lang, calendar_format=calendar_format)
    cancel_button = [[InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="reporting")]]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=cancel_button))
    await state.set_state(CustomReportStates.waiting_for_start_date)
    await callback.answer()

@dp.message(CustomReportStates.waiting_for_start_date)
async def process_start_date(message: types.Message, state: FSMContext):
    """Process the start date input."""
    lang = get_user_lang(message)
    settings = db.get_user_settings(message.from_user.id)

    try:
        if settings['calendar_format'] == 'jalali':
            # Parse Jalali date - try both YYYY/MM/DD and MM/DD/YYYY formats
            parts = message.text.strip().split('/')
            if len(parts) != 3:
                raise ValueError("Invalid format")

            jy, jm, jd = map(int, parts)

            # Try to detect format: if first part looks like a year (4 digits or >= 100), assume YYYY/MM/DD
            # if first part is small and third part looks like a year, assume MM/DD/YYYY
            if jy >= 100 or len(str(jy)) == 4:  # Likely a year in YYYY/MM/DD format
                pass  # jy, jm, jd are already in correct order
            elif jy <= 12 and jm <= 31 and (jd >= 100 or len(str(jd)) == 4):  # Likely MM/DD/YYYY format
                jy, jm, jd = jd, jy, jm
            else:
                # Ambiguous, assume YYYY/MM/DD format
                pass

            # Validate date ranges
            if not (1 <= jm <= 12):
                raise ValueError("Invalid month")
            if not (1 <= jd <= 31):
                raise ValueError("Invalid day")
            if jy < 1200 or jy > 1500:  # Reasonable year range for Jalali calendar
                raise ValueError("Invalid year")

            from persiantools.jdatetime import JalaliDate
            try:
                jalali_date = JalaliDate(jy, jm, jd)
                start_date = jalali_date.to_gregorian()
            except Exception as e:
                # If JalaliDate fails, try to provide a more specific error
                if "day is out of range" in str(e) or "invalid day" in str(e).lower():
                    raise ValueError(f"Invalid day for Jalali date {jy}/{jm}/{jd}")
                elif "month is out of range" in str(e) or "invalid month" in str(e).lower():
                    raise ValueError(f"Invalid month for Jalali date {jy}/{jm}/{jd}")
                else:
                    raise ValueError(f"Invalid Jalali date {jy}/{jm}/{jd}: {str(e)}")
        else:
            # Parse Gregorian date (YYYY-MM-DD)
            from datetime import datetime
            start_date = datetime.strptime(message.text.strip(), "%Y-%m-%d").date()

        # Store start date as string for FSM compatibility
        await state.update_data(start_date=start_date.strftime("%Y-%m-%d"))
        calendar_format = "Jalali (YYYY/MM/DD)" if settings['calendar_format'] == 'jalali' else "Gregorian (YYYY-MM-DD)"

        if settings['calendar_format'] == 'jalali':
            calendar_format = "Jalali (YYYY/MM/DD or MM/DD/YYYY)"
        else:
            calendar_format = "Gregorian (YYYY-MM-DD)"
        text = get_text('enter_end_date', lang, calendar_format=calendar_format)
        cancel_button = [[InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="reporting")]]

        await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=cancel_button))
        await state.set_state(CustomReportStates.waiting_for_end_date)

    except (ValueError, AttributeError) as e:
        error_msg = str(e)
        text = get_text('invalid_date_format', lang)
        if settings['calendar_format'] == 'jalali':
            text += "\n\nJalali (شمسی) formats:\n• YYYY/MM/DD (e.g., 1404/04/04)\n• MM/DD/YYYY (e.g., 04/04/1404)"
            if error_msg and error_msg != "Invalid format":
                text += f"\n\nError: {error_msg}"
        else:
            text += "\n\nGregorian format:\n• YYYY-MM-DD (e.g., 2025-06-25)"
            if error_msg and error_msg != "Invalid format":
                text += f"\n\nError: {error_msg}"
        cancel_button = [[InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="reporting")]]

        await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=cancel_button))

@dp.message(CustomReportStates.waiting_for_end_date)
async def process_end_date(message: types.Message, state: FSMContext):
    """Process the end date input and show custom report."""
    lang = get_user_lang(message)
    settings = db.get_user_settings(message.from_user.id)

    try:
        if settings['calendar_format'] == 'jalali':
            # Parse Jalali date - try both YYYY/MM/DD and MM/DD/YYYY formats
            date_text = message.text.strip()
            parts = date_text.split('/')
            if len(parts) != 3:
                raise ValueError("Invalid format")

            jy, jm, jd = map(int, parts)

            # Try to detect format: if first part looks like a year (4 digits or >= 100), assume YYYY/MM/DD
            # if first part is small and third part looks like a year, assume MM/DD/YYYY
            if jy >= 100 or len(str(jy)) == 4:  # Likely a year in YYYY/MM/DD format
                pass  # jy, jm, jd are already in correct order
            elif jy <= 12 and jm <= 31 and (jd >= 100 or len(str(jd)) == 4):  # Likely MM/DD/YYYY format
                jy, jm, jd = jd, jy, jm
            else:
                # Ambiguous, assume YYYY/MM/DD format
                pass

            # Validate date ranges
            if not (1 <= jm <= 12):
                raise ValueError("Invalid month")
            if not (1 <= jd <= 31):
                raise ValueError("Invalid day")
            if jy < 1200 or jy > 1500:  # Reasonable year range for Jalali calendar
                raise ValueError("Invalid year")

            from persiantools.jdatetime import JalaliDate
            try:
                jalali_date = JalaliDate(jy, jm, jd)
                end_date = jalali_date.to_gregorian()
            except Exception as e:
                # If JalaliDate fails, try to provide a more specific error
                if "day is out of range" in str(e) or "invalid day" in str(e).lower():
                    raise ValueError(f"Invalid day for Jalali date {jy}/{jm}/{jd}")
                elif "month is out of range" in str(e) or "invalid month" in str(e).lower():
                    raise ValueError(f"Invalid month for Jalali date {jy}/{jm}/{jd}")
                else:
                    raise ValueError(f"Invalid Jalali date {jy}/{jm}/{jd}: {str(e)}")
        else:
            # Parse Gregorian date (YYYY-MM-DD)
            from datetime import datetime
            end_date = datetime.strptime(message.text.strip(), "%Y-%m-%d").date()

        # Get stored start date
        data = await state.get_data()
        start_date = data.get('start_date')

        # Ensure start_date is a date object (FSM might serialize it as string)
        if isinstance(start_date, str):
            from datetime import datetime
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

        if start_date and end_date < start_date:
            text = "❌ تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد." if lang == 'fa' else "❌ End date cannot be before start date."
            calendar_format = "Jalali (YYYY/MM/DD)" if settings['calendar_format'] == 'jalali' else "Gregorian (YYYY-MM-DD)"
            text += f"\n\n{calendar_format}"
            cancel_button = [[InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="reporting")]]

            await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=cancel_button))
            return

        await state.clear()

        # Format dates for display
        if settings['calendar_format'] == 'jalali':
            from persiantools.jdatetime import JalaliDate
            start_jalali = JalaliDate.to_jalali(start_date.year, start_date.month, start_date.day)
            end_jalali = JalaliDate.to_jalali(end_date.year, end_date.month, end_date.day)
            start_date_display = f"{start_jalali.year}/{start_jalali.month:02d}/{start_jalali.day:02d}"
            end_date_display = f"{end_jalali.year}/{end_jalali.month:02d}/{end_jalali.day:02d}"
        else:
            start_date_display = start_date.strftime("%Y-%m-%d")
            end_date_display = end_date.strftime("%Y-%m-%d")

        # Generate custom report
        await generate_custom_report(message.from_user.id, start_date, end_date, start_date_display, end_date_display, lang)

    except (ValueError, AttributeError) as e:
        error_msg = str(e)
        text = get_text('invalid_date_format', lang)
        if settings['calendar_format'] == 'jalali':
            text += "\n\nJalali (شمسی) formats:\n• YYYY/MM/DD (e.g., 1404/04/04)\n• MM/DD/YYYY (e.g., 04/04/1404)"
            if error_msg and error_msg != "Invalid format":
                text += f"\n\nError: {error_msg}"
        else:
            text += "\n\nGregorian format:\n• YYYY-MM-DD (e.g., 2025-06-25)"
            if error_msg and error_msg != "Invalid format":
                text += f"\n\nError: {error_msg}"
        cancel_button = [[InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="reporting")]]

        await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=cancel_button))

async def generate_custom_report(user_id: int, start_date, end_date, start_date_display: str, end_date_display: str, lang: str):
    """Generate and send custom date range report."""
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    # Get balance report for the range
    balance_report = db.get_balance_report(user_id, start_date_str, end_date_str)

    # Get card/source balances for the range
    card_balances = db.get_card_source_balances_in_range(user_id, start_date_str, end_date_str)

    # Get transactions in the range
    transactions = db.get_transactions_in_range(user_id, start_date_str, end_date_str)

    settings = db.get_user_settings(user_id)
    currency = get_text('toman', lang) if settings['currency'] == 'toman' else get_text('dollar', lang)

    range_text = get_text('custom_range_title', lang, start_date=start_date_display, end_date=end_date_display)
    text = f"{get_text('reporting_title', lang)} - {range_text}\n\n"

    # Financial summary
    income = balance_report['income'] or 0
    expense = balance_report['expense'] or 0
    balance = balance_report['balance'] or 0

    text += f"{get_text('amount_earned', lang)} {format_amount(income)} {currency}\n"
    text += f"{get_text('amount_spent', lang)} {format_amount(expense)} {currency}\n"
    text += f"{get_text('current_balance', lang)} {format_amount(balance)} {currency}\n\n"

    # Card/source balances
    if card_balances:
        text += f"{get_text('card_source_balances', lang)}\n"
        for balance_info in card_balances:
            text += f"• {balance_info['name']}: {format_amount(balance_info['end_balance'] or 0)} {currency}\n"
        text += "\n"

    # Recent transactions
    if transactions:
        text += f"{get_text('transactions_in_range', lang)}\n"

        if len(transactions) <= 10:
            # Show all transactions if 10 or fewer
            for i, transaction in enumerate(transactions):
                trans_id, amount, trans_currency, trans_type, category, trans_date, note, card_source_name, card_number = transaction

                # Handle potential None values
                amount = amount or 0
                category = category or ("سایر" if lang == 'fa' else "Other")
                trans_type = trans_type or "expense"
                card_source = card_source_name or ""

                # Convert string date to datetime object if needed
                if isinstance(trans_date, str):
                    from datetime import datetime
                    trans_date = datetime.strptime(trans_date, "%Y-%m-%d").date()

                if settings['calendar_format'] == 'jalali':
                    from persiantools.jdatetime import JalaliDate
                    jalali_date = JalaliDate.to_jalali(trans_date.year, trans_date.month, trans_date.day)
                    date_str = f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d}"
                else:
                    date_str = trans_date.strftime("%Y-%m-%d")

                type_symbol = "🔼" if trans_type == 'income' else "🔻"

                card_text = f" ({card_source})" if card_source else ""
                text += f"{type_symbol} {amount:,} {currency} - {category}{card_text} - {date_str}\n"
            buttons = [
                [InlineKeyboardButton(text=get_text('export_report', lang), callback_data=f"export_report_custom_{start_date_str}_{end_date_str}_{start_date_display.replace('/', '-').replace(' ', '_')}_{end_date_display.replace('/', '-').replace(' ', '_')}")],
                [InlineKeyboardButton(text=get_text('back', lang), callback_data="reporting")]
            ]
        else:
            # Use pagination for more than 10 transactions
            page = 1
            per_page = 5  # Show 5 transactions per page for better readability
            transaction_text, total_pages, start_idx, end_idx, total_transactions = format_transactions_page(
                transactions, page, per_page, lang, currency, settings
            )
            text += transaction_text
            # For custom reports, we need to pass extra data for the date range
            start_date_display = start_date_display.replace('/', '-').replace(' ', '_')
            end_date_display = end_date_display.replace('/', '-').replace(' ', '_')
            extra_data = f"_{start_date_str}_{end_date_str}_{start_date_display}_{end_date_display}"
            buttons = create_pagination_buttons(page, total_pages, "custom", lang, extra_data)
            # Add export button at the end
            buttons.append([InlineKeyboardButton(text=get_text('export_report', lang), callback_data=f"export_report_custom_{start_date_str}_{end_date_str}_{start_date_display}_{end_date_display}")])
    else:
        text += f"{get_text('no_transactions', lang)}\n"
        buttons = [
            [InlineKeyboardButton(text=get_text('export_report', lang), callback_data=f"export_report_custom_{start_date_str}_{end_date_str}_{start_date_display.replace('/', '-').replace(' ', '_')}_{end_date_display.replace('/', '-').replace(' ', '_')}")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="reporting")]
        ]

    await send_menu_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("report_range_"))
async def show_report(callback: types.CallbackQuery):
    """Show detailed report for selected time range."""
    lang = get_user_lang(callback)
    range_type = callback.data.replace("report_range_", "")

    from datetime import date, timedelta

    today = date.today()
    if range_type == "overall":
        start_date = date(2000, 1, 1)  # Very early date to cover all transactions
        end_date = today
        range_text = "گزارش کلی" if lang == 'fa' else "Overall Report"
    elif range_type == "day":
        start_date = today
        end_date = today
        range_text = "امروز" if lang == 'fa' else "Today"
    elif range_type == "week":
        start_date = today - timedelta(days=6)  # Include today, so 7 days total
        end_date = today
        range_text = "هفته جاری" if lang == 'fa' else "This Week"
    elif range_type == "month":
        start_date = today.replace(day=1)
        end_date = today
        range_text = "ماه جاری" if lang == 'fa' else "This Month"
    elif range_type == "year":
        start_date = today.replace(month=1, day=1)
        end_date = today
        range_text = "سال جاری" if lang == 'fa' else "This Year"

    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    # Get balance report for the range
    balance_report = db.get_balance_report(callback.from_user.id, start_date_str, end_date_str)

    # Get card/source balances for the range
    card_balances = db.get_card_source_balances_in_range(callback.from_user.id, start_date_str, end_date_str)

    # Get transactions in the range
    transactions = db.get_transactions_in_range(callback.from_user.id, start_date_str, end_date_str)

    settings = db.get_user_settings(callback.from_user.id)
    currency = get_text('toman', lang) if settings['currency'] == 'toman' else get_text('dollar', lang)

    text = f"{get_text('reporting_title', lang)} - {range_text}\n\n"

    # Financial summary
    income = balance_report['income'] or 0
    expense = balance_report['expense'] or 0
    balance = balance_report['balance'] or 0
    text += f"{get_text('amount_earned', lang)}: {format_amount(income)} {currency}\n"
    text += f"{get_text('amount_spent', lang)}: {format_amount(expense)} {currency}\n"
    text += f"{get_text('current_balance', lang)}: {format_amount(balance)} {currency}\n\n"

    # Card/Source balances
    if card_balances:
        text += f"{get_text('card_source_balances', lang)}:\n"
        for card in card_balances:
            card_display = card['name'] or ("نامشخص" if lang == 'fa' else "Unknown")
            if card['card_number'] and len(card['card_number']) >= 4:
                card_display += f" (****{card['card_number'][-4:]})"

            end_balance = card['end_balance'] or 0
            net_change = card['net_change'] or 0

            text += f"• {card_display}: {format_amount(end_balance)} {currency}"
            if net_change != 0:
                change_text = f"(تغییر: {'+' if net_change > 0 else ''}{format_amount(net_change)})" if lang == 'fa' else f"(Change: {'+' if net_change > 0 else ''}{format_amount(net_change)})"
                text += f" {change_text}"
            text += "\n"
        text += "\n"

    # Transactions list
    if transactions:
        text += f"{get_text('transactions_in_range', lang)}\n"

        if len(transactions) <= 10:
            # Show all transactions if 10 or fewer
            for transaction in transactions:
                trans_id, amount, trans_currency, trans_type, category, trans_date, note, card_name, card_number = transaction

                # Handle potential None values
                amount = amount or 0
                category = category or ("نامشخص" if lang == 'fa' else "Unknown")
                trans_type = trans_type or "expense"

                type_emoji = "🔼" if trans_type == "income" else "🔻"
                card_display = card_name or ("نامشخص" if lang == 'fa' else "Unknown")
                if card_number and len(card_number) >= 4:
                    card_display += f" (****{card_number[-4:]})"

                # Format date for display
                display_date = format_date_for_display(trans_date, settings['calendar_format'], lang)

                text += f"{type_emoji} {format_amount(amount)} {currency} - {category} - {card_display} - {display_date}\n"
                if note:
                    text += f"   💬 {note}\n"
            buttons = [
                [InlineKeyboardButton(text=get_text('export_report', lang), callback_data=f"export_report_{range_type}")],
                [InlineKeyboardButton(text=get_text('back', lang), callback_data="reporting")]
            ]
        else:
            # Use pagination for more than 10 transactions
            page = 1
            per_page = 5  # Show 5 transactions per page for better readability
            transaction_text, total_pages, start_idx, end_idx, total_transactions = format_transactions_page(
                transactions, page, per_page, lang, currency, settings
            )
            text += transaction_text
            buttons = create_pagination_buttons(page, total_pages, range_type, lang)
            # Add export button at the end
            buttons.append([InlineKeyboardButton(text=get_text('export_report', lang), callback_data=f"export_report_{range_type}")])
    else:
        text += f"{get_text('no_transactions', lang)}\n"
        buttons = [
            [InlineKeyboardButton(text=get_text('export_report', lang), callback_data=f"export_report_{range_type}")],
            [InlineKeyboardButton(text=get_text('back', lang), callback_data="reporting")]
        ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# Pagination Handlers
@dp.callback_query(F.data.startswith("report_page_"))
async def handle_report_pagination(callback: types.CallbackQuery):
    """Handle pagination for reports."""
    lang = get_user_lang(callback)

    try:
        # Parse callback data: report_page_{page}_{range_type}[_{extra_data}]
        parts = callback.data.split('_')
        page = int(parts[2])
        range_type = parts[3]

        user_id = callback.from_user.id
        from datetime import date, timedelta

        today = date.today()

        # Determine date range based on type
        if range_type == "custom":
            # Custom range: report_page_{page}_custom_{start_date}_{end_date}_{start_display}_{end_display}
            if len(parts) >= 8:
                start_date_str = parts[4]
                end_date_str = parts[5]
                start_date_display = parts[6].replace('-', '/').replace('_', ' ')
                end_date_display = parts[7].replace('-', '/').replace('_', ' ')

                from datetime import datetime
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                range_text = get_text('custom_range_title', lang, start_date=start_date_display, end_date=end_date_display)
            else:
                await callback.answer(get_text('error', lang), show_alert=True)
                return
        else:
            # Standard ranges
            if range_type == "overall":
                start_date = date(2000, 1, 1)
                end_date = today
                range_text = "گزارش کلی" if lang == 'fa' else "Overall Report"
            elif range_type == "day":
                start_date = today
                end_date = today
                range_text = "امروز" if lang == 'fa' else "Today"
            elif range_type == "week":
                start_date = today - timedelta(days=6)
                end_date = today
                range_text = "هفته جاری" if lang == 'fa' else "This Week"
            elif range_type == "month":
                start_date = today.replace(day=1)
                end_date = today
                range_text = "ماه جاری" if lang == 'fa' else "This Month"
            elif range_type == "year":
                start_date = today.replace(month=1, day=1)
                end_date = today
                range_text = "سال جاری" if lang == 'fa' else "This Year"
            else:
                await callback.answer(get_text('error', lang), show_alert=True)
                return

            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")

        # Get all required data
        balance_report = db.get_balance_report(user_id, start_date_str, end_date_str)
        card_balances = db.get_card_source_balances_in_range(user_id, start_date_str, end_date_str)
        transactions = db.get_transactions_in_range(user_id, start_date_str, end_date_str)
        settings = db.get_user_settings(user_id)
        currency = get_text('toman', lang) if settings['currency'] == 'toman' else get_text('dollar', lang)

        # Build the report header (same for all pages)
        text = f"{get_text('reporting_title', lang)} - {range_text}\n\n"

        # Financial summary
        income = balance_report['income'] or 0
        expense = balance_report['expense'] or 0
        balance = balance_report['balance'] or 0
        text += f"{get_text('amount_earned', lang)}: {format_amount(income)} {currency}\n"
        text += f"{get_text('amount_spent', lang)}: {format_amount(expense)} {currency}\n"
        text += f"{get_text('current_balance', lang)}: {format_amount(balance)} {currency}\n\n"

        # Card/Source balances
        if card_balances:
            text += f"{get_text('card_source_balances', lang)}:\n"
            for card in card_balances:
                card_display = card['name'] or ("نامشخص" if lang == 'fa' else "Unknown")
                if card['card_number'] and len(card['card_number']) >= 4:
                    card_display += f" (****{card['card_number'][-4:]})"

                end_balance = card['end_balance'] or 0
                net_change = card['net_change'] or 0

                text += f"• {card_display}: {format_amount(end_balance)} {currency}"
                if net_change != 0:
                    change_text = f"(تغییر: {'+' if net_change > 0 else ''}{format_amount(net_change)})" if lang == 'fa' else f"(Change: {'+' if net_change > 0 else ''}{format_amount(net_change)})"
                    text += f" {change_text}"
                text += "\n"
            text += "\n"

        # Transactions with pagination
        if transactions:
            text += f"{get_text('transactions_in_range', lang)}\n"

            per_page = 5
            transaction_text, total_pages, start_idx, end_idx, total_transactions = format_transactions_page(
                transactions, page, per_page, lang, currency, settings
            )
            text += transaction_text

            if range_type == "custom":
                start_date_display = start_date_display.replace('/', '-').replace(' ', '_')
                end_date_display = end_date_display.replace('/', '-').replace(' ', '_')
                extra_data = f"_{start_date_str}_{end_date_str}_{start_date_display}_{end_date_display}"
                buttons = create_pagination_buttons(page, total_pages, range_type, lang, extra_data)
            else:
                buttons = create_pagination_buttons(page, total_pages, range_type, lang)
        else:
            text += f"{get_text('no_transactions', lang)}\n"
            buttons = [[InlineKeyboardButton(text=get_text('back', lang), callback_data="reporting")]]

        await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    except Exception as e:
        logging.error(f"Error in report pagination: {e}")
        await callback.answer(get_text('error', lang), show_alert=True)

    await callback.answer()

# Export Handlers
@dp.callback_query(F.data.startswith("export_report_"))
async def handle_export_report(callback: types.CallbackQuery):
    """Handle export report button clicks and show format selection."""
    lang = get_user_lang(callback)

    # Parse the callback data to get range information
    parts = callback.data.split('_')
    range_type = parts[2]  # export_report_{range_type}

    # Store range information for the actual export
    export_data = f"export_{range_type}"

    # Add additional data for custom ranges
    if range_type == "custom" and len(parts) >= 7:
        start_date = parts[3]
        end_date = parts[4]
        start_display = parts[5]
        end_display = parts[6]
        export_data = f"export_custom_{start_date}_{end_date}_{start_display}_{end_display}"

    text = get_text('select_export_format', lang)

    buttons = [
        [InlineKeyboardButton(text=get_text('export_csv', lang), callback_data=f"{export_data}_csv")],
        [InlineKeyboardButton(text=get_text('export_excel', lang), callback_data=f"{export_data}_excel")],
        [InlineKeyboardButton(text=get_text('export_pdf', lang), callback_data=f"{export_data}_pdf")],
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="reporting")]
    ]

    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("export_") & (F.data.endswith("_csv") | F.data.endswith("_excel") | F.data.endswith("_pdf")))
async def handle_export_format(callback: types.CallbackQuery):
    """Handle actual export format selection and generate files."""
    lang = get_user_lang(callback)
    user_id = callback.from_user.id

    # Parse export data
    parts = callback.data.split('_')
    export_format = parts[-1]  # Last part is the format (csv, excel, pdf)

    # Extract range information
    if parts[1] == "custom":
        # Custom range: export_custom_{start_date}_{end_date}_{start_display}_{end_display}_{format}
        start_date_str = parts[2]
        end_date_str = parts[3]
        start_date_display = parts[4]
        end_date_display = parts[5]
        range_type = "custom"
    else:
        # Standard range: export_{range_type}_{format}
        range_type = parts[1]
        start_date_str = None
        end_date_str = None
        start_date_display = None
        end_date_display = None

    try:
        # Show generating message
        await callback.answer(get_text('export_generating', lang))

        # Generate the export file
        file_path = await generate_export_file(
            user_id, range_type, export_format, lang,
            start_date_str, end_date_str, start_date_display, end_date_display
        )

        if file_path:
            # Send the file
            with open(file_path, 'rb') as file:
                # Set correct filename based on format
                if export_format == 'excel':
                    filename = "report.xlsx"
                elif export_format == 'pdf':
                    filename = "report.pdf"
                elif export_format == 'csv':
                    filename = "report.csv"
                else:
                    filename = f"report.{export_format}"

                await callback.message.answer_document(
                    document=types.input_file.BufferedInputFile(file.read(), filename=filename),
                    caption=get_text('export_ready', lang)
                )

            # Clean up the file
            import os
            os.remove(file_path)
        else:
            await callback.message.answer(get_text('export_error', lang))

    except Exception as e:
        logging.error(f"Error generating export: {e}")
        await callback.message.answer(get_text('export_error', lang))

# Planning FSM Handlers
@dp.callback_query(F.data == "add_plan")
async def start_add_plan(callback: types.CallbackQuery, state: FSMContext):
    lang = get_user_lang(callback)

    # Delete the original menu message
    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    except Exception:
        pass  # Ignore if message was already deleted

    sent_message = await callback.message.answer(get_text('enter_plan_title', lang))
    await state.update_data(prompt_message_id=sent_message.message_id)
    await state.set_state(PlanStates.waiting_for_title)
    await callback.answer()

@dp.message(PlanStates.waiting_for_title)
async def process_plan_title(message: types.Message, state: FSMContext):
    lang = get_user_lang(message)
    await state.update_data(title=message.text)

    # Delete the prompt message
    data = await state.get_data()
    prompt_message_id = data.get('prompt_message_id')
    if prompt_message_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception:
            pass  # Ignore if message was already deleted

    from datetime import date
    today = date.today().strftime("%Y-%m-%d")

    buttons = [
        [InlineKeyboardButton(text=get_text('today', lang), callback_data=f"pdate_{today}")],
        [InlineKeyboardButton(text=get_text('tomorrow', lang), callback_data="pdate_tomorrow")]
    ]
    await message.answer(get_text('select_date', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(PlanStates.waiting_for_date)

@dp.callback_query(PlanStates.waiting_for_date)
async def process_plan_date(callback: types.CallbackQuery, state: FSMContext):
    lang = get_user_lang(callback)
    from datetime import date, timedelta
    if callback.data == "pdate_tomorrow":
        p_date = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        p_date = callback.data.replace("pdate_", "")
    
    await state.update_data(date=p_date)
    skip_text = "Skip" if lang == 'en' else "رد کردن"
    sent_message = await callback.message.answer(get_text('enter_time', lang),
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=skip_text, callback_data="skip_time")]]))
    await state.update_data(prompt_message_id=sent_message.message_id)
    await state.set_state(PlanStates.waiting_for_time)
    await callback.answer()

@dp.callback_query(PlanStates.waiting_for_time)
@dp.message(PlanStates.waiting_for_time)
async def process_plan_time(event: types.Message | types.CallbackQuery, state: FSMContext):
    lang = get_user_lang(event)
    if isinstance(event, types.CallbackQuery):
        await state.update_data(time=None)
    else:
        await state.update_data(time=event.text)
    
    data = await state.get_data()
    db.add_plan(event.from_user.id, data['title'], data['date'], data.get('time'))

    # Delete the prompt message
    prompt_message_id = data.get('prompt_message_id')
    if prompt_message_id:
        try:
            await bot.delete_message(chat_id=event.from_user.id, message_id=prompt_message_id)
        except Exception:
            pass  # Ignore if message was already deleted

    text = get_text('plan_saved', lang)
    await send_menu_message(event.from_user.id, text, reply_markup=planning_menu_kb(lang))

    await state.clear()

# View Plans - Helper function
async def show_plans_view(callback: types.CallbackQuery, view_type: str = None):
    """Helper function to show plans view. view_type can be 'today' or 'week'."""
    lang = get_user_lang(callback)
    from datetime import date, timedelta
    today = date.today()
    
    # Determine view type if not provided
    if view_type is None:
        if callback.data == "plans_today":
            view_type = "today"
        elif callback.data == "plans_week":
            view_type = "week"
        else:
            # If called from done/del, try to determine from message context
            # Default to showing today's plans
            view_type = "today"
    
    if view_type == "today":
        plans = db.get_plans(callback.from_user.id, date=today.strftime("%Y-%m-%d"))
        title_text = get_text('plans_today_title', lang)
    else:
        start_week = today
        end_week = today + timedelta(days=7)
        plans = db.get_plans(callback.from_user.id, start_date=start_week.strftime("%Y-%m-%d"), end_date=end_week.strftime("%Y-%m-%d"))
        title_text = get_text('plans_week_title', lang)
    
    if not plans:
        await safe_edit_text(callback, f"{title_text}\n{get_text('no_plans', lang)}", reply_markup=planning_menu_kb(lang))
        return

    text = f"{title_text}:\n\n"
    buttons = []
    for plan in plans:
        # plan format: (id, user_id, title, date, time, is_done, ...)
        status = "✅" if plan[5] == 1 else "⬜️"
        time_part = f" ({plan[4]})" if plan[4] else ""
        text += f"{status} {plan[2]}{time_part} - {plan[3]}\n"
        buttons.append([
            InlineKeyboardButton(text=f"🗑 {plan[2]}", callback_data=f"del_plan_{plan[0]}_{view_type}"),
            InlineKeyboardButton(text=f"✅ {plan[2]}", callback_data=f"done_plan_{plan[0]}_{view_type}")
        ])
    
    buttons.append([InlineKeyboardButton(text=get_text('back', lang), callback_data="plan_main")])
    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.in_(["plans_today", "plans_week"]))
async def view_plans(callback: types.CallbackQuery):
    view_type = "today" if callback.data == "plans_today" else "week"
    await show_plans_view(callback, view_type)

@dp.callback_query(F.data.startswith("done_plan_"))
async def done_plan(callback: types.CallbackQuery):
    try:
        # Extract plan_id and view_type from callback data
        parts = callback.data.replace("done_plan_", "").split("_")
        plan_id = int(parts[0])
        view_type = parts[1] if len(parts) > 1 else "today"
        
        db.mark_plan_done(plan_id)
        await callback.answer("✅ ثبت شد.")
        # Refresh view with the same view type
        await show_plans_view(callback, view_type)
    except (ValueError, IndexError) as e:
        logging.error(f"Error in done_plan: {e}")
        await callback.answer("❌ خطا در پردازش درخواست", show_alert=True)

@dp.callback_query(F.data.startswith("del_plan_"))
async def del_plan(callback: types.CallbackQuery):
    try:
        # Extract plan_id and view_type from callback data
        parts = callback.data.replace("del_plan_", "").split("_")
        plan_id = int(parts[0])
        view_type = parts[1] if len(parts) > 1 else "today"
        
        db.delete_plan(plan_id)
        await callback.answer("🗑 حذف شد.")
        # Refresh view with the same view type
        await show_plans_view(callback, view_type)
    except (ValueError, IndexError) as e:
        logging.error(f"Error in del_plan: {e}")
        await callback.answer("❌ خطا در پردازش درخواست", show_alert=True)

# Global Text Handler (AI) - Moved here to ensure registration before polling
@dp.message(F.text & ~F.text.startswith("/"), StateFilter(None))
async def handle_text_ai(message: types.Message, state: FSMContext):
    lang = get_user_lang(message)
    from datetime import date
    current_date = date.today().strftime("%Y-%m-%d")

    loading_msg = await message.answer(get_text('analyzing', lang))
    try:
        result = await ai_parser.parse_message(message.text, current_date)
        await loading_msg.delete()

        section = result.get("section")
        action = result.get("action")

        # Handle different sections and actions
        if section == "finance":
            if action == "main":
                # Show finance main menu
                balance = db.get_current_month_balance(message.from_user.id)
                if lang == 'en':
                    text = (
                        "💰 Financial Management\n\n"
                        f"📊 Current Month Status:\n"
                        f"🔼 Income: {balance['income']:,} Toman\n"
                        f"🔻 Expense: {balance['expense']:,} Toman\n"
                        f"⚖️ Balance: {balance['balance']:,} Toman\n\n"
                        "Please select one of the options below:"
                    )
                else:  # Persian
                    text = (
                        "💰 بخش مدیریت مالی\n\n"
                        f"📊 وضعیت ماه جاری:\n"
                        f"🔼 درآمد: {balance['income']:,} تومان\n"
                        f"🔻 هزینه: {balance['expense']:,} تومان\n"
                        f"⚖️ مانده: {balance['balance']:,} تومان\n\n"
                        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
                    )
                await send_menu_message(message.from_user.id, text, reply_markup=finance_menu_kb(lang))

            elif action == "add_transaction":
                # AI-assisted transaction: create a draft and ask follow-up questions only for missing data
                parsed_amount = result.get("amount")
                parsed_type = result.get("type")
                parsed_category = result.get("category")
                parsed_date = result.get("date") or current_date
                parsed_note = result.get("note", "")
                parsed_currency = result.get("currency")
                parsed_time = result.get("time")
                parsed_balance = result.get("balance")
                parsed_party = result.get("party")
                card_hint = result.get("card_hint")  # last 4 digits if available

                settings = db.get_user_settings(message.from_user.id)
                currency = parsed_currency or settings['currency']

                if not parsed_amount or parsed_amount <= 0:
                    # Fall back to standard flow to ask amount first
                    await start_add_transaction(types.CallbackQuery(id="fake", from_user=message.from_user, message=message, data="add_transaction", chat_instance="fake"), state)
                    return

                # Try to resolve card by hint if present
                card_source_id = None
                if card_hint:
                    try:
                        cards_sources = db.get_cards_sources(message.from_user.id)
                        matches = [c for c in cards_sources if c[2] and c[2][-4:] == card_hint]
                        if len(matches) == 1:
                            card_source_id = matches[0][0]
                    except Exception:
                        pass

                # Seed FSM data
                await state.update_data(
                    amount=float(parsed_amount),
                    currency=currency,
                    type=parsed_type if parsed_type in ["income", "expense", "transfer"] else None,
                    category=parsed_category,
                    date=parsed_date,
                    description=parsed_note or "",
                    card_source_id=card_source_id,
                    time=parsed_time,
                    balance=parsed_balance,
                    party=parsed_party,
                    message_ids=[]
                )

                # Decide next missing field in preferred order: type -> category -> card -> description -> confirm
                data = await state.get_data()
                if data.get('type') is None:
                    # Ask for type
                    type_buttons = [
                        [InlineKeyboardButton(text=get_text('expense_type', lang), callback_data="type_expense")],
                        [InlineKeyboardButton(text=get_text('income_type', lang), callback_data="type_income")]
                    ]
                    await message.answer(get_text('select_type', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=type_buttons))
                    await state.set_state(TransactionStates.waiting_for_type)
                    return

                if not data.get('category'):
                    # Present categories just like in process_type
                    t_type = data['type']
                    categories = db.get_categories(message.from_user.id, t_type)
                    if not categories:
                        if t_type == "expense":
                            categories = [
                                get_text('cat_food', lang),
                                get_text('cat_transport', lang),
                                get_text('cat_rent', lang),
                                get_text('cat_entertainment', lang),
                                get_text('cat_other', lang)
                            ]
                        else:
                            categories = [
                                get_text('cat_salary', lang),
                                get_text('cat_bonus', lang),
                                get_text('cat_investment', lang),
                                get_text('cat_other', lang)
                            ]
                        for cat in categories:
                            db.add_category(message.from_user.id, cat, t_type)
                    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}")] for cat in categories]
                    buttons.append([InlineKeyboardButton(text=get_text('type_custom_category', lang), callback_data="type_custom_category")])
                    buttons.append([InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")])
                    await message.answer(get_text('select_category', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                    await state.set_state(TransactionStates.waiting_for_category)
                    return

                if data.get('card_source_id') is None:
                    # Ask for card selection
                    cards_sources = db.get_cards_sources(message.from_user.id)
                    if not cards_sources:
                        text = f"{get_text('no_card_source', lang)}\n\n{get_text('add_card_source_guide', lang)}"
                        buttons = [
                            [InlineKeyboardButton(text="💳 " + ("مدیریت کارت‌ها/منابع" if lang == 'fa' else "Manage Cards/Sources"), callback_data="manage_cards_sources")],
                            [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
                        ]
                        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                        return
                    # Build buttons with balances
                    currency_display = get_text('toman', lang) if currency == 'toman' else get_text('dollar', lang)
                    buttons = []
                    for card_source in cards_sources:
                        card_id, name, card_number, balance = card_source
                        display_name = name
                        if card_number:
                            masked_card = f"****{card_number[-4:]}" if len(card_number) >= 4 else card_number
                            display_name = f"{name} ({masked_card})"
                        balance_text = get_text('card_source_balance', lang, balance=format_amount(balance), currency=currency_display)
                        button_text = f"{display_name}\n{balance_text}"
                        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"card_{card_id}")])
                    buttons.append([InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")])
                    await message.answer(get_text('select_card_source', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                    await state.set_state(TransactionStates.waiting_for_card_source)
                    return

                # If description missing, ask (optional)
                if not data.get('description'):
                    # Ask optional description compactly with Skip
                    buttons = [
                        [InlineKeyboardButton(text=("رد کردن" if lang == 'fa' else "Skip"), callback_data="skip_description")],
                        [InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")]
                    ]
                    await message.answer(get_text('enter_description', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                    await state.set_state(TransactionStates.waiting_for_description)
                    return

                # All required fields present: save immediately (no extra confirmation)
                settings = db.get_user_settings(message.from_user.id)

                # Normalize date for storage: detect Jalali vs Gregorian by separator and year prefix
                date_input = data['date']
                if isinstance(date_input, str) and '/' in date_input and (date_input.strip().startswith('13') or date_input.strip().startswith('14')):
                    # Looks like Jalali
                    stored_date = parse_date_input(date_input, 'jalali')
                else:
                    stored_date = parse_date_input(date_input, 'gregorian')

                note = data.get('description') or ""
                # Append time/party/balance hints from AI parse if present in state
                ai_time = (await state.get_data()).get('time')
                ai_party = (await state.get_data()).get('party')
                ai_balance = (await state.get_data()).get('balance')
                extras = []
                if ai_time:
                    extras.append(f"time {ai_time}")
                if ai_party:
                    extras.append(f"party {ai_party}")
                if ai_balance is not None:
                    extras.append(f"balance {int(ai_balance):,}")
                if extras:
                    note = (note + ("\n" if note else "") + " | ".join(extras)).strip()

                db.add_transaction(
                    user_id=message.from_user.id,
                    amount=data['amount'],
                    currency=data['currency'],
                    type=data['type'],
                    category=data['category'],
                    card_source_id=data['card_source_id'],
                    date=stored_date,
                    note=note
                )

                # Acknowledge saved and show finance menu
                if lang == 'en':
                    ack = "✅ Transaction saved."
                else:
                    ack = "✅ تراکنش ذخیره شد."
                await message.answer(ack, reply_markup=finance_menu_kb(lang))
                await state.clear()

            elif action == "monthly_report":
                # Redirect to new reporting system with month range
                await reporting(types.CallbackQuery(
                    id="fake",
                    from_user=message.from_user,
                    message=message,
                    data="report_range_month",
                    chat_instance="fake"
                ))

            elif action == "categories":
                # Show categories
                expense_cats = db.get_categories(message.from_user.id, "expense")
                income_cats = db.get_categories(message.from_user.id, "income")

                text = f"{get_text('your_categories', lang)}\n\n"

                if expense_cats:
                    text += f"{get_text('expenses', lang)}\n"
                    for i, cat in enumerate(expense_cats, 1):
                        text += f"{i}. {cat}\n"
                    text += "\n"
                else:
                    text += f"{get_text('expenses', lang)} {get_text('no_category', lang)}\n\n"

                if income_cats:
                    text += f"{get_text('incomes', lang)}\n"
                    for i, cat in enumerate(income_cats, 1):
                        text += f"{i}. {cat}\n"
                else:
                    text += f"{get_text('incomes', lang)} {get_text('no_category', lang)}"

                buttons = [
                    [InlineKeyboardButton(text=get_text('add_expense_cat', lang), callback_data="add_category_expense")],
                    [InlineKeyboardButton(text=get_text('add_income_cat', lang), callback_data="add_category_income")],
                    [InlineKeyboardButton(text=get_text('back', lang), callback_data="finance_main")]
                ]
                await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        elif section == "planning":
            if action == "main":
                # Show planning main menu
                text = f"{get_text('planning_main', lang)}\n{get_text('planning_desc', lang)}"
                await send_menu_message(message.from_user.id, text, reply_markup=planning_menu_kb(lang))

            elif action == "add_plan":
                # Add plan directly
                title = result.get("title", "بدون عنوان" if lang == 'fa' else "No title")
                p_date = result.get("date", current_date)
                time = result.get("time")

                db.add_plan(message.from_user.id, title, p_date, time)

                time_display = time or ("نامشخص" if lang == 'fa' else "Not specified")
                await message.answer(
                    f"{get_text('ai_plan_saved', lang)}\n"
                    f"📝 {get_text('enter_plan_title', lang).replace('📝 ', '').replace(':', '')}: {title}\n"
                    f"{get_text('date_label', lang)}: {p_date}\n"
                    f"⏰ {get_text('enter_time', lang).replace('⏰ ', '').split('(')[0].strip()}: {time_display}"
                )
                # Send planning menu after successful plan
                menu_text = f"{get_text('planning_main', lang)}\n{get_text('planning_desc', lang)}"
                await send_menu_message(message.from_user.id, menu_text, reply_markup=planning_menu_kb(lang))

            elif action == "plans_today":
                # Show today's plans
                from datetime import date, timedelta
                today = date.today()
                plans = db.get_plans(message.from_user.id, date=today.strftime("%Y-%m-%d"))

                if not plans:
                    await send_menu_message(message.from_user.id, f"{get_text('plans_today_title', lang)}\n{get_text('no_plans', lang)}", reply_markup=planning_menu_kb(lang))
                    return

                text = f"{get_text('plans_today_title', lang)}:\n\n"
                buttons = []
                for plan in plans:
                    status = "✅" if plan[5] == 1 else "⬜️"
                    time_part = f" ({plan[4]})" if plan[4] else ""
                    text += f"{status} {plan[2]}{time_part} - {plan[3]}\n"
                    buttons.append([
                        InlineKeyboardButton(text=f"🗑 {plan[2]}", callback_data=f"del_plan_{plan[0]}_today"),
                        InlineKeyboardButton(text=f"✅ {plan[2]}", callback_data=f"done_plan_{plan[0]}_today")
                    ])

                buttons.append([InlineKeyboardButton(text=get_text('back', lang), callback_data="plan_main")])
                await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

            elif action == "plans_week":
                # Show week's plans
                from datetime import date, timedelta
                today = date.today()
                start_week = today
                end_week = today + timedelta(days=7)
                plans = db.get_plans(message.from_user.id, start_date=start_week.strftime("%Y-%m-%d"), end_date=end_week.strftime("%Y-%m-%d"))

                if not plans:
                    await send_menu_message(message.from_user.id, f"{get_text('plans_week_title', lang)}\n{get_text('no_plans', lang)}", reply_markup=planning_menu_kb(lang))
                    return

                text = f"{get_text('plans_week_title', lang)}:\n\n"
                buttons = []
                for plan in plans:
                    status = "✅" if plan[5] == 1 else "⬜️"
                    time_part = f" ({plan[4]})" if plan[4] else ""
                    text += f"{status} {plan[2]}{time_part} - {plan[3]}\n"
                    buttons.append([
                        InlineKeyboardButton(text=f"🗑 {plan[2]}", callback_data=f"del_plan_{plan[0]}_week"),
                        InlineKeyboardButton(text=f"✅ {plan[2]}", callback_data=f"done_plan_{plan[0]}_week")
                    ])

                buttons.append([InlineKeyboardButton(text=get_text('back', lang), callback_data="plan_main")])
                await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        elif section == "settings":
            if action == "change_language":
                # Show language selection menu
                current_lang = db.get_user_language(message.from_user.id)

                if current_lang == 'en':
                    text = "🌐 Change Language\n\nCurrent language: English\n\nPlease select your preferred language:"
                    buttons = [
                        [InlineKeyboardButton(text="🇮🇷 فارسی (Persian)", callback_data="set_lang_fa")],
                        [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
                        [InlineKeyboardButton(text=get_text('back', lang), callback_data="settings")]
                    ]
                else:  # Persian
                    text = "🌐 تغییر زبان\n\nزبان فعلی: فارسی\n\nلطفاً زبان مورد نظر خود را انتخاب کنید:"
                    buttons = [
                        [InlineKeyboardButton(text="🇮🇷 فارسی", callback_data="set_lang_fa")],
                        [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
                        [InlineKeyboardButton(text=get_text('back', lang), callback_data="settings")]
                    ]

                await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

            elif action == "clear_data":
                # Show clear data options
                data_type = result.get("data_type", "all")
                lang = get_user_lang(message)
                text = get_text('select_clear_option', lang)
                buttons = [
                    [InlineKeyboardButton(text=get_text('clear_everything', lang), callback_data="execute_clear_everything")],
                    [InlineKeyboardButton(text=get_text('clear_financial', lang), callback_data="execute_clear_financial")],
                    [InlineKeyboardButton(text=get_text('clear_planning', lang), callback_data="execute_clear_planning")],
                    [InlineKeyboardButton(text=get_text('clear_cards', lang), callback_data="execute_clear_cards")],
                    [InlineKeyboardButton(text=get_text('cancel', lang), callback_data="settings")]
                ]
                await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        elif section == "help":
            if action == "show":
                # Show help
                help_text = f"{get_text('help_title', lang)}\n\n{get_text('help_text', lang)}"
                buttons = [
                    [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
                ]
                kb = InlineKeyboardMarkup(inline_keyboard=buttons)
                await send_menu_message(message.from_user.id, help_text, reply_markup=kb)

        elif section == "admin":
            if not is_admin(message.from_user.id):
                await message.answer(get_text('access_denied', lang), show_alert=True)
                return

            if action == "users":
                # Show user list (first page)
                users = db.get_all_users()

                if not users:
                    text = "👥 لیست کاربران\n\nهیچ کاربری یافت نشد." if lang == 'fa' else "👥 User List\n\nNo users found."
                    await send_menu_message(message.from_user.id, text, reply_markup=admin_menu_kb(lang))
                    return

                page = 0
                users_per_page = 10
                start_idx = page * users_per_page
                end_idx = start_idx + users_per_page
                current_users = users[start_idx:end_idx]

                text = "👥 لیست کاربران:\n\n" if lang == 'fa' else "👥 User List:\n\n"

                for i, user in enumerate(current_users, start_idx + 1):
                    user_id, username, full_name, language, created_at = user
                    username_display = f"@{username}" if username else "بدون نام کاربری" if lang == 'fa' else "No username"
                    lang_flag = "🇮🇷" if language == 'fa' else "🇬🇧"
                    text += f"{i}. {full_name} ({username_display}) {lang_flag}\n"

                buttons = []
                if len(users) > users_per_page:
                    nav_buttons = []
                    if page > 0:
                        nav_buttons.append(InlineKeyboardButton(text="⬅️ قبلی" if lang == 'fa' else "⬅️ Previous",
                                                       callback_data=f"admin_users_page_{page-1}"))
                    if end_idx < len(users):
                        nav_buttons.append(InlineKeyboardButton(text="بعدی ➡️" if lang == 'fa' else "Next ➡️",
                                                       callback_data=f"admin_users_page_{page+1}"))
                    if nav_buttons:
                        buttons.append(nav_buttons)

                buttons.append([InlineKeyboardButton(text=get_text('back', lang), callback_data="admin_panel")])

                await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

            elif action == "stats":
                # Show statistics
                stats = db.get_user_stats()

                if lang == 'en':
                    text = "📊 Bot Statistics\n\n"
                    text += f"👥 Total Users: {stats['total_users']:,}\n"
                    text += f"🔥 Active Users (30 days): {stats['active_users']:,}\n\n"

                    text += "🌐 Language Distribution:\n"
                    for lang_code, count in stats['language_stats'].items():
                        flag = "🇮🇷 Persian" if lang_code == 'fa' else "🇬🇧 English"
                        text += f"  {flag}: {count:,}\n"

                    text += "\n📈 Activity Stats:\n"
                    text += f"💰 Total Transactions: {stats['total_transactions']:,}\n"
                    text += f"📅 Total Plans: {stats['total_plans']:,}\n"
                    text += f"📂 Total Categories: {stats['total_categories']:,}\n"
                else:
                    text = "📊 آمار ربات\n\n"
                    text += f"👥 تعداد کل کاربران: {stats['total_users']:,}\n"
                    text += f"🔥 کاربران فعال (۳۰ روز): {stats['active_users']:,}\n\n"

                    text += "🌐 توزیع زبان‌ها:\n"
                    for lang_code, count in stats['language_stats'].items():
                        flag = "🇮🇷 فارسی" if lang_code == 'fa' else "🇬🇧 انگلیسی"
                        text += f"  {flag}: {count:,}\n"

                    text += "\n📈 آمار فعالیت:\n"
                    text += f"💰 تعداد کل تراکنش‌ها: {stats['total_transactions']:,}\n"
                    text += f"📅 تعداد کل برنامه‌ها: {stats['total_plans']:,}\n"
                    text += f"📂 تعداد کل دسته‌بندی‌ها: {stats['total_categories']:,}\n"

                buttons = [[InlineKeyboardButton(text=get_text('back', lang), callback_data="admin_panel")]]
                await send_menu_message(message.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        elif action == "main_menu" or (section == "main" and action == "menu"):
            # Show main menu
            admin_status = is_admin(message.from_user.id)
            await send_menu_message(message.from_user.id, get_text('welcome', lang), reply_markup=main_menu_kb(lang, admin_status))

        else:
            # Fallback to buttons for unrecognized commands
            admin_status = is_admin(message.from_user.id)
            await send_menu_message(message.from_user.id, get_text('not_understood', lang), reply_markup=main_menu_kb(lang, admin_status))

    except Exception as e:
        if loading_msg:
            await loading_msg.delete()
        if "429" in str(e) or "quota" in str(e).lower():
            admin_status = is_admin(message.from_user.id)
            await send_menu_message(message.from_user.id, get_text('ai_quota_error', lang), reply_markup=main_menu_kb(lang, admin_status))
        else:
            admin_status = is_admin(message.from_user.id)
            await send_menu_message(message.from_user.id, get_text('ai_error', lang), reply_markup=main_menu_kb(lang, admin_status))

# Start polling
async def main():
    # Restart functionality removed
    # Start polling with retry logic for network errors and configurable proxy/IPv4/timeout
    max_retries = int(os.getenv("BOT_START_MAX_RETRIES", "5"))
    retry_delay = int(os.getenv("BOT_START_RETRY_DELAY", "3"))

    # Bot is initialized globally without custom proxy/session
    global bot

    # Preflight: try get_me with retries and backoff to surface early network issues
    preflight_attempts = int(os.getenv("BOT_PREFLIGHT_RETRIES", "3"))
    for attempt in range(preflight_attempts):
        try:
            _ = await bot.me()
            logging.info("Bot preflight getMe OK")
            break
        except Exception as e:
            if attempt < preflight_attempts - 1:
                wait_time = retry_delay * (2 ** attempt)
                logging.warning(f"Preflight getMe failed (attempt {attempt+1}/{preflight_attempts}): {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logging.error(f"Preflight getMe failed after {preflight_attempts} attempts: {e}")
                # Continue to polling loop; startup retry logic will handle further

    # Create an asyncio.Event that will be set when a shutdown signal is received.
    stop_event = asyncio.Event()

    # Signal handler to set the stop_event from the main thread.
    def _on_signal(sig_num, frame=None):
        logging.info(f"Received signal {sig_num}, shutting down...")
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(stop_event.set)
        except Exception:
            # Fallback if event loop is not accessible
            try:
                stop_event.set()
            except Exception:
                pass

    # Register signal handlers for graceful shutdown (works on Windows and Unix)
    try:
        signal.signal(signal.SIGINT, _on_signal)
    except Exception:
        logging.debug("Could not register SIGINT handler; fallback to default")
    try:
        signal.signal(signal.SIGTERM, _on_signal)
    except Exception:
        logging.debug("Could not register SIGTERM handler; fallback to default")

    for attempt in range(max_retries):
        try:
            logging.info(f"Starting bot polling (attempt {attempt + 1}/{max_retries})...")
            # Run polling as a task so we can cancel it on Ctrl+C / signals
            polling_task = asyncio.create_task(dp.start_polling(bot, handle_as_tasks=True))

            # Wait until either polling finishes or a stop signal is received
            done, pending = await asyncio.wait(
                [polling_task, asyncio.create_task(stop_event.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # If stop_event was set, cancel polling_task and cleanup
            if stop_event.is_set():
                logging.info("Shutdown requested, cancelling polling task...")
                polling_task.cancel()
                try:
                    await polling_task
                except asyncio.CancelledError:
                    logging.info("Polling task cancelled.")

                # Properly close bot and dispatcher
                logging.info("Closing bot session...")
                try:
                    if hasattr(bot, 'session') and bot.session:
                        await bot.session.close()
                except Exception as ce:
                    logging.debug(f"Error closing session during shutdown: {ce}")
                logging.info("Bot shutdown complete.")
                return  # Exit the function completely, don't retry

            break  # Exit retry loop whether polling finished or was cancelled
        except Exception as e:
            error_msg = str(e).lower()
            error_type = type(e).__name__

            # Check if it's a network/DNS/connection error
            is_network_error = any(keyword in error_msg for keyword in [
                'dns', 'network', 'connection', 'getaddrinfo', 'cannot connect',
                'clientconnectordnserror', 'telegramnetworkerror', 'timeout'
            ]) or 'network' in error_type.lower()

            # Check if shutdown was requested during the exception handling
            if stop_event.is_set():
                logging.info("Shutdown requested during error recovery, exiting...")
                try:
                    if hasattr(bot, 'session') and bot.session:
                        await bot.session.close()
                except Exception as ce:
                    logging.debug(f"Error closing session during shutdown: {ce}")
                logging.info("Bot shutdown complete.")
                return

            if is_network_error:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff: 3, 6, 12, 24 seconds
                    logging.warning(
                        f"Network error on startup (attempt {attempt + 1}/{max_retries}): {e}\n"
                        f"Retrying in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logging.error(
                        f"Failed to start polling after {max_retries} attempts due to network issues.\n"
                        f"Last error: {e}\n"
                        f"Please check your internet connection and try again."
                    )
                    raise
            else:
                # Not a network error, re-raise immediately
                logging.error(f"Failed to start polling (non-network error): {e}")
                raise

async def cleanup_bot():
    """Cleanup bot resources."""
    try:
        if hasattr(bot, 'session') and bot.session:
            await bot.session.close()
            logging.info("Bot session closed.")
    except Exception as e:
        logging.error(f"Error closing bot session: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
        # Ensure cleanup on keyboard interrupt
        asyncio.run(cleanup_bot())
    except Exception as e:
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['dns', 'network', 'connection', 'getaddrinfo', 'cannot connect']):
            logging.error(
                f"\n{'='*60}\n"
                f"FATAL ERROR: Cannot connect to Telegram API\n"
                f"Error: {e}\n"
                f"{'='*60}\n"
                f"Possible causes:\n"
                f"  1. No internet connection\n"
                f"  2. DNS resolution failure\n"
                f"  3. Firewall blocking Telegram API\n"
                f"  4. Telegram API temporarily unavailable\n"
                f"\nPlease check your network connection and try again.\n"
                f"{'='*60}"
            )
        else:
            logging.error(f"Fatal error: {e}", exc_info=True)

        # Ensure cleanup on fatal error
        try:
            asyncio.run(cleanup_bot())
        except Exception:
            pass  # Ignore cleanup errors during fatal shutdown

        # Give time for error logging before exit
        time.sleep(2)
        raise
