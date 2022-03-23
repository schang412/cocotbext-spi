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
from ... import SpiSlaveBase, SpiConfig, SpiFrameError, SpiFrameTimeout


class DRV8304(SpiSlaveBase):
    def __init__(self, signals):
        self._config = SpiConfig(
            word_width=16,
            cpol=False,
            cpha=True,
            msb_first=True,
            frame_spacing_ns=400
        )

        self._registers = {
            0: 0b00000000000,
            1: 0b00000000000,
            2: 0b00000000000,
            3: 0b01101110111,
            4: 0b11101110111,
            5: 0b00101000101,
            6: 0b01010000011
        }

        super().__init__(signals)

    async def get_register(self, reg_num):
        await self.idle.wait()
        return self._registers[reg_num]

    def create_spi_word(self, operation, address, content):
        command = 0
        if operation == "read":
            command |= 1 << 15
        elif operation == "write":
            # it is already 0
            pass
        else:
            raise ValueError("Expected operation to be in ['read', 'write']")

        try:
            self._registers[address]
        except KeyError:
            raise ValueError(f"Expected address to be in {list(self._registers.keys())}")
        command |= (address & 0b1111) << 11
        command |= (content & 0b11111111111)

        return command

    async def _transaction(self, frame_start, frame_end):
        await frame_start
        self.idle.clear()

        # SCLK pin should be low at the chip select edge
        if bool(self._sclk.value):
            raise SpiFrameError("DRV8304: sclk should be low at chip select edge")

        do_write = not bool(await self._shift(1))
        address = int(await self._shift(4))
        content = int(await self._shift(11, tx_word=self._registers[address]))

        # end of frame
        if await First(frame_end, RisingEdge(self._sclk)) != frame_end:
            raise SpiFrameError("DRV8304: clocked more than 16 bits")

        if bool(self._sclk.value):
            raise SpiFrameError("DRV8304: sclk should be low at chip select edge")

        if do_write:
            self._registers[address] = content
