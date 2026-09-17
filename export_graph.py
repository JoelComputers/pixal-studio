"""Write an API-format graph without contacting a GPU server."""
import argparse
import json
from pathlib import Path
from pixal_pipeline import build_graph
from settings import load_settings


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", required=True, help="Image filename already uploaded to ComfyUI")
    p.add_argument("--preset", choices=("preview", "detail"), default="detail")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--job-id", default="export")
    p.add_argument("--config")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    settings = load_settings(args.config)
    graph = build_graph(args.image, args.preset, args.seed, args.job_id, settings["models"])
    args.output.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
