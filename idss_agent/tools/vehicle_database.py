"""
Vehicle database tools for safety and feature data.

Uses LangChain's SQLDatabase and SQLDatabaseToolkit to provide
SQL query access to local SQLite databases.

Note: We combine both databases into a single toolkit to avoid tool name conflicts.
SQLite ATTACH DATABASE allows querying both databases in a single connection.
"""

import os
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from sqlalchemy import text


def get_vehicle_database_tools(llm):
    """
    Get SQL tools for both vehicle databases (safety and features).

    Combines both databases using SQLite's ATTACH DATABASE feature so the agent
    can query both in a single connection without tool name conflicts.

    Safety database (safety_data table) contains NHTSA safety ratings:
    - Crash test ratings (frontal, side, rollover)
    - Safety features (airbags, ABS, ESC, backup camera)
    - Active safety systems (collision warning, lane departure, etc.)

    Feature database (feature_data table) contains EPA fuel economy data:
    - MPG ratings (city, highway, combined)
    - Fuel type and annual fuel cost
    - CO2 emissions and GHG scores
    - Engine specs, transmission, drivetrain
    - Vehicle size class

    Usage in queries:
    - Query safety_data table for safety information
    - Query feature_data table for fuel economy and features

    Args:
        llm: Language model to use for query generation

    Returns:
        List of SQL tools that can access both databases
    """
    safety_db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "safety_data.db")
    feature_db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "feature_data.db")

    if not os.path.exists(safety_db_path):
        print(f"Warning: Safety database not found at {safety_db_path}")
        return []

    if not os.path.exists(feature_db_path):
        print(f"Warning: Feature database not found at {feature_db_path}")
        return []

    # Use safety_data.db as primary and attach feature_data.db
    # This way both can be queried in a single connection
    db = SQLDatabase.from_uri(f"sqlite:///{safety_db_path}")

    # Attach the feature database so we can query both
    # The feature database will be accessible as feature_db.feature_data
    # The safety database is accessible as safety_data (no prefix needed)
    with db._engine.connect() as conn:
        conn.execute(text(f"ATTACH DATABASE '{feature_db_path}' AS feature_db"))
        conn.commit()

    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    return toolkit.get_tools()

