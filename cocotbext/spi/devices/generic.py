
# Transmits the previously received word on the next transaction

from collections import deque

class SpiSlaveLoopback(SpiSlaveBase):
    def __init__(self, signals, config):

        self._config = config

        self._out_queue = deque()
        self._out_queue.append(0)

        super().__init__(signals)

    async def get_contents(self):
        await self._idle.wait()
        return self._out_queue[0]

    def _run(self):
        if self._cs_active_low:
            frame_start = FallingEdge(self._cs)
            frame_end = RisingEdge(self._cs)
        else:
            frame_start = RisingEdge(self._cs)
            frame_end = FallingEdge(self._cs)

        while True:
            self._idle.set()
            await frame_start
            self._idle.clear()

            content = int(await self._shift(self._config.word_width, tx_word=self._out_queue.popleft()))

            await frame_end

            self._out_queue.append(content)