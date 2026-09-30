-- O'chirilgan akkauntlar qayta /start qilganda bepul sinov qayta berilmasligi uchun.
-- Telegram ID ning o'zi emas, faqat HMAC hash saqlanadi (shaxsiy ma'lumot qolmaydi).
CREATE TABLE IF NOT EXISTS trial_guard (
    tg_hash     text PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now()
);
