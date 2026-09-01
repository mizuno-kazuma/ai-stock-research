-- 開示一覧に会社名を載せる。EDINET の filerName 等を正規化時に保持する。
-- 証券マスタがある場合は API 側でそちらの名称を優先する。
ALTER TABLE documents ADD COLUMN IF NOT EXISTS name_local VARCHAR;
