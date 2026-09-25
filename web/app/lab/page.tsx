import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import { DemoTag, Tag } from "@/components/ui";
import { Intro } from "@/components/lab/Intro";
import { FingerprintThumb, HearThumb, HubbleThumb, ThermoThumb } from "@/components/lab/Thumbs";
import s from "@/components/lab/lab.module.css";

export const metadata: Metadata = {
  title: "Lab · Planet Hunter",
  description: "Small experiments with real starlight: a star thermometer, a light curve you can hear, a Hubble diagram and chemical fingerprints.",
};

const ITEMS = [
  {
    href: "/lab/thermometer",
    title: "Star thermometer",
    text: "Slide a temperature from 2,000 to 40,000 K and watch the light shift from red to blue. Then find real stars on the same scale.",
    thumb: <ThermoThumb />,
    data: "real",
  },
  {
    href: "/lab/hear-a-star",
    title: "Hear a star",
    text: "A TESS light curve played as sound. Brightness is pitch, so each time a planet crosses its star you hear the note drop.",
    thumb: <HearThumb />,
    data: "real",
  },
  {
    href: "/lab/hubble",
    title: "Hubble diagram",
    text: "Plot supernovae by brightness and redshift, draw a line through them, and read off how fast the universe is expanding.",
    thumb: <HubbleThumb />,
    data: "demo",
  },
  {
    href: "/lab/fingerprints",
    title: "Chemical fingerprints",
    text: "Every element leaves its own barcode in light. Read the Sun's, compare a star's recipe with it, and see what is in a planet's air.",
    thumb: <FingerprintThumb />,
    data: "demo",
  },
] as const;

export default function LabIndex() {
  return (
    <>
      <Intro title="Lab" data="mixed">
        Four small experiments with starlight. They use the same stars and the same analysis results as the sky map.
      </Intro>
      <ul className={s.list}>
        {ITEMS.map((it) => (
          <li key={it.href}>
            <Link href={it.href} className={s.item}>
              {it.thumb}
              <span className={s.itemText}>
                <span className={s.itemTitle}>{it.title}</span>
                <span className={s.body}>{it.text}</span>
                <span className={s.itemMeta}>{it.data === "demo" ? <DemoTag /> : <Tag>Real data</Tag>}</span>
              </span>
              <ArrowRight className={s.itemArrow} size={20} aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
      <p className={`${s.help} ${s.footnote}`}>
        Demo data marks experiments that run on stand-in numbers until their real sources are connected: live supernovae from the Transient Name
        Server, and measured spectra.
      </p>
    </>
  );
}
