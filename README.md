# MetaETL

MetaETL extracts Meta Marketing API dimensions and daily facts into staging tables. Production transfer is outside this project.

## Daily Run

The Windows scheduled entry point is `run_metaetl.cmd`. It changes to the project directory, runs `uv run main.py`, writes scheduler output to `logs/scheduler.log`, and returns the ETL exit code.

The default fact window is yesterday through today. For a run on 2026-09-09:

```text
since=2026-09-08
until=2026-09-09
```

Meta treats `until` as an exclusive boundary. Page Insights uses daily periods. Post Insights is stored as a lifetime snapshot under the run snapshot date because Meta does not guarantee daily values for the selected post metrics.

## Configuration

Copy `.env.example` to `.env` and configure the values. Environment names use the `METAETL_` prefix.

```text
METAETL_DATABASE_BACKEND=sqlite
METAETL_SQLITE_PATH=metaetl.sqlite3
METAETL_USER_TOKEN=...
METAETL_POST_INSIGHTS_MODE=recent
METAETL_POST_INSIGHTS_LIMIT=1000
```

`METAETL_POST_INSIGHTS_MODE=recent` limits Post Insights to the newest staged posts by `CreatedTime`. Set it to `all` for every staged post. The default limit is 1,000. Older posts are intentionally not refreshed in `recent` mode; increase the limit or use `all` for full post coverage.

For SQL Server with Windows authentication:

```text
METAETL_DATABASE_BACKEND=sqlserver
METAETL_SQL_SERVER=server-name
METAETL_SQL_DATABASE=DataWarehouse
METAETL_SQL_USE_WINDOWS_AUTH=true
```

For SQL authentication set `METAETL_SQL_USE_WINDOWS_AUTH=false`, `METAETL_SQL_USERNAME`, and `METAETL_SQL_PASSWORD`.

## Data Flow

Dimensions run before facts on every scheduled run:

```text
Business -> AdAccount -> Campaign -> AdSet -> Ad/Creative -> Page -> Post
```

Facts run afterward and are isolated from one another:

```text
AdInsightsDaily
PageInsightsDaily
PostInsightsDaily
```

Fact keys:

- AdInsightsDaily: `AdID`, `Date`
- PageInsightsDaily: `PageID`, `Date`, `MetricName`
- PostInsightsDaily: `PostID`, `Date` where `Date` is the lifetime snapshot date

Repeated daily runs are therefore idempotent for the same date window.

## Historical Backfill

Do not run a month backfill from the scheduled daily task. Run it manually from the project directory:

```cmd
uv run python -c "from main import run_month_backfill; run_month_backfill('2026-08-01', '2026-09-01')"
```

The `run_month_backfill` function is defined in `main.py` and loads all three facts for the requested window.

## Windows Task Scheduler

1. Ensure `uv` is installed and available to the task account.
2. Copy `.env.example` to `.env` and configure the token and database.
3. Run `register_metaetl_task.cmd` from the project directory. It registers `MetaETL Daily` at 02:00 every day.
4. In Task Scheduler, configure the task account, password, working directory, and whether it may run while logged off.
5. Review `logs/scheduler.log` and the monthly files under `logs/` after each run.

To use another time, edit `/ST 02:00` in `register_metaetl_task.cmd`.

To remove the task:

```cmd
schtasks /Delete /TN "MetaETL Daily" /F
```

## Validation

```cmd
uv run python -c "import main; print('ok')"
```

A real API run requires a valid token, required Meta permissions, and access to the selected database.
