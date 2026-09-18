from mcp_servers.common import serve
from mcp_servers.orchestration_metadata.server import build_server

serve(build_server(), default_port=8102)
