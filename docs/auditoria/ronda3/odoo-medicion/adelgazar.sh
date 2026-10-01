#!/usr/bin/env bash
# Desinstala en una COPIA (5432, r3_med_slim) los módulos auto-instalados que ningún dcasa_* necesita
# (fuera del cierre de dependencias declarado en los __manifest__) ni se usan en el código, y compara
# memoria/arranque/CPU contra la base completa (r3_med_base). 3 repeticiones cada una.
set -euo pipefail
D=$(cd "$(dirname "$0")" && pwd); ROOT=/home/user/D_Casa_new_word
export PGPASSWORD=odoo
QUITAR="account_add_gln account_edi_ubl_cii purchase_edi_ubl_bis3 sale_edi_ubl api_doc auth_passkey auth_passkey_portal
base_import_module base_install_request calendar_sms crm_sms sale_sms stock_sms website_sms website_crm_sms sms
crm_iap_enrich crm_iap_mine iap_crm partner_autocomplete google_gmail microsoft_outlook privacy_lookup
sale_pdf_quote_builder snailmail snailmail_account spreadsheet_dashboard_account spreadsheet_dashboard_sale
spreadsheet_dashboard_stock_account spreadsheet_dashboard_website_sale spreadsheet_dashboard spreadsheet_account spreadsheet
web_unsplash website_crm website_sale_comparison_wishlist website_sale_comparison website_sale_stock_wishlist website_sale_wishlist"
if [[ "${1:-}" != "--solo-medir" ]]; then
  dropdb --if-exists -h localhost -U odoo r3_med_slim; createdb -h localhost -U odoo -T r3_med_base r3_med_slim
  LISTA=$(echo $QUITAR | tr ' ' ',')
  s=$(date +%s)
  python3 "$ROOT/vendor/odoo/odoo-bin" shell --addons-path="$ROOT/vendor/odoo/addons,$ROOT/vendor/odoo/odoo/addons,$ROOT/addons" \
    --db_host=localhost --db_user=odoo --db_password=odoo -d r3_med_slim --http-port=8177 --log-level=warn <<PY
mods = env['ir.module.module'].search([('name', 'in', '$LISTA'.split(',')), ('state', '=', 'installed')])
print('desinstalando', len(mods))
mods.button_immediate_uninstall()
env.cr.commit()
PY
  echo "desinstalacion_s=$(( $(date +%s) - s ))"
  psql -h localhost -U odoo -d r3_med_slim -Atc "select count(*) from ir_module_module where state='installed'"
  psql -h localhost -U odoo -d r3_med_slim -Atc "select name from ir_module_module where state='installed' and name like 'dcasa%' or name='website_dcasa' and state='installed'" | paste -sd' '
  psql -h localhost -U odoo -d r3_med_slim -Atqc "delete from ir_attachment where url like '/web/assets/%'"
  psql -h localhost -U odoo -d r3_med_base -Atqc "select 1" >/dev/null
fi
for db in r3_med_base r3_med_slim; do
  for rep in 1 2 3; do
    T0=$(date +%s.%N)
    PID=$(DB=$db PGPORT=5432 TAG=slim_${db}_$rep "$D/odoo_run.sh" 8177 0 1 32)
    python3 "$D/medir.py" esperar http://127.0.0.1:8177/ 300 >/dev/null
    arr=$(echo "$(date +%s.%N) - $T0" | bc)
    sleep 10; reposo=$(python3 "$D/medir.py" mem $PID)
    DB=$db python3 "$D/medir.py" calentar http://127.0.0.1:8177 >/dev/null; DB=$db python3 "$D/medir.py" calentar http://127.0.0.1:8177 >/dev/null
    sleep 2; cal=$(python3 "$D/medir.py" mem $PID)
    lat=$(DB=$db python3 "$D/medir.py" lat http://127.0.0.1:8177 $PID 20)
    echo "db=$db rep=$rep arranque_s=$arr reposo=$reposo caliente=$cal"
    echo "   lat=$lat"
    kill $PID; sleep 3
  done
done
