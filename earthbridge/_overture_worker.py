"""
Subprocess worker that reads Overture Parquet from S3 with DuckDB.

This runs out-of-process on purpose. DuckDB loads native extensions, and a
failure inside one is not always a Python exception: on some platforms
`INSTALL httpfs` terminates the interpreter outright, which no try/except in the
parent can catch. Isolating the query means the worst case is a dead subprocess
and a fallback, not a dead caller.

Invoked as:  python -m earthbridge._overture_worker <json-request>

The request is a JSON object with keys: glob, bbox, limit, output.
On success the worker writes a Parquet file to `output` and prints a JSON status
line to stdout. Any failure exits non-zero.
"""

import json
import sys


def main(argv) -> int:
    if len(argv) != 2:
        print(json.dumps({"status": "error", "message": "expected one JSON argument"}))
        return 2

    try:
        request = json.loads(argv[1])
        glob = request["glob"]
        min_x, min_y, max_x, max_y = [float(v) for v in request["bbox"]]
        limit = int(request["limit"])
        output = request["output"]
    except (ValueError, KeyError, TypeError) as e:
        print(json.dumps({"status": "error", "message": f"bad request: {e}"}))
        return 2

    try:
        import duckdb
    except ImportError:
        print(json.dumps({"status": "error", "message": "duckdb is not installed"}))
        return 3

    # DuckDB does not accept bound parameters for a read_parquet source or a
    # COPY ... TO destination, so those two are interpolated. Both are generated
    # by this library rather than supplied by a user, and quotes are escaped so a
    # path containing one cannot terminate the literal early.
    glob_literal = "'" + glob.replace("'", "''") + "'"
    output_literal = "'" + output.replace("'", "''") + "'"

    try:
        conn = duckdb.connect()
        conn.execute("INSTALL httpfs; LOAD httpfs;")
        conn.execute("SET s3_region='us-west-2';")

        # `geometry` is selected raw: it is already WKB in the Overture schema and
        # GeoPandas reads it directly. Routing it through ST_GeomFromWKB would
        # produce a DuckDB GEOMETRY that from_wkb cannot parse.
        conn.execute(
            f"""
            COPY (
                SELECT id, names.primary AS name, subtype, height, num_floors, geometry
                FROM read_parquet({glob_literal}, hive_partitioning=1)
                WHERE bbox.xmin <= ? AND bbox.xmax >= ?
                  AND bbox.ymin <= ? AND bbox.ymax >= ?
                ORDER BY id
                LIMIT ?
            ) TO {output_literal} (FORMAT PARQUET)
            """,
            [max_x, min_x, max_y, min_y, limit],
        )
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)[:500]}))
        return 1

    print(json.dumps({"status": "success", "output": output}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
