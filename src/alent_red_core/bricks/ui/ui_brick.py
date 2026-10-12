import asyncio
import datetime
import json
from importlib import resources
from io import BytesIO
from typing import TYPE_CHECKING
from uuid import uuid4

from PIL import Image

from ..base_brick import BaseBrick
from ...common import Logger
from ...models import (
    AgentReasoning,
    AgentVerbosity,
    Blob,
    BrickConfigType,
    BrickConfigUI,
    BrickConfigUIMovePointerCoordinateSpace,
    BrickConfigUIMovePointerGeometry,
    Conversation,
    Error,
    ErrorCode,
    MessageContent,
    MessageContentTool,
    MessageContentToolResponse,
    MessageContentType,
    MessageContentUser,
    Tool,
)
from ...database import Database
from ...blob import BlobStorage
from .system_access import BaseSystemAccess, SystemAccessBuilder
from .system_access.models import (
    Key,
    MouseButton,
    PointerPosition,
    PressKind,
    Screen,
    ScreenCapture,
)

if TYPE_CHECKING:
    from ..brick_manager import BrickManager
    from ...looper import Looper
    from ...providers import ProviderManager


class UIBrick(BaseBrick):
    """UI brick for screen capture and keyboard input."""

    _identifier = "ui"

    _tool_take_screenshot = "take_screenshot"
    _tool_press_keyboard_keys = "press_keyboard_keys"
    _tool_type_unicode_text = "type_unicode_text"
    _tool_click_pointer = "click_pointer"
    _tool_move_pointer_coordinates = "move_pointer_coordinates"
    _tool_move_pointer_description = "move_pointer_description"

    _vision_tool_locate_element = "locate_element"
    _vision_normalized_scale = 1000
    _vision_not_found_message = (
        "The vision model did not find an element matching your description. "
        "Take a new screenshot and retry with a more specific description (exact text, "
        "colors, position relative to other elements), or use move_pointer_coordinates."
    )

    _prompt_template = (
        "Screens: {{SCREENS}}\n\n"
        "Pointer moves: prefer move_pointer_coordinates, giving the pixel size of the "
        "screenshot you are looking at and the target point inside it. Moves only confirm; "
        "take a screenshot yourself when you need to check where the pointer is before "
        "clicking. If a move misses the target, use move_pointer_description instead."
    )
    _prompt_no_screens = "No screens detected."
    _screen_separator = ", "
    _primary_label = " main"

    _screenshot_max_edge = 1920
    _screenshot_format = "JPEG"
    _screenshot_quality = 80
    _screenshot_content_type = "image/jpeg"
    _screenshot_file_extension = "jpg"

    _cursor_assets_package = "alent_red_core.bricks.ui.assets"
    _cursor_dark_asset = "cursor_dark.png"
    _cursor_light_asset = "cursor_light.png"
    _cursor_marker_fraction = 0.05
    _cursor_luminance_threshold = 0.6
    _cursor_luminance_red_coefficient = 0.2126
    _cursor_luminance_green_coefficient = 0.7152
    _cursor_luminance_blue_coefficient = 0.0722

    _successive_press_delay_seconds = 0.002

    # ASCII "ALENTRED" packed as a 64-bit integer. Written to every synthetic
    # mouse/keyboard event's OS user-data field (kCGEventSourceUserData on
    # macOS, dwExtraInfo on Windows) so an overlay window can recognize and
    # pass through events from this process instead of consuming them.
    _event_tag = 0x414C454E54524544

    def __init__(
        self,
        config: BrickConfigUI,
        looper: "Looper",
        bricks: "BrickManager",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ):
        """Initialize UI brick.

        Args:
            config: UI brick configuration.
            looper: Looper instance for triggering conversation processing.
            bricks: Brick manager instance.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.
        """
        super().__init__(config, looper, bricks, providers, database, blob)
        self._logger = Logger.get_logger("bricks.ui.ui_brick")
        self._system_access: BaseSystemAccess
        self._cursor_dark_image: Image.Image
        self._cursor_light_image: Image.Image

    async def get_identifier(self) -> str:
        """Get unique identifier for this brick type.

        Returns:
            Brick identifier string.
        """
        return self._identifier

    async def setup(self) -> None:
        """Build the SystemAccess implementation and load cursor assets.

        Raises:
            Error: If the host operating system is not supported or the
                cursor asset files cannot be loaded.
        """
        self._logger.debug("setup_started")
        self._system_access = await SystemAccessBuilder.build()
        self._cursor_dark_image = await asyncio.to_thread(
            self._load_cursor_image, self._cursor_dark_asset
        )
        self._cursor_light_image = await asyncio.to_thread(
            self._load_cursor_image, self._cursor_light_asset
        )
        self._logger.debug(
            "setup_completed",
            cursor_dark_size=f"{self._cursor_dark_image.width}x{self._cursor_dark_image.height}",
            cursor_light_size=f"{self._cursor_light_image.width}x{self._cursor_light_image.height}",
        )

    async def get_prompt(self, conversation: Conversation) -> str | None:
        """Build a prompt listing the connected screens.

        Args:
            conversation: Conversation object.

        Returns:
            Rendered screens prompt.

        Raises:
            Error: If the host operating system is not supported.
        """
        self._logger.debug("get_prompt_started", conversation_id=str(conversation.id))

        screens = await self._system_access.list_screens()

        if not screens:
            screens_block = self._prompt_no_screens
        else:
            screens_block = self._screen_separator.join(
                self._format_screen_entry(screen=item) for item in screens
            )

        prompt = self._prompt_template.replace("{{SCREENS}}", screens_block)

        self._logger.debug(
            "get_prompt_completed",
            conversation_id=str(conversation.id),
            screen_count=len(screens),
        )

        return prompt

    async def get_tools(self, conversation: Conversation) -> list[Tool] | None:
        """Get available tools for this brick.

        Args:
            conversation: Conversation object.

        Returns:
            List of tools with the keyboard tool's key enum filtered to
            the host operating system's supported keys.
        """
        self._logger.debug("get_tools_started", conversation_id=str(conversation.id))

        allowed_key_values = sorted(key.value for key in self._system_access.allowed_keys)

        tools = [
            Tool(
                name=self._tool_take_screenshot,
                description=(
                    "Capture a screenshot of one connected screen and return it as an image."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "screen_id": {
                            "type": "integer",
                            "description": "Screen id from the screens list in the prompt.",
                            "minimum": 1,
                        },
                    },
                    "required": ["screen_id"],
                },
            ),
            Tool(
                name=self._tool_press_keyboard_keys,
                description=(
                    "Simulate a virtual keyboard key press. SAME_TIME holds all keys "
                    "down then releases them (use for shortcuts like Cmd+Shift+T). "
                    "SUCCESSIVE presses each key in sequence with a short delay. "
                    "Character keys are translated against the current keyboard layout, "
                    "so 'A' produces the user's 'a' even on AZERTY. The keys enum is "
                    "filtered to those supported by the host operating system."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": allowed_key_values,
                            },
                            "description": "Ordered list of keys to press.",
                            "minItems": 1,
                        },
                        "kind": {
                            "type": "string",
                            "enum": [member.value for member in PressKind],
                            "description": "SAME_TIME for shortcuts, SUCCESSIVE for sequences.",
                        },
                    },
                    "required": ["keys", "kind"],
                },
            ),
            Tool(
                name=self._tool_type_unicode_text,
                description=(
                    "Type a literal Unicode string into whatever currently has keyboard "
                    "focus. Bypasses keyboard layout entirely; supports emojis, accented "
                    "characters and any Unicode content. Use this instead of "
                    "press_keyboard_keys when you need to enter free-form text."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Unicode text to type.",
                        },
                    },
                    "required": ["text"],
                },
            ),
            Tool(
                name=self._tool_click_pointer,
                description=(
                    "Click a mouse button at the current pointer position. The pointer "
                    "is NOT moved by this tool; move it first if needed. Use count=1 for "
                    "a single click, 2 for a double-click, 3 for a triple-click. The OS "
                    "is told these are multi-clicks so apps that distinguish double-click "
                    "behavior (open, select word, etc.) react correctly."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "button": {
                            "type": "string",
                            "enum": [member.value for member in MouseButton],
                            "description": "Which mouse button to click.",
                        },
                        "count": {
                            "type": "integer",
                            "description": "Number of clicks (1 = single, 2 = double, 3 = triple).",
                            "minimum": 1,
                        },
                    },
                    "required": ["button", "count"],
                },
            ),
            Tool(
                name=self._tool_move_pointer_coordinates,
                description=(
                    "Move the pointer to a point of the screenshot you are looking at. Give "
                    "the pixel size of that screenshot image and the target point inside it, "
                    "origin at the top-left corner. Take a screenshot afterwards if you need "
                    "to verify the position."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "screen_id": {
                            "type": "integer",
                            "description": "Screen id from the screens list in the prompt.",
                            "minimum": 1,
                        },
                        "image_width": {
                            "type": "integer",
                            "description": "Width in pixels of the screenshot image you are looking at.",
                            "minimum": 1,
                        },
                        "image_height": {
                            "type": "integer",
                            "description": "Height in pixels of the screenshot image you are looking at.",
                            "minimum": 1,
                        },
                        "x": {
                            "type": "integer",
                            "description": "Target x in pixels of that screenshot image.",
                            "minimum": 0,
                        },
                        "y": {
                            "type": "integer",
                            "description": "Target y in pixels of that screenshot image.",
                            "minimum": 0,
                        },
                    },
                    "required": ["screen_id", "image_width", "image_height", "x", "y"],
                },
            ),
            Tool(
                name=self._tool_move_pointer_description,
                description=(
                    "Move the pointer onto a UI element located from your description by a "
                    "separate vision model. Use it when move_pointer_coordinates missed the "
                    "target. Take a screenshot afterwards if you need to verify the position."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "screen_id": {
                            "type": "integer",
                            "description": "Screen id from the screens list in the prompt.",
                            "minimum": 1,
                        },
                        "element_description": {
                            "type": "string",
                            "description": (
                                "Visual description (20-60 words, in English) of the element to "
                                "locate, for a vision model that has no context about your task: "
                                'the exact text displayed between quotes "...", colors, shape, '
                                "and position relative to nearby elements. Describe what it looks "
                                "like, never what you intend to do with it."
                            ),
                        },
                    },
                    "required": ["screen_id", "element_description"],
                },
            ),
        ]

        self._logger.debug(
            "get_tools_completed",
            conversation_id=str(conversation.id),
            tool_count=len(tools),
            allowed_key_count=len(allowed_key_values),
        )

        return tools

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
            Tool response.

        Raises:
            Error: If tool name is unknown or parameters are invalid.
        """
        self._logger.debug(
            "handle_tool_request_started",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        try:
            parsed_parameters = json.loads(parameters)
        except json.JSONDecodeError as exception:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid JSON parameters: {exception}",
            )

        if not isinstance(parsed_parameters, dict):
            raise Error(ErrorCode.INVALID_ARGUMENT, "Parameters must be a JSON object")

        if name == self._tool_take_screenshot:
            response = await self._handle_take_screenshot(
                parameters=parsed_parameters, conversation=conversation
            )
        elif name == self._tool_press_keyboard_keys:
            response = await self._handle_press_keyboard_keys(
                parameters=parsed_parameters, conversation=conversation
            )
        elif name == self._tool_type_unicode_text:
            response = await self._handle_type_unicode_text(
                parameters=parsed_parameters, conversation=conversation
            )
        elif name == self._tool_click_pointer:
            response = await self._handle_click_pointer(
                parameters=parsed_parameters, conversation=conversation
            )
        elif name == self._tool_move_pointer_coordinates:
            response = await self._handle_move_pointer_coordinates(
                parameters=parsed_parameters, conversation=conversation
            )
        elif name == self._tool_move_pointer_description:
            response = await self._handle_move_pointer_description(
                parameters=parsed_parameters, conversation=conversation
            )
        else:
            raise Error(ErrorCode.NOT_FOUND, f"Unknown tool: {name}")

        self._logger.debug(
            "handle_tool_request_completed",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        return response

    async def _handle_take_screenshot(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Capture, resize, persist a screenshot and return its blob key.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response containing the blob key of the saved screenshot.

        Raises:
            Error: If parameters are invalid or the capture fails.
        """
        screen_id = self._read_screen_id(parameters=parameters)

        self._logger.info(
            "take_screenshot_started",
            conversation_id=str(conversation.id),
            screen_id=screen_id,
        )

        blob_key = await self._capture_and_save_screenshot(
            screen_id=screen_id, with_pointer_overlay=True
        )

        self._logger.info(
            "take_screenshot_completed",
            conversation_id=str(conversation.id),
            screen_id=screen_id,
            blob_key=blob_key,
        )

        return MessageContentToolResponse(image_file_keys=[blob_key])

    async def _handle_press_keyboard_keys(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Press a sequence of keys, either together or successively.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response confirming the action.

        Raises:
            Error: If parameters are invalid or keys cannot be produced.
        """
        keys = self._read_keys(parameters=parameters)
        kind = self._read_press_kind(parameters=parameters)

        self._logger.info(
            "press_keyboard_keys_started",
            conversation_id=str(conversation.id),
            keys=[key.value for key in keys],
            kind=kind.value,
        )

        if kind == PressKind.SAME_TIME:
            await self._system_access.press_keys_together(keys, self._event_tag)
        elif kind == PressKind.SUCCESSIVE:
            for index, key in enumerate(keys):
                if index > 0:
                    await asyncio.sleep(self._successive_press_delay_seconds)
                await self._system_access.tap_key(key, self._event_tag)
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported press kind: {kind.value}")

        self._logger.info(
            "press_keyboard_keys_completed",
            conversation_id=str(conversation.id),
            keys=[key.value for key in keys],
            kind=kind.value,
        )

        return MessageContentToolResponse(text=json.dumps({"pressed": True}))

    async def _handle_type_unicode_text(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Type a literal Unicode string.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response confirming the action.

        Raises:
            Error: If parameters are invalid.
        """
        text = self._read_text(parameters=parameters)

        self._logger.info(
            "type_unicode_text_started",
            conversation_id=str(conversation.id),
            text_length=len(text),
        )

        await self._system_access.type_text(text, self._event_tag)

        self._logger.info(
            "type_unicode_text_completed",
            conversation_id=str(conversation.id),
            text_length=len(text),
        )

        return MessageContentToolResponse(text=json.dumps({"typed": True}))

    async def _handle_click_pointer(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Click a mouse button at the current pointer position.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response confirming the action.

        Raises:
            Error: If parameters are invalid or the click fails.
        """
        button = self._read_mouse_button(parameters=parameters)
        count = self._read_click_count(parameters=parameters)

        self._logger.info(
            "click_pointer_started",
            conversation_id=str(conversation.id),
            button=button.value,
            count=count,
        )

        await self._system_access.click_pointer(
            button=button, count=count, event_tag=self._event_tag
        )

        self._logger.info(
            "click_pointer_completed",
            conversation_id=str(conversation.id),
            button=button.value,
            count=count,
        )

        return MessageContentToolResponse(text=json.dumps({"clicked": True}))

    async def _handle_move_pointer_coordinates(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Move the pointer to a point given in the agent's screenshot image space.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response confirming the move.

        Raises:
            Error: If parameters are invalid or any step fails.
        """
        screen_id = self._read_screen_id(parameters=parameters)
        image_width = self._read_positive_int(parameters=parameters, key="image_width")
        image_height = self._read_positive_int(parameters=parameters, key="image_height")
        x = self._read_non_negative_int(parameters=parameters, key="x")
        y = self._read_non_negative_int(parameters=parameters, key="y")

        self._logger.info(
            "move_pointer_coordinates_started",
            conversation_id=str(conversation.id),
            screen_id=screen_id,
            image_width=image_width,
            image_height=image_height,
            x=x,
            y=y,
        )

        capture = await self._system_access.capture_screen(screen_id=screen_id)
        await self._move_pointer_to_ratio(
            screen_id=screen_id,
            capture=capture,
            ratio_x=x / image_width,
            ratio_y=y / image_height,
        )

        self._logger.info(
            "move_pointer_coordinates_completed",
            conversation_id=str(conversation.id),
            screen_id=screen_id,
        )

        return MessageContentToolResponse(text=json.dumps({"moved": True}))

    async def _handle_move_pointer_description(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Locate an element through the configured vision model, then move the pointer.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response confirming the move, or a text explaining that the vision
            model could not locate the element.

        Raises:
            Error: If parameters are invalid or any step fails.
        """
        screen_id = self._read_screen_id(parameters=parameters)
        element_description = self._read_element_description(parameters=parameters)

        self._logger.info(
            "move_pointer_description_started",
            conversation_id=str(conversation.id),
            screen_id=screen_id,
            element_description_length=len(element_description),
        )

        capture = await self._system_access.capture_screen(screen_id=screen_id)
        ratio = await self._locate_element_via_vision(
            capture=capture, element_description=element_description
        )

        if ratio is None:
            self._logger.info(
                "move_pointer_description_completed",
                conversation_id=str(conversation.id),
                screen_id=screen_id,
                found=False,
            )
            return MessageContentToolResponse(text=self._vision_not_found_message)

        await self._move_pointer_to_ratio(
            screen_id=screen_id, capture=capture, ratio_x=ratio[0], ratio_y=ratio[1]
        )

        self._logger.info(
            "move_pointer_description_completed",
            conversation_id=str(conversation.id),
            screen_id=screen_id,
            found=True,
        )

        return MessageContentToolResponse(text=json.dumps({"moved": True}))

    async def _move_pointer_to_ratio(
        self, screen_id: int, capture: ScreenCapture, ratio_x: float, ratio_y: float
    ) -> None:
        """Move the pointer to a relative position of the screen.

        Args:
            screen_id: 1-based identifier returned by list_screens.
            capture: Capture of that screen, used for its pixel dimensions.
            ratio_x: Horizontal position in [0, 1] of the screen width.
            ratio_y: Vertical position in [0, 1] of the screen height.
        """
        clamped_x = min(max(ratio_x, 0.0), 1.0)
        clamped_y = min(max(ratio_y, 0.0), 1.0)
        target_x = min(round(clamped_x * capture.width), capture.width - 1)
        target_y = min(round(clamped_y * capture.height), capture.height - 1)

        self._logger.debug(
            "move_pointer_to_ratio",
            screen_id=screen_id,
            ratio_x=round(ratio_x, 4),
            ratio_y=round(ratio_y, 4),
            target_x=target_x,
            target_y=target_y,
        )

        await self._system_access.move_pointer(screen_id=screen_id, x=target_x, y=target_y)

    async def _locate_element_via_vision(
        self, capture: ScreenCapture, element_description: str
    ) -> tuple[float, float] | None:
        """Ask the configured vision model where a described element is on the capture.

        The capture is sent as a temporary blob inside a synthetic tool exchange (the
        only way images travel in message contents), and the model answers through the
        locate_element tool whose schema follows the brick configuration.

        Args:
            capture: Raw screen capture to analyze (sent without pointer overlay).
            element_description: Free-form visual description of the target.

        Returns:
            Relative position (x, y) in [0, 1] of the element, or None when not found.

        Raises:
            Error: If the vision model is missing, fails, or answers without the tool.
        """
        ui_config = self._read_ui_config()
        llm_model = await self._database.llm_models.get(
            llm_model_id=ui_config.move_pointer_llm_model_id
        )
        if llm_model is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Move pointer LLM model {ui_config.move_pointer_llm_model_id} not found",
            )

        jpeg_bytes, _, _ = await asyncio.to_thread(
            self._render_screenshot, capture, None, self._screenshot_max_edge
        )
        blob_key = await self._blob.save(
            Blob(
                content=jpeg_bytes,
                content_type=self._screenshot_content_type,
                file_name=self._build_screenshot_file_name(screen_id=0),
            )
        )

        try:
            messages: list[MessageContent] = [
                MessageContentUser(
                    text=self._build_vision_prompt(ui_config, element_description),
                    attached_file_paths=[],
                ),
                MessageContentTool(
                    name=self._tool_take_screenshot,
                    processing=False,
                    error=None,
                    request="{}",
                    response=MessageContentToolResponse(image_file_keys=[blob_key]),
                    llm_id=str(uuid4()),
                    turn_id=str(uuid4()),
                ),
            ]
            response = await self._providers.llm(
                system_prompt=None,
                messages=messages,
                tools=[self._build_vision_tool(ui_config)],
                llm_model=llm_model,
                reasoning=AgentReasoning.DEFAULT,
                verbosity=AgentVerbosity.DEFAULT,
            )
        finally:
            await self._blob.delete(blob_key)

        for content in response.contents:
            if (
                content.type == MessageContentType.TOOL
                and content.name == self._vision_tool_locate_element
            ):
                return self._parse_vision_location(ui_config, content.request)

        raise Error(
            ErrorCode.INVALID_RESPONSE,
            "Vision model did not report a location through the locate_element tool",
        )

    def _build_vision_prompt(self, ui_config: BrickConfigUI, element_description: str) -> str:
        if ui_config.move_pointer_geometry == BrickConfigUIMovePointerGeometry.POINT:
            shape = "the click point of the element as x, y"
        else:
            shape = (
                "the bounding box of the element as x1, y1 (top-left corner) and "
                "x2, y2 (bottom-right corner)"
            )

        if (
            ui_config.move_pointer_coordinate_space
            == BrickConfigUIMovePointerCoordinateSpace.PIXELS
        ):
            space = (
                "in pixel coordinates of this image, origin at the top-left corner, together "
                "with the width and height of the image in pixels"
            )
        else:
            space = (
                f"on a 0 to {self._vision_normalized_scale} scale on each axis, where 0 is the "
                f"left or top edge and {self._vision_normalized_scale} the right or bottom edge"
            )

        return (
            "Locate the UI element described below in the screenshot. Answer only by calling "
            f"the {self._vision_tool_locate_element} tool. Report {shape} {space}. If the "
            "element is not visible, report found as false.\n\n"
            f"Element description:\n{element_description}"
        )

    def _build_vision_tool(self, ui_config: BrickConfigUI) -> Tool:
        properties: dict[str, object] = {
            "found": {
                "type": "boolean",
                "description": "Whether the described element is visible in the image.",
            }
        }
        if (
            ui_config.move_pointer_coordinate_space
            == BrickConfigUIMovePointerCoordinateSpace.PIXELS
        ):
            properties["width"] = {"type": "integer", "description": "Image width in pixels."}
            properties["height"] = {"type": "integer", "description": "Image height in pixels."}
        if ui_config.move_pointer_geometry == BrickConfigUIMovePointerGeometry.POINT:
            properties["x"] = {"type": "integer"}
            properties["y"] = {"type": "integer"}
        else:
            properties["x1"] = {"type": "integer"}
            properties["y1"] = {"type": "integer"}
            properties["x2"] = {"type": "integer"}
            properties["y2"] = {"type": "integer"}

        return Tool(
            name=self._vision_tool_locate_element,
            description="Report whether the described UI element is visible and where it is.",
            parameters_schema={
                "type": "object",
                "properties": properties,
                "required": list(properties.keys()),
            },
        )

    def _parse_vision_location(
        self, ui_config: BrickConfigUI, request: str
    ) -> tuple[float, float] | None:
        try:
            payload = json.loads(request)
        except json.JSONDecodeError as exception:
            raise Error(
                ErrorCode.INVALID_RESPONSE, f"Vision model returned invalid JSON: {exception}"
            )
        if not isinstance(payload, dict):
            raise Error(ErrorCode.INVALID_RESPONSE, "Vision model location must be a JSON object")

        found = payload.get("found")
        if not isinstance(found, bool):
            raise Error(ErrorCode.INVALID_RESPONSE, "Vision model location is missing found")
        if not found:
            return None

        if ui_config.move_pointer_geometry == BrickConfigUIMovePointerGeometry.POINT:
            x = self._read_vision_number(payload, "x")
            y = self._read_vision_number(payload, "y")
        else:
            x = (
                self._read_vision_number(payload, "x1") + self._read_vision_number(payload, "x2")
            ) / 2
            y = (
                self._read_vision_number(payload, "y1") + self._read_vision_number(payload, "y2")
            ) / 2

        if (
            ui_config.move_pointer_coordinate_space
            == BrickConfigUIMovePointerCoordinateSpace.PIXELS
        ):
            width = self._read_vision_number(payload, "width")
            height = self._read_vision_number(payload, "height")
            if width <= 0 or height <= 0:
                raise Error(
                    ErrorCode.INVALID_RESPONSE, "Vision model reported a non-positive image size"
                )
            return x / width, y / height

        return x / self._vision_normalized_scale, y / self._vision_normalized_scale

    def _read_vision_number(self, payload: dict[str, object], key: str) -> float:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Error(ErrorCode.INVALID_RESPONSE, f"Vision model location is missing {key}")
        return float(value)

    def _read_ui_config(self) -> BrickConfigUI:
        if self._config.type != BrickConfigType.UI:
            raise Error(ErrorCode.INTERNAL, f"Unexpected brick config type: {self._config.type}")
        return self._config

    def _format_screen_entry(self, screen: Screen) -> str:
        if screen.is_primary:
            return f"[{screen.id}]{self._primary_label}"
        return f"[{screen.id}]"

    def _read_screen_id(self, parameters: dict[str, object]) -> int:
        raw_screen_id = parameters.get("screen_id")
        if (
            not isinstance(raw_screen_id, int)
            or isinstance(raw_screen_id, bool)
            or raw_screen_id < 1
        ):
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: screen_id",
            )
        return raw_screen_id

    def _read_positive_int(self, parameters: dict[str, object], key: str) -> int:
        raw_value = parameters.get(key)
        if not isinstance(raw_value, int) or isinstance(raw_value, bool) or raw_value < 1:
            raise Error(ErrorCode.INVALID_ARGUMENT, f"Missing or invalid required parameter: {key}")
        return raw_value

    def _read_non_negative_int(self, parameters: dict[str, object], key: str) -> int:
        raw_value = parameters.get(key)
        if not isinstance(raw_value, int) or isinstance(raw_value, bool) or raw_value < 0:
            raise Error(ErrorCode.INVALID_ARGUMENT, f"Missing or invalid required parameter: {key}")
        return raw_value

    def _read_keys(self, parameters: dict[str, object]) -> list[Key]:
        raw_keys = parameters.get("keys")
        if not isinstance(raw_keys, list) or not raw_keys:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: keys",
            )

        keys: list[Key] = []
        for raw_key in raw_keys:
            if not isinstance(raw_key, str):
                raise Error(
                    ErrorCode.INVALID_ARGUMENT,
                    "Each entry in keys must be a string",
                )
            try:
                key = Key(raw_key)
            except ValueError:
                raise Error(ErrorCode.INVALID_ARGUMENT, f"Unknown key: {raw_key}")
            keys.append(key)
        return keys

    def _read_press_kind(self, parameters: dict[str, object]) -> PressKind:
        raw_kind = parameters.get("kind")
        if not isinstance(raw_kind, str):
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: kind",
            )
        try:
            return PressKind(raw_kind)
        except ValueError:
            raise Error(ErrorCode.INVALID_ARGUMENT, f"Unknown press kind: {raw_kind}")

    def _read_text(self, parameters: dict[str, object]) -> str:
        raw_text = parameters.get("text")
        if not isinstance(raw_text, str) or not raw_text:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: text",
            )
        return raw_text

    def _read_mouse_button(self, parameters: dict[str, object]) -> MouseButton:
        raw_button = parameters.get("button")
        if not isinstance(raw_button, str):
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: button",
            )
        try:
            return MouseButton(raw_button)
        except ValueError:
            raise Error(ErrorCode.INVALID_ARGUMENT, f"Unknown mouse button: {raw_button}")

    def _read_click_count(self, parameters: dict[str, object]) -> int:
        raw_count = parameters.get("count")
        if not isinstance(raw_count, int) or isinstance(raw_count, bool) or raw_count < 1:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: count",
            )
        return raw_count

    def _read_element_description(self, parameters: dict[str, object]) -> str:
        raw_description = parameters.get("element_description")
        if not isinstance(raw_description, str) or not raw_description.strip():
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: element_description",
            )
        return raw_description.strip()

    async def _capture_and_save_screenshot(self, screen_id: int, with_pointer_overlay: bool) -> str:
        """Capture the screen, optionally overlay pointer, persist as a blob.

        Args:
            screen_id: 1-based identifier returned by list_screens.
            with_pointer_overlay: When True, the brick's cursor icon is
                composited at the current pointer location (if the
                pointer is on this screen).

        Returns:
            The blob key for the saved JPEG.
        """
        capture = await self._system_access.capture_screen(screen_id=screen_id)
        if with_pointer_overlay:
            pointer_position = await self._system_access.get_pointer_position(screen_id=screen_id)
        else:
            pointer_position = None

        jpeg_bytes, _, _ = await asyncio.to_thread(
            self._render_screenshot, capture, pointer_position, self._screenshot_max_edge
        )

        return await self._blob.save(
            Blob(
                content=jpeg_bytes,
                content_type=self._screenshot_content_type,
                file_name=self._build_screenshot_file_name(screen_id=screen_id),
            )
        )

    def _render_screenshot(
        self, capture: ScreenCapture, pointer_position: PointerPosition | None, max_edge: int
    ) -> tuple[bytes, tuple[int, int], tuple[int, int]]:
        """Build the Pillow image, optionally overlay cursor, resize, encode JPEG.

        Args:
            capture: ScreenCapture from system_access.
            pointer_position: Pointer position in source-pixel coordinates,
                or None if the pointer is on a different display.
            max_edge: Maximum length of the longest edge after resizing.

        Returns:
            Tuple (jpeg_bytes, original_size, final_size).
        """
        image = Image.frombytes("RGB", (capture.width, capture.height), capture.bgra, "raw", "BGRX")
        original_size = image.size

        if pointer_position is not None:
            image = self._overlay_cursor(image=image, pointer_position=pointer_position)

        if max(image.size) > max_edge:
            image.thumbnail(
                (max_edge, max_edge),
                Image.Resampling.LANCZOS,
            )
        final_size = image.size

        buffer = BytesIO()
        image.save(buffer, format=self._screenshot_format, quality=self._screenshot_quality)
        return buffer.getvalue(), original_size, final_size

    def _overlay_cursor(self, image: Image.Image, pointer_position: PointerPosition) -> Image.Image:
        """Composite the cursor icon at the pointer position.

        The icon is sized to 5% of the image's shorter side. The dark
        or light variant is chosen based on the average luminance of
        the area underneath the cursor, matching the desktop app's behavior.

        Args:
            image: Source RGB screenshot at native resolution.
            pointer_position: Pointer position in source-pixel coordinates.

        Returns:
            New RGB image with the cursor composited at the pointer position.
        """
        marker_side = max(1, int(min(image.width, image.height) * self._cursor_marker_fraction))

        cursor_image = self._select_cursor_image(
            image=image, pointer_position=pointer_position, marker_side=marker_side
        )
        resized_cursor = cursor_image.resize((marker_side, marker_side), Image.Resampling.LANCZOS)

        clamped_x = max(0, min(pointer_position.x, image.width - 1))
        clamped_y = max(0, min(pointer_position.y, image.height - 1))

        composite = image.convert("RGBA")
        composite.alpha_composite(resized_cursor, dest=(clamped_x, clamped_y))
        return composite.convert("RGB")

    def _select_cursor_image(
        self, image: Image.Image, pointer_position: PointerPosition, marker_side: int
    ) -> Image.Image:
        """Pick the dark or light cursor icon based on local luminance.

        Args:
            image: Source RGB screenshot.
            pointer_position: Pointer position in source-pixel coordinates.
            marker_side: Side length of the cursor marker in pixels.

        Returns:
            The cursor Pillow image (dark for bright backgrounds, light
            for dark backgrounds).
        """
        sample_side = max(4, int(marker_side * 1.5))
        half = sample_side // 2

        sample_min_x = max(0, pointer_position.x - half)
        sample_min_y = max(0, pointer_position.y - half)
        sample_max_x = min(image.width, sample_min_x + sample_side)
        sample_max_y = min(image.height, sample_min_y + sample_side)

        sample = image.crop((sample_min_x, sample_min_y, sample_max_x, sample_max_y))
        sample_pixel = sample.resize((1, 1), Image.Resampling.LANCZOS).convert("RGB")
        pixel_value = sample_pixel.getpixel((0, 0))
        if not isinstance(pixel_value, tuple) or len(pixel_value) < 3:
            raise Error(
                ErrorCode.INTERNAL, "Cursor luminance sample returned unexpected pixel format"
            )
        red, green, blue = pixel_value[0], pixel_value[1], pixel_value[2]

        luminance = (
            self._cursor_luminance_red_coefficient * red
            + self._cursor_luminance_green_coefficient * green
            + self._cursor_luminance_blue_coefficient * blue
        ) / 255.0

        if luminance > self._cursor_luminance_threshold:
            return self._cursor_dark_image
        return self._cursor_light_image

    def _load_cursor_image(self, asset_name: str) -> Image.Image:
        """Load a bundled cursor PNG as an RGBA Pillow image.

        Args:
            asset_name: File name inside the cursor assets package.

        Returns:
            Cursor image with an alpha channel.

        Raises:
            Error: If the asset cannot be loaded.
        """
        try:
            asset_path = resources.files(self._cursor_assets_package).joinpath(asset_name)
            with resources.as_file(asset_path) as path:
                return Image.open(path).convert("RGBA")
        except Exception as exception:
            raise Error(
                ErrorCode.INTERNAL,
                f"Failed to load cursor asset {asset_name}: {exception}",
            )

    def _build_screenshot_file_name(self, screen_id: int) -> str:
        """Compose a descriptive screenshot file name.

        Args:
            screen_id: 1-based screen identifier.

        Returns:
            File name like 'screenshot_1_2026-05-23T14-23-07.jpg'.
        """
        timestamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H-%M-%S")
        return f"screenshot_{screen_id}_{timestamp}.{self._screenshot_file_extension}"
