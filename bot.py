import os, json, base64, httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8590477703:AAEVFUa4DBUiuvob2iI2Y1sOXetIjauk-n4")
GEMINI_KEY     = os.environ.get("GEMINI_KEY", "AIzaSyARQFS_fEKkDapYiUlbp4oRLBP0dR56U5Y")
SUPA_URL       = os.environ.get("SUPA_URL", "https://btgtgcwbrrnfbctchata.supabase.co")
SUPA_KEY       = os.environ.get("SUPA_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0Z3RnY3dicnJuZmJjdGNoYXRhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MTQ2OTgsImV4cCI6MjA5MjI5MDY5OH0.lyEWFcmsL3GIm0FrEZdGkK2uRSx26cNiBGFvCVsjdsY")

SUPA_H = {
    "apikey": SUPA_KEY,
    "Authorization": f"Bearer {SUPA_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

SYSTEM = """Ты — личный AI-ассистент. Пользователь пишет свободным текстом на русском или украинском.

Пойми сообщение и верни JSON с действием.

ПРАВИЛА:
- Съёмка (дата, место, люди, сценарий) → action: add_shoot. Дату в YYYY-MM-DD. "24 квітня"/"24 апреля" → текущий год.
- Завершение/окончание проекта → action: complete_project
- Новая идея → action: add_idea
- Дневник / настроение / как прошёл день → action: add_diary
- Новый проект → action: add_project
- Вопрос или разговор → action: none

Отвечай ТОЛЬКО валидным JSON без markdown и без пояснений:
{"reply":"дружелюбный ответ на русском","action":"none|add_shoot|complete_project|add_idea|add_diary|add_project","data":{}}

Поля data:
- add_shoot: date, time, location, project, people, script, notes
- complete_project: project_name
- add_idea: title, description, category
- add_diary: mood(хорошо/нейтрально/плохо), events, thoughts
- add_project: name, description"""

async def ask_gemini(text, image_b64=None):
    parts = []
    if image_b64:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})
    parts.append({"text": text or "Опиши что на фото и предложи куда сохранить"})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, json=payload)
        data = r.json()
        raw = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
        raw = raw.strip().replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(raw)
        except:
            return {"reply": raw, "action": "none", "data": {}}

async def supa_get(table, limit=10):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{SUPA_URL}/rest/v1/{table}?order=created_at.desc&limit={limit}", headers=SUPA_H)
        return r.json() if r.status_code == 200 else []

async def supa_insert(table, data):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{SUPA_URL}/rest/v1/{table}", headers=SUPA_H, json=data)
        return r.status_code in (200, 201)

async def supa_update(table, field, value, data):
    async with httpx.AsyncClient() as c:
        r = await c.patch(f"{SUPA_URL}/rest/v1/{table}?{field}=eq.{value}", headers=SUPA_H, json=data)
        return r.status_code in (200, 204)

async def apply_action(action, data, image_b64=None):
    today = datetime.now().strftime("%Y-%m-%d")
    months = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]
    today_ru = f"{datetime.now().day} {months[datetime.now().month-1]} {datetime.now().year}"

    if action == "add_shoot":
        await supa_insert("shoots", {
            "date": data.get("date", today),
            "time": data.get("time", ""),
            "location": data.get("location", ""),
            "project": data.get("project", ""),
            "people": data.get("people", ""),
            "script": data.get("script", ""),
            "notes": data.get("notes", ""),
            "status": "не снято"
        })
    elif action == "complete_project":
        name = data.get("project_name", "")
        projects = await supa_get("projects", 50)
        for p in projects:
            if name.lower() in p.get("name", "").lower():
                await supa_update("projects", "id", p["id"], {"status": "готово"})
                break
    elif action == "add_idea":
        img_url = f"data:image/jpeg;base64,{image_b64}" if image_b64 else None
        await supa_insert("ideas", {
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "category": data.get("category", "Идея"),
            "image_url": img_url
        })
    elif action == "add_diary":
        await supa_insert("diary", {
            "date": today_ru,
            "mood": data.get("mood", "нейтрально"),
            "events": data.get("events", ""),
            "thoughts": data.get("thoughts", "")
        })
    elif action == "add_project":
        await supa_insert("projects", {
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "status": "в работе"
        })

def kbd():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Съёмки", callback_data="shoots"),
         InlineKeyboardButton("🎬 Проекты", callback_data="projects")],
        [InlineKeyboardButton("💡 Идеи", callback_data="ideas"),
         InlineKeyboardButton("📓 Дневник", callback_data="diary")],
        [InlineKeyboardButton("📊 Итоги недели", callback_data="week")]
    ])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой личный дневник-ассистент 🙂\n\n"
        "Пиши мне как другу — я сам разберу и сохраню куда надо.\n\n"
        "Например:\n"
        "• *съёмки 15 мая в парке Горького, Котенко и Таня, 12:00*\n"
        "• *закончила проект Реклама*\n"
        "• *идея: серия видео про утро*\n"
        "• *сегодня хороший день, сняла урок 4*\n\n"
        "Или прикрепи фото 📎\n\nИспользуй кнопки для просмотра 👇",
        parse_mode="Markdown",
        reply_markup=kbd()
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text or msg.caption or ""
    image_b64 = None

    if msg.photo:
        photo = msg.photo[-1]
        file = await ctx.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()
        image_b64 = base64.b64encode(bytes(img_bytes)).decode()

    if not text and not image_b64:
        await msg.reply_text("Напиши что-нибудь или прикрепи фото 🙂")
        return

    thinking = await msg.reply_text("⏳")

    try:
        result = await ask_gemini(text, image_b64)
        reply = result.get("reply", "Записала!")
        action = result.get("action", "none")
        data = result.get("data", {})

        if action != "none":
            await apply_action(action, data, image_b64 if action == "add_idea" else None)

        await thinking.delete()
        await msg.reply_text(reply, reply_markup=kbd())
    except Exception as e:
        await thinking.delete()
        await msg.reply_text(f"Что-то пошло не так 😔 Попробуй ещё раз\n{str(e)[:100]}")

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cb = q.data

    if cb == "shoots":
        items = await supa_get("shoots", 5)
        if not items:
            text = "📅 Съёмок пока нет\n\nНапиши например: *съёмки 15 мая в парке Горького*"
        else:
            lines = ["📅 *Ближайшие съёмки:*\n"]
            for s in items:
                icon = "✅" if s.get("status") == "снято" else "🔸"
                line = f"{icon} {s.get('date','')} {s.get('time','')} — {s.get('location','?')}"
                if s.get("project"): line += f"\n   🎬 {s['project']}"
                if s.get("people"): line += f"\n   👥 {s['people']}"
                if s.get("script"): line += f"\n   📄 {s['script']}"
                lines.append(line)
            text = "\n\n".join(lines)

    elif cb == "projects":
        items = await supa_get("projects", 10)
        if not items:
            text = "🎬 Проектов пока нет\n\nНапиши: *новый проект Реклама*"
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
            text = "💡 Идей пока нет\n\nНапиши: *идея: серия видео про утро*"
        else:
            lines = ["💡 *Идеи:*\n"]
            for i in items:
                lines.append(f"• *{i.get('title','')}*")
                if i.get("description"): lines.append(f"  {i['description'][:150]}")
            text = "\n".join(lines)

    elif cb == "diary":
        items = await supa_get("diary", 3)
        if not items:
            text = "📓 Записей пока нет\n\nНапиши: *сегодня хороший день, закончила съёмку*"
        else:
            moods = {"хорошо": "😊", "нейтрально": "😐", "плохо": "😔"}
            lines = ["📓 *Последние записи:*\n"]
            for d in items:
                me = moods.get(d.get("mood", "нейтрально"), "😐")
                lines.append(f"{me} *{d.get('date','')}*")
                if d.get("events"): lines.append(f"  {d['events'][:150]}")
                if d.get("thoughts"): lines.append(f"  💭 {d['thoughts'][:100]}")
            text = "\n\n".join(lines)

    elif cb == "week":
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        shoots   = await supa_get("shoots", 100)
        ideas    = await supa_get("ideas", 100)
        diary    = await supa_get("diary", 100)
        projects = await supa_get("projects", 100)

        ns = len([s for s in shoots  if s.get("created_at","") > week_ago])
        ds = len([s for s in shoots  if s.get("status")=="снято" and s.get("created_at","") > week_ago])
        ni = len([i for i in ideas   if i.get("created_at","") > week_ago])
        nd = len([d for d in diary   if d.get("created_at","") > week_ago])
        ap = len([p for p in projects if p.get("status") != "готово"])

        text = (f"📊 *Итоги недели:*\n\n"
                f"📅 Съёмок добавлено: {ns}\n"
                f"✅ Съёмок проведено: {ds}\n"
                f"💡 Идей добавлено: {ni}\n"
                f"📓 Записей в дневнике: {nd}\n"
                f"🔸 Активных проектов: {ap}")
    else:
        text = "Неизвестная команда"

    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kbd())
    except:
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kbd())

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.CAPTION, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("🤖 Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
