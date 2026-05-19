from __future__ import annotations

import json

from .ingest_cutover import failed_ingest_validation_report


def main():
    print(json.dumps(failed_ingest_validation_report(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
