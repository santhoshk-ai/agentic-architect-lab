"""Provision the baseline Knowledge Base (fixed-size chunking) on S3 Vectors.

Creates: S3 data bucket + corpus upload, S3 vector bucket, one index per strategy you run,
IAM service role, KB, data source, ingestion job. Safe to re-run (state.json tracks progress).

Usage: python setup_kb.py [--strategy fixed|semantic|hierarchical]
"""
import argparse

import config as C
import kb_lib as L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="fixed", choices=list(C.STRATEGIES))
    a = ap.parse_args()

    cl = L.clients()
    state = L.load_state()
    L.provision_base(state, cl)
    print(f"== knowledge base: {a.strategy}")
    rec = L.ensure_kb(state, cl, a.strategy)
    print(f"\nREADY  region={C.REGION}  kb_id={rec['kb_id']}  strategy={a.strategy}")
    print("Next:  python compare_kb.py")


if __name__ == "__main__":
    main()
