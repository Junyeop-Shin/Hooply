"""선수 상세의 세부 능력은 절대 점수가 아니라 팀 내 상대 위치(백분위 · 상/중/하)로 내려간다."""

from tests.test_ranking_assignment import ROSTER, club  # noqa: F401 — 12명 팀 픽스처 재사용

API = "/api/v1"


def test_axis_ranks_are_relative_to_team(client, club):
    m = club["manager"]
    ranks = {}
    for pid in club["pid"].values():
        s = client.get(f"{API}/players/{pid}/stats", headers=m).json()
        assert set(s["skill_axes_rank"]) == {"shooting", "ball_handling", "passing", "defense", "rebound_post", "stamina"}
        ranks[pid] = s["skill_axes_rank"]
    for axis in ("shooting", "rebound_post"):
        rows = [r[axis] for r in ranks.values()]
        assert all(r["sample"] >= 4 and r["level"] in ("HIGH", "MID", "LOW") and 0 <= r["percentile"] <= 100 for r in rows)
    # 픽스처는 슛 답이 전원 같다 → 전부 중간 (동점은 위·아래를 만들지 않는다)
    assert {r["shooting"]["level"] for r in ranks.values()} == {"MID"}
    # 골밑은 키·5번 가능 여부가 달라 상위와 하위가 모두 나온다
    assert {r["rebound_post"]["level"] for r in ranks.values()} >= {"HIGH", "LOW"}
    # 플레이어 본인에게는 수치도 위치도 내려가지 않는다 (FR-28)
    me = club["members"][1]  # [0] 은 매니저
    mine = client.get(f"{API}/players/{club['pid'][ROSTER[1][0]]}/stats", headers=me).json()
    assert mine["skill_axes"] == {} and mine["skill_axes_rank"] == {}
