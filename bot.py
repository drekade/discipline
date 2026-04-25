import os, json, httpx, asyncio, random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GROQ_KEY       = os.environ.get("GROQ_KEY", "")
SUPA_URL       = os.environ.get("SUPA_URL", "")
SUPA_KEY       = os.environ.get("SUPA_KEY", "")

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

SYSTEM = f"""Ты — Рак, личный ассистент Катерины (контент-мейкер, режиссёр, 32 года). Профессиональный, чёткий, с лёгким юмором. Обращайся "Катерина".

ВСЕГДА возвращай JSON с тремя ключами: "reply" (текст ответа), "action" (одно из действий ниже), "data" (объект с полями для action). Никогда не возвращай пустой {{}}. Если ничего не подходит — action="none", reply=осмысленный ответ.

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

6. ДНЕВНИК (action: add_diary) — Катерина рассказывает про свой день: что делала, как встала, когда работала, как себя чувствовала, что было, как день прошёл.
   ПРИМЕРЫ когда ВСЕГДА action=add_diary:
   • "сегодня работала с 12 до 16, в 8 встала" → add_diary
   • "тяжелый день был" → add_diary
   • "снимали урок, потом монтировала" → add_diary
   • "поспала 1.5 часа и вперёд" → add_diary
   • "общалась с людьми, отвечала на вопросы ребёнка" → add_diary
   Любой рассказ с временем/действиями про прожитый день = ДНЕВНИК. НЕ отвечай "Окей!" на такое — сохрани!
   events = что делала (факты, через запятую). thoughts = чувства/мысли если есть.
   mood: хорошо/нейтрально/плохо — определи по тону.

7. ЛИЧНОЕ СОБЫТИЕ (action: add_event) — врач, ветеринар, школа, мероприятие, встреча
   data: {{title, date(YYYY-MM-DD), time, category, notes}}

8. НОВЫЙ ПРОЕКТ (action: add_project)

9. ОЧИСТКА ПОЛЯ (action: clear_field) — "отмени/убери/очисти заметку/ссылку"
   data: {{field: "notes"|"script"|"link", entity: "shoot"|"project"}}

10. ОТВЕТ НА УТОЧНЕНИЕ (action: clarify_reply) — ТОЛЬКО если ТВОЙ ПРОШЛЫЙ reply был вопросом "какая дата?"/"во сколько?"/"где?",
    а Катерина даёт эти недостающие данные одним-двумя словами ("завтра", "в 10", "25 апреля").
    data: {{field_given: "date"|"time"|"location", value: "..."}}

11. ЗАПРОС ИНФОРМАЦИИ (action: query) — Катерина спрашивает что-то по своим данным.
    ПРИМЕРЫ:
    • "какие люди снимались в этом месяце" → intent=list_people, period=month
    • "кто снимался на этой неделе" → intent=list_people, period=week
    • "когда последняя съёмка с олегом" → intent=last_shoot_with_person, params={{person:"олег"}}
    • "сколько съёмок было в апреле" → intent=count_shoots, period=month
    • "что у меня запланировано" / "что завтра" → intent=upcoming, params={{days:7}} или {{days:1}}
    • "съёмки с локомотивом" → intent=list_shoots, params={{project:"локомотив"}}
    • "съёмки в апреле" → intent=list_shoots, period=month
    • "какие у меня проекты" → intent=project_stats
    data: {{intent: "list_people"|"count_shoots"|"list_shoots"|"last_shoot_with_person"|"project_stats"|"upcoming", period: "week"|"month"|"all", params: {{...}}}}
    reply: всегда пиши "Сейчас посмотрю..." — основной текст бот сформирует сам по данным.

12. РАЗГОВОР (action: none) — только короткие междометия и прямые вопросы.
    "привет","дякую","ок","да","нет" — action: none.

ХАРАКТЕР: отвечай на том же языке что Катерина. Поддержи если тяжело. Не навязывайся с вопросами.

ПОСЛЕ СОХРАНЕНИЯ В ДНЕВНИК скажи коротко что записала, можешь мягко спросить как она.

ФОРМАТ — только JSON без markdown:
{{"reply":"текст","action":"none|add_shoot|add_multiple_shoots|delete_shoot|clarify|clarify_reply|clear_field|complete_project|add_idea|add_diary|add_event|add_project|query","data":{{}}}}

data для add_multiple_shoots: {{"shoots":[{{"date":"YYYY-MM-DD","time":"HH:MM","location":"","project":"","people":"","script":"","notes":""}}]}}
data для add_diary: mood(хорошо/нейтрально/плохо), events, thoughts
data для add_event: title, date(YYYY-MM-DD), time, category, notes
data для delete_shoot: shoot_date, shoot_location, shoot_time
data для clear_field: field, entity
data для clarify: partial
data для clarify_reply: field_given, value
data для query: intent, period (опционально), params (опционально)

⚠️ ОБЯЗАТЕЛЬНО: твой ответ — это ВАЛИДНЫЙ JSON в одну строку с тремя ключами reply, action, data. Не пустой {{}}. Не markdown. Не ```. Просто JSON.
ПРИМЕР минимального ответа: {{"reply":"Окей","action":"none","data":{{}}}}
ПРИМЕР для дневника: {{"reply":"Записала. Как настроение?","action":"add_diary","data":{{"mood":"нейтрально","events":"работала с 12 до 16, отвела Лилу в школу","thoughts":""}}}}"""

async def ask_groq(messages):
    groq_messages = [{"role": "system", "content": SYSTEM}]
    for m in messages:
        role = "assistant" if m["role"] == "model" else "user"
        text = "".join(p.get("text","") for p in m.get("parts",[]))
        groq_messages.append({"role": role, "content": text})
    # prefill: заставляем модель продолжить именно с JSON
    groq_messages.append({"role": "assistant", "content": "{"})
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": "openai/gpt-oss-120b", "messages": groq_messages, "temperature": 0.2, "max_tokens": 1500}
        )
        print(f"GROQ status: {r.status_code}")
        data = r.json()
        if "error" in data:
            print(f"GROQ ERROR: {data}")
        if "usage" in data:
            print(f"GROQ usage: {data['usage']}")
        finish_reason = data.get("choices",[{}])[0].get("finish_reason","?")
        print(f"GROQ finish_reason: {finish_reason}")
        raw = data.get("choices",[{}])[0].get("message",{}).get("content","")
        # дописываем { который мы префиллили обратно если модель его не повторила
        raw = raw.strip()
        if not raw.startswith("{"):
            raw = "{" + raw
        raw = raw.replace("```json","").replace("```","").strip()
        print(f"GROQ raw ({len(raw)} chars): {raw}")
        try:
            parsed = json.loads(raw)
            # Детектор пустого / битого ответа
            if not parsed or not isinstance(parsed, dict):
                print(f"GROQ EMPTY/BROKEN: {raw}")
                return {"reply": "Чего-то я завис. Повтори?", "action": "none", "data": {}}
            if "action" not in parsed:
                parsed["action"] = "none"
            if "reply" not in parsed:
                parsed["reply"] = "Окей"
            if "data" not in parsed:
                parsed["data"] = {}
            # Make sure reply doesn't contain raw JSON
            if isinstance(parsed.get("reply"), str) and '{"reply"' in parsed.get("reply",""):
                reply_text = parsed["reply"].split('{"reply"')[0].strip()
                parsed["reply"] = reply_text if reply_text else "Записала!"
            return parsed
        except Exception as e:
            print(f"GROQ PARSE ERROR: {e} | raw: {raw[:300]}")
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

def _parse_people(text):
    """Разбирает поле people в съёмке на отдельные имена."""
    if not text:
        return []
    raw = text.replace(";", ",").replace(" и ", ",").replace(" та ", ",")
    return [p.strip() for p in raw.split(",") if p.strip()]

def _period_filter(items, period):
    """Фильтрует записи по полю date в зависимости от периода."""
    if period == "all" or not period:
        return items
    now = datetime.now()
    if period == "week":
        cutoff = now - timedelta(days=7)
    elif period == "month":
        cutoff = now.replace(day=1)
    else:
        return items
    out = []
    for it in items:
        d = it.get("date","")
        if not d:
            continue
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            if dt >= cutoff:
                out.append(it)
        except:
            pass
    return out

def _period_label(period):
    if period == "week":
        return "за неделю"
    if period == "month":
        now = datetime.now()
        months = ["январь","февраль","март","апрель","май","июнь","июль","август","сентябрь","октябрь","ноябрь","декабрь"]
        return f"за {months[now.month-1]}"
    return "за всё время"

async def run_query(intent, period="month", params=None):
    """Универсальный обработчик запросов — возвращает текстовый ответ."""
    params = params or {}
    shoots = await supa_get("shoots", 500)
    projects = await supa_get("projects", 100)

    if intent == "list_people":
        flt = _period_filter(shoots, period)
        if not flt:
            return f"Съёмок {_period_label(period)} нет."
        # агрегируем людей
        people_stats = {}  # name -> {"count": int, "last": "YYYY-MM-DD"}
        for s in flt:
            for p in _parse_people(s.get("people","")):
                key = p.lower()
                if key not in people_stats:
                    people_stats[key] = {"name": p, "count": 0, "last": ""}
                people_stats[key]["count"] += 1
                d = s.get("date","")
                if d > people_stats[key]["last"]:
                    people_stats[key]["last"] = d
        if not people_stats:
            return f"Имён людей не записано в съёмках {_period_label(period)}."
        # сортировка по убыванию количества
        sorted_p = sorted(people_stats.values(), key=lambda x: -x["count"])
        lines = [f"👥 Люди {_period_label(period)}:\n"]
        for p in sorted_p:
            last = fmt_date(p["last"]) if p["last"] else "?"
            times = "съёмка" if p["count"]==1 else "съёмки" if p["count"]<5 else "съёмок"
            lines.append(f"• {p['name']} — {p['count']} {times}, последняя {last}")
        return "\n".join(lines)

    if intent == "count_shoots":
        flt = _period_filter(shoots, period)
        return f"📊 Съёмок {_period_label(period)}: {len(flt)}"

    if intent == "list_shoots":
        items = shoots
        if params.get("project"):
            q = params["project"].lower()
            items = [s for s in items if q in (s.get("project","") or "").lower()]
        if params.get("location"):
            q = params["location"].lower()
            items = [s for s in items if q in (s.get("location","") or "").lower()]
        if period and period != "all":
            items = _period_filter(items, period)
        if not items:
            return "Ничего не нашла по этому запросу."
        items = sorted(items, key=lambda x: x.get("date",""), reverse=True)[:15]
        lines = [f"📅 Съёмки ({len(items)}):\n"]
        for s in items:
            what = s.get("project","").strip() or s.get("location","?")
            lines.append(f"• {fmt_date(s.get('date',''))} {s.get('time','')} — {what}")
        return "\n".join(lines)

    if intent == "last_shoot_with_person":
        person = (params.get("person") or "").lower()
        if not person:
            return "С кем именно?"
        matched = [s for s in shoots if person in (s.get("people","") or "").lower()]
        if not matched:
            return f"Съёмок с «{params.get('person')}» не нашла."
        matched = sorted(matched, key=lambda x: x.get("date",""), reverse=True)
        last = matched[0]
        what = last.get("project","").strip() or last.get("location","?")
        return f"📅 Последняя съёмка с {params.get('person')} — {fmt_date(last.get('date',''))} {last.get('time','')}, {what}.\nВсего съёмок: {len(matched)}"

    if intent == "project_stats":
        if not projects:
            return "Проектов пока нет."
        lines = ["🎬 Проекты:\n"]
        for p in projects:
            cnt = sum(1 for s in shoots if s.get("project","")==p.get("name",""))
            status = p.get("status","в работе")
            lines.append(f"• {p.get('name','?')} — {cnt} съёмок, {status}")
        return "\n".join(lines)

    if intent == "upcoming":
        days = int(params.get("days", 7))
        today = datetime.now().date()
        cutoff = today + timedelta(days=days)
        items = []
        for s in shoots:
            d = s.get("date","")
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                if today <= dt <= cutoff:
                    items.append(("📷", s, dt))
            except:
                pass
        events = await supa_get("events", 200)
        for e in events:
            d = e.get("date","")
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                if today <= dt <= cutoff:
                    items.append(("📍", e, dt))
            except:
                pass
        if not items:
            return f"На ближайшие {days} {'день' if days==1 else 'дня' if days<5 else 'дней'} ничего не запланировано."
        items.sort(key=lambda x: x[2])
        lines = [f"📌 Что впереди:\n"]
        for icon, it, dt in items:
            title = it.get("project","") or it.get("location","") or it.get("title","")
            lines.append(f"• {icon} {fmt_date(it.get('date',''))} {it.get('time','')} — {title}")
        return "\n".join(lines)

    return "Не поняла запрос. Спроси по-другому?"

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
    # Schedule check-ins (если доступен job_queue)
    if ctx.job_queue is not None:
        try:
            ctx.job_queue.run_repeating(
                lambda ctx: asyncio.create_task(send_checkin(ctx.bot, uid)),
                interval=172800,  # every 2 days
                first=86400,  # first after 1 day
                name=f"checkin_{uid}"
            )
        except Exception as e:
            print(f"JobQueue error: {e}")
    else:
        print("JobQueue unavailable, check-ins disabled")

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
        if action == "query":
            # выполняем запрос и заменяем reply на результат
            intent = data.get("intent","")
            period = data.get("period","month")
            params = data.get("params", {}) or {}
            try:
                reply = await run_query(intent, period, params)
            except Exception as qe:
                print(f"QUERY ERROR: {qe}")
                reply = "Не получилось достать данные 😔"
        elif action not in ("none","clarify","clarify_reply"):
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
            # показываем что снимали (project) вместо локации; если проекта нет — локация как fallback
            what = s.get("project","").strip() or s.get("location","?")
            label = f"{icon} {fmt_date(s.get('date',''))} {s.get('time','')} — {what[:22]}"
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
    print("🦀 Rak bot v19 started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
