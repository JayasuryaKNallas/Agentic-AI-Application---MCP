# servers/monitoring_server.py
import asyncio
import random
import sys
import os
from datetime import datetime
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# import db helpers
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.setup_db import get_connection, setup_database

app = Server("monitoring-server")

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_server_metrics",
            description="Get real-time CPU, memory, and disk metrics for a server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "e.g. DB-01"}
                },
                "required": ["server_name"]
            }
        ),
        types.Tool(
            name="list_all_servers",
            description="List all servers and their current health status",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_alerts",
            description="Get active alerts for servers in warning or critical state",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="add_server_monitoring",
            description="Add a new server to the monitoring database with initial metrics",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string"},
                    "cpu":         {"type": "integer"},
                    "memory":      {"type": "integer"},
                    "disk":        {"type": "integer"},
                    "status":      {"type": "string", "enum": ["healthy","warning","critical"]}
                },
                "required": ["server_name","cpu","memory","disk","status"]
            }
        ),
        types.Tool(
            name="delete_server_monitoring",
            description="Remove a server from the monitoring database",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string"}
                },
                "required": ["server_name"]
            }
        ),
        types.Tool(
            name="update_server_status",
            description="Update a server's CPU, memory, disk, and status in the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string"},
                    "cpu":         {"type": "integer"},
                    "memory":      {"type": "integer"},
                    "disk":        {"type": "integer"},
                    "status":      {"type": "string", "enum": ["healthy","warning","critical"]}
                },
                "required": ["server_name", "cpu", "memory", "disk", "status"]
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    conn = get_connection()
    cursor = conn.cursor()

    try:
        if name == "get_server_metrics":
            server = arguments.get("server_name", "").upper()
            cursor.execute("SELECT * FROM servers WHERE name = ?", (server,))
            row = cursor.fetchone()
            if not row:
                return [types.TextContent(type="text", text=f"Server {server} not found")]
            result = f"""
Server: {row['name']}
Status: {row['status'].upper()}
CPU Usage: {row['cpu'] + random.randint(-3, 3)}%
Memory Usage: {row['memory'] + random.randint(-2, 2)}%
Disk Usage: {row['disk']}%
Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
            return [types.TextContent(type="text", text=result)]

        elif name == "list_all_servers":
            cursor.execute("SELECT * FROM servers")
            rows = cursor.fetchall()
            lines = ["=== Server Health Dashboard ==="]
            for r in rows:
                emoji = "🟢" if r["status"] == "healthy" else ("🟡" if r["status"] == "warning" else "🔴")
                lines.append(f"{emoji} {r['name']}: {r['status'].upper()} | CPU:{r['cpu']}% MEM:{r['memory']}%")
            return [types.TextContent(type="text", text="\n".join(lines))]

        elif name == "get_alerts":
            cursor.execute("SELECT * FROM servers WHERE status IN ('warning','critical')")
            rows = cursor.fetchall()
            if not rows:
                return [types.TextContent(type="text", text="✅ No active alerts")]
            alerts = [f"⚠️  [{r['status'].upper()}] {r['name']} — CPU:{r['cpu']}% Memory:{r['memory']}%" for r in rows]
            return [types.TextContent(type="text", text="\n".join(alerts))]
        
        elif name == "add_server_monitoring":
            server = arguments["server_name"].upper()
            try:
                cursor.execute(
                    "INSERT INTO servers VALUES (?,?,?,?,?)",
                    (server, arguments["cpu"], arguments["memory"],
                    arguments["disk"], arguments["status"])
                )
                conn.commit()
                return [types.TextContent(type="text",
                    text=f"✅ {server} added to monitoring — Status:{arguments['status']} CPU:{arguments['cpu']}% MEM:{arguments['memory']}%")]
            except Exception as e:
                return [types.TextContent(type="text", text=f"Error: {server} may already exist. {str(e)}")]

        elif name == "delete_server_monitoring":
            server = arguments["server_name"].upper()
            cursor.execute("DELETE FROM servers WHERE name = ?", (server,))
            if cursor.rowcount == 0:
                return [types.TextContent(type="text", text=f"Server {server} not found")]
            conn.commit()
            return [types.TextContent(type="text", text=f"🗑️  {server} removed from monitoring")]
        
        elif name == "update_server_status":
            server = arguments["server_name"].upper()
            cursor.execute(
                "UPDATE servers SET cpu=?, memory=?, disk=?, status=? WHERE name=?",
                (arguments["cpu"], arguments["memory"], arguments["disk"], arguments["status"], server)
            )
            if cursor.rowcount == 0:
                return [types.TextContent(type="text", text=f"Server {server} not found")]
            conn.commit()
            return [types.TextContent(type="text", text=f"✅ {server} updated — Status:{arguments['status']} CPU:{arguments['cpu']}% MEM:{arguments['memory']}%")]

    finally:
        conn.close()

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    setup_database()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())