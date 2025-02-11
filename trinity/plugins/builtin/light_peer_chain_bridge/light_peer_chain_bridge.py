from dataclasses import (
    dataclass,
)
from typing import (
    List,
    Type,
    TypeVar,
)

from cancel_token import (
    CancelToken,
)
from eth_typing import (
    Address,
    Hash32,
)
from eth.rlp.accounts import (
    Account,
)
from eth.rlp.headers import (
    BlockHeader,
)
from eth.rlp.receipts import (
    Receipt,
)
from lahja import (
    BaseEvent,
    BaseRequestResponseEvent,
)
from p2p.service import (
    BaseService,
)

from trinity.constants import (
    TO_NETWORKING_BROADCAST_CONFIG,
)
from trinity.endpoint import (
    TrinityEventBusEndpoint,
)
from trinity._utils.async_errors import (
    await_and_wrap_errors,
)
from trinity.rlp.block_body import BlockBody
from trinity.sync.light.service import (
    BaseLightPeerChain,
)


class BaseLightPeerChainResponse(BaseEvent):

    error: Exception


@dataclass
class BlockHeaderResponse(BaseLightPeerChainResponse):

    block_header: BlockHeader
    error: Exception = None


@dataclass
class BlockBodyResponse(BaseLightPeerChainResponse):

    block_body: BlockBody
    error: Exception = None


@dataclass
class ReceiptsResponse(BaseLightPeerChainResponse):

    receipts: List[Receipt]
    error: Exception = None


@dataclass
class AccountResponse(BaseLightPeerChainResponse):

    account: Account
    error: Exception = None


@dataclass
class BytesResponse(BaseLightPeerChainResponse):

    bytez: bytes
    error: Exception = None


@dataclass
class GetBlockHeaderByHashRequest(BaseRequestResponseEvent[BlockHeaderResponse]):

    block_hash: Hash32

    @staticmethod
    def expected_response_type() -> Type[BlockHeaderResponse]:
        return BlockHeaderResponse


@dataclass
class GetBlockBodyByHashRequest(BaseRequestResponseEvent[BlockBodyResponse]):

    block_hash: Hash32

    @staticmethod
    def expected_response_type() -> Type[BlockBodyResponse]:
        return BlockBodyResponse


@dataclass
class GetReceiptsRequest(BaseRequestResponseEvent[ReceiptsResponse]):

    block_hash: Hash32

    @staticmethod
    def expected_response_type() -> Type[ReceiptsResponse]:
        return ReceiptsResponse


@dataclass
class GetAccountRequest(BaseRequestResponseEvent[AccountResponse]):

    block_hash: Hash32
    address: Address

    @staticmethod
    def expected_response_type() -> Type[AccountResponse]:
        return AccountResponse


@dataclass
class GetContractCodeRequest(BaseRequestResponseEvent[BytesResponse]):

    block_hash: Hash32
    address: Address

    @staticmethod
    def expected_response_type() -> Type[BytesResponse]:
        return BytesResponse


class LightPeerChainEventBusHandler(BaseService):
    """
    The ``LightPeerChainEventBusHandler`` listens for certain events on the eventbus and
    delegates them to the ``LightPeerChain`` to get answers. It then propagates responses
    back to the caller.
    """

    def __init__(self,
                 chain: BaseLightPeerChain,
                 event_bus: TrinityEventBusEndpoint,
                 token: CancelToken = None) -> None:
        super().__init__(token)
        self.chain = chain
        self.event_bus = event_bus

    async def _run(self) -> None:
        self.logger.info("Running LightPeerChainEventBusHandler")

        self.run_daemon_task(self.handle_get_blockheader_by_hash_requests())
        self.run_daemon_task(self.handle_get_blockbody_by_hash_requests())
        self.run_daemon_task(self.handle_get_receipts_by_hash_requests())
        self.run_daemon_task(self.handle_get_account_requests())
        self.run_daemon_task(self.handle_get_contract_code_requests())

    async def handle_get_blockheader_by_hash_requests(self) -> None:
        async for event in self.event_bus.stream(GetBlockHeaderByHashRequest):

            val, error = await await_and_wrap_errors(
                self.chain.coro_get_block_header_by_hash(event.block_hash)
            )

            await self.event_bus.broadcast(
                event.expected_response_type()(val, error),
                event.broadcast_config()
            )

    async def handle_get_blockbody_by_hash_requests(self) -> None:
        async for event in self.event_bus.stream(GetBlockBodyByHashRequest):

            val, error = await await_and_wrap_errors(
                self.chain.coro_get_block_body_by_hash(event.block_hash)
            )

            await self.event_bus.broadcast(
                event.expected_response_type()(val, error),
                event.broadcast_config()
            )

    async def handle_get_receipts_by_hash_requests(self) -> None:
        async for event in self.event_bus.stream(GetReceiptsRequest):

            val, error = await await_and_wrap_errors(self.chain.coro_get_receipts(event.block_hash))

            await self.event_bus.broadcast(
                event.expected_response_type()(val, error),
                event.broadcast_config()
            )

    async def handle_get_account_requests(self) -> None:
        async for event in self.event_bus.stream(GetAccountRequest):

            val, error = await await_and_wrap_errors(
                self.chain.coro_get_account(event.block_hash, event.address)
            )

            await self.event_bus.broadcast(
                event.expected_response_type()(val, error),
                event.broadcast_config()
            )

    async def handle_get_contract_code_requests(self) -> None:

        async for event in self.event_bus.stream(GetContractCodeRequest):

            val, error = await await_and_wrap_errors(
                self.chain.coro_get_contract_code(event.block_hash, event.address)
            )

            await self.event_bus.broadcast(
                event.expected_response_type()(val, error),
                event.broadcast_config()
            )


class EventBusLightPeerChain(BaseLightPeerChain):
    """
    The ``EventBusLightPeerChain`` is an implementation of the ``BaseLightPeerChain`` that can
    be used from within any process.
    """

    def __init__(self, event_bus: TrinityEventBusEndpoint) -> None:
        self.event_bus = event_bus

    async def coro_get_block_header_by_hash(self, block_hash: Hash32) -> BlockHeader:
        event = GetBlockHeaderByHashRequest(block_hash)
        return self._pass_or_raise(
            await self.event_bus.request(event, TO_NETWORKING_BROADCAST_CONFIG)
        ).block_header

    async def coro_get_block_body_by_hash(self, block_hash: Hash32) -> BlockBody:
        event = GetBlockBodyByHashRequest(block_hash)
        return self._pass_or_raise(
            await self.event_bus.request(event, TO_NETWORKING_BROADCAST_CONFIG)
        ).block_body

    async def coro_get_receipts(self, block_hash: Hash32) -> List[Receipt]:
        event = GetReceiptsRequest(block_hash)
        return self._pass_or_raise(
            await self.event_bus.request(event, TO_NETWORKING_BROADCAST_CONFIG)
        ).receipts

    async def coro_get_account(self, block_hash: Hash32, address: Address) -> Account:
        event = GetAccountRequest(block_hash, address)
        return self._pass_or_raise(
            await self.event_bus.request(event, TO_NETWORKING_BROADCAST_CONFIG)
        ).account

    async def coro_get_contract_code(self, block_hash: Hash32, address: Address) -> bytes:
        event = GetContractCodeRequest(block_hash, address)
        return self._pass_or_raise(
            await self.event_bus.request(event, TO_NETWORKING_BROADCAST_CONFIG)
        ).bytez

    TResponse = TypeVar("TResponse", bound=BaseLightPeerChainResponse)

    def _pass_or_raise(self, response: TResponse) -> TResponse:
        if response.error is not None:
            raise response.error

        return response
