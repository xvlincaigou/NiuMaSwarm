# NiuMaSwarm

A lightweight, extensible multi-agent rollout framework for orchestrating AI agents.

Note: The implementation of this project was independently written by **Kimi (kimi-k2.5)**.

## Disclaimer

This repository is a **personal experimental project** and should be treated strictly as a demo / reference implementation.

- It is **not production-ready**.
- Many aspects required for real-world deployment (e.g., concurrency limits, robustness, cost control, tools) are intentionally not handled.
- The primary goal is to demonstrate **how to call and wire up agent swarm-style rollouts**, rather than how to build a full system.

This project is **not affiliated with, endorsed by, or representative of any company or official offering**.
All design choices reflect exploratory work and may change without notice.


## Installation

```bash
pip install -e .
```

## Quick Start

See `run_examples/` and `examples/` for complete working examples:

```bash
# Set environment variables
export KIMI_API_KEY="your-kimi-api-key"
export OPENAI_API_KEY="your-openai-api-key"
export SERPER_API_KEY="your-serper-api-key"  # optional
export FEISHU_APP_ID="your-feishu-app-id"    # optional, for Feishu docs
export FEISHU_APP_SECRET="your-feishu-app-secret"

# Run basic examples
python run_examples/run_kimi_kimi.py
python run_examples/run_kimi_qwen.py

# Run research report generation
python examples/research_report.py

# Run autonomous research swarm
python examples/auto_research_swarm.py
```

### Simple Agent

```python
import asyncio
from open_swarm import Agent, AgentConfig, MainRollout, RolloutConfig, SearchTool

async def main():
    config = AgentConfig(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model_id="kimi-k2.5",
        api_key="your-api-key",
        api_base_url="https://api.moonshot.cn/v1",
    )

    agent = Agent(config, tools=[SearchTool()])

    rollout = MainRollout(RolloutConfig(max_steps=10))
    result = await rollout.run(agent, "Hello! What can you do?")

    print(result.final_response)

asyncio.run(main())
```

### Multi-Agent System

```python
import asyncio
from open_swarm import (
    Agent, AgentConfig, MainRollout, RolloutConfig,
    SearchTool, CreateSubagentTool, TaskTool
)

async def main():
    agent_registry = {}

    # Create tools
    search = SearchTool()
    create_subagent = CreateSubagentTool(agent_registry)
    task = TaskTool(agent_registry=agent_registry, max_steps=15)

    # Create orchestrator with different models for main/sub
    config = AgentConfig(
        name="orchestrator",
        system_prompt="You are an orchestrator that delegates to sub-agents.",
        model_id="kimi-k2.5",
        api_key="your-kimi-key",
        api_base_url="https://api.moonshot.cn/v1",
        # Sub-agent can use a different model
        subagent_model_id="qwen2.5-72b-instruct",
        subagent_api_key="your-qwen-key",
        subagent_api_base_url="https://openai.app.msh.team/v1",
        temperature=1.0,  # kimi-k2.5 requires temperature=1.0
    )

    agent = Agent(config, tools=[search, create_subagent, task])
    task.set_parent_agent(agent)
    task.set_parent_tools([search])

    # Run with storage
    rollout = MainRollout(RolloutConfig(
        max_steps=30,
        storage_path="result/output.jsonl",
    ))
    result = await rollout.run(
        agent,
        "Research the latest AI developments and summarize them."
    )

    print(f"Created agents: {list(agent_registry.keys())}")
    print(f"Sub-agents used: {len(result.subs)}")
    print(result.final_response)

asyncio.run(main())
```

## Configuration

### Environment Variables

```bash
# Kimi API (api.moonshot.cn)
export KIMI_API_KEY=your-kimi-key

# OpenAI-compatible API (for qwen, etc.)
export OPENAI_API_KEY=your-api-key
export OPENAI_BASE_URL=https://api.openai.com/v1  # Optional

# Search Tool (Serper - Google Search API)
export SERPER_API_KEY=your-serper-key  # Get from https://serper.dev

# Feishu/Lark Document Tool (Open Platform)
export FEISHU_APP_ID=your-feishu-app-id
export FEISHU_APP_SECRET=your-feishu-app-secret

# Test Feishu integration
python examples/test_feishu.py
```

The `test_feishu.py` script provides an interactive way to test Feishu document creation with various formatting options including headings, lists, tables, and code blocks.

### AgentConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | required | Agent name |
| `system_prompt` | str | "You are a helpful assistant." | System prompt |
| `model_id` | str | "kimi-k2.5" | Model identifier |
| `api_key` | str | None | API key (uses env var if not set) |
| `api_base_url` | str | None | API base URL (uses env var if not set) |
| `subagent_model_id` | str | None | Model for sub-agents (defaults to model_id) |
| `subagent_api_key` | str | None | API key for sub-agents |
| `subagent_api_base_url` | str | None | API base URL for sub-agents |
| `max_tokens` | int | 4096 | Max tokens per request |
| `temperature` | float | 0.7 | Sampling temperature |

### RolloutConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_steps` | int | 50 | Maximum execution steps |
| `terminal_mode` | bool | True | Print output to terminal |
| `storage_path` | str | None | Path to save results as JSONL |
| `print_tool_calls` | bool | True | Print tool calls to terminal |
| `print_tool_results` | bool | True | Print tool results to terminal |

## Feishu Document Tool

Use `FeishuDocTool` to create cloud documents on Feishu (Lark) platform:

```python
from open_swarm import FeishuDocTool

feishu_tool = FeishuDocTool()

# Create a document
result = await feishu_tool.execute(
    title="Research Report Title",
    content="""# Executive Summary

## Key Findings
- Finding 1
- Finding 2

## Detailed Analysis
Content here..."""
)

print(result.content)  # Outputs document URL
```

Supported formatting:
- `# Heading 1` / `## Heading 2` / `### Heading 3`
- `- List item` / `* List item`
- `1. Numbered list`
- `**Bold**` / `*Italic*`
- \`\`\`Code blocks\`\`\`
- `| Tables | with | columns |` (formatted as aligned text)

## Automated Research Reports

### Basic Research Report

`examples/research_report.py` demonstrates how to use Agent Swarm to automatically generate research reports and save them to Feishu:

```bash
# Set all required environment variables
export KIMI_API_KEY="your-kimi-api-key"
export SERPER_API_KEY="your-serper-api-key"
export FEISHU_APP_ID="your-feishu-app-id"
export FEISHU_APP_SECRET="your-feishu-app-secret"

# Run the research report generator
python examples/research_report.py
```

Workflow:
1. **Create specialized sub-agents**: Researcher, Analyst, Writer
2. **Delegate tasks in parallel**: Multiple sub-agents research different aspects simultaneously
3. **Synthesize results**: Main agent integrates all findings
4. **Generate Feishu document**: Automatically create a formatted cloud document

### Autonomous Research Swarm

`examples/auto_research_swarm.py` demonstrates a more advanced workflow where the main agent autonomously decides what specialized sub-agents to create:

```bash
# Set all required environment variables
export KIMI_API_KEY="your-kimi-api-key"
export SERPER_API_KEY="your-serper-api-key"
export FEISHU_APP_ID="your-feishu-app-id"
export FEISHU_APP_SECRET="your-feishu-app-secret"

# Run the autonomous research swarm
python examples/auto_research_swarm.py
```

Features:
- **Autonomous agent creation**: Main agent analyzes the research topic and decides what specialized sub-agents are needed
- **Parallel execution**: All sub-agents execute research tasks concurrently
- **Intelligent synthesis**: Main agent compiles all findings into a comprehensive report
- **Automatic document creation**: Saves the final report to Feishu with formatted tables and sections

Example output:
- Creates 4 specialized analysts (Tech, Market, Business, User Behavior)
- Executes research in parallel
- Generates a comprehensive report with multiple tables
- Saves to Feishu with document URL

## Parallel Sub-agent Execution

The `TaskTool` now supports parallel execution of multiple sub-agents:

```python
from open_swarm import TaskTool

# Method 1: Single task (sequential)
result = await task_tool.execute(
    agent="researcher",
    prompt="Research topic A"
)

# Method 2: Multiple tasks in parallel
results = await task_tool.execute(
    tasks=[
        {"agent": "tech_analyst", "prompt": "Analyze technology trends"},
        {"agent": "market_analyst", "prompt": "Analyze market competition"},
        {"agent": "business_analyst", "prompt": "Analyze business models"},
    ]
)
# Returns array of results in the same order as tasks
```

This is useful for:
- Running multiple independent research tasks simultaneously
- Comparing different analysis perspectives
- Speeding up complex multi-step workflows

## Creating Custom Tools

```python
from open_swarm import BaseTool, ToolResult

class MyTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Description of what this tool does"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "First parameter"
                }
            },
            "required": ["param1"]
        }

    async def execute(self, param1: str) -> ToolResult:
        result = f"Processed: {param1}"
        return ToolResult(content=result, success=True)
```

## Architecture

```
open_swarm/
├── agent/          # Agent class and configuration
├── rollout/        # Rollout implementations (Main, Sub)
├── tool/           # Base tool, SearchTool, FeishuDocTool
├── swarm_tool/     # CreateSubagentTool, TaskTool (supports parallel execution)
├── utils/          # LLM client
├── run_examples/   # Basic example scripts
└── examples/       # Advanced examples (research, auto-swarm)
```

### Key Components

| Component | Description |
|-----------|-------------|
| `Agent` | Core agent with tool-use capabilities |
| `MainRollout` | Orchestrates the main agent execution |
| `SubRollout` | Handles sub-agent task execution |
| `SearchTool` | Web search via Serper API |
| `FeishuDocTool` | Create Feishu/Lark cloud documents |
| `CreateSubagentTool` | Dynamically create specialized sub-agents |
| `TaskTool` | Execute sub-agent tasks (supports parallel execution via `tasks` array) |

## Storage Format

Results are saved as JSONL with the following structure:

```json
{
  "main": [...],  // Main agent conversation messages
  "subs": [...]   // Sub-agent conversation records
}
```

## License

MIT License
