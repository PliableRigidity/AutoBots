# Procurement Checklist — Autonomous Antweight Combat Robot

Status labels:
- **OWNED** — In hand now
- **ORDERED** — Already ordered / in cart
- **REQUIRED** — Needed for the primary build; not yet ordered
- **OPTIONAL** — Useful spare or upgrade; not blocking
- **REMOVED** — Was on a previous list; no longer required for the primary system

---

## Robot Onboard Hardware

| Status | Item | Qty | Notes |
|---|---|---|---|
| OWNED | N20 brushed geared motors | 2 | Original motors. Specification unknown — measure stall current (Gate 1) |
| OWNED | 6 V NiMH pack (5-cell) | 1 | Capacity and Rₘ unknown — measure before Phase 2 |
| OWNED | Antweight chassis/body | 1 | Mass, track width, wheel radius all still to measure |
| ORDERED | ESP32-C3 Super Mini | 4 | 1 onboard, 1 base station, 2 spares |
| ORDERED | DRV8833 dual H-bridge module | 10 | Current motor driver plan. Gate 1: measure stall current first |
| ORDERED | D-shaft N20 wheels | 10 | Match existing motor shaft; keep identical spares |
| REQUIRED | LSM6DS3 breakout / module (SPI accessible) | 1–2 | Preferred IMU — check university supplier first. 1 onboard, 1 spare |
| REQUIRED | Compact 2.4 GHz ExpressLRS receiver with CRSF UART | 1–2 | 1 onboard + 1 spare. Required before Phase 2. Confirm LQ/RSSI output via CRSF. Size/weight critical for antweight |
| REQUIRED | Logic regulator module, 3.3 V out, ≥500 mA, input 4–8 V | 2 | Buck type (MP1584 / TPS62203 class) preferred; check dropout vs. sagged pack. Buy two — you will kill one |
| REQUIRED | Physical master disconnect / removable link, ≥5 A | 2 | Layer 1 safety. Non-negotiable. 1 final + 1 spare |
| OPTIONAL | Spare N20 motors matching existing pair | 2 | Buy only if originals are not matched; useful before competition |
| OPTIONAL | ELRS transmitter / module | — | **Confirm you already own a compatible TX before ordering RX.** Required for every manual override test session |

---

## Robot PCB

| Status | Item | Notes |
|---|---|---|
| REQUIRED | 1× Robot main/control PCB | Compact carrier board combining ESP32-C3 module, DRV8833, regulator/power distribution, LSM6DS3 or IMU connector, ELRS RX connector, battery voltage sensing, motor connectors, disconnect/power input. Module-based is fine — reduces risk. Priority: compact and reliable, not fully discrete |
| OPTIONAL | Custom PCB (robot main) | Only after the protoboard/module version is proven stable |

---

## External Vision and Setup

| Status | Item | Qty | Notes |
|---|---|---|---|
| OWNED | Logitech C525 webcam | 1 | Confirmed. Manual exposure working. Do not replace unless Phase 4 measurements show it is a limiting factor |
| OWNED | Laptop | 1 | Runs vision, fusion, control |
| OPTIONAL | Rigid clamp mount or heavy tripod | 1 | Important — a bumped camera silently breaks calibration. Mark mount position on the floor. Do not economise |
| OPTIONAL | Circular polarizing filter (match C525 thread) | 1 | Cuts acrylic specular glare substantially. Cheap and high-value — buy it |
| OPTIONAL | LED panel light, dimmable | 1–2 | Enables short exposure (≤3 ms). Check event rules first |
| OPTIONAL | AprilTag prints, matte | many | Print plenty of spares; they get scuffed |
| OPTIONAL | Checkerboard calibration target on rigid board | 1 | For camera intrinsic calibration |

---

## Makerspace / University (assume available — do not budget)

| Item |
|---|
| Multimeter with 10 A range or 0.1 Ω shunt for current measurement |
| Bench power supply with current limit |
| Oscilloscope |
| Logic analyser |
| Soldering iron, wire strippers, callipers, kitchen scale |
| Standard resistors, capacitors, hookup wire, headers, solder, heatshrink |

---

## No Longer Required for Primary System

These were on the previous list because ultrasonic TDOA was a required subsystem. TDOA is now optional/future. Do not buy unless the vision-only system proves insufficient and a TDOA research track is deliberately resumed.

| Status | Item | Notes |
|---|---|---|
| REMOVED | 40 kHz TX transducers (Murata MA40S4S or generic) | No longer required |
| REMOVED | 40 kHz RX transducers (Murata MA40S4R or generic) | No longer required |
| REMOVED | RP2040 / Raspberry Pi Pico (TDOA timing MCU) | No longer required |
| REMOVED | Op-amps (MCP6022 / TLV2372) for TDOA AFE | No longer required for TDOA. Only buy if a specific analogue front end is needed for something else |
| REMOVED | Comparator ICs (TDOA edge detection) | No longer required |
| REMOVED | External simultaneous-sampling quad ADC | No longer required |
| REMOVED | DS18B20 temperature sensor (TDOA speed-of-sound correction) | No longer required |
| REMOVED | C0G/NP0 filter capacitors (TDOA AFE) | No longer required for TDOA; normal decoupling capacitors are still needed |
| REMOVED | Shielded cable / BNC for TDOA receive chain | No longer required |
| REMOVED | 4× TDOA receiver-node PCBs | No longer required |
| REMOVED | 1× Central TDOA acquisition/timing PCB | No longer required |
| REMOVED | Ultrasonic TX driver (logic-level MOSFETs for burst drive) | No longer required |
| REMOVED | Acoustic absorber foam | No longer required |

---

## Buying Discipline

1. **Measure stall current before assuming DRV8833 will survive competition conditions** (Gate 1). Do not buy a stronger driver speculatively — measure first, select on evidence.
2. **Order the ELRS receiver before Phase 2.** It is needed for the command arbitration framework. Confirm you own a compatible TX transmitter first.
3. **Buy the LSM6DS3 before Phase 2.** Check university/makerspace supplier first — may already be available without ordering.
4. **Do not buy TDOA hardware** unless the vision system is completed and proven insufficient, and a deliberate TDOA research track is started with its own time budget.
5. **Do not buy a new camera.** C525 is confirmed. Re-evaluate only if Phase 4 measurements show it is a hard limit.
6. **Buy spares of anything that gets soldered in** — IMU breakouts, regulators. A $3 part blocking a weekend is a bad trade.
