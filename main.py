import asyncio
import calendar
import html
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, \
    ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import database

TOKEN = "YOUR_TOKEN_HERE"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- КЛАВИАТУРЫ ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить подписку")],
        [KeyboardButton(text="📋 Мои подписки"), KeyboardButton(text="📊 Статистика")]
    ], resize_keyboard=True
)

cancel_only_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
)


class AddSub(StatesGroup):
    waiting_for_name = State()
    waiting_for_category = State()
    waiting_for_period = State()
    waiting_for_price = State()
    waiting_for_date = State()
    waiting_for_link = State()
    waiting_for_reminder = State()


class EditSub(StatesGroup):
    waiting_for_new_value = State()


def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return sourcedate.replace(year=year, month=month, day=day)


# --- ГЕНЕРАТОР КАРУСЕЛИ ---
def get_sub_message(subs, index):
    total = len(subs)
    index = max(0, min(index, total - 1))
    sub = subs[index]
    sub_id, name, category, period, price, date, remind, link = sub

    safe_name = html.escape(name)
    remind_text = f"за {remind} дн." if remind > 0 else "выключено 🔕"

    text = (f"📑 <b>Подписка {index + 1} из {total}</b>\n\n"
            f"<blockquote><b>{safe_name}</b>\n"
            f"📁 Категория: {category}\n"
            f"💰 Стоимость: <b>{price} руб.</b> <i>({period.lower()})</i>\n"
            f"📅 Списание: <b>{date}</b>\n"
            f"🔔 Напоминание: {remind_text}</blockquote>")

    buttons = []
    buttons.append([InlineKeyboardButton(text="✅ Оплатил (Продлить)", callback_data=f"renew_{sub_id}_{index}")])
    if link: buttons.append([InlineKeyboardButton(text="💳 Оплатить / Настроить", url=link)])
    buttons.append([
        InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_{sub_id}"),
        InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_{sub_id}_{index}")
    ])

    if total > 1:
        prev_idx = index - 1 if index > 0 else total - 1
        next_idx = index + 1 if index < total - 1 else 0
        buttons.append([
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{prev_idx}"),
            InlineKeyboardButton(text=f"• {index + 1} •", callback_data="ignore"),
            InlineKeyboardButton(text="Вперед ➡️", callback_data=f"page_{next_idx}")
        ])
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart())
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    database.add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Я твой личный <b>Менеджер Подписок</b> 🍿\n"
        "Помогу не забыть об оплате и покажу, куда уходят твои деньги.\n\n"
        "<i>Выбери действие в меню ниже:</i>",
        reply_markup=main_keyboard, parse_mode="HTML"
    )


@dp.message(F.text == "❌ Отмена")
async def cancel_action(message: types.Message, state: FSMContext):
    if await state.get_state() is None: return
    await state.clear()
    await message.answer("Действие отменено 🚫", reply_markup=main_keyboard)


# --- ДОБАВЛЕНИЕ ПОДПИСКИ ---
@dp.message(F.text == "➕ Добавить подписку")
async def start_adding(message: types.Message, state: FSMContext):
    await message.answer("📝 Напиши <b>название сервиса</b> (например, Netflix):", reply_markup=cancel_only_kb,
                         parse_mode="HTML")
    await state.set_state(AddSub.waiting_for_name)


@dp.message(AddSub.waiting_for_name)
async def ask_category(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    cat_kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎮 Развлечения"), KeyboardButton(text="💼 Работа")],
        [KeyboardButton(text="🛠 Утилиты"), KeyboardButton(text="🎓 Обучение")],
        [KeyboardButton(text="🛒 Другое")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)
    await message.answer("📁 Выбери <b>категорию</b> подписки:", reply_markup=cat_kb, parse_mode="HTML")
    await state.set_state(AddSub.waiting_for_category)


@dp.message(AddSub.waiting_for_category)
async def ask_period(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await message.answer("📝 Напиши название сервиса:", reply_markup=cancel_only_kb, parse_mode="HTML")
        return await state.set_state(AddSub.waiting_for_name)
    await state.update_data(category=message.text)
    period_kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Ежемесячно"), KeyboardButton(text="Ежегодно")],
        [KeyboardButton(text="Разово")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)
    await message.answer("🔄 Как часто происходит списание?", reply_markup=period_kb)
    await state.set_state(AddSub.waiting_for_period)


@dp.message(AddSub.waiting_for_period)
async def ask_price(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        cat_kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🎮 Развлечения"), KeyboardButton(text="💼 Работа")],
            [KeyboardButton(text="🛠 Утилиты"), KeyboardButton(text="🎓 Обучение")],
            [KeyboardButton(text="🛒 Другое")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
        ], resize_keyboard=True)
        await message.answer("📁 Выбери категорию подписки:", reply_markup=cat_kb, parse_mode="HTML")
        return await state.set_state(AddSub.waiting_for_category)
    await state.update_data(period=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]],
                             resize_keyboard=True)
    await message.answer("💰 Введи <b>стоимость</b> (только число, например 299):", reply_markup=kb, parse_mode="HTML")
    await state.set_state(AddSub.waiting_for_price)


@dp.message(AddSub.waiting_for_price)
async def ask_date(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        period_kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Ежемесячно"), KeyboardButton(text="Ежегодно")],
            [KeyboardButton(text="Разово")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
        ], resize_keyboard=True)
        await message.answer("🔄 Как часто происходит списание?", reply_markup=period_kb)
        return await state.set_state(AddSub.waiting_for_period)
    try:
        price = float(message.text.replace(',', '.'))
        if price <= 0: raise ValueError
    except ValueError:
        return await message.answer("⚠️ Введи корректное число больше нуля:")
    await state.update_data(price=price)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]],
                             resize_keyboard=True)
    await message.answer("📅 Введи <b>дату следующего списания</b> (ДД.ММ.ГГГГ):", reply_markup=kb, parse_mode="HTML")
    await state.set_state(AddSub.waiting_for_date)


@dp.message(AddSub.waiting_for_date)
async def ask_link(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]],
                                 resize_keyboard=True)
        await message.answer("💰 Введи стоимость (числом):", reply_markup=kb, parse_mode="HTML")
        return await state.set_state(AddSub.waiting_for_price)
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
    except ValueError:
        return await message.answer("⚠️ Введи дату строго через точку (ДД.ММ.ГГГГ):")
    await state.update_data(date=message.text)
    link_kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ Пропустить")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)
    await message.answer("🔗 Пришли <b>ссылку</b> на страницу оплаты (или нажми Пропустить):", reply_markup=link_kb,
                         parse_mode="HTML")
    await state.set_state(AddSub.waiting_for_link)


@dp.message(AddSub.waiting_for_link)
async def ask_reminder(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]],
                                 resize_keyboard=True)
        await message.answer("📅 Введи дату списания (ДД.ММ.ГГГГ):", reply_markup=kb, parse_mode="HTML")
        return await state.set_state(AddSub.waiting_for_date)
    link = message.text
    if link != "⏭ Пропустить" and not link.startswith("http"):
        return await message.answer(
            "⚠️ Ссылка должна начинаться с http:// или https://\nПришли правильную ссылку или нажми Пропустить.")
    await state.update_data(link=None if link == "⏭ Пропустить" else link)
    remind_kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="За 1 день"), KeyboardButton(text="За 3 дня")],
        [KeyboardButton(text="За 7 дней"), KeyboardButton(text="Не напоминать")],
        [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)
    await message.answer("🔔 За сколько дней тебе <b>напоминать</b> об оплате?", reply_markup=remind_kb,
                         parse_mode="HTML")
    await state.set_state(AddSub.waiting_for_reminder)


@dp.message(AddSub.waiting_for_reminder)
async def finish_adding(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        link_kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="⏭ Пропустить")],
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="❌ Отмена")]
        ], resize_keyboard=True)
        await message.answer("🔗 Пришли ссылку на оплату:", reply_markup=link_kb, parse_mode="HTML")
        return await state.set_state(AddSub.waiting_for_link)
    user_data = await state.get_data()
    remind_days = 0 if message.text == "Не напоминать" else int(message.text.split()[1])
    database.add_subscription(
        message.from_user.id, user_data['name'], user_data['category'],
        user_data['period'], user_data['price'], user_data['date'],
        user_data.get('link'), remind_days
    )
    await message.answer("✨ <b>Подписка успешно добавлена!</b>", reply_markup=main_keyboard, parse_mode="HTML")
    await state.clear()


# --- СПИСОК ПОДПИСОК ---
@dp.message(F.text == "📋 Мои подписки")
async def btn_list_subs(message: types.Message):
    subs = database.get_subscriptions(message.from_user.id)
    if not subs: return await message.answer("У тебя пока нет подписок. 📭")
    text, kb = get_sub_message(subs, 0)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data.startswith("page_"))
async def page_handler(callback: types.CallbackQuery):
    index = int(callback.data.split('_')[1])
    subs = database.get_subscriptions(callback.from_user.id)
    text, kb = get_sub_message(subs, index)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass  # Игнорируем ошибку, если пользователь быстро листает и текст не успел измениться

    await callback.answer()


@dp.callback_query(F.data == "ignore")
async def ignore_callback(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("renew_"))
async def renew_sub_handler(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    sub_id, index = int(parts[1]), int(parts[2])
    sub_data = database.get_subscription_period_and_date(sub_id)
    if not sub_data: return
    period, date_str, name = sub_data
    if period == "Разово": return await callback.answer("Разовые платежи не продлеваются! 🛑", show_alert=True)
    try:
        current_date = datetime.strptime(date_str, "%d.%m.%Y").date()
    except ValueError:
        return
    new_date = add_months(current_date, 1) if period == "Ежемесячно" else add_months(current_date, 12)
    new_date_str = new_date.strftime("%d.%m.%Y")
    database.update_subscription(sub_id, "next_payment_date", new_date_str)
    await callback.answer(f"✅ Продлено до {new_date_str}", show_alert=True)
    subs = database.get_subscriptions(callback.from_user.id)
    text, kb = get_sub_message(subs, index)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data.startswith("del_"))
async def delete_sub_handler(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    sub_id, index = int(parts[1]), int(parts[2])
    database.delete_subscription(sub_id)
    await callback.answer("Удалено! 🗑")
    subs = database.get_subscriptions(callback.from_user.id)
    if not subs:
        await callback.message.edit_text("Ты удалил все подписки. Список пуст. 📭")
    else:
        text, kb = get_sub_message(subs, index - 1 if index >= len(subs) else index)
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data.startswith("edit_") & (F.data.count('_') == 1))
async def edit_menu_handler(callback: types.CallbackQuery):
    sub_id = callback.data.split('_')[1]
    name = database.get_subscription_name(sub_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Название", callback_data=f"edit_name_{sub_id}"),
         InlineKeyboardButton(text="💰 Стоимость", callback_data=f"edit_price_{sub_id}")],
        [InlineKeyboardButton(text="📅 Дату", callback_data=f"edit_date_{sub_id}"),
         InlineKeyboardButton(text="🔗 Ссылку", callback_data=f"edit_link_{sub_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")]
    ])
    await callback.message.edit_text(f"Что меняем у <b>{html.escape(name)}</b>?", reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "cancel_edit")
async def cancel_edit_handler(callback: types.CallbackQuery):
    await callback.message.delete()
    await btn_list_subs(callback.message)


@dp.callback_query(F.data.startswith("edit_") & (F.data.count('_') == 2))
async def ask_new_value_handler(callback: types.CallbackQuery, state: FSMContext):
    _, field, sub_id = callback.data.split('_')
    await state.update_data(edit_sub_id=sub_id, edit_field=field)
    prompts = {"price": "Новая стоимость:", "date": "Новая дата (ДД.ММ.ГГГГ):", "name": "Новое название:",
               "link": "Новая ссылка (http...):"}
    await callback.message.answer(f"⌨️ {prompts[field]}", reply_markup=cancel_only_kb)
    await state.set_state(EditSub.waiting_for_new_value)
    await callback.answer()


@dp.message(EditSub.waiting_for_new_value)
async def save_new_value_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    sub_id, field, new_value = data['edit_sub_id'], data['edit_field'], message.text
    if field == "price":
        try:
            new_value = float(new_value.replace(',', '.'))
            if new_value <= 0: raise ValueError
        except ValueError:
            return await message.answer("⚠️ Введи корректное число!")
    elif field == "date":
        try:
            datetime.strptime(new_value, "%d.%m.%Y")
        except ValueError:
            return await message.answer("⚠️ Введи дату в формате ДД.ММ.ГГГГ!")
    db_col = "price" if field == "price" else "next_payment_date" if field == "date" else "payment_link" if field == "link" else "service_name"
    database.update_subscription(sub_id, db_col, new_value)
    await message.answer("✅ Изменения сохранены!", reply_markup=main_keyboard)
    await state.clear()
    await btn_list_subs(message)


# ==========================================
# --- МНОГОУРОВНЕВАЯ СТАТИСТИКА (4 Вкладки) ---
# ==========================================

def get_stats_keyboard(current_tab):
    # Теперь вкладки расположены в два ряда (2x2)
    buttons = []
    tabs_row1 = {"main": "📊 Общая", "cats": "📁 Разделы"}
    tabs_row2 = {"months": "🗓 По месяцам", "soon": "📅 Ближайшие"}

    row1, row2 = [], []
    for key, name in tabs_row1.items():
        btn_text = f"🔹 {name}" if key == current_tab else name
        row1.append(InlineKeyboardButton(text=btn_text, callback_data=f"statstab_{key}"))
    for key, name in tabs_row2.items():
        btn_text = f"🔹 {name}" if key == current_tab else name
        row2.append(InlineKeyboardButton(text=btn_text, callback_data=f"statstab_{key}"))

    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


@dp.message(F.text == "📊 Статистика")
async def btn_stats(message: types.Message):
    await show_statistics_tab(message.from_user.id, "main", message)


@dp.callback_query(F.data.startswith("statstab_"))
async def stat_tabs_handler(callback: types.CallbackQuery):
    tab = callback.data.split('_')[1]
    await show_statistics_tab(callback.from_user.id, tab, callback.message, is_edit=True)
    await callback.answer()


async def show_statistics_tab(user_id, tab, message: types.Message, is_edit=False):
    subs = database.get_subscriptions(user_id)
    if not subs:
        text = "У тебя пока нет подписок. Статистика пуста. 📭"
        if is_edit:
            try:
                await message.edit_text(text)
            except TelegramBadRequest:
                pass
        else:
            await message.answer(text)
        return

    text = ""

    if tab == "main":
        total_monthly, total_yearly = 0.0, 0.0
        categories = {}
        for sub in subs:
            _, _, cat, period, price, _, _, _ = sub
            monthly_cost = price if period == "Ежемесячно" else (price / 12 if period == "Ежегодно" else 0)
            total_monthly += monthly_cost
            total_yearly += price * 12 if period == "Ежемесячно" else (price if period == "Ежегодно" else 0)
            if period != "Разово": categories[cat] = categories.get(cat, 0) + monthly_cost

        text = (f"📊 <b>Общая финансовая сводка:</b>\n\n"
                f"💸 Уходит в месяц: <b>{total_monthly:.2f} руб.</b>\n"
                f"💳 Уходит в год: <b>{total_yearly:.2f} руб.</b>\n\n"
                f"📉 <b>Доли категорий:</b>\n\n")

        cat_total = sum(categories.values())
        for cat, cost in sorted(categories.items(), key=lambda item: item[1], reverse=True):
            percent = (cost / cat_total * 100) if cat_total > 0 else 0
            filled = int(percent / 10)
            empty = 10 - filled
            bar = "█" * filled + "░" * empty
            text += f"▪️ {cat}: <b>{cost:.2f} руб.</b>\n<code>[{bar}] {percent:.0f}%</code>\n\n"

    elif tab == "cats":
        categories_dict = {}
        for sub in subs:
            _, name, cat, period, price, _, _, _ = sub
            if cat not in categories_dict: categories_dict[cat] = []
            categories_dict[cat].append((name, price, period))

        text = "📁 <b>Детализация по разделам:</b>\n\n"
        for cat, items in categories_dict.items():
            text += f"<b>{cat}</b>\n"
            for name, price, period in items:
                period_short = "мес" if period == "Ежемесячно" else "год" if period == "Ежегодно" else "раз"
                text += f" ├ {html.escape(name)} — {price}₽/{period_short}\n"
            text += "\n"

    elif tab == "months":
        today = datetime.now().date()
        months_dict = {}

        for i in range(12):
            m = add_months(today.replace(day=1), i)
            months_dict[(m.year, m.month)] = 0.0

        for sub in subs:
            _, _, _, period, price, date_str, _, _ = sub
            try:
                pay_date = datetime.strptime(date_str, "%d.%m.%Y").date()
            except ValueError:
                continue

            current_pay = pay_date
            for _ in range(60):
                if (current_pay.year, current_pay.month) in months_dict:
                    months_dict[(current_pay.year, current_pay.month)] += price

                if period == "Ежемесячно":
                    current_pay = add_months(current_pay, 1)
                elif period == "Ежегодно":
                    current_pay = add_months(current_pay, 12)
                else:
                    break

                if current_pay > add_months(today, 12): break

        month_names = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
        text = "🗓 <b>Прогноз расходов на год вперед:</b>\n\n"
        max_val = max(months_dict.values()) if months_dict.values() else 0

        for (y, m), val in months_dict.items():
            month_str = f"{month_names[m - 1]} {y}"
            if max_val > 0 and val > 0:
                percent = val / max_val * 100
                filled = int(percent / 10)
                bar = "█" * filled + "░" * (10 - filled)
                text += f"<b>{month_str}</b> — {val:.0f}₽\n<code>[{bar}]</code>\n"
            else:
                text += f"<b>{month_str}</b> — 0₽\n"

    elif tab == "soon":
        today = datetime.now().date()
        upcoming = []
        for sub in subs:
            _, name, _, period, price, date_str, _, _ = sub
            if period == "Разово": continue
            try:
                pay_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                if pay_date <= today + timedelta(days=30):
                    days_left = (pay_date - today).days
                    upcoming.append((days_left, pay_date, name, price))
            except ValueError:
                pass

        upcoming.sort(key=lambda x: x[0])
        text = "📅 <b>Календарь списаний (на 30 дней):</b>\n\n"
        if not upcoming:
            text += "<i>В ближайший месяц списаний не предвидится! 🎉</i>"
        else:
            for days_left, pay_date, name, price in upcoming:
                if days_left < 0:
                    time_text = "⚠️ Просрочено!"
                elif days_left == 0:
                    time_text = "🔥 <b>СЕГОДНЯ!</b>"
                elif days_left == 1:
                    time_text = "Завтра"
                else:
                    time_text = f"Через {days_left} дн."
                text += f"▪️ <b>{html.escape(name)}</b> ({price} руб.)\n   └ {pay_date.strftime('%d.%m.%Y')} — <i>{time_text}</i>\n\n"

    kb = get_stats_keyboard(tab)
    if is_edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            pass  # Игнорируем ошибку двойного клика по одной и той же вкладке
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ==========================================

# --- НАПОМИНАНИЯ ---
async def check_reminders():
    subs = database.get_all_subscriptions_for_reminders()
    today = datetime.now().date()
    for user_id, name, price, date_str, rem_days, link in subs:
        try:
            if (datetime.strptime(date_str, "%d.%m.%Y").date() - timedelta(days=rem_days)) == today:
                safe_name = html.escape(name)
                text = f"🔔 <b>Напоминание!</b>\nЧерез {rem_days} дн. спишется оплата за <b>{safe_name}</b> ({price} руб.)"
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="💳 Оплатить / Настроить", url=link)]]) if link else None
                await bot.send_message(user_id, text, reply_markup=kb, parse_mode="HTML")
        except ValueError:
            pass


@dp.message(F.text == "/test_remind")
async def test_remind_handler(message: types.Message):
    await check_reminders()
    await message.answer("Проверка окончена!")


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    scheduler.add_job(check_reminders, trigger='cron', hour=10, minute=0)
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())