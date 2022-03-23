# Timing Diagrams

The following images are sourced from [Analog Devices](https://www.analog.com/en/analog-dialogue/articles/introduction-to-spi-interface.html)



## SPI Mode 0

![spi_mode0](spi_mode0.png)

| MODE=0 | Value | Definition                                      |
| ------ | ----- | ----------------------------------------------- |
| CPOL   | 0     | Clock Idle State = LOW                          |
| CPHA   | 0     | Data Sampled on Rising, Data Shifted on Falling |


## SPI Mode 1

![spi_mode1](spi_mode1.png)

| MODE=1 | Value | Definition                                      |
| ------ | ----- | ----------------------------------------------- |
| CPOL   | 0     | Clock Idle State = LOW                          |
| CPHA   | 1     | Data Sampled on Falling, Data Shifted on Rising |



## SPI Mode 2

![spi_mode2](spi_mode2.png)

| MODE=2 | Value | Definition                                      |
| ------ | ----- | ----------------------------------------------- |
| CPOL   | 1     | Clock Idle State = HIGH                         |
| CPHA   | 0     | Data Sampled on Rising, Data Shifted on Falling |


## SPI Mode 3

![spi_mode3](spi_mode3.png)

| MODE=3 | Value | Definition                                      |
| ------ | ----- | ----------------------------------------------- |
| CPOL   | 1     | Clock Idle State = HIGH                         |
| CPHA   | 1     | Data Sampled on Falling, Data Shifted on Rising |