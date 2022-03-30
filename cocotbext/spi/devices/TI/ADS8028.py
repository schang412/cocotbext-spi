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

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, First, Timer, Event
from collections import deque
from ... import SpiSlaveBase, SpiConfig, SpiFrameError, SpiFrameTimeout


class ADS8028(SpiSlaveBase):
    def __init__(self, signals):
        self._config = SpiConfig(
            word_width=16,
            cpol=True,
            cpha=False,
            msb_first=True,
            frame_spacing_ns=6
        )

        self._control_register = 0
        self._control_register_updated = False
        self.adc_values = {
            0: 0,  # ain0
            1: 1,
            2: 2,
            3: 3,
            4: 4,
            5: 5,
            6: 6,
            7: 7,  # ain7
            8: 8  # temperature
        }
        self._out_queue = deque()

        super().__init__(signals)

    async def get_control_register(self):
        await self.idle.wait()
        return self._control_register

    def create_spi_word(self, operation, content):
        command = 0
        if operation == "read":
            # it is already 0
            pass
        elif operation == "write":
            command |= 1 << 15
        else:
            raise ValueError("Expected operation to be in ['read', 'write']")

        command |= (content & 0b111111111111111)

        return command

    def _generate_output(self):

        # check standby
        if self._control_register & (1 << 0):
            return 0

        # if we just updated the register, or its repeat, lets queue up the next one
        if self._control_register_updated or ((self._control_register & (1 << 14)) and not self._out_queue):
            self._control_register_updated = False

            for i in range(9):
                if not self._control_register & (1 << (13 - i)):
                    continue
                address = i << 12
                if i == 8 and (self._control_register & (1 << 1)):
                    address |= (1 << 12)
                self._out_queue.append((address & 0xF000) + (self.adc_values[i] & 0xFFF))

        if self._out_queue:
            return self._out_queue.popleft()
        return 0

    async def _transaction(self, frame_start, frame_end):
        await frame_start
        self.idle.clear()

        # SCLK pin should be high at the chip select edge
        if not bool(self._sclk.value):
            raise SpiFrameError("ADS8028: sclk should be high at chip select edge")

        tx_word = self._generate_output()

        # propagate the first bit on the fram start
        self._miso.value = bool(tx_word & (1 << 15))

        do_write = bool(await self._shift(1, tx_word=(tx_word & (1 << 14))))
        content = int(await self._shift(14, tx_word=(tx_word & (0x3FFF))))

        # get the last data bit
        r = await First(RisingEdge(self._sclk), frame_end)
        content = (content << 1) | int(self._mosi.value.integer)

        if r == frame_end:
            raise SpiFrameError("ADS8028: end of frame before last bit was sampled")

        # end of frame
        if await First(frame_end, FallingEdge(self._sclk)) != frame_end:
            raise SpiFrameError("ADS8028: clocked more than 16 bits")

        if not bool(self._sclk.value):
            raise SpiFrameError("ADS8028: sclk should be high at chip select edge")

        if do_write:
            self._control_register = content
            self._control_register_updated = True
            self._out_queue.clear()
            self._out_queue.append(0)
