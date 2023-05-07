# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2021 Spencer Chang
# Transmits the previously received word on the next transaction
from collections import deque

from cocotb.triggers import Edge
from cocotb.triggers import First

from ..exceptions import SpiFrameError
from ..spi import reverse_word
from ..spi import SpiBus
from ..spi import SpiConfig
from ..spi import SpiSlaveBase


class SpiSlaveLoopback(SpiSlaveBase):
    def __init__(self, bus: SpiBus, config: SpiConfig):
        self._config = config

        self._out_queue = deque()
        self._out_queue.append(0)

        super().__init__(bus)

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
            self._miso.value = bool(tx_word & (1 << self._config.word_width - 1))
            # now we can do the sclk cycles, but we do one less (because we don't have all the words
            content = int(await self._shift(self._config.word_width - 1, tx_word=tx_word))

            # get the last data bit
            r = await First(Edge(self._sclk), frame_end)
            content = (content << 1) | int(self._mosi.value.integer)

            # check to make sure we didn't lose the frame
            if r == frame_end:
                raise SpiFrameError("End of frame before last bit was sampled")
        else:
            content = int(await self._shift(self._config.word_width, tx_word=tx_word))

        await frame_end
        self._out_queue.append(content)
