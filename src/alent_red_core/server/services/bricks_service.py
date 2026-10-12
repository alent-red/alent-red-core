import grpc
from uuid import UUID
from google.protobuf.timestamp_pb2 import Timestamp
from ...common import Logger
from ...generated.proto.bricks import services_pb2_grpc, messages_pb2
from ...database import Database
from ...looper import Looper
from ...models import (
    Brick,
    BrickInput,
    BrickConfig,
    BrickConfigUI,
    BrickConfigUIMovePointerCoordinateSpace,
    BrickConfigUIMovePointerGeometry,
    BrickConfigCode,
    BrickConfigVision,
    BrickConfigSkills,
    BrickConfigCustom,
    BrickConfigSystem,
    BrickConfigScheduler,
    BrickConfigRenderer,
    BrickConfigBrowser,
    BrickConfigAgent,
    BrickConfigType,
    Error,
    ErrorCode,
)
from ..utils import handle_grpc_errors


class BricksService(services_pb2_grpc.BricksServicer):
    """Bricks management service."""

    def __init__(self, database: Database, looper: Looper):
        """Initialize bricks service.

        Args:
            database: Database instance for data access.
            looper: Looper instance for triggering refresh on changes.
        """
        self._database = database
        self._looper = looper
        self._logger = Logger.get_logger("server.services.bricks")

    @handle_grpc_errors
    async def GetAll(
        self,
        request: messages_pb2.GetAllBricksRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetAllBricksRequest, messages_pb2.GetAllBricksResponse
        ],
    ) -> messages_pb2.GetAllBricksResponse:
        """Get all bricks."""
        agent_id = UUID(request.agent_id) if request.HasField("agent_id") else None

        if agent_id:
            self._logger.debug("get_all_called", agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_called")

        bricks = await self._database.bricks.get_all(agent_id)

        if agent_id:
            self._logger.debug("get_all_completed", count=len(bricks), agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_completed", count=len(bricks))

        proto_bricks = [self._python_brick_to_proto(brick) for brick in bricks]

        return messages_pb2.GetAllBricksResponse(bricks=proto_bricks)

    @handle_grpc_errors
    async def Get(
        self,
        request: messages_pb2.GetBrickRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetBrickRequest, messages_pb2.GetBrickResponse
        ],
    ) -> messages_pb2.GetBrickResponse:
        """Get brick by ID."""
        brick_id = UUID(request.id)
        self._logger.debug("get_called", brick_id=str(brick_id))

        brick = await self._database.bricks.get(brick_id)

        if not brick:
            raise Error(ErrorCode.NOT_FOUND, "Brick not found")

        self._logger.debug("get_completed", brick_id=str(brick_id))

        return messages_pb2.GetBrickResponse(brick=self._python_brick_to_proto(brick))

    @handle_grpc_errors
    async def Save(
        self,
        request: messages_pb2.SaveBrickRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SaveBrickRequest, messages_pb2.SaveBrickResponse
        ],
    ) -> messages_pb2.SaveBrickResponse:
        """Save brick (create or update)."""
        brick_id = UUID(request.id) if request.HasField("id") else None

        if brick_id:
            self._logger.debug("save_called", brick_id=str(brick_id), mode="update")
        else:
            self._logger.debug("save_called", mode="create")

        brick_config = self._proto_config_to_python(request.brick.config)

        brick_input = BrickInput(name=request.brick.name, config=brick_config)

        brick = await self._database.bricks.save(brick_input, brick_id)

        await self._looper.refresh()

        if brick_id:
            self._logger.debug("save_completed", brick_id=str(brick.id), mode="update")
        else:
            self._logger.debug("save_completed", brick_id=str(brick.id), mode="create")

        return messages_pb2.SaveBrickResponse(brick=self._python_brick_to_proto(brick))

    @handle_grpc_errors
    async def Delete(
        self,
        request: messages_pb2.DeleteBrickRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.DeleteBrickRequest, messages_pb2.DeleteBrickResponse
        ],
    ) -> messages_pb2.DeleteBrickResponse:
        """Delete brick by ID."""
        brick_id = UUID(request.id)
        self._logger.debug("delete_called", brick_id=str(brick_id))

        await self._database.bricks.delete(brick_id)

        await self._looper.refresh()

        self._logger.debug("delete_completed", brick_id=str(brick_id))

        return messages_pb2.DeleteBrickResponse()

    def _python_brick_to_proto(self, brick: Brick) -> messages_pb2.Brick:
        """Convert Python Brick to proto Brick."""
        created_at_timestamp = Timestamp()
        created_at_timestamp.FromDatetime(brick.created_at)

        updated_at_timestamp = Timestamp()
        updated_at_timestamp.FromDatetime(brick.updated_at)

        return messages_pb2.Brick(
            id=str(brick.id),
            created_at=created_at_timestamp,
            updated_at=updated_at_timestamp,
            name=brick.name,
            config=self._python_config_to_proto(brick.config),
        )

    def _python_config_to_proto(self, config: BrickConfig) -> messages_pb2.BrickConfig:
        """Convert Python BrickConfig to proto BrickConfig."""
        if config.type == BrickConfigType.UI:
            return messages_pb2.BrickConfig(
                ui=messages_pb2.BrickConfigUI(
                    move_pointer_llm_model_id=str(config.move_pointer_llm_model_id),
                    move_pointer_geometry=self._python_geometry_to_proto(
                        config.move_pointer_geometry
                    ),
                    move_pointer_coordinate_space=self._python_coordinate_space_to_proto(
                        config.move_pointer_coordinate_space
                    ),
                )
            )
        elif config.type == BrickConfigType.CODE:
            return messages_pb2.BrickConfig(code=messages_pb2.BrickConfigCode())
        elif config.type == BrickConfigType.SYSTEM:
            return messages_pb2.BrickConfig(system=messages_pb2.BrickConfigSystem())
        elif config.type == BrickConfigType.SCHEDULER:
            return messages_pb2.BrickConfig(scheduler=messages_pb2.BrickConfigScheduler())
        elif config.type == BrickConfigType.RENDERER:
            return messages_pb2.BrickConfig(renderer=messages_pb2.BrickConfigRenderer())
        elif config.type == BrickConfigType.BROWSER:
            return messages_pb2.BrickConfig(browser=messages_pb2.BrickConfigBrowser())
        elif config.type == BrickConfigType.AGENT:
            return messages_pb2.BrickConfig(agent=messages_pb2.BrickConfigAgent())
        elif config.type == BrickConfigType.CUSTOM:
            return messages_pb2.BrickConfig(custom=messages_pb2.BrickConfigCustom(path=config.path))
        elif config.type == BrickConfigType.VISION:
            return messages_pb2.BrickConfig(vision=messages_pb2.BrickConfigVision())
        elif config.type == BrickConfigType.SKILLS:
            return messages_pb2.BrickConfig(skills=messages_pb2.BrickConfigSkills())
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unknown brick config type: {config.type}")

    def _proto_config_to_python(self, config: messages_pb2.BrickConfig) -> BrickConfig:
        """Convert proto BrickConfig to Python BrickConfig."""
        config_type = config.WhichOneof("config")

        match config_type:
            case "ui":
                return BrickConfigUI(
                    move_pointer_llm_model_id=UUID(config.ui.move_pointer_llm_model_id),
                    move_pointer_geometry=self._proto_geometry_to_python(
                        config.ui.move_pointer_geometry
                    ),
                    move_pointer_coordinate_space=self._proto_coordinate_space_to_python(
                        config.ui.move_pointer_coordinate_space
                    ),
                )
            case "code":
                return BrickConfigCode()
            case "vision":
                return BrickConfigVision()
            case "skills":
                return BrickConfigSkills()
            case "system":
                return BrickConfigSystem()
            case "scheduler":
                return BrickConfigScheduler()
            case "renderer":
                return BrickConfigRenderer()
            case "browser":
                return BrickConfigBrowser()
            case "agent":
                return BrickConfigAgent()
            case "custom":
                return BrickConfigCustom(path=config.custom.path)
            case _:
                raise Error(ErrorCode.NOT_SUPPORTED, f"Unknown brick config type: {config_type}")

    def _proto_geometry_to_python(
        self, proto_geometry: messages_pb2.BrickConfigUIMovePointerGeometry
    ) -> BrickConfigUIMovePointerGeometry:
        """Convert proto BrickConfigUIMovePointerGeometry to Python enum."""
        if proto_geometry == messages_pb2.BRICK_CONFIG_UI_MOVE_POINTER_GEOMETRY_POINT:
            return BrickConfigUIMovePointerGeometry.POINT
        elif proto_geometry == messages_pb2.BRICK_CONFIG_UI_MOVE_POINTER_GEOMETRY_BOUNDING_BOX:
            return BrickConfigUIMovePointerGeometry.BOUNDING_BOX
        else:
            raise ValueError(f"Unknown move pointer geometry: {proto_geometry}")

    def _python_geometry_to_proto(
        self, python_geometry: BrickConfigUIMovePointerGeometry
    ) -> messages_pb2.BrickConfigUIMovePointerGeometry:
        """Convert Python BrickConfigUIMovePointerGeometry to proto enum."""
        if python_geometry == BrickConfigUIMovePointerGeometry.POINT:
            return messages_pb2.BRICK_CONFIG_UI_MOVE_POINTER_GEOMETRY_POINT
        elif python_geometry == BrickConfigUIMovePointerGeometry.BOUNDING_BOX:
            return messages_pb2.BRICK_CONFIG_UI_MOVE_POINTER_GEOMETRY_BOUNDING_BOX
        else:
            raise ValueError(f"Unknown move pointer geometry: {python_geometry}")

    def _proto_coordinate_space_to_python(
        self, proto_coordinate_space: messages_pb2.BrickConfigUIMovePointerCoordinateSpace
    ) -> BrickConfigUIMovePointerCoordinateSpace:
        """Convert proto BrickConfigUIMovePointerCoordinateSpace to Python enum."""
        if (
            proto_coordinate_space
            == messages_pb2.BRICK_CONFIG_UI_MOVE_POINTER_COORDINATE_SPACE_PIXELS
        ):
            return BrickConfigUIMovePointerCoordinateSpace.PIXELS
        elif (
            proto_coordinate_space
            == messages_pb2.BRICK_CONFIG_UI_MOVE_POINTER_COORDINATE_SPACE_NORMALIZED_1000
        ):
            return BrickConfigUIMovePointerCoordinateSpace.NORMALIZED_1000
        else:
            raise ValueError(f"Unknown move pointer coordinate space: {proto_coordinate_space}")

    def _python_coordinate_space_to_proto(
        self, python_coordinate_space: BrickConfigUIMovePointerCoordinateSpace
    ) -> messages_pb2.BrickConfigUIMovePointerCoordinateSpace:
        """Convert Python BrickConfigUIMovePointerCoordinateSpace to proto enum."""
        if python_coordinate_space == BrickConfigUIMovePointerCoordinateSpace.PIXELS:
            return messages_pb2.BRICK_CONFIG_UI_MOVE_POINTER_COORDINATE_SPACE_PIXELS
        elif python_coordinate_space == BrickConfigUIMovePointerCoordinateSpace.NORMALIZED_1000:
            return messages_pb2.BRICK_CONFIG_UI_MOVE_POINTER_COORDINATE_SPACE_NORMALIZED_1000
        else:
            raise ValueError(f"Unknown move pointer coordinate space: {python_coordinate_space}")
