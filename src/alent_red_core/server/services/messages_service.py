import asyncio
import grpc
from typing import AsyncIterator
from uuid import UUID
from google.protobuf.timestamp_pb2 import Timestamp
from ...common import Logger
from ...generated.proto.messages import services_pb2_grpc, messages_pb2
from ...database import Database
from ...looper import Looper
from ...models import (
    ConversationInput,
    Message,
    MessageInput,
    MessageContent,
    MessageContentUser,
    MessageContentType,
    Error,
    ErrorCode,
)
from ..utils import handle_grpc_errors, map_exception_to_error, python_error_code_to_proto


class MessagesService(services_pb2_grpc.MessagesServicer):
    """Messages management service."""

    def __init__(self, database: Database, looper: Looper):
        """Initialize messages service.

        Args:
            database: Database instance for data access.
            looper: Looper instance for triggering conversation processing.
        """
        self._database = database
        self._looper = looper
        self._logger = Logger.get_logger("server.services.messages")

    @handle_grpc_errors
    async def GetAll(
        self,
        request: messages_pb2.GetAllMessagesRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetAllMessagesRequest, messages_pb2.GetAllMessagesResponse
        ],
    ) -> messages_pb2.GetAllMessagesResponse:
        """Get all messages for a conversation with pagination support."""
        conversation_id = UUID(request.conversation_id)
        before_message_id = (
            UUID(request.before_message_id) if request.HasField("before_message_id") else None
        )
        count = request.count if request.HasField("count") else None

        if before_message_id and count:
            self._logger.debug(
                "get_all_called",
                conversation_id=str(conversation_id),
                before_message_id=str(before_message_id),
                count=count,
            )
        elif before_message_id:
            self._logger.debug(
                "get_all_called",
                conversation_id=str(conversation_id),
                before_message_id=str(before_message_id),
            )
        elif count:
            self._logger.debug("get_all_called", conversation_id=str(conversation_id), count=count)
        else:
            self._logger.debug("get_all_called", conversation_id=str(conversation_id))

        messages = await self._database.messages.get_all(conversation_id, before_message_id, count)

        self._logger.debug(
            "get_all_completed", count=len(messages), conversation_id=str(conversation_id)
        )

        proto_messages = [self._python_message_to_proto(message) for message in messages]

        return messages_pb2.GetAllMessagesResponse(messages=proto_messages)

    @handle_grpc_errors
    async def Save(
        self,
        request: messages_pb2.SaveMessageRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SaveMessageRequest, messages_pb2.SaveMessageResponse
        ],
    ) -> messages_pb2.SaveMessageResponse:
        """Save message (create or update)."""
        message_id = UUID(request.id) if request.HasField("id") else None

        if message_id:
            self._logger.debug("save_called", message_id=str(message_id), mode="update")
        else:
            self._logger.debug("save_called", mode="create")

        conversation_id = UUID(request.message_content_user_input.conversation_id)

        conversation = await self._database.conversations.get(conversation_id)
        if not conversation:
            raise Error(ErrorCode.NOT_FOUND, "Conversation not found")

        message_content_user = MessageContentUser(
            type=MessageContentType.USER,
            text=request.message_content_user_input.text,
            attached_file_paths=list(request.message_content_user_input.attached_file_paths),
        )

        message_input = MessageInput(
            content=message_content_user,
            conversation_id=conversation_id,
        )

        if message_id:
            await self._database.messages.delete_after(message_id)
            conversation = await self._database.conversations.save(
                ConversationInput(
                    name=conversation.name,
                    agent_id=conversation.agent_id,
                    processing=conversation.processing,
                    error_code=conversation.error_code,
                    error_message=conversation.error_message,
                    context_tokens_count=None,
                    gateway_id=conversation.gateway_id,
                    gateway_external_id=conversation.gateway_external_id,
                    sender=conversation.sender,
                ),
                conversation.id,
            )

        message = await self._database.messages.save(message_input, message_id)

        await self._looper.process(conversation)

        if message_id:
            self._logger.debug("save_completed", message_id=str(message.id), mode="update")
        else:
            self._logger.debug("save_completed", message_id=str(message.id), mode="create")

        return messages_pb2.SaveMessageResponse(message=self._python_message_to_proto(message))

    async def WatchSaves(
        self,
        request: messages_pb2.WatchMessageSavesRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.WatchMessageSavesRequest,
            messages_pb2.WatchMessageSavesResponse,
        ],
    ) -> AsyncIterator[messages_pb2.WatchMessageSavesResponse]:
        """Stream message create and update events for a conversation."""
        try:
            conversation_id = UUID(request.conversation_id)
            self._logger.debug("watch_saves_called", conversation_id=str(conversation_id))

            async for message in self._database.messages.bus.watch_saves(conversation_id):
                yield messages_pb2.WatchMessageSavesResponse(
                    message=self._python_message_to_proto(message)
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

    async def WatchDeleteAfters(
        self,
        request: messages_pb2.WatchMessageDeleteAftersRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.WatchMessageDeleteAftersRequest,
            messages_pb2.WatchMessageDeleteAftersResponse,
        ],
    ) -> AsyncIterator[messages_pb2.WatchMessageDeleteAftersResponse]:
        """Stream delete_after events for a conversation."""
        try:
            conversation_id = UUID(request.conversation_id)
            self._logger.debug("watch_delete_afters_called", conversation_id=str(conversation_id))

            async for message_id in self._database.messages.bus.watch_delete_afters(
                conversation_id
            ):
                yield messages_pb2.WatchMessageDeleteAftersResponse(message_id=str(message_id))
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

    def _python_message_to_proto(self, python_message: Message) -> messages_pb2.Message:
        """Convert Python Message to proto Message."""
        created_at = Timestamp()
        created_at.FromDatetime(python_message.created_at)

        updated_at = Timestamp()
        updated_at.FromDatetime(python_message.updated_at)

        proto_content = self._python_message_content_to_proto(python_message.content)

        proto_message = messages_pb2.Message(
            id=str(python_message.id),
            created_at=created_at,
            updated_at=updated_at,
            content=proto_content,
            conversation_id=str(python_message.conversation_id),
        )

        return proto_message

    def _python_message_content_to_proto(
        self, python_content: MessageContent
    ) -> messages_pb2.MessageContent:
        """Convert Python MessageContent to proto MessageContent."""
        if python_content.type == MessageContentType.INTERNAL:
            return messages_pb2.MessageContent(
                internal=messages_pb2.MessageContentInternal(text=python_content.text)
            )
        elif python_content.type == MessageContentType.USER:
            return messages_pb2.MessageContent(
                user=messages_pb2.MessageContentUser(
                    text=python_content.text,
                    attached_file_paths=python_content.attached_file_paths,
                )
            )
        elif python_content.type == MessageContentType.AI:
            return messages_pb2.MessageContent(
                ai=messages_pb2.MessageContentAi(
                    text=python_content.text, processing=python_content.processing
                )
            )
        elif python_content.type == MessageContentType.TOOL:
            proto_response = None
            if python_content.response is not None:
                proto_response = messages_pb2.MessageContentToolResponse(
                    image_file_keys=python_content.response.image_file_keys,
                )
                if python_content.response.text is not None:
                    proto_response.text = python_content.response.text

            proto_tool = messages_pb2.MessageContentTool(
                name=python_content.name,
                processing=python_content.processing,
                request=python_content.request,
                response=proto_response,
            )

            if python_content.error is not None:
                proto_tool.error = python_error_code_to_proto(
                    python_error_code=python_content.error
                )

            return messages_pb2.MessageContent(tool=proto_tool)
        else:
            raise ValueError(f"Unknown message content type: {python_content.type}")
