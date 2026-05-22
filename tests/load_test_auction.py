import asyncio
import json
import logging
import os
import sys
import uuid
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orchestrator"))

import nats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("load_test")


async def run_auction(nc, assignment_type: str) -> dict:
    auction_id = str(uuid.uuid4())
    bid_subject = f"tasks.auction.bid.{auction_id}"
    bids = []

    async def on_bid(msg):
        try:
            bid = json.loads(msg.data.decode())
            bids.append(bid)
        except json.JSONDecodeError:
            pass

    sub = await nc.subscribe(bid_subject, cb=on_bid)
    auction_payload = {
        "auction_id": auction_id,
        "assignment_type": assignment_type,
    }
    await nc.publish("tasks.auction.check", json.dumps(auction_payload).encode())
    await asyncio.sleep(0.5)

    try:
        await sub.unsubscribe()
    except Exception:
        pass

    return {
        "auction_id": auction_id,
        "assignment_type": assignment_type,
        "bid_count": len(bids),
        "bids": bids,
        "winner": min(bids, key=lambda b: b["score"]) if bids else None,
    }


async def main():
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    nc = await nats.connect(servers=[nats_url])
    logger.info(f"Connected to NATS at {nats_url}")

    assignment_types = ["test", "essay", "code"]
    total_auctions = 30
    results = []
    winner_counter = Counter()
    spec_counter = Counter()

    logger.info(f"Running {total_auctions} auctions ({total_auctions//len(assignment_types)} per type)...")

    for i in range(total_auctions):
        atype = assignment_types[i % len(assignment_types)]
        result = await run_auction(nc, atype)
        results.append(result)

        w = result["winner"]
        if w:
            winner_counter[w["agent_id"]] += 1
            spec_counter[w.get("specialization", "?")] += 1
            status = "MATCH" if w.get("specialization") == atype else "MISMATCH"
            logger.info(
                f"[{i+1:02d}/{total_auctions}] type={atype} "
                f"bids={result['bid_count']} "
                f"winner={w['agent_id'][-8:]} score={w['score']:.2f} "
                f"spec={w.get('specialization', '?')} {status}"
            )
        else:
            logger.warning(f"[{i+1:02d}/{total_auctions}] NO BIDS for {atype}")

    await nc.drain()

    logger.info("=" * 60)
    logger.info("LOAD TEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"Total auctions: {total_auctions}")
    logger.info(f"Avg bids per auction: {sum(r['bid_count'] for r in results) / len(results):.1f}")
    logger.info("")

    logger.info("Winner distribution by agent:")
    for agent, count in winner_counter.most_common():
        pct = count / total_auctions * 100
        logger.info(f"  {agent[-20:]:20s} {count:3d} ({pct:5.1f}%)")

    logger.info("")
    logger.info("Winner distribution by specialization:")
    for spec, count in spec_counter.most_common():
        logger.info(f"  {spec:10s} {count:3d}")

    logger.info("")

    match_count = sum(
        1 for r in results
        if r["winner"] and r["winner"].get("specialization") == r["assignment_type"]
    )
    mismatch_count = total_auctions - match_count
    logger.info(f"Specialization match: {match_count}/{total_auctions} ({match_count/total_auctions*100:.0f}%)")
    logger.info(f"Specialization mismatch: {mismatch_count}/{total_auctions} ({mismatch_count/total_auctions*100:.0f}%)")

    if match_count > mismatch_count:
        logger.info("RESULT: Specialization-based auction selects matching agents more often ✅")
    else:
        logger.info("RESULT: Specialization-based auction does NOT favor matching agents ⚠️")

    if len(winner_counter) >= 2:
        logger.info("RESULT: Tasks are distributed across multiple agents ✅")
    else:
        logger.info("RESULT: Tasks are NOT distributed across agents ⚠️")

    all_bid_counts = [r["bid_count"] for r in results]
    avg_bids = sum(all_bid_counts) / len(all_bid_counts)
    if avg_bids >= 2:
        logger.info(f"RESULT: Consistent competition (avg {avg_bids:.1f} bids/auction) ✅")
    else:
        logger.info(f"RESULT: Low competition (avg {avg_bids:.1f} bids/auction) ⚠️")


if __name__ == "__main__":
    asyncio.run(main())
