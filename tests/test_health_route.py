from starlette.testclient import TestClient

import tax_http


def test_health_uses_cloud_run_safe_path():
    server = tax_http.make_server()
    app = server.streamable_http_app()
    with TestClient(app) as client:
        response = client.get("/health")
        reserved = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "tools": len(server._tool_manager.list_tools()),
        "law_lookup": bool(tax_http.tax_server.LAW_OC),
    }
    assert reserved.status_code == 404
