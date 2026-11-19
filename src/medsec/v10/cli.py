"""Build, validate, and plan unreviewed attack candidate suites."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .synthesis import build, plan, validate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("build")
    make.add_argument("--out", type=Path, required=True)
    make.add_argument("--seed", type=int, default=0)
    check = sub.add_parser("validate")
    check.add_argument("--suite", type=Path, required=True)
    planned = sub.add_parser("plan")
    planned.add_argument("--suite", type=Path, required=True)
    planned.add_argument("--attack-id", required=True)
    planned.add_argument("--model", default="deepseek-flash")
    planned.add_argument("--condition", choices=["clean_none", "attack_none", "clean_scope", "attack_scope"],
                         default="attack_none")
    planned.add_argument("--memory-root", type=Path)
    planned.add_argument("--out", type=Path,
                         help="For Harbor plans, create an exclusive JSON job config at this path")
    args = parser.parse_args()
    if args.command == "build":
        result = build(args.out, args.seed)
        print(json.dumps({"format": result["format"], "seed": result["seed"],
                          "task_count": result["task_count"], "attack_count": result["attack_count"],
                          "suite": str(args.out.resolve())}, ensure_ascii=False, indent=2))
    elif args.command == "validate":
        print(json.dumps(validate(args.suite), ensure_ascii=False, indent=2))
    else:
        result = plan(args.suite, args.attack_id, args.model, args.condition, args.memory_root)
        if args.out:
            if result["kind"] != "harbor":
                parser.error("--out is only valid for Harbor job configs")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x") as handle:
                handle.write(json.dumps(result["job_config"], ensure_ascii=False, indent=2) + "\n")
            result["job_config_path"] = str(args.out.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
