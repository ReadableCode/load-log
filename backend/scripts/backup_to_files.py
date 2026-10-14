# %%
"""Back up every load_log table to CSV + Parquet (plus DDL and a manifest).

Read-only: issues only SELECT / information_schema queries. Never mutates the
database. Writes a timestamped folder under load-log/data/ so existing backups
and generated files are never overwritten.

Run:
    cd backend && uv run --with pyarrow python scripts/backup_to_files.py
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../load-log
DATA_DIR = REPO_ROOT / "data"


# %%
def load_pg_env() -> dict:
    """Parse only POSTGRES_* keys out of the repo .env (a symlink full of other
    secrets — we touch nothing but the Postgres connection values)."""
    env_path = REPO_ROOT / ".env"
    wanted = (
        "POSTGRES_URL",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    )
    out: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key in wanted:
            out[key] = val.strip().strip('"').strip("'")
    out.setdefault("POSTGRES_DB", "apps")
    out.setdefault("POSTGRES_PORT", "5432")
    missing = [
        k
        for k in ("POSTGRES_URL", "POSTGRES_USER", "POSTGRES_PASSWORD")
        if k not in out
    ]
    if missing:
        raise SystemExit(f"Missing required env keys: {missing}")
    return out


# %%
def json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    return str(o)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


# %%
def main() -> None:
    env = load_pg_env()
    conn = psycopg2.connect(
        host=env["POSTGRES_URL"],
        port=env["POSTGRES_PORT"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
        dbname=env["POSTGRES_DB"],
        connect_timeout=10,
    )
    conn.set_session(readonly=True, autocommit=True)
    print(
        f"Connected to {env['POSTGRES_URL']}:{env['POSTGRES_PORT']}/"
        f"{env['POSTGRES_DB']} as {env['POSTGRES_USER']} (read-only)"
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = DATA_DIR / f"backup_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=False)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
            """)
        tables = cur.fetchall()

    manifest = {
        "created_at": datetime.now().isoformat(),
        "source": f"{env['POSTGRES_URL']}:{env['POSTGRES_PORT']}/{env['POSTGRES_DB']}",
        "tables": [],
    }
    ddl_lines: list[str] = []

    for schema, table in tables:
        fq = f"{schema}.{table}"
        df = pd.read_sql(f'SELECT * FROM "{schema}"."{table}"', conn)

        csv_path = out_dir / f"{schema}.{table}.csv"
        pq_path = out_dir / f"{schema}.{table}.parquet"
        df.to_csv(csv_path, index=False)
        df.to_parquet(pq_path, index=False, engine="pyarrow")

        # Column DDL straight from information_schema for a human-readable record.
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema, table),
            )
            cols = cur.fetchall()
        ddl_lines.append(f"-- {fq} ({len(df)} rows)")
        ddl_lines.append(f"CREATE TABLE {fq} (")
        col_defs = []
        for name, dtype, nullable, default in cols:
            piece = f"    {name} {dtype}"
            if default:
                piece += f" DEFAULT {default}"
            if nullable == "NO":
                piece += " NOT NULL"
            col_defs.append(piece)
        ddl_lines.append(",\n".join(col_defs))
        ddl_lines.append(");\n")

        manifest["tables"].append(
            {
                "schema": schema,
                "table": table,
                "rows": int(len(df)),
                "columns": list(df.columns),
                "csv": csv_path.name,
                "parquet": pq_path.name,
                "csv_sha256": sha256(csv_path),
                "parquet_sha256": sha256(pq_path),
            }
        )
        print(f"  {fq:<32} {len(df):>8} rows -> CSV + Parquet")

    (out_dir / "schema.sql").write_text("\n".join(ddl_lines))
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=json_default)
    )
    conn.close()

    print(f"\nBackup complete: {out_dir}")
    print(
        f"  {len(manifest['tables'])} tables, "
        f"{sum(t['rows'] for t in manifest['tables'])} total rows"
    )


if __name__ == "__main__":
    main()
