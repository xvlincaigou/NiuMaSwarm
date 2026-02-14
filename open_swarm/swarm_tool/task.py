"""Task Tool - Launch sub-agents to execute tasks"""

import asyncio
import logging
from typing import Dict, List, Any, Optional

from ..tool.base import BaseTool, ToolResult
from ..agent.agent import Agent, AgentConfig
from ..rollout.sub_rollout import SubRollout, SubRolloutConfig

logger = logging.getLogger(__name__)


class TaskTool(BaseTool):
    """Tool for launching sub-agents to execute tasks

    This tool supports BOTH single task and parallel multi-task execution:
    - Single task: Pass agent and prompt as top-level parameters
    - Parallel tasks: Pass tasks array with multiple task objects

    The tool automatically detects which mode to use and executes efficiently.
    """

    def __init__(
        self,
        agent_registry: Dict[str, Dict[str, Any]],
        parent_agent: Optional[Agent] = None,
        parent_tools: Optional[List[BaseTool]] = None,
        max_steps: int = 20,
    ):
        """Initialize Task tool

        Args:
            agent_registry: Registry of available agent configurations
            parent_agent: Reference to parent agent (for context forking)
            parent_tools: Tools to pass to sub-agents
            max_steps: Maximum steps for sub-agent execution
        """
        self.agent_registry = agent_registry
        self.parent_agent = parent_agent
        self.parent_tools = parent_tools or []
        self.max_steps = max_steps
        self.subagent_counter = 0
        self.sub_results: List[Dict[str, Any]] = []

    def set_parent_agent(self, agent: Agent):
        """Set the parent agent reference"""
        self.parent_agent = agent

    def set_parent_tools(self, tools: List[BaseTool]):
        """Set tools available to sub-agents"""
        self.parent_tools = tools

    @property
    def name(self) -> str:
        return "assign_task"

    @property
    def description(self) -> str:
        return (
            "Launch sub-agents to execute tasks. Supports BOTH single task and parallel multi-task execution.\n\n"
            "MODE 1 - Single Task (simple):\n"
            "  {\"agent\": \"agent_name\", \"prompt\": \"task description\"}\n\n"
            "MODE 2 - Parallel Tasks (RECOMMENDED for multiple tasks):\n"
            "  {\"tasks\": [\n"
            "    {\"agent\": \"agent1\", \"prompt\": \"task1\"},\n"
            "    {\"agent\": \"agent2\", \"prompt\": \"task2\"},\n"
            "    {\"agent\": \"agent3\", \"prompt\": \"task3\"}\n"
            "  ]}\n\n"
            "IMPORTANT: When you have multiple independent tasks, ALWAYS use MODE 2 (tasks array) "
            "so all sub-agents execute in PARALLEL for maximum efficiency. "
            "Do NOT call this tool multiple times sequentially."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "For single task mode: Name of the agent to use (must be created first with create_subagent)"
                },
                "prompt": {
                    "type": "string",
                    "description": "For single task mode: Detailed task description for the sub-agent"
                },
                "tasks": {
                    "type": "array",
                    "description": "For parallel mode: Array of task objects. Each must have 'agent' and 'prompt' keys.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "agent": {"type": "string"},
                            "prompt": {"type": "string"}
                        },
                        "required": ["agent", "prompt"]
                    }
                }
            },
            "oneOf": [
                {"required": ["agent", "prompt"]},
                {"required": ["tasks"]}
            ]
        }

    async def _execute_single_task(
        self,
        task_index: int,
        agent_name: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """Execute a single sub-agent task"""
        try:
            # Get agent configuration
            if agent_name not in self.agent_registry:
                return {
                    "index": task_index,
                    "agent": agent_name,
                    "success": False,
                    "error": f"Agent '{agent_name}' not found. Available: {list(self.agent_registry.keys())}",
                    "content": ""
                }

            agent_config = self.agent_registry[agent_name]

            # Increment counter
            self.subagent_counter += 1
            subagent_id = f"subagent_{self.subagent_counter}"

            logger.info(f"[Task] Launching {subagent_id} with config: {agent_name}")

            # Build sub-agent system prompt
            system_prompt = agent_config["system_prompt"]
            system_prompt += f"\n\nIMPORTANT:"
            system_prompt += f"\n- You have a MAXIMUM of {self.max_steps} steps to complete your task."
            system_prompt += f"\n- Return results AS SOON AS you have sufficient information."
            system_prompt += f"\n- If approaching step limit, summarize findings and return."

            # Create sub-agent configuration
            if self.parent_agent:
                subagent_model = self.parent_agent.config.subagent_model_id or self.parent_agent.config.model_id
                subagent_api_key = self.parent_agent.config.subagent_api_key or self.parent_agent.config.api_key
                subagent_base_url = self.parent_agent.config.subagent_api_base_url or self.parent_agent.config.api_base_url
            else:
                subagent_model = "kimi-k2.5"
                subagent_api_key = None
                subagent_base_url = None

            subagent_config = AgentConfig(
                name=subagent_id,
                system_prompt=system_prompt,
                model_id=subagent_model,
                api_key=subagent_api_key,
                api_base_url=subagent_base_url,
                max_tokens=self.parent_agent.config.max_tokens if self.parent_agent else 4096,
                temperature=self.parent_agent.config.temperature if self.parent_agent else 0.7,
            )

            # Create sub-agent with tools (excluding swarm tools to prevent recursion)
            subagent_tools = [
                tool for tool in self.parent_tools
                if tool.name not in ("create_subagent", "assign_task")
            ]

            subagent = Agent(
                config=subagent_config,
                tools=subagent_tools,
                llm_client=self.parent_agent.llm_client if self.parent_agent else None,
            )

            # Run sub-rollout
            rollout_config = SubRolloutConfig(
                max_steps=self.max_steps,
                step_hint=True,
                terminal_mode=False,
            )

            sub_rollout = SubRollout(rollout_config)
            result = await sub_rollout.run(
                agent=subagent,
                initial_message=prompt,
            )

            # Format result
            if result.status.value == "completed":
                content = result.final_response or "Task completed but no response generated."
            elif result.status.value == "max_steps_reached":
                content = f"Sub-agent reached step limit.\n\nLast response:\n{result.final_response or 'No response'}"
            elif result.status.value == "error":
                content = f"Sub-agent encountered an error: {result.error}"
            else:
                content = f"Sub-agent finished with status: {result.status.value}"

            logger.info(f"[Task] {subagent_id} completed with status: {result.status.value}")

            # Store result
            task_result = {
                "index": task_index,
                "agent": agent_name,
                "agent_id": subagent_id,
                "prompt": prompt,
                "content": content,
                "success": result.status.value in ("completed", "max_steps_reached"),
                "status": result.status.value,
                "steps": result.steps,
                "messages": result.messages,
            }
            self.sub_results.append(task_result)

            return task_result

        except Exception as e:
            logger.error(f"[Task] Task {task_index} failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "index": task_index,
                "agent": agent_name,
                "success": False,
                "error": str(e),
                "content": f"Error executing task: {str(e)}"
            }

    async def execute(
        self,
        agent: Optional[str] = None,
        prompt: Optional[str] = None,
        tasks: Optional[List[Dict[str, str]]] = None,
    ) -> ToolResult:
        """Launch sub-agents to execute tasks

        Supports two modes:
        1. Single task: Provide agent and prompt directly
        2. Parallel tasks: Provide tasks array with multiple tasks

        Args:
            agent: For single task mode - agent configuration name
            prompt: For single task mode - task description
            tasks: For parallel mode - list of task dicts with 'agent' and 'prompt'

        Returns:
            ToolResult with task execution results
        """
        # Determine execution mode
        if tasks is not None and len(tasks) > 0:
            # Parallel mode
            return await self._execute_parallel(tasks)
        elif agent and prompt:
            # Single task mode
            result = await self._execute_single_task(0, agent, prompt)
            return ToolResult(
                content=result.get("content", ""),
                success=result.get("success", False),
                error=result.get("error")
            )
        else:
            return ToolResult(
                content="",
                success=False,
                error="Invalid parameters. Provide either (agent + prompt) for single task, or tasks array for parallel execution."
            )

    async def _execute_parallel(self, tasks: List[Dict[str, str]]) -> ToolResult:
        """Execute multiple tasks in parallel"""
        logger.info(f"[Task] Starting {len(tasks)} tasks in parallel")

        # Create coroutines for all tasks
        coroutines = []
        for i, task in enumerate(tasks):
            agent_name = task.get("agent")
            prompt = task.get("prompt")
            if agent_name and prompt:
                coroutines.append(self._execute_single_task(i, agent_name, prompt))
            else:
                logger.warning(f"[Task] Skipping invalid task at index {i}")

        if not coroutines:
            return ToolResult(
                content="No valid tasks to execute",
                success=False,
                error="All tasks were invalid"
            )

        # Execute all tasks concurrently
        start_time = asyncio.get_event_loop().time()
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        end_time = asyncio.get_event_loop().time()

        logger.info(f"[Task] All {len(tasks)} tasks completed in {end_time - start_time:.2f}s")

        # Process results
        successful = []
        failed = []

        for result in results:
            if isinstance(result, Exception):
                failed.append({"error": str(result)})
            elif result.get("success"):
                successful.append(result)
            else:
                failed.append(result)

        # Format output
        output_lines = [
            f"Parallel Execution Complete ({len(successful)}/{len(tasks)} successful)",
            f"Time: {end_time - start_time:.2f}s",
            "=" * 60,
            ""
        ]

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                output_lines.append(f"## Task {i+1}: ERROR ❌")
                output_lines.append(f"Error: {str(result)}\n")
            else:
                agent_name = result.get("agent", "unknown")
                success = result.get("success", False)
                status_icon = "✅" if success else "❌"
                output_lines.append(f"## Task {i+1}: {agent_name} {status_icon}")
                output_lines.append(f"Status: {result.get('status', 'unknown')}")
                output_lines.append("")
                output_lines.append(result.get("content", "No content"))
                output_lines.append("")
                output_lines.append("-" * 60)
                output_lines.append("")

        return ToolResult(
            content="\n".join(output_lines),
            success=len(failed) == 0 or len(successful) > 0,
        )
