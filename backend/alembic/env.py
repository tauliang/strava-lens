from alembic import context
from strava_lens.db import engine
from strava_lens.models import Base

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
