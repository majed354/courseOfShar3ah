import argparse
from .extract import ROOT, build_catalog

parser = argparse.ArgumentParser(description="Local Quran-program equivalency pilot")
parser.add_argument("action", choices=["build", "serve"])
parser.add_argument("--port", type=int, default=8798)
parser.add_argument("--model", default="qwen3.8:27b-q8_0")
args = parser.parse_args()
if args.action == "build":
    build_catalog(ROOT / "equivalency-pilot/catalog.json")
else:
    from .server import serve
    serve(port=args.port, model=args.model)
