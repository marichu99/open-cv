def test_reference_data_endpoints_are_cacheable(client, geo):
    """Static reference data (geography, positions) is safe for a shared
    CDN to cache — these routes carry no auth and no per-user data, see
    app/utils/caching.py."""
    resp = client.get("/api/geography/counties")
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "public, max-age=3600"

    resp = client.get("/api/positions")
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "public, max-age=3600"


def test_live_results_endpoints_use_a_short_cache(client, geo):
    """Tally results change as submissions come in, so the cache is short —
    long enough to absorb a traffic spike, short enough to stay near-real-time."""
    position_id = geo["positions"]["president"]

    resp = client.get("/api/tally/positions")
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "public, max-age=5"

    resp = client.get("/api/tally/summary", query_string={"position_id": position_id})
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "public, max-age=5"
