import hashlib
import json
import re
from typing import Any

import psycopg2
from psycopg2 import sql

from context_jobs.embeddings import embed_query
from context_jobs.ingestion.records import ensure_record_ids
from context_jobs.ingestion.types import UpsertResult
from context_jobs.retrieval.base import NormalizedMatch
from context_jobs.retrieval.filter_dialect import to_pgvector_predicate
from core.config import EMBED_MODEL


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VECTOR_DIM_RE = re.compile(r"\bvector\s*\(\s*(\d+)\s*\)", re.IGNORECASE)


class PgVectorAdapter:
    provider = "pgvector"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config) if config else {}
        self.connection_uri = self.config.get("connection_uri")
        self.table_name = self.config.get("table_name")
        self.id_column = self.config.get("id_column")
        self.embedding_column = self.config.get("embedding_column", "embedding")
        self.content_column = self.config.get("content_column", "text")
        self.metadata_column = self.config.get("metadata_column")
        self.embedding_model = self.config.get("embedding_model") or EMBED_MODEL

        if not self.connection_uri or not self.table_name:
            raise ValueError("pgvector config requires connection_uri and table_name.")
        if not self.embedding_column or not self.content_column:
            raise ValueError("pgvector config requires embedding_column and content_column.")

        self.schema_name, self.relation_name = self._parse_table_name(self.table_name)
        for identifier in [
            self.schema_name,
            self.relation_name,
            self.id_column,
            self.embedding_column,
            self.content_column,
            self.metadata_column,
        ]:
            if identifier and not _IDENTIFIER_RE.match(identifier):
                raise ValueError(
                    f"Invalid SQL identifier '{identifier}' in pgvector config. "
                    "Use letters, numbers, and underscore only."
                )

    @staticmethod
    def _parse_table_name(table_name: str) -> tuple[str | None, str]:
        parts = table_name.split(".")
        if len(parts) == 1:
            return None, parts[0]
        if len(parts) == 2:
            return parts[0], parts[1]
        raise ValueError("Invalid table_name. Use 'table' or 'schema.table'.")

    def _qualified_table(self) -> sql.Composed | sql.Identifier:
        if self.schema_name:
            return sql.SQL("{}.{}").format(
                sql.Identifier(self.schema_name), sql.Identifier(self.relation_name)
            )
        return sql.Identifier(self.relation_name)

    @staticmethod
    def _vector_literal(vec: list[float]) -> str:
        return "[" + ",".join(f"{float(v):.10f}" for v in vec) + "]"

    def _resolve_vector_type_schema(self, cur) -> str:
        cur.execute(
            """
            SELECT n.nspname
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typname = 'vector'
            ORDER BY CASE WHEN n.nspname = 'public' THEN 0 ELSE 1 END
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(
                "pgvector type 'vector' not found. "
                "Run: CREATE EXTENSION vector WITH SCHEMA public;"
            )
        return str(row[0])

    def _prepare_connection(self, cur) -> str:
        """
        Ensure the vector type is visible for ::vector casts.

        Some installs place the extension in a non-public schema (e.g. content).
        """
        vector_schema = self._resolve_vector_type_schema(cur)
        # Keep public available for other objects; put vector schema first.
        cur.execute(
            sql.SQL("SET search_path TO {}, public").format(sql.Identifier(vector_schema))
        )
        return vector_schema

    def _declared_embedding_dimensions(self, conn) -> int | None:
        """
        Read vector(N) from pg_catalog for the configured embedding column.
        Returns None if dimension is not declared (plain `vector`) or column is missing.
        """
        schema = self.schema_name or "public"
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod) AS col_type,
                       a.atttypmod,
                       t.typname
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_type t ON t.oid = a.atttypid
                WHERE n.nspname = %s
                  AND c.relname = %s
                  AND a.attname = %s
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                """,
                (schema, self.relation_name, self.embedding_column),
            )
            row = cur.fetchone()
        if not row:
            return None
        col_type, atttypmod, typname = row[0], row[1], row[2]
        if col_type:
            m = _VECTOR_DIM_RE.search(str(col_type))
            if m:
                return int(m.group(1))
        # pgvector stores N in typmod as (dimensions + 4) for typed vector columns.
        if str(typname).lower() == "vector" and atttypmod is not None and int(atttypmod) >= 4:
            dim = int(atttypmod) - 4
            if dim > 0:
                return dim
        return None

    def _rows_to_matches(self, rows: list[Any]) -> list[NormalizedMatch]:
        results: list[NormalizedMatch] = []
        for row in rows:
            idx = 0
            content = row[idx] if row[idx] is not None else ""
            idx += 1

            row_id = None
            if self.id_column:
                row_id = row[idx]
                idx += 1

            metadata_raw = None
            if self.metadata_column:
                metadata_raw = row[idx]
                idx += 1

            score = row[idx] if idx < len(row) else 0.0

            metadata: dict[str, Any]
            if isinstance(metadata_raw, dict):
                metadata = metadata_raw
            elif isinstance(metadata_raw, str):
                try:
                    parsed = json.loads(metadata_raw)
                    metadata = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    metadata = {}
            else:
                metadata = {}

            preview = (
                metadata.get("preview")
                or metadata.get("text")
                or metadata.get("chunk")
                or metadata.get("content")
                or str(content)
            )[:600]

            normalized_id = str(row_id) if row_id is not None else self._fallback_id(str(content))
            results.append(
                NormalizedMatch(
                    id=normalized_id,
                    score=float(score or 0.0),
                    text_preview=preview,
                    metadata=metadata,
                )
            )
        return results

    def search(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[NormalizedMatch]:
        query_vec = embed_query(query_text, self.config)
        actual_dim = len(query_vec)
        vec_text = self._vector_literal(query_vec)

        select_columns = [sql.Identifier(self.content_column)]
        if self.id_column:
            select_columns.append(sql.Identifier(self.id_column))
        if self.metadata_column:
            select_columns.append(sql.Identifier(self.metadata_column))

        select_list = sql.SQL(", ").join(
            select_columns + [sql.SQL("1 - ({} <=> %s::vector) AS score").format(sql.Identifier(self.embedding_column))]
        )

        where_sql = ""
        filter_params: list[Any] = []
        if filters:
            if not self.metadata_column:
                raise ValueError(
                    "pgvector filtered search requires config.metadata_column "
                    "(JSONB column holding chunk metadata)."
                )
            predicate = to_pgvector_predicate(filters, metadata_column=self.metadata_column)
            if predicate:
                where_sql, filter_params = predicate
                where_sql = f"WHERE {where_sql} "

        query = sql.SQL(
            "SELECT {select_list} "
            "FROM {table} "
            "{where_clause}"
            "ORDER BY {embedding_col} <=> %s::vector "
            "LIMIT %s"
        ).format(
            select_list=select_list,
            table=self._qualified_table(),
            where_clause=sql.SQL(where_sql) if where_sql else sql.SQL(""),
            embedding_col=sql.Identifier(self.embedding_column),
        )

        rows: list[Any]
        with psycopg2.connect(self.connection_uri) as conn:
            with conn.cursor() as cur:
                self._prepare_connection(cur)
            declared = self._declared_embedding_dimensions(conn)
            if declared is not None and actual_dim != declared:
                raise ValueError(
                    "pgvector embedding dimension mismatch. "
                    f"Column '{self.embedding_column}' is declared as vector({declared}), "
                    f"but embedding_model '{self.embedding_model}' produced a query vector of length {actual_dim}. "
                    "Use the same embedding model (or matching output size) as when rows were inserted."
                )

            try:
                with conn.cursor() as cur:
                    self._prepare_connection(cur)
                    # Params: score vector, filter values..., order vector, limit
                    params: list[Any] = [vec_text, *filter_params, vec_text, top_k]
                    cur.execute(query, params)
                    rows = cur.fetchall()
            except Exception as exc:
                raw = str(exc)
                low = raw.lower()
                if (
                    "dimension" in low
                    or "different vector dimensions" in low
                    or ("expected" in low and "element" in low)
                ):
                    raise ValueError(
                        "pgvector query failed due to vector dimension mismatch. "
                        f"embedding_model '{self.embedding_model}' produced length {actual_dim}; "
                        f"the table column '{self.embedding_column}' expects a different vector size. "
                        "Declare the column as vector(N) where N matches the model output, or fix embedding_model. "
                        f"Raw error: {raw}"
                    ) from exc
                raise

        return self._rows_to_matches(rows)

    def search_by_metadata_filter(
        self,
        filters: dict[str, Any],
        top_k: int = 50,
    ) -> list[NormalizedMatch]:
        """Fetch chunks by metadata filter only (no semantic ranking)."""
        if not self.metadata_column:
            raise ValueError(
                "pgvector metadata filter search requires config.metadata_column."
            )
        predicate = to_pgvector_predicate(filters, metadata_column=self.metadata_column)
        if not predicate:
            return []
        where_sql, filter_params = predicate

        select_columns = [sql.Identifier(self.content_column)]
        if self.id_column:
            select_columns.append(sql.Identifier(self.id_column))
        select_columns.append(sql.Identifier(self.metadata_column))
        select_list = sql.SQL(", ").join(
            select_columns + [sql.SQL("1.0::float8 AS score")]
        )

        query = sql.SQL(
            "SELECT {select_list} FROM {table} WHERE {where_clause} LIMIT %s"
        ).format(
            select_list=select_list,
            table=self._qualified_table(),
            where_clause=sql.SQL(where_sql),
        )

        with psycopg2.connect(self.connection_uri) as conn:
            with conn.cursor() as cur:
                self._prepare_connection(cur)
                cur.execute(query, [*filter_params, top_k])
                rows = cur.fetchall()
        return self._rows_to_matches(rows)
    def test_connection(self) -> tuple[bool, str]:
        try:
            with psycopg2.connect(self.connection_uri) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM pg_extension WHERE extname = 'vector' LIMIT 1"
                    )
                    if cur.fetchone() is None:
                        return False, "pgvector extension is not installed in the target database."

                    relation_lookup = (
                        f"{self.schema_name}.{self.relation_name}"
                        if self.schema_name
                        else self.relation_name
                    )
                    cur.execute("SELECT to_regclass(%s)", (relation_lookup,))
                    if cur.fetchone()[0] is None:
                        return False, f"Table '{relation_lookup}' does not exist."

                    where_schema = self.schema_name or "public"
                    cur.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        """,
                        (where_schema, self.relation_name),
                    )
                    cols = {r[0] for r in cur.fetchall()}

                    required = {self.embedding_column, self.content_column}
                    missing = [c for c in required if c not in cols]
                    if missing:
                        return (
                            False,
                            f"Missing required columns in '{relation_lookup}': {missing}. "
                            "Expected at least embedding_column and content_column.",
                        )

                    if self.id_column and self.id_column not in cols:
                        return (
                            False,
                            f"id_column '{self.id_column}' was provided but does not exist in '{relation_lookup}'.",
                        )
                    if self.metadata_column and self.metadata_column not in cols:
                        return (
                            False,
                            f"metadata_column '{self.metadata_column}' was provided but does not exist in '{relation_lookup}'.",
                        )

            _ = self.search("test connection", top_k=1)
            return True, "pgvector connection test successful."
        except Exception as exc:
            return False, f"pgvector connection failed: {exc}"

    def target_exists(self) -> bool:
        relation_lookup = (
            f"{self.schema_name}.{self.relation_name}"
            if self.schema_name
            else self.relation_name
        )
        try:
            with psycopg2.connect(self.connection_uri) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass(%s)", (relation_lookup,))
                    return cur.fetchone()[0] is not None
        except Exception:
            return False

    def ensure_target(self, vector_dim: int, **kwargs: Any) -> tuple[bool, str]:
        _ = kwargs
        if self.target_exists():
            return True, f"pgvector table '{self.table_name}' already exists."
        id_col = self.id_column or "id"
        meta_col = self.metadata_column or "metadata"
        dim = int(vector_dim)
        if dim <= 0:
            return False, f"Invalid vector_dim={vector_dim!r}."

        conn = psycopg2.connect(self.connection_uri)
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                if self.schema_name:
                    cur.execute(
                        sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                            sql.Identifier(self.schema_name)
                        )
                    )

                # Resolve schema that owns the vector type (may be non-public).
                vector_schema = self._resolve_vector_type_schema(cur)
                cur.execute(
                    sql.SQL("SET search_path TO {}, public").format(sql.Identifier(vector_schema))
                )

                table_ident = self._qualified_table()
                create_sql = sql.SQL(
                    """
                    CREATE TABLE {} (
                        {} TEXT PRIMARY KEY,
                        {} TEXT,
                        {} {}.vector({}),
                        {} JSONB
                    )
                    """
                ).format(
                    table_ident,
                    sql.Identifier(id_col),
                    sql.Identifier(self.content_column),
                    sql.Identifier(self.embedding_column),
                    sql.Identifier(vector_schema),
                    sql.SQL(str(dim)),
                    sql.Identifier(meta_col),
                )
                cur.execute(create_sql)
                conn.commit()
            return True, f"Created pgvector table '{self.table_name}' with {vector_schema}.vector({dim})."
        except Exception as exc:
            conn.rollback()
            return False, f"Failed to create pgvector table: {exc}"
        finally:
            conn.close()

    def upsert(self, records: list[dict[str, Any]], batch_size: int = 100) -> UpsertResult:
        ensure_record_ids(records)
        id_col = self.id_column or "id"
        meta_col = self.metadata_column
        upserted = 0
        conn = psycopg2.connect(self.connection_uri)
        try:
            with conn.cursor() as cur:
                self._prepare_connection(cur)
                table_ident = self._qualified_table()
                for i in range(0, len(records), batch_size):
                    for rec in records[i : i + batch_size]:
                        row_id = str(rec["id"])
                        text = (rec.get("metadata") or {}).get("text") or (rec.get("metadata") or {}).get(
                            "preview"
                        ) or ""
                        vec_str = self._vector_literal(rec["values"])
                        if meta_col:
                            insert_sql = sql.SQL(
                                """
                                INSERT INTO {} ({}, {}, {}, {})
                                VALUES (%s, %s, %s::vector, %s)
                                ON CONFLICT ({}) DO UPDATE SET
                                    {} = EXCLUDED.{},
                                    {} = EXCLUDED.{},
                                    {} = EXCLUDED.{}
                                """
                            ).format(
                                table_ident,
                                sql.Identifier(id_col),
                                sql.Identifier(self.content_column),
                                sql.Identifier(self.embedding_column),
                                sql.Identifier(meta_col),
                                sql.Identifier(id_col),
                                sql.Identifier(self.content_column),
                                sql.Identifier(self.content_column),
                                sql.Identifier(self.embedding_column),
                                sql.Identifier(self.embedding_column),
                                sql.Identifier(meta_col),
                                sql.Identifier(meta_col),
                            )
                            cur.execute(
                                insert_sql,
                                (row_id, text, vec_str, json.dumps(rec.get("metadata") or {})),
                            )
                        else:
                            insert_sql = sql.SQL(
                                """
                                INSERT INTO {} ({}, {}, {})
                                VALUES (%s, %s, %s::vector)
                                ON CONFLICT ({}) DO UPDATE SET
                                    {} = EXCLUDED.{},
                                    {} = EXCLUDED.{}
                                """
                            ).format(
                                table_ident,
                                sql.Identifier(id_col),
                                sql.Identifier(self.content_column),
                                sql.Identifier(self.embedding_column),
                                sql.Identifier(id_col),
                                sql.Identifier(self.content_column),
                                sql.Identifier(self.content_column),
                                sql.Identifier(self.embedding_column),
                                sql.Identifier(self.embedding_column),
                            )
                            cur.execute(insert_sql, (row_id, text, vec_str))
                        upserted += 1
                conn.commit()
            return UpsertResult(success=True, upserted_count=upserted)
        except Exception as exc:
            conn.rollback()
            return UpsertResult(
                success=False,
                upserted_count=upserted,
                failed_count=len(records) - upserted,
                error=f"pgvector upsert failed: {exc}",
            )
        finally:
            conn.close()

