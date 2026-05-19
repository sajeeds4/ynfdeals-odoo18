from __future__ import annotations

import json

from .ingest_cutover import events_validation_report


def main():
    print(json.dumps(events_validation_report(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
