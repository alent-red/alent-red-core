import grpc
from uuid import UUID
from google.protobuf.timestamp_pb2 import Timestamp
from ...common import Logger
from ...generated.proto.agents import services_pb2_grpc, messages_pb2
from ...database import Database
from ...gateways import GatewayManager
from ...models import Agent, AgentInput, AgentReasoning, AgentVerbosity, Error, ErrorCode
from ..utils import handle_grpc_errors


class AgentsService(services_pb2_grpc.AgentsServicer):
    """Agents management service."""

    def __init__(self, database: Database, gateways: GatewayManager):
        """Initialize agents service.

        Args:
            database: Database instance for data access.
            gateways: Gateway manager instance for triggering refresh on changes.
        """
        self._database = database
        self._gateways = gateways
        self._logger = Logger.get_logger("server.services.agents")

    @handle_grpc_errors
    async def GetAll(
        self,
        request: messages_pb2.GetAllAgentsRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetAllAgentsRequest, messages_pb2.GetAllAgentsResponse
        ],
    ) -> messages_pb2.GetAllAgentsResponse:
        """Get all agents."""
        llm_model_id = UUID(request.llm_model_id) if request.HasField("llm_model_id") else None
        brick_id = UUID(request.brick_id) if request.HasField("brick_id") else None

        log_params = {}
        if llm_model_id:
            log_params["llm_model_id"] = str(llm_model_id)

        if brick_id:
            log_params["brick_id"] = str(brick_id)

        if log_params:
            self._logger.debug("get_all_called", **log_params)
        else:
            self._logger.debug("get_all_called")

        agents = await self._database.agents.get_all(llm_model_id, brick_id)

        if log_params:
            self._logger.debug("get_all_completed", count=len(agents), **log_params)
        else:
            self._logger.debug("get_all_completed", count=len(agents))

        proto_agents = [self._python_agent_to_proto(agent) for agent in agents]

        return messages_pb2.GetAllAgentsResponse(agents=proto_agents)

    @handle_grpc_errors
    async def Get(
        self,
        request: messages_pb2.GetAgentRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetAgentRequest, messages_pb2.GetAgentResponse
        ],
    ) -> messages_pb2.GetAgentResponse:
        """Get agent by ID."""
        agent_id = UUID(request.id)
        self._logger.debug("get_called", agent_id=str(agent_id))

        agent = await self._database.agents.get(agent_id)

        if not agent:
            raise Error(ErrorCode.NOT_FOUND, "Agent not found")

        self._logger.debug("get_completed", agent_id=str(agent_id))

        return messages_pb2.GetAgentResponse(agent=self._python_agent_to_proto(agent))

    @handle_grpc_errors
    async def Save(
        self,
        request: messages_pb2.SaveAgentRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SaveAgentRequest, messages_pb2.SaveAgentResponse
        ],
    ) -> messages_pb2.SaveAgentResponse:
        """Save agent (create or update)."""
        agent_id = UUID(request.id) if request.HasField("id") else None

        if agent_id:
            self._logger.debug("save_called", agent_id=str(agent_id), mode="update")
        else:
            self._logger.debug("save_called", mode="create")

        agent_input = AgentInput(
            name=request.agent.name,
            picture_file_key=(
                request.agent.picture_file_key
                if request.agent.HasField("picture_file_key")
                else None
            ),
            prompt=request.agent.prompt if request.agent.HasField("prompt") else None,
            attached_file_paths=list(request.agent.attached_file_paths),
            reasoning=self._proto_reasoning_to_python(request.agent.reasoning),
            verbosity=self._proto_verbosity_to_python(request.agent.verbosity),
            llm_model_id=UUID(request.agent.llm_model_id),
            brick_ids=[UUID(brick_id) for brick_id in request.agent.brick_ids],
        )

        agent = await self._database.agents.save(agent_input, agent_id)

        if agent_id:
            self._logger.debug("save_completed", agent_id=str(agent.id), mode="update")
        else:
            self._logger.debug("save_completed", agent_id=str(agent.id), mode="create")

        return messages_pb2.SaveAgentResponse(agent=self._python_agent_to_proto(agent))

    @handle_grpc_errors
    async def Delete(
        self,
        request: messages_pb2.DeleteAgentRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.DeleteAgentRequest, messages_pb2.DeleteAgentResponse
        ],
    ) -> messages_pb2.DeleteAgentResponse:
        """Delete agent by ID."""
        agent_id = UUID(request.id)
        self._logger.debug("delete_called", agent_id=str(agent_id))

        await self._database.agents.delete(agent_id)

        await self._gateways.refresh()

        self._logger.debug("delete_completed", agent_id=str(agent_id))

        return messages_pb2.DeleteAgentResponse()

    def _python_agent_to_proto(self, python_agent: Agent) -> messages_pb2.Agent:
        """Convert Python Agent to proto Agent."""
        created_at = Timestamp()
        created_at.FromDatetime(python_agent.created_at)

        updated_at = Timestamp()
        updated_at.FromDatetime(python_agent.updated_at)

        proto_agent = messages_pb2.Agent(
            id=str(python_agent.id),
            created_at=created_at,
            updated_at=updated_at,
            name=python_agent.name,
            reasoning=self._python_reasoning_to_proto(python_agent.reasoning),
            verbosity=self._python_verbosity_to_proto(python_agent.verbosity),
            attached_file_paths=python_agent.attached_file_paths,
        )

        if python_agent.picture_file_key is not None:
            proto_agent.picture_file_key = python_agent.picture_file_key

        if python_agent.prompt is not None:
            proto_agent.prompt = python_agent.prompt

        if python_agent.llm_model_id is not None:
            proto_agent.llm_model_id = str(python_agent.llm_model_id)

        return proto_agent

    def _proto_reasoning_to_python(
        self, proto_reasoning: messages_pb2.AgentReasoning
    ) -> AgentReasoning:
        """Convert proto AgentReasoning to Python enum."""
        if proto_reasoning == messages_pb2.AGENT_REASONING_DEFAULT:
            return AgentReasoning.DEFAULT
        elif proto_reasoning == messages_pb2.AGENT_REASONING_MINIMAL:
            return AgentReasoning.MINIMAL
        elif proto_reasoning == messages_pb2.AGENT_REASONING_LOW:
            return AgentReasoning.LOW
        elif proto_reasoning == messages_pb2.AGENT_REASONING_MEDIUM:
            return AgentReasoning.MEDIUM
        elif proto_reasoning == messages_pb2.AGENT_REASONING_HIGH:
            return AgentReasoning.HIGH
        elif proto_reasoning == messages_pb2.AGENT_REASONING_XHIGH:
            return AgentReasoning.XHIGH
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, "Invalid reasoning value")

    def _python_reasoning_to_proto(
        self, python_reasoning: AgentReasoning
    ) -> messages_pb2.AgentReasoning:
        """Convert Python AgentReasoning to proto enum."""
        if python_reasoning == AgentReasoning.DEFAULT:
            return messages_pb2.AGENT_REASONING_DEFAULT
        elif python_reasoning == AgentReasoning.MINIMAL:
            return messages_pb2.AGENT_REASONING_MINIMAL
        elif python_reasoning == AgentReasoning.LOW:
            return messages_pb2.AGENT_REASONING_LOW
        elif python_reasoning == AgentReasoning.MEDIUM:
            return messages_pb2.AGENT_REASONING_MEDIUM
        elif python_reasoning == AgentReasoning.HIGH:
            return messages_pb2.AGENT_REASONING_HIGH
        elif python_reasoning == AgentReasoning.XHIGH:
            return messages_pb2.AGENT_REASONING_XHIGH
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, "Invalid reasoning value")

    def _proto_verbosity_to_python(
        self, proto_verbosity: messages_pb2.AgentVerbosity
    ) -> AgentVerbosity:
        """Convert proto AgentVerbosity to Python enum."""
        if proto_verbosity == messages_pb2.AGENT_VERBOSITY_DEFAULT:
            return AgentVerbosity.DEFAULT
        elif proto_verbosity == messages_pb2.AGENT_VERBOSITY_LOW:
            return AgentVerbosity.LOW
        elif proto_verbosity == messages_pb2.AGENT_VERBOSITY_MEDIUM:
            return AgentVerbosity.MEDIUM
        elif proto_verbosity == messages_pb2.AGENT_VERBOSITY_HIGH:
            return AgentVerbosity.HIGH
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, "Invalid verbosity value")

    def _python_verbosity_to_proto(
        self, python_verbosity: AgentVerbosity
    ) -> messages_pb2.AgentVerbosity:
        """Convert Python AgentVerbosity to proto enum."""
        if python_verbosity == AgentVerbosity.DEFAULT:
            return messages_pb2.AGENT_VERBOSITY_DEFAULT
        elif python_verbosity == AgentVerbosity.LOW:
            return messages_pb2.AGENT_VERBOSITY_LOW
        elif python_verbosity == AgentVerbosity.MEDIUM:
            return messages_pb2.AGENT_VERBOSITY_MEDIUM
        elif python_verbosity == AgentVerbosity.HIGH:
            return messages_pb2.AGENT_VERBOSITY_HIGH
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, "Invalid verbosity value")
