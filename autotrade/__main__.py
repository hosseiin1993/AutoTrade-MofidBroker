def main() -> None:
    try:
        from autotrade.cli import app
    except ModuleNotFoundError as exc:
        if exc.name != "typer":
            raise
        raise SystemExit(
            "CLI extras missing. Install with: pip install 'autotrade-mofid[cli]'"
        ) from exc
    app()


if __name__ == "__main__":
    main()
