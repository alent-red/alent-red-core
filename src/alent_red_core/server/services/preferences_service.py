import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from ...common import Logger
from ...generated.proto.preferences import services_pb2_grpc, messages_pb2
from ...database import Database
from ...looper import Looper
from ...gateways import GatewayManager
from ...models import (
    PreferenceKey,
    PreferenceValueString,
    PreferenceValueInt,
    PreferenceValueFloat,
    PreferenceValueBool,
    PreferenceValueType,
    PreferenceInput,
    Preference,
)
from ..utils import handle_grpc_errors


class PreferencesService(services_pb2_grpc.PreferencesServicer):
    """Preferences management service."""

    def __init__(self, database: Database, looper: Looper, gateways: GatewayManager):
        """Initialize preferences service.

        Args:
            database: Database instance for data access.
            looper: Looper instance for triggering refresh on changes.
            gateways: Gateway manager instance for triggering refresh on changes.
        """
        self._database = database
        self._looper = looper
        self._gateways = gateways
        self._logger = Logger.get_logger("server.services.preferences")

    @handle_grpc_errors
    async def GetAll(
        self,
        request: messages_pb2.GetAllPreferencesRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetAllPreferencesRequest, messages_pb2.GetAllPreferencesResponse
        ],
    ) -> messages_pb2.GetAllPreferencesResponse:
        """Get all preferences."""
        self._logger.debug("get_all_called")

        preferences = await self._database.preferences.get_all()

        self._logger.debug("get_all_completed", count=len(preferences))

        proto_preferences = [
            self._python_preference_to_proto(preference) for preference in preferences
        ]

        return messages_pb2.GetAllPreferencesResponse(preferences=proto_preferences)

    @handle_grpc_errors
    async def SaveMany(
        self,
        request: messages_pb2.SaveManyPreferencesRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SaveManyPreferencesRequest, messages_pb2.SaveManyPreferencesResponse
        ],
    ) -> messages_pb2.SaveManyPreferencesResponse:
        """Save multiple preferences (upsert)."""
        self._logger.debug("save_many_called", count=len(request.preferences))

        preference_inputs = [
            PreferenceInput(
                key=self._proto_key_to_python(proto_preference.key),
                value=self._proto_value_to_python(proto_preference.value),
            )
            for proto_preference in request.preferences
        ]

        preferences = await self._database.preferences.save_many(
            preference_inputs, skip_existing=False
        )

        await self._looper.refresh()
        await self._gateways.refresh()

        self._logger.debug("save_many_completed", saved_count=len(preferences))

        proto_preferences = [
            self._python_preference_to_proto(preference) for preference in preferences
        ]

        return messages_pb2.SaveManyPreferencesResponse(preferences=proto_preferences)

    def _proto_key_to_python(self, proto_key: int) -> PreferenceKey:
        """Convert proto PreferenceKey enum to Python enum."""
        if proto_key == messages_pb2.PREFERENCE_KEY_SYSTEM_PROMPT:
            return PreferenceKey.SYSTEM_PROMPT
        elif proto_key == messages_pb2.PREFERENCE_KEY_AGENT_PROMPT_PLACEHOLDER:
            return PreferenceKey.AGENT_PROMPT_PLACEHOLDER
        elif proto_key == messages_pb2.PREFERENCE_KEY_BRICK_PROMPT_PLACEHOLDER:
            return PreferenceKey.BRICK_PROMPT_PLACEHOLDER
        elif proto_key == messages_pb2.PREFERENCE_KEY_ATTACHED_FILE_PATH_PROMPT_PREFIX:
            return PreferenceKey.ATTACHED_FILE_PATH_PROMPT_PREFIX
        elif proto_key == messages_pb2.PREFERENCE_KEY_BRICK_PROMPT_SEPARATOR:
            return PreferenceKey.BRICK_PROMPT_SEPARATOR
        elif proto_key == messages_pb2.PREFERENCE_KEY_BRICK_TOOL_NAME_SEPARATOR:
            return PreferenceKey.BRICK_TOOL_NAME_SEPARATOR
        elif proto_key == messages_pb2.PREFERENCE_KEY_ATTACHED_FILE_PATH_PROMPT_SEPARATOR:
            return PreferenceKey.ATTACHED_FILE_PATH_PROMPT_SEPARATOR
        elif proto_key == messages_pb2.PREFERENCE_KEY_NO_TOOL_RESPONSE_PROMPT:
            return PreferenceKey.NO_TOOL_RESPONSE_PROMPT
        elif proto_key == messages_pb2.PREFERENCE_KEY_OPEN_AI_BASE_URL:
            return PreferenceKey.OPEN_AI_BASE_URL
        elif proto_key == messages_pb2.PREFERENCE_KEY_ANTHROPIC_BASE_URL:
            return PreferenceKey.ANTHROPIC_BASE_URL
        elif proto_key == messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_MINIMAL_BUDGET_TOKENS:
            return PreferenceKey.ANTHROPIC_REASONING_MINIMAL_BUDGET_TOKENS
        elif proto_key == messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_LOW_BUDGET_TOKENS:
            return PreferenceKey.ANTHROPIC_REASONING_LOW_BUDGET_TOKENS
        elif proto_key == messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_MEDIUM_BUDGET_TOKENS:
            return PreferenceKey.ANTHROPIC_REASONING_MEDIUM_BUDGET_TOKENS
        elif proto_key == messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_HIGH_BUDGET_TOKENS:
            return PreferenceKey.ANTHROPIC_REASONING_HIGH_BUDGET_TOKENS
        elif proto_key == messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_XHIGH_BUDGET_TOKENS:
            return PreferenceKey.ANTHROPIC_REASONING_XHIGH_BUDGET_TOKENS
        elif proto_key == messages_pb2.PREFERENCE_KEY_ANTHROPIC_CACHE_MEDIUM_TTL:
            return PreferenceKey.ANTHROPIC_CACHE_MEDIUM_TTL
        elif proto_key == messages_pb2.PREFERENCE_KEY_ANTHROPIC_CACHE_HIGH_TTL:
            return PreferenceKey.ANTHROPIC_CACHE_HIGH_TTL
        elif proto_key == messages_pb2.PREFERENCE_KEY_LLM_STREAM:
            return PreferenceKey.LLM_STREAM
        else:
            raise ValueError(f"Unknown preference key: {proto_key}")

    def _python_key_to_proto(self, python_key: PreferenceKey) -> messages_pb2.PreferenceKey:
        """Convert Python PreferenceKey enum to proto enum."""
        if python_key == PreferenceKey.SYSTEM_PROMPT:
            return messages_pb2.PREFERENCE_KEY_SYSTEM_PROMPT
        elif python_key == PreferenceKey.AGENT_PROMPT_PLACEHOLDER:
            return messages_pb2.PREFERENCE_KEY_AGENT_PROMPT_PLACEHOLDER
        elif python_key == PreferenceKey.BRICK_PROMPT_PLACEHOLDER:
            return messages_pb2.PREFERENCE_KEY_BRICK_PROMPT_PLACEHOLDER
        elif python_key == PreferenceKey.ATTACHED_FILE_PATH_PROMPT_PREFIX:
            return messages_pb2.PREFERENCE_KEY_ATTACHED_FILE_PATH_PROMPT_PREFIX
        elif python_key == PreferenceKey.BRICK_PROMPT_SEPARATOR:
            return messages_pb2.PREFERENCE_KEY_BRICK_PROMPT_SEPARATOR
        elif python_key == PreferenceKey.BRICK_TOOL_NAME_SEPARATOR:
            return messages_pb2.PREFERENCE_KEY_BRICK_TOOL_NAME_SEPARATOR
        elif python_key == PreferenceKey.ATTACHED_FILE_PATH_PROMPT_SEPARATOR:
            return messages_pb2.PREFERENCE_KEY_ATTACHED_FILE_PATH_PROMPT_SEPARATOR
        elif python_key == PreferenceKey.NO_TOOL_RESPONSE_PROMPT:
            return messages_pb2.PREFERENCE_KEY_NO_TOOL_RESPONSE_PROMPT
        elif python_key == PreferenceKey.OPEN_AI_BASE_URL:
            return messages_pb2.PREFERENCE_KEY_OPEN_AI_BASE_URL
        elif python_key == PreferenceKey.ANTHROPIC_BASE_URL:
            return messages_pb2.PREFERENCE_KEY_ANTHROPIC_BASE_URL
        elif python_key == PreferenceKey.ANTHROPIC_REASONING_MINIMAL_BUDGET_TOKENS:
            return messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_MINIMAL_BUDGET_TOKENS
        elif python_key == PreferenceKey.ANTHROPIC_REASONING_LOW_BUDGET_TOKENS:
            return messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_LOW_BUDGET_TOKENS
        elif python_key == PreferenceKey.ANTHROPIC_REASONING_MEDIUM_BUDGET_TOKENS:
            return messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_MEDIUM_BUDGET_TOKENS
        elif python_key == PreferenceKey.ANTHROPIC_REASONING_HIGH_BUDGET_TOKENS:
            return messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_HIGH_BUDGET_TOKENS
        elif python_key == PreferenceKey.ANTHROPIC_REASONING_XHIGH_BUDGET_TOKENS:
            return messages_pb2.PREFERENCE_KEY_ANTHROPIC_REASONING_XHIGH_BUDGET_TOKENS
        elif python_key == PreferenceKey.ANTHROPIC_CACHE_MEDIUM_TTL:
            return messages_pb2.PREFERENCE_KEY_ANTHROPIC_CACHE_MEDIUM_TTL
        elif python_key == PreferenceKey.ANTHROPIC_CACHE_HIGH_TTL:
            return messages_pb2.PREFERENCE_KEY_ANTHROPIC_CACHE_HIGH_TTL
        elif python_key == PreferenceKey.LLM_STREAM:
            return messages_pb2.PREFERENCE_KEY_LLM_STREAM
        else:
            raise ValueError(f"Unknown preference key: {python_key}")

    def _proto_value_to_python(
        self, proto_value: messages_pb2.PreferenceValue
    ) -> PreferenceValueString | PreferenceValueInt | PreferenceValueFloat | PreferenceValueBool:
        """Convert proto PreferenceValue to Python PreferenceValue."""
        which = proto_value.WhichOneof("value")
        if which == "string_value":
            return PreferenceValueString(value=proto_value.string_value.value)
        elif which == "int_value":
            return PreferenceValueInt(value=proto_value.int_value.value)
        elif which == "float_value":
            return PreferenceValueFloat(value=proto_value.float_value.value)
        elif which == "bool_value":
            return PreferenceValueBool(value=proto_value.bool_value.value)
        else:
            raise ValueError(f"Unknown preference value type: {which}")

    def _python_value_to_proto(
        self,
        python_value: (
            PreferenceValueString | PreferenceValueInt | PreferenceValueFloat | PreferenceValueBool
        ),
    ) -> messages_pb2.PreferenceValue:
        """Convert Python PreferenceValue to proto PreferenceValue."""
        if python_value.type == PreferenceValueType.STRING:
            return messages_pb2.PreferenceValue(
                string_value=messages_pb2.PreferenceValueString(value=python_value.value)
            )
        elif python_value.type == PreferenceValueType.INT:
            return messages_pb2.PreferenceValue(
                int_value=messages_pb2.PreferenceValueInt(value=python_value.value)
            )
        elif python_value.type == PreferenceValueType.FLOAT:
            return messages_pb2.PreferenceValue(
                float_value=messages_pb2.PreferenceValueFloat(value=python_value.value)
            )
        elif python_value.type == PreferenceValueType.BOOL:
            return messages_pb2.PreferenceValue(
                bool_value=messages_pb2.PreferenceValueBool(value=python_value.value)
            )
        else:
            raise ValueError(f"Unknown preference value type: {python_value.type}")

    def _python_preference_to_proto(self, python_preference: Preference) -> messages_pb2.Preference:
        """Convert Python Preference to proto Preference."""
        created_at = Timestamp()
        created_at.FromDatetime(python_preference.created_at)

        updated_at = Timestamp()
        updated_at.FromDatetime(python_preference.updated_at)

        return messages_pb2.Preference(
            id=str(python_preference.id),
            created_at=created_at,
            updated_at=updated_at,
            key=self._python_key_to_proto(python_preference.key),
            value=self._python_value_to_proto(python_preference.value),
        )
