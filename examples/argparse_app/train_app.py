import examples.myapp.pipeline_params as pipeline  # registers @tunable
from jsonargparse import ArgumentParser  # could be argparse as well

from tunablex import use_config
from tunablex.runtime import defaults_for_apps
from tunablex.runtime import load_app_config
from tunablex.runtime import schema_for_apps
from tunablex.runtime import write_schema

if __name__ == "__main__":
    parser = ArgumentParser(prog="train_app")
    parser.add_argument("--config", help="Path to train_config.json")
    parser.add_argument(
        "--gen-schema", action="store_true", help="Generate JSON Schema & defaults for the 'train' app and exit"
    )
    parser.add_argument(
        "--schema-prefix", default="train_config", help="Prefix for generated files when using --gen-schema"
    )
    args = parser.parse_args()

    if args.gen_schema:
        schema = schema_for_apps("train")
        defaults = defaults_for_apps("train")
        write_schema(args.schema_prefix, schema, defaults)
        print(f"Wrote {args.schema_prefix}.schema.json and {args.schema_prefix}.json")
    else:
        cfg = load_app_config(app="train", json_path=args.config)
        with use_config(cfg):
            pipeline.train_main()
