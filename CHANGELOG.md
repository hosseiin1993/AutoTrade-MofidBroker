# Changelog

All notable changes to `autotrade-mofid` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-11-16

### Added

- List open and today's orders via `list_orders()` and `python -m autotrade orders`
- Edit the unfilled remainder of an open order via `edit_order()` and `python -m autotrade edit`
- Cancel an open order via `cancel_order()` and `python -m autotrade cancel`, with confirmation after a single DELETE
- Shared EasyTrader modify payload (`PUT /core/api/v2/order` with `modifyOrder.parentId`) and delete payload (`DELETE /core/api/v2/delete-order`)
- Edit validations: daily price band, lot size, price step, volume limits, and 5,000,000 Rial minimum notional
- Price modes on edit (`auto` / `ceiling` / `floor` / `reference` / `fixed`), matching buy/sell
- Refusal of fully filled, cancelled, and replaced `Modify` parent rows before any broker call
- Cancel wait through `OnCanceling` without sending a second delete

### Changed

- Package description and public API now cover place, edit, and cancel
- Create and modify order bodies share one field builder
- Order-state predicates live on `LiveOrder`; prepare validators are shared between buy and edit

## [0.1.1] - 2026-11-11

### Added

- First PyPI release
- `buy` / `sell` helpers and optional CLI (`autotrade-mofid[cli]`)

[0.2.0]: https://github.com/hosseiin1993/AutoTrade-MofidBroker/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/hosseiin1993/AutoTrade-MofidBroker/releases/tag/v0.1.1
