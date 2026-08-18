from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.daily_city_weather import CityCodeIndex, DailyInjectionState  # noqa: E402

AMAP_CITY_CODE_CSV_PATH = PLUGIN_ROOT / "cs" / "AMap_adcode_citycode.csv"


@pytest.fixture(scope="module")
def city_index():
    return CityCodeIndex(AMAP_CITY_CODE_CSV_PATH)


@pytest.mark.parametrize(
    ("area", "expected"),
    [
        ("现居四川-成都", ("成都市", "510100")),
        ("现居成都", ("成都市", "510100")),
        ("四川 成都", ("成都市", "510100")),
        ("成都市", ("成都市", "510100")),
        ("现居上海", ("上海市", "310000")),
        ("现居北京", ("北京市", "110000")),
        ("中国四川省成都市武侯区", ("武侯区", "510107")),
        ("吉林省吉林市", ("吉林市", "220200")),
        ("现居台湾", ("台湾省", "710000")),
        ("现居台湾省", ("台湾省", "710000")),
        ("现居吉林", ("吉林省", "220000")),
        ("现居香港特别行政区", ("香港特别行政区", "810000")),
        ("现居香港", ("香港特别行政区", "810000")),
        ("现居四川", ("四川省", "510000")),
        ("现居四川-阿坝", ("阿坝藏族羌族自治州", "513200")),
        ("现居阿坝州", ("阿坝藏族羌族自治州", "513200")),
        ("现居海南州", ("海南藏族自治州", "632500")),
        ("现居河北-辛集", ("辛集市", "130181")),
        ("现居长安", None),
        ("None", None),
        (None, None),
        ("保密", None),
        ("", None),
    ],
)
def test_extract_city(city_index, area, expected):
    assert city_index.extract_city(area) == expected


def test_daily_injection_state(tmp_path):
    async def run():
        state = DailyInjectionState(
            tmp_path / "state.sqlite3",
            ZoneInfo("Asia/Shanghai"),
        )
        try:
            assert await state.try_mark_injected("123456") is True
            assert await state.try_mark_injected("123456") is False
            assert await state.try_mark_injected("654321") is True
        finally:
            await state.close()

    asyncio.run(run())
