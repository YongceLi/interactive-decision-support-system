import sqlite3
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
load_dotenv()


uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
user = os.getenv("NEO4J_USERNAME", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "password")
# --- 1. Read from SQLite ---
conn = sqlite3.connect(os.path.join("data", "car_database.db"))
cur = conn.cursor()

cur.execute("""
    SELECT
        vm.make  AS base_make,
        vm.model AS base_model,
        mc.make  AS sim_make,
        mc.model AS sim_model
    FROM ModelComparisons mc
    JOIN VehicleModels vm ON mc.model_id = vm.id
""")
rows = cur.fetchall()
conn.close()

# --- 2. Neo4j setup ---
driver = GraphDatabase.driver(
    uri,  # adjust URI
    auth=(user, password) # change password
)

create_constraint_cypher = """
CREATE CONSTRAINT carmodel_unique IF NOT EXISTS
FOR (c:CarModel)
REQUIRE (c.make, c.model) IS UNIQUE;
"""

create_rel_cypher = """
MERGE (base:CarModel {make: $base_make, model: $base_model})
MERGE (sim :CarModel {make: $sim_make,  model: $sim_model})
MERGE (base)-[r:SIMILAR_TO]-(sim)
ON CREATE SET r.source = 'ModelComparisons';
"""

with driver.session() as session:
    # ensure constraint
    session.run(create_constraint_cypher)

    # insert in batches (simple version: one-by-one)
    for base_make, base_model, sim_make, sim_model in rows:
        try:
            session.run(
                create_rel_cypher,
                base_make=base_make,
                base_model=base_model,
                sim_make=sim_make,
                sim_model=sim_model,
            )
        except Exception as e:
            continue
driver.close()
