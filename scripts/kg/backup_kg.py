#!/usr/bin/env python3
"""Backup and restore Neo4j knowledge graph by namespace.

This script allows you to save the current graph state before running
potentially buggy steps, so you can restore it without rerunning step 1.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
)
LOGGER = logging.getLogger("kg_backup")


def ensure_driver(uri: str, user: str, password: str):
    if GraphDatabase is None:
        raise RuntimeError(
            "neo4j python driver is not installed. "
            "Install it with `pip install neo4j` before running the backup script."
        )
    return GraphDatabase.driver(uri, auth=(user, password))


def backup_namespace(driver, namespace: str, output_file: str) -> None:
    """Export all nodes and relationships for a namespace to a JSON file."""
    LOGGER.info("Backing up namespace '%s' to %s", namespace, output_file)
    
    with driver.session() as session:
        # Get all nodes
        nodes_result = session.run(
            """
            MATCH (n {namespace: $namespace})
            RETURN n.slug as slug, labels(n) as labels, properties(n) as props
            ORDER BY n.slug
            """,
            namespace=namespace,
        )
        nodes = []
        for record in nodes_result:
            nodes.append({
                "slug": record["slug"],
                "labels": record["labels"],
                "properties": dict(record["props"]),
            })
        
        # Get all relationships
        rels_result = session.run(
            """
            MATCH (a {namespace: $namespace})-[r {namespace: $namespace}]->(b {namespace: $namespace})
            RETURN 
                a.slug as from_slug,
                type(r) as rel_type,
                b.slug as to_slug,
                properties(r) as props
            ORDER BY a.slug, type(r), b.slug
            """,
            namespace=namespace,
        )
        relationships = []
        for record in rels_result:
            relationships.append({
                "from": record["from_slug"],
                "type": record["rel_type"],
                "to": record["to_slug"],
                "properties": dict(record["props"]),
            })
    
    backup_data = {
        "namespace": namespace,
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "nodes": nodes,
        "relationships": relationships,
    }
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)
    
    LOGGER.info(
        "Backup complete: %d nodes, %d relationships saved to %s",
        len(nodes),
        len(relationships),
        output_file,
    )


def restore_namespace(driver, backup_file: str, target_namespace: Optional[str] = None, purge_existing: bool = False) -> None:
    """Restore nodes and relationships from a backup file."""
    LOGGER.info("Restoring from backup file: %s", backup_file)
    
    backup_path = Path(backup_file)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")
    
    with open(backup_path, "r", encoding="utf-8") as f:
        backup_data = json.load(f)
    
    source_namespace = backup_data["namespace"]
    target_namespace = target_namespace or source_namespace
    
    LOGGER.info(
        "Restoring namespace '%s' -> '%s' (%d nodes, %d relationships)",
        source_namespace,
        target_namespace,
        backup_data["node_count"],
        backup_data["relationship_count"],
    )
    
    if purge_existing:
        LOGGER.info("Purging existing namespace '%s'", target_namespace)
        with driver.session() as session:
            session.run(
                "MATCH (n {namespace: $namespace}) DETACH DELETE n",
                namespace=target_namespace,
            )
    
    with driver.session() as session:
        # Restore nodes
        LOGGER.info("Restoring %d nodes...", len(backup_data["nodes"]))
        for node in backup_data["nodes"]:
            labels = ":".join(node["labels"])
            props = node["properties"].copy()
            props["namespace"] = target_namespace  # Update namespace
            
            # Build SET clause for all properties (excluding slug and namespace which are in MERGE)
            set_props = {k: v for k, v in props.items() if k not in ["slug", "namespace"]}
            if set_props:
                set_clauses = [f"n.{k} = ${k}" for k in set_props.keys()]
                set_clause = ", ".join(set_clauses)
                query = f"""
                MERGE (n:{labels} {{slug: $slug, namespace: $namespace}})
                SET {set_clause}
                """
                session.run(query, slug=node["slug"], namespace=target_namespace, **set_props)
            else:
                query = f"""
                MERGE (n:{labels} {{slug: $slug, namespace: $namespace}})
                """
                session.run(query, slug=node["slug"], namespace=target_namespace)
        
        # Restore relationships
        LOGGER.info("Restoring %d relationships...", len(backup_data["relationships"]))
        for rel in backup_data["relationships"]:
            props = rel["properties"].copy()
            props["namespace"] = target_namespace  # Update namespace
            
            # Build SET clause for relationship properties (excluding namespace which is in MERGE)
            set_props = {k: v for k, v in props.items() if k != "namespace"}
            rel_type = rel["type"]
            
            if set_props:
                set_clauses = [f"r.{k} = ${k}" for k in set_props.keys()]
                set_clause = ", ".join(set_clauses)
                query = f"""
                MATCH (a {{slug: $from_slug, namespace: $namespace}})
                MATCH (b {{slug: $to_slug, namespace: $namespace}})
                MERGE (a)-[r:{rel_type} {{namespace: $namespace}}]->(b)
                SET {set_clause}
                """
                session.run(
                    query,
                    from_slug=rel["from"],
                    to_slug=rel["to"],
                    namespace=target_namespace,
                    **set_props,
                )
            else:
                query = f"""
                MATCH (a {{slug: $from_slug, namespace: $namespace}})
                MATCH (b {{slug: $to_slug, namespace: $namespace}})
                MERGE (a)-[r:{rel_type} {{namespace: $namespace}}]->(b)
                """
                session.run(
                    query,
                    from_slug=rel["from"],
                    to_slug=rel["to"],
                    namespace=target_namespace,
                )
    
    LOGGER.info("Restore complete: namespace '%s' restored", target_namespace)


def main():
    parser = argparse.ArgumentParser(
        description="Backup or restore Neo4j knowledge graph by namespace"
    )
    parser.add_argument(
        "--neo4j-uri",
        default=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j connection URI",
    )
    parser.add_argument(
        "--neo4j-user",
        default=os.getenv("NEO4J_USER", "neo4j"),
        help="Neo4j username",
    )
    parser.add_argument(
        "--neo4j-password",
        default=os.getenv("NEO4J_PASSWORD", ""),
        help="Neo4j password",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Backup a namespace")
    backup_parser.add_argument(
        "--namespace",
        default="pc_parts",
        help="Namespace to backup (default: pc_parts)",
    )
    backup_parser.add_argument(
        "--output",
        default="data/kg_backups/pc_parts_backup.json",
        help="Output file path (default: data/kg_backups/pc_parts_backup.json)",
    )
    
    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument(
        "--backup-file",
        required=True,
        help="Path to backup JSON file",
    )
    restore_parser.add_argument(
        "--namespace",
        help="Target namespace (default: use namespace from backup)",
    )
    restore_parser.add_argument(
        "--purge",
        action="store_true",
        help="Delete existing nodes in target namespace before restoring",
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    driver = ensure_driver(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
    
    try:
        if args.command == "backup":
            backup_namespace(driver, args.namespace, args.output)
        elif args.command == "restore":
            restore_namespace(
                driver,
                args.backup_file,
                target_namespace=getattr(args, "namespace", None),
                purge_existing=args.purge,
            )
    finally:
        driver.close()


if __name__ == "__main__":
    main()

