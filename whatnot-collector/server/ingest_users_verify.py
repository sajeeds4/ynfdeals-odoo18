from __future__ import annotations

import json

from .ingest_cutover import users_validation_report


def main():
    print(json.dumps(users_validation_report(), indent=2))


if __name__ == "__main__":
    main()
