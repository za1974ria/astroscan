# AstroScan Bridge Agent — TB-3.1 prototype

Read-only telemetry adapter that will eventually run on an amateur
astronomer's Windows PC and forward device telemetry to AstroScan.

**TB-3.1 scope (this codebase)**: skeleton + mock adapter + tests only.

  - No Alpaca real-network discovery yet  (TB-3.2)
  - No ASCOM COM (Windows native) yet     (TB-3.3)
  - No cloud transmission yet             (TB-4)
  - No installer yet                       (TB-5)

## Safety contract (V1)

The agent is **read-only by construction**. The guarantees enforced by
this codebase and the CI safety tests:

1. The base adapter declares ONLY three public methods:
   `discover()`, `read_device(id)`, `close()`.
2. No code path invokes any telescope movement: AST and tokenizer audits
   refuse the identifiers `slew`, `park`, `goto`, `move`, `pulse`,
   `sync`, `motor` outside an explicit predicate whitelist
   (`is_slewing`, `is_parked`, `is_moving`, `is_at_park`, `is_at_home`,
   `is_tracking`).
3. The `safety.readonly_filter.enforce_property_allowlist(kind, name)`
   function refuses any property name outside the per-kind allow-list
   declared in `adapters/base.py`. This is the chokepoint future
   adapters will route through.
4. No outbound network calls in TB-3.1 — `requests` is not even in the
   dependency list.
5. Local audit at `~/.astroscan/agent.jsonl` (append-only JSONL).

## Folder tree

```
telescope_bridge_agent/
├── pyproject.toml
├── README.md
├── astroscan_bridge/
│   ├── __init__.py
│   ├── __main__.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── mock.py
│   ├── safety/
│   │   ├── __init__.py
│   │   ├── readonly_filter.py
│   │   └── audit.py
│   └── service/
│       ├── __init__.py
│       └── poller.py
└── tests/
    ├── __init__.py
    ├── test_safety_ast.py
    └── test_mock_adapter.py
```

## Quick start

```bash
# 1. (Optional) install in editable mode for dev:
pip install -e ".[dev]"

# 2. Discover mock devices:
python -m astroscan_bridge --driver mock discover

# 3. Read one device:
python -m astroscan_bridge --driver mock telemetry --device-id mock:telescope:0

# 4. Continuous polling (Ctrl-C to stop):
python -m astroscan_bridge --driver mock poll --interval 5

# 5. Audit log:
tail -f ~/.astroscan/agent.jsonl
```

## Tests

```bash
pytest tests/ -v
```

Two test files:
- `test_safety_ast.py` — refuses any forbidden operation identifier
  outside the predicate whitelist. Also refuses `requests.put/post/...`
  style calls if a future Alpaca adapter is added.
- `test_mock_adapter.py` — smoke contract for `MockAdapter`: device
  count, telemetry shape, public method surface, allow-list coverage.

## CLI reference

```
astroscan-bridge --driver mock <command>

commands:
  discover                   enumerate devices and exit
  telemetry --device-id ID   read one device's current telemetry
  poll [--interval SECS]     continuous polling loop
```

In TB-3.1 the only supported `--driver` value is `mock`. Asking for
`alpaca` or `ascom` raises a clear `ValueError` documenting which phase
introduces them.

## What this prototype is NOT

- Not a control panel — never sends commands.
- Not a guiding/imaging tool — does not capture frames.
- Not a network service — does not open ports, does not phone home.
- Not a packaged release — no MSI/deb, no service registration.

Once TB-3.2 / TB-3.3 land, Alpaca discovery and ASCOM COM enumeration
will plug into the same read-only contract enforced here.
