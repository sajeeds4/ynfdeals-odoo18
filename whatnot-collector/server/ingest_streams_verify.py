import json

from .ingest_cutover import streams_validation_report


def main():
    print(json.dumps(streams_validation_report(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
