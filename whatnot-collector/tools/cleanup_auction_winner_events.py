import sys


MESSAGE = (
    "legacy_sqlite_cleanup_retired: cleanup_auction_winner_events directly mutated "
    "SQLite events and deleted derived fact tables. Run a Postgres-native cleanup "
    "workflow instead; this tool intentionally fails closed during the cutover."
)


def main(_db_path=None):
    raise SystemExit(MESSAGE)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
