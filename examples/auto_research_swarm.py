"""Auto Research Swarm - Autonomous sub-agent creation with parallel execution

This example demonstrates:
1. Main agent AUTONOMOUSLY decides what sub-agents to create based on the research topic
2. Parallel execution of all sub-agents for maximum efficiency
3. Automatic synthesis and Feishu document creation

Key difference from research_report.py:
- No predefined agent types in the prompt
- Main agent decides what specializations are needed
- All sub-agents run in parallel using assign_tasks_parallel
"""

import asyncio
import logging
import os

from open_swarm import (
    Agent,
    AgentConfig,
    MainRollout,
    RolloutConfig,
    SearchTool,
    CreateSubagentTool,
    TaskTool,
    FeishuDocTool,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Run autonomous research swarm"""

    # Validate environment
    required_vars = ["KIMI_API_KEY"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print("\n" + "=" * 60)
        print("Missing required environment variables:")
        for v in missing:
            print(f"  - {v}")
        print("=" * 60)
        return

    # Optional: Check for wiki space
    wiki_space = os.environ.get("FEISHU_WIKI_SPACE_ID")
    if wiki_space:
        print(f"✓ Using wiki space: {wiki_space}")
    else:
        print("Note: FEISHU_WIKI_SPACE_ID not set. Will try to use default space.")

    # Initialize registry and tools
    agent_registry = {}
    search_tool = SearchTool()
    feishu_tool = FeishuDocTool()
    create_subagent = CreateSubagentTool(agent_registry)
    task_tool = TaskTool(agent_registry, max_steps=15)

    # Create orchestrator agent - NO predefined agent types!
    # The agent decides what sub-agents to create based on the task
    config = AgentConfig(
        name="research_orchestrator",
        system_prompt="""You are an intelligent research orchestrator that autonomously manages multi-agent research projects.

YOUR CORE CAPABILITIES:
1. Analyze the research topic to understand what aspects need investigation
2. AUTONOMOUSLY decide what specialized sub-agents to create
3. Use assign_task with tasks array to execute ALL sub-agents in PARALLEL
4. Synthesize results and create comprehensive reports

WORKFLOW:
1. Analyze the user's research request
2. Determine what research areas/aspects need investigation
3. Create specialized sub-agents using create_subagent (decide names and prompts yourself!)
4. Launch ALL sub-agents in PARALLEL using assign_task with tasks array
5. Wait for all results and synthesize findings
6. Create a formatted Feishu document with the final report

SUB-AGENT CREATION GUIDELINES:
- Create 3-5 specialized agents based on the research needs
- Name them descriptively (e.g., "market_analyst", "tech_researcher", "competitor_tracker")
- Give each a specific system prompt focused on their expertise

PARALLEL EXECUTION (CRITICAL):
- Use assign_task tool ONCE with a "tasks" array containing ALL tasks
- This will execute all sub-agents in PARALLEL for maximum efficiency
- Do NOT call assign_task multiple times sequentially
- Example format:
  {
    "tasks": [
      {"agent": "agent1", "prompt": "task1..."},
      {"agent": "agent2", "prompt": "task2..."},
      {"agent": "agent3", "prompt": "task3..."}
    ]
  }

FEISHU DOCUMENT:
- Always create a document at the end using create_feishu_doc
- Use proper markdown formatting
- Include: Title, Executive Summary, Key Findings, Detailed Analysis, Conclusions

Be strategic and autonomous in your decisions!""",
        model_id="kimi-k2.5",
        temperature=1.0,
    )

    agent = Agent(
        config=config,
        tools=[search_tool, feishu_tool, create_subagent, task_tool]
    )

    task_tool.set_parent_agent(agent)
    task_tool.set_parent_tools([search_tool])

    # Create rollout
    rollout_config = RolloutConfig(
        max_steps=60,
        terminal_mode=True,
        storage_path="result/auto_research_swarm.jsonl",
    )
    rollout = MainRollout(rollout_config)

    # Run research project
    print("\n" + "=" * 60)
    print("Auto Research Swarm - Autonomous Sub-Agent Creation")
    print("=" * 60)
    print("\nEnter research topic (or press Enter for default):")
    print("Example: Latest developments in AI video generation 2024-2025")

    user_input = input("> ").strip()

    if not user_input:
        user_input = "AI video generation tools and technologies: latest developments, key players, use cases, and future trends (2024-2025)"
        print(f"\nUsing default: {user_input}")

    message = f"""Research Topic: {user_input}

Execute this research project autonomously:

STEP 1 - Analyze and Plan:
Analyze this research topic and determine what aspects need investigation and what specialized agents to create.

STEP 2 - Create Specialized Sub-Agents:
Use create_subagent to create 3-5 agents based on your analysis.
Give each a descriptive name and focused system prompt.

STEP 3 - Execute in PARALLEL (CRITICAL):
Use assign_task tool with a "tasks" array containing ALL tasks at once.
This will run all sub-agents in PARALLEL for maximum efficiency.

Example:
{{
    "tasks": [
        {{"agent": "market_analyst", "prompt": "Research market trends..."}},
        {{"agent": "tech_researcher", "prompt": "Analyze technologies..."}},
        {{"agent": "competitor_tracker", "prompt": "Identify key players..."}}
    ]
}}

STEP 4 - Synthesize and create Feishu docx document using create_feishu_doc.

Start now!"""

    result = await rollout.run(agent=agent, initial_message=message)

    # Output results
    print("\n" + "=" * 60)
    print("Research Project Completed")
    print("=" * 60)
    print(f"Status: {result.status.value}")
    print(f"Steps: {result.steps}")
    print(f"Sub-agents created: {list(agent_registry.keys())}")
    print(f"Total sub-agent executions: {len(result.subs)}")

    if result.final_response:
        print(f"\nFinal Response:\n{result.final_response[:1000]}...")

    if result.status.value == "completed":
        print("\n✅ Check your Feishu account for the research document!")


if __name__ == "__main__":
    asyncio.run(main())
