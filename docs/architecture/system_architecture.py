from pathlib import Path
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.general import User, Client, General
from diagrams.aws.network import CloudFront
from diagrams.aws.compute import Lambda
from diagrams.aws.security import WAF, IAM
from diagrams.aws.ml import Bedrock
from diagrams.aws.storage import S3
from diagrams.aws.analytics import AmazonOpensearchService
from diagrams.aws.management import Cloudwatch
from diagrams.aws.integration import Eventbridge

OUTPUT = Path(__file__).resolve().with_name("system_architecture")
GRAPH = {
    "splines": "polyline",  
    "nodesep": "0.60",
    "ranksep": "0.90",
    "pad": "0.35",
    "compound": "true",
    "newrank": "true",
    "fontsize": "18",
    "bgcolor": "white",
}
NODE = {"fontsize": "11"}
EDGE = {"fontsize": "10", "arrowsize": ".7"}

with Diagram(
    name="EDGAR - SEC Filings Financial Research Assistant",
    filename=str(OUTPUT),
    show=False,
    direction="TB",
    outformat="png",
    graph_attr=GRAPH,
    node_attr=NODE,
    edge_attr=EDGE,
):
    operator = User(label="User")
    browser = Client(label="Browser")
    sec_api = General(label="SEC EDGAR API")

    with Cluster(label="Public Web Edge"):
        waf = WAF(label="AWS WAF\n(Rate Limiting)")
        cloudfront = CloudFront(label="CloudFront\n(Response Streaming)")
        waf - Edge(style="dashed", label="Protects") - cloudfront

    with Cluster(label="Compute & Orchestration"):
        orchestrator = Lambda(label="Orchestrator Lambda\n(Function URL + OAC)")

    operator >> browser >> cloudfront
    cloudfront >> Edge(label="Streaming Request") >> orchestrator

    with Cluster(label="Agentic Layer"):
        bedrock = Bedrock(label="Bedrock Agent\n(Guardrails + Memory)")
        knowledge_base = Bedrock(label="Bedrock Knowledge Base")
        bedrock >> Edge(label="Semantic Search") >> knowledge_base

    orchestrator >> Edge(label="InvokeAgent") >> bedrock

    with Cluster(label="RAG Retrieval & Storage"):
        open_search = AmazonOpensearchService(label="OpenSearch Serverless\n(Vector Store)")
        s3_raw = S3(label="S3 Document Store\n(Raw PDFs)")

    knowledge_base >> Edge(label="Vector Query") >> open_search
    knowledge_base >> Edge(label="Chunk & Embed") >> s3_raw

    with Cluster(label="Dynamic Tooling"):
        tool_call = Lambda(label="SEC Filing Tool Lambda\n(Extract Items 1A, 7)")

    bedrock >> Edge(label="Action Group") >> tool_call
    tool_call >> Edge(label="Fetch Filing") >> sec_api
    tool_call >> Edge(label="PutObject (PDF)") >> s3_raw

    with Cluster(label="Event-Driven Ingestion"):
        s3_event = Eventbridge(label="S3 Event Notification\n(s3:ObjectCreated:*)")
        ingest_lambda = Lambda(label="Ingestion Trigger Lambda")

    s3_raw >> s3_event >> ingest_lambda
    ingest_lambda >> Edge(label="StartIngestionJob") >> knowledge_base

    with Cluster(label="Security & Observability"):
        iam = IAM(label="Least-Privilege\nIAM Roles")
        cloudwatch = Cloudwatch(label="CloudWatch\nLogs & Metrics")
        s3_logs = S3(label="Bedrock Model\nInvocation Logs")

    bedrock >> Edge(style="dashed", label="Traces") >> cloudwatch
    bedrock >> Edge(style="dashed", label="Audit Logs") >> s3_logs
    orchestrator >> Edge(style="dashed") >> cloudwatch
    iam - Edge(style="dotted", label="Execution Policies") - bedrock
