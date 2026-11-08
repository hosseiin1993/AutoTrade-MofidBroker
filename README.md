# autotrade-mofid

Python library for **buy and sell** limit orders on Mofid EasyTrader.

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
| `Order` / `place_order` / `with_account` | Lower-level control |
| `OrderError` | Bad arguments |
| `TradeError` | Broker rejected or did not keep the order |

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
