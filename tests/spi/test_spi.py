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

import cocotb_test.simulator

import cocotb
from cocotb.triggers import Timer
from cocotb.regression import TestFactory

from cocotbext.spi import SpiMaster, SpiSignals, SpiConfig
from cocotbext.spi.devices.generic import SpiSlaveLoopback


class TB:
    def __init__(self, dut, word_width, spi_mode, msb_first):
        self.dut = dut
        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self.signals = SpiSignals(
            sclk=dut.sclk,
            mosi=dut.mosi,
            miso=dut.miso,
            cs=dut.ncs,
            cs_active_low=True
        )

        self.config = SpiConfig(
            word_width=word_width,
            sclk_freq=25e6,
            cpol=bool(spi_mode in [2, 3]),
            cpha=bool(spi_mode in [1, 3]),
            msb_first=msb_first,
            frame_spacing_ns=10
        )

        dut.spi_mode.value = spi_mode
        dut.spi_word_width.value = word_width

        self.source = SpiMaster(self.signals, self.config)
        self.sink = SpiSlaveLoopback(self.signals, self.config)


async def run_test(dut, payload_lengths, payload_data, word_width=16, spi_mode=1, msb_first=True):
    tb = TB(dut, word_width, spi_mode, msb_first)
    tb.log.info(f"Running test with mode={spi_mode}, msb_first={msb_first}, word_width={word_width}")

    await Timer(10, 'us')

    for test_data in [payload_data(x) for x in payload_lengths()]:
        tb.log.info("Write data: %s", ','.join(['0x%02x' % x for x in test_data]))
        await tb.source.write(test_data)

        rx_data = await tb.source.read()

        tb.log.info("Read data: %s", ','.join(['0x%02x' % x for x in rx_data]))
        tb.log.info("In register: 0x{:02x}".format(await tb.sink.get_contents()))
        assert list(rx_data[1:]) + [await tb.sink.get_contents()] == list(test_data)

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
    factory.generate_tests()


# cocotb-test
tests_dir = os.path.dirname(__file__)


def test_spi(request):
    dut = "test_spi"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(tests_dir, f"{dut}.v")
    ]

    parameters = {}

    extra_env = {f'PARAM_{k}': str(v) for k, v in parameters.items()}

    sim_build = os.path.join(tests_dir, "sim_build",
                             request.node.name.replace('[', '-').replace(']', ''))

    cocotb_test.simulator.run(
        python_search=[tests_dir],
        verilog_sources=verilog_sources,
        toplevel=toplevel,
        module=module,
        parameters=parameters,
        sim_build=sim_build,
        extra_env=extra_env,
    )
