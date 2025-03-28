from flask import Flask, request, jsonify
import pandas as pd
import json
import os
from datetime import datetime

app = Flask(__name__)

# --- Load Data ---
# Best practice: Load once at startup
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    merchants_df = pd.read_csv(os.path.join(DATA_DIR, 'synthetic_merchants.csv'))
    transactions_df = pd.read_csv(os.path.join(DATA_DIR, 'synthetic_transactions.csv'))
    # Convert timestamp column to datetime objects if it's not already
    transactions_df['timestamp'] = pd.to_datetime(transactions_df['timestamp'])
    print("Data loaded successfully.")
except FileNotFoundError:
    print("Error: synthetic_merchants.csv or synthetic_transactions.csv not found.")
    # In a real app, handle this more gracefully
    merchants_df = pd.DataFrame()
    transactions_df = pd.DataFrame()

# --- Tool Implementations ---
# These functions are the actual tools the MCP server provides.
# They should match the functions you define for your OpenAI Assistants.

def get_merchant_profile(merchant_id: str) -> dict:
    """Gets profile information for a specific merchant."""
    if merchants_df.empty:
        return {"error": "Merchant data not loaded"}
    profile = merchants_df[merchants_df['merchant_id'] == merchant_id]
    if profile.empty:
        return {"error": f"Merchant ID {merchant_id} not found."}
    # Convert to dictionary, handle potential multiple matches if ID isn't unique
    return profile.iloc[0].to_dict()

def get_merchant_aggregated_stats(merchant_id: str, start_date_str: str, end_date_str: str) -> dict:
    """Calculates aggregated transaction statistics for a merchant within a date range."""
    if transactions_df.empty:
        return {"error": "Transaction data not loaded"}
    try:
        start_date = datetime.fromisoformat(start_date_str)
        end_date = datetime.fromisoformat(end_date_str)
    except ValueError:
        return {"error": "Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)."}

    merchant_txns = transactions_df[
        (transactions_df['merchant_id'] == merchant_id) &
        (transactions_df['timestamp'] >= start_date) &
        (transactions_df['timestamp'] <= end_date)
    ]

    if merchant_txns.empty:
        return {"message": f"No transactions found for {merchant_id} in the period."}

    stats = {
        "merchant_id": merchant_id,
        "period_start": start_date_str,
        "period_end": end_date_str,
        "total_transactions": len(merchant_txns),
        "total_value": merchant_txns['amount'].sum(),
        "average_transaction_value": merchant_txns['amount'].mean(),
        "unique_cards": merchant_txns['card_id_token'].nunique(),
        "prepaid_card_percentage": (merchant_txns['card_type'] == 'Prepaid').mean() * 100,
        "rounded_transaction_percentage": merchant_txns['is_rounded'].mean() * 100,
        "transactions_by_card_country": merchant_txns['card_country'].value_counts().to_dict(),
    }
    return stats

def get_anomalous_transactions(merchant_id: str, start_date_str: str, end_date_str: str, min_amount: float = 1000.0) -> list:
    """Retrieves examples of potentially anomalous transactions (e.g., high value)."""
    if transactions_df.empty:
        return [{"error": "Transaction data not loaded"}]
    try:
        start_date = datetime.fromisoformat(start_date_str)
        end_date = datetime.fromisoformat(end_date_str)
    except ValueError:
        return [{"error": "Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)."}]

    anomalous_txns = transactions_df[
        (transactions_df['merchant_id'] == merchant_id) &
        (transactions_df['timestamp'] >= start_date) &
        (transactions_df['timestamp'] <= end_date) &
        (transactions_df['amount'] >= min_amount) # Example anomaly: high value
    ]
    # Return a limited number of examples
    return anomalous_txns.head(10).to_dict('records')


def update_merchant_risk_status(merchant_id: str, new_status: str, reason_code: str) -> dict:
    """Placeholder: Updates the merchant's risk status (simulated)."""
    print(f"MCP TOOL: Simulating update risk status for {merchant_id} to {new_status} due to {reason_code}")
    # In a real app, this would update a database.
    # We can try updating the in-memory dataframe for the PoC
    if not merchants_df.empty:
        if merchant_id in merchants_df['merchant_id'].values:
             merchants_df.loc[merchants_df['merchant_id'] == merchant_id, 'current_risk_status'] = new_status
             merchants_df.loc[merchants_df['merchant_id'] == merchant_id, 'last_risk_reason'] = reason_code
             return {"status": "success", "merchant_id": merchant_id, "new_status": new_status}
        else:
             return {"status": "error", "message": f"Merchant {merchant_id} not found for status update."}
    return {"status": "error", "message": "Merchant data not loaded."}


def create_aml_manual_review_case(merchant_id: str, risk_category: str, summary: str, key_indicators: list) -> dict:
    """Placeholder: Creates a manual review case (simulated)."""
    print(f"MCP TOOL: Simulating creation of manual review case for {merchant_id}")
    print(f"  Risk: {risk_category}")
    print(f"  Summary: {summary}")
    print(f"  Indicators: {key_indicators}")
    # In a real app, this would interact with a case management system API
    case_id = f"CASE_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}_{merchant_id}"
    return {"status": "success", "case_id": case_id, "merchant_id": merchant_id}

# --- Mapping Tool Names to Functions ---
AVAILABLE_TOOLS = {
    "get_merchant_profile": get_merchant_profile,
    "get_merchant_aggregated_stats": get_merchant_aggregated_stats,
    "get_anomalous_transactions": get_anomalous_transactions,
    "update_merchant_risk_status": update_merchant_risk_status,
    "create_aml_manual_review_case": create_aml_manual_review_case,
}

# --- MCP API Endpoints ---
@app.route('/tools', methods=['GET'])
def get_tools():
    """MCP endpoint to list available tools."""
    tool_list = []
    for name, func in AVAILABLE_TOOLS.items():
        # Basic introspection for description
        # For production, use a more robust way to define tool schemas (like Pydantic)
        tool_list.append({
            "name": name,
            "description": func.__doc__ or "No description available.",
            # Parameters would ideally be defined here too
        })
    return jsonify(tool_list)

@app.route('/execute', methods=['POST'])
def execute_tool():
    """MCP endpoint to execute a specific tool."""
    data = request.get_json()
    tool_name = data.get('tool_name')
    arguments = data.get('arguments', {}) # Arguments should be a dictionary

    if not tool_name:
        return jsonify({"error": "Missing 'tool_name'"}), 400

    if tool_name not in AVAILABLE_TOOLS:
        return jsonify({"error": f"Tool '{tool_name}' not found."}), 404

    func = AVAILABLE_TOOLS[tool_name]

    try:
        # Ensure arguments are passed correctly
        # This assumes arguments in the request match the function signature
        result = func(**arguments)
        return jsonify({"result": result})
    except TypeError as e:
         # Handle cases where arguments don't match function signature
         print(f"TypeError executing {tool_name}: {e}")
         print(f"Received arguments: {arguments}")
         return jsonify({"error": f"Argument mismatch for tool '{tool_name}': {e}"}), 400
    except Exception as e:
        print(f"Error executing tool {tool_name}: {e}")
        # Log the full error for debugging
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal server error executing tool '{tool_name}': {str(e)}"}), 500

# --- Run the Server ---
if __name__ == '__main__':
    # Makes the server accessible on your local network
    # Use '127.0.0.1' to restrict to only your machine
    app.run(host='0.0.0.0', port=5003, debug=True) # Use a port like 5003