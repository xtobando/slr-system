"""Real embedding acceptance check; no review decisions or PDF operations."""
import argparse
import json
from pathlib import Path

from test_engine import module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("fastembed", "ollama"), default="fastembed")
    parser.add_argument("--model")
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[1]
    from dotenv import load_dotenv
    load_dotenv(workspace.parent / '.env', override=False)
    encoder = module.SemanticEncoder(workspace, backend=args.backend, model=args.model)
    try:
        query = encoder.encode(["Myoelectric prosthetic hand control using muscle electrical signals"], mode="query")[0]
        vectors = encoder.encode([
            "Electromyography (EMG) decodes muscle activity — señales musculares — to control a prosthetic hand grasp.",
            "Ocean currents and sediment distribution in the Pacific marine ecosystem."])
        scores = [sum(a * b for a, b in zip(query, module.unit_vector(v, len(query)))) for v in vectors]
        if not scores[0] > scores[1]:
            raise module.EngineError("Embedding relevance ordering failed the acceptance example.")
        print(json.dumps({"backend": encoder.identity, "dimensions": len(query),
                          "related_cosine": scores[0], "unrelated_cosine": scores[1],
                          "unicode_roundtrip": "passed", "note": "Examples verify operation, not review recall or a calibrated threshold."}, indent=2))
    finally:
        encoder.close()


if __name__ == "__main__":
    main()
