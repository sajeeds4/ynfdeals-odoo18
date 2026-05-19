from __future__ import annotations

import json

from .ingest_cutover import lots_validation_report


def main():
    print(json.dumps(lots_validation_report(), indent=2))


if __name__ == "__main__":
    main()
