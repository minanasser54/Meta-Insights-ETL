-- One-time SQL Server migration for this change. Run BEFORE the next ETL run.
-- (create_all() creates missing tables/schemas but never alters existing ones.)

-- 1) AdAccount.AccountID changed NVARCHAR('act_123') -> BIGINT (123).
--    AdAccount is fully reloaded from Meta on every run, so dropping it loses nothing;
--    the next run recreates it with the new type.
DROP TABLE IF EXISTS [STG.Marketing].[AdAccount];

-- 2) The Creative table is no longer created, fetched or loaded. Drop the old one.
--    (Ad.CreativeID is still populated.)
DROP TABLE IF EXISTS [STG.Marketing].[Creative];

-- 3) Watermark.metaadsetl and its schema are created automatically by create_schema()
--    (needs CREATE SCHEMA permission the first time). To create them by hand instead:
-- IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'Watermark') EXEC('CREATE SCHEMA [Watermark]');
-- CREATE TABLE [Watermark].[metaadsetl] (
--     RunID     BIGINT IDENTITY PRIMARY KEY,
--     TableName NVARCHAR(200) NOT NULL,
--     StartTime DATETIME      NOT NULL,
--     EndTime   DATETIME      NULL,
--     Status    NVARCHAR(50)  NOT NULL
-- );
-- CREATE INDEX IX_metaadsetl_TableName_Status_StartTime ON [Watermark].[metaadsetl] (TableName, Status, StartTime);
