# Sobdeall + Arophant WordPress Maintenance Implementation Plan

Date: 2026-04-23
Status: Source-verified planning draft. No production mutation has been executed yet.
Scope: `sobdeall.com.tw` (`104.199.216.115`) first, then `arophant.com` (`34.80.131.138`)
Execution Policy: atomic repair -> verification -> small rollback if needed. No bulk change waves.

## Backup

本計劃涉及 production WordPress、資料庫、外掛與背景任務狀態，因此所有 mutation 之前必須先做 baseline backup；之後每一個原子化批次都要再做 micro backup，讓回滾範圍保持最小。

### Baseline Backup 1: `sobdeall.com.tw`

```bash
ssh -i ~/.ssh/id_rsa bitnami@104.199.216.115 '
set -e
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT=/opt/bitnami/backups/manual/sobdeall_pre_maint_${TS}
mkdir -p "$BACKUP_ROOT"
cd /opt/bitnami/wordpress
/opt/bitnami/wp-cli/bin/wp db export "$BACKUP_ROOT/bitnami_wordpress.sql" --path=/opt/bitnami/wordpress
tar -czf "$BACKUP_ROOT/wp-content_and_wp-config.tgz" wp-content wp-config.php
ls -lh "$BACKUP_ROOT"
'
```

Expected result:
- 產生 `bitnami_wordpress.sql`
- 產生 `wp-content_and_wp-config.tgz`
- `ls -lh` 可見兩個檔案且大小非 0

Fail condition:
- `wp db export` 非 0 結束
- `tar` 非 0 結束
- 任一備份檔缺失或大小為 0

### Baseline Backup 2: `arophant.com`

```bash
ssh -i ~/.ssh/id_rsa bitnami@34.80.131.138 '
set -e
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT=/opt/bitnami/backups/manual/arophant_pre_maint_${TS}
mkdir -p "$BACKUP_ROOT"
cd /opt/bitnami/wordpress
/opt/bitnami/wp-cli/bin/wp db export "$BACKUP_ROOT/bitnami_wordpress.sql" --path=/opt/bitnami/wordpress
tar -czf "$BACKUP_ROOT/wp-content_and_wp-config.tgz" wp-content wp-config.php
ls -lh "$BACKUP_ROOT"
'
```

Expected result:
- 產生 `bitnami_wordpress.sql`
- 產生 `wp-content_and_wp-config.tgz`
- `ls -lh` 可見兩個檔案且大小非 0

Fail condition:
- `wp db export` 非 0 結束
- `tar` 非 0 結束
- 任一備份檔缺失或大小為 0

### Micro Backup Rule: one batch, one rollback source

- Config-only batch: 先備份 `wp-config.php` 與即將修改的單一 hotfix 檔。
- Queue-cleanup batch: 先做 DB export，不碰檔案。
- Plugin/theme batch: 先做 DB export，再打包單一 plugin/theme 目錄。
- 任一批次驗證失敗時，只回滾該批次前的 micro backup，不回滾其他批次。

## Problem list

1. **`sobdeall` production debug logging 仍開啟，且 log 檔已膨脹到會干擾維運判讀的等級**。Severity `4`, Detection `4`, Priority `16`. Evidence: E1, E2, E11.
2. **`sobdeall` 的 `pricing-deals-for-woocommerce` 與目前 WooCommerce session API 不相容，已在 production 產生 fatal path**。Severity `5`, Detection `5`, Priority `25`. Evidence: E3, E4, E5.
3. **`sobdeall` 的背景任務系統已明顯退化，包含大量 failed Action Scheduler、`hubwoo_*` 殘留任務，以及 cron `could_not_set` 錯誤**。Severity `5`, Detection `4`, Priority `20`. Evidence: E6, E7, E8, E9.
4. **`arophant` 雖未重現前台故障，但 production debug logging 與 deprecated flood 持續寫入，已形成維護債與後續升級風險**。Severity `3`, Detection `4`, Priority `12`. Evidence: E10, E12, E13, E14.
5. **兩站都存在核心 / 主題 / 外掛更新債，但 `sobdeall` 當前有 runtime 故障訊號，不能直接做 bulk upgrade**。Severity `4`, Detection `3`, Priority `12`. Evidence: E5, E6, E14, E15, E16.

## Evidence

- **E1**: `sobdeall` 的 `/opt/bitnami/wordpress/wp-config.php:83-90` 目前設定為 `WP_DEBUG=true`, `WP_DEBUG_LOG=true`, `WP_DEBUG_DISPLAY=false`。
- **E2**: `sobdeall` 的 `/opt/bitnami/wordpress/wp-content/debug.log` 目前大小為 `6.1G`。
- **E3**: `sobdeall` active plugin list 顯示 `pricing-deals-for-woocommerce 2.0.3.2` 與 `pricing-deals-pro-for-woocommerce 2.0.3` 皆為 active。
- **E4**: `/opt/bitnami/wordpress/wp-content/plugins/pricing-deals-for-woocommerce/woo-integration/vtprd-parent-cart-validation.php:3723` 會將 `vtprd_get_and_set_saved_woo_session_cart` 掛到 `woocommerce_load_cart_from_session`。
- **E5**: `/opt/bitnami/wordpress/wp-content/plugins/pricing-deals-for-woocommerce/woo-integration/vtprd-parent-functions.php:7001-7005` 直接呼叫 `WC()->session->get_saved_cart()`；`sobdeall` debug log 已記錄 `Call to undefined method WC_Session_Handler::get_saved_cart()` fatal。
- **E6**: `sobdeall` Action Scheduler 狀態為 `complete=9537`, `failed=7709`, `pending=16`。
- **E7**: `sobdeall` top failed hooks 以 `hubwoo_ecomm_deal_update=7360` 為主，另有 `hubwoo_check_logs`, `hubwoo_cron_schedule`, `hubwoo_products_sync_check`, `hubwoo_deals_sync_check`, `huwoo_abncart_clear_old_cart`。
- **E8**: `sobdeall` 在 `/opt/bitnami/wordpress/wp-content/debug.log` 中反覆記錄 `action_scheduler_run_queue` 與 `rocket_preload_process_pending` 的 `could_not_set` / `Cron 事件清單無法儲存`。
- **E9**: `sobdeall` 的大型資料表包括 `wp_postmeta 180.7MB`, `wp_wpml_mails 116.4MB`, `wp_et_divi_ab_testing_stats 70.6MB`, `wp_actionscheduler_actions 41.4MB`, `wp_hubwoo_log 31.1MB`, `wp_wpmailsmtp_debug_events 27.6MB`, `wp_options 16.7MB`。
- **E10**: `arophant` 的 `/opt/bitnami/wordpress/wp-config.php:153-160` 目前設定為 `WP_DEBUG=true`, `WP_DEBUG_LOG=true`, `WP_DEBUG_DISPLAY=false`。
- **E11**: `sobdeall` 的 `/opt/bitnami/wordpress/wp-content/mu-plugins/` 目錄已存在，且 child theme `/opt/bitnami/wordpress/wp-content/themes/an-after-builder-develop-theme/functions.php` 存在，可作為 vendor 外的熱修插入點。
- **E12**: `arophant` 的 `/opt/bitnami/wordpress/wp-content/debug.log` 目前大小為 `113M`。
- **E13**: `arophant` debug log 尾端持續出現 `admin-columns-pro` 的 `json_decode()` / iterator return type deprecated，對應 `/opt/bitnami/wordpress/wp-content/plugins/admin-columns-pro/classes/Search/Middleware/Request.php:22`。
- **E14**: `arophant` debug log 尾端持續出現 Divi Gutenberg template deprecated，對應 `/opt/bitnami/wordpress/wp-content/themes/Divi/includes/builder/feature/gutenberg/BlockTemplates.php:109`。
- **E15**: `arophant` WordPress core 目前為 `6.4.8`，可更新到 `6.9.4`；`sobdeall` WordPress core 目前為 `6.5.8`，可更新到 `6.9.4`。
- **E16**: `arophant` Action Scheduler 狀態為 `complete=1033`, `failed=38`, `pending=11`，遠低於 `sobdeall`，表示兩站現況不能用同一個更新批次處理。
- **E17**: 兩台 VM 都有足夠的 baseline backup 條件。`arophant` 根目錄剩餘 `42G`，`sobdeall` 根目錄剩餘 `43G`；兩台 VM 都有 `/opt/bitnami/wp-cli/bin/wp`、`tar`，且 `mysqldump` / `mariadb-dump` 可用。
- **E18**: `sobdeall` 使用 `wps-hide-login`，`whl_page=global-login`，因此後台 smoke test 應以 `/global-login/` 為準，而不是 `/wp-login.php`。

## Proposed changes

### Change 1: `sobdeall` Batch S1 - 關閉 production debug logging 並先把觀測噪音壓下來
Resolves Problem #1.

- 修改 `/opt/bitnami/wordpress/wp-config.php:83-90`，將 `WP_DEBUG` 與 `WP_DEBUG_LOG` 關閉，保留 `WP_DEBUG_DISPLAY=false`。
- 在 baseline backup 完成後，先將既有 `debug.log` 重新命名歸檔，再讓系統重新建立新的小型 log 檔；不要先刪檔。
- 這一批次只動 `wp-config.php` 與 `debug.log`，不碰外掛、不碰 DB。
- Verified insertion points:
  - `/opt/bitnami/wordpress/wp-config.php:83-90`
  - `/opt/bitnami/wordpress/wp-content/debug.log`

Ordering:
- 這必須是 `sobdeall` 的第一個 mutation batch，因為後面每一批都需要更乾淨的 log 觀測面。

Rollback:
- 還原本批次前備份的 `wp-config.php`。
- 若需要保留原 log 行為，將 archived `debug.log` 名稱還原。

### Change 2: `sobdeall` Batch S2 - 以 vendor 外熱修方式隔離 `pricing-deals-for-woocommerce` 的 saved-cart fatal
Resolves Problem #2.

- 不直接改 vendor plugin 檔。
- 優先方案是在 `/opt/bitnami/wordpress/wp-content/mu-plugins/` 新增單一用途熱修檔，於 plugin 載入後移除或 guard `woocommerce_load_cart_from_session -> vtprd_get_and_set_saved_woo_session_cart` 這個 hook。
- 備援方案才是修改 child theme `/opt/bitnami/wordpress/wp-content/themes/an-after-builder-develop-theme/functions.php`；仍應保持為單一、可刪除、可快速回退的 shim。
- 熱修邏輯應以「WooCommerce session handler 沒有 `get_saved_cart()` 時不執行該 hook」為原則，不做更大範圍 plugin refactor。
- Verified insertion points / dependencies:
  - Hook registration: `.../vtprd-parent-cart-validation.php:3723`
  - Fatal call: `.../vtprd-parent-functions.php:7001-7005`
  - Reversible hotfix target: `/opt/bitnami/wordpress/wp-content/mu-plugins/` or child theme `functions.php`

Ordering:
- 必須在 Batch S1 之後、Batch S3 之前。若先清 queue 而不先止血，failed actions 可能重新累積。

Rollback:
- 若使用 mu-plugin，刪除單一 hotfix 檔並還原本批次 micro backup。
- 若使用 child theme snippet，回退該 snippet 對應的單一 patch 與 micro backup。

### Change 3: `sobdeall` Batch S3 - 定向清理 orphaned / failed Action Scheduler 任務，而不是整庫大掃除
Resolves Problem #3.

- 先用 DB export 做本批次前 micro backup。
- 第一輪只處理已確認為高量且高疑似殘留的 failed hooks：
  - `hubwoo_ecomm_deal_update`
  - `hubwoo_check_logs`
  - `hubwoo_cron_schedule`
  - `hubwoo_products_sync_check`
  - `hubwoo_deals_sync_check`
  - `huwoo_abncart_clear_old_cart`
- 目前 grep 在一般 `wp-content/plugins` / `wp-content/themes` 路徑中未找到 `hubwoo_*` / `huwoo_*` hook 定義，因此執行時應先再做一次 scoped search；若仍未找到來源，將它們視為 orphaned queue，僅刪除 `failed` 狀態列，不碰 `complete` / `pending`。
- `action_scheduler/migration_hook`、`aioseo_*`、`imagify_optimize_media` 等非 orphaned hook 不在第一輪清理範圍。
- 這一批只動 Action Scheduler failed rows，不做 Divi/WPML/WP Mail SMTP 大表清理。

Ordering:
- 必須在 Batch S2 穩定後執行，否則 fatal root cause 未解，queue 仍可能重新污染。

Rollback:
- 直接回滾本批次前的 DB export。

### Change 4: `sobdeall` Batch S4 - 小批次清理膨脹表與低風險更新
Resolves Problems #1, #3, #5.

- 前置條件：
  - Batch S1-S3 已完成
  - 前台、商品頁、購物車、`/global-login/` 連續驗證通過
  - 至少一個觀察窗內不再新增 `vtprd` fatal
- 第一子批次只做低風險清理：
  - archived debug log retention
  - `wp_wpmailsmtp_debug_events`
  - 老舊 `complete` Action Scheduler rows
- 第二子批次才評估中高風險大表：
  - `wp_wpml_mails`
  - `wp_et_divi_ab_testing_stats`
  - `wp_hubwoo_log`
  這些需要先確定商業與營運是否仍需保留。
- 更新順序必須拆開：
  1. 非店務核心外掛
  2. Divi parent theme `4.27.4 -> 4.27.6`
  3. 次要 WooCommerce 周邊外掛
  4. WooCommerce 核心與其相依外掛最後再評估
- `pricing-deals-for-woocommerce` / `pricing-deals-pro-for-woocommerce` 不應與 WooCommerce core 升級合併在同一批。

Rollback:
- 每一子批次各自使用自己的 micro backup；不可共用。

### Change 5: `arophant` Batch A1 - 關閉 production debug logging 並壓制 deprecated flood
Resolves Problem #4.

- 修改 `/opt/bitnami/wordpress/wp-config.php:153-160`，將 `WP_DEBUG` 與 `WP_DEBUG_LOG` 關閉，保留 `WP_DEBUG_DISPLAY=false`。
- archived 當前 `113M` 的 debug log，讓後續再觀察是否仍有 production-visible 問題。
- 這一批只動 config 與 log，不做外掛 / 主題 / 核心更新。

Ordering:
- 必須在 `sobdeall` 穩定後進行，避免雙站同時進入維護視窗。

Rollback:
- 還原 `wp-config.php` 與 archived `debug.log`。

### Change 6: `arophant` Batch A2 - 針對相容性警訊做小波段更新，不做一次性大升級
Resolves Problems #4 and #5.

- `arophant` 的主要訊號是 compatibility debt，而不是已重現的前台 fatal。
- 首先處理已被 evidence 指到的相容性來源：
  - `admin-columns-pro`
  - Divi / Gutenberg 相容性
  - WordPress core `6.4.8 -> 6.9.4`
- 若商業版套件沒有可直接更新的 package，先用停寫 debug log 方式消除 production 噪音，再安排 vendor package refresh。
- 不把 core、Divi、商業插件放在同一個 mutation batch。

Rollback:
- 每個更新批次各自使用對應的 DB export + 單一 plugin/theme tarball。

## Verification SOP

### V0: Backup verification for both sites

1. Run the baseline backup command for the target site.
2. Confirm `ls -lh "$BACKUP_ROOT"` contains the SQL export and tarball.
3. Pass:
   - 兩個檔案都存在且大小非 0。
4. Fail:
   - 任一備份檔不存在或大小為 0。

### V1: `sobdeall` Batch S1 verification

```bash
curl -I -L -k --max-time 20 https://www.sobdeall.com.tw
curl -I -L -k --max-time 20 https://www.sobdeall.com.tw/global-login/
ssh -i ~/.ssh/id_rsa bitnami@104.199.216.115 'tail -n 20 /opt/bitnami/wordpress/wp-content/debug.log 2>/dev/null || true'
```

Pass:
- 首頁 `200`
- `/global-login/` 最終 `200`
- 不再持續寫入舊的高頻 deprecated/fatal flood

Fail:
- 首頁非 `200`
- `/global-login/` 非 `200`
- log 仍快速新增與原本同型的大量錯誤

Proves fixed:
- Problem #1

### V2: `sobdeall` Batch S2 verification

```bash
curl -I -L -k --max-time 20 https://www.sobdeall.com.tw
curl -I -L -k --max-time 20 https://www.sobdeall.com.tw/product-category/acc/
curl -I -L -k --max-time 20 https://www.sobdeall.com.tw/my-account/
ssh -i ~/.ssh/id_rsa bitnami@104.199.216.115 'grep -i "get_saved_cart\|vtprd_get_and_set_saved_woo_session_cart" /opt/bitnami/wordpress/wp-content/debug.log | tail -n 20'
```

Pass:
- 以上頁面皆可成功回應，不出現 `500`
- debug log 不再新增 `get_saved_cart()` / `vtprd_get_and_set_saved_woo_session_cart` fatal

Fail:
- 任一頁面出現 `500`
- debug log 仍新增同型 fatal

Proves fixed:
- Problem #2

### V3: `sobdeall` Batch S3 verification

```bash
ssh -i ~/.ssh/id_rsa bitnami@104.199.216.115 '
/opt/bitnami/wp-cli/bin/wp db query "SELECT status, COUNT(*) AS cnt FROM wp_actionscheduler_actions GROUP BY status ORDER BY cnt DESC;" --path=/opt/bitnami/wordpress
/opt/bitnami/wp-cli/bin/wp db query "SELECT hook, COUNT(*) AS cnt FROM wp_actionscheduler_actions WHERE status=\"failed\" GROUP BY hook ORDER BY cnt DESC LIMIT 12;" --path=/opt/bitnami/wordpress
grep -i "could_not_set\|Cron 事件清單無法儲存" /opt/bitnami/wordpress/wp-content/debug.log | tail -n 20
'
```

Pass:
- `hubwoo_*` / `huwoo_*` failed counts 顯著下降或清零
- `failed` 總量下降
- 新的 `could_not_set` 不再持續增長

Fail:
- `hubwoo_*` / `huwoo_*` failed counts 重新回升
- `failed` 總量不降反升
- cron 錯誤持續新增

Proves fixed:
- Problem #3

### V4: `sobdeall` Batch S4 verification

```bash
curl -I -L -k --max-time 20 https://www.sobdeall.com.tw
curl -I -L -k --max-time 20 https://www.sobdeall.com.tw/global-login/
ssh -i ~/.ssh/id_rsa bitnami@104.199.216.115 '
/opt/bitnami/wp-cli/bin/wp core version --path=/opt/bitnami/wordpress
/opt/bitnami/wp-cli/bin/wp plugin list --status=active --path=/opt/bitnami/wordpress --format=table
/opt/bitnami/wp-cli/bin/wp theme list --path=/opt/bitnami/wordpress --format=table
'
```

Pass:
- 前台與登入入口正常
- 只出現預期更新的版本變動
- 沒有新的 fatal / queue regression

Fail:
- 站點可用性下降
- 更新範圍超出本批次預期
- queue 或 fatal 問題復發

Proves fixed:
- Problems #1, #3, #5

### V5: `arophant` Batch A1 verification

```bash
curl -I -L -k --max-time 20 https://www.arophant.com
curl -I -L -k --max-time 20 https://www.arophant.com/wp-login.php
ssh -i ~/.ssh/id_rsa bitnami@34.80.131.138 'tail -n 20 /opt/bitnami/wordpress/wp-content/debug.log 2>/dev/null || true'
```

Pass:
- 首頁最終 `200`
- `/wp-login.php` `200`
- 不再持續寫入 deprecated flood

Fail:
- 前台或登入頁失敗
- log 仍快速增長

Proves fixed:
- Problem #4

### V6: `arophant` Batch A2 verification

```bash
curl -I -L -k --max-time 20 https://www.arophant.com
curl -I -L -k --max-time 20 https://www.arophant.com/wp-admin/
ssh -i ~/.ssh/id_rsa bitnami@34.80.131.138 '
/opt/bitnami/wp-cli/bin/wp core version --path=/opt/bitnami/wordpress
/opt/bitnami/wp-cli/bin/wp db query "SELECT status, COUNT(*) AS cnt FROM wp_actionscheduler_actions GROUP BY status ORDER BY cnt DESC;" --path=/opt/bitnami/wordpress
'
```

Pass:
- 前台與後台入口可用
- 核心版本與本批次預期一致
- Action Scheduler 沒有異常暴增

Fail:
- 前台或後台入口失敗
- 更新後新增 fatal / failed actions

Proves fixed:
- Problems #4, #5

## Automated test plan

完整自動化測試在這兩台 standalone production VM 上不可直接等同於 repo 內單元測試，原因是：
- 變更目標在 production VM，而不是本地版本化應用 repo
- 目前沒有對應 staging / clone 環境可先跑 PHPUnit 或 Playwright
- 風險主要在 runtime config、外掛 hook、Action Scheduler 與 production data

因此本計劃採用「可重複執行的命令式 smoke suite」取代傳統自動化測試：

1. **Backup smoke**
   - Target: baseline / micro backup commands
   - Assertion: SQL export 與 tarball 皆存在且大小非 0
   - Prevents regression: 無法回滾卻進入 mutation

2. **HTTP availability smoke**
   - Target:
     - `sobdeall`: `/`, `/product-category/acc/`, `/my-account/`, `/global-login/`
     - `arophant`: `/`, `/wp-login.php`, `/wp-admin/`
   - Assertion: 預期 `200` 或可接受的 `301 -> 200`
   - Prevents regression: 修復批次導致前台或後台不可用

3. **Log regression smoke**
   - Target: `debug.log` 與 Apache error log tail
   - Assertion:
     - `sobdeall` 不再新增 `get_saved_cart()` / `vtprd_*` fatal
     - `arophant` 不再新增 production flood 等級 deprecated
   - Prevents regression: 同型錯誤在修復後繼續發生

4. **Background job smoke**
   - Target: `wp_actionscheduler_actions`
   - Assertion:
     - `sobdeall` 的 targeted failed hooks 下降，不再回彈
     - `arophant` failed actions 不因更新暴增
   - Prevents regression: 背景任務汙染恢復或惡化

5. **Version drift smoke**
   - Target: `wp core version`, `wp plugin list`, `wp theme list`
   - Assertion: 只出現本批次預期的版本變更
   - Prevents regression: 一次升太多、變更範圍失控

## Risks / open questions

1. `sobdeall` 的 `hubwoo_*` / `huwoo_*` hooks 目前在一般 `wp-content/plugins` / `wp-content/themes` 路徑中未找到來源，較像 orphaned tasks；但在真正刪除 failed rows 前，仍應再做一次 scoped search，排除外掛被移到非標準路徑。
2. `pricing-deals-for-woocommerce` 的 hotfix 若直接移除 saved-cart hook，可能改變某些折扣 / abandoned cart 邏輯；因此必須先做 vendor 外 shim，而不是直接 deactivate 整個 plugin。
3. `sobdeall` 的 `wp_wpml_mails`, `wp_et_divi_ab_testing_stats`, `wp_hubwoo_log` 是否可清，需要先確認營運留存需求；這些不能在第一輪修復就直接刪。
4. `arophant` 的主要問題目前是 compatibility debt，而不是已重現的可用性故障；因此不應搶在 `sobdeall` 前做高風險升級。
5. 兩站目前都把 production debug logging 開著，執行時應預期關閉 debug 後會失去部分即時噪音線索；因此每一批次都必須先保留 archived log。
6. 本計劃目前只覆蓋 standalone VM WordPress 層維護，不包含 GCP snapshot、VM image snapshot、或外部 CDN / WAF / DNS 層的變更。
