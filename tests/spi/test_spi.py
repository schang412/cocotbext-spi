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

import itertools
import logging
import pathlib
import json
import os

import cocotb
from cocotb.triggers import Timer
from cocotb_tools._pytest.hdl import HDL
import pytest

from cocotbext.spi import SpiBus
from cocotbext.spi import SpiConfig
from cocotbext.spi import SpiMaster
from cocotbext.spi.devices.generic import SpiSlaveLoopback


class TB:
    def __init__(
        self, dut, sclk_freq, word_width, spi_mode, msb_first, ignore_rx_value
    ):
        self.dut = dut
        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self.bus = SpiBus.from_entity(dut, cs_name="ncs")

        self.config = SpiConfig(
            word_width=word_width,
            sclk_freq=sclk_freq,
            cpol=bool(spi_mode in [2, 3]),
            cpha=bool(spi_mode in [1, 3]),
            msb_first=msb_first,
            frame_spacing_ns=10,
            ignore_rx_value=ignore_rx_value,
            cs_active_low=True,
        )

        dut.spi_mode.value = spi_mode
        dut.spi_word_width.value = word_width

        self.source = SpiMaster(self.bus, self.config)
        self.sink = SpiSlaveLoopback(self.bus, self.config)


@cocotb.test(
    timeout_time=1,
    timeout_unit="ms",
)
@cocotb.parametrize(
    sclk_freq=[15e6, 25e6],
    word_width=[8, 16, 32],
    spi_mode=[0, 1, 2, 3],
    msb_first=[True, False],
    ignore_rx_value=[None, 0, 128],
)
async def run_test(dut, sclk_freq, word_width, spi_mode, msb_first, ignore_rx_value):
    payload_lengths = list(range(1, 16)) + [128]

    def incrementing_payload(length):
        return bytearray(itertools.islice(itertools.cycle(range(256)), length))

    tb = TB(dut, sclk_freq, word_width, spi_mode, msb_first, ignore_rx_value)
    tb.log.info(
        "Running test with sclk_freq=%s mode=%s, msb_first=%s, word_width=%s, ignore_rx_value=%s",
        sclk_freq,
        spi_mode,
        msb_first,
        word_width,
        ignore_rx_value,
    )

    await Timer(10, "us")

    for test_data in [incrementing_payload(x) for x in payload_lengths]:
        tb.log.info("Write data: %s", ",".join(["0x%02x" % x for x in test_data]))
        await tb.source.write(test_data)

        # if the rx_queue is empty after write do not wait for read,
        # otherwise it will crash. (This happens when ignore_rx_value is set)
        rx_data = (
            tb.source.read_nowait() if tb.source.empty_rx() else await tb.source.read()
        )
        sink_content = await tb.sink.get_contents()

        # remove ignore_rx_value from sink and test_data for assert
        filtered_test_data = list(filter(lambda v: v != ignore_rx_value, test_data))
        filtered_sink = [sink_content] if sink_content != ignore_rx_value else []

        tb.log.info("Read data: %s", ",".join(["0x%02x" % x for x in rx_data]))
        tb.log.info(f"In register: 0x{sink_content:02x}")
        assert list(rx_data[1:]) + filtered_sink == filtered_test_data

    await Timer(100, "us")


@pytest.fixture(name="spi_module")
def spi_module_fixture(hdl: HDL) -> HDL:
    hdl.toplevel = "test_spi"
    hdl.sources = (pathlib.Path(__file__).parent / "test_spi.v",)
    hdl.build()

    return hdl


@pytest.mark.cocotb_runner
def spi_module_runner(spi_module: HDL) -> None:
    spi_module.test()
