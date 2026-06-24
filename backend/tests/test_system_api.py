def test_system_settings_are_redacted(client) -> None:
    response = client.get("/api/system/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_configured"] is False
    assert payload["qwen_model"] == "qwen3.7-plus"
    assert "api_key" not in response.text.lower()
    assert "DASHSCOPE" not in response.text


def test_system_storage_check_is_writable_and_cleans_probe(client) -> None:
    response = client.post("/api/system/check-storage")

    assert response.status_code == 200
    assert response.json()["available"] is True
    upload_dir = client.app.state.settings.resolved_upload_dir
    assert not list(upload_dir.glob(".storage-probe-*"))


def test_system_ocr_check_calls_configured_service(client) -> None:
    response = client.post("/api/system/check-ocr")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["available"] is True


def test_system_model_check_uses_gateway_without_exposing_prompt(client) -> None:
    response = client.post("/api/system/check-model")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["available"] is True
    assert "测试回答" not in response.text
