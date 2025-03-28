# Multi-Agent Fraud detector app, OpenAI-compatible with MCP Architecture

This repository contains a framework for running multi-agent OpenAI Assistant workflows using a Model-Client-Proxy (MCP) architecture.

## Overview

This project implements a system where multiple AI assistants analyze merchant data using OpenAI's Assistant API. The framework uses a Model-Client-Proxy architecture to separate the AI models from the data processing functions.

## Components

### MCP Server (`server.py`)
- **Technology**: Flask web server
- **Function**: 
  - Loads synthetic CSV data into Pandas DataFrames at startup
  - Contains Python functions that perform data analysis/actions (your "tools")
  - Provides API endpoints:
    - `/tools` (GET): Lists available functions with descriptions
    - `/execute` (POST): Receives `tool_name` and arguments, executes the corresponding function, and returns results

### Orchestrator (`orchestrator.py`)
- **Function**:
  - Manages OpenAI API key
  - Defines `tools_definition` matching the functions in `server.py`
  - Creates/retrieves Assistant IDs for each agent role
  - Contains the MCP Client implementation:
    - `execute_mcp_tool`: Sends tool requests to the server's `/execute` endpoint
    - `wait_for_run_completion`: Polls Assistant run status and handles tool calls
    - `analyze_merchant`: Orchestrates the agent workflow for a single merchant

## Setup & Installation

1. **Create and activate environment**:
   ```bash
   # Using conda
   conda create -n pxp1 python=3.11
   conda activate pxp1
   
   # Or using venv
   python -m venv pxp1
   source pxp1/bin/activate  # On Windows: pxp1\Scripts\activate
   
   # Install dependencies
   pip install -r requirements-pxp.txt
   ```

2. **Configuration**:
   - Add your OpenAI API key to the `.env` file
   - You can use the provided CSV files or generate new ones using the data generation script

## Running the Application

1. **Start the MCP Server**:
   ```bash
   python server.py
   ```

2. **Run the Orchestrator** (in a new console):
   ```bash
   # Dont forget to activate your environment first
   conda activate pxp1  # or source pxp1/bin/activate
   
   python orchestrator.py
   ```

## Customization

- **Model**: Default is `gpt-4-turbo-preview`, can be changed on line 116 in `orchestrator.py`
- **Merchant IDs**: Can be modified on line 346 to analyze different merchants (range: M1001-M1999)
- **Analysis Functions**: The analyze function currently uses basic pattern analysis, but can be augmented with machine learning models, graphs+ML, or any analytical tools.

## Data

The system works with synthetic CSV data containing merchant information. You can:
- Use the provided CSV files
- Generate new data using the data generation script

## System Flow

1. The server loads data and exposes tool functions via API endpoints
2. The orchestrator creates a sequence of agent runs for each merchant
3. Each agent can call the MCP server tools to access and analyze data
4. Results from one agent can be passed to the next in the sequence (wrapping context at each step)

## Notes

- After first run, copy the printed Assistant IDs back into the script (Row 109-114)
- Run again with different merchant IDs to analyze different entities (Row 346)

