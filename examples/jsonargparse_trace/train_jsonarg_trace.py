from jsonargparse import ArgumentParser
from tunablex import use_config
from tunablex.runtime import make_app_config_for_entry
from tunablex.cli_helpers import add_flags_by_entry, build_cfg_from_file_and_args
import examples.myapp.pipeline as pipeline  # registers @tunable

if __name__ == "__main__":
    AppConfig = make_app_config_for_entry(pipeline.train_main)

    parser = ArgumentParser(prog="train_jsonarg_trace")
    parser.add_argument("--config", help="Path to train_config.json (optional)")

    # auto-generate flags --section.field for the traced entrypoint (no app tags)
    add_flags_by_entry(parser, pipeline.train_main)

    args = parser.parse_args()

    cfg_dict = build_cfg_from_file_and_args(AppConfig, args, config_attr="config")
    cfg = AppConfig.model_validate(cfg_dict)

    with use_config(cfg):
        pipeline.train_main()
