"""Research Report Example - Automated research with Feishu document creation

This example demonstrates how to use the agent swarm to:
1. Conduct comprehensive research on a topic using multiple sub-agents
2. Compile findings into a structured report
3. Automatically create a Feishu cloud document with the results

Usage:
    export KIMI_API_KEY="your-kimi-api-key"
    export SERPER_API_KEY="your-serper-api-key"
    export FEISHU_APP_ID="your-feishu-app-id"
    export FEISHU_APP_SECRET="your-feishu-app-secret"
    python examples/research_report.py
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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# System prompts for specialized research agents
RESEARCH_AGENT_PROMPT = """You are a specialized research agent focused on gathering accurate, up-to-date information.

Your responsibilities:
1. Use the search tool to find current, authoritative information on your assigned topic
2. Focus on facts, data, and specific examples
3. Note sources and dates when available
4. Be thorough but concise - aim for comprehensive coverage in limited steps

Return format:
- Key findings as bullet points
- Important statistics or data points
- Recent developments (prioritize last 1-2 years)
- Source credibility notes

IMPORTANT: Complete your research and return findings promptly. You have limited steps."""

ANALYSIS_AGENT_PROMPT = """You are an analysis agent that synthesizes research findings into insights.

Your responsibilities:
1. Review research findings from multiple sources
2. Identify patterns, trends, and key themes
3. Highlight implications and significance
4. Organize information logically

Return format:
- Executive summary (2-3 sentences)
- Key themes identified
- Critical insights and implications
- Recommendations or conclusions

Be analytical and focus on extracting meaningful insights from the data."""

WRITER_AGENT_PROMPT = """You are a professional report writer.

Your responsibilities:
1. Transform research findings into polished, professional prose
2. Create well-structured sections with clear headings
3. Use appropriate formatting and style for business/research reports
4. Ensure logical flow and coherence

Writing guidelines:
- Use clear, professional language
- Include descriptive headings and subheadings
- Use bullet points for lists when appropriate
- Maintain objective tone
- Cite specific data points with context

Output should be ready for publication in a formal report."""


async def main():
    """Run automated research report generation"""

    # Check required environment variables
    required_env = ["KIMI_API_KEY", "SERPER_API_KEY", "FEISHU_APP_ID", "FEISHU_APP_SECRET"]
    missing = [env for env in required_env if not os.environ.get(env)]
    if missing:
        print("\n" + "=" * 60)
        print("Missing required environment variables:")
        for env in missing:
            print(f"  - {env}")
        print("\nPlease set these variables and try again.")
        print("=" * 60)
        return

    # Create shared agent registry
    agent_registry = {}

    # Create tools
    search_tool = SearchTool()
    feishu_doc_tool = FeishuDocTool()
    create_subagent = CreateSubagentTool(agent_registry)
    task_tool = TaskTool(
        agent_registry=agent_registry,
        max_steps=15,
    )

    # Create main agent configuration - orchestrator
    config = AgentConfig(
        name="research_orchestrator",
        system_prompt="""You are a research orchestrator agent that coordinates comprehensive research projects.

Your workflow:
1. Understand the research topic from the user
2. Create specialized sub-agents for different aspects of the research
3. Delegate parallel research tasks to sub-agents
4. Synthesize all findings into a cohesive report
5. Use the Feishu document tool to create a professional cloud document

Available actions:
- search: Direct search for quick facts
- create_subagent: Create specialized research agents
- task: Assign research tasks to agents
- create_feishu_doc: Create final report document

Research delegation strategy:
- Create multiple specialized research agents (market_trends, competitor_analysis, technology_landscape, etc.)
- Assign each a specific aspect to research
- Run them in parallel for efficiency
- Collect and synthesize all results

Document creation:
- Format the report with proper markdown structure
- Include title, executive summary, detailed findings, and conclusions
- Create a professional Feishu document with the compiled report

Be strategic in task delegation and ensure comprehensive coverage of the topic.""",
        model_id="kimi-k2.5",
        temperature=1.0,  # kimi-k2.5 requires temperature=1.0
    )

    # Create main agent
    agent = Agent(
        config=config,
        tools=[search_tool, feishu_doc_tool, create_subagent, task_tool]
    )

    # Set parent references for task tool
    task_tool.set_parent_agent(agent)
    task_tool.set_parent_tools([search_tool])

    # Create rollout
    rollout_config = RolloutConfig(
        max_steps=50,
        terminal_mode=True,
        storage_path="result/research_report_result.jsonl",
    )
    rollout = MainRollout(rollout_config)

    # Run research project
    print("\n" + "=" * 60)
    print("Research Report Generator with Feishu Integration")
    print("=" * 60)
    print("\nExample research topics:")
    print("1. Latest developments in AI agent frameworks (2024-2025)")
    print("2. Electric vehicle market analysis and key players")
    print("3. Quantum computing breakthroughs and commercial applications")
    print("4. Cybersecurity trends and emerging threats")
    print("\nEnter your research topic (or press Enter for default):")

    user_input = input("> ").strip()

    if not user_input:
        user_input = (
            "Research the latest developments in AI agent frameworks and multi-agent systems "
            "in 2024-2025. Focus on: 1) New frameworks and tools, 2) Key companies and products, "
            "3) Use cases and applications, 4) Future trends. Create a comprehensive report "
            "and save it to a Feishu document."
        )
        print(f"\nUsing default topic: {user_input}")

    # Create initial message with sub-agent creation instructions
    initial_message = f"""{user_input}

To complete this research project, follow these steps:

1. First, create specialized research sub-agents:
   - Create a "market_researcher" agent with system prompt: "{RESEARCH_AGENT_PROMPT}"
   - Create an "analyst" agent with system prompt: "{ANALYSIS_AGENT_PROMPT}"
   - Create a "writer" agent with system prompt: "{WRITER_AGENT_PROMPT}"

2. Delegate parallel research tasks:
   - Assign market/trend research tasks
   - Assign competitor/company research tasks
   - Assign technology/technical research tasks
   - Run all tasks in parallel for efficiency

3. Collect and synthesize results:
   - Review all sub-agent findings
   - Identify key patterns and insights
   - Organize into logical sections

4. Create the final report:
   - Use the writer agent to polish the content
   - Format with proper markdown (headings, lists, etc.)
   - Create a Feishu document with title matching the research topic
   - Include all sections: Executive Summary, Findings, Analysis, Conclusions

Start by creating the sub-agents and delegating research tasks in parallel."""

    result = await rollout.run(
        agent=agent,
        initial_message=initial_message
    )

    # Print results
    print("\n" + "=" * 60)
    print("Research Project Completed")
    print("=" * 60)
    print(f"Status: {result.status.value}")
    print(f"Steps: {result.steps}")
    print(f"Agents created: {list(agent_registry.keys())}")

    if result.final_response:
        print(f"\nFinal Response:\n{result.final_response}")

    # Check for Feishu document creation
    if result.status.value == "completed":
        print("\n" + "=" * 60)
        print("Check your Feishu account for the created research document!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
