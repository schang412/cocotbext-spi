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
import logging
import os

import cocotb
import cocotb_test.simulator
from cocotb.triggers import Timer

from cocotbext.spi import SpiBus
from cocotbext.spi import SpiConfig
from cocotbext.spi import SpiMaster
from cocotbext.spi.devices.TI import DRV8304


class TB:
    def __init__(self, dut):
        self.dut = dut
        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self.bus = SpiBus(entity = dut,
                          name = None,
                          signals = {
                                     'sclk' : 'sclk',
                                     'miso' : 'miso',
                                     'mosi' : 'mosi',
                                     'cs'   : "ncs"
                                    })

        self.config = SpiConfig(
            word_width=16,
            sclk_freq=25e6,
            cpol=False,
            cpha=True,
            msb_first=True,
            cs_active_low=True,
        )

        self.source = SpiMaster(self.bus, self.config)
        self.sink = DRV8304(self.bus)


@cocotb.test()
async def run_test_drv8304(dut):
    tb = TB(dut)
    await Timer(10, 'us')

    # we are working with 11 bit words
    bit_mask = 0x7FF

    # simulate a read event on a register of DRV8304
    await tb.source.write([tb.sink.create_spi_word("read", 0x03, 0b00000000000)])
    read_word = await tb.source.read(1)
    assert read_word[0] & bit_mask == 0x377

    # let the line idle for some time
    await Timer(500, units='ns')

    # simulate a write event on a register of DRV8304
    await tb.source.write([tb.sink.create_spi_word("write", 0x02, 0b00001000000)])

    read_word = await tb.source.read(1)
    assert read_word[0] & bit_mask == 0x00

    read_register = await tb.sink.get_register(0x02)
    assert read_register == 0b00001000000

    await Timer(5, 'us')

# cocotb-test

tests_dir = os.path.dirname(__file__)


def test_drv8304(request):
    dut = "test_drv8304"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(tests_dir, f"{dut}.v"),
    ]

    parameters = {}

    extra_env = {f'PARAM_{k}': str(v) for k, v in parameters.items()}

    sim_build = os.path.join(
        tests_dir, "sim_build",
        request.node.name.replace('[', '-').replace(']', ''),
    )

    cocotb_test.simulator.run(
        python_search=[tests_dir],
        verilog_sources=verilog_sources,
        toplevel=toplevel,
        module=module,
        parameters=parameters,
        sim_build=sim_build,
        extra_env=extra_env,
    )
