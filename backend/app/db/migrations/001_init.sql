-- Hisobchi AI — boshlang'ich sxema
-- Ma'lumotlar izolyatsiyasi: har bir user jadvali Postgres Row-Level Security bilan himoyalangan.
-- Ilova "app_user" roli bilan ulanadi (jadval egasi emas, BYPASSRLS yo'q), shuning uchun
-- kodda WHERE user_id unutilsa ham boshqa userning qatori hech qachon qaytmaydi.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- Kontekst funksiyalari ----------
CREATE OR REPLACE FUNCTION app_current_user() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION app_is_system() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT coalesce(current_setting('app.system', true), '') = 'on'
$$;

-- ---------- Users ----------
CREATE TABLE users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id     bigint NOT NULL UNIQUE,
    username        text,
    first_name      text,
    language        text NOT NULL DEFAULT 'uz',
    timezone        text NOT NULL DEFAULT 'Asia/Tashkent',
    report_enabled  boolean NOT NULL DEFAULT true,
    report_time     time NOT NULL DEFAULT '23:59',
    role            text NOT NULL DEFAULT 'user' CHECK (role IN ('user','superadmin')),
    is_blocked      boolean NOT NULL DEFAULT false,
    blocked_reason  text,
    trial_ends_at   timestamptz NOT NULL,
    pro_until       timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_active_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_users_created ON users (created_at);
CREATE INDEX ix_users_last_active ON users (last_active_at);

-- ---------- Categories ----------
CREATE TABLE categories (
    id          serial PRIMARY KEY,
    user_id     uuid REFERENCES users(id) ON DELETE CASCADE,  -- NULL = tizim (seed) kategoriyasi
    type        text NOT NULL CHECK (type IN ('expense','income')),
    key         text NOT NULL,
    name        text NOT NULL,
    emoji       text NOT NULL DEFAULT '•',
    sort        int  NOT NULL DEFAULT 100,
    is_active   boolean NOT NULL DEFAULT true
);
CREATE UNIQUE INDEX ux_categories_system_key ON categories (type, key) WHERE user_id IS NULL;
CREATE UNIQUE INDEX ux_categories_user_key ON categories (user_id, type, key) WHERE user_id IS NOT NULL;

-- Kategoriya o'rganish: user bir so'zni qayta kategoriyalasa, keyingi safar shu ishlatiladi.
-- phrase_hash = HMAC(secret, normalized_word) — so'zning o'zi saqlanmaydi.
CREATE TABLE category_rules (
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    phrase_hash  text NOT NULL,
    category_id  int  NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    hits         int  NOT NULL DEFAULT 1,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, phrase_hash)
);

-- ---------- Transactions ----------
CREATE TABLE transactions (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type             text NOT NULL CHECK (type IN ('expense','income')),
    amount           bigint NOT NULL CHECK (amount > 0 AND amount < 1000000000000),
    currency         text NOT NULL DEFAULT 'UZS',
    category_id      int REFERENCES categories(id),
    description_enc  bytea,                 -- AES-256-GCM bilan shifrlangan
    occurred_at      timestamptz NOT NULL,
    source           text NOT NULL DEFAULT 'text' CHECK (source IN ('text','voice','manual')),
    confidence       real,
    source_key       text,                  -- idempotency: "<chat>:<msg>:<idx>"
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    deleted_at       timestamptz
);
CREATE INDEX ix_tx_user_time ON transactions (user_id, occurred_at DESC) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX ux_tx_source_key ON transactions (user_id, source_key) WHERE source_key IS NOT NULL;

-- Tasdiq kutayotgan (confidence o'rta) parse natijalari
CREATE TABLE pending_parses (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    payload_enc  bytea NOT NULL,
    source       text NOT NULL,
    source_key   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_pending_user ON pending_parses (user_id, created_at);

-- Telegram update idempotency (bir xil update ikki marta kelsa — bitta natija)
CREATE TABLE processed_updates (
    update_key  text PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_processed_created ON processed_updates (created_at);

-- ---------- Reports ----------
CREATE TABLE reports (
    id            bigserial PRIMARY KEY,
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period_type   text NOT NULL CHECK (period_type IN ('daily','weekly','monthly','yearly','trial_d2','trial_end','pro_d3','pro_end')),
    period_start  date NOT NULL,
    status        text NOT NULL DEFAULT 'sent',
    sent_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, period_type, period_start)
);

CREATE TABLE ai_insights (
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period_type   text NOT NULL,
    period_start  date NOT NULL,
    text_enc      bytea NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, period_type, period_start)
);

-- ---------- Billing ----------
CREATE TABLE payment_requests (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount       bigint NOT NULL,
    days         int NOT NULL,
    status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    note         text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    decided_at   timestamptz,
    decided_by   bigint
);
-- bitta userda bir vaqtda faqat bitta "pending" ariza
CREATE UNIQUE INDEX ux_payreq_one_pending ON payment_requests (user_id) WHERE status = 'pending';
CREATE INDEX ix_payreq_status ON payment_requests (status, created_at DESC);

-- ---------- System ----------
CREATE TABLE app_settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
    id              bigserial PRIMARY KEY,
    actor_tg_id     bigint NOT NULL,
    action          text NOT NULL,
    target_user_id  uuid,
    meta            jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_created ON audit_logs (created_at DESC);

CREATE TABLE analytics_events (
    id          bigserial PRIMARY KEY,
    user_id     uuid,
    name        text NOT NULL,
    props       jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_events_name_time ON analytics_events (name, created_at);

-- ---------- Row-Level Security ----------
ALTER TABLE users            ENABLE ROW LEVEL SECURITY;
ALTER TABLE categories       ENABLE ROW LEVEL SECURITY;
ALTER TABLE category_rules   ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE pending_parses   ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports          ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_insights      ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE users            FORCE ROW LEVEL SECURITY;
ALTER TABLE categories       FORCE ROW LEVEL SECURITY;
ALTER TABLE category_rules   FORCE ROW LEVEL SECURITY;
ALTER TABLE transactions     FORCE ROW LEVEL SECURITY;
ALTER TABLE pending_parses   FORCE ROW LEVEL SECURITY;
ALTER TABLE reports          FORCE ROW LEVEL SECURITY;
ALTER TABLE ai_insights      FORCE ROW LEVEL SECURITY;
ALTER TABLE payment_requests FORCE ROW LEVEL SECURITY;

CREATE POLICY p_users ON users
  USING (app_is_system() OR id = app_current_user())
  WITH CHECK (app_is_system() OR id = app_current_user());

-- tizim kategoriyalari hammaga ko'rinadi, lekin faqat system o'zgartira oladi
CREATE POLICY p_categories_read ON categories FOR SELECT
  USING (app_is_system() OR user_id IS NULL OR user_id = app_current_user());
CREATE POLICY p_categories_ins ON categories FOR INSERT
  WITH CHECK (app_is_system() OR user_id = app_current_user());
CREATE POLICY p_categories_upd ON categories FOR UPDATE
  USING (app_is_system() OR user_id = app_current_user())
  WITH CHECK (app_is_system() OR user_id = app_current_user());
CREATE POLICY p_categories_del ON categories FOR DELETE
  USING (app_is_system() OR user_id = app_current_user());

CREATE POLICY p_category_rules ON category_rules
  USING (app_is_system() OR user_id = app_current_user())
  WITH CHECK (app_is_system() OR user_id = app_current_user());
CREATE POLICY p_transactions ON transactions
  USING (app_is_system() OR user_id = app_current_user())
  WITH CHECK (app_is_system() OR user_id = app_current_user());
CREATE POLICY p_pending ON pending_parses
  USING (app_is_system() OR user_id = app_current_user())
  WITH CHECK (app_is_system() OR user_id = app_current_user());
CREATE POLICY p_reports ON reports
  USING (app_is_system() OR user_id = app_current_user())
  WITH CHECK (app_is_system() OR user_id = app_current_user());
CREATE POLICY p_insights ON ai_insights
  USING (app_is_system() OR user_id = app_current_user())
  WITH CHECK (app_is_system() OR user_id = app_current_user());
CREATE POLICY p_payreq ON payment_requests
  USING (app_is_system() OR user_id = app_current_user())
  WITH CHECK (app_is_system() OR user_id = app_current_user());

-- ---------- Seed: kategoriyalar ----------
INSERT INTO categories (user_id, type, key, name, emoji, sort) VALUES
 (NULL,'expense','food','Ovqat','🍽',10),
 (NULL,'expense','groceries','Bozor / oziq-ovqat','🛒',20),
 (NULL,'expense','taxi','Taksi','🚕',30),
 (NULL,'expense','transport','Transport','🚌',40),
 (NULL,'expense','fuel','Benzin / yoqilg''i','⛽',50),
 (NULL,'expense','utilities','Kommunal','💡',60),
 (NULL,'expense','rent','Ijara','🏠',70),
 (NULL,'expense','home','Uy / remont','🛠',80),
 (NULL,'expense','internet','Aloqa / internet','📱',90),
 (NULL,'expense','health','Sog''liq','💊',100),
 (NULL,'expense','education','Ta''lim','📚',110),
 (NULL,'expense','entertainment','Ko''ngilochar','🎮',120),
 (NULL,'expense','clothes','Kiyim','👕',130),
 (NULL,'expense','gifts','Sovg''a / To''y','🎁',140),
 (NULL,'expense','charity','Sadaqa / xayriya','🤲',150),
 (NULL,'expense','advertising','Reklama','📣',160),
 (NULL,'expense','delivery','Dostavka','📦',170),
 (NULL,'expense','business','Biznes xarajati','💼',180),
 (NULL,'expense','construction','Qurilish','🧱',190),
 (NULL,'expense','taxes','Soliq / majburiy to''lov','🧾',200),
 (NULL,'expense','other','Boshqa','📌',999),
 (NULL,'income','salary','Maosh','💰',10),
 (NULL,'income','sales','Savdo / tushum','🏪',20),
 (NULL,'income','services','Xizmatdan daromad','🧑‍🔧',30),
 (NULL,'income','bonus','Bonus','🎉',40),
 (NULL,'income','refund','Qaytarilgan pul','↩️',50),
 (NULL,'income','rent_income','Ijara daromadi','🏘',60),
 (NULL,'income','other_income','Boshqa daromad','➕',999);

INSERT INTO app_settings (key, value) VALUES
 ('billing', '{"price": 49000, "pro_days": 30, "trial_days": 7, "card_number": "", "card_holder": "", "admin_username": "", "currency": "UZS"}'),
 ('ai', '{"auto_save_threshold": 0.85, "confirm_threshold": 0.60}');
