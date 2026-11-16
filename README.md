# autotrade-mofid

Python library for **buy, sell, edit, and cancel** limit orders on Mofid EasyTrader.

```python
from autotrade import buy, sell

buy("فولاد", 10, dry_run=True)          # prepare only
buy("تمشک", 92, price_mode="fixed", price=54370)
sell("تمشک", 92, price_mode="fixed", price=54360)
```

Login uses Playwright; orders go over EasyTrader’s unofficial MTS HTTP API.

> Automates real money. Start with `dry_run=True`. Use at your own risk.

## Install into another project

```bash
pip install autotrade-mofid
playwright install chrome
```

Optional CLI (`python -m autotrade …`):

```bash
pip install "autotrade-mofid[cli]"
```

Set credentials in the environment or a `.env` next to your app:

```bash
export MOFID_USER=…
export MOFID_PASS=…
# or: export AUTOTRADE_ENV=/path/to/.env
```

Or pass them per call:

```python
from autotrade import buy

buy("فولاد", 1, dry_run=True, username="09…", password="…")
```

## API

| Call | Purpose |
|------|---------|
| `buy(symbol, qty, **opts)` | Buy helper |
| `sell(symbol, qty, **opts)` | Sell helper |
| `list_orders(**opts)` | Open and today's orders |
| `edit_order(order_id, **opts)` | Modify the unfilled remainder |
| `cancel_order(order_id, **opts)` | Cancel, then confirm |
| `Order` / `place_order` / `with_account` | Lower-level control |
| `OrderError` | Bad arguments, or the order cannot be edited or cancelled |
| `TradeError` | Broker rejected the request, or a cancel was not confirmed |

Common options for `buy` / `sell`:

- `price_mode` — `auto` (default), `ceiling`, `floor`, `reference`, `fixed`
- `price` — Rial; required for `fixed`
- `target_time` — `"now"` (default) or `"HH:MM:SS"` on the broker clock
- `dry_run` — prepare only, no submit
- `username` / `password` — both together, or omit both and use env / `.env`

```python
from autotrade import Order, get_settings, place_order, with_account

account = with_account(get_settings())
order = Order.resolve(
    account,
    side="buy",
    symbol="فولاد",
    quantity=10,
    price_mode="auto",
    target_time="08:44:58",
    dry_run=True,
)
place_order(order, account)
```

## Orders, edit, and cancel

```bash
python -m autotrade orders
python -m autotrade edit --order-id ID --price-mode ceiling
python -m autotrade edit --order-id ID -p 4540 -q 10 --dry-run
python -m autotrade cancel --order-id ID
python -m autotrade cancel --order-id ID --dry-run
```

`orders` prints id, symbol, side, qty, filled, price, and status for the broker's open and today's order list.

`edit` changes only the unfilled remainder. A fully executed or cancelled order is refused before any modify request. `--price-mode` uses the same ceiling, floor, reference, and fixed prices as buy/sell (`auto` follows the order's side). The new price must sit in the symbol's daily band, the open quantity must match the lot size (and the price step, when the symbol has one), and the open notional must be at least 5,000,000 Rial. `--dry-run` prints the request and does not send it.

`cancel` calls the delete endpoint once, then reads the order list. Success means the order is gone or its status is cancelled; the filled quantity is reported either way. If the broker accepts the cancel and the order is still open, the command stops and does not send the cancel again.

```python
from autotrade import cancel_order, edit_order, list_orders

list_orders()
edit_order("1121…", price_mode="fixed", price=4540, quantity=10, dry_run=True)
cancel_order("1121…", dry_run=True)
```

Exit code `2` is a bad request (missing id, order not open). Exit code `1` is a broker rejection or a cancel that could not be confirmed.

### Endpoints

EasyTrader 2.6.1 sends these from the order ticket. Login still harvests the bearer token; these calls are plain HTTP, same as buy and sell.

| Action | Request | Body |
|--------|---------|------|
| List | `GET /core/api/order` | — |
| Edit | `PUT /core/api/v2/order` | `{ "modifyOrder": { "parentId": "<current order id>", "id": null, "price", "quantity", "side", "validityType", "createDateTime", "commission", "symbolIsin", "symbolName", "orderModelType": 1, "totalValue", "orderFrom": 34 } }` |
| Cancel | `DELETE /core/api/v2/delete-order` | `{ "orderId": "<id>", "orderFrom": 34 }` |

`quantity` on an edit is the new open quantity (the unfilled remainder, or `-q`). `parentId` is the id of the order being replaced. The web app leaves `id` null and does not send the host serial (`hon`). A create-shaped body (`{"order": ...}` without `parentId`) is what the broker rejects as a missing parent order id.

## Develop this repo

```bash
python3.15 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chrome
cp .env.example .env
pytest -q
```

If Chrome is missing, install Chromium and switch `channel="chrome"` →
`channel="chromium"` in `autotrade/browser.py`.

## How it works

1. Reuse a cached JWT, or log in with Playwright and harvest `Authorization: Bearer …`
2. Resolve symbol → ISIN, live quote, commission
3. Wait for the broker clock when `target_time` is not `"now"`
4. Submit `POST /core/api/v2/order` until accepted (or a hard rejection)
5. Treat success as order still on the book or cash moved

## Licence

MIT
