# servers/ticketing_server.py
import sys
import os
from datetime import datetime
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp import types
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
import uvicorn

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.setup_db import get_connection, setup_database

app = Server("ticketing-server")

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_tickets_for_server",
            description="Get all tickets for a specific server, optionally filtered by status",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string"},
                    "status": {"type": "string", "description": "open, in_progress, resolved, or all", "default": "all"}
                },
                "required": ["server_name"]
            }
        ),
        types.Tool(
            name="get_open_tickets_summary",
            description="Summary of all open and in-progress tickets across all servers",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="create_ticket",
            description="Create a new incident ticket for a server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_name": {"type": "string"},
                    "title":       {"type": "string"},
                    "priority":    {"type": "string", "enum": ["low","medium","high","critical"]}
                },
                "required": ["server_name", "title", "priority"]
            }
        ),
        types.Tool(
            name="update_ticket_status",
            description="Update the status of an existing ticket",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "e.g. INC-001"},
                    "status":    {"type": "string", "enum": ["open","in_progress","resolved"]}
                },
                "required": ["ticket_id", "status"]
            }
        ),
        types.Tool(
            name="delete_ticket",
            description="Delete a ticket from the system by ticket ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "e.g. INC-001"}
                },
                "required": ["ticket_id"]
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    conn = get_connection()
    cursor = conn.cursor()

    try:
        if name == "get_tickets_for_server":
            server = arguments.get("server_name", "").upper()
            status_filter = arguments.get("status", "all")

            if status_filter == "all":
                cursor.execute("SELECT * FROM tickets WHERE server_name = ?", (server,))
            else:
                cursor.execute(
                    "SELECT * FROM tickets WHERE server_name = ? AND status = ?",
                    (server, status_filter)
                )
            rows = cursor.fetchall()
            if not rows:
                return [types.TextContent(type="text", text=f"No tickets found for {server}")]
            lines = [f"Tickets for {server}:"]
            for r in rows:
                lines.append(f"  [{r['id']}] {r['title']} | Priority: {r['priority']} | Status: {r['status']}")
            return [types.TextContent(type="text", text="\n".join(lines))]

        elif name == "get_open_tickets_summary":
            cursor.execute("SELECT * FROM tickets WHERE status IN ('open','in_progress')")
            rows = cursor.fetchall()
            critical = [r for r in rows if r["priority"] == "critical"]
            high     = [r for r in rows if r["priority"] == "high"]
            summary  = f"""Open Tickets Summary:
Total open/in-progress: {len(rows)}
Critical: {len(critical)}
High priority: {len(high)}

Critical tickets:
""" + ("\n".join(f"  [{r['id']}] {r['server_name']}: {r['title']}" for r in critical) or "  None")
            return [types.TextContent(type="text", text=summary)]

        elif name == "create_ticket":
            # generate next ticket ID from DB
            cursor.execute("SELECT COUNT(*) FROM tickets")
            count = cursor.fetchone()[0]
            new_id = f"INC-{str(count + 1).zfill(3)}"
            today  = datetime.now().strftime("%Y-%m-%d")
            cursor.execute(
                "INSERT INTO tickets VALUES (?,?,?,?,?,?)",
                (new_id, arguments["server_name"].upper(), arguments["title"], arguments["priority"], "open", today)
            )
            conn.commit()
            return [types.TextContent(type="text", text=f"✅ Ticket {new_id} created for {arguments['server_name'].upper()}: {arguments['title']} [{arguments['priority']}]")]

        elif name == "update_ticket_status":
            cursor.execute(
                "UPDATE tickets SET status = ? WHERE id = ?",
                (arguments["status"], arguments["ticket_id"].upper())
            )
            if cursor.rowcount == 0:
                return [types.TextContent(type="text", text=f"Ticket {arguments['ticket_id']} not found")]
            conn.commit()
            return [types.TextContent(type="text", text=f"✅ Ticket {arguments['ticket_id']} updated to '{arguments['status']}'")]

        elif name == "delete_ticket":
            cursor.execute("DELETE FROM tickets WHERE id = ?", (arguments["ticket_id"].upper(),))
            if cursor.rowcount == 0:
                return [types.TextContent(type="text", text=f"Ticket {arguments['ticket_id']} not found")]
            conn.commit()
            return [types.TextContent(type="text", text=f"🗑️  Ticket {arguments['ticket_id']} deleted")]

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
    uvicorn.run(starlette_app, host="0.0.0.0", port=8001)