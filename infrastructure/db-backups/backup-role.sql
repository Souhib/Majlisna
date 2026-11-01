-- Read-only login for the Majlisna backup (pg_dump) and the restore drill's live counts.
--
-- Applied by install.sh, through the DB container's local socket, as its POSTGRES_USER:
--   docker exec -i majlisna-db sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup-role.sql
-- The password is set separately (set-role-password.py) as a SCRAM verifier computed on the
-- host, so the clear password never appears in SQL, on a command line or in a server log.
-- Idempotent: re-running only re-asserts the attributes and the membership.
--
-- pg_read_all_data (PostgreSQL 14+) grants SELECT on every table and sequence and USAGE on
-- every schema, current and future, and nothing that writes. It does not bypass row-level
-- security; no Majlisna table uses RLS, and if one ever does pg_dump fails loudly rather
-- than produce a partial dump. default_transaction_read_only is a second guard on top.
\set ON_ERROR_STOP on

SELECT 'CREATE ROLE majlisna_backup'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'majlisna_backup')
\gexec

ALTER ROLE majlisna_backup
  LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 2;
GRANT pg_read_all_data TO majlisna_backup;
SELECT format('GRANT CONNECT ON DATABASE %I TO majlisna_backup', current_database())
\gexec
ALTER ROLE majlisna_backup SET default_transaction_read_only = on;

-- Fail the install if the role could ever write or escalate.
DO $$
DECLARE
  r pg_roles%ROWTYPE;
  memberships text;
BEGIN
  SELECT * INTO r FROM pg_roles WHERE rolname = 'majlisna_backup';
  IF r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls OR NOT r.rolcanlogin THEN
    RAISE EXCEPTION 'majlisna_backup has unexpected attributes';
  END IF;
  SELECT string_agg(b.rolname, ',' ORDER BY b.rolname) INTO memberships
  FROM pg_auth_members m JOIN pg_roles b ON b.oid = m.roleid
  WHERE m.member = r.oid;
  IF memberships IS DISTINCT FROM 'pg_read_all_data' THEN
    RAISE EXCEPTION 'majlisna_backup must be a member of pg_read_all_data only, found %', memberships;
  END IF;
  IF EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relowner = r.oid) THEN
    RAISE EXCEPTION 'majlisna_backup must own nothing';
  END IF;
END
$$;
