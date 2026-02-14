"""Feishu Doc Tool - Create cloud documents on Feishu/Lark platform"""

import os
import json
import logging
from typing import Dict, Any, Optional
import aiohttp

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class FeishuDocTool(BaseTool):
    """Tool for creating and editing Feishu (Lark) cloud documents

    This tool uses Feishu Open Platform API to:
    - Create new cloud documents
    - Add content blocks (text, headings, lists, etc.)
    - Set document permissions

    Requires FEISHU_APP_ID and FEISHU_APP_SECRET environment variables.
    """

    def __init__(self):
        """Initialize Feishu Doc tool"""
        self.app_id = os.environ.get("FEISHU_APP_ID")
        self.app_secret = os.environ.get("FEISHU_APP_SECRET")
        self.access_token: Optional[str] = None
        self.token_expires_at: int = 0

    @property
    def name(self) -> str:
        return "create_feishu_doc"

    @property
    def description(self) -> str:
        return (
            "Create a cloud document on Feishu (Lark) platform.\n"
            "This tool creates a new document with structured content including "
            "title, headings, text, lists, and formatted sections.\n"
            "Perfect for saving research reports and collaborative documents.\n\n"
            "Note: Content supports markdown-like formatting:\n"
            "- # Heading 1, ## Heading 2, ### Heading 3\n"
            "- - bullet points, 1. numbered lists\n"
            "- **bold**, *italic*\n"
            "- ```code blocks```\n"
            "- | Tables | with | columns | (formatted as text)"
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
                        "```code blocks```, | tables | with | columns |, and plain text paragraphs."
                    )
                },
                "folder_token": {
                    "type": "string",
                    "description": "Optional: Feishu folder token to save the document in"
                }
            },
            "required": ["title", "content"]
        }

    async def _get_tenant_access_token(self) -> Optional[str]:
        """Get Feishu tenant access token (required for document operations)"""
        import time

        # Check if token is still valid
        if self.access_token and time.time() < self.token_expires_at - 300:
            return self.access_token

        if not self.app_id or not self.app_secret:
            logger.error("FEISHU_APP_ID or FEISHU_APP_SECRET not configured")
            return None

        # Use tenant_access_token instead of app_access_token for document operations
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json"}
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

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

    async def _create_document(self, title: str, folder_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create a new Feishu document"""
        token = await self._get_tenant_access_token()
        if not token:
            return None

        url = "https://open.feishu.cn/open-apis/docx/v1/documents"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {"title": title}
        if folder_token:
            payload["folder_token"] = folder_token

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    logger.debug(f"Create document response: {data}")
                    if data.get("code") == 0:
                        return data["data"]["document"]
                    else:
                        logger.error(f"Failed to create document: {data}")
                        return None
        except Exception as e:
            logger.error(f"Error creating document: {e}")
            return None

    async def _set_document_permissions(self, document_id: str) -> bool:
        """Set document permissions to allow anyone with link to view"""
        token = await self._get_tenant_access_token()
        if not token:
            return False

        # Set document public access
        url = f"https://open.feishu.cn/open-apis/drive/v1/permissions/{document_id}/public"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "external_access": True,  # Allow external access
            "security_entity": "anyone",  # Anyone can access
            "comment_entity": "anyone",  # Anyone can comment
            "share_entity": "anyone",  # Anyone can share
            "link_share_entity": "anyone"  # Link sharing enabled
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        logger.info(f"Successfully set permissions for document {document_id}")
                        return True
                    else:
                        logger.warning(f"Could not set permissions: {data}")
                        return False
        except Exception as e:
            logger.warning(f"Error setting permissions: {e}")
            return False

    async def _add_blocks(self, document_id: str, blocks: list) -> bool:
        """Add content blocks to document using the children API

        The correct endpoint is: /documents/{doc_id}/blocks/{block_id}/children
        This adds blocks as children of the specified parent block.
        """
        token = await self._get_tenant_access_token()
        if not token:
            return False

        # First, get the root block_id (which is the same as document_id for new docs)
        root_block_id = document_id

        # Use the /children endpoint to add blocks
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{root_block_id}/children"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Split blocks into chunks (API limit)
        chunk_size = 50
        for i in range(0, len(blocks), chunk_size):
            chunk = blocks[i:i + chunk_size]
            payload = {
                "children": chunk,
                "index": -1  # Append to end
            }

            logger.debug(f"Adding {len(chunk)} blocks to document {document_id}")
            logger.debug(f"Payload: {payload}")

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        text = await resp.text()
                        logger.debug(f"Response status: {resp.status}")
                        logger.debug(f"Response body: {text}")

                        if resp.status != 200:
                            logger.error(f"HTTP error {resp.status}: {text}")
                            return False

                        try:
                            data = json.loads(text)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON response: {text}")
                            return False

                        if data.get("code") != 0:
                            logger.error(f"API error: {data}")
                            return False

                        logger.info(f"Successfully added chunk of {len(chunk)} blocks")
            except Exception as e:
                logger.error(f"Error adding blocks: {e}")
                return False

        return True

    def _parse_content_to_blocks(self, content: str) -> list:
        """Parse markdown-like content to Feishu blocks

        Supports: headings, lists, code blocks, tables, inline formatting.

        Note: Feishu API uses snake_case for field names:
        - text_run (not textRun)
        - text_element_style (not text_style)
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

            # Heading 1 - make it bold and larger (simulated with styling)
            if stripped.startswith("# "):
                text = stripped[2:].strip()
                if text:
                    blocks.append({
                        "block_type": 2,
                        "text": {
                            "elements": [{
                                "type": "textRun",
                                "text_run": {
                                    "content": text,
                                    "text_element_style": {"bold": True}
                                }
                            }],
                            "style": {}
                        }
                    })
            # Heading 2 - make it bold
            elif stripped.startswith("## "):
                text = stripped[3:].strip()
                if text:
                    blocks.append({
                        "block_type": 2,
                        "text": {
                            "elements": [{
                                "type": "textRun",
                                "text_run": {
                                    "content": text,
                                    "text_element_style": {"bold": True}
                                }
                            }],
                            "style": {}
                        }
                    })
            # Heading 3 - make it italic
            elif stripped.startswith("### "):
                text = stripped[4:].strip()
                if text:
                    blocks.append({
                        "block_type": 2,
                        "text": {
                            "elements": [{
                                "type": "textRun",
                                "text_run": {
                                    "content": text,
                                    "text_element_style": {"italic": True, "bold": True}
                                }
                            }],
                            "style": {}
                        }
                    })
            # Bullet list - use bullet character prefix
            elif stripped.startswith(("- ", "* ")):
                text = "• " + stripped[2:].strip()
                if text:
                    blocks.append({
                        "block_type": 2,
                        "text": {"elements": self._create_text_elements(text), "style": {}}
                    })
            # Numbered list - keep the number prefix
            elif stripped[0].isdigit() and ". " in stripped[:4]:
                parts = stripped.split(". ", 1)
                if len(parts) == 2 and parts[1].strip():
                    text = parts[0] + ". " + parts[1].strip()
                    blocks.append({
                        "block_type": 2,
                        "text": {"elements": self._create_text_elements(text), "style": {}}
                    })
            # Table - detect markdown table format
            elif stripped.startswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1

                # Parse and format the table
                table_blocks = self._parse_table(table_lines)
                blocks.extend(table_blocks)
                continue  # Skip the i += 1 at the end since we already advanced

            # Code block
            elif stripped.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                code_content = "\n".join(code_lines)
                if code_content:
                    # Add code block marker
                    blocks.append({
                        "block_type": 2,
                        "text": {
                            "elements": [{
                                "type": "textRun",
                                "text_run": {
                                    "content": "【代码】",
                                    "text_element_style": {"bold": True}
                                }
                            }],
                            "style": {}
                        }
                    })
                    # Add code content with inline_code style
                    blocks.append({
                        "block_type": 2,
                        "text": {
                            "elements": [{
                                "type": "textRun",
                                "text_run": {
                                    "content": code_content,
                                    "text_element_style": {"inline_code": True}
                                }
                            }],
                            "style": {}
                        }
                    })
            # Regular paragraph
            else:
                elements = self._parse_inline_formatting(stripped)
                if elements:
                    blocks.append({
                        "block_type": 2,
                        "text": {"elements": elements, "style": {}}
                    })

            i += 1

        return blocks

    def _create_text_elements(self, text: str) -> list:
        """Create text elements with inline formatting support"""
        return self._parse_inline_formatting(text)

    def _parse_inline_formatting(self, text: str) -> list:
        """Parse inline formatting: **bold**, *italic*

        Returns elements in Feishu API format with snake_case fields.
        """
        import re

        elements = []
        # Pattern to match **bold** and *italic* (non-greedy)
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
                        "text_run": {
                            "content": content,
                            "text_element_style": {"bold": True}
                        }
                    })
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                content = part[1:-1].strip()
                if content:
                    elements.append({
                        "type": "textRun",
                        "text_run": {
                            "content": content,
                            "text_element_style": {"italic": True}
                        }
                    })
            else:
                elements.append({
                    "type": "textRun",
                    "text_run": {"content": part}
                })

        return elements if elements else [{"type": "textRun", "text_run": {"content": text}}]

    def _parse_table(self, table_lines: list) -> list:
        """Parse markdown table lines and convert to formatted text blocks

        Since Feishu API table block requires complex nested structure,
        we format the table as monospace text with proper column alignment.

        Args:
            table_lines: List of lines forming the markdown table

        Returns:
            List of text blocks formatted as a table
        """
        if len(table_lines) < 2:
            # Not a valid table, treat as regular text
            return [{
                "block_type": 2,
                "text": {"elements": self._create_text_elements("\n".join(table_lines)), "style": {}}
            }]

        blocks = []

        # Parse table rows
        rows = []
        max_cols = 0

        for line in table_lines:
            # Remove leading/trailing | and split by |
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows.append(cells)
            max_cols = max(max_cols, len(cells))

        # Skip separator row (row 1, which contains --- or similar)
        data_rows = [rows[0]] + rows[2:] if len(rows) > 2 else rows

        # Calculate column widths for alignment (use byte length for Chinese chars)
        col_widths = [0] * max_cols
        for row in data_rows:
            for i, cell in enumerate(row):
                # Use display width (approximate for mixed content)
                width = len(cell) if cell else 0
                col_widths[i] = max(col_widths[i], min(width, 20))  # Cap at 20

        # Format each row as a text block
        for row_idx, row in enumerate(data_rows):
            # Pad row to max columns
            while len(row) < max_cols:
                row.append("")

            # Build formatted row
            formatted_cells = []
            for i, cell in enumerate(row):
                # Pad cell content to column width (simple left-align)
                cell_len = len(cell) if cell else 0
                padding = max(0, col_widths[i] - cell_len)
                padded = cell + "  " + " " * padding  # Extra space for visual separation
                formatted_cells.append(padded)

            row_text = "| " + " | ".join(formatted_cells) + " |"

            # Create elements for this row
            if row_idx == 0:
                # Header row - bold with code style border
                elements = [
                    {
                        "type": "textRun",
                        "text_run": {
                            "content": "┌" + "─" * (len(row_text) - 2) + "┐\n",
                            "text_element_style": {"inline_code": True}
                        }
                    },
                    {
                        "type": "textRun",
                        "text_run": {
                            "content": row_text + "\n",
                            "text_element_style": {"bold": True, "inline_code": True}
                        }
                    },
                    {
                        "type": "textRun",
                        "text_run": {
                            "content": "├" + "─" * (len(row_text) - 2) + "┤",
                            "text_element_style": {"inline_code": True}
                        }
                    }
                ]
                blocks.append({
                    "block_type": 2,
                    "text": {"elements": elements, "style": {}}
                })
            else:
                # Data row - regular with inline_code for monospace look
                elements = [{
                    "type": "textRun",
                    "text_run": {
                        "content": row_text,
                        "text_element_style": {"inline_code": True}
                    }
                }]
                blocks.append({
                    "block_type": 2,
                    "text": {"elements": elements, "style": {}}
                })

        # Add bottom border
        if blocks:
            border_text = "└" + "─" * (len(row_text) - 2) + "┘"
            blocks.append({
                "block_type": 2,
                "text": {
                    "elements": [{
                        "type": "textRun",
                        "text_run": {
                            "content": border_text,
                            "text_element_style": {"inline_code": True}
                        }
                    }],
                    "style": {}
                }
            })

        # Add empty line after table
        blocks.append({
            "block_type": 2,
            "text": {"elements": [{"type": "textRun", "text_run": {"content": ""}}], "style": {}}
        })

        return blocks

    async def execute(
        self,
        title: str,
        content: str,
        folder_token: Optional[str] = None
    ) -> ToolResult:
        """Create a Feishu document with the given content

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
            logger.info(f"Creating Feishu document: {title}")
            doc_info = await self._create_document(title, folder_token)
            if not doc_info:
                return ToolResult(
                    content="",
                    success=False,
                    error="Failed to create Feishu document. Check your app credentials and permissions."
                )

            document_id = doc_info["document_id"]
            # Build document URL - Feishu docx documents use this format
            doc_url = f"https://www.feishu.cn/docx/{document_id}"

            logger.info(f"Document created with ID: {document_id}")

            # Parse and add content
            blocks = self._parse_content_to_blocks(content)
            logger.info(f"Parsed {len(blocks)} content blocks")

            if blocks:
                success = await self._add_blocks(document_id, blocks)
                if not success:
                    logger.warning("Failed to add content blocks, but document was created")
                    return ToolResult(
                        content=(
                            f"Document created but content could not be added.\n"
                            f"Title: {title}\n"
                            f"URL: {doc_url}\n"
                            f"Document ID: {document_id}\n\n"
                            f"You can manually add the content by editing the document."
                        ),
                        success=True  # Partial success
                    )

            # Set document permissions to allow access
            await self._set_document_permissions(document_id)

            logger.info(f"Successfully created Feishu document: {doc_url}")

            return ToolResult(
                content=(
                    f"✅ Document created successfully!\n\n"
                    f"Title: {title}\n"
                    f"URL: {doc_url}\n"
                    f"Document ID: {document_id}\n"
                    f"Content blocks: {len(blocks)}\n\n"
                    f"Note: If the URL doesn't open, please check your Feishu app permissions. "
                    f"The document may need to be shared manually from your Feishu workspace."
                ),
                success=True
            )

        except Exception as e:
            logger.error(f"Failed to create Feishu document: {e}")
            import traceback
            traceback.print_exc()
            return ToolResult(
                content="",
                success=False,
                error=f"Error creating Feishu document: {str(e)}"
            )
