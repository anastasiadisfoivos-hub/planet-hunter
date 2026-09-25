"""Every credit line and licence this package emits, with where the terms were read (2026-09-25)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Credit:
    credit: str
    license: str
    terms_url: str


RUBIN = Credit(
    "NSF–DOE Vera C. Rubin Observatory / LSST; cutout served by the Fink broker",
    "World-public Rubin alert data, no proprietary period; credit Rubin Observatory and Fink",
    "https://rubinobservatory.org/for-scientists/data-products/alerts-and-brokers",
)
ZTF = Credit(
    "Zwicky Transient Facility (Caltech / Palomar Observatory); cutout served by the Fink broker",
    "ZTF public alert stream: public data; credit ZTF and Fink",
    "https://www.ztf.caltech.edu/ztf-public-releases.html",
)

# hips2fits cuts: obs_copyright / obs_copyright_url / hips_license from each HiPS `properties`.
DSS2 = Credit(
    "Digitized Sky Survey (STScI/NASA; POSS-II Caltech/Palomar, UK Schmidt AAO/ROE), colour HiPS by CDS; "
    "cut with CDS hips2fits",
    "DSS plates © AURA, Caltech, AAO and UK PPARC; use with the STScI DSS acknowledgement; HiPS ODbL-1.0 (CDS)",
    "http://archive.stsci.edu/dss/copyright.html",
)
PANSTARRS = Credit(
    "Pan-STARRS1 DR1 (PS1 Science Consortium, via MAST/STScI), colour HiPS by CDS; cut with CDS hips2fits",
    "PS1 public data release, acknowledgement required; HiPS ODbL-1.0 (CDS)",
    "https://panstarrs.stsci.edu/",
)
LEGACY = Credit(
    "DESI Legacy Imaging Surveys DR10, colour HiPS by CDS; cut with CDS hips2fits",
    "Legacy Surveys public data, acknowledgement required; HiPS ODbL-1.0 (CDS)",
    "https://www.legacysurvey.org/acknowledgment/",
)

SDO = Credit(
    "Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams",
    "Not copyrighted (NASA SDO image-use rules); credit line required",
    "https://sdo.gsfc.nasa.gov/data/rules.php",
)
SDO_HELIOVIEWER = Credit(
    "Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams; rendered by Helioviewer.org",
    "Not copyrighted (NASA SDO image-use rules); credit line required",
    "https://sdo.gsfc.nasa.gov/data/rules.php",
)
LASCO = Credit(
    "SOHO/LASCO (ESA & NASA); rendered by Helioviewer.org",
    "SOHO data are free to use with credit to SOHO (ESA & NASA)",
    "https://soho.nascom.nasa.gov/data/data.html",
)
NOAA_OVATION = Credit(
    "NOAA Space Weather Prediction Center, OVATION aurora model",
    "Public domain (U.S. Government work, 17 U.S.C. §105); credit NOAA SWPC",
    "https://www.swpc.noaa.gov/products/aurora-30-minute-forecast",
)

ALL = {
    "rubin": RUBIN,
    "ztf": ZTF,
    "dss2": DSS2,
    "panstarrs": PANSTARRS,
    "legacy": LEGACY,
    "sdo": SDO,
    "sdo_helioviewer": SDO_HELIOVIEWER,
    "lasco": LASCO,
    "noaa_ovation": NOAA_OVATION,
}
