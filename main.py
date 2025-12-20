import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter

import sys
import os
import subprocess
from config import API_token, ADMIN_IDS
from database import Database
from ai_parser import ai_parser

# Setup logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=API_token)
dp = Dispatcher(storage=MemoryStorage())
db = Database()

# States
class TransactionStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_type = State()
    waiting_for_category = State()
    waiting_for_date = State()
    waiting_for_note = State()

class PlanStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_time = State()

# Keyboards
def main_menu_kb():
    buttons = [
        [InlineKeyboardButton(text="💰 مدیریت مالی", callback_data="finance_main")],
        [InlineKeyboardButton(text="📅 برنامه‌ریزی", callback_data="plan_main")],
        [InlineKeyboardButton(text="ℹ️ راهنما", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def finance_menu_kb():
    buttons = [
        [InlineKeyboardButton(text="➕ افزودن تراکنش", callback_data="add_transaction")],
        [InlineKeyboardButton(text="📊 گزارش ماهانه", callback_data="monthly_report")],
        [InlineKeyboardButton(text="📂 دسته‌بندی‌ها", callback_data="categories")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def planning_menu_kb():
    buttons = [
        [InlineKeyboardButton(text="➕ افزودن برنامه", callback_data="add_plan")],
        [InlineKeyboardButton(text="📆 برنامه‌های امروز", callback_data="plans_today")],
        [InlineKeyboardButton(text="📅 برنامه‌های این هفته", callback_data="plans_week")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Handlers
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    db.add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(
        "سلام! به دستیار هوشمند مالی و برنامه‌ریزی خوش آمدید.\nلطفاً یکی از بخش‌های زیر را انتخاب کنید:",
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "بخش مورد نظر را انتخاب کنید:",
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data == "finance_main")
async def finance_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💰 بخش مدیریت مالی\nدر این بخش می‌توانید درآمدها و هزینه‌های خود را ثبت و مدیریت کنید.",
        reply_markup=finance_menu_kb()
    )

@dp.callback_query(F.data == "plan_main")
async def plan_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📅 بخش برنامه‌ریزی\nدر این بخش می‌توانید کارهای روزانه و برنامه‌های خود را ثبت کنید.",
        reply_markup=planning_menu_kb()
    )

@dp.callback_query(F.data == "help")
@dp.message(Command("help"))
async def help_cmd(event: types.CallbackQuery | types.Message):
    help_text = (
        "💡 راهنما:\n\n"
        "شما می‌توانید هم با دکمه‌ها و هم با ارسال متن فارسی کارهای خود را انجام دهید.\n\n"
        "مثال‌های ورودی هوشمند:\n"
        "- امروز ۲۰۰ تومن غذا دادم\n"
        "- حقوق دیروز ۴ میلیون\n"
        "- فردا ساعت ۸ ورزش\n\n"
        "دستیار هوشمند متن شما را تحلیل کرده و ثبت می‌کند."
    )
    user_id = event.from_user.id
    buttons = [
        [InlineKeyboardButton(text="🗑 پاکسازی تمامی داده‌ها", callback_data="confirm_clear_data")],
    ]
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton(text="🔄 Restart Bot", callback_data="confirm_restart")])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(help_text, reply_markup=kb)
    else:
        await event.answer(help_text, reply_markup=kb)


# Data Management Handlers
@dp.callback_query(F.data == "confirm_clear_data")
async def ask_confirm_clear(callback: types.CallbackQuery):
    text = (
        "⚠️ آیا از پاکسازی تمامی اطلاعات (مالی و برنامه‌ریزی) اطمینان دارید؟\n"
        "این عمل غیرقابل بازگشت است!"
    )
    buttons = [
        [InlineKeyboardButton(text="🔥 بله، کاملا پاک شود", callback_data="execute_clear_data")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="help")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "execute_clear_data")
async def execute_clear_data(callback: types.CallbackQuery):
    db.clear_user_data(callback.from_user.id)
    await callback.message.edit_text("✅ تمامی اطلاعات شما با موفقیت حذف شد.", reply_markup=main_menu_kb())
    await callback.answer()

# Restart Bot Handlers
@dp.callback_query(F.data == "confirm_restart")
async def ask_confirm_restart(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ شما دسترسی به این بخش را ندارید.", show_alert=True)
        return
        
    text = "🔄 آیا از بازنشانی (Restart) ربات اطمینان دارید؟"
    buttons = [
        [InlineKeyboardButton(text="✅ بله، ری‌استارت شود", callback_data="execute_restart")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="help")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "execute_restart")
async def execute_restart(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ عدم دسترسی", show_alert=True)
        return
        
    await callback.message.edit_text("🔄 در حال ری‌استارت ربات...")
    await callback.answer("ربات در حال ری‌استارت است.", show_alert=True)
    
    # Safe exit for process manager to restart
    logging.info(f"Restart triggered by user {callback.from_user.id}")
    
    # We use a small delay to ensure the confirmation message is sent to Telegram
    await asyncio.sleep(1)
    
    # Self-restart logic:
    # Get absolute path to the script
    script_path = os.path.abspath(sys.argv[0])
    
    # Use os.execl to replace the current process (on Windows this creates a new process and exits old)
    # We pass the same executable, then the script path, then the restart flag.
    logging.info("Replacing process for restart...")
    os.execl(sys.executable, sys.executable, script_path, "--restarted")

# Helper: Persian numbers to English
def fa_to_en(text):
    fa_nums = "۰۱۲۳۴۵۶۷۸۹"
    en_nums = "0123456789"
    table = str.maketrans(fa_nums, en_nums)
    return text.translate(table)

# Transaction FSM Handlers
@dp.callback_query(F.data == "add_transaction")
async def start_add_transaction(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("💸 مبلغ تراکنش را وارد کنید (به تومان یا ریال):")
    await state.set_state(TransactionStates.waiting_for_amount)
    await callback.answer()

@dp.message(TransactionStates.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    amount_str = fa_to_en(message.text).replace(",", "").replace(" ", "")
    # Try to extract number
    import re
    nums = re.findall(r'\d+', amount_str)
    if not nums:
        await message.answer("❌ لطفا یک عدد معتبر وارد کنید:")
        return
    
    amount = float(nums[0])
    await state.update_data(amount=amount)
    
    buttons = [
        [InlineKeyboardButton(text="🔻 هزینه", callback_data="type_expense")],
        [InlineKeyboardButton(text="🔺 درآمد", callback_data="type_income")]
    ]
    await message.answer("نوع تراکنش را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(TransactionStates.waiting_for_type)

@dp.callback_query(TransactionStates.waiting_for_type)
async def process_type(callback: types.CallbackQuery, state: FSMContext):
    t_type = "expense" if callback.data == "type_expense" else "income"
    await state.update_data(type=t_type)
    
    categories = db.get_categories(callback.from_user.id, t_type)
    if not categories:
        # Default categories based on type
        if t_type == "expense":
            categories = ["غذا", "حمل و نقل", "اجاره", "تفریح", "سایر"]
        else:
            categories = ["حقوق", "پاداش", "سرمایه‌گذاری", "سایر"]
        for cat in categories:
            db.add_category(callback.from_user.id, cat, t_type)

    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}")] for cat in categories]
    await callback.message.edit_text("دسته را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(TransactionStates.waiting_for_category)
    await callback.answer()

@dp.callback_query(TransactionStates.waiting_for_category)
async def process_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.replace("cat_", "")
    await state.update_data(category=category)
    
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    await state.update_data(date=today)
    
    data = await state.get_data()
    summary = (
        "✅ تایید تراکنش:\n"
        f"💰 مبلغ: {data['amount']:,}\n"
        f"📂 نوع: {'هزینه' if data['type'] == 'expense' else 'درآمد'}\n"
        f"🏷 دسته: {data['category']}\n"
        f"📅 تاریخ: {data['date']}\n\n"
        "آیا تایید می‌کنید؟"
    )
    buttons = [
        [InlineKeyboardButton(text="✅ تایید", callback_data="confirm_transaction")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="finance_main")]
    ]
    await callback.message.edit_text(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data == "confirm_transaction")
async def confirm_transaction(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db.add_transaction(callback.from_user.id, data['amount'], data['type'], data['category'], data['date'])
    await callback.message.edit_text("✅ تراکنش با موفقیت ثبت شد.", reply_markup=finance_menu_kb())
    await state.clear()
    await callback.answer()

# Reports
@dp.callback_query(F.data == "monthly_report")
async def monthly_report(callback: types.CallbackQuery):
    from datetime import date
    today = date.today()
    report = db.get_monthly_report(callback.from_user.id, today.month, today.year)
    
    income = 0
    expense = 0
    for r_type, amount in report:
        if r_type == 'income': income = amount
        else: expense = amount
    
    text = (
        f"📊 گزارش ماه ({today.strftime('%Y-%m')}):\n\n"
        f"🔺 کل درآمد: {income:,}\n"
        f"🔻 کل هزینه: {expense:,}\n"
        f"⚖️ مانده: {income - expense:,}"
    )
    await callback.message.edit_text(text, reply_markup=finance_menu_kb())
    await callback.answer()

# Planning FSM Handlers
@dp.callback_query(F.data == "add_plan")
async def start_add_plan(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 عنوان برنامه یا کار خود را بنویسید:")
    await state.set_state(PlanStates.waiting_for_title)
    await callback.answer()

@dp.message(PlanStates.waiting_for_title)
async def process_plan_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    
    buttons = [
        [InlineKeyboardButton(text="امروز", callback_data=f"pdate_{today}")],
        [InlineKeyboardButton(text="فردا", callback_data="pdate_tomorrow")]
    ]
    await message.answer("زمان را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(PlanStates.waiting_for_date)

@dp.callback_query(PlanStates.waiting_for_date)
async def process_plan_date(callback: types.CallbackQuery, state: FSMContext):
    from datetime import date, timedelta
    if callback.data == "pdate_tomorrow":
        p_date = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        p_date = callback.data.replace("pdate_", "")
    
    await state.update_data(date=p_date)
    await callback.message.answer("⏰ زمان (مثلا 08:00) یا 'رد کردن' را بزنید:", 
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="skip", callback_data="skip_time")]]))
    await state.set_state(PlanStates.waiting_for_time)
    await callback.answer()

@dp.callback_query(PlanStates.waiting_for_time)
@dp.message(PlanStates.waiting_for_time)
async def process_plan_time(event: types.Message | types.CallbackQuery, state: FSMContext):
    if isinstance(event, types.CallbackQuery):
        await state.update_data(time=None)
    else:
        await state.update_data(time=event.text)
    
    data = await state.get_data()
    db.add_plan(event.from_user.id, data['title'], data['date'], data.get('time'))
    
    text = "✅ برنامه با موفقیت ثبت شد."
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=planning_menu_kb())
    else:
        await event.answer(text, reply_markup=planning_menu_kb())
    
    await state.clear()

# View Plans
@dp.callback_query(F.data.in_(["plans_today", "plans_week"]))
async def view_plans(callback: types.CallbackQuery):
    from datetime import date, timedelta
    today = date.today()
    if callback.data == "plans_today":
        plans = db.get_plans(callback.from_user.id, date=today.strftime("%Y-%m-%d"))
        title_text = "📆 برنامه‌های امروز"
    else:
        start_week = today
        end_week = today + timedelta(days=7)
        plans = db.get_plans(callback.from_user.id, start_date=start_week.strftime("%Y-%m-%d"), end_date=end_week.strftime("%Y-%m-%d"))
        title_text = "📅 برنامه‌های ۷ روز آینده"
    
    if not plans:
        await callback.message.edit_text(f"{title_text}\n❌ هیچ برنامه‌ای یافت نشد.", reply_markup=planning_menu_kb())
        return

    text = f"{title_text}:\n\n"
    buttons = []
    for plan in plans:
        # plan format: (id, user_id, title, date, time, is_done, ...)
        status = "✅" if plan[5] == 1 else "⬜️"
        time_part = f" ({plan[4]})" if plan[4] else ""
        text += f"{status} {plan[2]}{time_part} - {plan[3]}\n"
        buttons.append([
            InlineKeyboardButton(text=f"🗑 {plan[2]}", callback_data=f"del_plan_{plan[0]}"),
            InlineKeyboardButton(text=f"✅ {plan[2]}", callback_data=f"done_plan_{plan[0]}")
        ])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="plan_main")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("done_plan_"))
async def done_plan(callback: types.CallbackQuery):
    plan_id = int(callback.data.replace("done_plan_", ""))
    db.mark_plan_done(plan_id)
    await callback.answer("✅ ثبت شد.")
    # Refresh view
    await view_plans(callback)

@dp.callback_query(F.data.startswith("del_plan_"))
async def del_plan(callback: types.CallbackQuery):
    plan_id = int(callback.data.replace("del_plan_", ""))
    db.delete_plan(plan_id)
    await callback.answer("🗑 حذف شد.")
    # Refresh view
    await view_plans(callback)

# Global Text Handler (AI) - Moved here to ensure registration before polling
from aiogram.filters import StateFilter
@dp.message(F.text & ~F.text.startswith("/"), StateFilter(None))
async def handle_text_ai(message: types.Message, state: FSMContext):
    from datetime import date
    current_date = date.today().strftime("%Y-%m-%d")
    
    loading_msg = await message.answer("🔄 در حال تحلیل...")
    try:
        result = await ai_parser.parse_message(message.text, current_date)
        await loading_msg.delete()
        
        if result.get("action") == "add_transaction" and result.get("section") == "finance":
            amount = result.get("amount", 0)
            t_type = result.get("type", "expense")
            category = result.get("category", "سایر")
            t_date = result.get("date", current_date)
            note = result.get("note", "")
            
            db.add_transaction(message.from_user.id, amount, t_type, category, t_date, note)
            
            persian_type = "هزینه" if t_type == "expense" else "درآمد"
            await message.answer(
                f"✅ تراکنش هوشمند ثبت شد:\n"
                f"💰 مبلغ: {amount:,}\n"
                f"📂 نوع: {persian_type}\n"
                f"🏷 دسته: {category}\n"
                f"📅 تاریخ: {t_date}"
            )
        elif result.get("action") == "add_plan" and result.get("section") == "planning":
            title = result.get("title", "بدون عنوان")
            p_date = result.get("date", current_date)
            time = result.get("time")
            
            db.add_plan(message.from_user.id, title, p_date, time)
            
            await message.answer(
                f"✅ برنامه هوشمند ثبت شد:\n"
                f"📝 عنوان: {title}\n"
                f"📅 تاریخ: {p_date}\n"
                f"⏰ زمان: {time or 'نامشخص'}"
            )
        else:
            await message.answer(
                "❓ متوجه نشدم. می‌توانید از دکمه‌ها استفاده کنید یا جمله‌بندی دیگری را امتحان کنید.",
                reply_markup=main_menu_kb()
            )
    except Exception as e:
        if loading_msg:
            await loading_msg.delete()
        if "429" in str(e) or "quota" in str(e).lower():
            await message.answer(
                "⚠️ متاسفانه سهمیه روزانه هوش مصنوعی به پایان رسیده است.\n"
                "لطفاً از دکمه‌های منو برای ثبت اطلاعات استفاده کنید یا مدتی دیگر امتحان کنید.",
                reply_markup=main_menu_kb()
            )
        else:
            await message.answer(
                "❌ خطایی در تحلیل متن رخ داد. لطفاً از دکمه‌ها استفاده کنید.",
                reply_markup=main_menu_kb()
            )

# Start polling
async def main():
    # Check for restart flag
    if "--restarted" in sys.argv:
        logging.info("Restart detected. Sending notifications to admins...")
        for admin_id in ADMIN_IDS:
            try:
                # Use a small delay to ensure session is ready
                await asyncio.sleep(2)
                await bot.send_message(admin_id, "✅ ربات با موفقیت ری‌استارت شد و آماده به کار است.")
                logging.info(f"Notification sent to {admin_id}")
            except Exception as e:
                logging.error(f"Failed to send restart notification to {admin_id}: {e}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
