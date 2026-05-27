"""Reset the SmartHome SQLite database.

Deletes `server/smarthome.db` (and its WAL/SHM siblings). On the next
server start, each automation's `init_schema()` will recreate its tables
empty.

Pass `--seed` to also re-init the schemas immediately and run each
automation's `seed_demo` module if one exists.

Usage (stop the server first — Windows holds a file lock while uvicorn
is running):

    cd C:\\Projects\\SmartHome\\server
    .\\.venv\\Scripts\\python.exe reset_db.py            # empty DB
    .\\.venv\\Scripts\\python.exe reset_db.py --seed     # + demo data
"""
import argparse
import importlib
import socket
import sys

from db import DB_PATH

DB_FILES = [
    DB_PATH,
    DB_PATH.parent / (DB_PATH.name + "-wal"),
    DB_PATH.parent / (DB_PATH.name + "-shm"),
]


def server_listening(port: int = 8000) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def wipe() -> None:
    removed: list[str] = []
    for f in DB_FILES:
        if f.exists():
            try:
                f.unlink()
                removed.append(f.name)
            except PermissionError as exc:
                print(f"ERROR: cannot delete {f.name}: {exc}")
                print("  Is the server still running? Stop it and retry.")
                sys.exit(1)
    if removed:
        print(f"Removed: {', '.join(removed)}")
    else:
        print("Nothing to remove (DB files not present).")


def reseed() -> None:
    # Import lazily so a plain reset doesn't pay the FastAPI import cost.
    from main import AUTOMATIONS

    for auto in AUTOMATIONS:
        name = auto.__name__.rsplit(".", 1)[-1]
        auto.init_schema()
        try:
            seed_mod = importlib.import_module(f"automations.{name}.seed_demo")
        except ModuleNotFoundError:
            print(f"  {name}: no seed_demo module - skipping")
            continue
        seed_fn = getattr(seed_mod, "seed", None)
        if seed_fn is None:
            print(f"  {name}: seed_demo has no seed() function - skipping")
            continue
        print(f"  {name}: seeding...")
        seed_fn()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--seed",
        action="store_true",
        help="After wiping, re-init schemas and run each automation's seed_demo.",
    )
    args = parser.parse_args()

    if server_listening():
        print("ERROR: something is listening on port 8000 - stop the server first.")
        sys.exit(1)

    wipe()
    if args.seed:
        print("\nRe-seeding automations:")
        reseed()
    print("\nDone.")


if __name__ == "__main__":
    main()
