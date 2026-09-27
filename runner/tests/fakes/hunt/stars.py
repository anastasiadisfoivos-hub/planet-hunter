from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Star:
    tic: int
    ra: float = 10.0
    dec: float = -20.0
    tmag: float | None = 10.5
    teff: float | None = 3500.0
    rad: float | None = 0.4

    def to_row(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> Star:
        def num(k, d):
            v = row.get(k)
            return float(v) if v not in (None, "") else d
        return cls(int(row["tic"]), num("ra", 10.0), num("dec", -20.0), num("tmag", 10.5), num("teff", 3500.0),
                   num("rad", 0.4))


def star(tic: int) -> Star:
    return Star(int(tic), ra=(tic % 360) * 1.0, dec=((tic % 170) - 85) * 1.0)
