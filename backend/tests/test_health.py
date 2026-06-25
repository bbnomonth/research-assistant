def test_health_reports_database_and_model_configuration(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "model_configured": False,
        "ocr_configured": True,
    }


def test_local_frontend_cors_preflight(client) -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://127.0.0.1:5173"
    )

    fallback_port = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert fallback_port.status_code == 200
    assert (
        fallback_port.headers["access-control-allow-origin"]
        == "http://localhost:5174"
    )
