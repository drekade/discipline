import os, json, httpx, asyncio, random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8590477703:AAEVFUa4DBUiuvob2iI2Y1sOXetIjauk-n4")
GROQ_KEY       = os.environ.get("GROQ_KEY", "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")
SUPA_URL       = os.environ.get("SUPA_URL", "https://btgtgcwbrrnfbctchata.supabase.co")
SUPA_KEY       = os.environ.get("SUPA_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0Z3RnY3dicnJuZmJjdGNoYXRhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MTQ2OTgsImV4cCI6MjA5MjI5MDY5OH0.lyEWFcmsL3GIm0FrEZdGkK2uRSx26cNiBGFvCVsjdsY")

SUPA_H = {
    "apikey": SUPA_KEY,
    "Authorization": f"Bearer {SUPA_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

YEAR = datetime.now().year
TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_NICE = datetime.now().strftime("%d.%m.%Y")
conversations = {}
pending = {}
last_checkin = {}  # uid -> datetime of last check-in message

SYSTEM = f"""Ты — Рак, личный ассистент Катерины (контент-мейкер, режиссёр, 32 года). Профессиональный, чёткий, с лёгким юмором. Обращайся "Катерина". Отвечаешь коротко.

СЕГОДНЯ: {TODAY} ({TODAY_NICE})
ТЕКУЩИЙ ГОД: {YEAR}

УКРАИНСКИЕ МЕСЯЦЫ: січень=01 лютий=02 березень=03 квітень=04 травень=05 червень=06 липень=07 серпень=08 вересень=09 жовтень=10 листопад=11 грудень=12

ЛОГИКА РАСПОЗНАВАНИЯ:

1. НЕСКОЛЬКО СЪЁМОК (action: add_multiple_shoots) — несколько блоков с датами/местами.
   Каждый блок — отдельная съёмка. Массив shoots[]. Игнорируй @ники.

2. ОДНА СЪЁМКА (action: add_shoot) — есть явная локация + желательно дата.
   Если есть ЛОКАЦИЯ но нет ДАТЫ → action=clarify, data.partial = {{location, time, project, people}} — всё что знаешь. В reply спроси дату.
   Если нет локации — это не съёмка.

3. УДАЛЕНИЕ СЪЁМКИ (action: delete_shoot) — "удали съёмку X"
   data: {{shoot_date, shoot_location, shoot_time}}

4. ЗАВЕРШЕНИЕ ПРОЕКТА (action: complete_project) — "закончила/завершила проект X"

5. ИДЕЯ (action: add_idea) — "идея:", "ідея:"

6. ДНЕВНИК (action: add_diary) — Катерина рассказывает про прожитый день: что делала, как встала, когда работала, как себя чувствовала.
   ВАЖНО: если видишь рассказ про день, работу, детали дня — action=add_diary. Не перестраховывайся.
   events = что делала (факты). thoughts = мысли/чувства если есть.

7. ЛИЧНОЕ СОБЫТИЕ (action: add_event) — врач, ветеринар, школа, мероприятие, встреча
   data: {{title, date(YYYY-MM-DD), time, category, notes}}

8. НОВЫЙ ПРОЕКТ (action: add_project)

9. ОЧИСТКА ПОЛЯ (action: clear_field) — "отмени/убери/очисти заметку/ссылку"
   data: {{field: "notes"|"script"|"link", entity: "shoot"|"project"}}

10. ОТВЕТ НА УТОЧНЕНИЕ (action: clarify_reply) — ТОЛЬКО если ТВОЙ ПРОШЛЫЙ reply был вопросом "какая дата?"/"во сколько?"/"где?",
    а Катерина даёт эти недостающие данные одним-двумя словами ("завтра", "в 10", "25 апреля").
    data: {{field_given: "date"|"time"|"location", value: "..."}}

11. РАЗГОВОР (action: none) — только короткие междометия и прямые вопросы.
    "привет","дякую","ок","да","нет" — action: none.

ХАРАКТЕР: отвечай на том же языке что Катерина. Поддержи если тяжело. Не навязывайся с вопросами.

ПОСЛЕ СОХРАНЕНИЯ В ДНЕВНИК скажи коротко что записала, можешь мягко спросить как она.

ФОРМАТ — только JSON без markdown:
{{"reply":"текст","action":"none|add_shoot|add_multiple_shoots|delete_shoot|clarify|clarify_reply|clear_field|complete_project|add_idea|add_diary|add_event|add_project","data":{{}}}}

data для add_multiple_shoots: {{"shoots":[{{"date":"YYYY-MM-DD","time":"HH:MM","location":"","project":"","people":"","script":"","notes":""}}]}}
data для add_diary: mood(хорошо/нейтрально/плохо), events, thoughts
data для add_event: title, date(YYYY-MM-DD), time, category, notes
data для delete_shoot: shoot_date, shoot_location, shoot_time
data для clear_field: field, entity
data для clarify: partial
data для clarify_reply: field_given, value"""

async def ask_groq(messages):
    groq_messages = [{"role": "system", "content": SYSTEM}]
    for m in messages:
        role = "assistant" if m["role"] == "model" else "user"
        text = "".join(p.get("text","") for p in m.get("parts",[]))
        groq_messages.append({"role": role, "content": text})
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": groq_messages, "temperature": 0.3, "max_tokens": 1000}
        )
        data = r.json()
        raw = data.get("choices",[{}])[0].get("message",{}).get("content","{}")
        raw = raw.strip().replace("```json","").replace("```","").strip()
        print(f"GROQ: {raw[:200]}")
        try:
            parsed = json.loads(raw)
            # Make sure reply doesn't contain raw JSON
            if isinstance(parsed.get("reply"), str) and '{"reply"' in parsed.get("reply",""):
                # Extract just the text before the JSON
                reply_text = parsed["reply"].split('{"reply"')[0].strip()
                parsed["reply"] = reply_text if reply_text else "Записала!"
            return parsed
        except:
            # If raw itself looks like it has JSON embedded, try to extract
            if '{"reply"' in raw:
                try:
                    start = raw.index('{"reply"')
                    return json.loads(raw[start:])
                except:
                    pass
            return {"reply": raw.split('{')[0].strip() or "Окей!", "action": "none", "data": {}}

async def supa_get(table, limit=100, order="created_at.desc"):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{SUPA_URL}/rest/v1/{table}?order={order}&limit={limit}", headers=SUPA_H)
        return r.json() if r.status_code == 200 else []

async def supa_insert(table, data):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{SUPA_URL}/rest/v1/{table}", headers=SUPA_H, json=data)
        print(f"INSERT {table}: {r.status_code} {r.text[:80]}")
        return r.status_code in (200, 201)

async def supa_update(table, field, value, data):
    async with httpx.AsyncClient() as c:
        r = await c.patch(f"{SUPA_URL}/rest/v1/{table}?{field}=eq.{value}", headers=SUPA_H, json=data)
        return r.status_code in (200, 204)

async def supa_delete(table, field, value):
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{SUPA_URL}/rest/v1/{table}?{field}=eq.{value}", headers=SUPA_H)
        return r.status_code in (200, 204)

async def apply_action(action, data):
    today = datetime.now().strftime("%Y-%m-%d")
    months = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]
    today_ru = f"{datetime.now().day} {months[datetime.now().month-1]} {datetime.now().year}"

    if action == "add_shoot":
        # пост-валидация: съёмка без локации не сохраняется
        loc = (data.get("location") or "").strip()
        if not loc or loc.lower() in ("не указано","none","null","—","-"):
            print(f"SKIP add_shoot: empty location ({data})")
            return False
        return await supa_insert("shoots", {
            "date": data.get("date", today), "time": data.get("time",""),
            "location": loc, "project": data.get("project",""),
            "people": data.get("people",""), "script": data.get("script",""),
            "notes": data.get("notes",""), "status": "не снято"
        })
    elif action == "add_multiple_shoots":
        shoots = data.get("shoots", [])
        saved = 0
        for s in shoots:
            # пост-валидация: каждая съёмка обязана иметь локацию
            loc = (s.get("location") or "").strip()
            if not loc or loc.lower() in ("не указано","none","null","—","-"):
                print(f"SKIP multiple_shoot: empty location ({s})")
                continue
            ok = await supa_insert("shoots", {
                "date": s.get("date", today), "time": s.get("time",""),
                "location": loc, "project": s.get("project",""),
                "people": s.get("people",""), "script": s.get("script",""),
                "notes": s.get("notes",""), "status": "не снято"
            })
            if ok: saved += 1
        return saved
    elif action == "clear_field":
        # очистка поля у последней съёмки или проекта
        field = data.get("field","notes")
        entity = data.get("entity","shoot")
        if entity == "shoot":
            shoots = await supa_get("shoots", 1, order="created_at.desc")
            if shoots:
                return await supa_update("shoots","id",shoots[0]["id"],{field:""})
        elif entity == "project":
            projects = await supa_get("projects", 1, order="created_at.desc")
            if projects:
                return await supa_update("projects","id",projects[0]["id"],{field:""})
        return False
    elif action == "delete_shoot":
        shoots = await supa_get("shoots", 100)
        for s in shoots:
            date_match = not data.get("shoot_date") or s.get("date","") == data.get("shoot_date","")
            loc = data.get("shoot_location","").lower()
            loc_match = not loc or loc in s.get("location","").lower()
            time_val = data.get("shoot_time","")
            time_match = not time_val or time_val in s.get("time","")
            if date_match and loc_match and time_match:
                return await supa_delete("shoots","id",s["id"])
        return False
    elif action == "complete_project":
        projects = await supa_get("projects", 50)
        for p in projects:
            if data.get("project_name","").lower() in p.get("name","").lower():
                await supa_update("projects","id",p["id"],{"status":"готово"})
                return True
    elif action == "add_idea":
        return await supa_insert("ideas",{"title":data.get("title",""),"description":data.get("description",""),"category":data.get("category","Идея"),"image_url":None})
    elif action == "add_diary":
        return await supa_insert("diary",{"date":today_ru,"mood":data.get("mood","нейтрально"),"events":data.get("events",""),"thoughts":data.get("thoughts","")})
    elif action == "add_event":
        return await supa_insert("events",{"title":data.get("title",""),"date":data.get("date",today),"time":data.get("time",""),"category":data.get("category","Личное"),"notes":data.get("notes","")})
    elif action == "add_project":
        return await supa_insert("projects",{"name":data.get("name",""),"description":data.get("description",""),"status":"в работе"})
    return False

def fmt_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m")
    except:
        return date_str or ""

def main_kbd():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Съёмки", callback_data="shoots"),
         InlineKeyboardButton("🎬 Проекты", callback_data="projects")],
        [InlineKeyboardButton("💡 Идеи", callback_data="ideas"),
         InlineKeyboardButton("📓 Дневник", callback_data="diary")],
        [InlineKeyboardButton("🗓 События", callback_data="events"),
         InlineKeyboardButton("📊 Итоги", callback_data="week")]
    ])

def shoot_detail_kbd(shoot_id, status):
    toggle_label = "Отметить снято ✅" if status != "снято" else "Отметить не снято 🔸"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data=f"toggle_{shoot_id}")],
        [InlineKeyboardButton("🔗 Добавить ссылку", callback_data=f"addlink_shoot_{shoot_id}"),
         InlineKeyboardButton("📝 Добавить заметку", callback_data=f"addnote_shoot_{shoot_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"del_shoot_{shoot_id}")],
        [InlineKeyboardButton("◀️ К съёмкам", callback_data="shoots")]
    ])

def proj_detail_kbd(proj_id, status):
    toggle_label = "Вернуть в работу" if status == "готово" else "✅ Завершить"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data=f"toggle_proj_{proj_id}")],
        [InlineKeyboardButton("🔗 Добавить ссылку", callback_data=f"addlink_proj_{proj_id}"),
         InlineKeyboardButton("📝 Добавить заметку", callback_data=f"addnote_proj_{proj_id}")],
        [InlineKeyboardButton("◀️ К проектам", callback_data="projects")]
    ])

def render_shoot(s):
    lines = [f"📅 {s.get('date','')} {s.get('time','')}",
             f"📍 {s.get('location','')}"]
    if s.get("project"): lines.append(f"🎬 {s['project']}")
    if s.get("people"): lines.append(f"👥 {s['people']}")
    if s.get("notes"): lines.append(f"📝 {s['notes']}")
    if s.get("script"): lines.append(f"🔗 {s['script']}")
    lines.append(f"\nСтатус: {'✅ снято' if s.get('status')=='снято' else '🔸 не снято'}")
    return "\n".join(lines)

def render_project(p, shoots, tasks):
    lines = [f"🎬 *{p.get('name','')}*",
             f"Статус: {'✅ готово' if p.get('status')=='готово' else '🔸 в работе'}"]
    if p.get("description"): lines.append(f"\n{p['description']}")
    if p.get("link"): lines.append(f"🔗 {p['link']}")
    if p.get("notes"): lines.append(f"📝 {p['notes']}")
    proj_tasks = [t for t in tasks if t.get("project_id") == p.get("id")]
    if proj_tasks:
        lines.append(f"\n📋 Задачи:")
        for t in proj_tasks:
            icon = "✅" if t.get("status")=="готово" else "🔄" if t.get("status")=="в работе" else "⬜"
            lines.append(f"  {icon} {t.get('title','')}")
    proj_shoots = [s for s in shoots if s.get("project","") == p.get("name","")]
    if proj_shoots:
        lines.append(f"\n📅 Съёмок: {len(proj_shoots)}")
    return "\n".join(lines)

def get_history(uid):
    if uid not in conversations: conversations[uid] = []
    return conversations[uid]

def add_history(uid, role, text):
    h = get_history(uid)
    h.append({"role": role, "parts": [{"text": text or "—"}]})
    if len(h) > 14: conversations[uid] = h[-14:]

async def send_checkin(bot, uid):
    """Send a gentle check-in message"""
    phrases = [
        "Как ты сегодня, Катерина? 🙂",
        "Катерина, как дела? Всё в порядке?",
        "Как прошёл день?",
    ]
    await bot.send_message(chat_id=uid, text=random.choice(phrases))
    last_checkin[uid] = datetime.now()

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conversations[uid] = []
    pending.pop(uid, None)
    await update.message.reply_text(
        "Привет, Катерина! Я Рак — твой личный ассистент 🦀\n\n"
        "Пиши как угодно — русский, украинский, вперемешку.\n"
        "Можешь пересылать сообщения от координатора.\n\n"
        "Записываю съёмки, идеи, проекты, события и дневник 🙂",
        reply_markup=main_kbd()
    )
    # Schedule check-ins
    ctx.job_queue.run_repeating(
        lambda ctx: asyncio.create_task(send_checkin(ctx.bot, uid)),
        interval=172800,  # every 2 days
        first=86400,  # first after 1 day
        name=f"checkin_{uid}"
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    text = msg.text or msg.caption or ""
    if not text:
        await msg.reply_text("Напиши что-нибудь 🙂")
        return

    # Check if waiting for link/note
    if uid in pending:
        p = pending[uid]
        # pending от clarify обрабатываем ниже в общей ветке Groq, не здесь
        if p.get("type") == "clarify_shoot":
            pass
        else:
            # стоп-слова: отмена или очистка вместо ввода заметки/ссылки
            stop_words = ("отмен","отміни","не надо","забей","стоп","cancel","скасуй")
            low = text.strip().lower()
            if any(low.startswith(w) for w in stop_words) or low in ("нет","ні","no"):
                pending.pop(uid, None)
                # если хотели "отмени заметку" и это было pending notes — очистим поле
                if "очисти" in low or "удали" in low or "сотри" in low:
                    entity_type = p["type"]
                    entity_id = p["id"]
                    field = p["field"]
                    table = "shoots" if entity_type == "shoot" else "projects"
                    await supa_update(table,"id",entity_id,{field:""})
                    await msg.reply_text(f"🗑 {field} очищено", reply_markup=main_kbd())
                else:
                    await msg.reply_text("Окей, отменила ✓", reply_markup=main_kbd())
                return
            p = pending.pop(uid)
            field = p["field"]
            entity_type = p["type"]
            entity_id = p["id"]
            if entity_type == "shoot":
                await supa_update("shoots","id",entity_id,{field:text.strip()})
                shoots = await supa_get("shoots",100)
                s = next((x for x in shoots if x.get("id")==entity_id),None)
                if s:
                    await msg.reply_text(f"{'🔗 Ссылка' if field=='script' else '📝 Заметка'} добавлена ✓\n\n"+render_shoot(s),
                        parse_mode="Markdown",reply_markup=shoot_detail_kbd(entity_id,s.get("status","")))
                return
            elif entity_type == "project":
                await supa_update("projects","id",entity_id,{field:text.strip()})
                projects = await supa_get("projects",50)
                shoots = await supa_get("shoots",100)
                tasks = await supa_get("tasks",200)
                p_obj = next((x for x in projects if x.get("id")==entity_id),None)
                if p_obj:
                    await msg.reply_text(f"{'🔗 Ссылка' if field=='link' else '📝 Заметка'} добавлена ✓\n\n"+render_project(p_obj,shoots,tasks),
                        parse_mode="Markdown",reply_markup=proj_detail_kbd(entity_id,p_obj.get("status","")))
                return

    add_history(uid, "user", text)
    thinking = await msg.reply_text("⏳")
    try:
        result = await ask_groq(get_history(uid))
        reply = result.get("reply","Окей!")
        action = result.get("action","none")
        data = result.get("data",{})
        add_history(uid, "model", reply)

        # === Обработка clarify: сохраняем частичные данные и ждём ответа ===
        if action == "clarify":
            pending[uid] = {"type":"clarify_shoot","partial":data.get("partial",{})}
            await thinking.delete()
            await msg.reply_text(reply)
            return

        # === Обработка ответа на уточнение ===
        if action == "clarify_reply":
            prev = pending.pop(uid, None)
            if prev and prev.get("type") == "clarify_shoot":
                merged = dict(prev.get("partial",{}))
                field = data.get("field_given","")
                value = data.get("value","")
                if field and value:
                    merged[field] = value
                # если теперь есть локация — пробуем сохранить
                if (merged.get("location") or "").strip():
                    saved = await apply_action("add_shoot", merged)
                    await thinking.delete()
                    if saved:
                        details = []
                        if merged.get("date"): details.append(f"📅 {merged['date']}")
                        if merged.get("time"): details.append(f"🕐 {merged['time']}")
                        if merged.get("location"): details.append(f"📍 {merged['location']}")
                        reply_text = reply + "\n\n" + "\n".join(details) if details else reply
                        await msg.reply_text(reply_text, reply_markup=main_kbd())
                    else:
                        await msg.reply_text(reply)
                    return
                else:
                    # ещё чего-то не хватает — продолжаем держать pending
                    pending[uid] = {"type":"clarify_shoot","partial":merged}
                    await thinking.delete()
                    await msg.reply_text(reply)
                    return
            # если pending не было — обработаем как обычное сообщение
            await thinking.delete()
            await msg.reply_text(reply)
            return

        saved = False
        if action not in ("none","clarify","clarify_reply"):
            saved = await apply_action(action, data)
        # если было pending от clarify а пришло что-то другое — сбрасываем
        pending.pop(uid, None) if uid in pending and pending[uid].get("type") == "clarify_shoot" else None
        await thinking.delete()
        if action == "add_shoot" and saved:
            details = []
            if data.get("date"): details.append(f"📅 {data['date']}")
            if data.get("time"): details.append(f"🕐 {data['time']}")
            if data.get("location"): details.append(f"📍 {data['location']}")
            if data.get("people"): details.append(f"👥 {data['people']}")
            if details: reply += "\n\n" + "\n".join(details)
        elif action == "add_multiple_shoots" and saved:
            reply += f"\n\nЗаписала {saved} съёмок ✓"
        show_kbd = action not in ("none","clarify")
        await msg.reply_text(reply, reply_markup=main_kbd() if show_kbd else None)
    except Exception as e:
        await thinking.delete()
        print(f"ERROR: {e}")
        await msg.reply_text("Что-то пошло не так 😔 Попробуй ещё раз")

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cb = q.data
    uid = q.from_user.id

    if cb == "main":
        pending.pop(uid, None)
        await q.edit_message_text("Выбери раздел:", reply_markup=main_kbd())
        return

    if cb == "shoots":
        pending.pop(uid, None)
        items = await supa_get("shoots",20,order="date.asc")
        if not items:
            await q.edit_message_text("📅 Съёмок пока нет", reply_markup=main_kbd())
            return
        buttons = []
        for s in items:
            icon = "✅" if s.get("status")=="снято" else "🔸"
            label = f"{icon} {fmt_date(s.get('date',''))} {s.get('time','')} — {s.get('location','?')[:18]}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"shoot_{s['id']}")])
        buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="main")])
        await q.edit_message_text("📅 Выбери съёмку:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if cb.startswith("shoot_") and "_" not in cb[6:]:
        shoot_id = int(cb.split("_")[1])
        items = await supa_get("shoots",100)
        s = next((x for x in items if x.get("id")==shoot_id),None)
        if not s:
            await q.edit_message_text("Не найдено")
            return
        await q.edit_message_text(render_shoot(s),reply_markup=shoot_detail_kbd(shoot_id,s.get("status","")))
        return

    if cb.startswith("addlink_shoot_"):
        shoot_id = int(cb.split("_")[2])
        pending[uid] = {"type":"shoot","id":shoot_id,"field":"script"}
        await q.edit_message_text("🔗 Отправь ссылку:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена",callback_data=f"shoot_{shoot_id}")]]))
        return

    if cb.startswith("addnote_shoot_"):
        shoot_id = int(cb.split("_")[2])
        pending[uid] = {"type":"shoot","id":shoot_id,"field":"notes"}
        await q.edit_message_text("📝 Напиши заметку:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена",callback_data=f"shoot_{shoot_id}")]]))
        return

    if cb.startswith("toggle_") and "proj" not in cb:
        shoot_id = int(cb.split("_")[1])
        items = await supa_get("shoots",100)
        s = next((x for x in items if x.get("id")==shoot_id),None)
        if s:
            await supa_update("shoots","id",shoot_id,{"status":"снято" if s.get("status")!="снято" else "не снято"})
        items = await supa_get("shoots",100)
        s = next((x for x in items if x.get("id")==shoot_id),None)
        if s:
            await q.edit_message_text(render_shoot(s),reply_markup=shoot_detail_kbd(shoot_id,s.get("status","")))
        return

    if cb.startswith("del_shoot_"):
        shoot_id = int(cb.split("_")[2])
        await supa_delete("shoots","id",shoot_id)
        await q.edit_message_text("🗑 Удалено",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ К съёмкам",callback_data="shoots")]]))
        return

    if cb == "projects":
        pending.pop(uid, None)
        items = await supa_get("projects",20)
        if not items:
            await q.edit_message_text("🎬 Проектов пока нет", reply_markup=main_kbd())
            return
        buttons = []
        for p in items:
            icon = "✅" if p.get("status")=="готово" else "🔸"
            buttons.append([InlineKeyboardButton(f"{icon} {p.get('name','')[:30]}", callback_data=f"proj_{p['id']}")])
        buttons.append([InlineKeyboardButton("◀️ Назад",callback_data="main")])
        await q.edit_message_text("🎬 Выбери проект:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if cb.startswith("proj_") and "toggle" not in cb:
        proj_id = int(cb.split("_")[1])
        projects = await supa_get("projects",50)
        shoots = await supa_get("shoots",100)
        tasks = await supa_get("tasks",200)
        p = next((x for x in projects if x.get("id")==proj_id),None)
        if not p:
            await q.edit_message_text("Не найдено")
            return
        await q.edit_message_text(render_project(p,shoots,tasks),parse_mode="Markdown",reply_markup=proj_detail_kbd(proj_id,p.get("status","")))
        return

    if cb.startswith("addlink_proj_"):
        proj_id = int(cb.split("_")[2])
        pending[uid] = {"type":"project","id":proj_id,"field":"link"}
        await q.edit_message_text("🔗 Отправь ссылку (Google Docs, Notion, Figma...):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена",callback_data=f"proj_{proj_id}")]]))
        return

    if cb.startswith("addnote_proj_"):
        proj_id = int(cb.split("_")[2])
        pending[uid] = {"type":"project","id":proj_id,"field":"notes"}
        await q.edit_message_text("📝 Напиши заметку:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена",callback_data=f"proj_{proj_id}")]]))
        return

    if cb.startswith("toggle_proj_"):
        proj_id = int(cb.split("_")[2])
        projects = await supa_get("projects",50)
        p = next((x for x in projects if x.get("id")==proj_id),None)
        if p:
            await supa_update("projects","id",proj_id,{"status":"готово" if p.get("status")!="готово" else "в работе"})
        projects = await supa_get("projects",50)
        shoots = await supa_get("shoots",100)
        tasks = await supa_get("tasks",200)
        p = next((x for x in projects if x.get("id")==proj_id),None)
        if p:
            await q.edit_message_text(render_project(p,shoots,tasks),parse_mode="Markdown",reply_markup=proj_detail_kbd(proj_id,p.get("status","")))
        return

    if cb == "ideas":
        items = await supa_get("ideas",10)
        if not items:
            await q.edit_message_text("💡 Идей пока нет", reply_markup=main_kbd())
            return
        lines = ["💡 *Идеи:*\n"]
        for i in items:
            lines.append(f"• *{i.get('title','')}*")
            if i.get("description"): lines.append(f"  {i['description'][:150]}")
        await q.edit_message_text("\n".join(lines),parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад",callback_data="main")]]))
        return

    if cb == "diary":
        pending.pop(uid, None)
        items = await supa_get("diary",10)
        if not items:
            await q.edit_message_text("📓 Записей пока нет", reply_markup=main_kbd())
            return
        buttons = []
        moods = {"хорошо":"😊","нейтрально":"😐","плохо":"😔"}
        for d in items:
            me = moods.get(d.get("mood","нейтрально"),"😐")
            buttons.append([InlineKeyboardButton(f"{me} {d.get('date','')}", callback_data=f"diary_{d['id']}")])
        buttons.append([InlineKeyboardButton("◀️ Назад",callback_data="main")])
        await q.edit_message_text("📓 Дневник:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if cb.startswith("diary_"):
        diary_id = int(cb.split("_")[1])
        items = await supa_get("diary",50)
        d = next((x for x in items if x.get("id")==diary_id),None)
        if not d:
            await q.edit_message_text("Не найдено")
            return
        moods = {"хорошо":"😊","нейтрально":"😐","плохо":"😔"}
        me = moods.get(d.get("mood","нейтрально"),"😐")
        lines = [f"{me} *{d.get('date','')}*"]
        if d.get("events"): lines.append(f"\n📌 {d['events']}")
        if d.get("thoughts"): lines.append(f"\n💭 {d['thoughts']}")
        await q.edit_message_text("\n".join(lines),parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ К дневнику",callback_data="diary")]]))
        return

    if cb == "events":
        items = await supa_get("events",15,order="date.asc")
        if not items:
            await q.edit_message_text("🗓 Событий пока нет\n\nНапиши боту: *запись к врачу 5 мая 10:00*",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад",callback_data="main")]]))
            return
        lines = ["🗓 *События:*\n"]
        for e in items:
            lines.append(f"• *{e.get('date','')}* {e.get('time','')} — {e.get('title','')}")
            if e.get("category"): lines.append(f"  {e['category']}")
        await q.edit_message_text("\n".join(lines),parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад",callback_data="main")]]))
        return

    if cb == "week":
        week_ago = (datetime.now()-timedelta(days=7)).isoformat()
        shoots = await supa_get("shoots",200)
        ideas = await supa_get("ideas",200)
        diary = await supa_get("diary",200)
        projects = await supa_get("projects",200)
        ns = len([s for s in shoots if s.get("created_at","")>week_ago])
        ds = len([s for s in shoots if s.get("status")=="снято" and s.get("created_at","")>week_ago])
        ni = len([i for i in ideas if i.get("created_at","")>week_ago])
        nd = len([d for d in diary if d.get("created_at","")>week_ago])
        ap = len([p for p in projects if p.get("status")!="готово"])
        text = (f"📊 *Итоги недели:*\n\n"
                f"📅 Съёмок добавлено: {ns}\n✅ Съёмок проведено: {ds}\n"
                f"💡 Идей: {ni}\n📓 Записей в дневнике: {nd}\n🔸 Активных проектов: {ap}")
        await q.edit_message_text(text,parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад",callback_data="main")]]))
        return

    await q.edit_message_text("Неизвестная команда", reply_markup=main_kbd())

def main():
    import time
    time.sleep(15)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION | filters.FORWARDED, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("🦀 Rak bot v12 started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
