-- Qarzlar moduli + AI suhbat tarixi + yangi kategoriyalar (topilgan pul / yo'qotish).

-- ---------- Debts ----------
CREATE TABLE debts (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    direction         text NOT NULL CHECK (direction IN ('given','taken')),   -- given: men berdim, taken: men oldim
    amount            bigint NOT NULL CHECK (amount > 0 AND amount < 1000000000000),
    paid_amount       bigint NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
    counterparty_enc  bytea,                 -- kim bilan (AES-256-GCM)
    note_enc          bytea,
    occurred_at       timestamptz NOT NULL,
    due_at            timestamptz,
    status            text NOT NULL DEFAULT 'open' CHECK (status IN ('open','paid')),
    paid_at           timestamptz,
    last_reminded_on  date,
    source            text NOT NULL DEFAULT 'text' CHECK (source IN ('text','voice','manual')),
    source_key        text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_debts_user_status ON debts (user_id, status, due_at);
CREATE INDEX ix_debts_due ON debts (due_at) WHERE status = 'open' AND due_at IS NOT NULL;
CREATE UNIQUE INDEX ux_debts_source_key ON debts (user_id, source_key) WHERE source_key IS NOT NULL;

ALTER TABLE debts ENABLE ROW LEVEL SECURITY;
ALTER TABLE debts FORCE ROW LEVEL SECURITY;
CREATE POLICY p_debts ON debts
  USING (app_is_system() OR user_id = app_current_user())
  WITH CHECK (app_is_system() OR user_id = app_current_user());

-- ---------- AI chat ----------
CREATE TABLE ai_chat_messages (
    id           bigserial PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         text NOT NULL CHECK (role IN ('user','assistant')),
    content_enc  bytea NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_ai_chat_user ON ai_chat_messages (user_id, id DESC);

ALTER TABLE ai_chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_chat_messages FORCE ROW LEVEL SECURITY;
CREATE POLICY p_ai_chat ON ai_chat_messages
  USING (app_is_system() OR user_id = app_current_user())
  WITH CHECK (app_is_system() OR user_id = app_current_user());

-- ---------- Yangi tizim kategoriyalari ----------
INSERT INTO categories (user_id, type, key, name, emoji, sort) VALUES
 (NULL,'expense','loss','Yo''qotish / zarar','🕳',210),
 (NULL,'income','found','Topilgan pul / yutuq','🍀',70)
ON CONFLICT (type, key) WHERE user_id IS NULL DO NOTHING;

-- Qarz eslatmalari ham reports jadvalida hisobga olinmaydi (debts.last_reminded_on ishlatiladi).
