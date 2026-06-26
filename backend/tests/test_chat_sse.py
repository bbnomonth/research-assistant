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
    assert '"mode": "other"' in body
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


def test_framework_building_streams_reply(client) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"content": "请帮我搭建车辆路径优化论文框架"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"mode": "framework_building"' in body
    assert "event: token" not in body
    assert body.count("event: done") == 1
    assert "event: done" in body


def test_framework_building_followup_inherits_mode(client) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"content": "请帮我搭建车辆路径优化论文框架"},
    ) as response:
        first_body = "".join(response.iter_text())

    project_id = first_body.split('"project_id": "')[1].split('"')[0]
    session_id = first_body.split('"session_id": "')[1].split('"')[0]

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "content": "灾后救援",
            "project_id": project_id,
            "session_id": session_id,
        },
    ) as response:
        second_body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"mode": "framework_building"' in second_body
    assert '"mode": "other"' not in second_body


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
