import type { CatchType } from "@/lib/contract";

export const TYPE_LABEL: Record<CatchType, string> = {
  asteroid: "Asteroid",
  near_earth_object: "Near-Earth object",
  trans_neptunian_object: "Trans-Neptunian object",
  comet: "Comet",
  interstellar_object: "Interstellar object",
  supernova: "Supernova",
  active_galaxy: "Active galaxy",
  tidal_disruption_event: "Tidal disruption event",
  microlensing: "Microlensing event",
  kilonova: "Kilonova",
  variable_star: "Variable star",
  flare: "Stellar flare",
  eclipsing_binary: "Eclipsing binary",
  planet_candidate: "Planet candidate",
  unknown: "Something unclassified",
};

/** Rubin scheduler footprint regions (labels from rubin_scheduler.get_current_footprint). */
export const REGION_LABEL: Record<string, string> = {
  lowdust: "Wide-Fast-Deep, low dust",
  dusty_plane: "Galactic plane",
  bulgy: "Galactic bulge",
  nes: "North ecliptic spur",
  scp: "South celestial pole",
  LMC_SMC: "Magellanic Clouds",
  virgo: "Virgo cluster",
  euclid_overlap: "Euclid overlap",
  outside: "Not covered",
};
