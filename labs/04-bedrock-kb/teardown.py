"""Delete everything this lab created: KBs + data sources, S3 Vectors indexes and bucket,
S3 data bucket, IAM role. Reads state.json.

Usage: python teardown.py [--dry-run]
"""
import argparse
import time

from botocore.exceptions import ClientError

import kb_lib as L


def gone(fn):
    try:
        fn()
        return False
    except ClientError as e:
        if e.response["Error"]["Code"] in ("ResourceNotFoundException", "NotFoundException",
                                           "NoSuchEntity", "404", "NoSuchBucket"):
            return True
        raise


def step(dry, msg, fn):
    print(("DRY  " if dry else "     ") + msg)
    if dry:
        return
    try:
        fn()
    except ClientError as e:
        c = e.response["Error"]["Code"]
        if c in ("ResourceNotFoundException", "NotFoundException", "NoSuchEntity", "NoSuchBucket"):
            print(f"     (already gone: {c})")
        else:
            raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    dry = a.dry_run

    state = L.load_state()
    if "data_bucket" not in state:
        raise SystemExit("state.json has nothing to delete.")
    cl = L.clients()
    agent, s3v, s3, iam = cl["agent"], cl["s3v"], cl["s3"], cl["iam"]

    for name, rec in state.get("kbs", {}).items():
        kb = rec.get("kb_id")
        if not kb:
            continue
        if rec.get("ds_id"):
            step(dry, f"delete data source {rec['ds_id']} ({name})",
                 lambda: agent.delete_data_source(knowledgeBaseId=kb, dataSourceId=rec["ds_id"]))
            while not dry and not gone(lambda: agent.get_data_source(
                    knowledgeBaseId=kb, dataSourceId=rec["ds_id"])):
                time.sleep(5)
        step(dry, f"delete knowledge base {kb} ({name})",
             lambda: agent.delete_knowledge_base(knowledgeBaseId=kb))
        while not dry and not gone(lambda: agent.get_knowledge_base(knowledgeBaseId=kb)):
            time.sleep(5)

    vb = state["vector_bucket"]
    for name, rec in state.get("kbs", {}).items():
        if rec.get("index_name"):
            step(dry, f"delete vector index {rec['index_name']}",
                 lambda: s3v.delete_index(vectorBucketName=vb, indexName=rec["index_name"]))
    step(dry, f"delete vector bucket {vb}", lambda: s3v.delete_vector_bucket(vectorBucketName=vb))

    b = state["data_bucket"]

    def empty_and_delete():
        objs = s3.list_objects_v2(Bucket=b).get("Contents", [])
        if objs:
            s3.delete_objects(Bucket=b, Delete={"Objects": [{"Key": o["Key"]} for o in objs]})
        s3.delete_bucket(Bucket=b)
    step(dry, f"empty + delete data bucket {b}", empty_and_delete)

    rn = state.get("role_name")
    if rn:
        step(dry, f"delete role policy + role {rn}",
             lambda: (iam.delete_role_policy(RoleName=rn, PolicyName="kb-access"),
                      iam.delete_role(RoleName=rn)))

    if not dry:
        L.C.STATE_FILE.unlink(missing_ok=True)
        print("\nTeardown complete. state.json removed.")
        print("Verify:  aws bedrock-agent list-knowledge-bases --region", state["region"])
        print("         aws s3vectors list-vector-buckets --region", state["region"])


if __name__ == "__main__":
    main()
