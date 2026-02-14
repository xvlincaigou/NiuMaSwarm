"""Feishu Wiki Tool - Create wiki documents on Feishu/Lark platform

Wiki (知识库) is Feishu's knowledge base document type, different from docx.
- Wiki is better for structured knowledge and team collaboration
- Documents appear in your personal/team knowledge base
"""

import os
import json
import logging
from typing import Dict, Any, Optional
import aiohttp

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class FeishuWikiTool(BaseTool):
    """Tool for creating Feishu (Lark) Wiki documents

    This tool creates documents in your personal/team knowledge base (wiki),
    which is different from docx cloud documents.

    Requires FEISHU_APP_ID and FEISHU_APP_SECRET environment variables.
    Optional: FEISHU_SPACE_ID for a specific wiki space.
    """

    def __init__(self):
        """Initialize Feishu Wiki tool"""
        self.app_id = os.environ.get("FEISHU_APP_ID")
        self.app_secret = os.environ.get("FEISHU_APP_SECRET")
        self.space_id = os.environ.get("FEISHU_WIKI_SPACE_ID")  # Optional: specific wiki space
        self.access_token: Optional[str] = None
        self.token_expires_at: int = 0

    @property
    def name(self) -> str:
        return "create_feishu_wiki"

    @property
    def description(self) -> str:
        return (
            "Create a wiki (知识库) document on Feishu (Lark) platform.\n"
            "Wiki documents are knowledge base documents that appear in your personal/team space, "
            "different from regular docx cloud documents.\n\n"
            "This is RECOMMENDED for research reports as they appear directly in your Feishu workspace.\n\n"
            "Content supports markdown-like formatting:\n"
            "- # Heading 1, ## Heading 2, ### Heading 3\n"
            "- - bullet points, 1. numbered lists\n"
            "- **bold**, *italic*\n"
            "- ```code blocks```"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Document title (required)"
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Document content in markdown-like format. "
                        "Supports: # Heading 1, ## Heading 2, ### Heading 3, "
                        "- bullet points, 1. numbered lists, **bold**, *italic*, "
                        "```code blocks```, and plain text paragraphs."
                    )
                },
                "folder_token": {
                    "type": "string",
                    "description": "Optional: Folder token to organize the wiki document"
                }
            },
            "required": ["title", "content"]
        }

    async def _get_tenant_access_token(self) -> Optional[str]:
        """Get Feishu tenant access token"""
        import time

        if self.access_token and time.time() < self.token_expires_at - 300:
            return self.access_token

        if not self.app_id or not self.app_secret:
            logger.error("FEISHU_APP_ID or FEISHU_APP_SECRET not configured")
            return None

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json"}
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        self.access_token = data["tenant_access_token"]
                        self.token_expires_at = time.time() + data.get("expire", 7200)
                        logger.info("Successfully obtained Feishu tenant_access_token")
                        return self.access_token
                    else:
                        logger.error(f"Failed to get tenant access token: {data}")
                        return None
        except Exception as e:
            logger.error(f"Error getting tenant access token: {e}")
            return None

    async def _get_user_access_token(self) -> Optional[str]:
        """Get user access token to create documents in user's space"""
        # For wiki documents, we need to act on behalf of a user
        # Try to get from environment or use a default approach
        # This is a simplified version - in production you might need OAuth flow
        token = await self._get_tenant_access_token()
        return token

    async def _create_wiki_document(self, title: str, content: str, folder_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create a new Feishu wiki document

        Wiki uses nodes API to create documents in knowledge base
        """
        token = await self._get_tenant_access_token()
        if not token:
            return None

        # Get or find a space_id
        space_id = self.space_id
        if not space_id:
            # Try to get user's default space
            space_id = await self._get_default_space(token)
            if not space_id:
                logger.error("No wiki space found. Please set FEISHU_WIKI_SPACE_ID or ensure you have wiki access.")
                return None

        # Create wiki node (document)
        url = "https://open.feishu.cn/open-apis/wiki/v2/spaces/{}/nodes".format(space_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Convert markdown content to wiki format (rich text)
        wiki_content = self._convert_to_wiki_format(content)

        payload = {
            "node_type": "origin",
            "title": title,
            "content": wiki_content
        }

        if folder_token:
            payload["parent_node_token"] = folder_token

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    logger.debug(f"Create wiki response: {data}")
                    if data.get("code") == 0:
                        return data["data"]["node"]
                    else:
                        logger.error(f"Failed to create wiki document: {data}")
                        # If wiki fails, try fallback to docx
                        return None
        except Exception as e:
            logger.error(f"Error creating wiki document: {e}")
            return None

    async def _get_default_space(self, token: str) -> Optional[str]:
        """Get the default wiki space for the user"""
        url = "https://open.feishu.cn/open-apis/wiki/v2/spaces"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        items = data.get("data", {}).get("items", [])
                        if items:
                            # Return first space
                            return items[0]["space_id"]
                    logger.warning(f"No wiki spaces found or error: {data}")
                    return None
        except Exception as e:
            logger.error(f"Error getting wiki spaces: {e}")
            return None

    def _convert_to_wiki_format(self, content: str) -> Dict[str, Any]:
        """Convert markdown-like content to Feishu wiki rich text format

        Wiki uses a block-based structure similar to docx but with different format
        """
        blocks = []
        lines = content.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            # Heading 1
            if stripped.startswith("# "):
                text = stripped[2:].strip()
                blocks.append({
                    "block_type": 1,
                    "heading1": {"elements": self._create_elements(text)}
                })
            # Heading 2
            elif stripped.startswith("## "):
                text = stripped[3:].strip()
                blocks.append({
                    "block_type": 2,
                    "heading2": {"elements": self._create_elements(text)}
                })
            # Heading 3
            elif stripped.startswith("### "):
                text = stripped[4:].strip()
                blocks.append({
                    "block_type": 3,
                    "heading3": {"elements": self._create_elements(text)}
                })
            # Bullet list
            elif stripped.startswith(("- ", "* ")):
                text = stripped[2:].strip()
                blocks.append({
                    "block_type": 11,
                    "bullet": {"elements": self._create_elements("• " + text)}
                })
            # Numbered list
            elif stripped[0].isdigit() and ". " in stripped[:4]:
                parts = stripped.split(". ", 1)
                if len(parts) == 2 and parts[1].strip():
                    text = parts[0] + ". " + parts[1].strip()
                    blocks.append({
                        "block_type": 13,
                        "ordered": {"elements": self._create_elements(text)}
                    })
            # Code block
            elif stripped.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                code_content = "\n".join(code_lines)
                if code_content:
                    blocks.append({
                        "block_type": 14,
                        "code": {
                            "elements": [{"type": "textRun", "text_run": {"content": code_content}}],
                            "style": {}
                        }
                    })
            # Regular paragraph
            else:
                elements = self._create_inline_elements(stripped)
                blocks.append({
                    "block_type": 2,
                    "text": {"elements": elements, "style": {}}
                })

            i += 1

        return {"blocks": blocks}

    def _create_elements(self, text: str) -> list:
        """Create basic text elements"""
        return [{"type": "textRun", "text_run": {"content": text}}]

    def _create_inline_elements(self, text: str) -> list:
        """Parse inline formatting: **bold**, *italic*"""
        import re

        elements = []
        pattern = r'(\*\*[^*]+?\*\*|\*[^*]+?\*|[^*]+)'
        parts = re.findall(pattern, text)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                content = part[2:-2].strip()
                if content:
                    elements.append({
                        "type": "textRun",
                        "text_run": {"content": content, "text_element_style": {"bold": True}}
                    })
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                content = part[1:-1].strip()
                if content:
                    elements.append({
                        "type": "textRun",
                        "text_run": {"content": content, "text_element_style": {"italic": True}}
                    })
            else:
                elements.append({
                    "type": "textRun",
                    "text_run": {"content": part}
                })

        return elements if elements else [{"type": "textRun", "text_run": {"content": text}}]

    async def execute(
        self,
        title: str,
        content: str,
        folder_token: Optional[str] = None
    ) -> ToolResult:
        """Create a Feishu wiki document

        Args:
            title: Document title
            content: Document content in markdown-like format
            folder_token: Optional folder token

        Returns:
            ToolResult with document URL or error
        """
        try:
            # Check credentials
            if not self.app_id or not self.app_secret:
                return ToolResult(
                    content="",
                    success=False,
                    error="Feishu credentials not configured. Set FEISHU_APP_ID and FEISHU_APP_SECRET environment variables."
                )

            # Create document
            logger.info(f"Creating Feishu wiki document: {title}")
            doc_info = await self._create_wiki_document(title, content, folder_token)

            if not doc_info:
                return ToolResult(
                    content="",
                    success=False,
                    error="Failed to create Feishu wiki document. Check your app permissions and ensure you have wiki access. "
                          "You may need to set FEISHU_WIKI_SPACE_ID environment variable."
                )

            node_token = doc_info["node_token"]
            obj_token = doc_info.get("obj_token", "")
            space_id = doc_info.get("space_id", self.space_id or "")

            # Build wiki URL
            # Wiki documents use a different URL format
            wiki_url = f"https://www.feishu.cn/wiki/{node_token}"

            logger.info(f"Successfully created Feishu wiki document: {wiki_url}")

            return ToolResult(
                content=(
                    f"✅ Wiki document created successfully!\n\n"
                    f"Title: {title}\n"
                    f"URL: {wiki_url}\n"
                    f"Node Token: {node_token}\n"
                    f"Space ID: {space_id}\n\n"
                    f"The document is now available in your Feishu Wiki (知识库)."
                ),
                success=True
            )

        except Exception as e:
            logger.error(f"Failed to create Feishu wiki document: {e}")
            import traceback
            traceback.print_exc()
            return ToolResult(
                content="",
                success=False,
                error=f"Error creating Feishu wiki document: {str(e)}"
            )
