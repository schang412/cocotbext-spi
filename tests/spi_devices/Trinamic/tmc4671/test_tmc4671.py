"""
Copyright (c) 2022 Spencer Chang

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
from cocotb_tools._pytest.hdl import HDL
import pytest

from cocotbext.spi import SpiBus
from cocotbext.spi import SpiConfig
from cocotbext.spi import SpiMaster
from cocotbext.spi.devices.Trinamic import TMC4671


class TB:
    def __init__(self, dut):
        self.dut = dut
        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self.bus = SpiBus.from_entity(dut, cs_name="ncs")

        self.config = SpiConfig(
            word_width=40,
            sclk_freq=2e6,
            cpol=True,
            cpha=True,
            msb_first=True,
            cs_active_low=True,
        )

        self.source = SpiMaster(self.bus, self.config)
        self.sink = TMC4671(self.bus)


@cocotb.test()
async def run_test_tmc4671(dut):
    tb = TB(dut)
    await Timer(10, "us")

    # we are working with 32 bit words
    bit_mask = 0xFFFF_FFFF

    # set the CHIPINFO_ADDR register to 0 (to get SI_TYPE)
    await tb.source.write([tb.sink.create_spi_word("write", 0x01, 0)])
    _ = await tb.source.read(1)

    await Timer(20, unit="ns")

    # read the CHIPINFO_DATA register for the SI_TYPE value
    await tb.source.write([tb.sink.create_spi_word("read", 0x00, 0)])
    read_word = await tb.source.read(1)
    assert read_word[0] & bit_mask == 0x34363731

    await Timer(20, unit="ns")

    # set the CHIPINFO_ADDR register to 1 (to get SI_VERSION)
    await tb.source.write([tb.sink.create_spi_word("write", 0x01, 1)])
    _ = await tb.source.read(1)

    await Timer(20, unit="ns")

    # read the CHIPINFO_DATA register for the SI_VERSION
    await tb.source.write([tb.sink.create_spi_word("read", 0x00, 0)])
    read_word = await tb.source.read(1)
    assert read_word[0] & bit_mask == 0x0000_0100

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
