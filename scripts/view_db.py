#!/usr/bin/env python3
"""
Simple script to view SQLite database contents.
Usage: python scripts/view_db.py [database_path] [table_name] [limit]
"""
import sys
import sqlite3
from pathlib import Path
from tabulate import tabulate

def view_table(db_path: str, table_name: str = None, limit: int = 20):
    """View database table contents."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get list of tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    if not table_name:
        print(f"Available tables in {db_path}:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  - {table} ({count} rows)")
        return
    
    if table_name not in tables:
        print(f"Error: Table '{table_name}' not found.")
        print(f"Available tables: {', '.join(tables)}")
        return
    
    # Get table schema
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Get data
    query = f"SELECT * FROM {table_name} LIMIT {limit}"
    cursor.execute(query)
    rows = cursor.fetchall()
    
    if not rows:
        print(f"Table '{table_name}' is empty.")
        return
    
    # Convert to list of dicts for tabulate
    data = [dict(row) for row in rows]
    
    # Print table
    print(f"\n{table_name} (showing {len(rows)} of {limit} rows):")
    print("=" * 80)
    print(tabulate(data, headers="keys", tablefmt="grid", maxcolwidths=30))
    
    # Get total count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    total = cursor.fetchone()[0]
    print(f"\nTotal rows: {total}")
    
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/view_db.py <database_path> [table_name] [limit]")
        print("\nExamples:")
        print("  python scripts/view_db.py data/pc_parts.db")
        print("  python scripts/view_db.py data/pc_parts.db pc_parts 10")
        sys.exit(1)
    
    db_path = sys.argv[1]
    table_name = sys.argv[2] if len(sys.argv) > 2 else None
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    
    if not Path(db_path).exists():
        print(f"Error: Database file '{db_path}' not found.")
        sys.exit(1)
    
    view_table(db_path, table_name, limit)


