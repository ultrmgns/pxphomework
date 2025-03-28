import os
import time
import json
import requests # For MCP client calls
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta

# --- Configuration ---
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env file")

client = OpenAI(api_key=OPENAI_API_KEY)

# URL of your running MCP server
MCP_SERVER_URL = "http://localhost:5003" # Use the IP if server is on another machine

# --- Assistant Setup ---
# Define the tools for the Assistants (matching names in MCP server)
# IMPORTANT: The parameter descriptions here help the Assistant call the tools correctly.
tools_definition = [
    {
        "type": "function",
        "function": {
            "name": "get_merchant_profile",
            "description": "Gets profile information for a specific merchant ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string", "description": "The unique ID of the merchant."},
                },
                "required": ["merchant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_merchant_aggregated_stats",
            "description": "Calculates aggregated transaction statistics for a merchant within a specified ISO format date range (e.g., YYYY-MM-DDTHH:MM:SS).",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string", "description": "The unique ID of the merchant."},
                    "start_date_str": {"type": "string", "description": "The start date/time in ISO format (YYYY-MM-DDTHH:MM:SS)."},
                    "end_date_str": {"type": "string", "description": "The end date/time in ISO format (YYYY-MM-DDTHH:MM:SS)."},
                },
                "required": ["merchant_id", "start_date_str", "end_date_str"],
            },
        },
    },
     {
        "type": "function",
        "function": {
            "name": "get_anomalous_transactions",
            "description": "Retrieves examples of potentially anomalous transactions (e.g., high value) for a merchant within a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string", "description": "The unique ID of the merchant."},
                    "start_date_str": {"type": "string", "description": "The start date/time in ISO format (YYYY-MM-DDTHH:MM:SS)."},
                    "end_date_str": {"type": "string", "description": "The end date/time in ISO format (YYYY-MM-DDTHH:MM:SS)."},
                    "min_amount": {"type": "number", "description": "Optional minimum transaction amount to consider anomalous (default 1000.0)."},
                },
                "required": ["merchant_id", "start_date_str", "end_date_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_merchant_risk_status",
            "description": "Updates the merchant's risk status based on analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string", "description": "The unique ID of the merchant."},
                    "new_status": {"type": "string", "description": "The new risk status (e.g., 'High', 'Medium', 'Low', 'Watchlist')."},
                    "reason_code": {"type": "string", "description": "A brief code or reason for the status change."},
                },
                "required": ["merchant_id", "new_status", "reason_code"],
            },
        },
    },
        {
        "type": "function",
        "function": {
            "name": "create_aml_manual_review_case",
            "description": "Creates a manual review case for AML Compliance when high risk is detected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string", "description": "The unique ID of the merchant requiring review."},
                    "risk_category": {"type": "string", "description": "The assessed risk category (e.g., 'High', 'Critical')."},
                    "summary": {"type": "string", "description": "A concise summary of the reasons for escalation."},
                    "key_indicators": {"type": "array", "items": {"type": "string"}, "description": "List of specific ML/TL indicators detected."},
                },
                "required": ["merchant_id", "risk_category", "summary", "key_indicators"],
            },
        },
    }
]

# --- Assistant Creation/Retrieval ---
# It's better to create assistants once and reuse their IDs.
# Replace with your actual Assistant IDs after creating them once.
ASSISTANT_IDS = {
    "Data Aggregation": None, # Replace with ID like "asst_..."
    "Pattern Detection": None, # Replace with ID like "asst_..."
    "Risk Assessment": None, # Replace with ID like "asst_..."
    "Action Alerting": None, # Replace with ID like "asst_..."
}

def create_or_retrieve_assistant(name, instructions, tools, model="gpt-4-turbo-preview"):
    """Creates an assistant or retrieves ID if already defined."""
    assistant_id = ASSISTANT_IDS.get(name)
    if assistant_id:
        print(f"Using existing Assistant ID for {name}: {assistant_id}")
        return assistant_id

    print(f"Creating new Assistant for {name}...")
    assistant = client.beta.assistants.create(
        name=name,
        instructions=instructions,
        tools=tools,
        model=model,
    )
    ASSISTANT_IDS[name] = assistant.id
    print(f"Created Assistant {name} with ID: {assistant.id}")
    return assistant.id

# Define Instructions for each Agent
instructions = {
    "Data Aggregation": """Your task is to gather and summarize relevant data for a given merchant ID covering a specific period.
Use the provided tools to fetch:
1. The merchant's profile.
2. Aggregated transaction statistics (total volume, value, avg value, card types, countries, rounded values).
3. Examples of anomalous transactions (e.g., high value).
Present this information clearly and concisely for the next agent. Use ISO format (YYYY-MM-DDTHH:MM:SS) for dates.""",

    "Pattern Detection": """Analyze the provided aggregated data, anomalous transaction examples, and profile information for the merchant.
Identify patterns potentially indicative of Money/Transaction Laundering based on known indicators like:
- High percentage of prepaid cards
- High percentage of rounded transaction values
- Significant activity from high-risk jurisdictions (check profile and card countries)
- Transaction values inconsistent with the merchant category code (MCC) profile
- Structuring patterns (if suggested by transaction examples or velocity)
- Sudden changes in activity volume/value (compare stats over time if possible - requires history not implemented here)
- Ownership changes noted in profile combined with other risks.
List the specific patterns detected.""",

    "Risk Assessment": """Based *only* on the input (merchant profile, aggregated stats, and detected ML/TL patterns), assess the overall ML/TL risk level for the merchant.
Assign a risk category: 'Low', 'Medium', 'High', or 'Critical'.
Provide a clear, concise justification summarizing the key contributing factors and detected indicators. Do not use external tools.""",

    "Action Alerting": """The assessed ML/TL risk for the merchant is [Risk Category] due to [Justification].
Based on this assessment, determine the appropriate next steps according to this policy:
- Low: No action needed. State this.
- Medium: Update status to 'Medium Risk Watchlist'.
- High: Update status to 'High Risk' and create a manual review case.
- Critical: Update status to 'Critical Risk - Urgent Review' and create a manual review case.
Use the provided tools ('update_merchant_risk_status', 'create_aml_manual_review_case') to execute these actions. Confirm the actions taken."""
}

# Create or get IDs (run this part once initially if IDs are None)
if any(v is None for v in ASSISTANT_IDS.values()):
    print("Setting up Assistants...")
    ASSISTANT_IDS["Data Aggregation"] = create_or_retrieve_assistant("Data Aggregation", instructions["Data Aggregation"], tools_definition)
    ASSISTANT_IDS["Pattern Detection"] = create_or_retrieve_assistant("Pattern Detection", instructions["Pattern Detection"], tools_definition) # May need tools later
    ASSISTANT_IDS["Risk Assessment"] = create_or_retrieve_assistant("Risk Assessment", instructions["Risk Assessment"], []) # No tools needed
    ASSISTANT_IDS["Action Alerting"] = create_or_retrieve_assistant("Action Alerting", instructions["Action Alerting"], tools_definition)
    print("--- Assistant Setup Complete ---")
    print("Please copy these IDs into the ASSISTANT_IDS dictionary in the script for future runs:")
    print(ASSISTANT_IDS)
    # exit() # Exit after first run to save IDs

# --- MCP Client Function ---
def execute_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Sends a tool execution request to the MCP server."""
    print(f"  [MCP Client] Requesting execution: {tool_name} with args: {arguments}")
    try:
        response = requests.post(
            f"{MCP_SERVER_URL}/execute",
            json={"tool_name": tool_name, "arguments": arguments},
            timeout=30 # Add a timeout
        )
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        result_data = response.json()
        if "error" in result_data:
             print(f"  [MCP Server Error] Tool {tool_name}: {result_data['error']}")
             return json.dumps({"error": result_data['error']}) # Return error as JSON string
        print(f"  [MCP Client] Received result for {tool_name}")
        # The Assistant API expects the tool output as a JSON string
        return json.dumps(result_data.get("result", {}))
    except requests.exceptions.RequestException as e:
        print(f"  [MCP Client Error] Failed to connect or execute tool {tool_name}: {e}")
        return json.dumps({"error": f"MCP connection error: {e}"})
    except json.JSONDecodeError as e:
         print(f"  [MCP Client Error] Failed to decode JSON response from MCP server for {tool_name}: {e}")
         return json.dumps({"error": f"MCP invalid JSON response: {e}"})


# --- Orchestration Functions ---
def wait_for_run_completion(thread_id, run_id, agent_name):
    """Polls the run status and handles tool calls via MCP."""
    print(f"  Waiting for {agent_name} (Run ID: {run_id})...")
    while True:
        try:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            status = run.status
            # print(f"    Run status: {status}")

            if status == "completed":
                print(f"  ✅ {agent_name} completed.")
                return run
            elif status == "requires_action":
                print(f"  🛠️ {agent_name} requires action (tool calls)...")
                tool_outputs = []
                for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                    tool_name = tool_call.function.name
                    # Arguments are a JSON string, parse them
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                         print(f"  [Error] Could not parse arguments for {tool_name}: {tool_call.function.arguments}")
                         output = json.dumps({"error": "Invalid arguments JSON received from Assistant"})
                         arguments = {} # Prevent crash in execute_mcp_tool

                    # Execute tool via MCP Server
                    output = execute_mcp_tool(tool_name=tool_name, arguments=arguments)

                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": output,
                    })

                # Submit outputs back to the Assistant
                print(f"  Submitting {len(tool_outputs)} tool output(s)...")
                client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run_id,
                    tool_outputs=tool_outputs
                )
            elif status in ["failed", "cancelled", "expired"]:
                print(f"  ❌ {agent_name} Run {status}. Details: {run.last_error}")
                return run # Return failed run object
            elif status in ["queued", "in_progress"]:
                 pass # Continue polling
            else:
                 print(f"  ❓ Unknown run status: {status}")

            time.sleep(2) # Wait before polling again

        except Exception as e:
            print(f"  [Error] Exception while checking run status: {e}")
            time.sleep(5) # Wait longer after an error


def get_latest_message_content(thread_id):
    """Retrieves the text content of the latest message in a thread."""
    try:
        messages = client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=1)
        if messages.data:
            message = messages.data[0]
            if message.content:
                 # Get the last text content part
                 text_content = [block.text.value for block in message.content if block.type == 'text']
                 return "\n".join(text_content)
        return None # No messages or no text content
    except Exception as e:
        print(f"  [Error] Failed to retrieve messages: {e}")
        return None

# --- Main Workflow ---
def analyze_merchant(merchant_id: str, analysis_days: int = 7):
    """Runs the full agent workflow for a single merchant."""
    print(f"\n--- Starting Analysis for Merchant: {merchant_id} ---")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=analysis_days)
    start_date_str = start_date.isoformat(timespec='seconds')
    end_date_str = end_date.isoformat(timespec='seconds')

    try:
        # 1. Create a Thread
        thread = client.beta.threads.create()
        print(f"Created Thread ID: {thread.id}")

        # 2. Initial Message (Task for Data Aggregation)
        initial_message = f"Please gather data for merchant '{merchant_id}' from {start_date_str} to {end_date_str}."
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=initial_message,
        )
        print(f"Initial message sent: '{initial_message}'")

        # --- Agent Sequence ---
        current_assistant_id = ASSISTANT_IDS["Data Aggregation"]
        agent_name = "Data Aggregation"
        run_instructions = None # No specific instructions needed for first run

        for next_agent_name in ["Pattern Detection", "Risk Assessment", "Action Alerting", "Done"]:
            # 3. Run the current Assistant
            print(f"\nRunning {agent_name}...")
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=current_assistant_id,
                instructions=run_instructions # Pass instructions if needed for this step
            )

            # 4. Wait for completion (handles tool calls via MCP)
            run_result = wait_for_run_completion(thread.id, run.id, agent_name)

            if run_result.status != "completed":
                 print(f"Workflow stopped due to {agent_name} run failure.")
                 break # Exit loop for this merchant on failure

            # 5. Get the result message (optional, good for logging/debugging)
            last_message = get_latest_message_content(thread.id)
            print(f"  Result from {agent_name}:\n---\n{last_message}\n---")

            # 6. Prepare for the next agent
            if next_agent_name == "Done":
                print(f"\n--- Analysis Complete for Merchant: {merchant_id} ---")
                break

            agent_name = next_agent_name
            current_assistant_id = ASSISTANT_IDS[agent_name]
            # Optional: Add specific instructions for the next agent based on previous output
            # run_instructions = f"Based on the previous analysis:\n{last_message}\n\nPlease perform your task."
            run_instructions = None # Keep it simple for now

    except Exception as e:
        print(f"\n--- [Error] Workflow failed for Merchant {merchant_id}: {e} ---")
        import traceback
        traceback.print_exc()


# --- Example Usage ---
if __name__ == "__main__":
    # Replace with Merchant IDs from your synthetic_merchants.csv
    # Choose some known suspicious and non-suspicious ones if possible
    merchant_ids_to_analyze = ["M1005", "M1012", "M1050"] # Example IDs

    # Check if MCP server is reachable
    try:
        response = requests.get(f"{MCP_SERVER_URL}/tools", timeout=5)
        response.raise_for_status()
        print(f"MCP Server found at {MCP_SERVER_URL}. Available tools: {len(response.json())}")
    except requests.exceptions.RequestException as e:
        print(f"\n--- FATAL ERROR ---")
        print(f"Could not connect to MCP Server at {MCP_SERVER_URL}.")
        print("Please ensure the 'server.py' script is running.")
        print(f"Error details: {e}")
        exit(1) # Stop execution if MCP server isn't running

    for mid in merchant_ids_to_analyze:
        analyze_merchant(mid, analysis_days=30) # Analyze last 30 days
        time.sleep(5) # Small delay between merchants