from pathlib import Path

import pytest

from src.data.qlib_client import QlibDataProvider


QLIB_DATA = Path(r"D:\Quant\data\qlib_bin")


@pytest.mark.integration
@pytest.mark.skipif(not QLIB_DATA.exists(), reason="local Qlib data is unavailable")
def test_qlib_calendar_and_features():
    provider = QlibDataProvider(QLIB_DATA)
    calendar = provider.calendar()
    features = provider.features(["SH600000"], ["$open", "$close", "$volume"])
    assert len(calendar) > 1000
    assert not features.empty
    assert list(features.columns) == ["$open", "$close", "$volume"]
    assert features.dropna().shape[0] > 100

