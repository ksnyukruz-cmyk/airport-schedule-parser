import argparse
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Табло аэропортов")
    public = bool(os.environ.get("PORT"))
    parser.add_argument("--host", default="0.0.0.0" if public else "127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    uvicorn.run("app.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
