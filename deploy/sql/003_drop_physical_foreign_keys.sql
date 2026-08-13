-- 删除旧数据库的物理外键
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN
        SELECT namespace.nspname AS schema_name,
               relation.relname AS table_name,
               constraint_row.conname AS constraint_name
        FROM pg_constraint constraint_row
        JOIN pg_class relation ON relation.oid = constraint_row.conrelid
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        WHERE constraint_row.contype = 'f'
          AND namespace.nspname = 'public'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I DROP CONSTRAINT %I',
            item.schema_name,
            item.table_name,
            item.constraint_name
        );
    END LOOP;
END $$;
