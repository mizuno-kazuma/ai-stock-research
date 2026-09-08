-- 004_securities_product_category.sql
-- J-Quants の商品区分（ProductCategory）を保存する。ETF・REIT・優先出資証券などを
-- 個別株（内国株券）から区別できるようにする（docs/03-data-model.md §2.1）。
-- 既存行は NULL のままでよい。NULL はユニバースフィルタで「除外しない」扱いにする
-- （収集し直すまでの間、個別株フィルタを有効にしても既存データが全滅しないように）。
ALTER TABLE securities ADD COLUMN IF NOT EXISTS product_category VARCHAR;
