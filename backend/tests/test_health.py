def test_health_reports_database_and_model_configuration(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "model_configured": False,
        "ocr_configured": True,
    }
