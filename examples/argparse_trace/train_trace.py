from jsonargparse import ArgumentParser
from tunablex import use_config
from tunablex.runtime import load_config_for_entry
import examples.myapp.pipeline as pipeline  # registers @tunable

if __name__ == "__main__":
    parser = ArgumentParser(prog="train_trace")
    parser.add_argument("--config", required=True, help="Path to train_config.json")
    args = parser.parse_args()

    cfg = load_config_for_entry(pipeline.train_main, args.config)  # no app tags needed
    with use_config(cfg):
        pipeline.train_main()
