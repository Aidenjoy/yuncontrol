"""Release registry: administrator CRUD, one record per platform, public check."""

from test_backend_mvp import auth_headers, make_client

MACOS_ARM = {
    "platform": "desktop-macos-arm64",
    "version": "1.10.0",
    "downloadUrl": "https://dl.example.com/yundashi-1.10.0-arm64.dmg",
    "fileName": "yundashi-1.10.0-arm64.dmg",
    "notes": "Fixes the onboarding layout.",
    "published": True,
}

ALL_PLATFORMS = (
    "desktop-macos-arm64",
    "desktop-macos-x64",
    "desktop-windows",
    "android",
    "ios",
)


def payload(**overrides):
    """One valid record with per-test overrides."""
    return {**MACOS_ARM, **overrides}


def test_release_registry_requires_admin_and_validates_input(tmp_path):
    client = make_client(tmp_path)
    admin = auth_headers(client)
    member = auth_headers(client, user_id="member")
    for headers in ({}, member):
        assert client.get("/admin/releases", headers=headers).status_code in (401, 403)
        assert (
            client.post("/admin/releases", headers=headers, json=payload()).status_code
            in (401, 403)
        )
        assert client.delete("/admin/releases/1", headers=headers).status_code in (
            401,
            403,
        )

    # Unknown platforms, unparsable versions, and credential-bearing URLs are refused.
    for bad_platform in ("windows", "desktop-macos", "desktop-linux"):
        assert (
            client.post(
                "/admin/releases",
                headers=admin,
                json=payload(platform=bad_platform),
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/admin/releases", headers=admin, json=payload(version="latest")
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/admin/releases",
            headers=admin,
            json=payload(downloadUrl="ftp://dl.example.com/app.dmg"),
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/admin/releases",
            headers=admin,
            json=payload(downloadUrl="https://user:secret@dl.example.com/app.dmg"),
        ).status_code
        == 422
    )


def test_one_release_per_platform_and_reuse_after_delete(tmp_path):
    client = make_client(tmp_path)
    admin = auth_headers(client)

    created = client.post(
        "/admin/releases", headers=admin, json=payload(published=False)
    )
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["platform"] == "desktop-macos-arm64"
    assert record["published"] is False
    assert record["fileName"] == "yundashi-1.10.0-arm64.dmg"

    listed = client.get("/admin/releases", headers=admin).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == record["id"]

    # The platform is taken even when the version differs: one record only.
    duplicate = client.post(
        "/admin/releases", headers=admin, json=payload(version="1.11.0")
    )
    assert duplicate.status_code == 409, duplicate.text
    assert "1.10.0" in duplicate.json()["detail"]

    # Shipping a new build means editing the existing row.
    updated = client.put(
        f"/admin/releases/{record['id']}",
        headers=admin,
        json=payload(
            version="1.10.1",
            downloadUrl="https://dl.example.com/yundashi-1.10.1-arm64.dmg",
            published=True,
        ),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == "1.10.1"
    assert updated.json()["published"] is True
    assert client.get("/admin/releases", headers=admin).json()["total"] == 1

    # Moving a record onto an occupied platform is refused as well.
    client.post(
        "/admin/releases",
        headers=admin,
        json=payload(platform="desktop-macos-x64", version="1.10.1"),
    )
    moved = client.put(
        f"/admin/releases/{record['id']}",
        headers=admin,
        json=payload(platform="desktop-macos-x64", version="1.10.1"),
    )
    assert moved.status_code == 409, moved.text

    assert (
        client.delete(f"/admin/releases/{record['id']}", headers=admin).status_code
        == 204
    )
    # Only the Intel record survives the deletion of the Apple Silicon one.
    remaining = client.get("/admin/releases", headers=admin).json()
    assert remaining["total"] == 1
    assert remaining["items"][0]["platform"] == "desktop-macos-x64"
    assert (
        client.put(
            f"/admin/releases/{record['id']}", headers=admin, json=payload()
        ).status_code
        == 404
    )

    # The row was soft-deleted, so the platform can be registered again.
    assert client.post("/admin/releases", headers=admin, json=payload()).status_code == 201


def test_every_platform_can_hold_its_own_single_release(tmp_path):
    client = make_client(tmp_path)
    admin = auth_headers(client)

    for platform in ALL_PLATFORMS:
        response = client.post(
            "/admin/releases",
            headers=admin,
            json=payload(platform=platform, version="2.0.0"),
        )
        assert response.status_code == 201, (platform, response.text)

    assert client.get("/admin/releases", headers=admin).json()["total"] == len(
        ALL_PLATFORMS
    )

    # macOS keeps two independent builds: Apple Silicon and Intel.
    macos = client.get(
        "/admin/releases?platform=desktop-macos-arm64", headers=admin
    ).json()
    assert [item["platform"] for item in macos["items"]] == ["desktop-macos-arm64"]
    assert macos["total"] == 1


def test_public_latest_returns_only_published_platforms(tmp_path):
    client = make_client(tmp_path)
    admin = auth_headers(client)
    for record in (
        payload(platform="desktop-macos-arm64", version="1.10.0", published=True),
        # Intel build exists but is still a draft, so it stays invisible.
        payload(platform="desktop-macos-x64", version="1.10.0", published=False),
        payload(
            platform="android",
            version="3.1.0",
            downloadUrl="https://dl.example.com/yundashi-3.1.0.apk",
            fileName="yundashi-3.1.0.apk",
            published=True,
        ),
    ):
        assert (
            client.post("/admin/releases", headers=admin, json=record).status_code
            == 201
        )

    everything = client.get("/api/v2/releases/latest")
    assert everything.status_code == 200
    by_platform = {item["platform"]: item for item in everything.json()["items"]}
    assert set(by_platform) == {"desktop-macos-arm64", "android"}
    assert by_platform["desktop-macos-arm64"]["version"] == "1.10.0"
    assert by_platform["android"]["version"] == "3.1.0"

    arm = client.get(
        "/api/v2/releases/latest?platform=desktop-macos-arm64"
    ).json()["items"]
    assert [item["version"] for item in arm] == ["1.10.0"]

    # A draft is neither listed nor selectable by platform.
    assert (
        client.get("/api/v2/releases/latest?platform=desktop-macos-x64").json()["items"]
        == []
    )
    assert client.get("/api/v2/releases/latest?platform=ios").json()["items"] == []


def test_version_check_compares_versions_and_links_the_download(tmp_path):
    client = make_client(tmp_path)
    admin = auth_headers(client)
    assert client.post("/admin/releases", headers=admin, json=payload()).status_code == 201

    older = client.get(
        "/api/v2/releases/check?platform=desktop-macos-arm64&currentVersion=1.9.9"
    ).json()
    assert older["latestVersion"] == "1.10.0"
    assert older["updateAvailable"] is True
    assert (
        older["downloadUrl"]
        == "https://dl.example.com/yundashi-1.10.0-arm64.dmg"
    )
    assert older["fileName"] == "yundashi-1.10.0-arm64.dmg"

    current = client.get(
        "/api/v2/releases/check?platform=desktop-macos-arm64&currentVersion=1.10.0"
    ).json()
    assert current["updateAvailable"] is False

    # A final build is newer than its own pre-release.
    assert (
        client.get(
            "/api/v2/releases/check"
            "?platform=desktop-macos-arm64&currentVersion=1.10.0-beta.1"
        ).json()["updateAvailable"]
        is True
    )
    # Without a local version the client is told the newest build exists.
    assert (
        client.get(
            "/api/v2/releases/check?platform=desktop-macos-arm64"
        ).json()["updateAvailable"]
        is True
    )
    assert (
        client.get(
            "/api/v2/releases/check"
            "?platform=desktop-macos-arm64&currentVersion=newest"
        ).status_code
        == 400
    )

    empty = client.get(
        "/api/v2/releases/check?platform=ios&currentVersion=1.0.0"
    ).json()
    assert empty["latestVersion"] is None
    assert empty["updateAvailable"] is False
    assert empty["downloadUrl"] is None
