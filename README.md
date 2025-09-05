# tunableX

Function-first **tunable parameters** for Python apps — with **automatic JSON & JSON Schema**, **per-executable** composition (via tags) or **dynamic** composition (via call-graph **tracing**), and **runtime auto-injection**.

## Key API
- `@tunable(...)` — declare which parameters are user-tunable (per function).
- `schema_for_apps(*apps)` / `defaults_for_apps(*apps)` — by app tags.
- `schema_by_trace(entrypoint)` / `make_app_config_for_entry(entrypoint)` — by tracing (no tags needed).
- `use_config(cfg)` — injects sections into all decorated functions during the run.
- `load_app_config(app, path)` / `load_config_for_entry(entry, path)` — validate JSON against the composed model.

See `examples/` for:
- argparse + app tags
- argparse + tracing (no app)
- jsonargparse + app tags
- jsonargparse + tracing (no app)
