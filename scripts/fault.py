"""fault.py - set, show or clear the fixed delay on one replica (Part D). Takes effect at once, no restart.

  python scripts/fault.py set B 0.4      # every GET /products/<id> and gRPC GetProduct on replica B takes +0.4 s
  python scripts/fault.py show
  python scripts/fault.py clear          # back to normal
"""
import json
import os
import sys

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "faults", "delay.json")


def read():
    try:
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write(data):
    with open(FILE, "w", encoding="utf-8", newline="\n") as f:     # written in place: the containers see the change
        json.dump(data, f)
        f.write("\n")


def main(argv):
    if argv[:1] == ["set"] and len(argv) == 3 and argv[1] in ("A", "B", "C"):
        d = read()
        d[argv[1]] = float(argv[2])
        write(d)
    elif argv[:1] == ["clear"]:
        write({})
    elif argv[:1] != ["show"]:
        sys.exit(__doc__)
    print("delays now:", read() or "none")


if __name__ == "__main__":
    main(sys.argv[1:])
