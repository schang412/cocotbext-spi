
# Transmits the previously received word on the next transaction

from collections import deque
from cocotb.triggers import FallingEdge, RisingEdge, Event, First, Timer

from .. import SpiSlaveBase, SpiFrameError, reverse_word


class SpiSlaveLoopback(SpiSlaveBase):
    def __init__(self, signals, config):

        self._config = config

        self._out_queue = deque()
        self._out_queue.append(0)

        super().__init__(signals)

    async def get_contents(self):
        await self.idle.wait()
        if self._config.msb_first:
            return self._out_queue[0]
        else:
            return reverse_word(self._out_queue[0], self._config.word_width)

    async def _transaction(self, frame_start, frame_end):
        await frame_start
        self.idle.clear()

        # we do not have to reverse the word based on msb or lsb since we are just looping back
        tx_word = self._out_queue.popleft()
        if not self._config.cpha:
            # when CPHA=0, we use the chip select edge (frame start) to propagate data.
            self._miso <= bool(tx_word & (1 << self._config.word_width - 1))
            # now we can do the sclk cycles, but we do one less (because we don't have all the words
            content = int(await self._shift(self._config.word_width - 1, tx_word=tx_word))
            # get the last data bit
            await RisingEdge(self._sclk)
            content = (content << 1) | int(self._mosi.value.integer)
        else:
            content = int(await self._shift(self._config.word_width, tx_word=tx_word))

        await frame_end
        self._out_queue.append(content)

