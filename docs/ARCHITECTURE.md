# Architecture

`contract.py` owns all bounded JSON structures. `gate.py` is a pure evaluator and
cannot mutate state. `transaction.py` is the only mutation boundary; it requires a
verified `ready` artifact. `cli.py` exposes the same API to local automation, and
`probes.py` exercises the complete lifecycle with synthetic data.

The snapshot producer and the gate remain separate. The producer records observed
facts; the gate decides under an explicit policy. This prevents a partial upstream
failure from being interpreted as a passing merge condition.

