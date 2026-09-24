import argparse
import json
import os

import uvicorn

from chore_stars.app import create_app, run_job
from chore_stars.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="chore-stars")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    job = sub.add_parser("job")
    job.add_argument("name", nargs="?", default="daily")
    args = parser.parse_args()
    settings = load_settings()
    if args.cmd == "serve":
        os.makedirs(settings.photo_dir, exist_ok=True)
        app = create_app(settings)
        uvicorn.run(app, host=args.host or settings.host, port=args.port or settings.port)
    elif args.cmd == "job":
        print(json.dumps(run_job(args.name, settings), default=str))


if __name__ == "__main__":
    main()
