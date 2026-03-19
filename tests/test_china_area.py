from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_china_provinces_and_cities():
    r = client.get("/api/v1/addresses/china/provinces")
    assert r.status_code == 200
    provinces = r.json()["data"]
    assert len(provinces) > 0
    assert "adcode" in provinces[0]
    assert "name" in provinces[0]

    province_adcode = provinces[0]["adcode"]
    cities_r = client.get("/api/v1/addresses/china/cities", params={"province_adcode": province_adcode})
    assert cities_r.status_code == 200
    assert isinstance(cities_r.json()["data"], list)
