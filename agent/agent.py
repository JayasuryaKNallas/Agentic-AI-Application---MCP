import json
import os
from openai import OpenAI
from client.mcp_client import MCPClient

class ITOpsAgent:
    """
    ReAct Agent powered by gpt-oss-120b running on Groq.

    The ReAct loop works the same way — the only difference is the
    OpenAI-compatible API format for tool calls vs Anthropic's format.

    Groq's API is OpenAI-compatible, meaning:
    - Same endpoint structure as OpenAI
    - Same message format (role: user/assistant/tool)
    - Same tool_calls response format
    - Just a different base_url and API key
    """

    def __init__(self, mcp_client: MCPClient):
        # Point the OpenAI client at Groq's endpoint
        self.client = OpenAI(
            api_key=os.environ.get("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )
        self.model = "openai/gpt-oss-120b"
        self.mcp_client = mcp_client
        self.conversation_history = []

        self.system_prompt = """You are an expert IT Operations Assistant with access to three enterprise systems:

1. **Monitoring System**: Real-time server metrics (CPU, memory, disk, alerts)
2. **Ticketing System**: Incident tickets and support requests
3. **Inventory System**: Server asset details and configurations (CMDB)

Your job is to help IT operations teams quickly understand system health, investigate issues, and make informed decisions.

When answering questions:
- Always gather data from relevant systems before responding
- Correlate information across systems (e.g., if a server has high CPU AND open tickets, mention both)
- Be concise but thorough — ops teams are busy
- Flag critical issues clearly
- Suggest next steps when appropriate

Available servers: DB-01, WEB-01, WEB-02, APP-01"""

    def _get_tools_for_groq(self) -> list[dict]:
        """
        Convert MCP tools into OpenAI/Groq tool format.
        Groq expects: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        This is slightly different from Anthropic's format which uses "input_schema".
        """
        tools = []
        for tool in self.mcp_client.all_tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema  # same schema, different key name
                }
            })
        return tools

    async def chat(self, user_message: str) -> str:
        """Process a user message through the ReAct loop"""

        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        print(f"\n{'='*50}")
        print(f"User: {user_message}")
        print(f"{'='*50}")

        # ReAct Loop
        while True:
            print("\n[Agent] Thinking...")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *self.conversation_history
                ],
                tools=self._get_tools_for_groq(),
                tool_choice="auto",   # Let the model decide when to use tools
                max_tokens=4096,
                temperature=0.2       # Lower = more deterministic, good for ops tasks
            )

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            print(f"[Agent] Finish reason: {finish_reason}")

            # --- Case 1: Model wants to call tools ---
            if finish_reason == "tool_calls":

                # Add assistant's message (with tool_calls) to history
                # Important: we must store it exactly as returned so the model
                # can match tool results back to tool call IDs
                self.conversation_history.append({
                    "role": "assistant",
                    "content": message.content,       # may be None
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                })

                # Execute each tool call
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    
                    # Groq returns arguments as a JSON STRING — must parse it
                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}

                    print(f"[Agent] 🔧 Calling tool: {tool_name} with args: {tool_args}")

                    # Route through MCP client to the correct server
                    result = await self.mcp_client.call_tool(tool_name, tool_args)
                    print(f"[Agent] 📊 Result:\n{result}")

                    # Add each tool result back to history
                    # OpenAI format requires role="tool" with the matching tool_call_id
                    self.conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,   # must match the call ID above
                        "content": result
                    })

                # Loop continues — model will now see results and reason again

            # --- Case 2: Model has final answer ---
            elif finish_reason == "stop":
                final_answer = message.content or "No response generated."

                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_answer
                })

                return final_answer

            else:
                return f"Unexpected finish reason: {finish_reason}"

    def reset_conversation(self):
        self.conversation_history = []
        print("[Agent] Conversation history cleared.")

    async def generate_ops_summary(self) -> str:
        """
        Proactively pulls data from all three systems and generates
        a structured operational insights report — no user question needed.
        """
        summary_prompt = """Give me a full operational summary of our infrastructure right now.

    I need you to:
    1. Check all server health and active alerts from monitoring
    2. Pull all open and in-progress tickets from the ticketing system  
    3. Identify any aging servers from inventory that need attention
    4. Cross-reference everything — if a server has both high metrics AND open tickets, flag it as a priority
    5. End with a clear 'Action Items' section listing what needs attention today

    Structure your response as a proper ops briefing."""

        return await self.chat(summary_prompt)

