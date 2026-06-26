from research_agent.repositories.conversations import ConversationRepository
from research_agent.services.research_diagnosis import is_framework_final_plan
from research_agent.services.topic_guidance import is_topic_guidance_final_plan


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
    assert "event: token" in body
    assert "event: framework_card_offer" not in body
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


def test_framework_final_plan_detection_is_conservative() -> None:
    assert not is_framework_final_plan("请先说明你的研究对象是什么？")
    assert is_framework_final_plan(
        "最终方案如下。\n"
        "题目优化建议：基于机器学习的车辆路径优化研究。\n"
        "研究问题：如何提升路径优化效率？\n"
        "核心论证逻辑：问题界定、模型构建、算法设计和实验验证。\n"
        "章节结构：第一章 绪论；第二章 文献综述；第三章 方法设计。\n"
        "每章写作重点：围绕问题逐章展开。\n"
        "可能的研究方法与创新点：对比实验与算法改进。"
    )


def test_framework_card_requires_final_plan(client) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"content": "请帮我搭建车辆路径优化论文框架"},
    ) as response:
        body = "".join(response.iter_text())

    project_id = body.split('"project_id": "')[1].split('"')[0]
    session_id = body.split('"session_id": "')[1].split('"')[0]
    response = client.post(
        "/api/chat/framework/card",
        json={"project_id": project_id, "session_id": session_id},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "尚未生成最终方案，暂不能整理为框架卡片。"


def test_framework_card_can_be_created_after_final_plan(client) -> None:
    database = client.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        project, session = repository.ensure_conversation(None, None)
        repository.add_message(session.id, "user", "请帮我搭建论文框架")
        repository.add_message(
            session.id,
            "assistant",
            (
                "最终方案如下。\n"
                "题目优化建议：基于机器学习的车辆路径优化研究。\n"
                "研究问题：如何提升路径优化效率？\n"
                "核心论证逻辑：问题界定、模型构建、算法设计和实验验证。\n"
                "章节结构：第一章 绪论；第二章 文献综述；第三章 方法设计。\n"
                "每章写作重点：围绕问题逐章展开。\n"
                "可能的研究方法与创新点：对比实验与算法改进。"
            ),
            mode="framework_building",
        )
        db.commit()
        project_id = project.id
        session_id = session.id

    response = client.post(
        "/api/chat/framework/card",
        json={"project_id": project_id, "session_id": session_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "framework_card"
    assert payload["title"] == "基于机器学习的车辆路径优化研究"


def test_topic_guidance_final_plan_detection_is_conservative() -> None:
    # Short 追问不应触发
    assert not is_topic_guidance_final_plan("你更想研究哪个具体场景？")
    # 新格式，含方向名称等新关键词
    assert is_topic_guidance_final_plan(
        "以下是我的选题方案。\n"
        "方向一：基于强化学习的城市配送路径优化。\n"
        "核心研究问题：如何利用强化学习提升多约束城市配送路径的求解效率？\n"
        "推荐依据：学生具备运筹学基础，数据资源可通过企业合作获取。\n"
        "方向二：考虑碳排放的绿色车辆路径问题。\n"
        "核心研究问题：如何在路径优化中平衡成本与碳排放？\n"
        "推荐依据：与碳中和政策契合，文献基础扎实。\n"
        "整体选型建议：若侧重理论深度，优先选方向一；若偏重实践落地，选方向二。"
    )


def test_topic_guidance_card_requires_final_plan(client) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"content": "请帮我找一个机器学习方向的论文选题"},
    ) as response:
        body = "".join(response.iter_text())

    project_id = body.split('"project_id": "')[1].split('"')[0]
    session_id = body.split('"session_id": "')[1].split('"')[0]
    response = client.post(
        "/api/chat/topic/card",
        json={"project_id": project_id, "session_id": session_id},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "尚未生成最终选题方案，暂不能整理为选题卡片。"


def test_topic_guidance_card_can_be_created_after_final_plan(client) -> None:
    database = client.app.state.database
    with database.session_factory() as db:
        repository = ConversationRepository(db)
        project, session = repository.ensure_conversation(None, None)
        repository.add_message(session.id, "user", "请帮我找选题")
        repository.add_message(
            session.id,
            "assistant",
            (
                "以下是我的选题方案。\n"
                "方向一：基于强化学习的城市配送路径优化。\n"
                "核心研究问题：如何利用强化学习提升多约束城市配送路径的求解效率？\n"
                "推荐依据：学生具备运筹学基础，数据资源可通过企业合作获取。\n"
                "方向二：考虑碳排放的绿色车辆路径问题。\n"
                "核心研究问题：如何在路径优化中平衡成本与碳排放？\n"
                "推荐依据：与碳中和政策契合，文献基础扎实。\n"
                "整体选型建议：若侧重理论深度，优先选方向一；若偏重实践落地，选方向二。"
            ),
            mode="topic_guidance",
        )
        db.commit()
        project_id = project.id
        session_id = session.id

    response = client.post(
        "/api/chat/topic/card",
        json={"project_id": project_id, "session_id": session_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "topic_guidance_plan"
    assert payload["title"] == "选题方案"


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
