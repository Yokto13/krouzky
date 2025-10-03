# Krouzky — Preference votes visualizer

A small Dash app that visualizes candidate preference votes and preference shares per region or party using data parsed from the Czech election XML.

There is currently no mapping from numbers to parties or to candidates, so this must be done manually.


## Running it

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Set the correct year in the URL in main.py.

Run it; it will print a localhost URL where the dashboard is available:

```bash
uv run python main.py
```