"""프로필 사진 — 업로드·교체·삭제, 주소 키 확인, 팀원 카드에 사진 주소가 실리는지 (S-17)."""

import base64

API = "/api/v1"
# 1x1 PNG
PNG = "data:image/png;base64," + base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)).decode()


def test_upload_replace_and_delete(client, signup):
    h = signup("pic@example.com", name="허재")
    assert client.get(f"{API}/me", headers=h).json()["profile_image_url"] is None

    r = client.post(f"{API}/me/avatar", json={"data_url": PNG}, headers=h)
    assert r.status_code == 200, r.text
    url = r.json()["profile_image_url"]
    assert url.startswith("/api/v1/users/") and "avatar?v=" in url

    # 주소 그대로 요청하면 이미지가 오고, 키가 없거나 틀리면 404
    img = client.get(url)  # url 은 이미 /api/v1 로 시작한다
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert "max-age" in img.headers.get("cache-control", "")
    path = url.split("?")[0]
    assert client.get(path).status_code == 404
    assert client.get(f"{path}?v=wrongkey").status_code == 404

    # 교체하면 주소(키)가 바뀐다 → 브라우저가 옛 사진을 계속 쓰지 않는다
    url2 = client.post(f"{API}/me/avatar", json={"data_url": PNG}, headers=h).json()["profile_image_url"]
    assert url2 != url
    assert client.get(url).status_code == 404  # 옛 키는 막힌다

    # 삭제하면 주소가 비고 이미지도 사라진다
    assert client.delete(f"{API}/me/avatar", headers=h).json()["profile_image_url"] is None
    assert client.get(url2).status_code == 404


def test_rejects_bad_images(client, signup):
    h = signup("bad@example.com", name="서장훈")
    for bad in ("not-a-data-url", "data:text/plain;base64,aGk=", "data:image/gif;base64,R0lGODlhAQABAAAAACw="):
        r = client.post(f"{API}/me/avatar", json={"data_url": bad}, headers=h)
        assert r.status_code == 400, bad
    big = "data:image/png;base64," + base64.b64encode(b"x" * (512 * 1024 + 10)).decode()
    r = client.post(f"{API}/me/avatar", json={"data_url": big}, headers=h)
    assert r.status_code == 400 and "KB" in r.json()["message"]


def test_team_player_cards_carry_photo(client, signup):
    """팀원 목록·참석자 등 어디서나 쓰는 PlayerCard 에 사진 주소가 실려야 아바타가 바뀐다."""
    owner = signup("owner@pic.com", name="이상민")
    team = client.post(f"{API}/teams", json={"name": "사진팀"}, headers=owner).json()
    url = client.post(f"{API}/me/avatar", json={"data_url": PNG}, headers=owner).json()["profile_image_url"]
    cards = client.get(f"{API}/teams/{team['id']}/players", headers=owner).json()["items"]
    assert cards[0]["profile_image_url"] == url
