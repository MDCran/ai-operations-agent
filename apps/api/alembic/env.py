from alembic import context
from app.db.session import engine
from app.models.entities import Base


def include_object(object_, name, type_, reflected, compare_to):
    # LangGraph's PostgreSQL checkpointer owns these tables; they are not part
    # of this application's SQLAlchemy metadata or Alembic migrations.
    if type_ == "table" and name.startswith("checkpoint"):
        return False
    if type_ == "index" and getattr(getattr(object_, "table", None), "name", "").startswith("checkpoint"):
        return False
    return True


with engine.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()
