import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.integration_contract import HrisEnvelope, HrisOutboundMetadataHeaders


def main() -> int:
    schema = {
        "headers": HrisOutboundMetadataHeaders.model_json_schema(),
        "envelope": HrisEnvelope.model_json_schema(),
    }
    print(json.dumps(schema, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
