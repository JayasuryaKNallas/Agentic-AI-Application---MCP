import asyncio
import os
import sys
from dotenv import load_dotenv
from client.mcp_client import MCPClient
from agent.agent import ITOpsAgent

load_dotenv()

async def main():
    print("🚀 Starting IT Operations Assistant...")
    print("=" * 55)
    
    mcp_client = MCPClient()
    
    try:
        # Connect to all three servers
        # Note: HTTP servers must already be running before we connect
        await mcp_client.connect_to_stdio_server(
            "monitoring",
            "servers/monitoring_server.py"
        )
        await mcp_client.connect_to_http_server(
            "ticketing",
            "http://localhost:8001/sse"
        )
        await mcp_client.connect_to_http_server(
            "inventory",
            "http://localhost:8002/sse"
        )
        
        print(f"\n✅ All servers connected! Total tools available: {len(mcp_client.all_tools)}")
        print("=" * 55)
        
        # Create the agent
        agent = ITOpsAgent(mcp_client)
        
        # Interactive chat loop
        print("\n💬 IT Ops Assistant ready! Type 'quit' to exit, 'reset' to clear history.\n")
        print("Try asking:")
        print("  • 'What's the overall health of our infrastructure?'")
        print("  • 'Tell me everything about DB-01'")
        print("  • 'Are there any critical issues I should know about?'")
        print("  • 'Which servers are aging and need upgrades?'\n")
        print("  • Type 'summary' for a full operational briefing")
        
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Goodbye!")
                break
            
            if not user_input:
                continue
            if user_input.lower() == "quit":
                print("👋 Goodbye!")
                break
            if user_input.lower() == "reset":
                agent.reset_conversation()
                continue
            if user_input.lower() == "summary":
                response = await agent.generate_ops_summary()
                print(f"\n🤖 Assistant:\n{response}\n")
                continue
            
            # Get response from agent
            response = await agent.chat(user_input)
            print(f"\n🤖 Assistant:\n{response}\n")
    
    finally:
        await mcp_client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
