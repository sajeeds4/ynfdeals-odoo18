import json

from .postgres_cutover import company_validation_report


def main():
    print(json.dumps(company_validation_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
