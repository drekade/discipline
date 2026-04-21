import os, json, base64, httpx, asyncio
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

SYSTEM = f"""Ты — Рак, личный ассистент Катерины (контент-мейкер, режиссёр). Профессиональный, чёткий, с лёгким юмором. Отвечаешь коротко. Обращайся к пользователю "Катерина".

СЕГОДНЯ: {TODAY} ({TODAY_NICE})
ТЕКУЩИЙ ГОД: {YEAR}

УКРАИНСКИЕ МЕСЯЦЫ: січень=01 лютий=02 березень=03 квітень=04 травень=05 червень=06 липень=07 серпень=08 вересень=09 жовтень=10 листопад=11 грудень=12

ЛОГИКА РАСПОЗНАВАНИЯ:

1. НЕСКОЛЬКО СЪЁМОК (action: add_multiple_shoots) — если в сообщении несколько блоков с датами/местами.
   Каждый блок — отдельная съёмка. Возвращай массив shoots[].
   Игнорируй @ники, это просто теги людей.
   
2. ОДНА СЪЁМКА (action: add_shoot) — одна дата/место/люди.
   Если нет даты — action=clarify, спроси только дату.

3. ЗАМЕТКА К СЪЁМКЕ (action: add_note) — "к съёмке X заметка/сценарий/ссылка"
   data: {{shoot_date, shoot_location, note, script}}

4. ЗАВЕРШЕНИЕ ПРОЕКТА (action: complete_project) — "закончила/завершила проект X"
5. ИДЕЯ (action: add_idea) — "идея:", "ідея:"
6. ДНЕВНИК (action: add_diary) — настроение, как прошёл день
7. НОВЫЙ ПРОЕКТ (action: add_project) — "новый проект"
8. РАЗГОВОР (action: none) — приветствия, болтовня, эмоции без данных для записи.
   "привет","привіт","як справи","дякую","окей","ок","нет","да" — ВСЕГДА action: none!

ХАРАКТЕР: отвечай на том же языке что Катерина. Приветствия — тепло. Подтверждай съёмки кратким списком.

ФОРМАТ — только JSON без markdown:
{{"reply":"текст","action":"none|add_shoot|add_multiple_shoots|add_note|clarify|complete_project|add_idea|add_diary|add_project","data":{{}}}}

data для add_shoot: date(YYYY-MM-DD), time(HH:MM), location, project, people, script, notes
data для add_multiple_shoots: {{"shoots":[{{"date":"YYYY-MM-DD","time":"HH:MM","location":"","project":"","people":"","script":"","notes":""}}]}}
data для add_note: shoot_date(YYYY-MM-DD), shoot_location, note, script
data для complete_project: project_name
data для add_idea: title, description, category
data для add_diary: mood(хорошо/нейтрально/плохо), events, thoughts
data для add_project: name, description"""

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
            json={"model": "llama-3.3-70b-versatile", "messages": groq_messages, "temperature": 0.2, "max_tokens": 1000}
        )
        data = r.json()
        print(f"GROQ STATUS: {r.status_code}")
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        raw = raw.strip().replace("```json","").replace("```","").strip()
        print(f"GROQ RAW: {raw[:300]}")
        try:
            return json.loads(raw)
        except:
            return {"reply": raw, "action": "none", "data": {}}

async def supa_get(table, limit=100):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{SUPA_URL}/rest/v1/{table}?order=created_at.desc&limit={limit}", headers=SUPA_H)
        return r.json() if r.status_code == 200 else []

async def supa_insert(table, data):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{SUPA_URL}/rest/v1/{table}", headers=SUPA_H, json=data)
        print(f"SUPA {table}: {r.status_code} {r.text[:100]}")
        return r.status_code in (200, 201)

async def supa_update(table, field, value, data):
    async with httpx.AsyncClient() as c:
        r = await c.patch(f"{SUPA_URL}/rest/v1/{table}?{field}=eq.{value}", headers=SUPA_H, json=data)
        return r.status_code in (200, 204)

async def apply_action(action, data):
    today = datetime.now().strftime("%Y-%m-%d")
    months = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]
    today_ru = f"{datetime.now().day} {months[datetime.now().month-1]} {datetime.now().year}"

    if action == "add_shoot":
        return await supa_insert("shoots", {
            "date": data.get("date", today), "time": data.get("time",""),
            "location": data.get("location",""), "project": data.get("project",""),
            "people": data.get("people",""), "script": data.get("script",""),
            "notes": data.get("notes",""), "status": "не снято"
        })

    elif action == "add_multiple_shoots":
        shoots = data.get("shoots", [])
        saved = 0
        for s in shoots:
            ok = await supa_insert("shoots", {
                "date": s.get("date", today), "time": s.get("time",""),
                "location": s.get("location",""), "project": s.get("project",""),
                "people": s.get("people",""), "script": s.get("script",""),
                "notes": s.get("notes",""), "status": "не снято"
            })
            if ok: saved += 1
        return saved

    elif action == "add_note":
        # Find shoot and update it
        shoots = await supa_get("shoots", 100)
        for s in shoots:
            date_match = s.get("date","") == data.get("shoot_date","")
            loc = data.get("shoot_location","").lower()
            loc_match = loc in s.get("location","").lower() if loc else True
            if date_match or loc_match:
                update_data = {}
                if data.get("note"): update_data["notes"] = data["note"]
                if data.get("script"): update_data["script"] = data["script"]
                if update_data:
                    await supa_update("shoots", "id", s["id"], update_data)
                    return True
        return False

    elif action == "complete_project":
        projects = await supa_get("projects", 50)
        for p in projects:
            if data.get("project_name","").lower() in p.get("name","").lower():
                await supa_update("projects","id",p["id"],{"status":"готово"})
                return True

    elif action == "add_idea":
        return await supa_insert("ideas",{
            "title":data.get("title",""),"description":data.get("description",""),
            "category":data.get("category","Идея"),"image_url":None
        })

    elif action == "add_diary":
        return await supa_insert("diary",{
            "date":today_ru,"mood":data.get("mood","нейтрально"),
            "events":data.get("events",""),"thoughts":data.get("thoughts","")
        })

    elif action == "add_project":
        return await supa_insert("projects",{
            "name":data.get("name",""),"description":data.get("description",""),"status":"в работе"
        })
    return False

def kbd():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Съёмки", callback_data="shoots"),
         InlineKeyboardButton("🎬 Проекты", callback_data="projects")],
        [InlineKeyboardButton("💡 Идеи", callback_data="ideas"),
         InlineKeyboardButton("📓 Дневник", callback_data="diary")],
        [InlineKeyboardButton("📊 Итоги недели", callback_data="week")]
    ])

def get_history(uid):
    if uid not in conversations:
        conversations[uid] = []
    return conversations[uid]

def add_history(uid, role, text):
    h = get_history(uid)
    h.append({"role": role, "parts": [{"text": text or "—"}]})
    if len(h) > 12:
        conversations[uid] = h[-12:]

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conversations[uid] = []
    await update.message.reply_text(
        "Привет, Катерина! Я Рак — твой личный ассистент 🦀\n\n"
        "Пиши как угодно — русский, украинский, вперемешку.\n"
        "Можешь пересылать сообщения от координатора — разберу все съёмки сразу.\n\n"
        "Записываю съёмки, идеи, проекты и дневник 🙂",
        reply_markup=kbd()
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    text = msg.text or msg.caption or ""

    if not text:
        await msg.reply_text("Напиши что-нибудь 🙂")
        return

    add_history(uid, "user", text)
    thinking = await msg.reply_text("⏳")

    try:
        result = await ask_groq(get_history(uid))
        reply = result.get("reply", "Окей!")
        action = result.get("action", "none")
        data = result.get("data", {})
        add_history(uid, "model", reply)

        saved = False
        if action not in ("none", "clarify"):
            saved = await apply_action(action, data)

        await thinking.delete()

        # Build confirmation
        if action == "add_shoot" and saved:
            details = []
            if data.get("date"): details.append(f"📅 {data['date']}")
            if data.get("time"): details.append(f"🕐 {data['time']}")
            if data.get("location"): details.append(f"📍 {data['location']}")
            if data.get("people"): details.append(f"👥 {data['people']}")
            if details: reply += "\n\n" + "\n".join(details)

        elif action == "add_multiple_shoots" and saved:
            reply += f"\n\nЗаписала {saved} съёмок ✓"

        elif action == "add_note" and saved:
            reply += " ✓"

        show_kbd = action not in ("none", "clarify")
        await msg.reply_text(reply, reply_markup=kbd() if show_kbd else None)

    except Exception as e:
        await thinking.delete()
        print(f"ERROR: {e}")
        await msg.reply_text("Что-то пошло не так 😔 Попробуй ещё раз")

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cb = q.data

    if cb == "shoots":
        items = await supa_get("shoots", 15)
        if not items:
            text = "📅 Съёмок пока нет"
        else:
            lines = ["📅 *Съёмки:*\n"]
            for s in sorted(items, key=lambda x: x.get("date","") or ""):
                icon = "✅" if s.get("status") == "снято" else "🔸"
                line = f"{icon} *{s.get('date','')}*"
                if s.get("time"): line += f" {s['time']}"
                line += f" — {s.get('location','?')}"
                if s.get("project"): line += f"\n   🎬 {s['project']}"
                if s.get("people"): line += f"\n   👥 {s['people']}"
                if s.get("script"): line += f"\n   📄 {s['script']}"
                if s.get("notes"): line += f"\n   📝 {s['notes'][:80]}"
                lines.append(line)
            text = "\n\n".join(lines)

    elif cb == "projects":
        items = await supa_get("projects", 20)
        if not items:
            text = "🎬 Проектов пока нет"
        else:
            lines = ["🎬 *Проекты:*\n"]
            for p in items:
                icon = "✅" if p.get("status") == "готово" else "🔸"
                lines.append(f"{icon} *{p.get('name','')}* — {p.get('status','в работе')}")
                if p.get("description"): lines.append(f"   {p['description']}")
            text = "\n".join(lines)

    elif cb == "ideas":
        items = await supa_get("ideas", 5)
        if not items:
            text = "💡 Идей пока нет"
        else:
            lines = ["💡 *Идеи:*\n"]
            for i in items:
                lines.append(f"• *{i.get('title','')}*")
                if i.get("description"): lines.append(f"  {i['description'][:150]}")
            text = "\n".join(lines)

    elif cb == "diary":
        items = await supa_get("diary", 3)
        if not items:
            text = "📓 Записей пока нет"
        else:
            moods = {"хорошо":"😊","нейтрально":"😐","плохо":"😔"}
            lines = ["📓 *Последние записи:*\n"]
            for d in items:
                me = moods.get(d.get("mood","нейтрально"),"😐")
                lines.append(f"{me} *{d.get('date','')}*")
                if d.get("events"): lines.append(f"  {d['events'][:150]}")
                if d.get("thoughts"): lines.append(f"  💭 {d['thoughts'][:100]}")
            text = "\n\n".join(lines)

    elif cb == "week":
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        shoots   = await supa_get("shoots", 200)
        ideas    = await supa_get("ideas", 200)
        diary    = await supa_get("diary", 200)
        projects = await supa_get("projects", 200)
        ns = len([s for s in shoots if s.get("created_at","") > week_ago])
        ds = len([s for s in shoots if s.get("status")=="снято" and s.get("created_at","") > week_ago])
        ni = len([i for i in ideas if i.get("created_at","") > week_ago])
        nd = len([d for d in diary if d.get("created_at","") > week_ago])
        ap = len([p for p in projects if p.get("status") != "готово"])
        text = (f"📊 *Итоги недели:*\n\n"
                f"📅 Съёмок добавлено: {ns}\n"
                f"✅ Съёмок проведено: {ds}\n"
                f"💡 Идей: {ni}\n"
                f"📓 Записей в дневнике: {nd}\n"
                f"🔸 Активных проектов: {ap}")
    else:
        text = "Неизвестная команда"

    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kbd())
    except:
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kbd())

def main():
    import time
    time.sleep(15)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION | filters.FORWARDED, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("🦀 Rak bot v5 started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
