// The methods notebook's structure. The words come from the PLAN session: fill `body` (paragraphs) per section.
// Until a section has a body, the page says so instead of guessing.

export type MethodSection = { id: string; title: string; asks: string; body: string[]; link?: { href: string; text: string } };

export const METHODS: MethodSection[] = [
  { id: "data", title: "The data", asks: "Which TESS light curves the search reads, and how they are cleaned.", body: [] },
  { id: "search", title: "Finding dips", asks: "How repeating dips are found and how strong one must be.", body: [] },
  { id: "checks", title: "The checks", asks: "Each test a signal must pass before it is kept.", body: [] },
  { id: "known", title: "Already known", asks: "The lists of planets, candidates and binaries a signal is compared against.", body: [] },
  { id: "pixels", title: "The pixel check", asks: "How the TESS pixels show which star the light went missing from.", body: [] },
  { id: "vetting", title: "Vetting", asks: "LEO, TRICERATOPS, Gaia and variability catalogues.", body: [] },
  { id: "votes", title: "Votes", asks: "What people's votes are for, and why counts appear only after voting.", body: [] },
  {
    id: "limits",
    title: "What it cannot find",
    asks: "Sizes and periods the search misses, from hiding fake planets in real data.",
    body: [],
    link: { href: "/sensitivity", text: "The sensitivity grid" },
  },
  { id: "honesty", title: "Candidate, not planet", asks: "Why nothing here is called a discovery.", body: [] },
];
