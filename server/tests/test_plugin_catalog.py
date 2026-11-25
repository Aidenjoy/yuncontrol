"""Publication boundaries and the exact upstream desktop catalog wire format."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_server.infra.db.schema import plugin_catalog_flow, plugin_catalog_info
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import func, select
from test_backend_mvp import auth_headers, make_client

ITEM = {
    "id": "test-plugin",
    "name": "dsh-plugin-example",
    "displayName": "Example",
    "summary": "Example plugin",
    "latestVersion": "1.0.0",
    "package": {"registry": "npm", "name": "dsh-plugin-example"},
    "categories": ["tools"],
}


def test_catalog_publication_and_permissions(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SERVER_PLUGIN_ORIGIN", "https://control.example.com")
    client = make_client(tmp_path)
    admin = auth_headers(client)
    member = auth_headers(client, user_id="member")
    for headers in ({}, member):
        assert client.get("/admin/plugins", headers=headers).status_code in (401, 403)
        assert client.post(
            "/admin/plugins", headers=headers, json={"item": ITEM}
        ).status_code in (401, 403)
    created = client.post("/admin/plugins", headers=admin, json={"item": ITEM})
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["status"] == "draft"
    public = "/api/v2/plugins/search"
    assert client.get(public).json()["items"] == []
    assert (
        client.patch(
            "/admin/plugins/" + record["id"],
            headers=admin,
            json={"status": "published"},
        ).status_code
        == 200
    )
    page = client.get(public, params={"q": "Example", "category": "tools", "limit": 1})
    assert page.status_code == 200, page.text
    assert page.json()["items"] == [ITEM]
    assert page.headers["cache-control"] == "no-store"
    schemas = Path(__file__).parents[1] / "agent_server/core/plugin_schemas"
    for name, response in [
        ("catalog-provider-page", page),
        ("catalog-source", client.get("/api/v2/plugins/config")),
    ]:
        Draft202012Validator(
            json.loads((schemas / (name + ".schema.json")).read_text()),
            format_checker=FormatChecker(),
        ).validate(response.json())
    assert (
        client.patch(
            "/admin/plugins/" + record["id"], headers=admin, json={"status": "draft"}
        ).status_code
        == 200
    )
    hidden = client.get(public)
    assert hidden.json()["items"] == []
    assert hidden.json()["revision"] != page.json()["revision"]
    assert (
        client.delete("/admin/plugins/" + record["id"], headers=admin).status_code
        == 200
    )
    assert client.get("/admin/plugins", headers=admin).json()["total"] == 0


def test_import_is_atomic_and_preserves_switch(tmp_path):
    client = make_client(tmp_path)
    admin = auth_headers(client)
    bad = client.post(
        "/admin/plugins/import",
        headers=admin,
        json={"items": [{"item": ITEM}, {"item": {"name": "invalid"}}]},
    )
    assert bad.status_code == 422
    assert client.get("/admin/plugins", headers=admin).json()["total"] == 0
    result = client.post(
        "/admin/plugins/import", headers=admin, json={"items": [{"item": ITEM}]}
    )
    assert result.status_code == 200, result.text
    record = result.json()[0]
    assert record["status"] == "draft"
    client.patch(
        "/admin/plugins/" + record["id"], headers=admin, json={"status": "published"}
    )
    assert (
        client.post(
            "/admin/plugins/import", headers=admin, json={"items": [{"item": ITEM}]}
        ).json()[0]["status"]
        == "published"
    )
    assert (
        client.put("/admin/plugins/999", headers=admin, json={"item": ITEM}).status_code
        == 404
    )
    assert (
        client.put(
            "/admin/plugins/" + record["id"],
            headers=admin,
            json={"item": {**ITEM, "id": "different"}},
        ).status_code
        == 422
    )


def test_concurrent_import_is_idempotent_and_audited(tmp_path):
    client = make_client(tmp_path)
    admin = auth_headers(client)

    def create(_):
        return client.post("/admin/plugins", headers=admin, json={"item": ITEM})

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(create, range(8)))
    assert all(result.status_code == 201 for result in results), [
        r.text for r in results
    ]
    assert len({r.json()["id"] for r in results}) == 1

    async def counts():
        async with client.app.state.store._engine.connect() as conn:
            return (
                await conn.scalar(
                    select(func.count()).select_from(plugin_catalog_info)
                ),
                await conn.scalar(
                    select(func.count()).select_from(plugin_catalog_flow)
                ),
            )

    assert asyncio.run(counts()) == (1, 8)


def test_live_filter_on_old_cursor_and_literal_search(tmp_path):
    client = make_client(tmp_path)
    admin = auth_headers(client)
    ids = []
    for index in range(3):
        item = {
            **ITEM,
            "id": f"plugin-{index}",
            "name": f"example-{index}",
            "package": {"registry": "npm", "name": f"example-{index}"},
        }
        record = client.post(
            "/admin/plugins", headers=admin, json={"item": item}
        ).json()
        ids.append(record["id"])
        client.patch(
            "/admin/plugins/" + record["id"],
            headers=admin,
            json={"status": "published"},
        )
    public = "/api/v2/plugins/search"
    first = client.get(public, params={"limit": 1}).json()
    cursor = first["page"]["nextCursor"]
    client.patch("/admin/plugins/" + ids[1], headers=admin, json={"status": "draft"})
    page = client.get(public, params={"limit": 1, "cursor": cursor}).json()
    assert [item["package"]["name"] for item in page["items"]] == ["example-2"]
    assert page["page"]["total"] == 2
    assert client.get(public, params={"q": "%"}).json()["items"] == []
    assert client.get(public, params={"cursor": cursor, "limit": 2}).status_code == 422


def test_protocol_validation_and_disabled_identity_reimport(tmp_path, monkeypatch):
    """Invalid optional protocol values cannot poison the desktop index; restoring remains a draft."""
    client = make_client(tmp_path)
    admin = auth_headers(client)
    for item in (
        {**ITEM, "updatedAt": "not-a-date"},
        {
            **ITEM,
            "repository": {
                "url": "https://github.com/owner/repo",
                "subdirectory": "../escape",
            },
        },
        {**ITEM, "repository": {"url": "https://github.com/owner"}},
        {
            **ITEM,
            "repository": {
                "url": "https://github.com/owner/repo",
                "subdirectory": "%ZZ",
            },
        },
    ):
        assert (
            client.post(
                "/admin/plugins", headers=admin, json={"item": item}
            ).status_code
            == 422
        )
    repository_item = {
        **ITEM,
        "id": "repo-only",
        "repository": {"url": "https://github.com/example/plugin"},
    }
    repository_item.pop("package")
    record = client.post(
        "/admin/plugins", headers=admin, json={"item": repository_item}
    )
    assert record.status_code == 201, record.text
    identifier = record.json()["id"]
    client.patch(
        "/admin/plugins/" + identifier, headers=admin, json={"status": "published"}
    )
    assert (
        client.get(
            "/api/v2/plugins/search", params={"category": ["tools", "missing"]}
        ).json()["items"]
        == []
    )
    assert (
        client.get("/api/v2/plugins/search", params={"limit": 101}).status_code == 422
    )
    client.delete("/admin/plugins/" + identifier, headers=admin)
    restored = client.post(
        "/admin/plugins", headers=admin, json={"item": repository_item}
    ).json()
    assert restored["id"] == identifier
    assert restored["status"] == "draft"
    assert (
        client.patch(
            "/admin/plugins/999999999999999999999999",
            headers=admin,
            json={"status": "published"},
        ).status_code
        == 422
    )
    monkeypatch.setenv("AGENT_SERVER_PLUGIN_ORIGIN", "https://host:invalid")
    assert client.get("/api/v2/plugins/config").status_code == 503
