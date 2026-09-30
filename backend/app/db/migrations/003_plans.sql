-- 3 ta tarif: 1 oylik, 3 oylik, 1 yillik. Narx/chegirma admin paneldan o'zgartiriladi (kodda hardcode yo'q).
CREATE TABLE plans (
    code        text PRIMARY KEY,                 -- m1 | m3 | y1
    name        text NOT NULL,
    days        int  NOT NULL CHECK (days > 0),
    price       bigint NOT NULL CHECK (price > 0),
    old_price   bigint CHECK (old_price IS NULL OR old_price > 0),   -- chegirmadan oldingi narx (ustidan chizilib ko'rsatiladi)
    badge       text,                             -- masalan: "🔥 -20%", "Eng foydali"
    sort        int  NOT NULL DEFAULT 100,
    is_active   boolean NOT NULL DEFAULT true,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO plans (code, name, days, price, sort) VALUES
 ('m1', '1 oylik',  30,  49000, 10),
 ('m3', '3 oylik',  90, 129000, 20),
 ('y1', '1 yillik', 365, 449000, 30);

ALTER TABLE payment_requests ADD COLUMN plan_code text REFERENCES plans(code);
UPDATE payment_requests SET plan_code = 'm1' WHERE plan_code IS NULL;

-- Ommaviy xabarlar tarixi (natijalar bilan)
CREATE TABLE broadcasts (
    id           bigserial PRIMARY KEY,
    admin_tg_id  bigint NOT NULL,
    segment      text NOT NULL,
    kind         text NOT NULL,                   -- text | photo | copy
    preview      text,
    total        int NOT NULL DEFAULT 0,
    sent         int NOT NULL DEFAULT 0,
    failed       int NOT NULL DEFAULT 0,
    status       text NOT NULL DEFAULT 'running', -- running | done
    created_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz
);
