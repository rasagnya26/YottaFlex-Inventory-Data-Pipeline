from src.generator import generate
import pandas as pd

def test_generator_is_reproducible(tmp_path):
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    generate(a, rows=25, seed=7)
    generate(b, rows=25, seed=7)
    assert pd.read_csv(a).equals(pd.read_csv(b))
