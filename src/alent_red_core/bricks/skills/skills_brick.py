import asyncio
import hashlib
import json
import os
import platform
import re
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import yaml

from ..base_brick import BaseBrick
from ...common import Logger
from ...models import (
    BrickConfigSkills,
    Conversation,
    Error,
    ErrorCode,
    MessageContentToolResponse,
    Tool,
)
from ...database import Database
from ...blob import BlobStorage
from .models import Skill, SkillRoot

if TYPE_CHECKING:
    from ..brick_manager import BrickManager
    from ...looper import Looper
    from ...providers import ProviderManager


class SkillsBrick(BaseBrick):
    """Skills brick exposing Agent Skills installed on the host to the LLM.

    Skills follow the open Agent Skills format: one directory per skill holding a
    SKILL.md with a YAML front matter (name, description) and Markdown instructions.
    Known roots of other tools are scanned so already-installed skills are reused.
    """

    _identifier = "skills"

    _tool_load_skill = "load_skill"

    _os_darwin = "Darwin"
    _os_windows = "Windows"

    _label_agent = "agent"
    _label_app = "app"
    _label_claude = "claude"
    _label_agents = "agents"

    _app_folder_name = "AlentRed"
    _app_skills_folder_name = "skills"
    _agent_skills_folder_name = "skills-agents"

    _description_agent = "writable, private to this agent, kept across its conversations"
    _description_app = "writable, shared by every agent"
    _description_read_only = "read-only"

    _skill_file_name = "SKILL.md"
    _front_matter_delimiter = "---"
    _name_pattern = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    _name_max_length = 64
    _id_separator = "/"

    _prompt_intro = (
        "Skills: reusable instruction sets installed on this computer. When a task matches "
        "a skill, call load_skill with its id BEFORE acting and follow the instructions it "
        "returns. Available skills (id: description):"
    )
    _prompt_no_skills = "Available skills: none."
    _prompt_roots_intro = "Skill roots (each skill is a subfolder holding a SKILL.md):"
    _prompt_create_hint = (
        "To create a skill, write <root>/<name>/SKILL.md in a writable root (agent for "
        "something private to you, app for something every agent should get), starting "
        "with a YAML front matter between --- lines holding name (lowercase letters, digits "
        "and hyphens, equal to the folder name) and description, then the instructions. "
        "It becomes available on the next turn."
    )
    _prompt_separator = "\n"

    def __init__(
        self,
        config: BrickConfigSkills,
        looper: "Looper",
        bricks: "BrickManager",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ):
        """Initialize skills brick.

        Args:
            config: Skills brick configuration.
            looper: Looper instance for triggering conversation processing.
            bricks: Brick manager instance.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.
        """
        super().__init__(config, looper, bricks, providers, database, blob)
        self._app_folder: Path | None = None
        self._shared_roots: list[SkillRoot] = []
        self._logger = Logger.get_logger("bricks.skills.skills_brick")

    async def get_identifier(self) -> str:
        """Get unique identifier for this brick type.

        Returns:
            Brick identifier string.
        """
        return self._identifier

    async def setup(self) -> None:
        """Resolve the skill roots for the host operating system.

        Raises:
            Error: If the host operating system is not supported.
        """
        self._app_folder = self._resolve_app_folder(platform.system())
        self._shared_roots = self._resolve_shared_roots(self._app_folder)
        self._logger.debug("setup_completed", root_count=len(self._shared_roots))

    async def get_prompt(self, conversation: Conversation) -> str | None:
        """List the discovered skills and the roots they come from.

        Args:
            conversation: Conversation object.

        Returns:
            Rendered skills prompt.
        """
        roots = self._resolve_roots(conversation.agent_id)
        skills = await asyncio.to_thread(self._scan, roots)

        lines: list[str] = []
        if skills:
            lines.append(self._prompt_intro)
            lines.extend(f"- {skill.id}: {skill.description}" for skill in skills)
        else:
            lines.append(self._prompt_no_skills)

        lines.append(self._prompt_roots_intro)
        lines.extend(f"- {root.label}: {root.path} ({root.description})" for root in roots)
        lines.append(self._prompt_create_hint)

        self._logger.debug(
            "get_prompt_completed", conversation_id=str(conversation.id), skill_count=len(skills)
        )

        return self._prompt_separator.join(lines)

    async def get_tools(self, conversation: Conversation) -> list[Tool] | None:
        """Get available tools for this brick.

        Args:
            conversation: Conversation object.

        Returns:
            List with the load_skill tool.
        """
        return [
            Tool(
                name=self._tool_load_skill,
                description=(
                    "Load the full instructions of a skill listed in the prompt, plus the "
                    "absolute path of its folder so you can read its files or run its scripts."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Skill id as listed in the prompt, e.g. claude/pdf.",
                        }
                    },
                    "required": ["id"],
                },
            )
        ]

    async def handle_tool_request(
        self,
        name: str,
        parameters: str,
        conversation: Conversation,
    ) -> MessageContentToolResponse | None:
        """Handle tool request.

        Args:
            name: Tool name.
            parameters: Tool parameters as JSON string.
            conversation: Conversation object.

        Returns:
            Tool response with the skill instructions, or a text listing the available
            ids when the requested one is unknown.

        Raises:
            Error: If tool name is unknown or parameters are invalid.
        """
        self._logger.debug(
            "handle_tool_request_started",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        if name != self._tool_load_skill:
            raise Error(ErrorCode.NOT_FOUND, f"Unknown tool: {name}")

        skill_id = self._read_skill_id(parameters=parameters)
        roots = self._resolve_roots(conversation.agent_id)
        skills = await asyncio.to_thread(self._scan, roots)
        skill = next((item for item in skills if item.id == skill_id), None)

        if skill is None:
            self._logger.info(
                "load_skill_unknown", conversation_id=str(conversation.id), skill_id=skill_id
            )
            available = ", ".join(item.id for item in skills) or "none"
            return MessageContentToolResponse(
                text=f"Unknown skill id: {skill_id}. Available skills: {available}."
            )

        self._logger.info(
            "load_skill_completed", conversation_id=str(conversation.id), skill_id=skill_id
        )

        return MessageContentToolResponse(
            text=f"Skill {skill.id}\nFolder: {skill.directory}\n\n{skill.body}"
        )

    def _resolve_app_folder(self, os_name: str) -> Path:
        if os_name == self._os_darwin:
            return Path.home() / "Library" / "Application Support" / self._app_folder_name
        if os_name == self._os_windows:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if not local_app_data:
                raise Error(ErrorCode.INTERNAL, "LOCALAPPDATA environment variable is not set")
            return Path(local_app_data) / self._app_folder_name
        raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")

    def _resolve_shared_roots(self, app_folder: Path) -> list[SkillRoot]:
        home = Path.home()
        return [
            SkillRoot(
                label=self._label_app,
                path=app_folder / self._app_skills_folder_name,
                writable=True,
                description=self._description_app,
            ),
            SkillRoot(
                label=self._label_claude,
                path=home / ".claude" / "skills",
                writable=False,
                description=self._description_read_only,
            ),
            SkillRoot(
                label=self._label_agents,
                path=home / ".agents" / "skills",
                writable=False,
                description=self._description_read_only,
            ),
        ]

    def _resolve_roots(self, agent_id: UUID | None) -> list[SkillRoot]:
        # Order matters: on a duplicated skill the first root wins, so the agent's own
        # folder shadows the shared one, which shadows the other tools' folders.
        if self._app_folder is None:
            raise Error(ErrorCode.INTERNAL, "Skills roots not initialized")
        if agent_id is None:
            return self._shared_roots

        agent_root = SkillRoot(
            label=self._label_agent,
            path=self._app_folder / self._agent_skills_folder_name / str(agent_id),
            writable=True,
            description=self._description_agent,
        )
        return [agent_root, *self._shared_roots]

    def _scan(self, roots: list[SkillRoot]) -> list[Skill]:
        skills: list[Skill] = []
        seen_ids: set[str] = set()
        seen_digests: set[str] = set()

        for root in roots:
            if not root.path.is_dir():
                continue
            for directory in sorted(root.path.iterdir()):
                skill_file = directory / self._skill_file_name
                if directory.name.startswith(".") or not skill_file.is_file():
                    continue

                skill = self._load_skill(root, directory, skill_file)
                if skill is None:
                    continue

                digest = hashlib.sha256(skill.body.encode("utf-8")).hexdigest()
                if skill.id in seen_ids or digest in seen_digests:
                    self._logger.debug("skill_duplicated", skill_id=skill.id, path=str(directory))
                    continue

                seen_ids.add(skill.id)
                seen_digests.add(digest)
                skills.append(skill)

        return skills

    def _load_skill(self, root: SkillRoot, directory: Path, skill_file: Path) -> Skill | None:
        try:
            content = skill_file.read_text(encoding="utf-8")
        except OSError as exception:
            self._logger.debug("skill_unreadable", path=str(skill_file), reason=str(exception))
            return None

        front_matter, body = self._split_front_matter(content)
        if front_matter is None:
            self._logger.debug("skill_invalid", path=str(skill_file), reason="missing front matter")
            return None

        name = front_matter.get("name", directory.name)
        description = front_matter.get("description")
        if not isinstance(name, str) or not self._is_valid_name(name):
            self._logger.debug("skill_invalid", path=str(skill_file), reason="invalid name")
            return None
        if not isinstance(description, str) or not description.strip():
            self._logger.debug("skill_invalid", path=str(skill_file), reason="missing description")
            return None

        return Skill(
            id=f"{root.label}{self._id_separator}{name}",
            name=name,
            description=" ".join(description.split()),
            directory=directory,
            body=body.strip(),
        )

    def _split_front_matter(self, content: str) -> tuple[dict[str, object] | None, str]:
        lines = content.splitlines()
        if not lines or lines[0].strip() != self._front_matter_delimiter:
            return None, content

        for index in range(1, len(lines)):
            if lines[index].strip() == self._front_matter_delimiter:
                try:
                    parsed = yaml.safe_load("\n".join(lines[1:index]))
                except yaml.YAMLError:
                    return None, content
                if not isinstance(parsed, dict):
                    return None, content
                return {str(key): value for key, value in parsed.items()}, "\n".join(
                    lines[index + 1 :]
                )

        return None, content

    def _is_valid_name(self, name: str) -> bool:
        return len(name) <= self._name_max_length and self._name_pattern.match(name) is not None

    def _read_skill_id(self, parameters: str) -> str:
        try:
            parsed_parameters = json.loads(parameters)
        except json.JSONDecodeError as exception:
            raise Error(ErrorCode.INVALID_ARGUMENT, f"Invalid JSON parameters: {exception}")

        if not isinstance(parsed_parameters, dict):
            raise Error(ErrorCode.INVALID_ARGUMENT, "Parameters must be a JSON object")

        raw_id = parsed_parameters.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise Error(ErrorCode.INVALID_ARGUMENT, "Missing or invalid required parameter: id")
        return raw_id.strip()
