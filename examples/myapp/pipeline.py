from __future__ import annotations
from typing import Literal
from pydantic import Field
from tunablex import tunable


@tunable(
    "dropna",
    "normalize",
    "clip_outliers",
    namespace="preprocess",
    apps=("train", "serve"),
)
def preprocess(
    path: str,
    dropna: bool = True,
    normalize: Literal["zscore", "minmax", "none"] = "zscore",
    clip_outliers: float = Field(3.0, ge=0, le=10),
):
    print("preprocess", dropna, normalize, clip_outliers, "on", path)
    return "clean"


@tunable("hidden_units", "dropout", namespace="model", apps=("train",))
def build_model(
    hidden_units: int = Field(128, ge=1), dropout: float = Field(0.2, ge=0.0, le=1.0)
):
    print("build_model", hidden_units, dropout)
    return "model"


@tunable("epochs", "batch_size", "optimizer", namespace="train", apps=("train",))
def train(
    epochs: int = Field(10, ge=1),
    batch_size: int = 32,
    optimizer: Literal["adam", "sgd"] = "adam",
):
    print("train", epochs, batch_size, optimizer)


@tunable("port", "workers", namespace="serve", apps=("serve",))
def serve_api(port: int = Field(8080, ge=1, le=65535), workers: int = Field(2, ge=1)):
    print("serve_api", port, workers)


def train_main():
    preprocess("/data/train.csv")
    build_model()
    train()


def serve_main():
    preprocess("/data/live.csv")
    serve_api()
