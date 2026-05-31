"""Create database tables. Idempotent."""
from creative_director.storage.db import init_db


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
