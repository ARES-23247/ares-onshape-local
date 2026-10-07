"""Same local bridge operations as MCP, for hosts whose tool catalog has not reloaded."""
import argparse
import json
import sys
import native_recipe_bridge as bridge


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["prepare_native_recipe", "prepare_recipe_step", "bind_recipe_step",
                                               "prepare_recipe_update", "native_recipe_status", "verify_native_recipe"])
    parser.add_argument("--input", required=True, help="Credential-free workspace JSON containing keyword arguments")
    args = parser.parse_args()
    _, _, parameters = bridge.workflow.local_json(args.input)
    try:
        result = getattr(bridge, args.operation)(**parameters)
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}))
        sys.exit(1)
