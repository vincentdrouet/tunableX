"""
Example: Generate JSON Schema and default config by tracing execution of an entrypoint.

Usage:
  python examples/trace_generate_schema.py --entry train --prefix train_config
  -> writes train_config.schema.json and train_config.json

  python examples/trace_generate_schema.py --entry serve --prefix serve_config
  -> writes serve_config.schema.json and serve_config.json
"""
from __future__ import annotations
import argparse
from tunablex.runtime import schema_by_trace, write_schema
import examples.myapp.pipeline as pipeline  # registers @tunable


def main():
    parser = argparse.ArgumentParser(prog="trace_generate_schema")
    parser.add_argument(
        "--entry",
        choices=["train", "serve"],
        default="train",
        help="Which entrypoint to trace (train_main or serve_main)",
    )
    parser.add_argument(
        "--prefix",
        default="config",
        help="Output file prefix (writes <prefix>.schema.json and <prefix>.json)",
    )
    args = parser.parse_args()

    entry_fn = pipeline.train_main if args.entry == "train" else pipeline.serve_main
    schema, defaults, namespaces = schema_by_trace(entry_fn)
    write_schema(args.prefix, schema, defaults)

    print(f"Traced namespaces: {sorted(namespaces)}")
    print(f"Wrote {args.prefix}.schema.json and {args.prefix}.json")


if __name__ == "__main__":
    main()
