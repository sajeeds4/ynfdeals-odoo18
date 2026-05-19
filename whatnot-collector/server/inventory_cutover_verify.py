import json

from .postgres_cutover import inventory_validation_report


def main():
    print(json.dumps(inventory_validation_report(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
