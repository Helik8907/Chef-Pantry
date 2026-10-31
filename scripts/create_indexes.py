"""Script to provision and poll MongoDB Atlas vector and operational indexes."""

import sys
import time
import pymongo

from app.infra.config import get_database
from app.infra.embedding_provider import get_vector_strategy
from app.infra.memory_repository import MemoryRepository


def main(max_wait_seconds: int = 60, poll_interval: int = 3) -> None:
    """Ensure database indexes exist and poll vector index readiness."""
    version_parts = []
    for p in pymongo.__version__.split(".")[:2]:
        try:
            version_parts.append(int(p))
        except ValueError:
            break
    if len(version_parts) >= 2 and tuple(version_parts[:2]) < (4, 7):
        print(
            f"[ERROR] PyMongo 4.7 or newer is required for Automated Embedding index creation. "
            f"Installed version: {pymongo.__version__}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("[INFO] Initializing MongoDB database and vector strategy...")
    db = get_database()
    strategy = get_vector_strategy()
    repo = MemoryRepository(db=db, strategy=strategy)

    print(
        "\n[NOTE] MongoDB Atlas builds Vector Search indexes asynchronously in the background.\n"
        "       Atlas Automated Embedding requires an Atlas M10+ dedicated cluster with Voyage AI enabled.\n"
    )

    print(f"[INFO] Ensuring operational and vector indexes for '{strategy.index_name}'...")
    repo.ensure_indexes()
    print("[INFO] Index provisioning requests completed.")

    print(f"[INFO] Polling vector index readiness (timeout: {max_wait_seconds}s)...")
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        status = repo.vector_index_status()
        elapsed = int(time.time() - start_time)
        print(f"[{elapsed}s] Vector index '{strategy.index_name}' status: {status}")

        if status == "ready":
            print(f"[SUCCESS] Vector search index '{strategy.index_name}' is ready for queries!")
            sys.exit(0)

        time.sleep(poll_interval)

    print(
        f"[ERROR] Vector index '{strategy.index_name}' was not ready after {max_wait_seconds} seconds.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
