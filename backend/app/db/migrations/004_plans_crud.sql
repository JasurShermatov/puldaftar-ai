-- Tariflar to'liq CRUD: to'lovlarda ishlatilgan tarif o'chirilsa — arxivlanadi (tarix buzilmaydi).
ALTER TABLE plans ADD COLUMN IF NOT EXISTS archived boolean NOT NULL DEFAULT false;
