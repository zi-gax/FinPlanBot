import asyncio
import logging
import signal
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest

import sys
import os
from config import API_token, ADMIN_IDS
from database import Database
from ai_parser import ai_parser
from translations import get_text

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

# States
class TransactionStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_card_source = State()
    waiting_for_date = State()
    waiting_for_description = State()
    waiting_for_type = State()
    waiting_for_category = State()
    waiting_for_note = State()  # Keep for backward compatibility

class PlanStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()

class CategoryStates(StatesGroup):
    waiting_for_category_name = State()

class CardSourceStates(StatesGroup):
    waiting_for_source_name = State()
    waiting_for_card_number = State()
    waiting_for_edit_name = State()
    waiting_for_edit_card_number = State()

class SettingsStates(StatesGroup):
    waiting_for_currency = State()
    waiting_for_calendar = State()

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
            [InlineKeyboardButton(text="🔙 Back", callback_data="main_menu")]
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="➕ افزودن تراکنش", callback_data="add_transaction")],
            [InlineKeyboardButton(text="📊 گزارش‌گیری", callback_data="reporting")],
            [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="financial_settings")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def planning_menu_kb(lang='fa'):
    """Generate planning menu keyboard based on language."""
    if lang == 'en':
        buttons = [
            [InlineKeyboardButton(text="➕ Add Plan", callback_data="add_plan")],
            [InlineKeyboardButton(text="📆 Today's Plans", callback_data="plans_today")],
            [InlineKeyboardButton(text="📅 This Week's Plans", callback_data="plans_week")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="main_menu")]
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="➕ افزودن برنامه", callback_data="add_plan")],
            [InlineKeyboardButton(text="📆 برنامه‌های امروز", callback_data="plans_today")],
            [InlineKeyboardButton(text="📅 برنامه‌های این هفته", callback_data="plans_week")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_menu_kb(lang='fa'):
    """Generate admin panel menu keyboard based on language."""
    if lang == 'en':
        buttons = [
            [InlineKeyboardButton(text="👥 User List", callback_data="admin_users")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="main_menu")]
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="👥 لیست کاربران", callback_data="admin_users")],
            [InlineKeyboardButton(text="📊 آمار", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
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
    lang = db.get_user_language(callback.from_user.id)

    if lang == 'en':
        text = "⚙️ Settings\n\nSelect an option:"
        buttons = [
            [InlineKeyboardButton(text="💰 Financial Settings", callback_data="financial_settings")],
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="main_menu")]
        ]
    else:  # Persian
        text = "⚙️ تنظیمات\n\nگزینه مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text="💰 تنظیمات مالی", callback_data="financial_settings")],
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
        ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
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
            [InlineKeyboardButton(text="🔙 Back", callback_data="settings")]
        ]
    else:  # Persian
        text = f"⚙️ تنظیمات مالی\n\nتنظیمات فعلی:\n💵 واحد پول: {currency_text}\n📅 تقویم: {calendar_text}\n\nگزینه مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text="💵 تغییر واحد پول", callback_data="change_currency")],
            [InlineKeyboardButton(text="📅 تغییر تقویم", callback_data="change_calendar")],
            [InlineKeyboardButton(text="💳 مدیریت کارت‌ها/منابع", callback_data="manage_cards_sources")],
            [InlineKeyboardButton(text="📂 مدیریت دسته‌بندی‌ها", callback_data="categories")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")]
        ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# Card/Source Management Handlers
@dp.callback_query(F.data == "manage_cards_sources")
async def manage_cards_sources_menu(callback: types.CallbackQuery):
    """Show card/source management menu."""
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

            balance_text = get_text('card_source_balance', lang, balance=balance, currency=currency)
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
            [InlineKeyboardButton(text="🔙 Back", callback_data="financial_settings")]
        ])
    else:
        buttons.extend([
            [InlineKeyboardButton(text="➕ افزودن کارت/منبع", callback_data="add_card_source")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="financial_settings")]
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
        await manage_cards_sources_menu(event)
    else:
        # For message events, create a fake callback query
        fake_callback = types.CallbackQuery(
            id="fake",
            from_user=event.from_user,
            message=event,
            data="manage_cards_sources",
            chat_instance="fake"
        )
        await manage_cards_sources_menu(fake_callback)

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
        text = f"💳 Edit Card/Source\n\nName: {name}\nCard: {card_display}\nBalance: {balance:,} {currency}\n\nSelect action:"
        buttons = [
            [InlineKeyboardButton(text="✏️ Edit Name", callback_data=f"edit_name_{card_id}")],
            [InlineKeyboardButton(text="💳 Edit Card Number", callback_data=f"edit_card_number_{card_id}")],
            [InlineKeyboardButton(text="🗑 Delete", callback_data=f"delete_card_{card_id}")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="manage_cards_sources")]
        ]
    else:
        text = f"💳 ویرایش کارت/منبع\n\nنام: {name}\nکارت: {card_display}\nموجودی: {balance:,} {currency}\n\nاقدام مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text="✏️ ویرایش نام", callback_data=f"edit_name_{card_id}")],
            [InlineKeyboardButton(text="💳 ویرایش شماره کارت", callback_data=f"edit_card_number_{card_id}")],
            [InlineKeyboardButton(text="🗑 حذف", callback_data=f"delete_card_{card_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="manage_cards_sources")]
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

    buttons.append([InlineKeyboardButton(text="🔙 بازگشت" if lang == 'fa' else "🔙 Back", callback_data="admin_panel")])

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

    buttons.append([InlineKeyboardButton(text="🔙 بازگشت" if lang == 'fa' else "🔙 Back", callback_data="admin_panel")])

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

    buttons = [[InlineKeyboardButton(text="🔙 بازگشت" if lang == 'fa' else "🔙 Back", callback_data="admin_panel")]]

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
            [InlineKeyboardButton(text="🔙 Back", callback_data="settings")]
        ]
    else:  # Persian
        text = "🌐 تغییر زبان\n\nزبان فعلی: فارسی\n\nلطفاً زبان مورد نظر خود را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text="🇮🇷 فارسی", callback_data="set_lang_fa")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")]
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
        [InlineKeyboardButton(text="🔙 " + get_text('back', lang), callback_data="main_menu")]
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
    buttons = [
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="main_menu")]
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(event, types.CallbackQuery):
        await send_menu_message(event.from_user.id, help_text, reply_markup=kb)
        await event.answer()
    else:
        await send_menu_message(event.from_user.id, help_text, reply_markup=kb)


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

    # Show success message and redirect to settings
    success_text = get_text('data_cleared', lang)
    if lang == 'en':
        settings_text = "⚙️ Settings\n\nSelect an option:"
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="main_menu")]
        ]
    else:  # Persian
        settings_text = "⚙️ تنظیمات\n\nگزینه مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
        ]

    # Show success message briefly, then show settings
    await send_menu_message(callback.from_user.id, success_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "execute_clear_cards")
async def execute_clear_cards(callback: types.CallbackQuery):
    lang = get_user_lang(callback)
    db.clear_cards(callback.from_user.id)

    # Show success message and redirect to settings
    success_text = "✅ کارت‌ها با موفقیت پاکسازی شد." if lang == 'fa' else "✅ Cards cleared successfully."
    if lang == 'en':
        settings_text = "⚙️ Settings\n\nSelect an option:"
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="main_menu")]
        ]
    else:  # Persian
        settings_text = "⚙️ تنظیمات\n\nگزینه مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
        ]

    # Show success message briefly, then show settings
    await send_menu_message(callback.from_user.id, success_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "execute_clear_financial")
async def execute_clear_financial(callback: types.CallbackQuery):
    lang = get_user_lang(callback)
    db.clear_financial_data(callback.from_user.id)

    # Show success message and redirect to settings
    success_text = get_text('financial_data_cleared', lang)
    if lang == 'en':
        settings_text = "⚙️ Settings\n\nSelect an option:"
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="main_menu")]
        ]
    else:  # Persian
        settings_text = "⚙️ تنظیمات\n\nگزینه مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
        ]

    # Show success message briefly, then show settings
    await send_menu_message(callback.from_user.id, success_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "execute_clear_planning")
async def execute_clear_planning(callback: types.CallbackQuery):
    lang = get_user_lang(callback)
    db.clear_planning_data(callback.from_user.id)

    # Show success message and redirect to settings
    success_text = get_text('planning_data_cleared', lang)
    if lang == 'en':
        settings_text = "⚙️ Settings\n\nSelect an option:"
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="main_menu")]
        ]
    else:  # Persian
        settings_text = "⚙️ تنظیمات\n\nگزینه مورد نظر را انتخاب کنید:"
        buttons = [
            [InlineKeyboardButton(text=get_text('clear_data', lang), callback_data="confirm_clear_data")],
            [InlineKeyboardButton(text="🌐 تغییر زبان", callback_data="change_language")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
        ]

    # Show success message briefly, then show settings
    await send_menu_message(callback.from_user.id, success_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

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
        year, month, day = map(int, date_input.split('-'))
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
    sent_message = await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

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
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    text = f"{get_text('amount_label', lang)}: {amount:,} {currency_display}\n\n{get_text('select_card_source', lang)}"
    buttons = []
    for card_source in cards_sources:
        card_id, name, card_number, balance = card_source
        # Mask card number if it exists
        display_name = name
        if card_number:
            masked_card = f"****{card_number[-4:]}" if len(card_number) >= 4 else card_number
            display_name = f"{name} ({masked_card})"

        balance_text = get_text('card_source_balance', lang, balance=balance, currency=currency_display)
        button_text = f"{display_name}\n{balance_text}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"card_{card_id}")])

    buttons.append([InlineKeyboardButton(text=get_text('cancel_btn', lang), callback_data="cancel_transaction")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
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
        return

    await state.update_data(card_source_id=card_id)

    # Move to date input
    settings = db.get_user_settings(callback.from_user.id)
    calendar_format = settings['calendar_format']
    calendar_display = "شمسی" if calendar_format == 'jalali' and lang == 'fa' else ("Jalali" if calendar_format == 'jalali' else "Gregorian")

    data = await state.get_data()
    amount = data['amount']
    currency_display = get_text('toman', lang) if data['currency'] == 'toman' else get_text('dollar', lang)

    text = f"{get_text('amount_label', lang)}: {amount:,} {currency_display}\n"
    text += f"{get_text('card_source_label', lang)}: {card_source[1]}\n\n"  # card_source[1] is name
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
        # Basic date validation - accept YYYY-MM-DD format
        import re
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_input):
            calendar_name = "شمسی" if calendar_format == 'jalali' and lang == 'fa' else ("Jalali" if calendar_format == 'jalali' else "Gregorian")
            await event.answer(f"❌ فرمت تاریخ نامعتبر. لطفا از فرمت YYYY-MM-DD ({calendar_name}) استفاده کنید." if lang == 'fa' else f"❌ Invalid date format. Please use YYYY-MM-DD ({calendar_name}) format.")
            return
        # Convert input date to Gregorian for storage
        selected_date = parse_date_input(date_input, calendar_format)

    await state.update_data(date=selected_date)

    # Move to description input (optional)
    data = await state.get_data()
    currency_display = get_text('toman', lang) if data['currency'] == 'toman' else get_text('dollar', lang)
    card_source = db.get_card_source(data['card_source_id'])

    text = f"{get_text('transaction_details', lang)}\n\n"
    text += f"{get_text('amount_label', lang)}: {data['amount']:,} {currency_display}\n"
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
    text += f"{get_text('amount_label', lang)}: {data['amount']:,} {currency_display}\n"
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
        await event.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

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
    text += f"{get_text('amount_label', lang)}: {amount:,} {currency_display}\n"
    text += f"{get_text('card_source_label', lang)}: {card_source[1]}\n"
    text += f"{get_text('currency_label', lang)}: {currency_display}\n"
    text += f"{get_text('date_label', lang)}: {data['date']}\n"
    if data.get('description'):
        text += f"{get_text('description_label', lang)}: {data['description']}\n"
    text += f"{get_text('type_label', lang)}: {type_text}\n\n"
    text += f"{get_text('select_category', lang)}"

    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}")] for cat in categories]
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

    summary += f"{get_text('amount_label', lang)}: {data['amount']:,} {currency_display}\n"
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
    lang = get_user_lang(callback)
    await state.clear()

    # Show finance main menu
    text = get_text('select_transaction_type', lang) if get_text('select_transaction_type', lang) != 'select_transaction_type' else (
        "نوع تراکنش را انتخاب کنید:" if lang == 'fa' else "Select transaction type:"
    )

    buttons = [
        [InlineKeyboardButton(text=get_text('add_transaction', lang), callback_data="add_transaction")],
        [InlineKeyboardButton(text="🔙 " + get_text('back', lang), callback_data="finance_main")]
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
            f"💰 {card_source[1]} balance: {card_source[3]:,} {currency_display}"
        )
    else:
        text = (
            f"{get_text('transaction_saved', lang)}\n\n"
            f"{get_text('balance_updated', lang, balance=card_source[3], currency=currency_display)}\n\n"
            f"💰 موجودی {card_source[1]}: {card_source[3]:,} {currency_display}"
        )
    await send_menu_message(callback.from_user.id, text, reply_markup=finance_menu_kb(lang))
    await state.clear()
    await callback.answer(get_text('done', lang))

# Categories Management
@dp.callback_query(F.data == "categories")
async def show_categories(callback: types.CallbackQuery):
    """Show user's expense and income categories."""
    lang = get_user_lang(callback)
    expense_cats = db.get_categories(callback.from_user.id, "expense")
    income_cats = db.get_categories(callback.from_user.id, "income")
    
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
    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
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
    
    type_text = get_text('expense_type', lang) if cat_type == "expense" else get_text('income_type', lang)
    await message.answer(
        get_text('category_added', lang, name=category_name, type=type_text),
        reply_markup=finance_menu_kb(lang)
    )
    await state.clear()

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
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="finance_main")]
    ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

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
    text += f"{get_text('amount_earned', lang)}: {income:,} {currency}\n"
    text += f"{get_text('amount_spent', lang)}: {expense:,} {currency}\n"
    text += f"{get_text('current_balance', lang)}: {balance:,} {currency}\n\n"

    # Card/Source balances
    if card_balances:
        text += f"{get_text('card_source_balances', lang)}:\n"
        for card in card_balances:
            card_display = card['name'] or ("نامشخص" if lang == 'fa' else "Unknown")
            if card['card_number'] and len(card['card_number']) >= 4:
                card_display += f" (****{card['card_number'][-4:]})"

            end_balance = card['end_balance'] or 0
            net_change = card['net_change'] or 0

            text += f"• {card_display}: {end_balance:,} {currency}"
            if net_change != 0:
                change_text = f"(تغییر: {'+' if net_change > 0 else ''}{net_change:,})" if lang == 'fa' else f"(Change: {'+' if net_change > 0 else ''}{net_change:,})"
                text += f" {change_text}"
            text += "\n"
        text += "\n"

    # Transactions list
    if transactions:
        text += f"{get_text('transactions_in_range', lang)}\n"
        for transaction in transactions[:10]:  # Limit to 10 transactions to avoid message too long
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

            text += f"{type_emoji} {amount:,} {currency} - {category} - {card_display} - {display_date}\n"
            if note:
                text += f"   💬 {note}\n"

        if len(transactions) > 10:
            remaining = len(transactions) - 10
            text += f"\n... و {remaining} تراکنش دیگر" if lang == 'fa' else f"\n... and {remaining} more transactions"
    else:
        text += f"{get_text('no_transactions', lang)}\n"

    buttons = [
        [InlineKeyboardButton(text=get_text('back', lang), callback_data="reporting")]
    ]

    await send_menu_message(callback.from_user.id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# Planning FSM Handlers
@dp.callback_query(F.data == "add_plan")
async def start_add_plan(callback: types.CallbackQuery, state: FSMContext):
    lang = get_user_lang(callback)
    await callback.message.answer(get_text('enter_plan_title', lang))
    await state.set_state(PlanStates.waiting_for_title)
    await callback.answer()

@dp.message(PlanStates.waiting_for_title)
async def process_plan_title(message: types.Message, state: FSMContext):
    lang = get_user_lang(message)
    await state.update_data(title=message.text)
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
    await callback.message.answer(get_text('enter_time', lang), 
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=skip_text, callback_data="skip_time")]]))
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
    
    text = get_text('plan_saved', lang)
    if isinstance(event, types.CallbackQuery):
        await send_menu_message(event.from_user.id, text, reply_markup=planning_menu_kb(lang))
    else:
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
                # Add transaction directly
                amount = result.get("amount", 0)
                t_type = result.get("type", "expense")
                category = result.get("category", "سایر" if lang == 'fa' else "Other")
                t_date = result.get("date", current_date)
                note = result.get("note", "")

                db.add_transaction(message.from_user.id, amount, t_type, category, t_date, note)

                type_text = get_text('expense_type', lang) if t_type == "expense" else get_text('income_type', lang)
                await message.answer(
                    f"{get_text('ai_transaction_saved', lang)}\n"
                    f"{get_text('amount_label', lang)}: {amount:,}\n"
                    f"{get_text('type_label', lang)}: {type_text}\n"
                    f"{get_text('category_label', lang)}: {category}\n"
                    f"{get_text('date_label', lang)}: {t_date}"
                )
                # Send finance menu after successful transaction
                balance = db.get_current_month_balance(message.from_user.id)
                if lang == 'en':
                    menu_text = (
                        "💰 Financial Management\n\n"
                        f"📊 Current Month Status:\n"
                        f"🔼 Income: {balance['income']:,} Toman\n"
                        f"🔻 Expense: {balance['expense']:,} Toman\n"
                        f"⚖️ Balance: {balance['balance']:,} Toman\n\n"
                        "Please select one of the options below:"
                    )
                else:  # Persian
                    menu_text = (
                        "💰 بخش مدیریت مالی\n\n"
                        f"📊 وضعیت ماه جاری:\n"
                        f"🔼 درآمد: {balance['income']:,} تومان\n"
                        f"🔻 هزینه: {balance['expense']:,} تومان\n"
                        f"⚖️ مانده: {balance['balance']:,} تومان\n\n"
                        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
                    )
                await send_menu_message(message.from_user.id, menu_text, reply_markup=finance_menu_kb(lang))

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
                        [InlineKeyboardButton(text="🔙 Back", callback_data="settings")]
                    ]
                else:  # Persian
                    text = "🌐 تغییر زبان\n\nزبان فعلی: فارسی\n\nلطفاً زبان مورد نظر خود را انتخاب کنید:"
                    buttons = [
                        [InlineKeyboardButton(text="🇮🇷 فارسی", callback_data="set_lang_fa")],
                        [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")],
                        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")]
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

                buttons.append([InlineKeyboardButton(text="🔙 بازگشت" if lang == 'fa' else "🔙 Back", callback_data="admin_panel")])

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

                buttons = [[InlineKeyboardButton(text="🔙 بازگشت" if lang == 'fa' else "🔙 Back", callback_data="admin_panel")]]
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
    # Start polling with retry logic for network errors
    max_retries = 5
    retry_delay = 3
    
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
                await bot.session.close()
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
                await bot.session.close()
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
        import time
        time.sleep(2)
        raise
