from __future__ import annotations

from tests.conftest import PAGE_HEIGHT, PAGE_WIDTH, upload


def test_lens_returns_regions_for_an_image(client, page_image):
    response = client.post("/api/lens", files=upload(page_image))
    assert response.status_code == 200

    body = response.json()
    assert body["image_width"] == PAGE_WIDTH
    assert body["image_height"] == PAGE_HEIGHT
    assert body["engine"]["is_mock"] is True
    assert len(body["regions"]) > 0
    assert "CTC" in body["full_text"]


def test_lens_regions_stay_inside_the_image(client, page_image):
    """The overlay maths assumes coordinates are in-bounds source pixels."""
    body = client.post("/api/lens", files=upload(page_image)).json()

    for region in body["regions"]:
        box = region["quad"]["bbox"]
        assert box["x"] >= 0
        assert box["y"] >= 0
        assert box["x"] + box["width"] <= PAGE_WIDTH + 1
        assert box["y"] + box["height"] <= PAGE_HEIGHT + 1
        assert 0.0 <= region["confidence"] <= 1.0


def test_lens_exercises_rotated_regions(client, page_image):
    """At least one region must be slanted, or the frontend's rotation path
    never gets tested against mock data."""
    body = client.post("/api/lens", files=upload(page_image)).json()
    angles = [abs(region["quad"]["angle_deg"]) for region in body["regions"]]
    assert max(angles) > 0.1


def test_lens_is_deterministic(client, page_image):
    first = client.post("/api/lens", files=upload(page_image)).json()
    second = client.post("/api/lens", files=upload(page_image)).json()
    assert [r["quad"] for r in first["regions"]] == [r["quad"] for r in second["regions"]]


def test_lens_rejects_non_images(client):
    response = client.post("/api/lens", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 415


def test_lens_rejects_empty_uploads(client):
    response = client.post("/api/lens", files={"file": ("page.png", b"", "image/png")})
    assert response.status_code == 400


def test_lens_rejects_undecodable_images(client):
    response = client.post("/api/lens", files={"file": ("page.png", b"not-a-png", "image/png")})
    assert response.status_code == 400
