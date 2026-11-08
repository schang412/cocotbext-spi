# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2023 Spencer Chang
import logging
import pathlib

import cocotb
from cocotb.triggers import Timer
from cocotb_tools._pytest.hdl import HDL
import pytest

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
    await Timer(10, "us")

    # test a single byte read
    await tb.source.write([tb.sink.create_spi_command("read", 0x00), 0x00], burst=True)
    read_word = (await tb.source.read(2))[1]
    assert read_word == 0b1110_0101

    # await the necessary time between transactions
    await Timer(200, unit="ns")

    # test a multibyte read
    await tb.source.write(
        [
            tb.sink.create_spi_command("read", 0x2C, multibyte=True),
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ],
        burst=True,
    )
    read_word = (await tb.source.read(6))[1:]
    assert list(read_word) == [0b0000_1010, 0x00, 0x00, 0x00, 0b0000_0010]

    await Timer(200, unit="ns")

    # test a multibyte write
    await tb.source.write(
        [tb.sink.create_spi_command("write", 0x1E, multibyte=True), 0x01, 0b11, 0xAA],
        burst=True,
    )
    assert (await tb.sink.get_register(0x1E)) == 0x01
    assert (await tb.sink.get_register(0x1F)) == 0b11
    assert (await tb.sink.get_register(0x20)) == 0xAA

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
