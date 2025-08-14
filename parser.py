# -*- coding: utf-8 -*-
from telethon import TelegramClient
from telethon.tl.types import Message
from datetime import timezone
import csv, re, requests

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
    t = t.replace('\u200b', '').replace('\xa0', ' ')
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'\n{3,}', '\n\n', t).strip()
    return t

def first_sentence(t: str, max_len=140) -> str:
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
    pick = []
    wcount = 0
    for w in words:
        if re.match(r'\w', w, flags=re.UNICODE):
            pick.append(w)
            wcount += 1
        if wcount >= max_words:
            break
    title = ' '.join(pick).upper()
    title = re.sub(r'[\.\,\-\–\—\:]+$', '', title)
    return title or 'НОВОЕ'

def emoji_hint(t: str) -> str:
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
    t = clean_text(text)
    hook = first_sentence(t)
    title = title_from_text(t)
    emo = emoji_hint(t)

    body = t.split('\n')
    bullets = []
    for line in body[1:]:
        line = line.strip()
        if not line:
            continue
        if len(line) > 120:
            line = line[:118].rstrip() + '…'
        bullets.append(f"- {line}")
        if len(bullets) >= 3:
            break

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

# ---------- отправка в Telegram ----------
BOT_TOKEN = "ТОКЕН_ТВОЕГО_БОТА"
CHAT_ID = "ID_ТВОЕГО_ЧАТА"  # например -1001234567890

def send_message_to_tg(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, data=data)

def send_file_to_tg(file_path: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    with open(file_path, 'rb') as f:
        requests.post(url, data={"chat_id": CHAT_ID}, files={"document": f})

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
                text = clean_text(msg.message or "")
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

                # отправляем адаптированный текст в ТГ
                send_message_to_tg(styled)

        except Exception as e:
            print(f"[{username}] error: {e}")

    # сохраняем CSV
    csv_path = 'output.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["channel","message_id","date_utc","views","forwards","replies","link","original_text","styled_text"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Saved {csv_path} (rows={len(rows)})")

    # отправляем файл в ТГ
    send_file_to_tg(csv_path)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
