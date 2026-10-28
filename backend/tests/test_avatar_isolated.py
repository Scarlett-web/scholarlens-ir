"""Avatar decoding and owner boundaries without a running Elasticsearch service."""
from io import BytesIO

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
import pytest

from backend.accounts import Store, router


@pytest.fixture
def avatar_api(tmp_path):
    store = Store(str(tmp_path))

    def no_paper(_):
        raise HTTPException(404)

    app = FastAPI()
    app.include_router(router(store, no_paper))
    with TestClient(app) as client:
        def login(username):
            body = {"username": username, "password": "isolated-avatar-test-password"}
            assert client.post("/api/auth/register", json=body).status_code == 201
            result = client.post("/api/auth/login", json=body)
            assert result.status_code == 200
            return {"Authorization": "Bearer " + result.json()["access_token"]}

        yield client, login("image_reader_a"), login("image_reader_b")


@pytest.mark.parametrize("image_format,extension,mime", [("PNG", ".png", "image/png"), ("JPEG", ".jpg", "image/jpeg")])
def test_avatar_reencodes_supported_pixels_and_retains_owner_boundary(avatar_api, image_format, extension, mime):
    client, owner, other = avatar_api
    data = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "not retained")
    Image.new("RGB", (32, 24), (40, 90, 130)).save(data, format=image_format, pnginfo=metadata)
    payload = {"file": ("portrait" + extension, data.getvalue(), mime)}
    assert client.post("/api/me/avatar", files=payload).status_code == 401
    assert client.post("/api/me/avatar", headers=owner, files=payload).status_code == 200
    response = client.get("/api/me/avatar", headers=owner)
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    with Image.open(BytesIO(response.content)) as image:
        assert image.format == "PNG" and image.mode == "RGB" and image.size == (32, 24)
        assert "Comment" not in image.info
    assert client.get("/api/me/avatar", headers=other).status_code == 404
    assert client.get("/api/me/avatar").status_code == 401


def test_avatar_rejects_corrupt_mislabeled_and_excess_pixel_images(avatar_api):
    client, owner, _ = avatar_api
    invalid = [("bad.png", b"\x89PNG\r\n\x1a\ninvalid", "image/png"), ("fake.png", b"GIF89a", "image/png")]
    large = BytesIO()
    Image.new("RGB", (2000, 2001)).save(large, format="PNG")
    invalid.append(("pixels.png", large.getvalue(), "image/png"))
    for filename, data, mime in invalid:
        response = client.post("/api/me/avatar", headers=owner, files={"file": (filename, data, mime)})
        assert response.status_code == 400
    assert client.get("/api/me/avatar", headers=owner).status_code == 404
