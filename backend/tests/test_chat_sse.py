def test_chat_endpoint_streams_sse_and_persists_ids(client) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"content": "什么是运筹学"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: mode" in body
    assert '"mode": "general_qa"' in body
    assert "event: token" in body
    assert "event: done" in body
    assert '"project_id":' in body
    assert '"session_id":' in body


def test_literature_discovery_streams_real_candidate_structure(client) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"content": "帮我搜索车辆路径优化论文"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"mode": "literature_discovery"' in body
    assert body.count("event: stage") == 4
    assert "event: search_results" in body
    assert '"arxiv_id": "2401.00001"' in body
    assert "event: done" in body


def test_research_diagnosis_streams_artifact_event(client) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"content": "诊断我的车辆路径优化选题和研究框架"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"mode": "research_diagnosis"' in body
    assert body.count("event: stage") == 3
    assert "event: artifact" in body
    assert '"artifact_type": "research_diagnosis"' in body
    assert "event: done" in body


def test_paper_reading_requires_explicit_paper_id(client) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "content": "请引导我精读这篇论文",
            "mode_override": "paper_reading",
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"mode": "paper_reading"' in body
    assert "event: error" in body
    assert "PAPER_READING_REQUIRES_PAPER" in body
