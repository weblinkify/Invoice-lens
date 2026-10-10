"""Seed a running InvoiceLens API with the sample invoices (and a mock-erp webhook).

Usage: ``python -m scripts.seed_demo --api http://localhost:8000``
"""

import argparse
import os
import sys
import time

import httpx


def seed(api: str, webhook_url: str | None, webhook_secret: str | None, wait: bool) -> int:
    base = api.rstrip("/") + "/api/v1"
    headers = {"X-API-Key": os.environ["API_KEY"]} if os.environ.get("API_KEY") else {}
    with httpx.Client(base_url=base, headers=headers, timeout=30) as client:
        samples = client.get("/samples").raise_for_status().json()
        ids = [
            client.post(f"/samples/{s['name']}").raise_for_status().json()["id"] for s in samples
        ]
        print(f"Queued {len(ids)} sample invoices")

        if webhook_url and webhook_secret:
            existing = client.get("/webhook-endpoints").raise_for_status().json()
            if not any(ep["url"] == webhook_url for ep in existing):
                client.post(
                    "/webhook-endpoints",
                    json={"url": webhook_url, "secret": webhook_secret, "description": "Mock ERP"},
                ).raise_for_status()
                print(f"Registered webhook {webhook_url}")

        if wait:
            deadline = time.monotonic() + 120
            pending = set(ids)
            while pending and time.monotonic() < deadline:
                for doc_id in list(pending):
                    status = client.get(f"/documents/{doc_id}").json()["status"]
                    if status not in ("queued", "processing"):
                        pending.discard(doc_id)
                time.sleep(0.5)
            print("All samples processed" if not pending else f"{len(pending)} still processing")
            return 1 if pending else 0
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--webhook-url", default=os.environ.get("MOCK_ERP_URL"))
    parser.add_argument("--webhook-secret", default=os.environ.get("MOCK_ERP_SECRET"))
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()
    sys.exit(seed(args.api, args.webhook_url, args.webhook_secret, not args.no_wait))


if __name__ == "__main__":
    main()
