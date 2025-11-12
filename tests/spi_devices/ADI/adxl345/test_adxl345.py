# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2023 Spencer Chang
import logging
import os

import cocotb
import cocotb_test.simulator
from cocotb.triggers import Timer

from cocotbext.spi import SpiBus
from cocotbext.spi import SpiConfig
from cocotbext.spi import SpiMaster
from cocotbext.spi.devices.ADI import ADXL345


class TB:
    def __init__(self, dut):
        self.dut = dut
        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self.bus = SpiBus.from_entity(dut, cs_name="ncs")

        self.config = SpiConfig(
            word_width=8,
            sclk_freq=25e6,
            cpol=True,
            cpha=True,
            msb_first=True,
            cs_active_low=True,
        )

        self.source = SpiMaster(self.bus, self.config)
        self.sink = ADXL345(self.bus)


@cocotb.test()
async def run_test_adxl345(dut):
    tb = TB(dut)
    await Timer(10, 'us')

    # test a single byte read
    await tb.source.write([tb.sink.create_spi_command("read", 0x00), 0x00], burst=True)
    read_word = (await tb.source.read(2))[1]
    assert read_word == 0b1110_0101

    # await the necessary time between transactions
    await Timer(200, units='ns')

    # test a multibyte read
    await tb.source.write(
        [
            tb.sink.create_spi_command("read", 0x2C, multibyte=True),
            0x00, 0x00, 0x00, 0x00, 0x00,
        ], burst=True,
    )
    read_word = (await tb.source.read(6))[1:]
    assert list(read_word) == [0b0000_1010, 0x00, 0x00, 0x00, 0b0000_0010]

    await Timer(200, units='ns')

    # test a multibyte write
    await tb.source.write([tb.sink.create_spi_command("write", 0x1e, multibyte=True), 0x01, 0b11, 0xAA], burst=True)
    assert (await tb.sink.get_register(0x1e)) == 0x01
    assert (await tb.sink.get_register(0x1f)) == 0b11
    assert (await tb.sink.get_register(0x20)) == 0xAA

    await Timer(5, 'us')


# cocotb-test

tests_dir = os.path.dirname(__file__)


def test_adxl345(request):
    dut = "test_adxl345"
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
