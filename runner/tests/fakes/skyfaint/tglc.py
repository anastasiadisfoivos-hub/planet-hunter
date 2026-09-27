"""Stand-in for skyfaint.tglc: the fake hunt's light curve, through the same FaintLC.to_hunt() call."""
from hunt import lightcurve


class FaintLC:
    def __init__(self, tic):
        self.tic = tic

    def to_hunt(self):
        return lightcurve.stitch(self.tic)


def get_lightcurves(tic, **_):
    return FaintLC(int(tic))
