"""
Replay CLI — re-run the pipeline from any node forward using a saved trace.

Usage:
    python -m orchestration.tools.replay \\
        --claim-id <id> \\
        --from-node adjudicator \\
        --override-prompt prompts/adjudicator_v2.txt

This is the most-used debugging tool in the system. It lets you A/B test prompt
changes on real failed cases without re-running expensive upstream specialists.
The orchestrator re-uses the EvidenceStore snapshot from the original trace.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def replay(
    claim_id: str,
    from_node: str,
    override_prompt: Path | None = None,
    trace_dir: Path = Path("traces"),
) -> dict:
    """
    Replay a claim starting from from_node, using the EvidenceStore
    as it existed at the start of that node's execution in the original trace.

    Args:
        claim_id: the claim to replay
        from_node: node name to start from (all prior nodes reuse original outputs)
        override_prompt: optional path to a replacement prompt template for from_node
        trace_dir: directory containing JSONL trace files

    Returns:
        the final EvidenceStore as a dict
    """
    raise NotImplementedError(
        "Replay implementation pending — requires EvidenceStore snapshot "
        "serialization in trace_store.py (Phase 2)."
    )


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Replay a claim from a specific node.")
    parser.add_argument("--claim-id", required=True)
    parser.add_argument("--from-node", required=True)
    parser.add_argument("--override-prompt", type=Path)
    parser.add_argument("--trace-dir", type=Path, default=Path("traces"))
    args = parser.parse_args()

    result = asyncio.run(
        replay(
            claim_id=args.claim_id,
            from_node=args.from_node,
            override_prompt=args.override_prompt,
            trace_dir=args.trace_dir,
        )
    )
    print(json.dumps(result, indent=2))
