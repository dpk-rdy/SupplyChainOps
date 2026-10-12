import pytest

from bid_intelligence import synth
from bid_intelligence import warehouse as W


@pytest.fixture(scope="session")
def frames():
    return synth.generate(seed=7, n_opportunities=300, n_pipeline=40)


@pytest.fixture(scope="session")
def con(frames):
    con = W.connect()
    W.load_raw(con, frames)
    W.build_marts(con, "base")
    return con
