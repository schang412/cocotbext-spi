
# Transmits the previously received word on the next transaction

from collections import deque
from cocotb.triggers import FallingEdge, RisingEdge, Event, First, Timer

from .. import SpiSlaveBase, SpiFrameError


class SpiSlaveLoopback(SpiSlaveBase):
    def __init__(self, signals, config):

        self._config = config

        self._out_queue = deque()
        self._out_queue.append(0)

        super().__init__(signals)

    async def get_contents(self):
        await self.idle.wait()
        return self._out_queue[0]

    async def _transaction(self, frame_start, frame_end):
        await frame_start
        self.idle.clear()

        content = int(await self._shift(self._config.word_width, tx_word=self._out_queue.popleft()))

        await frame_end
        self._out_queue.append(content)
