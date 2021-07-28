#!/usr/bin/env python


import logging
import os

import cocotb_test.simulator

import cocotb
from cocotb.triggers import Timer
from cocotb.regression import TestFactory

from cocotbext.spi import SpiMaster, SpiSignals, SpiConfig
from cocotbext.spi.devices.TI import DRV8304, ADS8028


class TB_DRV8304:
    def __init__(self, dut):
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
            word_width=16,
            sclk_freq=25e6,
            cpol=False,
            cpha=True,
            msb_first=True
        )

        self.source = SpiMaster(self.signals, self.config)
        self.sink = DRV8304(self.signals)


class TB_ADS8028:
    def __init__(self, dut):
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
            word_width=16,
            sclk_freq=25e6,
            cpol=False,
            cpha=True,
            msb_first=True
        )

        self.source = SpiMaster(self.signals, self.config)
        self.sink = ADS8028(self.signals)


@cocotb.test()
async def run_test_drv8304(dut):
    tb = TB_DRV8304(dut)
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


@cocotb.test()
async def run_test_ads8028(dut):
    tb = TB_ADS8028(dut)
    await Timer(10, 'us')

    address_mask = 0xF000
    data_mask = 0x0FFF

    await tb.source.write([tb.sink.create_spi_word("write", 0b111100011100100)])
    _ = await tb.source.read()

    await Timer(20, units='ns')

    await tb.source.write([tb.sink.create_spi_word("read", 0x0000)])
    _ = await tb.source.read()

    await Timer(20, units='ns')

    await tb.source.write([tb.sink.create_spi_word("read", 0x0000)])
    ain0 = (await tb.source.read())[0]
    assert ain0 & address_mask == 0 << 12
    assert ain0 & data_mask == 0

    await Timer(20, units='ns')

    await tb.source.write([tb.sink.create_spi_word("read", 0x0000)])
    ain1 = (await tb.source.read())[0]
    assert ain1 & address_mask == 1 << 12
    assert ain1 & data_mask == 1

    await Timer(5, 'us')

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
