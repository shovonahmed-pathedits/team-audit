# Debug Investigation Log: Fulfillment Search & Debug Logging Failure

**Date:** 2026-08-12
**Target File:** `DisputeFiller.pyw`, `debug_fulfillment.py`

## Root Cause Analysis

### 1. Debug Script Bug (`debug_fulfillment.py`)
- `debug_fulfillment.py` line 36 passed `order_id=443065` in the GET query string.
- Tista's backend form expects `order_name` (e.g., `order_name=%23443065`).
- Passing `order_id` caused Tista to ignore the parameter and return a 200 OK blank form (63.8 KB), which was written to `debug_fulfillment_page.html`. This created false diagnostic logs showing no search results.

### 2. URL Parameter Encoding Issue in `DisputeFiller.pyw`
- Order numbers contain a `#` prefix (e.g. `#443065`).
- Unencoded `#` (`order_name=#443065`) is parsed as a URL fragment, truncating the query parameter to `order_name=` and producing 0 results.
- Proper URL encoding (`order_name=%23443065`) returns the full fulfillment table and radio inputs.

### 3. Log System Deficiencies
- `_get` and `_post` silently caught `requests.RequestException` and returned `None`.
- `_find_fulfillment_details` failure produced a single generic message without logging HTTP status, URL, response length, or HTML preview.
- The debug preview output path was hardcoded to `e:\Mohsin678...`.

## Fix Plan
1. Update `debug_fulfillment.py` to use `order_name=%23443065`.
2. Update `DisputeFiller.pyw` search request URL construction to ensure `#` is cleanly stripped and URL-encoded as `%23`.
3. Enhance `_get` and `_post` error logging to capture and report network exceptions.
4. Improve `_find_fulfillment_details` error logging and dynamic debug file writing path.
