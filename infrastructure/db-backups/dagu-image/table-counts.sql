-- Exact row count of every table in the public schema, one "table|count" line each,
-- sorted by name. Used by the restore drill on both sides: the live database (through
-- live-table-counts.sh, read-only role, read-only transaction) and the restored copy.
-- Exact counts, not pg_class.reltuples estimates: the drill must compare real rows.
SELECT c.relname AS table_name,
       (xpath('/row/n/text()',
              query_to_xml(format('SELECT count(*) AS n FROM %I.%I', n.nspname, c.relname),
                           false, true, '')))[1]::text::bigint AS row_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relname;
