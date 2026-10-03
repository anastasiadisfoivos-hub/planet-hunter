import type { HTMLAttributes } from "react";
import s from "./ui.module.css";

export type TagProps = HTMLAttributes<HTMLSpanElement> & {
  /** neutral by default. demo: dashed, for mock data. */
  tone?: "neutral" | "accent" | "rubin" | "supernova" | "demo";
};

/** Small mono uppercase label. */
export function Tag({ tone = "neutral", className, ...rest }: TagProps) {
  return <span className={[s.tag, tone !== "neutral" && s[`tag-${tone}`], className].filter(Boolean).join(" ")} {...rest} />;
}

/** The standard marker for mock data. Use it next to anything that isn't real yet. */
export function DemoTag() {
  return (
    <Tag tone="demo" title="Made-up numbers for testing. Real data arrives with the api service.">
      Demo data
    </Tag>
  );
}
