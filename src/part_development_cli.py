"""Offline part-definition tools for clients whose MCP catalog has not reloaded."""
import argparse
import asyncio
import inspect
import json
import sys

import part_development as parts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["save_part_definition", "preview_part_definition", "prepare_part_definition",
                                              "part_development_status", "verify_part_parameter_change"])
    parser.add_argument("--input", required=True, help="Workspace JSON containing tool keyword arguments")
    args = parser.parse_args()
    try:
        _, _, parameters = parts.w.local_json(args.input)
        result = getattr(parts, args.operation)(**parameters)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}))
        sys.exit(1)
