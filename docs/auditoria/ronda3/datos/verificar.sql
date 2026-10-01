-- Integridad de la base restaurada (r3-datos). Una fila por control.
SELECT 'asientos_total', count(*)::text FROM r3_asiento
UNION ALL SELECT 'asientos_max_id', coalesce(max(id),0)::text FROM r3_asiento
UNION ALL SELECT 'asientos_huecos', (coalesce(max(id),0) - count(*))::text FROM r3_asiento
UNION ALL SELECT 'asientos_corruptos', count(*)::text FROM r3_asiento WHERE monto <> round(id*1.07,2) OR glosa <> md5(id::text)
UNION ALL SELECT 'asiento_ultimo_ts', coalesce(max(ts)::text,'-') FROM r3_asiento
UNION ALL SELECT 'md5_res_partner', md5(string_agg(md5(t::text), ',' ORDER BY id)) FROM res_partner t
UNION ALL SELECT 'md5_product_template', md5(string_agg(md5(t::text), ',' ORDER BY id)) FROM product_template t
UNION ALL SELECT 'md5_ir_attachment', md5(string_agg(md5(t::text), ',' ORDER BY id)) FROM ir_attachment t
UNION ALL SELECT 'md5_account_account', md5(string_agg(md5(t::text), ',' ORDER BY id)) FROM account_account t;
