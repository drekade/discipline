import os, json, httpx, asyncio, random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, BotCommand, MenuButtonCommands
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GROQ_KEY = os.environ.get("GROQ_KEY", "")
SUPA_URL = os.environ.get("SUPA_URL", "")
SUPA_KEY = os.environ.get("SUPA_KEY", "")
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
last_checkin = {}

SYSTEM = f"""Ты — Рак, личный ассистент Катерины (контент-мейкер, режиссёр, 32 года). Профессиональный, чёткий, с лёгким юмором. Обращайся "Катерина".\nВСЕГДА возвращай JSON с тремя ключами: "reply" (текст ответа), "action" (одно из действий ниже), "data" (параметры).
СЕГОДНЯ: {TODAY} ({TODAY_NICE})
ТЕКУЩИЙ ГОД: {YEAR}
УКРАИНСКИЕ МЕСЯЦЫ: січень=01 лютий=02 березень=03 квітень=04 травень=05 червень=06 липень=07 серпень=08 вересень=09 жовтень=10 листопад=11 грудень=12

ЛОГИКА РАСПОЗНАВАНИЯ:
1. НЕСКОЛЬКО СЪЁМОК (action: add_multiple_shoots) — несколько блоков с датами/местами.
   Каждый блок — отдельная съёмка. Массив shoots[]. Игнорируй @ники и теги.
   ВАЖНО: если в сообщении 2+ даты (числа месяца или дни недели) с разными локациями/описаниями — это ВСЕГДА add_multiple_shoots.
   Дни недели тоже считаются датами: середа=среда, п\'ятниця=пятница, субота=суббота, неділя=воскресенье.\nКаждая съёмка: date, time, location, project, people, notes (всё остальное что не вошло).\n2. ОДНА СЪЁМКА (action: add_shoot) — есть явная локация + желательно дата.\nЕсли есть ЛОКАЦИЯ но нет ДАТЫ → action=clarify, data.partial = {{location, time, project, people}}\nЕсли нет локации — это не съёмка.\n3. УДАЛЕНИЕ СЪЁМКИ (action: delete_shoot) — "удали съёмку X"\ndata: {{shoot_date, shoot_location, shoot_time}}\n4. ЗАВЕРШЕНИЕ ПРОЕКТА (action: complete_project) — "закончила/завершила проект X"\n5. ИДЕЯ (action: add_idea) — "идея:", "ідея:"\ndata: {{"title": "суть идеи одной фразой", "description": "детали если есть", "category": "Идея"}}\n6. ДНЕВНИК (action: add_diary) — Катерина рассказывает про свой день.\nПРИМЕРЫ когда ВСЕГДА action=add_diary:\n• "сегодня работала с 12 до 16, в 8 встала" → add_diary\n• "тяжелый день был" → add_diary\n• "снимали урок, потом монтировала" → add_diary\nЛюбой рассказ с временем/действиями про прожитый день = ДНЕВНИК.\nevents = что делала (факты). thoughts = чувства/мысли если есть.\nmood: хорошо/нейтрально/плохо — определи по тону.\n7. ЛИЧНОЕ СОБЫТИЕ (action: add_event) — врач, ветеринар, школа, мероприятие, встреча\ndata: {{title, date(YYYY-MM-DD), time, category, notes}}\n8. НОВЫЙ ПРОЕКТ (action: add_project)\n9. ТЕМА ПРОЕКТА (action: update_topic) — "сняла тему X", "смонтировала тему Y", "тема Z готова"\ndata: {{"topic": "название или номер темы", "project": "проект если упомянут", "stage": "стадия которую отмечаем"}}\n10. ОТМЕНА СЪЁМКИ (action: cancel_shoot) — "съёмка такого-то числа отменилась", с причиной или без.\ndata: {{"date": "YYYY-MM-DD", "location": "если есть", "reason": "причина если указана"}}\n11. СЦЕНАРИЙ БЕЗ СЪЁМКИ (action: add_script) — ссылка + слово "сценарий" без явной даты И локации.\nСоздаём съёмку-заготовку: дата пустая, локация "?", статус "не снято".\ndata: {{"url": "https://...", "project": "проект если упомянут", "title": "о чём сценарий одной фразой"}}\n12. ОЧИСТКА ПОЛЯ (action: clear_field) — "отмени/убери/очисти заметку/ссылку"\ndata: {{field: "notes"|"script"|"link", entity: "shoot"|"project"}}\n13. ОТВЕТ НА УТОЧНЕНИЕ (action: clarify_reply) — ТОЛЬКО если твой прошлый reply был вопросом
    data: {{field_given: "date"|"time"|"location", value: "..."}}

14. ЗАПРОС ИНФОРМАЦИИ (action: query)
    ПРИМЕРЫ:
    • "какие люди снимались в этом месяце" → intent=list_people, period=month
    • "когда последняя съёмка с олегом" → intent=last_shoot_with_person, params={{person:"олег"}}
    • "что у меня запланировано" → intent=upcoming, params={{days:7}}
    • "съёмки с локомотивом" → intent=list_shoots, params={{project:"локомотив"}}
    data: {{intent: "list_people"|"count_shoots"|"list_shoots"|"last_shoot_with_person"|"project_stats"|"upcoming", period, params}}
    reply: всегда пиши "Сейчас посмотрю..."

15. РАЗГОВОР (action: none) — только короткие междометия и прямые вопросы.

ХАРАКТЕР: отвечай на том же языке что Катерина. Поддержи если тяжело.
ФОРМАТ — только JSON без markdown:
{{"reply":"текст","action":"none|add_shoot|add_multiple_shoots|delete_shoot|cancel_shoot|clarify|clarify_reply|clear_field|complete_project|add_idea|add_diary|add_event|add_project|add_script|update_topic|query","data":{{}}}}
data для add_multiple_shoots: {{"shoots":[{{"date":"YYYY-MM-DD","time":"HH:MM","location":"","project":"","people":"","notes":""}}]}}
data для add_diary: mood(хорошо/нейтрально/плохо), events, thoughts
data для add_event: title, date(YYYY-MM-DD), time, category, notes
data для delete_shoot: shoot_date, shoot_location, shoot_time
data для clear_field: field, entity
data для clarify: partial
data для clarify_reply: field_given, value
data для query: intent, period (опционально), params (опционально)
data для add_idea: title, description, category
data для add_script: url, title, project
data для update_topic: topic, project, stage
data для cancel_shoot: date, location, reason
ОБЯЗАТЕЛЬНО: твой ответ — это ВАЛИДНЫЙ JSON в одну строку.
ПРИМЕР минимального ответа: {{"reply":"Окей","action":"none","data":{{}}}}
ПРИМЕР для дневника: {{"reply":"Записала. Как настроение?","action":"add_diary","data":{{"mood":"нейтрально","events":"работала с 12 до 16","thoughts":""}}}}"""


async def ask_groq(messages):
    groq_messages = [{"role": "system", "content": SYSTEM}]
    for m in messages:
        role = "assistant" if m["role"] == "model" else "user"
        text = "".join(p.get("text","") for p in m.get("parts",[]))
        groq_messages.append({"role": role, "content": text})
    groq_messages.append({"role": "assistant", "content": "{"})
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": "openai/gpt-oss-120b", "messages": groq_messages, "temperature": 0.2, "max_tokens": 800}
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
    raw = raw.strip()
    if not raw.startswith("{"):
        raw = "{" + raw
    raw = raw.replace("```json","").replace("```","").strip()
    print(f"GROQ raw ({len(raw)} chars): {raw}")
    try:
        parsed = json.loads(raw)
        if not parsed or not isinstance(parsed, dict):
            return {"reply": "Чего-то я завис. Повтори?", "action": "none", "data": {}}
        if "action" not in parsed: parsed["action"] = "none"
        if "reply" not in parsed: parsed["reply"] = "Окей"
        if "data" not in parsed: parsed["data"] = {}
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


async def supa_insert(table, data, return_id=False):
    headers = dict(SUPA_H)
    if return_id:
        headers["Prefer"] = "return=representation"
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{SUPA_URL}/rest/v1/{table}", headers=headers, json=data)
        print(f"INSERT {table}: {r.status_code} {r.text[:80]}")
        if r.status_code in (200, 201):
            if return_id:
                try:
                    arr = r.json()
                    if isinstance(arr, list) and arr:
                        return arr[0].get("id")
                except:
                    pass
            return True
        return False if not return_id else None


async def supa_update(table, field, value, data):
    async with httpx.AsyncClient() as c:
        r = await c.patch(f"{SUPA_URL}/rest/v1/{table}?{field}=eq.{value}", headers=SUPA_H, json=data)
        return r.status_code in (200, 204)


async def supa_delete(table, field, value):
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{SUPA_URL}/rest/v1/{table}?{field}=eq.{value}", headers=SUPA_H)
        return r.status_code in (200, 204)


def _parse_people(text):
    if not text:
        return []
    raw = text.replace(";", ",").replace(" и ", ",").replace(" та ", ",")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _period_filter(items, period):
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
    params = params or {}
    shoots = await supa_get("shoots", 500)
    projects = await supa_get("projects", 100)

    if intent == "list_people":
        flt = _period_filter(shoots, period)
        if not flt:
            return f"Съёмок {_period_label(period)} нет."
        people_stats = {}
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
            lines.append(f"• {fmt_date(s.get('date',''))} {(s.get('time') or '')} — {what}")
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
        return f"📅 Последняя съёмка с {params.get('person')} — {fmt_date(last.get('date',''))} {(last.get('time') or '')} — {what}"

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
                    items.append(("📅", s, dt))
            except:
                pass
        events = await supa_get("events", 200)
        for e in events:
            d = e.get("date","")
            try:
                dt = datetime.strptime(d, "%Y-%m-%d").date()
                if today <= dt <= cutoff:
                    items.append(("🗓", e, dt))
            except:
                pass
        if not items:
            return f"На ближайшие {days} {'день' if days==1 else 'дня' if days<5 else 'дней'} ничего не запланировано."
        items.sort(key=lambda x: x[2])
        lines = ["🗓 Что впереди:\n"]
        for icon, it, dt in items:
            title = it.get("project","") or it.get("location","") or it.get("title","")
            lines.append(f"• {icon} {fmt_date(it.get('date',''))} {it.get('time','')} — {title}")
        return "\n".join(lines)

    return "Не поняла запрос. Спроси по-другому?"


async def apply_action(action, data):
    today = datetime.now().strftime("%Y-%m-%d")

    if action == "add_shoot":
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

    elif action == "cancel_shoot":
        shoots = await supa_get("shoots", 100)
        date_val = data.get("date","")
        loc_val = (data.get("location","") or "").lower()
        reason = (data.get("reason","") or "").strip()
        for s in shoots:
            date_match = not date_val or s.get("date","") == date_val
            loc_match = not loc_val or loc_val in (s.get("location","") or "").lower() or loc_val in (s.get("project","") or "").lower()
            if date_match and loc_match and s.get("status") != "отменена":
                notes = (s.get("notes") or "").strip()
                if reason:
                    import re as _re
                    notes = _re.sub(r"[\u2715] причина отмены: [^\n]+\n?", "", notes).strip()
                    notes = (notes + "\n" if notes else "") + f"\u2715 причина отмены: {reason}"
                return await supa_update("shoots","id",s["id"],{"status":"отменена","notes":notes})
        return False

    elif action == "clear_field":
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
            date_match = not data.get("shoot_date") or s.get("date","") == data.get("shoot_date")
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
        title = (data.get("title") or data.get("idea") or data.get("name") or "").strip()
        desc = (data.get("description") or data.get("text") or data.get("content") or "").strip()
        if not title and desc:
            title, desc = desc, ""
        if not title:
            print(f"SKIP add_idea: no title in data={data}")
            return False
        return await supa_insert("ideas",{"title":title,"description":desc,"category":data.get("category","Идея"),"image_url":None})

    elif action == "add_diary":
        return await supa_insert("diary",{"date":today,"mood":data.get("mood","нейтрально"),"events":data.get("events",""),"thoughts":data.get("thoughts","")})

    elif action == "add_event":
        return await supa_insert("events",{"title":data.get("title",""),"date":data.get("date",today),"time":data.get("time",""),"category":data.get("category",""),"notes":data.get("notes","")})

    elif action == "add_project":
        return await supa_insert("projects",{"name":data.get("name",""),"description":data.get("description",""),"status":"в работе"})

    elif action == "add_script":
        url = (data.get("url") or "").strip()
        if not url:
            return False
        project = (data.get("project") or "").strip()
        title = (data.get("title") or "").strip()
        shoot_title = title if title else "Сценарий без названия"
        shoot_data = {
            "date": None, "time": None, "location": "?",
            "project": project or shoot_title, "people": "",
            "status": "не снято", "script": url,
            "notes": "⏳ не запланировано — дата и место не известны"
        }
        shoot_id = await supa_insert("shoots", shoot_data, return_id=True)
        await supa_insert("scripts", {"title": f"Сценарий — {shoot_title}", "link": url, "tag": "другое"})
        return bool(shoot_id)

    elif action == "update_topic":
        topic_name = (data.get("topic") or "").strip()
        proj_name = (data.get("project") or "").strip()
        stage_name = (data.get("stage") or "").strip()
        if not topic_name:
            return False
        topics_r = await supa_get("topics", 50)
        if proj_name:
            projs = await supa_get("projects", 20)
            proj_match = next((p for p in projs if proj_name.lower() in (p.get("name") or "").lower()), None)
            if proj_match:
                topics_r = [t for t in topics_r if t.get("project_id") == proj_match.get("id")]
        topic = next((t for t in topics_r if topic_name.lower() in (t.get("title") or "").lower()), None)
        if not topic:
            return False
        stages = topic.get("stages") or []
        updated = False
        for st in stages:
            if isinstance(st, dict) and stage_name.lower() in (st.get("name") or "").lower():
                st["done"] = True
                updated = True
                break
        if not updated and stages:
            for st in stages:
                if isinstance(st, dict) and not st.get("done"):
                    st["done"] = True
                    updated = True
                    break
        if updated:
            return await supa_update("topics","id",topic["id"],{"stages":stages})
        return False

    return False


def fmt_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m")
    except:
        return date_str or ""


def append_log(old_text, new_text):
    new_text = (new_text or "").strip()
    if not new_text:
        return old_text or ""
    header = f"━━ {datetime.now().strftime('%d.%m.%Y')} ━━"
    new_block = f"{header}\n{new_text}"
    old_text = (old_text or "").strip()
    if not old_text:
        return new_block
    return f"{new_block}\n\n{old_text}"


def main_kbd():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Съёмки", callback_data="shoots"),
         InlineKeyboardButton("🎬 Проекты", callback_data="projects")],
        [InlineKeyboardButton("💡 Идеи", callback_data="ideas"),
         InlineKeyboardButton("📓 Дневник", callback_data="diary")],
        [InlineKeyboardButton("🗓 События", callback_data="events"),
         InlineKeyboardButton("📊 Итоги", callback_data="week")]
    ])


def reply_kbd():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🏠 Сегодня"), KeyboardButton("📅 Съёмки")],
        [KeyboardButton("🎬 Проекты"), KeyboardButton("💡 Идеи")],
        [KeyboardButton("📓 Дневник"), KeyboardButton("📊 Итоги")]
    ], resize_keyboard=True, is_persistent=True)


def proj_detail_kbd_with_figma(proj_id, status, has_figma):
    toggle_label = "Вернуть в работу" if status == "готово" else "✅ Завершить"
    figma_label = "🎨 Открыть Figma" if has_figma else "🎨 Добавить Figma"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data=f"toggle_proj_{proj_id}")],
        [InlineKeyboardButton("🔗 Добавить ссылку", callback_data=f"addlink_proj_{proj_id}"),
         InlineKeyboardButton("📝 Добавить заметку", callback_data=f"addnote_proj_{proj_id}")],
        [InlineKeyboardButton(figma_label, callback_data=f"figma_proj_{proj_id}")],
        [InlineKeyboardButton("◀️ К проектам", callback_data="projects")]
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
    lines = [f"📅 {s.get('date','')} {(s.get('time') or '')}"]
    if s.get("project"): lines.append(f"🎬 {s['project']}")
    if s.get("location"): lines.append(f"📍 {s['location']}")
    if s.get("people"): lines.append(f"👥 {s['people']}")
    if s.get("notes"): lines.append(f"📝 {s['notes']}")
    if s.get("script"): lines.append(f"🔗 {s['script']}")
    lines.append(f"\nСтатус: {'✅ снято' if s.get('status')=='снято' else '🔸 не снято'}")
    return "\n".join(lines)


def render_project(p, shoots, tasks):
    lines = [f"🎬 {p.get('name','')}",
             f"Статус: {'✅ готово' if p.get('status')=='готово' else '🔸 в работе'}"]
    if p.get("description"): lines.append(f"\n{p['description']}")
    if p.get("link"): lines.append(f"🔗 {p['link']}")
    if p.get("notes"): lines.append(f"📝 {p['notes']}")
    proj_tasks = [t for t in tasks if t.get("project_id") == p.get("id")]
    if proj_tasks:
        lines.append(f"\n📋 Задачи:")
        for t in proj_tasks:
            icon = "✅" if t.get("status")=="готово" else "🔄" if t.get("status")=="в работе" else "⭕"
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
    phrases = ["Как ты сегодня, Катерина? 😊", "Катерина, как дела? Всё в порядке?", "Как прошёл день?"]
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
        "Записываю съёмки, идеи, проекты, события и дневник.\n"
        "Кнопки внизу — быстрые переходы.\n"
        "Префиксы: «сценарий: <ссылка>», «референс: <ссылка>», «фигма: <ссылка>»",
        reply_markup=reply_kbd()
    )
    if ctx.job_queue is not None:
        try:
            ctx.job_queue.run_repeating(
                lambda ctx: asyncio.create_task(send_checkin(ctx.bot, uid)),
                interval=172800, first=86400, name=f"checkin_{uid}"
            )
        except Exception as e:
            print(f"JobQueue error: {e}")
    else:
        print("JobQueue unavailable, check-ins disabled")


async def cmd_today_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    update.message.text = "🏠 Сегодня"
    await handle_message(update, ctx)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🦀 Что я умею:\n\n"
        "📝 Записываю автоматически:\n"
        "• съёмки (дата, локация, проект, люди)\n"
        "• идеи (начни с «идея:»)\n"
        "• события (врач, школа)\n"
        "• дневник (рассказ про день)\n\n"
        "🔗 Префиксы для ссылок:\n"
        "• «сценарий: <ссылка>» — создаст запись в архиве\n"
        "• «референс: <ссылка>» — добавит к последней съёмке\n"
        "• «фигма: <ссылка>» — привяжет к проекту\n\n"
        "❓ Спрашивай по данным:\n"
        "• «кто снимался в этом месяце»\n"
        "• «когда последняя съёмка с олегом»\n"
        "• «что у меня запланировано»\n"
        "• «съёмки с локомотивом»",
        reply_markup=reply_kbd()
    )


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conversations[uid] = []
    pending.pop(uid, None)
    await update.message.reply_text("🗑 Контекст очищен. Начинаем сначала.", reply_markup=reply_kbd())


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    text = msg.text or msg.caption or ""
    if not text:
        await msg.reply_text("Напиши что-нибудь 😊")
        return

    text_stripped = text.strip()
    if text_stripped in ("🏠 Сегодня", "📅 Съёмки", "🎬 Проекты", "💡 Идеи", "📓 Дневник", "📊 Итоги"):
        if text_stripped == "🏠 Сегодня":
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                shoots = await supa_get("shoots", 100)
                events = await supa_get("events", 100)
                today_shoots = [s for s in (shoots or []) if s.get("date") == today_str]
                today_events = [e for e in (events or []) if e.get("date") == today_str]
                lines = [f"📅 Сегодня — {datetime.now().strftime('%d.%m.%Y')}\n"]
                if not today_shoots and not today_events:
                    lines.append("Сегодня свободно ✦")
                for s in today_shoots:
                    what = s.get("project") or s.get("location") or "съёмка"
                    done = "✅" if s.get("status") == "снято" else "🔸"
                    lines.append(f"{done} {(s.get('time') or '')} — {what}")
                for e in today_events:
                    lines.append(f"🗓 {e.get('time','')} — {e.get('title','')}")
                await msg.reply_text("\n".join(lines), reply_markup=reply_kbd())
            except Exception as e:
                print(f"TODAY ERROR: {e}")
                await msg.reply_text("Не получилось загрузить 😔", reply_markup=reply_kbd())
            return

        elif text_stripped == "📅 Съёмки":
            await msg.reply_text("Все съёмки:", reply_markup=main_kbd())
            return

        elif text_stripped == "🎬 Проекты":
            projects = await supa_get("projects", 50)
            if not projects:
                await msg.reply_text("Проектов пока нет.", reply_markup=reply_kbd())
                return
            buttons = []
            for p in projects:
                icon = "✅" if p.get("status") == "готово" else "🔸"
                buttons.append([InlineKeyboardButton(f"{icon} {p.get('name','?')}", callback_data=f"proj_{p['id']}")])
            await msg.reply_text("🎬 Проекты:", reply_markup=InlineKeyboardMarkup(buttons))
            return

        elif text_stripped == "💡 Идеи":
            try:
                ideas = await supa_get("ideas", 50)
                shown = [i for i in ideas if (i.get("title") or "").strip()]
                if not shown:
                    await msg.reply_text("Идей пока нет.", reply_markup=reply_kbd())
                    return
                lines = ["💡 Идеи:\n"]
                for i in shown[:20]:
                    t = i["title"].strip()
                    lines.append(f"• *{t}*")
                    d = (i.get("description") or "").strip()
                    if d: lines.append(f"  {d[:80]}")
                await msg.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=reply_kbd())
            except Exception as e:
                print(f"IDEAS ERROR: {e}")
                await msg.reply_text("Не получилось загрузить идеи 😔", reply_markup=reply_kbd())
            return

        elif text_stripped == "📓 Дневник":
            try:
                diary = await supa_get("diary", 20, order="date.desc")
                if not diary:
                    await msg.reply_text("Дневник пока пуст.", reply_markup=reply_kbd())
                    return
                lines = ["📓 Дневник:\n"]
                for d in diary[:10]:
                    mood_icon = {"хорошо":"😊","нейтрально":"😐","плохо":"😔"}.get(d.get("mood","нейтрально"),"😐")
                    events_text = (d.get("events","") or "")[:60]
                    lines.append(f"{mood_icon} {d.get('date','')} — {events_text}")
                await msg.reply_text("\n".join(lines), reply_markup=reply_kbd())
            except Exception as e:
                print(f"DIARY ERROR: {e}")
                await msg.reply_text("Не получилось загрузить дневник 😔", reply_markup=reply_kbd())
            return

        elif text_stripped == "📊 Итоги":
            try:
                shoots = await supa_get("shoots", 200)
                projects = await supa_get("projects", 50)
                ideas = await supa_get("ideas", 100)
                diary = await supa_get("diary", 100)
                week_ago = datetime.now() - timedelta(days=7)
                week_shoots = 0
                done_shoots = 0
                for s in shoots or []:
                    try:
                        ca = datetime.strptime(s.get("created_at","")[:10], "%Y-%m-%d")
                        if ca >= week_ago:
                            week_shoots += 1
                            if s.get("status") == "снято":
                                done_shoots += 1
                    except:
                        pass
                active_proj = sum(1 for p in (projects or []) if p.get("status") != "готово")
                await msg.reply_text(
                    f"📊 Итоги за неделю\n\n"
                    f"📅 Съёмок добавлено: {week_shoots}\n"
                    f"✅ Съёмок проведено: {done_shoots}\n"
                    f"🎬 Активных проектов: {active_proj}\n"
                    f"💡 Идей всего: {len(ideas or [])}\n"
                    f"📓 Записей в дневнике: {len(diary or [])}",
                    reply_markup=reply_kbd()
                )
            except Exception as e:
                print(f"WEEK ERROR: {e}")
                await msg.reply_text("Не получилось загрузить итоги 😔", reply_markup=reply_kbd())
            return

    if uid in pending:
        p = pending[uid]
        if p.get("type") == "clarify_shoot":
            pass
        elif p.get("type") == "figma_url_for_proj":
            proj_id = p["proj_id"]
            url = text.strip()
            await supa_update("projects", "id", proj_id, {"figma_url": url})
            pending.pop(uid, None)
            projects = await supa_get("projects", 50)
            proj = next((x for x in projects if x.get("id") == proj_id), None)
            await msg.reply_text(f"🎨 Figma добавлена к «{proj.get('name','') if proj else '?'}» ✓", reply_markup=reply_kbd())
            return
        else:
            stop_words = ("отмен","отміни","не надо","забей","стоп","cancel","скасуй")
            low = text.strip().lower()
            if any(low.startswith(w) for w in stop_words) or low in ("нет","ні","no"):
                pending.pop(uid, None)
                if "очисти" in low or "удали" in low or "сотри" in low:
                    entity_type = p["type"]
                    entity_id = p["id"]
                    field = p["field"]
                    table = "shoots" if entity_type == "shoot" else "projects"
                    await supa_update(table,"id",entity_id,{field:""})
                    await msg.reply_text(f"📝 {field} очищено", reply_markup=main_kbd())
                else:
                    await msg.reply_text("Окей, отменила ✓", reply_markup=main_kbd())
                return
            p = pending.pop(uid)
            field = p["field"]
            entity_type = p["type"]
            entity_id = p["id"]
            if entity_type == "shoot":
                shoots = await supa_get("shoots",100)
                s_cur = next((x for x in shoots if x.get("id")==entity_id),None)
                old = s_cur.get(field,"") if s_cur else ""
                merged = append_log(old, text.strip())
                await supa_update("shoots","id",entity_id,{field:merged})
                shoots = await supa_get("shoots",100)
                s = next((x for x in shoots if x.get("id")==entity_id),None)
                if s:
                    await msg.reply_text(f"{'🔗 Ссылка' if field=='script' else '📝 Заметка'} добавлена ✓",
                        reply_markup=shoot_detail_kbd(entity_id,s.get("status","")))
                return
            elif entity_type == "project":
                projects = await supa_get("projects",50)
                p_cur = next((x for x in projects if x.get("id")==entity_id),None)
                old = p_cur.get(field,"") if p_cur else ""
                merged = append_log(old, text.strip())
                await supa_update("projects","id",entity_id,{field:merged})
                projects = await supa_get("projects",50)
                shoots = await supa_get("shoots",100)
                tasks = await supa_get("tasks",200)
                p_obj = next((x for x in projects if x.get("id")==entity_id),None)
                if p_obj:
                    await msg.reply_text(f"{'🔗 Ссылка' if field=='link' else '📝 Заметка'} добавлена ✓",
                        reply_markup=proj_detail_kbd_with_figma(entity_id,p_obj.get("status",""),bool(p_obj.get("figma_url"))))
                return

    text_low = text.lower().strip()
    prefix_match = None
    for prefix in ("сценарій:", "сценарий:", "сценарій ", "сценарий "):
        if text_low.startswith(prefix):
            prefix_match = ("script", text[len(prefix):].strip())
            break
    if not prefix_match:
        for prefix in ("референс:", "реф:", "референс ", "реф "):
            if text_low.startswith(prefix):
                prefix_match = ("ref", text[len(prefix):].strip())
                break
    if not prefix_match:
        for prefix in ("фігма:", "фигма:", "figma:", "фігма ", "фигма ", "figma "):
            if text_low.startswith(prefix):
                prefix_match = ("figma", text[len(prefix):].strip())
                break

    if prefix_match:
        kind, value = prefix_match
        if not value:
            await msg.reply_text(f"После «{kind}» жду ссылку или текст.")
            return
        shoots = await supa_get("shoots", 5, order="created_at.desc")
        last_shoot = shoots[0] if shoots else None

        if kind == "script":
            import re as _re
            raw_text = text
            cleaned = _re.sub(r"https?://\S+", "", raw_text)
            cleaned = _re.sub(r"(?i)(сценарій?|скрипт)\s*:", "", cleaned)
            cleaned = cleaned.strip(" .,\n—-")
            shoot_title = cleaned if len(cleaned) > 2 else "Сценарий без названия"
            shoot_data = {
                "date": None, "time": None, "location": "?",
                "project": shoot_title, "people": "",
                "status": "не снято", "script": value,
                "notes": "⏳ не запланировано — дата и место не известны"
            }
            shoot_id = await supa_insert("shoots", shoot_data, return_id=True)
            await supa_insert("scripts", {"title": f"Сценарий — {shoot_title}", "link": value, "tag": "другое"})
            if shoot_id:
                await msg.reply_text(
                    f"📜 Сохранила сценарий «{shoot_title}». Создала съёмку-заготовку — дата и место пока не известны.\n"
                    "Как только решишь — открой карточку в браузере и допиши.",
                    reply_markup=reply_kbd()
                )
            else:
                await msg.reply_text("Не получилось сохранить 😔")
            return

        if kind == "ref":
            if not last_shoot:
                await msg.reply_text("Сначала добавь съёмку, потом референс.")
                return
            old_notes = last_shoot.get("notes", "")
            new_text = f"🎨 референс: {value}"
            merged = append_log(old_notes, new_text)
            await supa_update("shoots", "id", last_shoot["id"], {"notes": merged})
            await msg.reply_text(f"🎨 Референс добавила к съёмке {last_shoot.get('date','')} ✓", reply_markup=reply_kbd())
            return

        if kind == "figma":
            projects = await supa_get("projects", 50, order="created_at.desc")
            active = [p for p in projects if p.get("status") != "готово"]
            if not active:
                await msg.reply_text("Нет активных проектов. Сначала добавь проект.")
                return
            if len(active) == 1:
                p = active[0]
                await supa_update("projects", "id", p["id"], {"figma_url": value})
                await msg.reply_text(f"🎨 Figma добавлена к проекту «{p.get('name','')}» ✓", reply_markup=reply_kbd())
            else:
                pending[uid] = {"type": "figma_choose", "url": value}
                buttons = [[InlineKeyboardButton(p["name"], callback_data=f"figma_pick_{p['id']}")] for p in active]
                await msg.reply_text("🎨 К какому проекту привязать figma?", reply_markup=InlineKeyboardMarkup(buttons))
            return

    add_history(uid, "user", text)
    thinking = await msg.reply_text("⏳")
    try:
        result = await ask_groq(get_history(uid))
        reply = result.get("reply","Окей!")
        action = result.get("action","none")
        data = result.get("data",{})
        add_history(uid, "model", reply)

        if action == "clarify":
            pending[uid] = {"type":"clarify_shoot","partial":data.get("partial",{})}
            await thinking.delete()
            await msg.reply_text(reply)
            return

        if action == "clarify_reply":
            prev = pending.pop(uid, None)
            if prev and prev.get("type") == "clarify_shoot":
                merged = dict(prev.get("partial",{}))
                field = data.get("field_given","")
                value = data.get("value","")
                if field and value:
                    merged[field] = value
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
                    pending[uid] = {"type":"clarify_shoot","partial":merged}
                    await thinking.delete()
                    await msg.reply_text(reply)
                    return
            await thinking.delete()
            await msg.reply_text(reply)
            return

        saved = False
        if action == "query":
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
            reply += f"\nЗаписала {saved} съёмок ✓"

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

    if cb == "noop":
        return

    if cb.startswith("stag_"):
        parts = cb.split("_", 2)
        script_id = int(parts[1])
        tag = parts[2]
        await supa_update("scripts", "id", script_id, {"tag": tag})
        pending.pop(uid, None)
        await q.edit_message_text(f"📋 Тег сценария: {tag} ✓")
        return

    if cb.startswith("figma_pick_"):
        proj_id = int(cb.split("_")[2])
        p = pending.pop(uid, None)
        if p and p.get("type") == "figma_choose":
            await supa_update("projects", "id", proj_id, {"figma_url": p["url"]})
            projects = await supa_get("projects", 50)
            proj = next((x for x in projects if x.get("id") == proj_id), None)
            await q.edit_message_text(f"🎨 Figma добавлена к проекту «{proj.get('name','') if proj else '?'}» ✓")
        else:
            await q.edit_message_text("Не нашла что привязать 😔")
        return

    if cb.startswith("figma_proj_"):
        proj_id = int(cb.split("_")[2])
        projects = await supa_get("projects", 50)
        proj = next((x for x in projects if x.get("id") == proj_id), None)
        if not proj:
            await q.edit_message_text("Проект не найден")
            return
        if proj.get("figma_url"):
            await q.message.reply_text(f"🎨 Figma проекта:\n{proj['figma_url']}", reply_markup=proj_detail_kbd_with_figma(proj_id, proj.get("status",""), True))
        else:
            pending[uid] = {"type": "figma_url_for_proj", "proj_id": proj_id}
            await q.message.reply_text("🎨 Пришли ссылку на Figma:")
        return

    if cb == "shoots":
        pending.pop(uid, None)
        from datetime import date, timedelta
        all_shoots = await supa_get("shoots", 100, order="date.desc")
        today_str = date.today().isoformat()
        cutoff = (date.today() - timedelta(days=45)).isoformat()
        active = [s for s in all_shoots
                  if s.get("status") != "отменена"
                  and (not s.get("date") or s.get("date","") >= cutoff)]
        upcoming = sorted([s for s in active if (s.get("date") or "") >= today_str],
                          key=lambda s: (s.get("date",""), s.get("time","")))
        recent = sorted([s for s in active if (s.get("date") or "") < today_str],
                        key=lambda s: s.get("date",""), reverse=True)[:7]
        if not active:
            await q.edit_message_text("📅 Актуальных съёмок нет", reply_markup=main_kbd())
            return
        buttons = []
        if upcoming:
            buttons.append([InlineKeyboardButton("— предстоящие —", callback_data="noop")])
            for s in upcoming[:5]:
                icon = "🔜"
                what = (s.get("project") or s.get("location") or "съёмка")[:20]
                t = s.get("time") or ""
                label = f"{icon} {fmt_date(s.get('date',''))} {t} — {what}"
                buttons.append([InlineKeyboardButton(label, callback_data=f"shoot_{s['id']}")])
        if recent:
            buttons.append([InlineKeyboardButton("— недавние —", callback_data="noop")])
            for s in recent:
                icon = "✅" if s.get("status")=="снято" else "🔸"
                what = (s.get("project") or s.get("location") or "съёмка")[:20]
                t = s.get("time") or ""
                label = f"{icon} {fmt_date(s.get('date',''))} {t} — {what}"
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
        await q.edit_message_text(render_project(p,shoots,tasks),reply_markup=proj_detail_kbd_with_figma(proj_id,p.get("status",""),bool(p.get("figma_url"))))
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
                await q.edit_message_text(render_project(p,shoots,tasks),reply_markup=proj_detail_kbd_with_figma(proj_id,p.get("status",""),bool(p.get("figma_url"))))
        return

    if cb == "ideas":
        items = await supa_get("ideas",50)
        shown = [i for i in items if (i.get("title") or "").strip()]
        if not shown:
            await q.edit_message_text("💡 Идей пока нет", reply_markup=main_kbd())
            return
        parts = ["💡 Идеи:\n"]
        for i in shown[:20]:
            t = i["title"].strip()
            parts.append(f"• *{t}*")
            d = (i.get("description") or "").strip()
            if d: parts.append(f"  {d[:150]}")
        await q.edit_message_text("\n".join(parts), parse_mode="Markdown",
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
        lines = [f"{me} {d.get('date','')}"]
        if d.get("events"): lines.append(f"\n📝 {d['events']}")
        if d.get("thoughts"): lines.append(f"\n💭 {d['thoughts']}")
        await q.edit_message_text("\n".join(lines),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ К дневнику",callback_data="diary")]]))
        return

    if cb == "events":
        items = await supa_get("events",15,order="date.asc")
        if not items:
            await q.edit_message_text(
                "🗓 Событий пока нет\nНапиши боту: запись к врачу 5 мая в 10:00",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад",callback_data="main")]]))
            return
        lines = ["🗓 События:\n"]
        for e in items:
            lines.append(f"• {e.get('date','')} {e.get('time','')} — {e.get('title','')}")
            if e.get("category"): lines.append(f"  {e['category']}")
        await q.edit_message_text("\n".join(lines),
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
        text = (
            f"📊 Итоги недели:\n\n"
            f"📅 Съёмок добавлено: {ns}\n✅ Съёмок проведено: {ds}\n"
            f"💡 Идей: {ni}\n📓 Записей в дневнике: {nd}\n🔸 Активных проектов: {ap}"
        )
        await q.edit_message_text(text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад",callback_data="main")]]))
        return

    await q.edit_message_text("Неизвестная команда", reply_markup=main_kbd())


def main():
    import time
    time.sleep(5)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", cmd_today_handler))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION | filters.FORWARDED, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    async def post_init(application):
        await application.bot.set_my_commands([
            BotCommand("today", "что у меня сегодня"),
            BotCommand("help", "что я умею"),
            BotCommand("clear", "очистить контекст"),
            BotCommand("start", "перезапуск"),
        ])
        try:
            await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        except Exception as e:
            print(f"menu button: {e}")

    app.post_init = post_init
    print("🦀 Rak bot v26 started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
