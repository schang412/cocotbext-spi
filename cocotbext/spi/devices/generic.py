"""
Copyright (c) 2021 Spencer Chang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

# Transmits the previously received word on the next transaction

from collections import deque
from cocotb.triggers import Edge, Event, First, Timer

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

