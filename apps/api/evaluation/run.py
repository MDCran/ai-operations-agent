"""Routing evaluation; provider must be explicitly selected through AI_PROVIDER.

Running with OpenAI incurs provider usage. This is an evaluation harness, not a production quality score.
"""

import json
from pathlib import Path

from app.agents.providers import provider
from app.tools.registry import REGISTRY


def evaluate():
    cases = json.loads(Path(__file__).with_name("cases.json").read_text())
    tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema.model_json_schema(),
        }
        for tool in REGISTRY.values()
    ]
    passed = 0
    for case in cases:
        plan, usage = provider().plan(case["message"], [], tools)
        valid = plan.agent == case["agent"] and case["tool"] in {call.name for call in plan.calls}
        passed += valid
        print(
            json.dumps(
                {
                    "case": case["id"],
                    "passed": valid,
                    "agent": plan.agent,
                    "tools": [c.name for c in plan.calls],
                    "usage": usage,
                }
            )
        )
    print(json.dumps({"passed": passed, "total": len(cases)}))
    return passed == len(cases)


if __name__ == "__main__":
    raise SystemExit(0 if evaluate() else 1)
