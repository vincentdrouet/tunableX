from jsonargparse import ArgumentParser  # could be argparse as well
from tunablex import use_config
from tunablex.runtime import load_app_config
import examples.myapp.pipeline as pipeline  # registers @tunable

if __name__ == "__main__":
    parser = ArgumentParser(prog="train_app")
    parser.add_argument("--config", required=True, help="Path to train_config.json")
    args = parser.parse_args()

    cfg = load_app_config(app="train", json_path=args.config)
    with use_config(cfg):
        pipeline.train_main()
