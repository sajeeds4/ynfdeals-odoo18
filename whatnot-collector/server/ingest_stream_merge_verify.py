import json
import sys

from .ingest_cutover import stream_merge_validation_report


def main():
    source_id = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else None
    target_id = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
    print(json.dumps(stream_merge_validation_report(source_id=source_id, target_id=target_id), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
