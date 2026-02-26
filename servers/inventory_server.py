# servers/inventory_server.py
import sys
import os
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp import types
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
import uvicorn

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.setup_db import get_connection, setup_database

app = Server("inventory-server")

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_server_info",
            description="Get full hardware and config details for a server from inventory",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string"}
                },
                "required": ["server_name"]
            }
        ),
        types.Tool(
            name="get_servers_by_owner",
            description="Find all servers owned by a specific team",
            inputSchema={
                "type": "object",
                "properties": {
                    "team_name": {"type": "string"}
                },
                "required": ["team_name"]
            }
        ),
        types.Tool(
            name="get_aging_servers",
            description="Find servers older than a given number of years",
            inputSchema={
                "type": "object",
                "properties": {
                    "older_than_years": {"type": "number", "default": 3}
                }
            }
        ),
        types.Tool(
            name="add_server",
            description="Add a new server to the inventory database",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":       {"type": "string"},
                    "type":       {"type": "string"},
                    "os":         {"type": "string"},
                    "ram":        {"type": "string"},
                    "cpu_cores":  {"type": "integer"},
                    "location":   {"type": "string"},
                    "owner":      {"type": "string"},
                    "ip":         {"type": "string"},
                    "age_years":  {"type": "integer"}
                },
                "required": ["name","type","os","ram","cpu_cores","location","owner","ip","age_years"]
            }
        ),
        types.Tool(
            name="update_server_info",
            description="Update details of an existing server in the inventory",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string"},
                    "field":       {"type": "string", "description": "Column to update: os, ram, cpu_cores, location, owner, ip, age_years"},
                    "value":       {"type": "string", "description": "New value"}
                },
                "required": ["server_name", "field", "value"]
            }
        ),
        types.Tool(
            name="delete_server",
            description="Remove a server from the inventory database",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string"}
                },
                "required": ["server_name"]
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    conn = get_connection()
    cursor = conn.cursor()

    try:
        if name == "get_server_info":
            server = arguments.get("server_name", "").upper()
            cursor.execute("SELECT * FROM inventory WHERE name = ?", (server,))
            row = cursor.fetchone()
            if not row:
                return [types.TextContent(type="text", text=f"Server {server} not found in inventory")]
            result = f"""
Asset: {row['name']}
Type: {row['type']}
OS: {row['os']}
RAM: {row['ram']} | CPU Cores: {row['cpu_cores']}
IP Address: {row['ip']}
Location: {row['location']}
Owner: {row['owner']}
Age: {row['age_years']} year(s)
            """.strip()
            return [types.TextContent(type="text", text=result)]

        elif name == "get_servers_by_owner":
            team = arguments.get("team_name", "")
            cursor.execute("SELECT * FROM inventory WHERE owner LIKE ?", (f"%{team}%",))
            rows = cursor.fetchall()
            if not rows:
                return [types.TextContent(type="text", text=f"No servers found for team: {team}")]
            lines = [f"Servers owned by {team}:"]
            for r in rows:
                lines.append(f"  {r['name']} — {r['type']} ({r['os']}) @ {r['location']}")
            return [types.TextContent(type="text", text="\n".join(lines))]

        elif name == "get_aging_servers":
            threshold = arguments.get("older_than_years", 3)
            cursor.execute("SELECT * FROM inventory WHERE age_years >= ?", (threshold,))
            rows = cursor.fetchall()
            if not rows:
                return [types.TextContent(type="text", text=f"No servers older than {threshold} years")]
            lines = [f"Servers older than {threshold} years:"]
            for r in rows:
                lines.append(f"  {r['name']}: {r['age_years']}yr — {r['os']} — Owner: {r['owner']}")
            return [types.TextContent(type="text", text="\n".join(lines))]

        elif name == "add_server":
            server = arguments["name"].upper()
            cursor.execute(
                "INSERT INTO inventory VALUES (?,?,?,?,?,?,?,?,?)",
                (server, arguments["type"], arguments["os"], arguments["ram"],
                 arguments["cpu_cores"], arguments["location"], arguments["owner"],
                 arguments["ip"], arguments["age_years"])
            )
            conn.commit()
            return [types.TextContent(type="text", text=f"✅ Server {server} added to inventory")]

        elif name == "update_server_info":
            server = arguments["server_name"].upper()
            field  = arguments["field"]
            value  = arguments["value"]
            # whitelist allowed fields to prevent SQL injection
            allowed = {"os","ram","cpu_cores","location","owner","ip","age_years","type"}
            if field not in allowed:
                return [types.TextContent(type="text", text=f"Field '{field}' is not updatable")]
            cursor.execute(f"UPDATE inventory SET {field} = ? WHERE name = ?", (value, server))
            if cursor.rowcount == 0:
                return [types.TextContent(type="text", text=f"Server {server} not found")]
            conn.commit()
            return [types.TextContent(type="text", text=f"✅ {server} — {field} updated to '{value}'")]

        elif name == "delete_server":
            server = arguments["server_name"].upper()
            cursor.execute("DELETE FROM inventory WHERE name = ?", (server,))
            if cursor.rowcount == 0:
                return [types.TextContent(type="text", text=f"Server {server} not found in inventory")]
            conn.commit()
            return [types.TextContent(type="text", text=f"🗑️  Server {server} removed from inventory")]

    finally:
        conn.close()

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


def create_starlette_app():
    sse = SseServerTransport("/messages/")
    async def handle_sse(request: Request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())
    return Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ])

if __name__ == "__main__":
    setup_database()
    starlette_app = create_starlette_app()
    uvicorn.run(starlette_app, host="0.0.0.0", port=8002)