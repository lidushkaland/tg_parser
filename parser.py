# -*- coding: utf-8 -*-
from telethon import TelegramClient
from telethon.tl.types import Message
from datetime import timezone
import csv, re

# ---------- конфиг ----------
# читаем config.txt (рядом с parser.py)
cfg = {}
with open('config.txt', 'r', encoding='utf-8') as f:
    for line in f:
        if '=' in line:
            k, v = line.strip().split('=', 1)
            cfg[k.strip()] = v.strip()

API_ID        = int(cfg['API_ID'])
API_HASH      = cfg['API_HASH']
PHONE         = cfg['PHONE']
LIMIT_PER_CH  = int(cfg.get('LIMIT_PER_CH', '30'))

# читаем каналы (по одному на строку; можно @name или ссылкой)
channels = []
with open('channels.txt', 'r', encoding='utf-8') as f:
    for raw in f:
        s = raw.strip()
        if not s:
            continue
        # нормализуем к username
        s = s.replace('https://t.me/', '').replace('http://t.me/', '')
        s = s.lstrip('@').strip('/')
        channels.append(s)

# ---------- утилиты форматирования ----------
def clean_text(t: str) -> str:
    if not t:
        return ''
    # убираем лишние пробелы
    t = t.replace('\u200b', '').replace('\xa0', ' ')
    # убираем html-теги если вдруг прилетели
    t = re.sub(r'<[^>]+>', '', t)
    # схлопываем многоточия/переводы
    t = re.sub(r'\n{3,}', '\n\n', t).strip()
    return t

def first_sentence(t: str, max_len=140) -> str:
    # берём первую фразу до точки/восклиц/вопроса, ограничиваем длину
    if not t:
        return ''
    m = re.split(r'(?<=[\.\!\?])\s+', t)
    s = (m[0] if m else t).strip()
    if len(s) > max_len:
        s = s[:max_len-1].rstrip() + '…'
    return s

def title_from_text(t: str, max_words=7) -> str:
    if not t:
        return 'НОВОЕ'
    words = re.findall(r'\w+|\S', t, flags=re.UNICODE)
    # берём первые смысловые слова
    pick = []
    wcount = 0
    for w in words:
        if re.match(r'\w', w, flags=re.UNICODE):
            pick.append(w)
            wcount += 1
        if wcount >= max_words:
            break
    title = ' '.join(pick).upper()
    # подчистим
    title = re.sub(r'[\.\,\-\–\—\:]+$', '', title)
    return title or 'НОВОЕ'

def emoji_hint(t: str) -> str:
    """очень лёгкий маппинг по ключевым словам, чтобы добавить вайба"""
    s = t.lower()
    if any(k in s for k in ['ai','нейросет','искусствен','gpt','model']):
        return '🤖'
    if any(k in s for k in ['маркет','продаж','воронк','реклам','бренд']):
        return '📈'
    if any(k in s for k in ['дизайн','визуал','креатив','мем']):
        return '🎨'
    if any(k in s for k in ['обновлен','релиз','запуст','апдейт']):
        return '🚀'
    if any(k in s for k in ['конкурс','челлендж','итоги','кей']):
        return '🏆'
    return '✨'

def make_styled(text: str, ch: str, date, views: int, fwds: int, replies: int, link: str) -> str:
    """
    генерим markdown для Telegram (Parse Mode = Markdown)
    — хук
    — 2-3 живых пункта
    — мини-метрики
    — ссылка
    """
    t = clean_text(text)
    hook = first_sentence(t)
    title = title_from_text(t)
    emo = emoji_hint(t)

    # быстрые пункты: вторую/третью строки делаем короткими
    body = t.split('\n')
    bullets = []
    for line in body[1:]:
        line = line.strip()
        if not line:
            continue
        # обрежем длинноты
        if len(line) > 120:
            line = line[:118].rstrip() + '…'
        bullets.append(f"- {line}")
        if len(bullets) >= 3:
            break

    # сборка markdown
    md = []
    md.append(f"*{emo} {title}*")
    if hook:
        md.append(f"\n_{hook}_")
    if bullets:
        md.append("\n" + "\n".join(bullets))
    md.append("\n— _метрики:_ " +
              f"👀 {views or 0} · 🔁 {fwds or 0} · 💬 {replies or 0}")
    md.append(f"\n[Открыть пост]({link})")
    return "\n".join(md).strip()

def tme_link(username: str, mid: int) -> str:
    return f"https://t.me/{username}/{mid}"

# ---------- основной код ----------
client = TelegramClient('session', API_ID, API_HASH)

async def main():
    rows = []
    await client.start(phone=PHONE)

    for username in channels:
        try:
            entity = await client.get_entity(username)
            async for msg in client.iter_messages(entity, limit=LIMIT_PER_CH):
                if not isinstance(msg, Message):
                    continue
                # оригинал
                text = clean_text(msg.message or "")
                # метрики
                views   = getattr(msg, "views", 0) or 0
                forwards= getattr(msg, "forwards", 0) or 0
                repl    = getattr(getattr(msg, "replies", None), "replies", 0) or 0
                link    = tme_link(username, msg.id)
                dt      = msg.date.astimezone(timezone.utc).isoformat()

                styled  = make_styled(text, username, dt, views, forwards, repl, link)

                rows.append({
                    "channel": username,
                    "message_id": msg.id,
                    "date_utc": dt,
                    "views": views,
                    "forwards": forwards,
                    "replies": repl,
                    "link": link,
                    "original_text": text,
                    "styled_text": styled
                })
        except Exception as e:
            print(f"[{username}] error: {e}")

    # сохраняем CSV в utf-8
    with open('output.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["channel","message_id","date_utc","views","forwards","replies","link","original_text","styled_text"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Saved output.csv (rows={len(rows)})")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
from telethon import TelegramClient
import csv

# Читаем настройки из config.txt
config = {}
with open('config.txt', 'r') as f:
    for line in f:
        key, value = line.strip().split('=')
        config[key] = value

api_id = int(config['API_ID'])
api_hash = config['API_HASH']
phone = config['PHONE']
limit_per_ch = int(config['LIMIT_PER_CH'])

client = TelegramClient('session_name', api_id, api_hash)

async def main():
    with open('channels.txt', 'r') as f:
        channels = [line.strip() for line in f]

    with open('output.csv', 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Channel', 'Message'])

        for ch in channels:
            async for message in client.iter_messages(ch, limit=limit_per_ch):
                writer.writerow([ch, message.text or "MEDIA/EMPTY"])

with client:
    client.loop.run_until_complete(main())

