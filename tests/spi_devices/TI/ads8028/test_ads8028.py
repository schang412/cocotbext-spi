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
import pathlib

import cocotb
from cocotb.triggers import Timer
import pytest
from cocotb_tools._pytest.hdl import HDL


from cocotbext.spi import SpiBus
from cocotbext.spi import SpiConfig
from cocotbext.spi import SpiMaster
from cocotbext.spi.devices.TI import ADS8028


class TB:
    def __init__(self, dut):
        self.dut = dut
        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self.bus = SpiBus.from_entity(dut, cs_name="ncs")

        self.config = SpiConfig(
            word_width=16,
            sclk_freq=25e6,
            cpol=True,
            cpha=False,
            msb_first=True,
            cs_active_low=True,
        )

        self.source = SpiMaster(self.bus, self.config)
        self.sink = ADS8028(self.bus)


@cocotb.test()
async def run_test_ads8028(dut):
    tb = TB(dut)
    await Timer(10, "us")

    address_mask = 0xF000
    data_mask = 0x0FFF

    await tb.source.write([tb.sink.create_spi_word("write", 0b111100011100100)])
    _ = await tb.source.read()

    await Timer(20, unit="ns")

    await tb.source.write([tb.sink.create_spi_word("read", 0x0000)])
    _ = await tb.source.read()

    await Timer(20, unit="ns")

    await tb.source.write([tb.sink.create_spi_word("read", 0x0000)])
    ain0 = (await tb.source.read())[0]
    assert ain0 & address_mask == 0 << 12
    assert ain0 & data_mask == 0

    await Timer(20, unit="ns")

    await tb.source.write([tb.sink.create_spi_word("read", 0x0000)])
    ain1 = (await tb.source.read())[0]
    assert ain1 & address_mask == 1 << 12
    assert ain1 & data_mask == 1

    await Timer(5, "us")


@pytest.fixture(name="spi_module")
def spi_module_fixture(hdl: HDL) -> HDL:
    hdl.toplevel = "test_spi"
    hdl.sources = (pathlib.Path(__file__).parent.parent.parent.parent / "spi" / "test_spi.v",)
    hdl.build()

    return hdl


@pytest.mark.cocotb_runner
def spi_module_runner(spi_module: HDL) -> None:
    spi_module.test()
