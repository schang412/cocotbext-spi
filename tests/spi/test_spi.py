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
import os

import cocotb
import cocotb_test.simulator
from cocotb.regression import TestFactory
from cocotb.triggers import Timer

from cocotbext.spi import SpiBus
from cocotbext.spi import SpiConfig
from cocotbext.spi import SpiMaster
from cocotbext.spi.devices.generic import SpiSlaveLoopback


class TB:
    def __init__(self, dut, word_width, spi_mode, msb_first, ignore_rx_value):
        self.dut = dut
        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self.bus = SpiBus.from_entity(dut, cs_name="ncs")

        self.config = SpiConfig(
            word_width=word_width,
            sclk_freq=25e6,
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


async def run_test(dut, payload_lengths, payload_data, word_width=16, spi_mode=1, msb_first=True, ignore_rx_value=None):
    tb = TB(dut, word_width, spi_mode, msb_first, ignore_rx_value)
    tb.log.info(
        "Running test with mode=%s, msb_first=%s, word_width=%s, ignore_rx_value=%s",
        spi_mode,
        msb_first,
        word_width,
        ignore_rx_value,
    )

    await Timer(10, 'us')

    for test_data in [payload_data(x) for x in payload_lengths()]:
        tb.log.info("Write data: %s", ','.join(['0x%02x' % x for x in test_data]))
        await tb.source.write(test_data)

        # if the rx_queue is empty after write do not wait for read,
        # otherwise it will crash. (This happens when ignore_rx_value is set)
        rx_data = tb.source.read_nowait() if tb.source.empty_rx() else await tb.source.read()
        sink_content = await tb.sink.get_contents()

        # remove ignore_rx_value from sink and test_data for assert
        filtered_test_data = list(filter(lambda v: v != ignore_rx_value, test_data))
        filtered_sink = [sink_content] if sink_content != ignore_rx_value else []

        tb.log.info("Read data: %s", ','.join(['0x%02x' % x for x in rx_data]))
        tb.log.info(f"In register: 0x{sink_content:02x}")
        assert list(rx_data[1:]) + filtered_sink == filtered_test_data

    await Timer(100, 'us')


def size_list():
    return list(range(1, 16)) + [128]


def incrementing_payload(length):
    return bytearray(itertools.islice(itertools.cycle(range(256)), length))


if cocotb.SIM_NAME:
    factory = TestFactory(run_test)
    factory.add_option("payload_lengths", [size_list])
    factory.add_option("payload_data", [incrementing_payload])
    factory.add_option("word_width", [8, 16, 32])
    factory.add_option("spi_mode", [0, 1, 2, 3])
    factory.add_option("msb_first", [True, False])
    factory.add_option("ignore_rx_value", [None, 0, 128])
    factory.generate_tests()


# cocotb-test
tests_dir = os.path.dirname(__file__)


def test_spi(request):
    dut = "test_spi"
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
