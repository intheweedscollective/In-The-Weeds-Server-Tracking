"""
Database connection module - Shared across all routes to avoid circular imports.
"""

from motor.motor_asyncio import AsyncIOMotorClient
import os

# Database connection (initialized once, shared globally)
_db = None
_client = None

def get_database():
    """Get the database instance. Lazy initialization."""
    global _db, _client
    if _db is None:
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "staff_score_db")
        _client = AsyncIOMotorClient(mongo_url)
        _db = _client[db_name]
    return _db

def close_database():
    """Close the database connection."""
    global _client
    if _client:
        _client.close()
        _client = None

# Alias for backwards compatibility
db = property(lambda self: get_database())
