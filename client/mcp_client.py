import asyncio
import sys
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

class MCPClient:
    """
    The MCP Client manages connections to all MCP servers.
    It collects all available tools and provides a unified interface
    for the agent to call any tool across any server.
    """

    def __init__(self):
        self.sessions: dict[str, ClientSession] = {}   # server_name → session
        self.tool_to_server: dict[str, str] = {}       # tool_name → server_name
        self.all_tools: list = []
        self.exit_stack = AsyncExitStack()

    async def connect_to_stdio_server(self, server_name: str, script_path: str):
        """Connect to a STDIO-based MCP server (runs it as a subprocess)"""
        print(f"[MCP Client] Connecting to STDIO server: {server_name}")
        
        server_params = StdioServerParameters(
            command=sys.executable,   # path to current Python interpreter
            args=[script_path],       # script to run as subprocess
            env=None
        )
        
        # stdio_client launches the subprocess and creates read/write streams
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = stdio_transport
        
        # ClientSession handles the MCP handshake and protocol
        session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        
        self.sessions[server_name] = session
        await self._register_tools(server_name, session)
        print(f"[MCP Client] ✅ Connected to {server_name}")

    async def connect_to_http_server(self, server_name: str, url: str):
        """Connect to an HTTP/SSE-based MCP server"""
        print(f"[MCP Client] Connecting to HTTP server: {server_name} at {url}")
        
        sse_transport = await self.exit_stack.enter_async_context(
            sse_client(url)
        )
        read_stream, write_stream = sse_transport
        
        session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        
        self.sessions[server_name] = session
        await self._register_tools(server_name, session)
        print(f"[MCP Client] ✅ Connected to {server_name}")

    async def _register_tools(self, server_name: str, session: ClientSession):
        """Ask server what tools it offers, and index them"""
        response = await session.list_tools()
        for tool in response.tools:
            self.tool_to_server[tool.name] = server_name
            self.all_tools.append(tool)
            print(f"  → Registered tool: {tool.name} (from {server_name})")

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Route a tool call to the correct server"""
        server_name = self.tool_to_server.get(tool_name)
        if not server_name:
            return f"Error: No server found for tool '{tool_name}'"
        
        session = self.sessions[server_name]
        print(f"[MCP Client] Calling {tool_name} on {server_name}")
        
        result = await session.call_tool(tool_name, arguments)
        
        # Extract text from the result content
        return "\n".join(
            block.text for block in result.content 
            if hasattr(block, "text")
        )

    async def cleanup(self):
        await self.exit_stack.aclose()