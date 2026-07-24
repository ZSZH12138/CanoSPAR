# Historical blocker report — recovered by authorized waiver (2026-07-24)

Status: historical measurement retained; the implementation may proceed because
the user explicitly waived the 6 GiB `available_ram_gib` gate on 2026-07-24.
The original gate result remains `gate_passed: false`; its effective status is
recorded separately as `effective_gate_passed: true` in
`reports/week1/hardware_gate.json`.

# CanoSPAR Week 1 implementation blocker report

## 1. Historical blocking reason

The hardware gate did not pass at measurement time: repeated available-memory
checks were below the required 6 GiB minimum. The user-authorized waiver above
resolves the implementation block only; it does not alter the original result.

## 2. Measured data (retained unchanged)

| Check | Measured value | Threshold or conclusion |
|---|---:|---|
| Operating system | Microsoft Windows 11 Education, 64-bit | Supported |
| CPU | 6 physical cores, 12 logical cores | Passed (minimum 2 logical cores) |
| Total RAM | 15.75 GiB | Meets recommended total RAM |
| Available RAM | 1.95, 1.11, 0.96, 0.88 GiB | Failed the mandatory 6 GiB gate |
| Free disk | 183.74 GiB | Passed (minimum 12 GiB) |
| GPU | Detected | Not required in this phase |
| CUDA | Not available | Not required in this phase |
| Git | Available | Available |
| Conda | Available | Isolated environment can be created |
| Docker | Available | Container build is not required this week |
| Apptainer | Not available | Container build is not required this week |

The machine-readable source of the measurements is
`reports/week1/hardware_gate.json`. This report contains no user name, host
name, token, or sensitive absolute path.

## 3. Recovery record

On 2026-07-24, the user explicitly waived only the `available_ram_gib` check.
Accordingly, `gate_passed` remains `false` for audit accuracy while
`effective_gate_passed` is `true` for the authorized Week 1 work scope.
