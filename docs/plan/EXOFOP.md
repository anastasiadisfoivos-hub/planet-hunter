# ExoFOP: can we submit CTOIs, and what makes one a TOI?

Checked 2026-09-26 against the live pages. **Short answer: a refereed paper is now required.** The earlier
session was right, and the TESS TOI FAQ is out of date on this point.

## 1. Current rule (ExoFOP, primary source)

ExoFOP news, **August 19, 2026** (https://exofop.ipac.caltech.edu/tess/news.php, also on the ExoFOP-TESS home page
https://exofop.ipac.caltech.edu/tess/):

> "ExoFOP has reopened support for community planet candidates from TESS, Kepler, K2, and beyond. To ensure the
> quality and utility of candidates uploaded to ExoFOP for the community, going forward candidates must first be
> published in a peer-reviewed journal with online access before being uploaded to ExoFOP, and approval to upload
> candidates is required."

It came after a pause. ExoFOP news, **March 31, 2026**:

> "ExoFOP has temporarily paused the functionality for users to upload new planet candidates (CTOIs and other
> projects)."

The Candidate Guidelines (https://exofop.ipac.caltech.edu/tess/candidate_help.php; the old `ctoi_help.php` now
redirects there) say:

> "Candidates must be published in a peer-reviewed journal that offers online access before being uploaded to
> ExoFOP."

> "ExoFOP will only allow upload of Community Candidates accepted and published in the refereed literature. The URL
> link to the paper must be provided."

> "To request access to submit published candidates, complete the Published Candidate Upload Request. After
> approval, then you can submit candidates."

The request form (https://exofop.ipac.caltech.edu/tess/pub_candidate_upload_request.php) needs an ExoFOP login.

### What an upload must contain

- A TIC-based name (`TIC nnn.nn`), a discovery data source (TESS by default), a tag, a **paper URL (required)**
  and an initial note.
- At least 2 of period, mid-transit time (BJD) and depth (ppm). For **cTOI consideration by the TOI working
  group**: "all four of orbital period, transit epoch, transit depth, and transit duration must be included and
  greater than zero (0)."
- Cross-check against existing candidates, TOIs and confirmed planets. Aliases (2×, 3×) of a known period get
  added as a parameter set on the existing object, not as a new candidate. "Duplicate objects will be removed,
  and repeated duplications may lead to suspension of your account."
- Supporting material (a light curve with the fitted transit) uploaded to the star under the same tag. "Without
  supporting material, candidates may be removed."
- No lowercase letters ('b', 'c') before a planet is confirmed in refereed literature. Disposition PC or FP
  only, never CP.

## 2. The conflicting source (out of date)

TESS TOI Release FAQ (https://tess.mit.edu/toi-releases/toi-release-faqs/):

> "If you find a planet candidate submit it to ExoFOP-TESS. Your candidate will become a community TOI (cTOI).
> The candidate will be reviewed by the TESS TOI Team where if it meets the team standard it will be assigned
> TOI number."

It does not mention the publication requirement. ExoFOP runs the upload, so its 19 August 2026 rule is the one
in force. The FAQ is still right that the **TOI team** decides on promotion.

## 3. What gets a CTOI promoted to a TOI

Guerrero et al. 2021, *The TESS Objects of Interest Catalog from the TESS Prime Mission*, ApJS 254, 39,
doi:10.3847/1538-4365/abefe1, §8 (arXiv:2103.12538):

> "The TOI team periodically checks for matches on TIC ID and period between the CTOI list hosted on ExoFOP and
> the comprehensive collection of TCEs considered for vetting on the TEV platform."

> "The vetting team may promote a CTOI to a TOI if the CTOI identifies a quality planet candidate from the SPOC or
> QLP pipeline mistakenly ruled out in the triage or vetting process."

> "All CTOIs which have been promoted to TOIs were also TCEs in the SPOC pipeline or the QLP, and recovered from
> those pipelines."

> "169 CTOIs from the Prime Mission are now TOIs; 106 of these were recovered from TCEs mistakenly ruled out in
> pre-vetting triage."

> "CTOIs which do not match with TCEs on TEV, and which also do not have data products from either the QLP or SPOC
> pipeline, could still be valid events, but were not found in the initial run of either pipeline, and would need to
> be recovered manually in a reprocessing step."

In practice, a CTOI gets promoted when:

1. It has all four parameters (period, epoch, depth, duration), which the guidelines now make explicit.
2. The signal matches a SPOC or QLP TCE (a Threshold Crossing Event) on the same TIC with the same period. Every
   promotion in the Prime Mission did.
3. It passes the TOI team's own vetting standard (Guerrero et al. 2021, §4–5): transit-like, not an EB (no
   secondary, consistent odd/even), not off target, not a known object or an alias.

A signal found only in data SPOC and QLP never produced (for example a TGLC light curve of a Tmag 15 star) has
no precedent for promotion. It would stay a CTOI at best.

## 4. What this means for planet-hunter

- **We cannot upload candidates straight from the nightly sweep.** Each one would first need a refereed paper,
  and ExoFOP has to approve the uploader account.
- The realistic path is to **batch the best-vetted candidates into one paper**: the search, the injection-recovery
  sensitivity, pixel-level vetting, Gaia checks, and a table of periods, epochs, depths and durations with
  uncertainties. Submit it to a refereed journal (AJ, MNRAS, A&A). RNAAS notes are editor-moderated rather than
  peer-reviewed, so they probably do not meet the rule; ask exofop-support@ipac.caltech.edu before relying on one.
  After acceptance, request upload access and bulk-upload with the paper URL.
- Until then, the app should say "candidate (not submitted)". Candidates that match an existing SPOC/QLP TCE
  have the best odds of later becoming TOIs, so it is worth recording that in each candidate JSON.
- Open question for ExoFOP support: does the TOI team still review candidates sent to it outside ExoFOP? None
  of the pages checked describe a channel other than a published upload.
