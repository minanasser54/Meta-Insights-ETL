from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="METAETL_",
        extra="ignore",
    )

    api_version: str = "v25.0"
    user_token: str | None = None
    page_access_token: str | None = None
    account_id: str | None = None
    page_id: str | None = None

    database_backend: str = "sqlite"
    sqlite_path: str = "metaetl.sqlite3"
    sql_server: str | None = None
    sql_database: str = "DataWarehouse"
    sql_driver: str = "ODBC Driver 18 for SQL Server"
    sql_schema: str = "STG.Marketing"
    sql_use_windows_auth: bool = True
    sql_username: str | None = None
    sql_password: str | None = None
    sql_encrypt: str = "no"

    token_source: str = "env"
    token_query: str | None = None
    dry_run: bool = False
    log_directory: str = "logs"
    log_level: str = "INFO"
    post_insights_mode: str = "recent"
    post_insights_limit: int = 1000

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}"

    def sql_connection_string(self) -> str:
        if not self.sql_server:
            raise ValueError("METAETL_SQL_SERVER is required for SQL Server")
        base = (
            f"DRIVER={{{self.sql_driver}}};SERVER={self.sql_server};"
            f"DATABASE={self.sql_database};Encrypt={self.sql_encrypt};"
        )
        if self.sql_use_windows_auth:
            return base + "Trusted_Connection=yes;"
        if not self.sql_username or self.sql_password is None:
            raise ValueError("SQL username and password are required for SQL authentication")
        return base + f"UID={self.sql_username};PWD={self.sql_password};"

    def sqlalchemy_url(self) -> str:
        if self.database_backend.lower() == "sqlite":
            return f"sqlite:///{self.sqlite_path}"
        if self.database_backend.lower() != "sqlserver":
            raise ValueError("METAETL_DATABASE_BACKEND must be sqlite or sqlserver")
        return f"mssql+pyodbc:///?odbc_connect={quote_plus(self.sql_connection_string())}"


Config = Settings


@lru_cache(maxsize=1)
def get_conf() -> Settings:
    return Settings()
