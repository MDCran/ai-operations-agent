from alembic.config import Config
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import text

from alembic import command
from app.core.config import settings
from app.db.session import engine


def initialize():
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    command.upgrade(Config("alembic.ini"), "head")
    with PostgresSaver.from_conn_string(settings().postgres_dsn) as saver:
        saver.setup()


if __name__ == "__main__":
    initialize()
