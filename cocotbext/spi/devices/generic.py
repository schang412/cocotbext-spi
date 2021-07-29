
# Transmits the previously received word on the next transaction

from collections import deque
from cocotb.triggers import FallingEdge, RisingEdge, Event, First, Timer

from .. import SpiSlaveBase, SpiFrameError

class SpiSlaveLoopback(SpiSlaveBase):
    def __init__(self, signals, config):

        self._config = config

        self._out_queue = deque()
        self._out_queue.append(0)

        self._idle = Event()
        self._idle.set()

        super().__init__(signals)

    async def get_contents(self):
        await self._idle.wait()
        return self._out_queue[0]

    async def _run(self):
        if self._cs_active_low:
            frame_start = FallingEdge(self._cs)
            frame_end = RisingEdge(self._cs)
        else:
            frame_start = RisingEdge(self._cs)
            frame_end = FallingEdge(self._cs)

        frame_spacing = Timer(self._config.frame_spacing_ns, units='ns')

        while True:
            self._idle.set()
            if (await First(frame_start, frame_spacing)) == frame_start:
                raise SpiFrameError(f"There must be at least {self._config.frame_spacing_ns} ns between frames")
            await frame_start

            self._idle.clear()

            content = int(await self._shift(self._config.word_width, tx_word=self._out_queue.popleft()))

            await frame_end

            self._out_queue.append(content)