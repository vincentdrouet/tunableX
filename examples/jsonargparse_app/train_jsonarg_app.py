from jsonargparse import ArgumentParser
from tunablex import use_config
from tunablex.runtime import make_app_config_for
from tunablex.cli_helpers import add_flags_by_app, build_cfg_from_file_and_args
import examples.myapp.pipeline as pipeline  # registers @tunable

if __name__ == "__main__":
    APP = "train"
    AppConfig = make_app_config_for(APP)

    parser = ArgumentParser(prog="train_jsonarg_app")
    parser.add_argument("--config", help="Path to train_config.json (optional)")

    # auto-generate flags --section.field for this app
    add_flags_by_app(parser, APP)

    args = parser.parse_args()

    # merge: defaults <- file (optional) <- CLI flags
    cfg_dict = build_cfg_from_file_and_args(AppConfig, args, config_attr="config")
    cfg = AppConfig.model_validate(cfg_dict)

    with use_config(cfg):
        pipeline.train_main()
