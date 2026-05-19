#!/usr/bin/env python3
import getpass
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from server.auth import hash_password


def main():
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    print(hash_password(password))


if __name__ == "__main__":
    main()
