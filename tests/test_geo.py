import pytest

from overlook.geo import find_country, haversine_km, mean_lat_lon


def test_haversine_london_paris():
    assert float(haversine_km(51.5074, -0.1278, 48.8566, 2.3522)) == pytest.approx(344, abs=3)


def test_haversine_is_zero_for_same_point():
    assert float(haversine_km(10, 20, 10, 20)) == 0.0


def test_mean_lat_lon_across_dateline():
    lat, lon = mean_lat_lon([0, 0], [179, -179])
    assert lat == pytest.approx(0, abs=1e-6)
    assert abs(lon) == pytest.approx(180, abs=1e-6)


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Cholera – Sudan", "Sudan"),
        ("Avian Influenza A(H5N1) – Cambodia", "Cambodia"),
        ("Ebola disease caused by Sudan ebolavirus – Uganda", "Uganda"),  # disease name contains a country
        ("Measles – Democratic Republic of the Congo", "Democratic Republic of the Congo"),
        ("Mpox – Papua New Guinea", "Papua New Guinea"),
        ("Yellow fever – Türkiye", "Turkey"),
        ("Influenza – Viet Nam", "Vietnam"),
        ("Cholera – Guinea-Bissau", "Guinea-Bissau"),
    ],
)
def test_find_country(title, expected):
    found = find_country(title)
    assert found is not None and found[0] == expected


def test_find_country_returns_none_when_absent():
    assert find_country("Global situation update") is None


def test_find_country_respects_word_boundaries():
    assert find_country("Romania outbreak")[0] == "Romania"  # not "Oman"
    assert find_country("Nigeria – Lassa fever")[0] == "Nigeria"  # not "Niger"
