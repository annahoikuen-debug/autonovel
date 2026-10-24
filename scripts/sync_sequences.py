import os
from sqlalchemy import text, create_engine


def sync_sequences():
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" in url and not url.startswith("postgresql+psycopg2") and not url.startswith("postgresql+asyncpg"):
        url = url.replace("postgresql://", "postgresql+psycopg2://")
    elif "asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")

    engine = create_engine(url)
    with engine.connect() as conn:
        seqs = conn.execute(
            text("""
            SELECT s.relname AS seq, t.relname AS tbl, a.attname AS col
            FROM pg_class s
            JOIN pg_depend d ON d.objid = s.oid
            JOIN pg_class t ON t.oid = d.refobjid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
            WHERE s.relkind = 'S' AND t.relkind = 'r'
        """)
        ).fetchall()
        for seq, tbl, col in seqs:
            max_val = conn.execute(text(f'SELECT COALESCE(MAX("{col}"), 0) FROM "{tbl}"')).scalar()
            conn.execute(text(f"SELECT setval('{seq}', {max(max_val, 1) + 1})"))
            print(f"Synced {seq} to {max(max_val, 1) + 1}")
        conn.commit()
    print("All sequences synced!")


if __name__ == "__main__":
    sync_sequences()
