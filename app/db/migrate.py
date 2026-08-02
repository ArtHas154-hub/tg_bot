import asyncio
from alembic import command
from alembic.config import Config


def run_migrations() -> None:
    alembic_cfg = Config('alembic.ini')
    command.upgrade(alembic_cfg, 'head')


if __name__ == '__main__':
    asyncio.run(asyncio.to_thread(run_migrations))
