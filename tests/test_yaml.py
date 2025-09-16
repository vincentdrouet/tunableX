
import pytest

YAML_CONTENT = """preprocess:
  dropna: true
  normalize: minmax
  clip_outliers: 2.5
model:
  hidden_units: 512
  dropout: 0.1
train:
  epochs: 42
  batch_size: 16
  optimizer: sgd
"""


@pytest.mark.skipif(pytest.importorskip("yaml") is None, reason="PyYAML not installed")
def test_yaml_config_end_to_end(tmp_path, run_example):
    cfg = tmp_path / "train_config.yaml"
    cfg.write_text(YAML_CONTENT)
    code, out, err = run_example(
        "examples/argparse_trace/train_trace.py",
        ["--config", str(cfg)],
    )
    assert code == 0, err
    assert "build_model 512 0.1" in out
    assert "train 42 16 sgd" in out
