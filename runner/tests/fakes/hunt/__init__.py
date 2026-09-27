"""A stand-in for hunt/ in the runner's tests: the same entry points and output shapes the runner uses, no
network, deterministic by TIC. TIC % 7 == 0: no data. TIC % 5 == 0: one periodic candidate (TIC % 10 == 0 also a
promising sub-threshold signal). TIC % 11 == 0: raises (an error, retried). FAKE_HUNT_SLEEP seconds per star."""
