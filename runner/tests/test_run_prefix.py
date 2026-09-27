"""PH_RUN_PREFIX: the run id's prefix (kaggle/ runs as "kaggle-YYYYMMDD"); the default stays "oracle"."""

from datetime import UTC, datetime

from scheduler.config import Config
from scheduler.run import run_day


def test_default_prefix_is_oracle():
    run_id, start = run_day(Config.from_env({}), datetime(2026, 9, 27, 3, 0, tzinfo=UTC))
    assert run_id == "oracle-20260927" and start == datetime(2026, 9, 27, 0, 15, tzinfo=UTC)


def test_prefix_and_start_from_env():
    cfg = Config.from_env({"PH_RUN_PREFIX": "kaggle", "PH_RUN_START_UTC": "21:40"})
    run_id, start = run_day(cfg, datetime(2026, 9, 27, 21, 40, 5, tzinfo=UTC))
    assert run_id == "kaggle-20260927" and start == datetime(2026, 9, 27, 21, 40, tzinfo=UTC)
