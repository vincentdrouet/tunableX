"""Pipeline using centralized TunableParameters classes.

Functions access values via class attributes (e.g., Model.hidden_units) and
are registered by inferring namespace from default expressions like
`param=Model.hidden_units`.
"""

from __future__ import annotations

from tunablex import tunable

from .params import Main
from .params import Model
from .params import Preprocess
from .params import Serve
from .params import Train


@tunable("hidden_units", "dropout", apps=("train",))
def build_model(hidden_units=Model.hidden_units, dropout=Main.dropout):
    """Build the model using centralized parameters."""
    print("build_model", hidden_units, dropout)
    return "model"


@tunable("epochs", "batch_size", "optimizer", apps=("train",))
def train(epochs=Train.epochs, batch_size=Train.batch_size, optimizer=Train.optimizer):
    """Train the model using centralized parameters."""
    print("train", epochs, batch_size, optimizer)


@tunable("dropna", "normalize", "clip_outliers", apps=("train", "serve"))
def preprocess(
    path: str, dropna=Preprocess.dropna, normalize=Preprocess.normalize, clip_outliers=Preprocess.clip_outliers
):
    """Preprocess the dataset using centralized parameters."""
    print("preprocess", dropna, normalize, clip_outliers, "on", path)
    return "clean"


@tunable("port", "workers", apps=("serve",))
def serve_api(port=Serve.port, workers=Serve.workers):
    print("serve_api", port, workers)


def train_main():
    """End-to-end train entrypoint using centralized params."""
    preprocess("/data/train.csv")
    build_model()
    train()


def serve_main():
    preprocess("/data/live.csv")
    serve_api()
