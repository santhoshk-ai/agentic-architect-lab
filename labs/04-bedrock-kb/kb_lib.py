"""Provisioning helpers: S3 data bucket, S3 Vectors bucket/index, IAM role, Knowledge Base,
data source and ingestion. Every create is idempotent through state.json."""
import json
import time
import uuid

import boto3
from botocore.exceptions import ClientError

import config as C


# ---------------------------------------------------------------- state
def load_state():
    if C.STATE_FILE.exists():
        return json.loads(C.STATE_FILE.read_text())
    return {"kbs": {}}


def save_state(state):
    C.STATE_FILE.write_text(json.dumps(state, indent=2))


def clients():
    s = boto3.session.Session(region_name=C.REGION)
    return {
        "s3": s.client("s3"),
        "s3v": s.client("s3vectors"),
        "iam": s.client("iam"),
        "sts": s.client("sts"),
        "agent": s.client("bedrock-agent"),
        "rt": s.client("bedrock-agent-runtime"),
    }


def code(e):
    return e.response["Error"]["Code"]


# ---------------------------------------------------------------- names
def ensure_names(state, cl):
    if "account" not in state:
        state["account"] = cl["sts"].get_caller_identity()["Account"]
    if "suffix" not in state:
        state["suffix"] = uuid.uuid4().hex[:8]       # keeps the account ID out of bucket names
    state["region"] = C.REGION
    state.setdefault("data_bucket", f"{C.PREFIX}-data-{state['suffix']}")
    state.setdefault("vector_bucket", f"{C.PREFIX}-vec-{state['suffix']}")
    state.setdefault("role_name", f"{C.PREFIX}-kb-role-{state['suffix']}")
    save_state(state)
    return state


def embed_model_arn():
    return f"arn:aws:bedrock:{C.REGION}::foundation-model/{C.EMBED_MODEL_ID}"


def gen_model_arn(account):
    m = C.GEN_MODEL_ID
    if m.startswith("arn:"):
        return m
    if m.split(".")[0] in ("us", "eu", "apac", "global", "jp", "au", "ca"):
        return f"arn:aws:bedrock:{C.REGION}:{account}:inference-profile/{m}"
    return f"arn:aws:bedrock:{C.REGION}::foundation-model/{m}"


# ---------------------------------------------------------------- S3 data
def ensure_data_bucket(state, cl):
    b = state["data_bucket"]
    try:
        cl["s3"].head_bucket(Bucket=b)
        print(f"  data bucket exists: {b}")
    except ClientError:
        kw = {"Bucket": b}
        if C.REGION != "us-east-1":
            kw["CreateBucketConfiguration"] = {"LocationConstraint": C.REGION}
        cl["s3"].create_bucket(**kw)
        cl["s3"].put_public_access_block(
            Bucket=b,
            PublicAccessBlockConfiguration={k: True for k in (
                "BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")})
        print(f"  created data bucket: {b}")
    n = 0
    for f in sorted(C.CORPUS_DIR.iterdir()):
        if f.is_file():
            cl["s3"].upload_file(str(f), b, C.CORPUS_S3_PREFIX + f.name)
            n += 1
    print(f"  uploaded {n} corpus files (documents + .metadata.json sidecars)")


# ---------------------------------------------------------------- S3 Vectors
def ensure_vector_bucket(state, cl):
    vb = state["vector_bucket"]
    try:
        cl["s3v"].create_vector_bucket(vectorBucketName=vb)
        print(f"  created vector bucket: {vb}")
    except ClientError as e:
        if code(e) != "ConflictException":
            raise
        print(f"  vector bucket exists: {vb}")


def ensure_index(state, cl, strategy):
    vb, name = state["vector_bucket"], f"idx-{strategy}"
    try:
        arn = cl["s3v"].create_index(
            vectorBucketName=vb, indexName=name, dataType="float32",
            dimension=C.EMBED_DIMS, distanceMetric="cosine",
            # chunk text and Bedrock's own metadata are too big for filterable metadata (2 KB)
            metadataConfiguration={"nonFilterableMetadataKeys":
                                   ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]},
        )["indexArn"]
        print(f"  created index: {name}")
    except ClientError as e:
        if code(e) != "ConflictException":
            raise
        arn = cl["s3v"].get_index(vectorBucketName=vb, indexName=name)["index"]["indexArn"]
        print(f"  index exists: {name}")
    return name, arn


# ---------------------------------------------------------------- IAM
def ensure_role(state, cl):
    iam, acct, rn = cl["iam"], state["account"], state["role_name"]
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": acct},
                "ArnLike": {"AWS:SourceArn": f"arn:aws:bedrock:{C.REGION}:{acct}:knowledge-base/*"},
            },
        }],
    }
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "Embed", "Effect": "Allow", "Action": ["bedrock:InvokeModel"],
             "Resource": [embed_model_arn()]},
            {"Sid": "ListData", "Effect": "Allow", "Action": ["s3:ListBucket"],
             "Resource": [f"arn:aws:s3:::{state['data_bucket']}"],
             "Condition": {"StringEquals": {"aws:ResourceAccount": acct}}},
            {"Sid": "ReadData", "Effect": "Allow", "Action": ["s3:GetObject"],
             "Resource": [f"arn:aws:s3:::{state['data_bucket']}/*"],
             "Condition": {"StringEquals": {"aws:ResourceAccount": acct}}},
            {"Sid": "Vectors", "Effect": "Allow",
             "Action": ["s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors",
                        "s3vectors:QueryVectors", "s3vectors:GetIndex"],
             "Resource": f"arn:aws:s3vectors:{C.REGION}:{acct}:bucket/{state['vector_bucket']}/index/*"},
        ],
    }
    try:
        arn = iam.create_role(RoleName=rn, AssumeRolePolicyDocument=json.dumps(trust),
                              Description="Bedrock KB service role for labs/04-bedrock-kb")["Role"]["Arn"]
        print(f"  created role: {rn} (waiting 15 s for IAM propagation)")
        fresh = True
    except ClientError as e:
        if code(e) != "EntityAlreadyExists":
            raise
        arn = iam.get_role(RoleName=rn)["Role"]["Arn"]
        print(f"  role exists: {rn}")
        fresh = False
    iam.put_role_policy(RoleName=rn, PolicyName="kb-access", PolicyDocument=json.dumps(policy))
    if fresh:
        time.sleep(15)
    state["role_arn"] = arn
    save_state(state)
    return arn


# ---------------------------------------------------------------- KB + data source
def wait_kb(agent, kb_id):
    while True:
        st = agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]["status"]
        if st == "ACTIVE":
            return
        if st in ("FAILED", "DELETE_UNSUCCESSFUL", "UPDATE_UNSUCCESSFUL"):
            raise RuntimeError(f"KB {kb_id} status {st}")
        time.sleep(5)


def create_kb(state, cl, strategy, index_arn):
    agent = cl["agent"]
    for attempt in range(6):            # IAM propagation can take a few more seconds
        try:
            kb = agent.create_knowledge_base(
                name=f"{C.PREFIX}-{strategy}",
                description=f"labs/04 Nova City corpus, {strategy} chunking",
                roleArn=state["role_arn"],
                knowledgeBaseConfiguration={
                    "type": "VECTOR",
                    "vectorKnowledgeBaseConfiguration": {
                        "embeddingModelArn": embed_model_arn(),
                        "embeddingModelConfiguration": {"bedrockEmbeddingModelConfiguration": {
                            "dimensions": C.EMBED_DIMS, "embeddingDataType": "FLOAT32"}},
                    },
                },
                storageConfiguration={"type": "S3_VECTORS",
                                      "s3VectorsConfiguration": {"indexArn": index_arn}},
            )["knowledgeBase"]
            break
        except ClientError as e:
            if code(e) in ("ValidationException", "AccessDeniedException") and attempt < 5:
                print(f"  create_knowledge_base retry {attempt + 1}: {e.response['Error']['Message'][:120]}")
                time.sleep(10)
                continue
            raise
    wait_kb(agent, kb["knowledgeBaseId"])
    print(f"  KB active: {kb['knowledgeBaseId']} ({strategy})")
    return kb["knowledgeBaseId"]


def create_data_source(state, cl, kb_id, strategy):
    ds = cl["agent"].create_data_source(
        knowledgeBaseId=kb_id,
        name=f"ds-{strategy}",
        dataSourceConfiguration={"type": "S3", "s3Configuration": {
            "bucketArn": f"arn:aws:s3:::{state['data_bucket']}",
            "inclusionPrefixes": [C.CORPUS_S3_PREFIX]}},
        vectorIngestionConfiguration={"chunkingConfiguration": C.STRATEGIES[strategy]},
        dataDeletionPolicy="DELETE",
    )["dataSource"]
    print(f"  data source: {ds['dataSourceId']} ({C.STRATEGIES[strategy]['chunkingStrategy']})")
    return ds["dataSourceId"]


def ingest(cl, kb_id, ds_id):
    agent = cl["agent"]
    t0 = time.time()
    job = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]
    while job["status"] not in ("COMPLETE", "FAILED", "STOPPED"):
        time.sleep(10)
        job = agent.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id,
                                      ingestionJobId=job["ingestionJobId"])["ingestionJob"]
    secs = round(time.time() - t0)
    if job["status"] != "COMPLETE":
        raise RuntimeError(f"ingestion {job['status']}: {job.get('failureReasons')}")
    stats = job.get("statistics", {})
    print(f"  ingestion COMPLETE in {secs}s: "
          f"scanned={stats.get('numberOfDocumentsScanned')} "
          f"indexed={stats.get('numberOfNewDocumentsIndexed')} "
          f"failed={stats.get('numberOfDocumentsFailed')}")
    return stats, secs


def ensure_kb(state, cl, strategy):
    """Index + KB + data source + ingestion for one chunking strategy (skips what exists)."""
    if strategy in state["kbs"] and state["kbs"][strategy].get("ingested"):
        print(f"  [{strategy}] already provisioned: {state['kbs'][strategy]['kb_id']}")
        return state["kbs"][strategy]
    rec = state["kbs"].setdefault(strategy, {})
    rec["index_name"], rec["index_arn"] = ensure_index(state, cl, strategy)
    save_state(state)
    if "kb_id" not in rec:
        rec["kb_id"] = create_kb(state, cl, strategy, rec["index_arn"])
        save_state(state)
    if "ds_id" not in rec:
        rec["ds_id"] = create_data_source(state, cl, rec["kb_id"], strategy)
        save_state(state)
    stats, secs = ingest(cl, rec["kb_id"], rec["ds_id"])
    rec.update(ingested=True, ingest_seconds=secs,
               docs_indexed=stats.get("numberOfNewDocumentsIndexed"))
    save_state(state)
    return rec


def provision_base(state, cl):
    ensure_names(state, cl)
    print("== base resources")
    ensure_data_bucket(state, cl)
    ensure_vector_bucket(state, cl)
    ensure_role(state, cl)
