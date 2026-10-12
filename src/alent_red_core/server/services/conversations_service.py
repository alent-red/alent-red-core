import asyncio
import grpc
from typing import AsyncIterator
from uuid import UUID
from google.protobuf.timestamp_pb2 import Timestamp
from ...common import Logger
from ...generated.proto.conversations import services_pb2_grpc, messages_pb2
from ...database import Database
from ...looper import Looper
from ...models import Conversation, ConversationInput, ConversationSender, Error, ErrorCode
from ..utils import handle_grpc_errors, map_exception_to_error, python_error_code_to_proto


class ConversationsService(services_pb2_grpc.ConversationsServicer):
    """Conversations management service."""

    def __init__(self, database: Database, looper: Looper):
        """Initialize conversations service.

        Args:
            database: Database instance for data access.
            looper: Looper instance for pausing conversation processing.
        """
        self._database = database
        self._looper = looper
        self._logger = Logger.get_logger("server.services.conversations")

    @handle_grpc_errors
    async def GetAll(
        self,
        request: messages_pb2.GetAllConversationsRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetAllConversationsRequest, messages_pb2.GetAllConversationsResponse
        ],
    ) -> messages_pb2.GetAllConversationsResponse:
        """Get all conversations."""
        agent_id = UUID(request.agent_id) if request.HasField("agent_id") else None

        if agent_id:
            self._logger.debug("get_all_called", agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_called")

        conversations = await self._database.conversations.get_all(agent_id)

        if agent_id:
            self._logger.debug(
                "get_all_completed", count=len(conversations), agent_id=str(agent_id)
            )
        else:
            self._logger.debug("get_all_completed", count=len(conversations))

        proto_conversations = [
            self._python_conversation_to_proto(conversation) for conversation in conversations
        ]

        return messages_pb2.GetAllConversationsResponse(conversations=proto_conversations)

    @handle_grpc_errors
    async def Get(
        self,
        request: messages_pb2.GetConversationRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetConversationRequest, messages_pb2.GetConversationResponse
        ],
    ) -> messages_pb2.GetConversationResponse:
        """Get conversation by ID."""
        conversation_id = UUID(request.id)
        self._logger.debug("get_called", conversation_id=str(conversation_id))

        conversation = await self._database.conversations.get(conversation_id)

        if not conversation:
            raise Error(ErrorCode.NOT_FOUND, "Conversation not found")

        self._logger.debug("get_completed", conversation_id=str(conversation_id))

        return messages_pb2.GetConversationResponse(
            conversation=self._python_conversation_to_proto(conversation)
        )

    @handle_grpc_errors
    async def Save(
        self,
        request: messages_pb2.SaveConversationRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SaveConversationRequest, messages_pb2.SaveConversationResponse
        ],
    ) -> messages_pb2.SaveConversationResponse:
        """Save conversation (create or update)."""
        conversation_id = UUID(request.id) if request.HasField("id") else None

        if conversation_id:
            self._logger.debug("save_called", conversation_id=str(conversation_id), mode="update")

            existing_conversation = await self._database.conversations.get(conversation_id)
            if not existing_conversation:
                raise Error(ErrorCode.NOT_FOUND, "Conversation not found")

            conversation_input = ConversationInput(
                name=(request.conversation.name if request.conversation.HasField("name") else None),
                agent_id=UUID(request.conversation.agent_id),
                processing=False,
                error_code=None,
                error_message=None,
                context_tokens_count=existing_conversation.context_tokens_count,
                gateway_id=existing_conversation.gateway_id,
                gateway_external_id=existing_conversation.gateway_external_id,
                sender=existing_conversation.sender,
            )
        else:
            self._logger.debug("save_called", mode="create")

            conversation_input = ConversationInput(
                name=(request.conversation.name if request.conversation.HasField("name") else None),
                agent_id=UUID(request.conversation.agent_id),
                processing=False,
                error_code=None,
                error_message=None,
                context_tokens_count=None,
                gateway_id=None,
                gateway_external_id=None,
                sender=None,
            )

        conversation = await self._database.conversations.save(conversation_input, conversation_id)

        if conversation_id:
            self._logger.debug(
                "save_completed", conversation_id=str(conversation.id), mode="update"
            )
        else:
            self._logger.debug(
                "save_completed", conversation_id=str(conversation.id), mode="create"
            )

        return messages_pb2.SaveConversationResponse(
            conversation=self._python_conversation_to_proto(conversation)
        )

    @handle_grpc_errors
    async def Delete(
        self,
        request: messages_pb2.DeleteConversationRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.DeleteConversationRequest, messages_pb2.DeleteConversationResponse
        ],
    ) -> messages_pb2.DeleteConversationResponse:
        """Delete conversation by ID."""
        conversation_id = UUID(request.id)
        self._logger.debug("delete_called", conversation_id=str(conversation_id))

        await self._database.conversations.delete(conversation_id)

        self._logger.debug("delete_completed", conversation_id=str(conversation_id))

        return messages_pb2.DeleteConversationResponse()

    @handle_grpc_errors
    async def Split(
        self,
        request: messages_pb2.SplitConversationRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SplitConversationRequest, messages_pb2.SplitConversationResponse
        ],
    ) -> messages_pb2.SplitConversationResponse:
        """Split conversation at a specific message."""
        split_at_message_id = UUID(request.split_at_message_id)
        self._logger.debug("split_called", split_at_message_id=str(split_at_message_id))

        new_conversation = await self._database.conversations.split(split_at_message_id)

        self._logger.debug(
            "split_completed",
            split_at_message_id=str(split_at_message_id),
            new_conversation_id=str(new_conversation.id),
        )

        return messages_pb2.SplitConversationResponse(
            conversation=self._python_conversation_to_proto(new_conversation)
        )

    @handle_grpc_errors
    async def Pause(
        self,
        request: messages_pb2.PauseConversationRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.PauseConversationRequest, messages_pb2.PauseConversationResponse
        ],
    ) -> messages_pb2.PauseConversationResponse:
        """Pause an in-progress conversation processing."""
        conversation_id = UUID(request.id)
        self._logger.debug("pause_called", conversation_id=str(conversation_id))

        conversation = await self._database.conversations.get(conversation_id)
        if not conversation:
            raise Error(ErrorCode.NOT_FOUND, "Conversation not found")

        await self._looper.pause(conversation)

        self._logger.debug("pause_completed", conversation_id=str(conversation_id))

        return messages_pb2.PauseConversationResponse()

    async def WatchSaves(
        self,
        request: messages_pb2.WatchConversationSavesRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.WatchConversationSavesRequest,
            messages_pb2.WatchConversationSavesResponse,
        ],
    ) -> AsyncIterator[messages_pb2.WatchConversationSavesResponse]:
        """Stream conversation create and update events."""
        try:
            conversation_id = (
                UUID(request.conversation_id) if request.HasField("conversation_id") else None
            )

            if conversation_id:
                self._logger.debug("watch_saves_called", conversation_id=str(conversation_id))
            else:
                self._logger.debug("watch_saves_called")

            async for conversation in self._database.conversations.bus.watch_saves(conversation_id):
                yield messages_pb2.WatchConversationSavesResponse(
                    conversation=self._python_conversation_to_proto(conversation)
                )
        except asyncio.CancelledError:
            raise
        except Exception as exception:
            status_code, error_code, error_message = map_exception_to_error(exception)
            trailing_metadata: tuple[tuple[str, str], ...] = (("error-code", error_code.value),)
            if error_message is not None:
                trailing_metadata = trailing_metadata + (("error-message", error_message),)
            await context.abort(
                code=status_code,
                details="Operation failed",
                trailing_metadata=trailing_metadata,
            )

    async def WatchDeletions(
        self,
        request: messages_pb2.WatchConversationDeletionsRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.WatchConversationDeletionsRequest,
            messages_pb2.WatchConversationDeletionsResponse,
        ],
    ) -> AsyncIterator[messages_pb2.WatchConversationDeletionsResponse]:
        """Stream conversation delete events."""
        try:
            self._logger.debug("watch_deletions_called")

            async for conversation_id in self._database.conversations.bus.watch_deletions():
                yield messages_pb2.WatchConversationDeletionsResponse(id=str(conversation_id))
        except asyncio.CancelledError:
            raise
        except Exception as exception:
            status_code, error_code, error_message = map_exception_to_error(exception)
            trailing_metadata: tuple[tuple[str, str], ...] = (("error-code", error_code.value),)
            if error_message is not None:
                trailing_metadata = trailing_metadata + (("error-message", error_message),)
            await context.abort(
                code=status_code,
                details="Operation failed",
                trailing_metadata=trailing_metadata,
            )

    def _python_conversation_to_proto(
        self, python_conversation: Conversation
    ) -> messages_pb2.Conversation:
        """Convert Python Conversation to proto Conversation."""
        created_at = Timestamp()
        created_at.FromDatetime(python_conversation.created_at)

        updated_at = Timestamp()
        updated_at.FromDatetime(python_conversation.updated_at)

        proto_conversation = messages_pb2.Conversation(
            id=str(python_conversation.id),
            created_at=created_at,
            updated_at=updated_at,
            processing=python_conversation.processing,
        )

        if python_conversation.name is not None:
            proto_conversation.name = python_conversation.name

        if python_conversation.error_code is not None:
            proto_conversation.error_code = python_error_code_to_proto(
                python_error_code=python_conversation.error_code
            )

        if python_conversation.error_message is not None:
            proto_conversation.error_message = python_conversation.error_message

        if python_conversation.agent_id is not None:
            proto_conversation.agent_id = str(python_conversation.agent_id)

        if python_conversation.context_tokens_count is not None:
            proto_conversation.context_tokens_count = python_conversation.context_tokens_count

        if python_conversation.gateway_id is not None:
            proto_conversation.gateway_id = str(python_conversation.gateway_id)

        if python_conversation.gateway_external_id is not None:
            proto_conversation.gateway_external_id = python_conversation.gateway_external_id

        if python_conversation.sender is not None:
            proto_conversation.sender.CopyFrom(
                self._python_sender_to_proto(python_conversation.sender)
            )

        return proto_conversation

    def _python_sender_to_proto(
        self, python_sender: ConversationSender
    ) -> messages_pb2.ConversationSender:
        """Convert Python ConversationSender to proto ConversationSender."""
        proto_sender = messages_pb2.ConversationSender()

        if python_sender.name is not None:
            proto_sender.name = python_sender.name

        if python_sender.user_name is not None:
            proto_sender.user_name = python_sender.user_name

        if python_sender.picture_file_key is not None:
            proto_sender.picture_file_key = python_sender.picture_file_key

        return proto_sender
