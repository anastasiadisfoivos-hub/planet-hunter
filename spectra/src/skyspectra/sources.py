"""Provenance for every file: source, credit, licence. One place, so files and README agree."""

from __future__ import annotations

SOURCES: dict[str, dict[str, str]] = {
    "nist": {
        "source": "NIST Atomic Spectra Database (ASD), lines query - https://physics.nist.gov/asd",
        "credit": "Kramida, A., Ralchenko, Yu., Reader, J. and NIST ASD Team, NIST Atomic Spectra Database, "
                  "National Institute of Standards and Technology, Gaithersburg, MD. "
                  "DOI: https://doi.org/10.18434/T4W30F",
        "licence": "NIST Standard Reference Data, freely accessible online; cite as above. Copyright protection "
                   "on this compilation of data has been secured by the Secretary of the U.S. Department of "
                   "Commerce on behalf of the United States in the United States and all countries that are "
                   "parties to the Universal Copyright Convention, pursuant to Section 290(e) of Title 15 of "
                   "the United States Code.",
    },
    "kurucz": {
        "source": "Kitt Peak Solar Flux Atlas 2005 (R. L. Kurucz), file solarfluxintwl.asc - "
                  "http://kurucz.harvard.edu/sun/fluxatlas2005/",
        "credit": "Kurucz, R. L. 2005, 'New atlases for solar flux, irradiance, central intensity, and limb "
                  "intensity', Mem. Soc. Astron. Ital. Suppl. 8, 189; from the NSO/Kitt Peak FTS solar flux "
                  "atlas of Kurucz, Furenlid, Brault & Testerman (1984). NSO/Kitt Peak FTS data produced by "
                  "NSF/NOAO.",
        "licence": "No licence stated; distributed publicly by R. L. Kurucz (Harvard-Smithsonian CfA) for "
                   "scientific use. Cite Kurucz (2005).",
    },
    "hypatia": {
        "source": "Hypatia Catalog API v2 (composition, solar normalisation Lodders et al. 2009) - "
                  "https://hypatiacatalog.com/api",
        "credit": "Hinkel, N. R., Timmes, F. X., Young, P. A., Pagano, M. D. & Turnbull, M. C. 2014, AJ 148, 54 "
                  "(The Hypatia Catalog); abundances compiled from the literature catalogues listed per value.",
        "licence": "Free public access, no key (API v2.2). No explicit licence stated; the Hypatia team asks "
                   "that Hinkel et al. (2014) be cited.",
    },
    "gaia": {
        "source": "Gaia DR3 XP sampled mean spectra (xp_sampled_mean_spectrum) via the ESA Gaia Archive "
                  "DataLink - https://gea.esac.esa.int/data-server/data?RETRIEVAL_TYPE=XP_SAMPLED",
        "credit": "This work has made use of data from the European Space Agency (ESA) mission Gaia "
                  "(https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis "
                  "Consortium (DPAC). Gaia Collaboration, De Angeli et al. 2023, A&A 674, A2; "
                  "Montegriffo et al. 2023, A&A 674, A3.",
        "licence": "CC BY-SA 3.0 IGO (ESA Gaia data licence)",
    },
    "nea": {
        "source": "NASA Exoplanet Archive, Atmospheric Spectroscopy table (TAP table 'spectra', "
                  "spec_type = Transmission) and its spectrum files - "
                  "https://exoplanetarchive.ipac.caltech.edu/cgi-bin/atmospheres/nph-firefly?atmospheres",
        "credit": "This research has made use of the NASA Exoplanet Archive, which is operated by the "
                  "California Institute of Technology, under contract with NASA under the Exoplanet "
                  "Exploration Program. Each spectrum: see its reference/bibcode.",
        "licence": "NASA Exoplanet Archive data are public and free to use with the acknowledgement above; "
                   "cite the original paper of each spectrum.",
    },
}


def meta(name: str, **extra) -> dict:
    return {**SOURCES[name], **{k: v for k, v in extra.items() if v is not None}}
