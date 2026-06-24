from fastapi import Request

from research_agent.db.engine import Database


def get_database(request: Request) -> Database:
    return request.app.state.database

